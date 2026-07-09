import urequests

class Blynk:

    def __init__(self, auth_token, server="https://blynk.cloud"):
        self.token = auth_token
        self.server = server.rstrip("/")

    def virtual_write(self, pin, value):
        url = f"{self.server}/external/api/update?token={self.token}&V{pin}={value}"

        try:
            r = urequests.get(url)
            r.close()
            return True

        except Exception as e:
            print("Blynk Write Fehler:", e)
            return False

    def virtual_read(self, pin):
        url = f"{self.server}/external/api/get?token={self.token}&V{pin}"

        try:
            r = urequests.get(url)
            value = r.text
            r.close()
            return value

        except Exception as e:
            print("Blynk Read Fehler:", e)
            return None

    def log_event(self, event_code, description=""):
        url = (
            f"{self.server}/external/api/logEvent?"
            f"token={self.token}&code={event_code}"
            f"&description={description}"
        )

        try:
            r = urequests.get(url)
            r.close()
            return True

        except Exception as e:
            print("Blynk Event Fehler:", e)
            return False

    def run(self):
        # Platzhalter, damit alte Blynk-Strukturen nicht abstürzen
        pass