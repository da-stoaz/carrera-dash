import paho.mqtt.client as mqtt
from gpiozero import Button
from signal import pause
import time

# --- Konfiguration ---
MQTT_BROKER = "localhost"
MQTT_PORT = 1883

# Sensor 1 (Schiene 1)
SENSOR_PIN_1 = 17 # GPIO 17
MQTT_TOPIC_1 = "sensor/schiene_1" # Eindeutiges Topic für Sensor 1

# Sensor 2 (Schiene 2) - NEU
SENSOR_PIN_2 = 27 # GPIO 27
MQTT_TOPIC_2 = "sensor/schiene_2" # Eindeutiges Topic für Sensor 2
# --- Ende Konfiguration ---

# Initialisiere beide Sensoren
hall_sensor_1 = Button(SENSOR_PIN_1, pull_up=True)
hall_sensor_2 = Button(SENSOR_PIN_2, pull_up=True) # NEU

# --- MQTT-Setup ---
def on_connect(client, userdata, flags, rc):
    if rc == 0:
        print("Erfolgreich mit MQTT-Broker verbunden.")
    else:
        print(f"Verbindung fehlgeschlagen mit Code: {rc}")

client = mqtt.Client()
client.on_connect = on_connect

try:
    client.connect(MQTT_BROKER, MQTT_PORT, 60)
except ConnectionRefusedError:
    print("Verbindung zum MQTT-Broker fehlgeschlagen. Läuft der Mosquitto-Dienst?")
    exit()

client.loop_start()

# --- Callback-Funktionen für Sensor 1 ---
def magnet_1_erkannt():
    print("Schiene 1: Magnet erkannt! Sende MQTT...")
    client.publish(MQTT_TOPIC_1, "MAGNET_ERKANNT")

def magnet_1_entfernt():
    print("Schiene 1: Kein Magnet. (log)")
    #client.publish(MQTT_TOPIC_1, "KEIN_MAGNET")

# --- Callback-Funktionen für Sensor 2 (NEU) ---
def magnet_2_erkannt():
    print("Schiene 2: Magnet erkannt! Sende MQTT...")
    client.publish(MQTT_TOPIC_2, "MAGNET_ERKANNT") # Sendet auf Topic 2

def magnet_2_entfernt():
    print("Schiene 2: Kein Magnet. (log)")
    #client.publish(MQTT_TOPIC_2, "KEIN_MAGNET") # Sendet auf Topic 2


# --- Sensor-Ereignisse zuweisen ---
# Sensor 1
hall_sensor_1.when_pressed = magnet_1_erkannt
hall_sensor_1.when_released = magnet_1_entfernt

# Sensor 2 (NEU)
hall_sensor_2.when_pressed = magnet_2_erkannt
hall_sensor_2.when_released = magnet_2_entfernt

print(f"Überwachung für Schiene 1 (GPIO {SENSOR_PIN_1}) und Schiene 2 (GPIO {SENSOR_PIN_2}) gestartet.")
print("Warte auf Magnete...")

# Das Skript am Laufen halten
try:
    pause()
except KeyboardInterrupt:
    print("Skript beendet.")
    client.loop_stop()
    client.disconnect()