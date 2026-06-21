import os
import re
from datetime import datetime, timezone
from supabase import create_client, Client
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

# This tells Google we only want permission to edit files created by this app
SCOPES = ['https://www.googleapis.com/auth/drive.file']

class CloudUploader:
    def __init__(self, supabase_url, supabase_key, gdrive_folder_id):
        self.supabase: Client = create_client(supabase_url, supabase_key)
        self.gdrive_folder_id = gdrive_folder_id
        self.gdrive_active = False

        creds = None
        # The file token.json stores your login session so you only have to log in ONCE.
        if os.path.exists('token.json'):
            creds = Credentials.from_authorized_user_file('token.json', SCOPES)

        try:
            # If there are no valid credentials, pop open a browser window!
            if not creds or not creds.valid:
                if creds and creds.expired and creds.refresh_token:
                    creds.refresh(Request())
                else:
                    flow = InstalledAppFlow.from_client_secrets_file('credentials.json', SCOPES)
                    creds = flow.run_local_server(port=0)
                
                # Save the session token for the next time the Pi reboots
                with open('token.json', 'w') as token:
                    token.write(creds.to_json())

            self.gdrive_service = build('drive', 'v3', credentials=creds)
            self.gdrive_active = True
            print("[GDrive] Authenticated successfully as HUMAN USER.")
        except Exception as e:
            print(f"[GDrive] Failed to initialize Google Drive: {e}")
            print("[!] Make sure 'credentials.json' is in the folder!")

        self.diseases = [
            'Anthracnose', 'Bacterial Soft Rot', 'Big Vein', 'Downy Mildew', 
            'Lettuce Mosaic Virus', 'Other Disease', 'Powdery Mildew', 
            'Septoria Leaf Spot', 'Tip Burn'
        ]
        self.pests = ['Aphid', 'Leaf Miner', 'Other Pests', 'Thrip', 'Whitefly']

    def classify_plant(self, detections):
        has_disease = any(d['class'] in self.diseases for d in detections)
        has_pest = any(d['class'] in self.pests for d in detections)

        if has_disease: return 'disease'
        elif has_pest: return 'pest'
        else: return 'healthy'

    def upload_wave(self, local_dir, wave_results):
        if not self.gdrive_active:
            print("[Error] Google Drive not active. Cannot sync to cloud.")
            return

        image_paths = [f for f in os.listdir(local_dir) if f.lower().endswith(('.jpg', '.png'))]
        if not image_paths:
            return

        print("\n[Cloud Sync] Initiating GDrive Upload & Supabase DB Sync...")

        now_iso = datetime.now(timezone.utc).isoformat()
        wave_data = {"status": "completed", "started_at": now_iso, "completed_at": now_iso} 
        
        try:
            wave_response = self.supabase.table("waves").insert(wave_data).execute()
            wave_id = wave_response.data[0]['id']
        except Exception as e:
            print(f"[Supabase] Error creating wave in database: {e}")
            return

        wave_timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        for filename in image_paths:
            local_path = os.path.join(local_dir, filename)
            remote_name = f"wave_{wave_timestamp}_{filename}"
            
            public_url = None
            try:
                file_metadata = {'name': remote_name, 'parents': [self.gdrive_folder_id]}
                media = MediaFileUpload(local_path, mimetype='image/jpeg', resumable=True)
                
                file = self.gdrive_service.files().create(
                    body=file_metadata, media_body=media, fields='id').execute()
                file_id = file.get('id')
                
                self.gdrive_service.permissions().create(
                    fileId=file_id, body={'type': 'anyone', 'role': 'reader'}, fields='id').execute()

                public_url = f"https://drive.google.com/uc?export=view&id={file_id}"
                
            except Exception as e:
                print(f"    [!] Failed to upload {filename} to GDrive: {e}")
                continue

            if not public_url:
                continue

            match = re.search(r'plant_(\d+)', filename)
            position = int(match.group(1)) if match else 0
            detections = wave_results.get(filename, [])
            classification = self.classify_plant(detections)

            image_record = {
                "wave_id": wave_id,
                "position": position,
                "classification": classification,
                "image_url": public_url, 
                "detections": detections
            }

            try:
                self.supabase.table("wave_images").insert(image_record).execute()
                print(f" -> DB Sync: Plant {position} | Class: {classification} | GDrive Synced")
            except Exception as e:
                print(f"    [!] Failed to insert database record: {e}")

        print("[Cloud Sync] Cycle complete.\n")