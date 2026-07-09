from machine import Pin
import network
import time
import socket
import BlynkLib
import urequests as requests

# -----------------------------
# Konfiguration & Variablen
# -----------------------------
button = Pin(22, Pin.IN, Pin.PULL_UP)

SSID = "Tim"
PASSWORD = "Wlan1234Hotspot"

AP_SSID = "mainesp"
AP_PASSWORD = "esp32ap1"

BLYNK_AUTH = "Qy7NNe7keW3_bgbvWFnX5Pb3B_iAPQLH"

BLYNK_INTERVAL = 5000 

werteTempLight = [
    ("temperatur", 2), 
    ("luftfeuchtigkeit", 3), 
    ("lichtwert", 4), 
    ("rollo", 5), 
    ("lampe", 6)
]

wertePVmanager = [
    ("temperatur", 1),
    ("pv_leistung", 0),
    ("klimastate", 8)
]

werteLueftung = [
    ("led", 11),
    ("feuchtigkeit", 12),
    ("temperatur", 13),
    ("luftqualität", 14)
]

blynk_sende_puffer = {}

# -----------------------------
# Hilfsfunktionen
# -----------------------------
def log(*args):
    text = " ".join(str(a) for a in args)
    print(text)
    with open("log.txt", "a") as f:
        f.write(text + "\n")


def logData(*args):
    text = " ".join(str(a) for a in args)
    print(text)
    with open("daetensaetze.txt", "a") as f:
        f.write(text + "\n")


def zeitstempel():
    y, mo, d, h, mi, s, wd, yd = time.localtime()
    return "{:04d}-{:02d}-{:02d} {:02d}:{:02d}:{:02d}".format(y, mo, d, h, mi, s)


def zeitstempel_url():
    y, mo, d, h, mi, s, wd, yd = time.localtime()
    return "{:04d}-{:02d}-{:02d}_{:02d}:{:02d}:{:02d}".format(y, mo, d, h, mi, s)


def datensatz_parsen(line):
    teile = line.strip().split(";")
    if len(teile) != 3:
        return None

    sender = teile[0].strip()
    attribut = teile[1].strip().lower()
    wert_text = teile[2].strip()

    try:
        if "." in wert_text:
            attributwert = float(wert_text)
        else:
            attributwert = int(wert_text)
    except:
        attributwert = wert_text

    return sender, attribut, attributwert


def sende_an_esp(client_sock, ip, nachricht):
    try:
        if isinstance(nachricht, bytes):
            data = nachricht
        else:
            data = str(nachricht).encode()
        client_sock.send(data + b"\n")
        print("Gesendet an", ip, ":", nachricht)
        return True
    except:
        print("Senden direkt fehlgeschlagen an", ip)
        schliesse_client(client_sock, ip)
        return False


def schliesse_client(client_sock, ip):
    print("Entferne Client-Verbindung sauber. IP:", ip)
    if client_sock in verbundene_esps:
        verbundene_esps.remove(client_sock)
    if client_sock in puffer_pro_client:
        del puffer_pro_client[client_sock]
    if client_sock in client_ips:
        del client_ips[client_sock]
    try:
        client_sock.close()
    except:
        pass


# -----------------------------
# Access Point (AP) starten
# -----------------------------
ap = network.WLAN(network.AP_IF)
ap.active(False)
time.sleep(2)
ap.active(True)
time.sleep(2)

ap.config(
    essid=AP_SSID,
    password=AP_PASSWORD,
    authmode=network.AUTH_WPA_WPA2_PSK,
    channel=1
)

time.sleep(3)

print("==========================")
print("MAIN ESP ACCESS POINT")
print("==========================")

if ap.active():
    print("WLAN aktiv | SSID:", AP_SSID, "| AP IP:", ap.ifconfig()[0])
    log("WLAN aktiv | SSID:", AP_SSID, "| AP IP:", ap.ifconfig()[0])
else:
    print("AP FEHLER!")


# -----------------------------
# Internet-WLAN (STA) verbinden
# -----------------------------
wlan = network.WLAN(network.STA_IF)
wlan.active(False)
time.sleep(1)
wlan.active(True)
time.sleep(2)

print("\nVerbinde mit Internet WLAN...")
wlan.connect(SSID, PASSWORD)

timeout = 30
while not wlan.isconnected() and timeout > 0:
    print(".", end="")
    time.sleep(1)
    timeout -= 1

if wlan.isconnected():
    print("\nInternet WLAN verbunden! IP:", wlan.ifconfig()[0])
    log("\nInternet WLAN verbunden! IP:", wlan.ifconfig()[0])
else:
    print("\nKein Internet WLAN")


# -----------------------------
# TCP Server aufsetzen
# -----------------------------
PORT = 5000
server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
server.bind(("0.0.0.0", PORT))
server.listen(4)
server.settimeout(0.05) # Kürzeres Timeout für schnellere Loops

print("\n==========================")
print("TCP SERVER STARTED")
print("==========================")
print("Port:", PORT)

verbundene_esps = []
puffer_pro_client = {}
client_ips = {} # Speichert jetzt: { client_socket: ip_adresse }

blynk = BlynkLib.Blynk(BLYNK_AUTH)

last_status_print = time.ticks_ms()
last_blynk_upload = time.ticks_ms()
zaehler = 0
fensterstate = 0
letzte_anzahl_esps = -1 


# -----------------------------
# Hauptschleife (Non-Blocking)
# -----------------------------
while True:
    try:
        blynk.run()
    except Exception as blynk_err:
        print("Blynk Run Fehler:", blynk_err)

    try:
        client, addr = server.accept()
        ip = addr[0]

        print("\nNeuer ESP verbunden | IP:", ip)
        log("\nNeuer ESP verbunden | IP:", ip)

        client.settimeout(0.0)
        verbundene_esps.append(client)
        puffer_pro_client[client] = ""
        client_ips[client] = ip # Zuordnung direkt über das Socket-Objekt!
    except OSError:
        pass

    # Daten empfangen und auswerten
    for client in verbundene_esps[:]:
        ip = client_ips.get(client, "Unbekannt")

        try:
            daten = client.recv(1024)

            # Wenn recv b"" zurückgibt, hat der Client die Verbindung getrennt
            if daten == b"":
                print("Client hat Verbindung sauber geschlossen. IP:", ip)
                schliesse_client(client, ip)
                continue

            nachricht = daten.decode()
            print("\nEmpfangen von IP:", ip, "| Daten:", nachricht)
            logData("Daten von", ip, ":", nachricht)

            puffer_pro_client[client] += nachricht

            while "\n" in puffer_pro_client[client]:
                line, puffer_pro_client[client] = puffer_pro_client[client].split("\n", 1)
                ergebnis = datensatz_parsen(line)

                if ergebnis is not None:
                    sender, attribut, attributwert = ergebnis
                    print("Geparsed -> Sender:", sender, "| Attribut:", attribut, "| Wert:", attributwert)
                    
                    # 1. Beantwortung von GET-Abfragen des PVManagers
                    if sender == "PVManager" and attribut == "get":
                        sende_an_esp(client, ip, fensterstate)
                            
                    # 2. Daten von TempLight verarbeiten
                    if sender == "TempLight":
                        for att, attw in werteTempLight:
                            if att.lower() == attribut:
                                blynk_sende_puffer[attw] = attributwert

                    # 3. FensterSensor aktualisiert den globalen Zustand und Pin 7
                    if attribut == "fensterstate":
                        fensterstate = attributwert
                        blynk_sende_puffer[7] = attributwert
                        print("Gesendet 1 + " + str(attributwert))
                    
                    # 4. Sensor-Daten des PVManagers verarbeiten
                    if sender == "PVManager" and attribut != "get":
                        for att, attw in wertePVmanager:
                            if att.lower() == attribut:
                                blynk_sende_puffer[attw] = attributwert
                    
                    if sender == "MotionD":
                        blynk_sende_puffer[15] = attributwert
                                    
                    # 5. Lüftungsdaten verarbeiten
                    if sender == "Lueftung":
                        if attribut == "get":
                            try:
                                res = requests.get(attributwert, timeout=5.0)
                                dataWea = res.content
                                res.close()
                                print("Wetterdaten erfolgreich geholt, sende an Client...")
                                sende_an_esp(client, ip, dataWea)
                            except Exception as req_err:
                                print("Internet-Abfrage fehlgeschlagen:", req_err)
                                sende_an_esp(client, ip, b"{}")
                        else:
                            for att, attw in werteLueftung:
                                if att.lower() == attribut:
                                    blynk_sende_puffer[attw] = attributwert
                    
                else:
                    print("Ungültige Zeile:", line)

        except OSError as e:
            # Fehler 11 (EAGAIN) bedeutet: Aktuell keine Daten vorhanden -> Alles okay, weitergehen.
            if len(e.args) > 0 and e.args[0] == 11:
                pass
            else:
                # Jeder andere Fehler (z.B. 104 ECONNRESET) bedeutet, der Client ist tot!
                print("Verbindung verloren (OSError {}) zu IP:".format(e.args[0] if e.args else "Unbekannt"), ip)
                schliesse_client(client, ip)

        except Exception as e:
            print("Allgemeiner Fehler bei Client IP:", ip, "| Fehler:", e)
            schliesse_client(client, ip)

    # Einzigartige IP-Adressen zählen (Verhindert doppeltes Zählen bei kurzzeitigen Reconnects)
    einzigartige_ips = set(client_ips.values())
    aktuelle_anzahl = len(einzigartige_ips)
    
    if aktuelle_anzahl != letzte_anzahl_esps:
        letzte_anzahl_esps = aktuelle_anzahl
        try:
            blynk.virtual_write(9, aktuelle_anzahl)
            print("[Blynk] Änderung erkannt! Echtzeit-Geräteanzahl an Pin 9:", aktuelle_anzahl)
        except Exception as e:
            print("Fehler beim Senden an Pin 9:", e)

    # 5-Sekunden Blynk-Intervall
    now = time.ticks_ms()
    if time.ticks_diff(now, last_blynk_upload) >= BLYNK_INTERVAL:
        last_blynk_upload = now
        
        if blynk_sende_puffer:
            print("[Blynk] 5s Intervall erreicht. Sende neueste gefilterte Daten...")
            
            try:
                aktuelles_v_zeit = zeitstempel_url()
                blynk.virtual_write(10, "%s" % aktuelles_v_zeit)
                print("[Blynk] URL-sicherer Zeitstempel an Pin 10 gesendet:", aktuelles_v_zeit)
            except Exception as e:
                print("Fehler beim Senden des Zeitstempels an Pin 10:", e)
        
            for pin, wert in blynk_sende_puffer.items():
                try:
                    if isinstance(wert, str):
                        zahl_wert = float(wert) if "." in wert else int(wert)
                    else:
                        zahl_wert = wert
                        
                    blynk.virtual_write(pin, zahl_wert)
                    logData("An Blynk übertragen - Pin:", pin, "Wert:", zahl_wert)
                except Exception as e:
                    print("Fehler beim Blynk-Senden:", e)
            blynk_sende_puffer.clear()

    # Status-Anzeige
    if time.ticks_diff(now, last_status_print) >= 2000:
        last_status_print = now
        zaehler += 2
        
        print("\n--------- STATUS ---------")
        print("AP IP:", ap.ifconfig()[0], "| Aktive ESPs (Sockets):", len(verbundene_esps), "| Physische Geräte:", len(set(client_ips.values())))
        print("Internet:", "verbunden (" + wlan.ifconfig()[0] + ")" if wlan.isconnected() else "nicht verbunden")
        print("Uptime:", zaehler, "s")

    # Button Abfrage
    if button.value() == 0:
        time.sleep_ms(50)
        if button.value() == 0:
            with open("log.txt", "w") as f:
                pass
            log("Geleert: [" + zeitstempel() + "]")
            break

    time.sleep_ms(2)