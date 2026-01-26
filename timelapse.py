import os
import json
import shutil
import asyncio
import aiohttp
import tempfile
import datetime
import websockets
from config import *
from PIL import Image
from constant import *

# Shared state
snapshot_count = 1
motion_event = asyncio.Event()
is_motion_active = False # Tracks the live state from the websocket

# Create a temporary directory
tmp_dir = tempfile.mkdtemp()
print(f"Created temp folder at: {tmp_dir}")

def generate_timelapse():
  print('-- GENERATING TIMELAPSE --')
  timelapse_name = os.path.join(*output_path_full_resolution, datetime.datetime.now().strftime('%Y%m%d'))
  os.system(f'ffmpeg -framerate 30 -start_number 1 -i {tmp_dir}/img_%d.jpeg -c:v libx264 -crf 17 -preset veryslow ' + timelapse_name + '.mp4')

def generate_timelapse_ha():
  print('-- GENERATING TIMELAPSE --')
  timelapse_name = os.path.join(*output_path_home_assistant, datetime.datetime.now().strftime('%Y%m%d'))
  os.system(f'ffmpeg -framerate 30 -start_number 1 -i {tmp_dir}/img_%d.jpeg -c:v libx264 -crf 26 -preset veryslow ' + timelapse_name + "-timelapse-ha.mp4")

def clean_up_snapshots():
  # Clean Up
  print('-- STARTING CLEAN UP --')
  files = os.listdir(tmp_dir)

  for item in files:
    if item.endswith(".jpeg"):
      print('Deleting', os.path.join( tmp_dir, item ))
      os.remove(os.path.join( tmp_dir, item ))

async def capture_snapshot_async(session):
    """Asynchronously captures and processes the image."""
    global snapshot_count
    url = f"{camera_url}/snap.jpeg"
    try:
        async with session.get(url, timeout=5) as response:
            if response.status == 200:
                filename = f'{tmp_dir}/img_{snapshot_count}.jpeg'
                content = await response.read()
                
                # Use a thread for blocking CPU-bound Image processing
                def process_image(data, fname):
                    with open(fname, "wb") as f:
                        f.write(data)
                    im = Image.open(fname)
                    im = im.resize((1280, 720))
                    im.save(fname)

                await asyncio.get_running_loop().run_in_executor(None, process_image, content, filename)
                print(f'Captured {filename} at {datetime.datetime.now().strftime("%H:%M:%S")}')
                snapshot_count += 1
    except Exception as e:
        print(f"Capture error: {e}")

async def monitor_home_assistant():
    """Persistent Websocket that handles disconnections and restarts."""
    global is_motion_active
    reconnect_delay = 5  # Start with 5 seconds

    while True:
        try:
            print(f"Attempting to connect to Home Assistant at {ha_url_websocket}...")
            async with websockets.connect(ha_url_websocket) as websocket:
                # 1. Reset backoff on successful connection
                reconnect_delay = 5 
                
                # 2. Auth Handshake
                await websocket.send(json.dumps({"type": "auth", "access_token": ha_long_lived_token}))
                await websocket.recv()
                await websocket.send(json.dumps({"type": "auth", "access_token": ha_long_lived_token}))
                
                # 3. Subscribe
                await websocket.send(json.dumps({
                    "id": 1,
                    "type": "subscribe_events",
                    "event_type": "state_changed"
                }))

                print("Websocket Connected and Authenticated.")
                
                # 4. Process messages
                async for message in websocket:
                    event = json.loads(message)
                    if event["type"] == "event":
                        data = event["event"]["data"]
                        if data["entity_id"] == ha_detection_entity_id:
                            new_state = data["new_state"]["state"]
                            if new_state == "on":
                                is_motion_active = True
                                motion_event.set()
                            else:
                                is_motion_active = False

        except (websockets.ConnectionClosed, ConnectionRefusedError, OSError) as e:
            # This catches server restarts, network drops, or "Server Not Found"
            print(f"Websocket disconnected: {e}. Retrying in {reconnect_delay}s...")
            is_motion_active = False # Default to safe state on disconnect
            await asyncio.sleep(reconnect_delay)
            
            # Optional: Exponential backoff so you don't spam a rebooting server
            reconnect_delay = min(reconnect_delay * 2, 60) 
            
        except Exception as e:
            print(f"Unexpected error in HA monitor: {e}")
            await asyncio.sleep(5)

async def smart_sleep(default_seconds):
    """
    Waits for default_seconds OR until motion_event is set.
    Returns True if interrupted by motion, False if timed out.
    """
    try:
        # Wait for the event to be set, but with a timeout of the default interval
        await asyncio.wait_for(motion_event.wait(), timeout=default_seconds)
        motion_event.clear() # Reset for the next run
        return True
    except asyncio.TimeoutError:
        return False

async def run_daily_capture():
    """Main loop that switches between 60s and 1s intervals based on motion."""
    global snapshot_count
    async with aiohttp.ClientSession() as session:
        while True:
            # 1. Reset for the New Day
            # Set the new end_time to midnight of the current day
            end_time = datetime.datetime.now().replace(hour=23, minute=59, second=59)
            # Reset snapshot counter so day starts at img_1.jpeg
            snapshot_count = 1 
            
            print(f"-- STARTING NEW DAY CAPTURE: {datetime.datetime.now().date()} --")
            
            while datetime.datetime.now() < end_time:
                # 1. Take a snapshot
                await capture_snapshot_async(session)
                
                # 2. Determine sleep behavior
                if is_motion_active:
                    # SITUATION A: Motion is currently happening. 
                    # Capture at 1-second intervals.
                    await asyncio.sleep(SNAPSHOT_INTERVAL_MOTION)
                else:
                    # SITUATION B: No motion. 
                    # Wait for 60 seconds OR until motion_event is set.
                    try:
                        await asyncio.wait_for(motion_event.wait(), timeout=SNAPSHOT_INTERVAL_DEFAULT)
                        print("Motion detected during sleep! Transitioning to fast capture...")
                    except asyncio.TimeoutError:
                        # Normal interval passed with no motion
                        pass
                    
                    # Clear the event so we can wait for the next one
                    motion_event.clear()
            
            # 3. End of Day Processing
            # This runs once the 'while datetime.datetime.now() < end_time' loop finishes
            print(f"-- PROCESSING END OF DAY: {datetime.datetime.now().date()} --")
            
            # We use await here to ensure processing finishes before the next day starts,
            # OR we can use asyncio.create_task() if we want to start capturing Day 2
            # immediately while Day 1's video is still rendering.
            await asyncio.get_running_loop().run_in_executor(None, generate_timelapse)
            await asyncio.get_running_loop().run_in_executor(None, generate_timelapse_ha)
            await asyncio.get_running_loop().run_in_executor(None, clean_up_snapshots)

async def main():
    # Run the HA listener and the Snapshot loop concurrently
    await asyncio.gather(
        monitor_home_assistant(),
        run_daily_capture()
    )

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("-- Script Stopped --")
        generate_timelapse()
        generate_timelapse_ha()
        clean_up_snapshots()
        shutil.rmtree(tmp_dir)