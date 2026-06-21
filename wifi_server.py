from flask import Flask, jsonify, request
from flask_cors import CORS
import subprocess

app = Flask(__name__)
CORS(app)

@app.route('/scan', methods=['GET'])
def scan():
    try:
        subprocess.run(['nmcli', 'dev', 'wifi', 'rescan'], timeout=5, check=False)
        
        # Grab both the ACTIVE status and the SSID
        output = subprocess.check_output(['nmcli', '-t', '-f', 'ACTIVE,SSID', 'dev', 'wifi']).decode('utf-8')
        
        networks = []
        current_network = None
        
        for line in output.split('\n'):
            line = line.strip()
            if not line:
                continue
            
            parts = line.split(':')
            if len(parts) >= 2:
                active_status = parts[0]
                ssid = ':'.join(parts[1:]) # Rejoin in case the Wi-Fi name has a colon in it
                
                if ssid and ssid not in networks:
                    networks.append(ssid)
                
                if active_status == 'yes':
                    current_network = ssid
                    
        return jsonify({
            'success': True, 
            'networks': networks, 
            'current_network': current_network
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/connect', methods=['POST'])
def connect():
    data = request.json
    ssid = data.get('ssid')
    password = data.get('password')
    try:
        cmd = ['nmcli', 'dev', 'wifi', 'connect', ssid]
        if password:
            cmd.extend(['password', password])
        subprocess.check_output(cmd)
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

if __name__ == '__main__':
    print("Starting Local Wi-Fi Manager on port 5001...")
    app.run(host='127.0.0.1', port=5001)