import uvicorn
import asyncio
import time
import random
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
import aiomqtt  # Async-friendly MQTT client

# --- CONFIGURATION ---
# !! IMPORTANT: Change these values to match your setup !!
BROKER_ADDRESS = "192.168.1.144"  # Or "192.168.1.100", "localhost", etc.
TOPIC_RACE_START = "carrera/race/start"
TOPIC_TRACK1_FINISH = "sensor/schiene_1"
TOPIC_TRACK2_FINISH = "sensor/schiene_2"
# --- END CONFIGURATION ---

app = FastAPI()

# --- Global Race State ---
# This dictionary will hold all our race information
race_data = {
    "status": "idle", # "idle", "running", "finished"
    "tracks": {
        1: {"lap_start_time": 0.0, "laps": []}, # List of lap times in seconds
        2: {"lap_start_time": 0.0, "laps": []}
    }
}

def reset_race_state():
    """Helper function to reset the global race state."""
    global race_data
    race_data["status"] = "idle"
    race_data["tracks"][1]["lap_start_time"] = 0.0
    race_data["tracks"][1]["laps"] = []
    race_data["tracks"][2]["lap_start_time"] = 0.0
    race_data["tracks"][2]["laps"] = []
    print("Race state has been reset.")

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
    Handles the F1 start light sequence.
    This assumes the state has already been set to "running".
    """
    global race_data
    try:
        # 1. Frontend UI is already reset by the "start" command.
        print("Starting new race sequence...")
        
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
        race_data["tracks"][1]["lap_start_time"] = start_time
        race_data["tracks"][2]["lap_start_time"] = start_time
        
        await client.publish(TOPIC_RACE_START, "GO")
        
        # 6. Tell frontend to start its own timers
        await websocket.send_json({"type": "start_race"}) # This now *only* starts the timers
        print(f"Race started. Lap 1 start time: {start_time}")

    except Exception as e:
        print(f"Error during race sequence: {e}")

async def mqtt_listener(websocket: WebSocket, client: aiomqtt.Client):
    """
    Listens for incoming MQTT messages from the light gates.
    Calculates lap times and sends them to the frontend.
    """
    global race_data
    print(f"Subscribing to {TOPIC_TRACK1_FINISH} and {TOPIC_TRACK2_FINISH}")
    await client.subscribe(TOPIC_TRACK1_FINISH)
    await client.subscribe(TOPIC_TRACK2_FINISH)
    
    try:
        async for message in client.messages:
            # Only process if the race is running
            if race_data["status"] != "running":
                continue # Ignore messages if race isn't active

            finish_time = time.monotonic()
            track = 0
            
            if message.topic.value == TOPIC_TRACK1_FINISH:
                track = 1
            elif message.topic.value == TOPIC_TRACK2_FINISH:
                track = 2
            
            if track > 0:
                # Check if lap has started (start time is not 0)
                if race_data["tracks"][track]["lap_start_time"] == 0:
                    print(f"Ignoring message on track {track}: lap not started.")
                    continue

                # Calculate lap time
                lap_time_sec = finish_time - race_data["tracks"][track]["lap_start_time"]
                
                # Add to lap list
                race_data["tracks"][track]["laps"].append(lap_time_sec)
                
                # Set the start time for the *next* lap
                race_data["tracks"][track]["lap_start_time"] = finish_time
                
                # Send the completed lap time to the frontend
                print(f"Track {track} finished lap. Time: {lap_time_sec:.3f}s")
                await websocket.send_json({
                    "type": "lap_finish", 
                    "track": track, 
                    "lap_time_sec": lap_time_sec
                    # Frontend will use this to update "Last Lap" and "Live History"
                })
                
    except Exception as e:
        print(f"MQTT listener error: {e}")

async def stop_race(websocket: WebSocket):
    """
    Stops the race, calculates final stats, and sends to frontend.
    """
    global race_data
    if race_data["status"] != "running":
        print("Ignoring stop request: race not running.")
        return # Can't stop a race that isn't running

    print("Stopping race...")
    race_data["status"] = "finished"
    race_data["tracks"][1]["lap_start_time"] = 0.0
    race_data["tracks"][2]["lap_start_time"] = 0.0
    
    # Calculate stats
    laps_1 = race_data["tracks"][1]["laps"]
    laps_2 = race_data["tracks"][2]["laps"]
    
    fastest_1 = min(laps_1) if laps_1 else 0
    fastest_2 = min(laps_2) if laps_2 else 0

    await websocket.send_json({
        "type": "race_finished",
        "track_1_laps": laps_1,
        "track_2_laps": laps_2,
        "track_1_fastest": fastest_1,
        "track_2_fastest": fastest_2
    })
    print("Race finished. Final data sent to frontend.")

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
            async for data in websocket.iter_text():
                if data == "start":
                    if race_data["status"] == "running":
                        continue # Don't start a race that's already running
                    
                    # Reset state *before* starting
                    reset_race_state()
                    race_data["status"] = "running"
                    
                    # Tell frontend to reset its UI
                    await websocket.send_json({"type": "reset"})
                    
                    # Start the light sequence
                    asyncio.create_task(race_sequence(websocket, client))
                
                elif data == "stop":
                    await stop_race(websocket)
                
                elif data == "reset":
                    reset_race_state()
                    await websocket.send_json({"type": "reset"})
                
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