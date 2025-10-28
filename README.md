# Memorial Photo Slideshow

A simple Flask-based photo slideshow that displays images from a public Google Drive folder in a beautiful full-screen kiosk mode.

## Features

- 🖼️ Fetches photos from Google Drive folder automatically
- 💾 **SQLite caching** - Photo metadata cached locally for fast loading
- 🖼️ **Local image caching** - Images downloaded and served locally (no rate limiting!)
- 🔄 **Auto-refresh** - Cache updates every 10 minutes automatically to pick up new photos
- ⏱️ **Live countdown timer** - Shows exactly when the next update will happen
- ⏯️ Auto-playing slideshow with smooth fade transitions
- 🔄 **Resume from last photo** - Continues where it left off after page reload
- ⌨️ Keyboard controls:
  - **Spacebar**: Pause/Resume
  - **Arrow Right**: Next photo
  - **Arrow Left**: Previous photo
- 🎨 Beautiful full-screen display with Tailwind CSS
- 📱 Responsive design that works on any screen size

## Setup Instructions

### 1. Get a Google API Key

Since your Google Drive folder is public, you only need a simple API key:

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project (or select existing one)
3. Enable the **Google Drive API**:
   - Go to "APIs & Services" → "Enable APIs and Services"
   - Search for "Google Drive API"
   - Click "Enable"
4. Create an API Key:
   - Go to "APIs & Services" → "Credentials"
   - Click "Create Credentials" → "API Key"
   - Copy your API key

### 2. Install Dependencies

Make sure your virtual environment is activated:

```bash
source .venv/bin/activate
```

Install the required packages:

```bash
pip install -r requirements.txt
```

### 3. Configure Environment Variables

Create a `.env` file in the project root:

```bash
cat > .env << EOF
GOOGLE_DRIVE_FOLDER_ID=1EGGGv1mw0Wd2SLlwU14Em6-W-sob7YjO
GOOGLE_API_KEY=your_api_key_here
EOF
```

Replace `your_api_key_here` with your actual Google API key from step 1.

### 4. Run the Application

```bash
python app.py
```

The app will start on `http://localhost:5000`

### 5. Open in Browser

1. Open your browser and go to `http://localhost:5000`
2. Press **F11** to enter full-screen mode (recommended for kiosk display)
3. The slideshow will start automatically

## Configuration

### Slideshow Settings

Edit `templates/index.html` to customize:

- **Slide Duration**: Change `SLIDE_DURATION` (currently 7000ms = 7 seconds)
- **Transition Speed**: Modify the CSS `transition: opacity 1s` value

### Cache Settings

Edit `app.py` to customize:

- **Cache Duration**: Change `CACHE_DURATION_MINUTES` (currently 10 minutes)
- **Database Location**: Change `DB_PATH` (currently `photos.db`)

### Manual Refresh

To manually refresh photos from Google Drive without waiting for the cache to expire:

Visit: `http://localhost:5000/api/refresh`

Or run:
```bash
curl http://localhost:5000/api/refresh
```

## Troubleshooting

### Photos not loading?

1. Make sure your Google Drive folder is set to "Anyone with the link can view"
2. Verify your API key is correct in `.env`
3. Check that the Google Drive API is enabled in your Google Cloud project
4. Look at the browser console (F12) for error messages

### API Key Issues?

If you get authentication errors, ensure:
- The API key is correctly copied (no extra spaces)
- The Google Drive API is enabled for your project
- The folder ID matches your public folder

## Project Structure

```
memorial/
├── app.py              # Flask backend
├── requirements.txt    # Python dependencies
├── .env               # Configuration (not in git)
├── photos.db          # SQLite cache (auto-created)
├── cached_images/     # Downloaded images (auto-created)
├── templates/
│   └── index.html     # Slideshow frontend
└── README.md          # This file
```

## How Caching Works

### Two-Level Cache System with Async Downloads

1. **First Run**: 
   - Fetches photo list from Google Drive API (instant!)
   - Saves metadata to SQLite database (`photos.db`)
   - **Slideshow starts immediately** with cached images
   - New images download in background while slideshow plays
   
2. **Subsequent Loads**: 
   - Reads photo list from local database (instant!)
   - Serves images from local cache (no Google rate limits!)
   - Any missing images appear as they finish downloading
   
3. **Auto-Refresh**: 
   - Every 10 minutes, checks for new photos
   - Downloads only new images in background
   - Updates database with new metadata
   
4. **Manual Refresh**: 
   - Visit `/api/refresh` to force an immediate update

### Benefits

- ✅ **No rate limiting** - All images served from local disk
- ✅ **Super fast loading** - No network delays after first run
- ✅ **Works offline** - Once cached, no internet needed
- ✅ **New photos auto-appear** - Within 10 minutes max
- ✅ **Reliable kiosk operation** - Can run for days/weeks

## Notes

- This is designed for local/kiosk use and runs in Flask dev mode
- The slideshow loops continuously
- All photos must be in the specified Google Drive folder
- The database file (`photos.db`) is created automatically on first run

