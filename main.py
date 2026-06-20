import time
import os
# Import our custom modules
from rpi_code import run_hardware_sequence
from batch_processor import run_batch_inference
from supabase_uploader import WaveUploader

# --- Global Configuration ---
CAPTURE_DIR = 'wave_captures'
PROCESSED_DIR = 'processed_captures'
MODEL_PATH = "lettuce_student_resnet18.onnx"

# --- Supabase Credentials ---
SUPABASE_URL = "https://eiqtrqnioobwslzntkdo.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImVpcXRycW5pb29id3Nsem50a2RvIiwicm9sZSI6ImFub24iLCJpYXQiOjE3ODA4OTk1NDMsImV4cCI6MjA5NjQ3NTU0M30.cUNW3nWp3D6iO2IjLsq1-8zLNz4_3i1bgEe8dy6Dyagyour_service_role_key_here"
BUCKET_NAME = "scans"

def main():
    print("\n" + "="*50)
    print("=== FarmGuard Lite: System Initialized ===")
    print("="*50)
    
    # Optional: You can wrap this in a `while True:` loop if you want it to 
    # run endlessly on a timer (e.g., every 3 hours). For now, it runs once.
    try:
        # ---------------------------------------------------------
        # PHASE 1: Hardware Movement & Image Capture
        # ---------------------------------------------------------
        print("\n[PHASE 1] Starting Hardware Sequence...")
        # Make sure the capture directory exists before hardware starts
        os.makedirs(CAPTURE_DIR, exist_ok=True)
        
        # This will pause the main script until the motors return to X0 Y0
        run_hardware_sequence(CAPTURE_DIR)
        
        # ---------------------------------------------------------
        # PHASE 2: AI Image Inference
        # ---------------------------------------------------------
        print("\n[PHASE 2] Starting AI Inference...")
        ai_results = run_batch_inference(
            input_dir=CAPTURE_DIR, 
            output_dir=PROCESSED_DIR,
            model_path=MODEL_PATH,
            is_yuyv=False # Change to True if capturing raw YUYV
        )
        
        # ---------------------------------------------------------
        # PHASE 3: Cloud Database Sync
        # ---------------------------------------------------------
        print("\n[PHASE 3] Syncing to Supabase Cloud...")
        uploader = WaveUploader(
            supabase_url=SUPABASE_URL, 
            supabase_key=SUPABASE_KEY, 
            bucket_name=BUCKET_NAME
        )
        uploader.upload_wave(PROCESSED_DIR, ai_results)
        
        print("\n" + "="*50)
        print("=== Wave Cycle Completed Successfully ===")
        print("="*50 + "\n")
        
    except KeyboardInterrupt:
        print("\n[!] Sequence manually halted by user.")
    except Exception as e:
        print(f"\n[!] Critical Pipeline Error: {e}")

if __name__ == "__main__":
    main()