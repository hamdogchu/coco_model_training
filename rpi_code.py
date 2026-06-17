import time
import cv2
import os
from datetime import datetime
import RPi.GPIO as GPIO
from supabase import create_client, Client

# --- Supabase Configuration ---
SUPABASE_URL = "YOUR_ACTUAL_SUPABASE_URL"
SUPABASE_KEY = "YOUR_ACTUAL_ANON_KEY"
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# --- Motor Pin Configuration ---
DIR_X = 20
STEP_X = 21
DIR_Y = 19
STEP_Y = 26

# --- Timing & Calibration ---
STEP_DELAY = 0.001 
STEPS_PER_MM = 25
NUM_PLANTS = 14
INTERVAL_SECONDS = 1800 # 30 minutes

PLANT_COORDINATES = {
    1:  (50, 50),   2:  (150, 50),   3:  (250, 50),   4:  (350, 50),
    5:  (450, 50),  6:  (550, 50),   7:  (650, 50),   
    8:  (50, 150),  9:  (150, 150),  10: (250, 150),  11: (350, 150),
    12: (450, 150), 13: (550, 150),  14: (650, 150)
}

current_x_mm = 0
current_y_mm = 0

def setup_gpio():
    GPIO.setmode(GPIO.BCM)
    GPIO.setwarnings(False)
    GPIO.setup([DIR_X, STEP_X, DIR_Y, STEP_Y], GPIO.OUT)
    GPIO.output([DIR_X, STEP_X, DIR_Y, STEP_Y], GPIO.LOW)

def step_motor(dir_pin, step_pin, steps, direction_high):
    GPIO.output(dir_pin, GPIO.HIGH if direction_high else GPIO.LOW)
    for _ in range(abs(int(steps))):
        GPIO.output(step_pin, GPIO.HIGH)
        time.sleep(STEP_DELAY)
        GPIO.output(step_pin, GPIO.LOW)
        time.sleep(STEP_DELAY)

def move_to_plant(position_index):
    global current_x_mm, current_y_mm
    target_x, target_y = PLANT_COORDINATES[position_index]
    
    steps_x = (target_x - current_x_mm) * STEPS_PER_MM
    steps_y = (target_y - current_y_mm) * STEPS_PER_MM
    
    print(f"Moving to Plant {position_index}...")
    if steps_x != 0: step_motor(DIR_X, STEP_X, steps_x, direction_high=(steps_x > 0))
    if steps_y != 0: step_motor(DIR_Y, STEP_Y, steps_y, direction_high=(steps_y > 0))
        
    current_x_mm, current_y_mm = target_x, target_y
    time.sleep(1) # Let camera settle

def return_to_home():
    global current_x_mm, current_y_mm
    print("Returning to Home...")
    steps_x = -current_x_mm * STEPS_PER_MM
    steps_y = -current_y_mm * STEPS_PER_MM
    
    if steps_x != 0: step_motor(DIR_X, STEP_X, steps_x, direction_high=False)
    if steps_y != 0: step_motor(DIR_Y, STEP_Y, steps_y, direction_high=False)
        
    current_x_mm = 0
    current_y_mm = 0

def capture_image(filename):
    cap = cv2.VideoCapture(0)
    time.sleep(2)
    ret, frame = cap.read()
    if ret:
        frame_resized = cv2.resize(frame, (1920, 1080))
        cv2.imwrite(filename, frame_resized)
    cap.release()
    return ret

def run_student_algorithm(image_path):
    # TODO: Insert your TFLite model inference here
    return ["healthy", "disease", "pest"][int(time.time()) % 3] 

def run_wave():
    print(f"--- Starting Monitoring Wave ---")
    
    wave_data = supabase.table('waves').insert({'status': 'monitoring'}).execute()
    wave_id = wave_data.data[0]['id']
    
    for i in range(1, NUM_PLANTS + 1):
        move_to_plant(i)
        img_filename = f"plant_{i}.jpg"
        
        if capture_image(img_filename):
            classification = run_student_algorithm(img_filename)
            storage_path = f"{classification}/{wave_id}_plant_{i}.jpg"
            
            with open(img_filename, 'rb') as f:
                supabase.storage.from_('scans').upload(file=f, path=storage_path, file_options={"content-type": "image/jpeg"})
            
            public_url = supabase.storage.from_('scans').get_public_url(storage_path)
            
            supabase.table('wave_images').insert({
                'wave_id': wave_id,
                'position': i,
                'classification': classification,
                'image_url': public_url
            }).execute()
            
            print(f"Plant {i} Processed -> {classification}")
            os.remove(img_filename)

    return_to_home()
    
    supabase.table('waves').update({
        'status': 'completed',
        'completed_at': 'now()'
    }).eq('id', wave_id).execute()
    print("Wave complete.")

if __name__ == "__main__":
    setup_gpio()
    try:
        while True:
            run_wave()
            print("Waiting 30 minutes...")
            time.sleep(INTERVAL_SECONDS)
    except KeyboardInterrupt:
        print("Script stopped by user.")
    finally:
        GPIO.cleanup()