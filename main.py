import uvicorn
import asyncio
import time
import random
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
import aiomqtt  # Async-friendly MQTT client

# --- CONFIGURATION ---
# !! IMPORTANT: Change these values to match your setup !!
BROKER_ADDRESS = "localhost"  # Or "192.168.1.100", "localhost", etc.
TOPIC_RACE_START = "carrera/race/start"
TOPIC_TRACK1_FINISH = "carrera/track1/finish"
TOPIC_TRACK2_FINISH = "carrera/track2/finish"
# --- END CONFIGURATION ---

app = FastAPI()

# --- Lap Timing State ---
# We store the start time of the *current lap* for each track.
# This is a simple global state for this app.
track_lap_start_times = {
    1: 0.0,
    2: 0.0
}
# ---

# Read the HTML file from disk
try:
    with open("index.html", "r") as f:
        html_content = f.read()
except FileNotFoundError:
    print("FATAL ERROR: 'index.html' not found in the same directory as 'main.py'.")
    print("Please make sure both files are in the same folder.")
    exit()


@app.get("/")
async def get_root():
    """Serves the main HTML dashboard."""
    return HTMLResponse(content=html_content)

async def race_sequence(websocket: WebSocket, client: aiomqtt.Client):
    """
    Handles the F1 start light sequence and race timing.
    """
    global track_lap_start_times
    try:
        # 1. Reset the frontend UI
        print("Starting new race sequence...")
        await websocket.send_json({"type": "reset"})
        
        # 2. Turn on the 5 red lights, one by one
        for i in range(1, 6):
            await asyncio.sleep(1.0)  # 1-second delay between lights
            print(f"Light {i} ON")
            await websocket.send_json({"type": "light", "light_id": i, "state": "on"})
            
        # 3. Random hold time (like real F1)
        await asyncio.sleep(random.uniform(1.0, 4.0))
        
        # 4. Lights out!
        print("LIGHTS OUT!")
        await websocket.send_json({"type": "lights_out"})
        
        # 5. Send MQTT "start" signal and record start time for Lap 1
        start_time = time.monotonic()
        track_lap_start_times[1] = start_time
        track_lap_start_times[2] = start_time
        
        await client.publish(TOPIC_RACE_START, "GO")
        
        # 6. Tell frontend to start its own timers
        await websocket.send_json({"type": "start_race"})
        print(f"Race started. Lap 1 start time: {start_time}")

    except Exception as e:
        print(f"Error during race sequence: {e}")

async def mqtt_listener(websocket: WebSocket, client: aiomqtt.Client):
    """
    Listens for incoming MQTT messages from the light gates.
    Calculates lap times and sends them to the frontend.
    """
    global track_lap_start_times
    print(f"Subscribing to {TOPIC_TRACK1_FINISH} and {TOPIC_TRACK2_FINISH}")
    await client.subscribe(TOPIC_TRACK1_FINISH)
    await client.subscribe(TOPIC_TRACK2_FINISH)
    
    try:
        async for message in client.messages:
            finish_time = time.monotonic()
            track = 0
            
            if message.topic.value == TOPIC_TRACK1_FINISH:
                track = 1
            elif message.topic.value == TOPIC_TRACK2_FINISH:
                track = 2
            
            if track > 0:
                # Check if race has started (start time is not 0)
                if track_lap_start_times[track] > 0:
                    # Calculate lap time
                    lap_time_sec = finish_time - track_lap_start_times[track]
                    
                    # Set the start time for the *next* lap
                    track_lap_start_times[track] = finish_time
                    
                    # Send the completed lap time to the frontend
                    print(f"Track {track} finished lap. Time: {lap_time_sec:.3f}s")
                    await websocket.send_json({
                        "type": "lap_finish", 
                        "track": track, 
                        "lap_time_sec": lap_time_sec
                    })
                else:
                    print(f"Ignoring message on track {track}: race not started.")
                
    except Exception as e:
        print(f"MQTT listener error: {e}")

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """Main WebSocket connection handler."""
    await websocket.accept()
    listener_task = None
    
    try:
        # Connect to the MQTT broker
        async with aiomqtt.Client(BROKER_ADDRESS) as client:
            print(f"Connected to MQTT broker at {BROKER_ADDRESS}")
            
            # Start the MQTT listener task
            listener_task = asyncio.create_task(mqtt_listener(websocket, client))
            
            # Wait for messages from the browser
            # FIX: Use .iter_text() which is an async iterator
            async for data in websocket.iter_text():
                if data == "start":
                    # Start the race sequence
                    asyncio.create_task(race_sequence(websocket, client))
                
    except WebSocketDisconnect:
        print("Client disconnected from WebSocket.")
    except aiomqtt.exceptions.MqttError as e:
        print(f"MQTT Connection Error: {e}. Is the broker running at {BROKER_ADDRESS}?")
        try:
            await websocket.send_json({"type": "status", "message": f"Error: Could not connect to MQTT broker at {BROKER_ADDRESS}"})
        except:
            pass # Client might be gone
    except Exception as e:
        print(f"An error occurred: {e}")
    finally:
        if listener_task:
            listener_task.cancel()
        print("WebSocket connection closed.")