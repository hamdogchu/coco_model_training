import subprocess
import time
import os

def capture_image(output_dir=".", filename=None, resolution="1920x1080", img_type="compressed"):
    
    # 1. Set the correct format and file extension based on user choice
    if img_type == "raw":
        img_format = "yuyv422"
        ext = ".png"  # Lossless for raw uncompressed
    elif img_type == "compressed":
        img_format = "mjpeg"
        ext = ".jpg"  # Standard JPEG for compressed
    else:
        print("[Warning] Not a proper format. Using default 'compressed' setting.")
        img_format = "mjpeg"
        ext = ".jpg"
        img_type = "compressed" # Update this so the filename matches

    # 2. Generate filename with the correct extension
    if filename is None:
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        filename = f"ugreen_{img_type}_{timestamp}{ext}"
    else:
        filename = f"{filename}{ext}"
        
    filepath = os.path.join(output_dir, filename)
    print(f"Asking FFmpeg to capture a {img_type} {resolution} frame...")

    # 3. The FFmpeg command
    command = [
        "ffmpeg",
        "-y",                               # Overwrite file if it exists
        "-f", "v4l2",                       # Use the standard Linux video driver
        "-input_format", img_format,        # Apply our dynamic format (YUYV or MJPG)
        "-video_size", resolution,          # Apply our dynamic resolution
        "-i", "/dev/video0",                # Your USB camera
        "-ss", "1.0",                       # Warm-up: Wait 1 second for auto-exposure
        "-frames:v", "1",                   # Grab exactly 1 clean frame
        filepath                            # Where to save it
    ]

    # 4. The Retry Loop (Try up to 3 times)
    max_attempts = 3
    for attempt in range(1, max_attempts + 1):
        try:
            # Run the command
            result = subprocess.run(command, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            print(f"[Success] Photo saved as: {filepath}")
            return True # Success! Exit the loop and the function.
            
        except subprocess.CalledProcessError as e:
            print(f"[Warning] Attempt {attempt}/{max_attempts} failed. Camera may be busy.")
            
            if attempt < max_attempts:
                print("Retrying in 2 seconds...")
                time.sleep(2) # Give the OS time to release the camera hardware
            else:
                # If we hit the max attempts, print the error and give up
                print(f"[Error] FFmpeg failed after {max_attempts} attempts. Giving up.")
                print(f"Error Details:\n{e.stderr.decode('utf-8')}")
                return False

# --- Run the test ---
if __name__ == "__main__":
    # Test Raw
    capture_image(resolution="2592x1944", img_type="raw")
    
    # Test Compressed
    # capture_image(resolution="3840x2160", img_type="compressed")