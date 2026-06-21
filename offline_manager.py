import os
import json
import shutil
import socket
import subprocess # <--- NEW: Required to send OS commands
from datetime import datetime, timezone
from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS

SETTINGS_FILE = 'local_settings.json'
OFFLINE_QUEUE_DIR = 'offline_queue'

# Global Local State
local_settings = {
    'interval_minutes': 30,
    'is_paused': False,
    'force_trigger': False,
    'needs_sync': False,
    'is_scanning': False,
    'is_uploading': False
}

def load_settings():
    global local_settings
    if os.path.exists(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE, 'r') as f:
                saved = json.load(f)
                local_settings.update(saved)
        except Exception:
            pass

def save_settings():
    with open(SETTINGS_FILE, 'w') as f:
        json.dump(local_settings, f)

def get_current_settings():
    return local_settings

def reset_force_trigger():
    global local_settings
    local_settings['force_trigger'] = False
    save_settings()

def set_scanning_state(is_scanning_status):
    global local_settings
    local_settings['is_scanning'] = is_scanning_status
    local_settings['needs_sync'] = True
    save_settings()

def set_uploading_state(is_uploading_status):
    global local_settings
    local_settings['is_uploading'] = is_uploading_status
    local_settings['needs_sync'] = True
    save_settings()
    
def set_last_completed():
    global local_settings
    # Broadcasts the exact completion time in standard ISO format
    local_settings['last_completed'] = datetime.now(timezone.utc).isoformat()
    save_settings()

def set_seconds_remaining(seconds):
    global local_settings
    local_settings['seconds_remaining'] = seconds

def has_offline_waves():
    if not os.path.exists(OFFLINE_QUEUE_DIR): return False
    waves = [d for d in os.listdir(OFFLINE_QUEUE_DIR) if d.startswith("wave_")]
    return len(waves) > 0

app = Flask(__name__)
CORS(app)

# --- NEW: Route to force the on-screen keyboard to appear ---
@app.route('/toggle_keyboard', methods=['POST'])
def toggle_keyboard():
    try:
        # Explicitly targets DISPLAY=:0. If dbus fails (e.g. over SSH), it falls back to launching onboard directly!
        os.system('DISPLAY=:0 dbus-send --type=method_call --dest=org.onboard.Onboard /org/onboard/Onboard/Keyboard org.onboard.Onboard.Keyboard.ToggleVisible || DISPLAY=:0 onboard &')
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

# --- NEW: Route to toggle fullscreen (F11) ---
@app.route('/toggle_fullscreen', methods=['POST'])
def toggle_fullscreen():
    try:
        # Explicitly tells xdotool to target DISPLAY=:0 so it knows which monitor to press F11 on
        os.system('DISPLAY=:0 xdotool key F11')
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

# --- Routes to serve offline images to the LCD ---
@app.route('/offline_waves', methods=['GET'])
def list_offline_waves():
    if not os.path.exists(OFFLINE_QUEUE_DIR):
        return jsonify({'waves': []})
    # List all wave folders, sorted newest first
    waves = sorted([d for d in os.listdir(OFFLINE_QUEUE_DIR) if d.startswith("wave_")], reverse=True)
    return jsonify({'waves': waves})

@app.route('/offline_waves/<wave_id>/data', methods=['GET'])
def get_offline_wave_data(wave_id):
    wave_dir = os.path.join(OFFLINE_QUEUE_DIR, wave_id)
    results_file = os.path.join(wave_dir, "results.json")
    if os.path.exists(results_file):
        try:
            with open(results_file, "r") as f:
                data = json.load(f)
            return jsonify({'success': True, 'results': data})
        except Exception as e:
            return jsonify({'success': False, 'error': str(e)}), 500
    return jsonify({'success': False, 'error': 'Not found'}), 404

@app.route('/offline_waves/<wave_id>/image/<filename>', methods=['GET'])
def serve_offline_image(wave_id, filename):
    wave_dir = os.path.join(OFFLINE_QUEUE_DIR, wave_id)
    return send_from_directory(wave_dir, filename)

# --- 2. LOCAL API FLASK ROUTES ---
@app.route('/settings', methods=['GET'])
def get_settings_route():
    return jsonify(local_settings)

@app.route('/settings', methods=['POST'])
def update_settings_route():
    global local_settings
    data = request.json
    if 'interval_minutes' in data: local_settings['interval_minutes'] = data['interval_minutes']
    if 'is_paused' in data: local_settings['is_paused'] = data['is_paused']
    if 'force_trigger' in data: local_settings['force_trigger'] = data['force_trigger']
    
    local_settings['needs_sync'] = True
    save_settings()
    return jsonify({'success': True, 'settings': local_settings})

def start_local_api():
    app.run(host='127.0.0.1', port=5000, debug=False, use_reloader=False)


# --- 3. NETWORK & SYNC LOGIC ---
def check_internet():
    try:
        socket.create_connection(("8.8.8.8", 53), timeout=2)
        return True
    except OSError:
        return False

def sync_settings_with_supabase(supabase):
    global local_settings
    try:
        now_iso = datetime.now(timezone.utc).isoformat()

        if local_settings.get('needs_sync'):
            # Force Supabase to follow RPi changes AND send heartbeat
            supabase.table('tray_settings').update({
                'interval_minutes': local_settings['interval_minutes'],
                'is_paused': local_settings['is_paused'],
                'force_trigger': local_settings['force_trigger'],
                'is_scanning': local_settings.get('is_scanning', False),
                'is_uploading': local_settings.get('is_uploading', False), 
                'last_heartbeat': now_iso 
            }).eq('id', 1).execute()
            
            local_settings['needs_sync'] = False
            save_settings()
            print("[Sync] Local RPi changes pushed to Supabase.")
        else:
            # Ping the database to say we are alive
            supabase.table('tray_settings').update({
                'last_heartbeat': now_iso,
                'is_scanning': local_settings.get('is_scanning', False),
                'is_uploading': local_settings.get('is_uploading', False) 
            }).eq('id', 1).execute()

            # Pull remote changes from the mobile app
            remote_res = supabase.table('tray_settings').select('*').eq('id', 1).execute()
            if remote_res.data:
                remote = remote_res.data[0]
                local_settings['interval_minutes'] = remote.get('interval_minutes', 30)
                local_settings['is_paused'] = remote.get('is_paused', False)
                
                if remote.get('force_trigger'):
                    local_settings['force_trigger'] = True
                    supabase.table('tray_settings').update({'force_trigger': False}).eq('id', 1).execute()
                    
                save_settings()
    except Exception as e:
        print(f"[!] Network sync error: {e}")

# --- 4. OFFLINE QUEUE LOGIC ---
def queue_wave_offline(ai_results, processed_dir):
    os.makedirs(OFFLINE_QUEUE_DIR, exist_ok=True)
    wave_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    wave_dir = os.path.join(OFFLINE_QUEUE_DIR, f"wave_{wave_id}")
    os.makedirs(wave_dir, exist_ok=True)
    
    for filename in os.listdir(processed_dir):
        if filename.lower().endswith(('.jpg', '.png')):
            shutil.copy(os.path.join(processed_dir, filename), os.path.join(wave_dir, filename))
            
    with open(os.path.join(wave_dir, "results.json"), "w") as f:
        json.dump(ai_results, f)
        
    print(f"[Offline] Wave {wave_id} securely saved to local storage.")
    
    waves = sorted([d for d in os.listdir(OFFLINE_QUEUE_DIR) if d.startswith("wave_")])
    while len(waves) > 10:
        oldest = waves.pop(0)
        print(f"[Offline] Storage limit reached. Deleting oldest wave: {oldest}")
        shutil.rmtree(os.path.join(OFFLINE_QUEUE_DIR, oldest))

def sync_offline_queue(uploader):
    if not os.path.exists(OFFLINE_QUEUE_DIR):
        return
        
    waves = sorted([d for d in os.listdir(OFFLINE_QUEUE_DIR) if d.startswith("wave_")])
    if not waves:
        return
        
    print(f"\n[Sync] Found {len(waves)} offline waves in local storage. Uploading to Cloud...")
    for wave_folder in waves:
        wave_dir = os.path.join(OFFLINE_QUEUE_DIR, wave_folder)
        results_file = os.path.join(wave_dir, "results.json")
        
        if os.path.exists(results_file):
            try:
                with open(results_file, "r") as f:
                    ai_results = json.load(f)
                
                print(f" -> Uploading backlog {wave_folder}...")
                uploader.upload_wave(wave_dir, ai_results)
                shutil.rmtree(wave_dir)
            except Exception as e:
                print(f" -> [!] Failed to upload {wave_folder}: {e}")
                break