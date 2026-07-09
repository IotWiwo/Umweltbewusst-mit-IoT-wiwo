import socket
import machine
import network
import time
import dht
import urequests
import tm1637

SSID = "mainesp"
PASSWORD = "esp32ap1"

MAIN_ESP_IP = "192.168.4.1"
PORT = 5000

esp_name = "FensterSensor"

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
# Verbindung zum Main-ESP Logik
# -----------------------------
client = None

def verbinde_mit_server():
    global client
    # Wenn bereits ein Socket existiert, schließen wir es vorsichtshalber zuerst
    if client:
        try:
            client.close()
        except:
            pass
        client = None

    print("Verbinde mit Main-ESP...")
    try:
        client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        client.connect((MAIN_ESP_IP, PORT))
        print("Mit Main-ESP verbunden!")
        return True
    except Exception as e:
        print("Main-ESP Verbindung fehlgeschlagen:", e)
        client = None
        return False


def datensatz_format(att, attw):
    return "{};{};{}".format(esp_name, att, attw)


def buffer_senden(buffer):
    global client
    if not buffer:
        return
    
    # Falls gar kein Client existiert, versuchen wir neu zu verbinden
    if client is None:
        if not verbinde_mit_server():
            print("Senden abgebrochen: Keine Verbindung zum Server.")
            return

    nachricht = "\n".join(buffer) + "\n"
    
    try:
        client.send(nachricht.encode())
        print("Gesendet:\n" + nachricht)
    except Exception as e:
        print("Fehler beim Senden (Verbindung verloren):", e)
        # Setze Client auf None, damit im nächsten Durchlauf neu verbunden wird
        client = None


# ---------- Konfiguration ----------
DHT_PIN = 4
IR_PIN = 3
CLK_PIN = 14  
DIO_PIN = 15  

SEND_INTERVAL_MS = 10000  

# ---------- Sensoren & Display initialisieren ----------
dht_sensor = dht.DHT11(machine.Pin(DHT_PIN))

ir_adc = machine.ADC(machine.Pin(IR_PIN))
ir_adc.atten(machine.ADC.ATTN_11DB)   
ir_adc.width(machine.ADC.WIDTH_12BIT)  

display = tm1637.TM1637(clk=machine.Pin(CLK_PIN), dio=machine.Pin(DIO_PIN))
display.brightness(7) 
display.write([0, 0, 0, 0]) 


# ---------- Sensordaten lesen und senden ----------
def read_and_send():
    # IR-Distanzsensor auslesen
    try:
        distance_raw = ir_adc.read()
        print("IR-Rohwert:", distance_raw)
        
        if distance_raw > 500:
            distance_true = 1
            display.write([0x3F, 0x73, 0x79, 0x37])
        else:
            distance_true = 0
            display.write([0, 0, 0, 0])
            display.show("ZU")
        
        send_buffer.append(datensatz_format(" FensterState", distance_true))
            
    except Exception as e:
        print("ADC Lesefehler:", e)


# Erstmaliger Verbindungsversuch vor der Schleife
verbinde_mit_server()

# ---------- Hauptschleife ----------
while True:
    send_buffer = []
    read_and_send()
    buffer_senden(send_buffer)
    time.sleep_ms(SEND_INTERVAL_MS)