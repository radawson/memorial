import os
import sqlite3
import requests
import threading
from datetime import datetime, timedelta
from pathlib import Path
from flask import Flask, render_template, jsonify, send_from_directory
from googleapiclient.discovery import build
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)

# Configuration
GOOGLE_DRIVE_FOLDER_ID = os.getenv('GOOGLE_DRIVE_FOLDER_ID', '1EGGGv1mw0Wd2SLlwU14Em6-W-sob7YjO')
GOOGLE_API_KEY = os.getenv('GOOGLE_API_KEY')
DB_PATH = 'photos.db'
CACHE_DIR = 'cached_images'
CACHE_DURATION_MINUTES = 10  # Refresh from Drive API after this many minutes

# Create cache directory if it doesn't exist
Path(CACHE_DIR).mkdir(exist_ok=True)

def init_db():
    """Initialize the SQLite database"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS photos (
            id TEXT PRIMARY KEY,
            name TEXT,
            url TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS cache_info (
            key TEXT PRIMARY KEY,
            last_updated TIMESTAMP
        )
    ''')
    conn.commit()
    conn.close()

def should_refresh_cache():
    """Check if cache is older than CACHE_DURATION_MINUTES"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('SELECT last_updated FROM cache_info WHERE key = ?', ('photos',))
    result = c.fetchone()
    conn.close()
    
    if not result:
        return True
    
    last_updated = datetime.fromisoformat(result[0])
    return datetime.now() - last_updated > timedelta(minutes=CACHE_DURATION_MINUTES)

def save_photos_to_db(photos):
    """Save photos to SQLite database"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    # Clear existing photos
    c.execute('DELETE FROM photos')
    
    # Insert new photos
    for photo in photos:
        c.execute('INSERT INTO photos (id, name, url) VALUES (?, ?, ?)',
                  (photo['id'], photo['name'], photo['url']))
    
    # Update cache timestamp
    c.execute('INSERT OR REPLACE INTO cache_info (key, last_updated) VALUES (?, ?)',
              ('photos', datetime.now().isoformat()))
    
    conn.commit()
    conn.close()

def get_photos_from_db():
    """Get photos from SQLite database"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('SELECT id, name, url FROM photos ORDER BY name')
    rows = c.fetchall()
    conn.close()
    
    return [{'id': row[0], 'name': row[1], 'url': row[2]} for row in rows]

def download_image(file_id, file_name):
    """Download an image from Google Drive and cache it locally"""
    cache_path = os.path.join(CACHE_DIR, file_id)
    
    # Skip if already cached
    if os.path.exists(cache_path):
        print(f"⏭ Skipped (already cached): {file_name}")
        return cache_path
    
    # Try multiple URL formats to download the image
    urls_to_try = [
        f"https://drive.google.com/uc?export=download&id={file_id}",
        f"https://lh3.googleusercontent.com/d/{file_id}",
        f"https://drive.google.com/thumbnail?id={file_id}&sz=w2000"
    ]
    
    for url in urls_to_try:
        try:
            response = requests.get(url, timeout=30, allow_redirects=True)
            if response.status_code == 200 and len(response.content) > 0:
                # Save the image
                with open(cache_path, 'wb') as f:
                    f.write(response.content)
                print(f"✓ Downloaded: {file_name}")
                return cache_path
        except Exception as e:
            print(f"Failed to download from {url}: {e}")
            continue
    
    print(f"✗ Could not download {file_name} from any URL")
    return None

def download_images_async(files_to_download):
    """Download multiple images asynchronously in the background"""
    def download_worker():
        for file_id, file_name in files_to_download:
            # Double-check file doesn't exist (might have been downloaded by another process)
            cache_path = os.path.join(CACHE_DIR, file_id)
            if not os.path.exists(cache_path):
                download_image(file_id, file_name)
            else:
                print(f"⏭ Skipped (already exists): {file_name}")
    
    # Start download in background thread
    thread = threading.Thread(target=download_worker, daemon=True)
    thread.start()
    print(f"⏬ Started background download of {len(files_to_download)} images")

def fetch_photos_from_drive():
    """Fetch all image files from the public Google Drive folder"""
    try:
        # Check if API key is set
        if not GOOGLE_API_KEY:
            print("✗ ERROR: GOOGLE_API_KEY not set in .env file!")
            return []
        
        # Build the Drive API client with API key (for public folders)
        print(f"🔍 Querying folder: {GOOGLE_DRIVE_FOLDER_ID}")
        service = build('drive', 'v3', developerKey=GOOGLE_API_KEY)
        
        # Query for all image files in the folder
        # Set pageSize to 1000 (max allowed) to get all photos
        results = service.files().list(
            q=f"'{GOOGLE_DRIVE_FOLDER_ID}' in parents and (mimeType contains 'image/')",
            fields="files(id, name, mimeType, thumbnailLink)",
            orderBy='name',
            pageSize=1000
        ).execute()
        
        files = results.get('files', [])
        print(f"📊 Drive API returned {len(files)} files")
        
        # If there are more than 1000 files, handle pagination
        while 'nextPageToken' in results:
            results = service.files().list(
                q=f"'{GOOGLE_DRIVE_FOLDER_ID}' in parents and (mimeType contains 'image/')",
                fields="files(id, name, mimeType, thumbnailLink)",
                orderBy='name',
                pageSize=1000,
                pageToken=results['nextPageToken']
            ).execute()
            files.extend(results.get('files', []))
        
        # Build photo list and identify which images need downloading
        photo_urls = []
        files_to_download = []
        
        for file in files:
            file_id = file['id']
            file_name = file['name']
            cache_path = os.path.join(CACHE_DIR, file_id)
            
            # Add to photo list regardless of cache status
            photo_url = f"/images/{file_id}"
            photo_urls.append({
                'id': file_id,
                'name': file_name,
                'url': photo_url
            })
            
            # Track which images need downloading
            if not os.path.exists(cache_path):
                files_to_download.append((file_id, file_name))
        
        # Download missing images asynchronously
        if files_to_download:
            print(f"📥 {len(files_to_download)} new images need downloading")
            download_images_async(files_to_download)
        else:
            print(f"✓ All {len(files)} images already cached")
        
        print(f"✓ Prepared {len(photo_urls)} photo URLs")
        return photo_urls
    except Exception as e:
        print(f"✗ ERROR fetching photos from Drive: {e}")
        import traceback
        traceback.print_exc()
        return []

@app.route('/')
def index():
    """Render the slideshow page"""
    return render_template('index.html')

@app.route('/images/<file_id>')
def serve_image(file_id):
    """Serve a cached image, or return placeholder if not yet downloaded"""
    cache_path = os.path.join(CACHE_DIR, file_id)
    
    if os.path.exists(cache_path):
        return send_from_directory(CACHE_DIR, file_id)
    else:
        # Return a simple placeholder response
        # The image is being downloaded in the background
        from flask import Response
        return Response(status=404)

def get_photos():
    """Get photos from cache or refresh from Drive if needed"""
    # Check if we need to refresh the cache
    if should_refresh_cache():
        print("Cache expired or empty, fetching from Google Drive...")
        photos = fetch_photos_from_drive()
        if photos and len(photos) > 0:
            save_photos_to_db(photos)
            print(f"✓ Refreshed cache with {len(photos)} photos")
            return photos
        else:
            print("⚠ Failed to fetch from Drive (or 0 photos returned), using cached data")
            # Fall back to existing cached data - don't clear the database!
            cached_photos = get_photos_from_db()
            if cached_photos and len(cached_photos) > 0:
                print(f"✓ Using {len(cached_photos)} cached photos")
                return cached_photos
            else:
                print("✗ No cached photos available!")
                return []
    else:
        print("Using cached photos from database")
        photos = get_photos_from_db()
    
    return photos

@app.route('/api/photos')
def api_photos():
    """API endpoint to get list of photos"""
    photos = get_photos()
    
    # Get cache info for countdown timer
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('SELECT last_updated FROM cache_info WHERE key = ?', ('photos',))
    result = c.fetchone()
    conn.close()
    
    cache_info = {}
    if result:
        last_updated = datetime.fromisoformat(result[0])
        next_refresh = last_updated + timedelta(minutes=CACHE_DURATION_MINUTES)
        seconds_until_refresh = int((next_refresh - datetime.now()).total_seconds())
        cache_info = {
            'last_updated': last_updated.isoformat(),
            'next_refresh': next_refresh.isoformat(),
            'seconds_until_refresh': max(0, seconds_until_refresh)
        }
    
    return jsonify({
        'photos': photos, 
        'count': len(photos),
        'cache_info': cache_info
    })

@app.route('/api/refresh')
def api_refresh():
    """Force refresh photos from Google Drive"""
    print("Manual refresh requested...")
    photos = fetch_photos_from_drive()
    if photos:
        save_photos_to_db(photos)
        return jsonify({'success': True, 'count': len(photos), 'message': 'Photos refreshed successfully'})
    else:
        return jsonify({'success': False, 'message': 'Failed to fetch photos from Drive'}), 500

if __name__ == '__main__':
    init_db()
    print(f"Database initialized. Cache will refresh every {CACHE_DURATION_MINUTES} minutes.")
    app.run(debug=True, host='0.0.0.0', port=5000)

