import uvicorn
import asyncio
import time
import random
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
import aiomqtt
from contextlib import asynccontextmanager
from typing import List, Union

# --- CONFIGURATION ---
BROKER_ADDRESS = "192.168.1.144"
TOPIC_RACE_START = "carrera/race/start"
TOPIC_TRACK1_FINISH = "sensor/schiene_1"
TOPIC_TRACK2_FINISH = "sensor/schiene_2"
# --- END CONFIGURATION ---

# --- Global MQTT Client & Tasks ---
# These will be initialized during the 'lifespan' startup event
mqtt_client: Union[aiomqtt.Client, None] = None
mqtt_listener_task: Union[asyncio.Task, None] = None
# --- Global Race State ---
race_data = {
    "status": "idle", # "idle", "running", "finished"
    "tracks": {
        1: {"lap_start_time": 0.0, "laps": []},
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

# NEW: Helper to get the current state for new clients
def get_current_state_message():
    """Creates a message object representing the full current state."""
    laps_1 = race_data["tracks"][1]["laps"]
    laps_2 = race_data["tracks"][2]["laps"]
    
    return {
        "type": "full_state", # Frontend will need to handle this
        "status": race_data["status"],
        "track_1_laps": laps_1,
        "track_2_laps": laps_2,
        "track_1_last_lap": laps_1[-1] if laps_1 else 0,
        "track_2_last_lap": laps_2[-1] if laps_2 else 0,
    }

# NEW: Connection Manager
class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        """Accept a new client and send them the current race state."""
        await websocket.accept()
        self.active_connections.append(websocket)
        # Send the current state so the new client can catch up
        await websocket.send_json(get_current_state_message())

    def disconnect(self, websocket: WebSocket):
        """Remove a client."""
        try:
            self.active_connections.remove(websocket)
        except ValueError:
            pass # Client already removed

    async def broadcast_json(self, data: dict):
        """Broadcast a JSON message to all connected clients."""
        print(f"Broadcasting: {data.get('type')}")
        # Iterate over a copy in case the list changes during iteration
        for connection in self.active_connections[:]:
            try:
                await connection.send_json(data)
            except (WebSocketDisconnect, RuntimeError):
                self.disconnect(connection)

# NEW: Create a single, global manager
manager = ConnectionManager()

# MODIFIED: mqtt_listener now runs as a background task
async def mqtt_listener(client: aiomqtt.Client):
    """
    Listens for MQTT messages. Runs as a single background task.
    Calculates lap times and broadcasts them to all clients.
    """
    global race_data
    print(f"Subscribing to {TOPIC_TRACK1_FINISH} and {TOPIC_TRACK2_FINISH}")
    await client.subscribe(TOPIC_TRACK1_FINISH)
    await client.subscribe(TOPIC_TRACK2_FINISH)
    
    try:
        async for message in client.messages:
            if race_data["status"] != "running":
                continue

            finish_time = time.monotonic()
            track = 0
            
            if message.topic.value == TOPIC_TRACK1_FINISH:
                track = 1
            elif message.topic.value == TOPIC_TRACK2_FINISH:
                track = 2
            
            if track > 0:
                if race_data["tracks"][track]["lap_start_time"] == 0:
                    print(f"Ignoring message on track {track}: lap not started.")
                    continue

                lap_time_sec = finish_time - race_data["tracks"][track]["lap_start_time"]
                race_data["tracks"][track]["laps"].append(lap_time_sec)
                race_data["tracks"][track]["lap_start_time"] = finish_time
                
                print(f"Track {track} finished lap. Time: {lap_time_sec:.3f}s")
                # MODIFIED: Broadcast to all clients
                await manager.broadcast_json({
                    "type": "lap_finish", 
                    "track": track, 
                    "lap_time_sec": lap_time_sec
                })
                
    except asyncio.CancelledError:
        print("MQTT listener task stopping.")
    except Exception as e:
        print(f"MQTT listener error: {e}")

# MODIFIED: race_sequence now broadcasts
async def race_sequence(client: aiomqtt.Client):
    """
    Handles the F1 start light sequence. Broadcasts updates to all clients.
    """
    global race_data
    try:
        print("Starting new race sequence...")
        
        for i in range(1, 6):
            await asyncio.sleep(1.0)
            print(f"Light {i} ON")
            # MODIFIED: Broadcast to all clients
            await manager.broadcast_json({"type": "light", "light_id": i, "state": "on"})
            
        await asyncio.sleep(random.uniform(1.0, 4.0))
        
        print("LIGHTS OUT!")
        # MODIFIED: Broadcast to all clients
        await manager.broadcast_json({"type": "lights_out"})
        
        start_time = time.monotonic()
        race_data["tracks"][1]["lap_start_time"] = start_time
        race_data["tracks"][2]["lap_start_time"] = start_time
        
        await client.publish(TOPIC_RACE_START, "GO")
        
        # MODIFIED: Broadcast to all clients
        await manager.broadcast_json({"type": "start_race"})
        print(f"Race started. Lap 1 start time: {start_time}")

    except Exception as e:
        print(f"Error during race sequence: {e}")
        # If sequence fails, reset everyone to idle
        reset_race_state()
        await manager.broadcast_json({"type": "reset"})

# MODIFIED: stop_race now broadcasts
async def stop_race():
    """
    Stops the race, calculates final stats, and broadcasts to all clients.
    """
    global race_data
    if race_data["status"] != "running":
        return

    print("Stopping race...")
    race_data["status"] = "finished"
    race_data["tracks"][1]["lap_start_time"] = 0.0
    race_data["tracks"][2]["lap_start_time"] = 0.0
    
    laps_1 = race_data["tracks"][1]["laps"]
    laps_2 = race_data["tracks"][2]["laps"]
    fastest_1 = min(laps_1) if laps_1 else 0
    fastest_2 = min(laps_2) if laps_2 else 0

    # MODIFIED: Broadcast to all clients
    await manager.broadcast_json({
        "type": "race_finished",
        "track_1_laps": laps_1,
        "track_2_laps": laps_2,
        "track_1_fastest": fastest_1,
        "track_2_fastest": fastest_2
    })
    print("Race finished. Final data sent to frontend.")

# MODIFIED: Replace your entire 'lifespan' function with this one

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manages application startup and shutdown events."""
    global mqtt_client, mqtt_listener_task
    print("Application startup...")
    
    try:
        # MODIFIED: Use 'async with' to correctly manage the connection
        async with aiomqtt.Client(BROKER_ADDRESS) as client:
            print(f"Connected to MQTT broker at {BROKER_ADDRESS}")
            
            # Assign the connected client to the global variable
            mqtt_client = client 
            
            # Start the *single* MQTT listener task
            mqtt_listener_task = asyncio.create_task(mqtt_listener(mqtt_client))
            print("MQTT listener task started.")
            
            yield  # --- Application is now running ---
            
            # --- Application is shutting down (code resumes after yield) ---
            print("Application shutting down...")
            if mqtt_listener_task:
                mqtt_listener_task.cancel()
                # Give it a moment to cancel
                try:
                    await mqtt_listener_task
                except asyncio.CancelledError:
                    print("MQTT listener task successfully cancelled.")
            
            # The 'async with' block will automatically call disconnect here
            
    except aiomqtt.exceptions.MqttError as e:
        print(f"FATAL: Could not connect to MQTT broker: {e}. Is it running?")
        mqtt_client = None
        yield # Allow the app to start, but in a failed state
    except Exception as e:
        print(f"An unexpected error occurred during lifespan: {e}")
        mqtt_client = None
        yield # Allow the app to start, but in a failed state
    
    finally:
        # This code runs after the 'async with' block has exited
        print("MQTT connection closed.")
        mqtt_client = None # Ensure global client is cleared

# --- FastAPI App ---
app = FastAPI(lifespan=lifespan) # MODIFIED: Add the lifespan handler

# Read the HTML file from disk
try:
    with open("index.html", "r") as f:
        html_content = f.read()
except FileNotFoundError:
    print("FATAL ERROR: 'index.html' not found")
    exit()

@app.get("/")
async def get_root():
    """Serves the main HTML dashboard."""
    return HTMLResponse(content=html_content)

# MODIFIED: WebSocket endpoint is now much simpler
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """Handles new client connections and incoming commands."""
    await manager.connect(websocket) # Connect the client and send current state
    
    try:
        # Only listen for commands from this client
        async for data in websocket.iter_text():
            
            if data == "start":
                if race_data["status"] == "running":
                    continue # Ignore
                if not mqtt_client:
                     print("ERROR: MQTT client not ready.")
                     continue
                
                # Set global state
                reset_race_state()
                race_data["status"] = "running"
                
                # Tell ALL clients to reset their UI
                await manager.broadcast_json({"type": "reset"})
                
                # Start the *single* race sequence task
                asyncio.create_task(race_sequence(mqtt_client))
            
            elif data == "stop":
                # stop_race() will handle broadcasting
                await stop_race()
            
            elif data == "reset":
                reset_race_state()
                # Tell ALL clients to reset
                await manager.broadcast_json({"type": "reset"})
                
    except WebSocketDisconnect:
        print("Client disconnected.")
    except Exception as e:
        print(f"An error occurred in WebSocket handler: {e}")
    finally:
        manager.disconnect(websocket)
        print("WebSocket connection closed.")

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)