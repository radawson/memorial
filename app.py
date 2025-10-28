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
    print("\n=== FETCH PHOTOS FROM DRIVE ===")
    try:
        # ------------------------------------------------------------------
        # 1. BASIC SANITY CHECKS
        # ------------------------------------------------------------------
        if not GOOGLE_API_KEY:
            print("ERROR: GOOGLE_API_KEY not set in .env file!")
            return []
        if not GOOGLE_DRIVE_FOLDER_ID:
            print("ERROR: GOOGLE_DRIVE_FOLDER_ID not set!")
            return []

        print(f"Using API key: {GOOGLE_API_KEY[:8]}…")
        print(f"Folder ID      : {GOOGLE_DRIVE_FOLDER_ID}")

        # ------------------------------------------------------------------
        # 2. BUILD THE SERVICE (with a tiny timeout so we fail fast)
        # ------------------------------------------------------------------
        from googleapiclient.discovery import build
        from googleapiclient.errors import HttpError
        import httplib2

        service = build('drive', 'v3',
                        developerKey=GOOGLE_API_KEY,
                        cache_discovery=False)   # avoid stale discovery cache

        # ------------------------------------------------------------------
        # 3. FIRST PAGE – we also capture the raw response for debugging
        # ------------------------------------------------------------------
        query = f"'{GOOGLE_DRIVE_FOLDER_ID}' in parents and mimeType contains 'image/'"
        print(f"Query          : {query}")

        request = service.files().list(
            q=query,
            fields="nextPageToken, files(id, name, mimeType, thumbnailLink, webViewLink)",
            orderBy='name',
            pageSize=1000
        )

        # Execute the request inside a try/except that prints *everything*
        try:
            results = request.execute(http=httplib2.Http(timeout=30))
        except HttpError as http_err:
            # Google-specific HTTP error (401, 403, 404, …)
            print(f"HTTP ERROR {http_err.resp.status} from Drive API:")
            print(http_err.content.decode())
            return []
        except Exception as exc:
            print(f"UNEXPECTED EXCEPTION while calling Drive API:")
            import traceback
            traceback.print_exc()
            return []

        files = results.get('files', [])
        print(f"First page returned {len(files)} files")
        print(f"Raw first-page keys: {list(results.keys())}")

        # ------------------------------------------------------------------
        # 4. PAGINATION LOOP (with the same detailed logging)
        # ------------------------------------------------------------------
        page_token = results.get('nextPageToken')
        page = 1
        while page_token:
            page += 1
            print(f"Fetching page {page} (token={page_token[:20]}…)")
            request = service.files().list(
                q=query,
                fields="nextPageToken, files(id, name, mimeType, thumbnailLink, webViewLink)",
                orderBy='name',
                pageSize=1000,
                pageToken=page_token
            )
            try:
                results = request.execute(http=httplib2.Http(timeout=30))
            except HttpError as http_err:
                print(f"HTTP ERROR on page {page}: {http_err.resp.status}")
                print(http_err.content.decode())
                break
            except Exception as exc:
                print(f"Exception on page {page}:")
                import traceback
                traceback.print_exc()
                break

            page_files = results.get('files', [])
            files.extend(page_files)
            print(f"Page {page} added {len(page_files)} files (total now {len(files)})")
            page_token = results.get('nextPageToken')

        # ------------------------------------------------------------------
        # 5. FINAL SUMMARY
        # ------------------------------------------------------------------
        print(f"TOTAL files retrieved from Drive: {len(files)}")
        if not files:
            print("WARNING: No files matched the query – check folder ID, sharing, and MIME filter.")
            return []

        # ------------------------------------------------------------------
        # 6. BUILD PHOTO LIST + schedule missing downloads
        # ------------------------------------------------------------------
        photo_urls = []
        files_to_download = []

        for file in files:
            file_id   = file['id']
            file_name = file.get('name', '(no name)')
            cache_path = os.path.join(CACHE_DIR, file_id)

            photo_urls.append({
                'id'   : file_id,
                'name' : file_name,
                'url'  : f"/images/{file_id}"
            })

            if not os.path.exists(cache_path):
                files_to_download.append((file_id, file_name))

        if files_to_download:
            print(f"{len(files_to_download)} images are missing locally – starting async download")
            download_images_async(files_to_download)
        else:
            print("All images already cached locally")

        print("=== FETCH COMPLETE ===\n")
        return photo_urls

    except Exception as e:
        print("FATAL ERROR in fetch_photos_from_drive():")
        import traceback, sys
        traceback.print_exc(file=sys.stdout)
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
    """Get photos from cache - ALWAYS return cached data immediately"""
    # ALWAYS return cached data first for instant loading
    cached_photos = get_photos_from_db()
    
    if cached_photos and len(cached_photos) > 0:
        print(f"✓ Returning {len(cached_photos)} cached photos")
        
        # Check in background if we need to refresh (non-blocking)
        if should_refresh_cache():
            print("⏰ Cache refresh needed - starting background refresh...")
            refresh_cache_async()
        
        return cached_photos
    else:
        # No cache exists - need to fetch for first time (blocking)
        print("📥 No cache found, fetching from Google Drive (first run)...")
        photos = fetch_photos_from_drive()
        if photos and len(photos) > 0:
            save_photos_to_db(photos)
            print(f"✓ Initial cache created with {len(photos)} photos")
            return photos
        else:
            print("✗ Failed to fetch photos from Drive")
            return []

def refresh_cache_async():
    """Refresh the cache in a background thread without blocking the response"""
    def refresh_worker():
        print("🔄 Background refresh starting...")
        photos = fetch_photos_from_drive()
        if photos and len(photos) > 0:
            save_photos_to_db(photos)
            print(f"✓ Background refresh complete: {len(photos)} photos in cache")
        else:
            print("⚠ Background refresh failed, keeping existing cache")
    
    # Start refresh in background thread
    thread = threading.Thread(target=refresh_worker, daemon=True)
    thread.start()

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

@app.route('/api/debug/drive')
def debug_drive():
    """Return the raw JSON that the Drive API gave us (or the error)"""
    photos = fetch_photos_from_drive()
    # Re-run the same query but capture the *raw* response dict
    try:
        service = build('drive', 'v3', developerKey=GOOGLE_API_KEY, cache_discovery=False)
        results = service.files().list(
            q=f"'{GOOGLE_DRIVE_FOLDER_ID}' in parents and mimeType contains 'image/'",
            fields="nextPageToken, files(id, name, mimeType, thumbnailLink, webViewLink)",
            pageSize=1000
        ).execute()
        return jsonify({
            "raw_drive_response": results,
            "photo_count": len(photos),
            "cached_photos": get_photos_from_db()
        })
    except Exception as e:
        import traceback, io, sys
        buf = io.StringIO()
        traceback.print_exc(file=buf)
        return jsonify({
            "error": str(e),
            "traceback": buf.getvalue()
        }), 500

@app.route('/api/refresh')
def api_refresh():
    """Force refresh photos from Google Drive (blocking for manual requests)"""
    print("📥 Manual refresh requested...")
    photos = fetch_photos_from_drive()
    if photos and len(photos) > 0:
        save_photos_to_db(photos)
        return jsonify({'success': True, 'count': len(photos), 'message': 'Photos refreshed successfully'})
    else:
        # Return current cache even if refresh failed
        cached = get_photos_from_db()
        return jsonify({'success': False, 'count': len(cached), 'message': 'Failed to fetch from Drive, using cached photos'}), 200

if __name__ == '__main__':
    init_db()
    print(f"Database initialized. Cache will refresh every {CACHE_DURATION_MINUTES} minutes.")
    app.run(debug=True, host='0.0.0.0', port=5000)

