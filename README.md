Carrera F1 Race Control

This project provides a web-based F1 start light sequence and lap timer for your Carrera track, all powered by Python (FastAPI) and MQTT.

How it Works

main.py (Python Backend): This is the "brain." It runs on your Raspberry Pi.

It starts a FastAPI web server.

It serves the index.html file to any web browser on your network.

It opens a WebSocket connection to the browser for real-time, two-way communication.

It maintains the official race state (idle, running, finished) and stores a list of all completed laps.

It connects to your Mosquitto MQTT broker using aiomqtt.

It subscribes to your two light-gate topics (carrera/track1/finish and carrera/track2/finish).

index.html (Web Frontend): This is the dashboard you see in your browser.

It connects to the Python backend's WebSocket.

It has three main buttons: Start Race, Stop Race, and New Race.

It shows live "Current Lap" timers that count up in real-time.

It shows a "Recent Laps" history for the last 3 laps during the race.

The Race Sequence

Start: You click "START RACE."

The frontend sends a "start" message.

The backend resets all lap data, sets status="running", and sends a "reset" message to the frontend UI.

The backend starts the F1 light sequence, sending WebSocket messages to turn on each light.

After "Lights Out," the backend publishes the "GO" message to MQTT, starts its internal lap timers, and sends "start_race" to the frontend.

The frontend receives "start_race" and starts its own live "Current Lap" timers.

Laps:

Your car triggers a light gate, sending an MQTT message.

The backend (in mqtt_listener) receives this only if status="running".

It calculates the lap time, adds it to the list of laps (race_data["tracks"][1]["laps"]), and sends a "lap_finish" message to the frontend with the exact time.

The frontend receives this, displays it under "Last Lap," adds it to the "Recent Laps" history, and resets its "Current Lap" timer.

Stop: You click "STOP RACE."

The frontend sends a "stop" message.

The backend sets status="finished", calculates the fastest lap for each track, and sends a "race_finished" message with all lap data.

The frontend receives this, stops its timers, and displays a "Race Summary" modal showing all laps and highlighting the fastest.

The "Stop Race" button is hidden, and "New Race" appears.

Reset: You click "NEW RACE" (after a race is finished).

The frontend sends a "reset" message.

The backend calls reset_race_state(), clearing all data.

The backend sends a "reset" message back to the frontend, which calls resetUI(), hiding the modal, clearing all timers, and showing the "START RACE" button again.

Setup Instructions

IMPORTANT: Make sure main.py and index.html are saved in the same folder on your Raspberry Pi.

Edit Configuration:

Open main.py.

At the top, change BROKER_ADDRESS to match the IP address or hostname of your Raspberry Pi (e.g., "192.168.1.50" or "raspberrypi.local").

Change the TOPIC_... variables to match your exact MQTT topic names.

Create Virtual Environment & Install (If you haven't):

Open a terminal and navigate to this folder.

python3 -m venv venv

source venv/bin/activate

pip install -r requirements.txt

(You only need to do this setup once)

Run the Server:

IMPORTANT: Make sure your virtual environment is active (you should see (venv) in your terminal prompt).

Run this command:

uvicorn main:app --host 0.0.0.0 --port 8000


This command tells uvicorn (the server) to "run the app object found inside the main.py file."

You should see uvicorn start up and say it's listening on http://0.0.0.0:8000.

Open the Dashboard:

On any device on the same network (your phone, a laptop, etc.), open a web browser.

Go to the IP address of your Raspberry Pi, followed by :8000.

Example: http://192.168.1.50:8000 or http://raspberrypi.local:8000