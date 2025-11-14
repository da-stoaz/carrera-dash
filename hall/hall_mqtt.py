import paho.mqtt.client as mqtt
from gpiozero import Button  # Button eignet sich perfekt für digitale 2-Zustand-Sensoren
from signal import pause
import time

# --- Konfiguration ---
MQTT_BROKER = "localhost"  # Dein Pi ist jetzt der Broker
MQTT_PORT = 1883
MQTT_TOPIC = "sensor/hall" # Das Thema, unter dem die Nachricht gesendet wird

SENSOR_PIN = 17 # Der GPIO-Pin, den wir in Schritt 1 verbunden haben
# --- Ende Konfiguration ---

# Wir verwenden 'Button' von gpiozero. 
# 'pull_up=True' bedeutet, dass der Pin intern auf HIGH gezogen wird.
# Die meisten Hallsensoren ziehen den Pin auf LOW, wenn ein Magnet erkannt wird.
# Dies wird als "drücken" (pressed) interpretiert.
hall_sensor = Button(SENSOR_PIN, pull_up=True)

# Funktion, die aufgerufen wird, wenn der MQTT-Client sich verbindet
def on_connect(client, userdata, flags, rc):
    if rc == 0:
        print("Erfolgreich mit MQTT-Broker verbunden.")
    else:
        print(f"Verbindung fehlgeschlagen mit Code: {rc}")

# Funktion, die aufgerufen wird, wenn ein Magnet erkannt wird
def magnet_erkannt():
    print("Magnet erkannt! Sende MQTT-Nachricht...")
    client.publish(MQTT_TOPIC, "MAGNET_ERKANNT")

# Funktion, die aufgerufen wird, wenn der Magnet entfernt wird
def magnet_entfernt():
    print("Kein Magnet. Sende MQTT-Nachricht...")
    client.publish(MQTT_TOPIC, "KEIN_MAGNET")

# --- MQTT-Setup ---
client = mqtt.Client()
client.on_connect = on_connect

try:
    client.connect(MQTT_BROKER, MQTT_PORT, 60)
except ConnectionRefusedError:
    print("Verbindung zum MQTT-Broker fehlgeschlagen. Läuft der Mosquitto-Dienst?")
    exit()

# Starte den MQTT-Client-Loop in einem eigenen Thread
client.loop_start()

# --- Sensor-Ereignisse zuweisen ---
# Weise die Funktionen den Ereignissen des Sensors zu
# 'when_pressed' wird ausgelöst, wenn der Sensor-Pin auf LOW geht (Magnet da)
hall_sensor.when_pressed = magnet_erkannt

# 'when_released' wird ausgelöst, wenn der Sensor-Pin auf HIGH geht (Magnet weg)
hall_sensor.when_released = magnet_entfernt

print(f"Hallsensor-Überwachung auf GPIO {SENSOR_PIN} gestartet.")
print("Warte auf Magnet...")

# Das Skript am Laufen halten, um auf Ereignisse zu warten
try:
    pause()
except KeyboardInterrupt:
    print("Skript beendet.")
    client.loop_stop()
    client.disconnect()