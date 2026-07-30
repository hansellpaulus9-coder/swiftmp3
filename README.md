SwiftMP3 - Simple Music Downloader

Overview

This is a lightweight Flask app that searches YouTube and allows downloading audio as MP3 using `yt-dlp` and `ffmpeg`.

Files

- `app.py` - Main Flask application (serves `index.html`, `/search`, `/download`).
- `index.html` - Frontend UI in project root.
- `downloads/` - Output folder for generated MP3 files.

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

3. Install FFmpeg and ensure `ffmpeg` is available on your PATH.

Run

```bash
python app.py
```

Open http://127.0.0.1:5000/ in your browser.

Notes

- `yt-dlp` downloads YouTube content; ensure you comply with YouTube's Terms of Service.
- If downloads fail during audio extraction, verify FFmpeg is installed.
