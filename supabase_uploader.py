import os
import re
from datetime import datetime, timezone
from supabase import create_client, Client

class WaveUploader:
    def __init__(self, supabase_url, supabase_key, bucket_name="scans", max_storage_mb=1000):
        self.supabase: Client = create_client(supabase_url, supabase_key)
        self.bucket_name = bucket_name
        self.max_bytes = max_storage_mb * 1024 * 1024
        self.trigger_threshold = 0.90
        self.target_threshold = 0.80

        # Define category lists based on your 15 classes
        self.diseases = [
            'Anthracnose', 'Bacterial Soft Rot', 'Big Vein', 'Downy Mildew', 
            'Lettuce Mosaic Virus', 'Other Disease', 'Powdery Mildew', 
            'Septoria Leaf Spot', 'Tip Burn'
        ]
        self.pests = [
            'Aphid', 'Leaf Miner', 'Other Pests', 'Thrip', 'Whitefly'
        ]

    def manage_storage(self):
        """Checks bucket capacity and deletes the oldest files if it exceeds 90%."""
        print("[Supabase] Checking cloud storage capacity...")
        try:
            response = self.supabase.storage.from_(self.bucket_name).list()
            files = [f for f in response if f['name'] != '.emptyFolderPlaceholder']
            total_size_bytes = sum(f.get('metadata', {}).get('size', 0) for f in files)
            capacity_percent = total_size_bytes / self.max_bytes
            
            print(f"[Supabase] Current Bucket Usage: {total_size_bytes / (1024*1024):.1f} MB ({capacity_percent * 100:.1f}%)")

            if capacity_percent >= self.trigger_threshold:
                print(f"[Supabase] Storage over {self.trigger_threshold * 100}%. Initiating cleanup of oldest waves...")
                files.sort(key=lambda x: x.get('created_at', ''))
                target_size = self.max_bytes * self.target_threshold
                files_to_delete = []
                
                for f in files:
                    if total_size_bytes <= target_size:
                        break 
                    files_to_delete.append(f['name'])
                    total_size_bytes -= f.get('metadata', {}).get('size', 0)
                
                if files_to_delete:
                    print(f"[Supabase] Deleting {len(files_to_delete)} old files to free up space...")
                    self.supabase.storage.from_(self.bucket_name).remove(files_to_delete)
                    print("[Supabase] Cleanup complete.")
                    
        except Exception as e:
            print(f"[Supabase] Warning: Failed to run storage management: {e}")

    def classify_plant(self, detections):
        """Applies your priority logic: Disease > Pest > Healthy"""
        has_disease = any(d['class'] in self.diseases for d in detections)
        has_pest = any(d['class'] in self.pests for d in detections)

        if has_disease:
            return 'disease'
        elif has_pest:
            return 'pest'
        else:
            return 'healthy'

    def upload_wave(self, local_dir, wave_results):
        # 1. Manage Storage space first
        self.manage_storage() 

        image_paths = [f for f in os.listdir(local_dir) if f.lower().endswith(('.jpg', '.png'))]
        if not image_paths:
            print(f"[Supabase] No images to upload.")
            return

        print("\n[Supabase] Initiating Database and Storage Sync...")

        # --- TIMESTAMP FIX ---
        # Get the current time in UTC, formatted to an ISO string for Postgres
        now_iso = datetime.now(timezone.utc).isoformat()
        
        # 2. Create the Wave record in the Database first
        wave_data = {
            "status": "completed",
            "started_at": now_iso,     # Needed so your Flutter app can sort newest-first
            "completed_at": now_iso    # Needed so your Flutter app displays the timestamp
        } 
        
        try:
            wave_response = self.supabase.table("waves").insert(wave_data).execute()
            wave_id = wave_response.data[0]['id']
            print(f"[Supabase] Created Wave ID: {wave_id}")
        except Exception as e:
            print(f"[Supabase] Error creating wave in database: {e}")
            return

        wave_timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        # 3. Process and Upload each image
        for filename in image_paths:
            local_path = os.path.join(local_dir, filename)
            remote_name = f"wave_{wave_timestamp}_{filename}"
            
            # Upload to Storage Bucket
            try:
                with open(local_path, 'rb') as f:
                    self.supabase.storage.from_(self.bucket_name).upload(
                        path=remote_name, 
                        file=f.read(),
                        file_options={"content-type": "image/jpeg", "upsert": "true"}
                    )
                
                # Retrieve the public URL for the database
                public_url = self.supabase.storage.from_(self.bucket_name).get_public_url(remote_name)
            except Exception as e:
                print(f"    [!] Failed to upload {filename} to bucket: {e}")
                continue

            # 4. Extract position integer from filename (e.g., "scanned_plant_14.png" -> 14)
            match = re.search(r'plant_(\d+)', filename)
            position = int(match.group(1)) if match else 0

            # 5. Determine Database Classification
            detections = wave_results.get(filename, [])
            classification = self.classify_plant(detections)

            # 6. Insert Row into wave_images Database
            image_record = {
                "wave_id": wave_id,
                "position": position,
                "classification": classification,
                "image_url": public_url,
                "detections": detections
            }

            try:
                self.supabase.table("wave_images").insert(image_record).execute()
                print(f" -> DB Sync: Plant {position} | Class: {classification} | Uploaded")
            except Exception as e:
                print(f"    [!] Failed to insert database record for Plant {position}: {e}")

        print("[Supabase] Wave upload and database sync complete.\n")