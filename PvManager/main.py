import socket
import machine
import network
import time
import math
import dht
import tm1637

# =========================================================
# Konfiguration
# =========================================================

# --- WLAN / Server ---
SSID = "mainesp"
PASSWORD = "esp32ap1"
MAIN_ESP_IP = "192.168.4.1"
PORT = 5000
ESP_NAME = "PVManager"

# --- Pins ---
DHT_PIN = 4
AC_LED_PIN = 5
CLK_PV = 14
DIO_PV = 15
CLK_TEMP = 18
DIO_TEMP = 19

# --- Timing ---
SEND_INTERVAL_MS = 10000          # Alle 3 Sekunden Daten senden & Fenster abfragen
WIFI_RETRY_INTERVAL_MS = 10000   
WIFI_CONNECT_TIMEOUT_S = 15      
WIFI_RETRY_TIMEOUT_S = 3         
SOCKET_TIMEOUT_S = 10           # Auf 3 Sekunden optimiert für besseres Timing

# --- Simulations-Parameter ---
TAG_DAUER_MS = 120000  
MPP_WATT = 800         
POWER_THRESHOLD = 400  
TEMP_THRESHOLD = 2 

# =========================================================
# Globale Zustände & Hardware-Initialisierung
# =========================================================

wlan = network.WLAN(network.STA_IF)

_letzter_wifi_versuch = 0
letzte_dht_messung = 0
letzte_sendung = 0

aktuelle_temperatur = 20  
simulierter_fenster_state = 0  # 0 = ZU, 1 = OFFEN

ac_led = machine.Pin(AC_LED_PIN, machine.Pin.OUT)
ac_led.off()
dht_sensor = dht.DHT11(machine.Pin(DHT_PIN))

display_pv = tm1637.TM1637(clk=machine.Pin(CLK_PV), dio=machine.Pin(DIO_PV))
display_temp = tm1637.TM1637(clk=machine.Pin(CLK_TEMP), dio=machine.Pin(DIO_TEMP))

display_pv.brightness(7)
display_temp.brightness(7)

# =========================================================
# Netzwerk-Funktionen
# =========================================================

def wlan_verbinden(timeout_s=WIFI_CONNECT_TIMEOUT_S):
    if wlan.isconnected():
        return True
    print("Verbinde mit WLAN:", SSID)
    try:
        wlan.active(False)
        time.sleep(1)
        wlan.active(True)
        time.sleep(1)
        wlan.connect(SSID, PASSWORD)
    except Exception as e:
        print("WLAN Start Fehler:", e)
        return False

    t = timeout_s
    while not wlan.isconnected() and t > 0:
        print(".", end="")
        time.sleep(1)
        t -= 1

    if wlan.isconnected():
        print("\nWLAN verbunden! IP:", wlan.ifconfig()[0])
        return True
    print("\nWLAN-Verbindung fehlgeschlagen.")
    return False


def datensatz_format(attribut, wert):
    return "{};{};{}".format(ESP_NAME, attribut, wert)


def daten_austauschen(buffer):
    """
    Öffnet eine kurze TCP-Verbindung, sendet die Daten und wartet 
    direkt im Anschluss auf die Antwort des Haupt-ESPs bezüglich des Fenster-Status.
    Danach wird die Verbindung sofort wieder geschlossen.
    """
    global simulierter_fenster_state

    if not wlan.isconnected():
        print("Senden abgebrochen: Keine WLAN-Verbindung.")
        return

    nachricht = "\n".join(buffer) + "\n"

    try:
        # Verbindung für diesen Sendevorgang frisch aufbauen
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(SOCKET_TIMEOUT_S)
        s.connect((MAIN_ESP_IP, PORT))
        
        # 1. Daten senden
        s.send(nachricht.encode())
        
        # 2. Direkt auf Antwort warten
        raw_antwort = s.recv(1024)
        s.close() # Verbindung sofort schließen, um den Server-Socket freizugeben
        
        if raw_antwort:
            antwort = raw_antwort.decode().strip()
            print(f"Antwort vom Haupt-ESP empfangen: {antwort}")
            
            # Präziser Abgleich statt fehleranfälliger "in"-Prüfung
            if antwort == "1":
                simulierter_fenster_state = 1  # Fenster ist offen
            elif antwort == "0":
                simulierter_fenster_state = 0  # Fenster ist zu
            else:
                print(f"Unerwartetes Antwortformat: {antwort}")
        else:
            print("Verbindung wurde vom Haupt-ESP ohne Antwort geschlossen.")

    except Exception as e:
        print("Fehler beim Datenaustausch:", e)


# =========================================================
# Start: Initialer Verbindungsaufbau
# =========================================================

print("=== PV- & Klima-Simulation mit Fenster-Sperre gestartet ===")
wlan_verbinden()
_letzter_wifi_versuch = time.ticks_ms()
letzte_sendung = time.ticks_ms()

# =========================================================
# Hauptschleife
# =========================================================

while True:
    try:
        jetzt = time.ticks_ms()

        # -----------------------------------------------------
        # 1. Photovoltaik-Sinuskurve berechnen
        # -----------------------------------------------------
        tages_fortschritt = jetzt % TAG_DAUER_MS
        winkel = (tages_fortschritt / TAG_DAUER_MS) * 2 * math.pi
        sinus_wert = math.sin(winkel)
        
        if sinus_wert > 0:
            aktuelle_leistung = int(sinus_wert * MPP_WATT)
        else:
            aktuelle_leistung = 0
            
        display_pv.number(aktuelle_leistung)

        # -----------------------------------------------------
        # 2. DHT11 auslesen (alle 2 Sekunden)
        # -----------------------------------------------------
        if time.ticks_diff(jetzt, letzte_dht_messung) >= 2000:
            letzte_dht_messung = jetzt
            try:
                dht_sensor.measure()
                aktuelle_temperatur = dht_sensor.temperature()
                display_temp.show(f"{aktuelle_temperatur} C")
            except Exception as e:
                print("Fehler beim DHT11-Auslesen:", e)

        # -----------------------------------------------------
        # 3. Logik-Entscheidung mit FENSTER-PRÜFUNG
        # -----------------------------------------------------
        leistung_ok = aktuelle_leistung > POWER_THRESHOLD
        temperatur_ok = aktuelle_temperatur > TEMP_THRESHOLD
        fenster_zu = (simulierter_fenster_state == 0)
        
        # Klimaanlagen-Logik schalten
        if leistung_ok and temperatur_ok and fenster_zu:
            if ac_led.value() == 0:
                print(f"[AC AN] Start bei {aktuelle_leistung}W, {aktuelle_temperatur}°C und Fenster ZU.")
            ac_led.on()
        else:
            if ac_led.value() == 1:
                grund = "Fenster OFFEN" if not fenster_zu else "Zu wenig Leistung/Temp"
                print(f"[AC AUS] Stopp wegen: {grund} (PV: {aktuelle_leistung}W, Temp: {aktuelle_temperatur}°C)")
            ac_led.off()

        # -----------------------------------------------------
        # 4. Netzwerk-Verbindung bei Verlust wiederherstellen
        # -----------------------------------------------------
        if not wlan.isconnected():
            if time.ticks_diff(jetzt, _letzter_wifi_versuch) >= WIFI_RETRY_INTERVAL_MS:
                _letzter_wifi_versuch = jetzt
                wlan_verbinden(timeout_s=WIFI_RETRY_TIMEOUT_S)

        # -----------------------------------------------------
        # 5. Daten senden & Fenster abrufen (alle 3 Sekunden)
        # -----------------------------------------------------
        if time.ticks_diff(jetzt, letzte_sendung) >= SEND_INTERVAL_MS:
            letzte_sendung = jetzt
            
            send_buffer = []
            send_buffer.append(datensatz_format("Temperatur", aktuelle_temperatur))
            send_buffer.append(datensatz_format("PV_Leistung", aktuelle_leistung))
            send_buffer.append(datensatz_format("KlimaState", ac_led.value()))
            send_buffer.append(datensatz_format("get", "fensterstate"))
            
            # Senden und im selben Atemzug Antwort verarbeiten
            daten_austauschen(send_buffer)

    except Exception as e:
        print("Unerwarteter Fehler in der Hauptschleife:", e)

    time.sleep_ms(100)