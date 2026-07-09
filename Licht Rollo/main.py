from machine import Pin, ADC
import dht
import network
import time
import socket

SSID = "mainesp"
PASSWORD = "esp32ap1"

MAIN_ESP_IP = "192.168.4.1"
PORT = 5000

esp_name = "TempLight"

# -----------------------------
# WLAN Initialisierung
# -----------------------------
wlan = network.WLAN(network.STA_IF)
wlan.active(True)

def wlan_verbinden():
    """Startet den Verbindungsaufbau, blockiert aber nicht endlos."""
    if not wlan.isconnected():
        print("Versuche WLAN-Verbindung mit:", SSID)
        try:
            wlan.connect(SSID, PASSWORD)
        except OSError as e:
            print("WLAN-Verbindungsfehler:", e)

# Erster Verbindungsversuch beim Start
wlan_verbinden()

# -----------------------------
# TCP Client Variable & Funktion
# -----------------------------
client = None
last_net_check = time.ticks_ms()
NET_CHECK_INTERVAL = 10000  # Alle 10 Sekunden Netzwerkstatus prüfen/wiederherstellen

def check_network_and_socket():
    """Prüft im Hintergrund das WLAN und den Server-Socket (Non-blocking)."""
    global client
    
    # 1. WLAN prüfen & ggf. reconnecten
    if not wlan.isconnected():
        if client is not None:
            try: client.close()
            except: pass
            client = None
        wlan_verbinden()
        return False

    # 2. Wenn WLAN steht, aber Socket fehlt -> neu verbinden
    if wlan.isconnected() and client is None:
        print("WLAN steht. Verbinde mit Main-ESP Server...")
        try:
            client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            # Setze ein kurzes Timeout für den Verbindungsaufbau, damit der Loop nicht blockiert
            client.settimeout(1.0) 
            client.connect((MAIN_ESP_IP, PORT))
            # Nach erfolgreichem Connect wieder auf non-blocking stellen
            client.settimeout(0.0) 
            print("Mit Main-ESP erfolgreich verbunden!")
            return True
        except Exception as e:
            print("Verbindung zu Main-ESP fehlgeschlagen, neuer Versuch gleich:", e)
            if client is not None:
                try: client.close()
                except: pass
                client = None
            return False
            
    return client is not None

def buffer_senden(buffer):
    global client
    if not buffer:
        return
        
    nachricht = "\n".join(buffer) + "\n"
    
    # Nur senden, wenn der Client existiert
    if client is not None:
        try:
            client.send(nachricht.encode())
            print("Gesendet:\n" + nachricht)
        except Exception as e:
            print("Sende-Fehler (Verbindung verloren):", e)
            # Socket zurücksetzen, damit die Hintergrundprüfung ihn neu aufbaut
            try: client.close()
            except: pass
            client = None
    else:
        print("Daten nicht gesendet (Aktuell keine Server-Verbindung):")
        print(nachricht.strip())

def datensatz_format(att, attw):
    return "{};{};{}".format(esp_name, att, attw)

# -----------------------------
# Hardware
# -----------------------------
relais1 = Pin(14, Pin.OUT)
relais2 = Pin(15, Pin.OUT)

relais1.value(1)
relais2.value(1)

dht_sensor = dht.DHT22(Pin(4))

ldr_adc = ADC(Pin(5))
ldr_adc.atten(ADC.ATTN_11DB)

led_temp = Pin(1, Pin.OUT)
led_licht = Pin(2, Pin.OUT)

schwellwert_lichtsensor = 1000
schwellwert_temperatur = 27.5

time.sleep(2)

# Sende-Intervall auf 9000ms (9 Sekunden) hochgesetzt
MESS_INTERVAL = 9000
last_dht = time.ticks_ms() - MESS_INTERVAL
last_ldr = time.ticks_ms() - MESS_INTERVAL

temp = None
licht_wert = None
hum = None

led_temp_state = None
led_licht_state = None

boot = True
zustand_alt = False

# -----------------------------
# Hauptschleife
# -----------------------------
while True:
    now = time.ticks_ms()
    send_buffer = []

    # Intervallmäßige Prüfung von WLAN & Socket (alle 10 Sek)
    if time.ticks_diff(now, last_net_check) >= NET_CHECK_INTERVAL:
        last_net_check = now
        check_network_and_socket()

    # -----------------------------
    # Lichtsensor (Alle 9 Sekunden)
    # -----------------------------
    if time.ticks_diff(now, last_ldr) >= MESS_INTERVAL:
        last_ldr = now
        try:
            licht_wert = ldr_adc.read()
            print("Lichtsensor (ADC): {}".format(licht_wert))
            send_buffer.append(datensatz_format("Lichtwert", licht_wert))
        except Exception as e:
            print("LM393 Fehler:", e)

    # -----------------------------
    # DHT22 (Alle 9 Sekunden)
    # -----------------------------
    if time.ticks_diff(now, last_dht) >= MESS_INTERVAL:
        last_dht = now
        try:
            dht_sensor.measure()
            temp = dht_sensor.temperature()
            hum = dht_sensor.humidity()

            print("Temperatur: {} °C".format(temp))
            print("Luftfeuchtigkeit: {} %".format(hum))

            send_buffer.append(datensatz_format("Temperatur", temp))
            send_buffer.append(datensatz_format("Luftfeuchtigkeit", hum))
        except OSError as e:
            print("DHT22 Fehler:", e)

    # -----------------------------
    # LED Licht (Event-basiert bei Änderung)
    # -----------------------------
    if licht_wert is not None:
        neuer_led_licht_state = 1 if licht_wert > schwellwert_lichtsensor else 0
        if neuer_led_licht_state != led_licht_state:
            led_licht_state = neuer_led_licht_state
            led_licht.value(led_licht_state)
            send_buffer.append(datensatz_format("Lampe", led_licht_state))

    # -----------------------------
    # Temperatur + Licht (Relais) (Event-basiert bei Änderung)
    # -----------------------------
    if licht_wert is not None and temp is not None:
        zustand_neu = (
            licht_wert < schwellwert_lichtsensor and
            temp > schwellwert_temperatur
        )

        if zustand_neu != led_temp_state:
            led_temp_state = zustand_neu
            led_temp.value(led_temp_state)

        if boot:
            zustand_alt = zustand_neu
            boot = False
        elif zustand_neu != zustand_alt:
            if zustand_neu:
                print("Schwellwerte erreicht -> Relais 1")
                relais2.value(1)
                relais1.value(0)
                time.sleep(5)  # Kurze Blockade für den Schaltimpuls
                relais1.value(1)
                send_buffer.append(datensatz_format("Rollo", 1))
            else:
                print("Schwellwerte verlassen -> Relais 2")
                relais1.value(1)
                relais2.value(0)
                time.sleep(5)  # Kurze Blockade für den Schaltimpuls
                relais2.value(1)
                send_buffer.append(datensatz_format("Rollo", 0))

            zustand_alt = zustand_neu

            # Nach der 5-sekündigen Blockade durch das Relais korrigieren wir die Timer,
            # damit die regulären Messungen nicht sofort unkontrolliert feuern.
            last_ldr = time.ticks_ms()
            last_dht = time.ticks_ms()

    # Buffer abschicken
    if send_buffer:
        buffer_senden(send_buffer)

    time.sleep_ms(100)