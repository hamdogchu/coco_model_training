import serial
import time
import sys
import os
from capture_4k_img import capture_image

# --- Configuration ---
SERIAL_PORT = '/dev/ttyACM0' 
BAUD_RATE = 115200
CAP_DIR = 'wave_captures'

setup_commands = [
    "G21", # millimeters
    "G90", # absolute coordinate
    "G17", # XY plane
    "G94",  # units per minute feed rate mode
    "G92 X0 Y0" #machine think its in zero
]

coordinates = [
    ("X0", "Y0"),      
    ("X0", "Y150"),
    ("X0", "Y350"),
    ("X0", "Y510"),
    ("X0", "Y670"),
    ("X120", "Y600"),
    ("X120", "Y450"),
    ("X120", "Y260"),
    ("X120", "Y120"),
    ("X260", "Y0"),
    ("X260", "Y150"),
    ("X260", "Y350"),
    ("X260", "Y510"),
    ("X260", "Y670") 
]

def wait_for_idle(ser):
    """Polls grblHAL to pause Python until the physical movement stops."""
    # Give the controller a fraction of a second to start the movement
    time.sleep(0.1) 
    ser.flushInput() 
    
    while True:
        # Send the status report query
        ser.write(b'?')
        line = ser.readline().decode('utf-8').strip()
        
        # grbl status looks like: <Idle|MPos:0.000,0.000,0.000|FS:0,0>
        if line.startswith('<'):
            # Extract the current machine state (Idle, Run, Sleep, etc.)
            status = line.split('|')[0].replace('<', '')
            if status == 'Idle':
                break
        
        # Poll 10 times a second to avoid overloading the serial connection
        time.sleep(0.1)

def send_command(ser, cmd):
    """Sends a command to grbl and waits for the 'ok' response."""
    print(f"Sending: {cmd}")
    ser.write((cmd + '\r\n').encode('utf-8')) 
    
    while True:
        line = ser.readline().decode('utf-8').strip()
        if line == 'ok':
            break
        elif 'error' in line.lower():
            print(f"GRBL Error: {line}")
            break

def run_hardware_sequence(CAPTURE_DIR=CAP_DIR):
    # 1. Setup Camera and Directory
    os.makedirs(CAPTURE_DIR, exist_ok=True)

    time.sleep(2) # Give the camera sensor time to warm up and auto-expose
    
    try:
        print(f"Connecting to {SERIAL_PORT} at {BAUD_RATE} baud...")
        with serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=1) as ser:
            
            try:
                # Wake up grbl
                ser.write(b'\r\n\r\n')
                time.sleep(2)   
                ser.flushInput()  
                print("Connected to grblHAL.")

                print("\n--- Sending Setup Commands ---")
                for cmd in setup_commands:
                    send_command(ser, cmd)

                print("\n--- Starting Plant Sequence ---")
                time.sleep(3.5)
                
                # enumerate provides an index (i) starting at 1 for naming the plants
                for i, (x, y) in enumerate(coordinates, start=1):
                    
                    # A. Command the move
                    move_cmd = f"G0 {x} {y}"
                    send_command(ser, move_cmd)
                    
                    # B. Wait for the machine to physically arrive at the coordinate
                    print(f"Moving to plant {i}...")
                    wait_for_idle(ser)
                    
                    # D. Hardware pause for 3.5 seconds
                    send_command(ser, "G4 P2")

                    # C. Take the picture
                    #setup
                    #v4l2-ctl --list-formats-ext
                    capture_image(CAPTURE_DIR, filename=f"plant_{i}", resolution="2592x1944", img_type="raw")
                    print(f"capturing plant_{i}")
                    
                    # E. Wait out the dwell time before looping
                    wait_for_idle(ser)

                print("\n--- Returning to Home ---")
                send_command(ser, "G0 X0 Y0")
                wait_for_idle(ser)
                
             
            except KeyboardInterrupt:
                print("\n\n[!] Ctrl+C detected! Triggering grblHAL Soft Reset...")
                ser.write(b'\x18')
                ser.flush()
                time.sleep(0.5) 
                print("Motors halted. Buffer cleared.")
                sys.exit(0)
            print("\nSequence complete.")
    except serial.SerialException as e:
        print(f"\nSerial Error: {e}")
        print("Hint: Check if your Pico is connected and the port matches.")
        sys.exit(1)
        

if __name__ == "__main__":
    run_hardware_sequence()
    
