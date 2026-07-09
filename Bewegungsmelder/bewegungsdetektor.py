from machine import Pin
import time
import network

SSID = "mainesp"
PASSWORD = "esp32ap1"

MAIN_ESP_IP = "192.168.4.1"
PORT = 5000

esp_name = "TempLight"


# -----------------------------
# WLAN verbinden
# -----------------------------

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

timeout = 30

while not wlan.isconnected() and timeout > 0:
    print(".", end="")
    time.sleep(1)
    timeout -= 1

if wlan.isconnected():
    print("\nVerbunden!")
    print("IP:", wlan.ifconfig()[0])
else:
    raise Exception("Keine WLAN Verbindung")


# -----------------------------
# Verbindung zum Main-ESP
# -----------------------------

client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

print("Verbinde mit Main-ESP...")

try:
    client.connect((MAIN_ESP_IP, PORT))
    print("Mit Main-ESP verbunden!")
except Exception as e:
    print("Main-ESP Verbindung fehlgeschlagen:", e)


def datensatz_format(att, attw):
    return "{};{};{}".format(esp_name, att, attw)


def buffer_senden(buffer):
    if not buffer:
        return
    nachricht = "\n".join(buffer) + "\n"
    client.send(nachricht.encode())
    print("Gesendet:\n" + nachricht)

# Wir nutzen Pin 2 (stelle sicher, dass dein Sensor an GP2/Pin 2 angeschlossen ist)
pir_pin = Pin(0, Pin.IN)
led = Pin(1, Pin.OUT)

#print("System startet....")
#time.sleep(2) # PIR-Sensoren brauchen oft kurz Zeit zum Kalibrieren

while True:
    if pir_pin.value() == 1: # 1 bedeutet HIGH / Bewegung erkannt
        #print("Bewegung erkannt!")
        led.value(1)# diod leuchtet für 5 sekunden
        time.sleep(5)
        led.value(0)
    #else:
    #    print("---")
        
    time.sleep(0.5) # Wartet eine halbe Sekunde vor der naechsten Abfrage