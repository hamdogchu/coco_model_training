import time
import os
import json
import shutil
import socket
import threading
from datetime import datetime, timezone
from rpi_code import run_hardware_sequence
from batch_processor import run_batch_inference
from supabase_uploader import CloudUploader
from supabase import create_client, Client
import offline_manager

CAPTURE_DIR = 'wave_captures'
PROCESSED_DIR = 'processed_captures'
MODEL_PATH = "lettuce_student_resnet18.onnx"

SUPABASE_URL = "https://eiqtrqnioobwslzntkdo.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImVpcXRycW5pb29id3Nsem50a2RvIiwicm9sZSI6ImFub24iLCJpYXQiOjE3ODA4OTk1NDMsImV4cCI6MjA5NjQ3NTU0M30.cUNW3nWp3D6iO2IjLsq1-8zLNz4_3i1bgEe8dy6Dyag"
BUCKET_NAME = "scans"
GDRIVE_FOLDER_ID = "1YbloloKCFaKHyMFZs1ZbHPz0TpxzBJBs"

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
uploader = CloudUploader(
    supabase_url=SUPABASE_URL, 
    supabase_key=SUPABASE_KEY, 
    gdrive_folder_id=GDRIVE_FOLDER_ID
)

# --- Main Hardware Execution ---
def perform_wave():
    try:
        print("\n[PHASE 1] Starting Hardware Sequence...")
        
        # --- FIX 1: Broadcast that we are scanning! ---
        offline_manager.set_scanning_state(True)
        if offline_manager.check_internet():
            offline_manager.sync_settings_with_supabase(supabase)

        os.makedirs(CAPTURE_DIR, exist_ok=True)
        os.makedirs(PROCESSED_DIR, exist_ok=True)
        
        # Clear out old temp files from previous waves
        for f in os.listdir(CAPTURE_DIR): os.remove(os.path.join(CAPTURE_DIR, f))
        for f in os.listdir(PROCESSED_DIR): os.remove(os.path.join(PROCESSED_DIR, f))
            
        #run_hardware_sequence(CAPTURE_DIR)
        
        print("\n[PHASE 2] Starting AI Inference...")
        ai_results = run_batch_inference(
            input_dir=CAPTURE_DIR, output_dir=PROCESSED_DIR,
            model_path=MODEL_PATH, is_yuyv=False 
        )
        
        # PHASE 3: Always save to local queue first, regardless of internet
        offline_manager.queue_wave_offline(ai_results, PROCESSED_DIR)
    except Exception as e:
        print(f"[!] Scan Error: {e}")
    finally:
        # This MUST run. If this line is skipped, the UI will stay stuck.
        offline_manager.set_scanning_state(False)
        offline_manager.set_last_completed()
        # Force a sync so the UI sees the new state immediately
        offline_manager.sync_settings_with_supabase(supabase)

def main():
    print("=== FarmGuard Lite: Offline-First System Initialized ===")
    
    offline_manager.load_settings()
    
    # Start the local API so the 7-inch LCD can talk to the script offline
    api_thread = threading.Thread(target=offline_manager.start_local_api, daemon=True)
    api_thread.start()
    
    last_wave_time = 0 # Start immediately on boot
    
    try:
        while True:
            is_online = offline_manager.check_internet()
            
            # --- Sync State with Cloud ---
            if is_online:
                # --- FIX 3: Broadcast Upload State and delay the timer reset ---
                if offline_manager.has_offline_waves():
                    offline_manager.set_uploading_state(True)
                    offline_manager.sync_settings_with_supabase(supabase)
                    
                    offline_manager.sync_offline_queue(uploader)
                    
                    offline_manager.set_uploading_state(False)
                    last_wave_time = time.time() # Reset the clock AFTER upload completely finishes!
                
                offline_manager.sync_settings_with_supabase(supabase)
            
            # --- Trigger Logic (Works Offline or Online) ---
            current_settings = offline_manager.get_current_settings()
            
            if current_settings.get('force_trigger'):
                print("\n[COMMAND] Manual Trigger Received!")
                offline_manager.reset_force_trigger()
                perform_wave()
                last_wave_time = time.time()
                offline_manager.set_last_completed()
                
            elif not current_settings.get('is_paused'):
                interval_seconds = current_settings.get('interval_minutes', 30) * 60
                
                # Check if enough time has passed based on the local timer
                if time.time() - last_wave_time >= interval_seconds:
                    print(f"\n[TIMER] {current_settings.get('interval_minutes')} minutes elapsed. Starting automatic wave.")
                    perform_wave()
                    last_wave_time = time.time()
                    offline_manager.set_last_completed()
                print("wave complete")
            time.sleep(5)
            
    except KeyboardInterrupt:
        print("\n[!] Sequence manually halted.")
    except Exception as e:
        print(f"\n[!] Critical Pipeline Error: {e}")

if __name__ == "__main__":
    main()