import serial
import time
import cv2

# --- Serial Configuration ---
# You will need to change this to the actual port your Pico connects to.
# On Windows, it will be something like 'COM3'. On a Raspberry Pi/Linux, it is usually '/dev/ttyACM0' or '/dev/ttyUSB0'
SERIAL_PORT = '/dev/ttyACM0' 
BAUD_RATE = 115200

# Open the serial connection to the Pico
try:
    pico = serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=1)
    # Wake up grblHAL
    pico.write(b"\r\n\r\n")
    time.sleep(2)
    pico.flushInput()
    print("Connected to grblHAL on Pico.")
except Exception as e:
    print(f"Failed to connect to Pico: {e}")
    exit()

# --- Plant Coordinates (G-code strings) ---
# --- Plant Coordinates (G-code strings) ---
PLANT_GCODE = [
    "G90",          # Enforce absolute coordinate mode
    "G0 X0 Y0",     # Plant 1 / Home Start
    "G0 X5 Y150",   # Plant 2
    "G0 X10 Y350",  # Plant 3
    "G0 X15 Y510",  # Plant 4
    "G0 X20 Y670",  # Plant 5
    "G0 X150 Y600", # Plant 6
    "G0 X150 Y450", # Plant 7
    "G0 X150 Y260", # Plant 8
    "G0 X150 Y120", # Plant 9
    "G0 X290 Y0",   # Plant 10
    "G0 X290 Y150", # Plant 11
    "G0 X290 Y350", # Plant 12
    "G0 X290 Y510", # Plant 13
    "G0 X290 Y690"  # Plant 14
]

def wait_for_idle():
    """
    Polls grblHAL to check if the machine is still moving.
    Blocks the script from taking a picture until the motors have completely stopped.
    """
    while True:
        pico.write(b"?\n")
        response = pico.readline().decode('utf-8').strip()
        
        # Look for the status report, e.g., <Idle|MPos:50.000,50.000,0.000>
        if response.startswith('<Idle'):
            break
        time.sleep(0.1)

def send_gcode(command):
    """Sends a command to the Pico and waits for it to execute."""
    print(f"Sending: {command}")
    pico.write((command + '\n').encode('utf-8'))
    
    # Wait for the 'ok' acknowledgement from GRBL's buffer
    while True:
        response = pico.readline().decode('utf-8').strip()
        if response == 'ok':
            break
            
    # Wait for physical movement to finish
    wait_for_idle()
    
    # Give the camera gantry 1 second to stop shaking before capturing
    time.sleep(1)

def capture_image(filename):
    """Snaps the photo at the current stopped position."""
    cap = cv2.VideoCapture(0)
    time.sleep(2) # Auto-focus
    ret, frame = cap.read()
    if ret:
        cv2.imwrite(filename, frame)
    cap.release()
    print(f"Captured: {filename}")
    return ret

def run_wave():
    print("--- Starting Automated Wave ---")
    
    # Ensure machine is in absolute positioning mode and millimeters
    send_gcode("G90") 
    send_gcode("G21")
    
    for i, gcode in enumerate(PLANT_GCODE, start=1):
        # 1. Move the machine
        send_gcode(gcode)
        
        # 2. Machine is confirmed stopped, take the photo
        img_filename = f"plant_{i}.jpg"
        capture_image(img_filename)
        
        # 3. TODO: Run your Supabase database upload logic here
        
    print("Wave complete. Returning to home.")
    send_gcode("G0 X0 Y0")

if __name__ == "__main__":
    try:
        run_wave()
    except KeyboardInterrupt:
        print("Stopping machine!")
        # Send a feed hold / stop command to GRBL in an emergency
        pico.write(b"!") 
    finally:
        pico.close()