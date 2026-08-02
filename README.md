SwiftMP3 - Simple Music Downloader

Overview

This is a lightweight Flask app that searches a public music catalog and links the audio preview download directly from the browser.

Files

- `app.py` - Main Flask application (serves the UI and the `/search` and `/download` routes).
- `templates/index.html` - Frontend UI.
- `downloads/` - Optional local output folder for any downloaded files.

Setup

1. Create a virtual environment (recommended):

```bash
python -m venv venv
source venv/Scripts/activate   # Windows
# or
source venv/bin/activate       # macOS / Linux
```

2. Install dependencies:

```bash
pip install -r requirements.txt
```

Run

```bash
python app.py
```

Open http://127.0.0.1:5000/ in your browser.

Notes

- The app now uses the public iTunes search API, which avoids the old YouTube download workflow.
- Render should work as a simple Gunicorn Flask deployment without any FFmpeg requirement.
