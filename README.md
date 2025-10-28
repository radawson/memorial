# Memorial Photo Slideshow

A simple Flask-based photo slideshow that displays images from a public Google Drive folder in a beautiful full-screen kiosk mode.

## Features

- 🖼️ Fetches photos from Google Drive folder automatically
- 💾 **SQLite caching** - Photos are cached locally for fast loading and minimal API calls
- 🔄 **Auto-refresh** - Cache updates every 24 hours automatically
- ⏯️ Auto-playing slideshow with smooth fade transitions
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

- **Cache Duration**: Change `CACHE_DURATION_HOURS` (currently 24 hours)
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
├── templates/
│   └── index.html     # Slideshow frontend
└── README.md          # This file
```

## How Caching Works

1. **First Run**: Fetches all photos from Google Drive and saves to SQLite database (`photos.db`)
2. **Subsequent Loads**: Reads photos from the local database (instant loading!)
3. **Auto-Refresh**: Every 24 hours, automatically fetches fresh data from Google Drive
4. **Manual Refresh**: Visit `/api/refresh` to force an immediate update

This means:
- ✅ Fast page loads after first run
- ✅ Minimal Google Drive API usage
- ✅ Kiosk can run for extended periods without issues
- ✅ Add new photos to Drive, visit `/api/refresh`, and they appear!

## Notes

- This is designed for local/kiosk use and runs in Flask dev mode
- The slideshow loops continuously
- All photos must be in the specified Google Drive folder
- The database file (`photos.db`) is created automatically on first run

