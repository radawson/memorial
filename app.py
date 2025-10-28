import os
import sqlite3
from datetime import datetime, timedelta
from flask import Flask, render_template, jsonify
from googleapiclient.discovery import build
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)

# Configuration
GOOGLE_DRIVE_FOLDER_ID = os.getenv('GOOGLE_DRIVE_FOLDER_ID', '1EGGGv1mw0Wd2SLlwU14Em6-W-sob7YjO')
GOOGLE_API_KEY = os.getenv('GOOGLE_API_KEY')
DB_PATH = 'photos.db'
CACHE_DURATION_HOURS = 24  # Refresh from Drive API after this many hours

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
    """Check if cache is older than CACHE_DURATION_HOURS"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('SELECT last_updated FROM cache_info WHERE key = ?', ('photos',))
    result = c.fetchone()
    conn.close()
    
    if not result:
        return True
    
    last_updated = datetime.fromisoformat(result[0])
    return datetime.now() - last_updated > timedelta(hours=CACHE_DURATION_HOURS)

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

def fetch_photos_from_drive():
    """Fetch all image files from the public Google Drive folder"""
    try:
        # Build the Drive API client with API key (for public folders)
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
        
        # Convert to direct image URLs
        photo_urls = []
        for file in files:
            # Use Google Drive's thumbnail API with large size for better compatibility
            # This works better than uc?export=view for embedded images
            photo_url = f"https://drive.google.com/thumbnail?id={file['id']}&sz=w2000"
            photo_urls.append({
                'id': file['id'],
                'name': file['name'],
                'url': photo_url
            })
        
        return photo_urls
    except Exception as e:
        print(f"Error fetching photos: {e}")
        return []

@app.route('/')
def index():
    """Render the slideshow page"""
    return render_template('index.html')

def get_photos():
    """Get photos from cache or refresh from Drive if needed"""
    # Check if we need to refresh the cache
    if should_refresh_cache():
        print("Cache expired or empty, fetching from Google Drive...")
        photos = fetch_photos_from_drive()
        if photos:
            save_photos_to_db(photos)
            print(f"Cached {len(photos)} photos to database")
        else:
            print("Failed to fetch from Drive, using cached data")
            photos = get_photos_from_db()
    else:
        print("Using cached photos from database")
        photos = get_photos_from_db()
    
    return photos

@app.route('/api/photos')
def api_photos():
    """API endpoint to get list of photos"""
    photos = get_photos()
    return jsonify({'photos': photos, 'count': len(photos)})

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
    print(f"Database initialized. Cache will refresh every {CACHE_DURATION_HOURS} hours.")
    app.run(debug=True, host='0.0.0.0', port=5000)

