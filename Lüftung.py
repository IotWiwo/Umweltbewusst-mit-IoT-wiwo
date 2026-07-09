from machine import Pin, ADC
import esp32, time, dht, network, json, socket

# PINNummern
rauchnr = 0
dhtnr = 1
lednr = 2

# Grenzwerte
maxluftfeuchtigkeit = 35
maxluftqualitaet = 30000
maxtemperatur = 27

# Intervalle
intervall = 10
weather_refresh_intervall = 120

# WLAN
SSID = "mainesp"
PASSWORD = "esp32ap1"

MAIN_ESP_IP = "192.168.4.1"
PORT = 5000

esp_name = "Lueftung"

dht = dht.DHT11(Pin(dhtnr))
led = Pin(lednr, Pin.OUT)
rauch = ADC(Pin(rauchnr))

wlan = network.WLAN(network.STA_IF)

try:
    wlan.disconnect()
except:
    pass

wlan.active(False)
time.sleep(2)

wlan.active(True)
time.sleep(2)

print("Verbinde mit:", SSID)

try:
    wlan.connect(SSID, PASSWORD)
except OSError as e:
    print("WLAN Start Fehler:", e)
    time.sleep(2)
    wlan.active(False)
    time.sleep(2)
    wlan.active(True)
    time.sleep(2)
    wlan.connect(SSID, PASSWORD)

while (not wlan.isconnected()):
    print("Wird mit WLAN verbunden")
    socconnected = False
    time.sleep(1)
    if wlan.status() == network.STAT_IDLE:
        wlan.connect(SSID, PASSWORD)
        time.sleep(1)
    if wlan.status() == network.STAT_CONNECTING:
        print("Connecting")
    while wlan.status() == network.STAT_CONNECTING:
        print(".", end="")
        time.sleep(1)

client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

print("Verbinde mit Main-ESP...")

try:
    client.connect((MAIN_ESP_IP, PORT))
    print("Mit Main-ESP verbunden!")
    socconnected = True
except Exception as e:
    print("Main-ESP Verbindung fehlgeschlagen:", e)
    socconnected = False
    

def datensatz_format(att, attw):
    return "{};{};{}".format(esp_name, att, attw)


def buffer_senden(buffer):
    if not buffer:
        return
    nachricht = "\n".join(buffer) + "\n"
    client.send(nachricht.encode())
    print("Gesendet:\n" + nachricht)


def daten_empfangen():
    try:
        client.settimeout(1.0) # Etwas mehr Zeit für die Antwort geben
        daten = client.recv(2048)
        if daten:
            text = daten.decode().strip()
            print("Empfangen vom Main-ESP:", text)
            return text
    except: 
        pass
    return None


# --- STANDORT ABFRAGEN (HIER GELÖST) ---
buffer_senden([datensatz_format("GET", "https://ipinfo.io/json")])

# Warten auf die Antwort vom Main-ESP
antwort_ipinfo = None
for _ in range(50): # Versuche max. 5 Sekunden lang zu warten
    antwort_ipinfo = daten_empfangen()
    if antwort_ipinfo:
        break
    time.sleep(0.1)

if not antwort_ipinfo:
    print("Fehler: Keine Antwort von ipinfo.io erhalten. Nutze Standardwerte.")
    lat, lon = "49.4542", "11.0775"
else:
    try:
        response_data = json.loads(antwort_ipinfo)
        lat, lon = response_data["loc"].split(",")
        print("Standort: {}, {}: {}".format(lat, lon, response_data.get("city", "Unbekannt")))
    except Exception as e:
        print("Fehler beim Parsen der Standortdaten:", e)
        lat, lon = "52.5200", "13.4050"


# --- WETTER ABFRAGEN (INITIAL) ---
outside_temp = 20.0 # Standardwert, falls Abfrage fehlschlägt
last_weatherrefresh = time.time()

def wetter_aktualisieren(lat, lon):
    url = "https://api.brightsky.dev/current_weather?lat={}&lon={}".format(lat, lon)
    buffer_senden([datensatz_format("GET", url)])
    
    antwort_wetter = None
    for _ in range(50):
        antwort_wetter = daten_empfangen()
        if antwort_wetter:
            break
        time.sleep(0.1)
        
    if antwort_wetter:
        try:
            weather = json.loads(antwort_wetter)
            return float(weather["weather"]["temperature"])
        except Exception as e:
            print("Fehler beim Parsen der Wetterdaten:", e)
    return 20.0

# Erste Wetterabfrage beim Start
outside_temp = wetter_aktualisieren(lat, lon)
print("Aktuelle Außentemperatur:", outside_temp)

# --- HAUPTSCHLEIFE ---
while True:
    while (not wlan.isconnected()):
        print("Wlan getrennt wird neu verbunden")
        socconnected = False
        time.sleep(1)
        if wlan.status() == network.STAT_IDLE:
            wlan.connect(SSID, PASSWORD)
            time.sleep(1)
        if wlan.status() == network.STAT_CONNECTING:
            print("Connecting")
        while wlan.status() == network.STAT_CONNECTING:
            print(".", end="")
            time.sleep(1)
    
    if not socconnected:
        try:
            client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            client.connect((MAIN_ESP_IP, PORT))
            socconnected = True
            print("Mit Main-ESP verbunden!")
        except Exception as e:
            print("Main-ESP Verbindung fehlgeschlagen:", e)
        
        
    
    empfangen = daten_empfangen()
    if empfangen:
        teile = empfangen.split(";")
        if len(teile) == 3: # Format: ESP_NAME;ATTRIBUT;WERT
            attr = teile[1].lower()
            wert = teile[2]

            if attr == "led":
                try:
                    led.value(int(wert))
                except:
                    pass

    send_buffer = []

    try:
        dht.measure()
        hum = dht.humidity()
        temp = dht.temperature()
    except Exception as e:
        print("DHT11 Sensorfehler:", e)
        hum, temp = 0, 0

    smk = rauch.read_u16()

    send_buffer.append(datensatz_format("Feuchtigkeit", hum))
    send_buffer.append(datensatz_format("Temperatur", temp))
    send_buffer.append(datensatz_format("Luftqualität", smk))

    # Logik für LED-Steuerung
    if (hum > maxluftfeuchtigkeit or smk > maxluftqualitaet):
        led.value(1)
        send_buffer.append(datensatz_format("Led", 1))
    elif (temp > maxtemperatur and temp > outside_temp):
        led.value(1)
        send_buffer.append(datensatz_format("Led", 1))
    else:
        led.value(0)
        send_buffer.append(datensatz_format("Led", 0))
    print(f"Temperatur: {temp} °C, Luftfeuchtigkeit: {hum}%, Luftqualtiät: {smk}/65535")
    
    try:
        buffer_senden(send_buffer)
    except OSError as e:
        if e.errno == 128:
            socconnected = False
        else:
            print("Fehler:", e)
    except Exception as e:
            print("Fehler: ", e)
            
    time.sleep(intervall)

    # Wetter zyklisch aktualisieren
    if (time.time() - last_weatherrefresh > weather_refresh_intervall):
        print("Aktualisiere Wetterdaten...")
        try:
            outside_temp = wetter_aktualisieren(lat, lon)
        except OSError as e:
            if e.errno == 128:
                socconnected = False
            else:
                print("Fehler:", e)
        except Exception as e:
            print("Fehler: ", e)
        last_weatherrefresh = time.time()
