from flask import Flask, request, jsonify, render_template, Response
import urllib.parse
import os
import requests
import re
from pathlib import Path
import subprocess
import json

app = Flask(__name__, template_folder='templates')

DOWNLOADS_DIR = '/tmp/downloads' if os.name != 'nt' else 'downloads'

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
}


def ensure_downloads_dir():
    Path(DOWNLOADS_DIR).mkdir(exist_ok=True, parents=True)


def clean_filename(value):
    safe = re.sub(r'[^a-zA-Z0-9 _-]+', '', value or 'track')
    safe = safe.strip().replace(' ', '_')[:60]
    return safe or 'track'


def format_duration(seconds):
    if not seconds:
        return '0:00'
    try:
        s = int(seconds) if isinstance(seconds, (int, str)) else 0
        minutes, secs = divmod(s, 60)
        return f"{minutes}:{secs:02d}"
    except:
        return '0:00'


def search_invidious(query):
    """
    Search Invidious (YouTube alternative) for full music tracks
    """
    try:
        safe_query = urllib.parse.quote(query.strip())
        # Public Invidious instance
        url = f"https://inv.nadeko.net/api/v1/search?q={safe_query}&type=video"
        
        response = requests.get(url, headers=HEADERS, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        tracks = []
        for result in data.get('videos', []):
            video_id = result.get('videoId', '')
            if not video_id:
                continue
            
            title = result.get('title', '')
            duration = result.get('duration', 0)
            
            # Filter for song-length videos (1min to 10min)
            if duration < 60 or duration > 600:
                continue
            
            tracks.append({
                'id': video_id,
                'title': title,
                'duration': format_duration(duration),
                'source': 'YouTube',
                'platform': 'youtube',
                'quality': '192kbps',
                'full_track': True
            })
        
        return tracks[:15]
    except Exception as e:
        print(f"Invidious search error: {e}")
        return []


def search_deezer_basic(query):
    """
    Search Deezer for track metadata
    """
    try:
        safe_query = urllib.parse.quote(query.strip())
        url = f"https://api.deezer.com/search?q={safe_query}&limit=15"
        
        response = requests.get(url, headers=HEADERS, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        tracks = []
        for track in data.get('data', []):
            track_id = track.get('id', '')
            if not track_id:
                continue
            
            artist = track.get('artist', {}).get('name', 'Unknown') if isinstance(track.get('artist'), dict) else 'Unknown'
            title = track.get('title', '')
            duration = track.get('duration', 0)
            
            tracks.append({
                'id': str(track_id),
                'title': f"{artist} - {title}",
                'duration': format_duration(duration),
                'source': 'Deezer',
                'platform': 'deezer',
                'quality': '128kbps',
                'full_track': False  # Deezer is fallback only
            })
        
        return tracks[:15]
    except Exception as e:
        print(f"Deezer search error: {e}")
        return []


@app.route('/')
def home():
    return render_template('index.html')


@app.route('/search', methods=['POST'])
def search_tracks():
    data = request.get_json()
    query = (data or {}).get('query', '').strip()
    
    if not query:
        return jsonify({'error': 'Enter song name'}), 400
    
    try:
        all_tracks = []
        
        # Search YouTube via Invidious (full songs)
        yt_tracks = search_invidious(query)
        all_tracks.extend(yt_tracks)
        
        # Add Deezer as fallback
        if len(all_tracks) < 10:
            deezer_tracks = search_deezer_basic(query)
            all_tracks.extend(deezer_tracks)
        
        # Remove duplicates
        seen = set()
        unique_tracks = []
        for track in all_tracks:
            key = track['title'].lower()
            if key not in seen:
                seen.add(key)
                unique_tracks.append(track)
        
        # Sort: full tracks first
        unique_tracks.sort(key=lambda x: (not x.get('full_track'), x['title']))
        
        if not unique_tracks:
            return jsonify({'error': 'No songs found'}), 404
        
        return jsonify({
            'success': True,
            'tracks': unique_tracks[:20]
        })
    except Exception as e:
        print(f"Search error: {e}")
        return jsonify({'error': 'Search failed'}), 500


@app.route('/download', methods=['GET'])
def download_track():
    track_id = (request.args.get('id') or '').strip()
    title = request.args.get('title', 'track')
    platform = (request.args.get('platform') or '').strip()
    
    if not track_id:
        return "Missing track", 400
    
    try:
        if platform == 'youtube':
            # Download from YouTube using yt-dlp
            ensure_downloads_dir()
            
            # Create temp filename
            temp_file = os.path.join(DOWNLOADS_DIR, '%(title)s.%(ext)s')
            
            # Command to download audio
            cmd = [
                'yt-dlp',
                '--quiet',
                '--no-warnings',
                '-f', 'bestaudio',
                '-x',
                '--audio-format', 'mp3',
                '--audio-quality', '192K',
                '-o', temp_file,
                f'https://www.youtube.com/watch?v={track_id}'
            ]
            
            print(f"Running: {' '.join(cmd)}")
            result = subprocess.run(cmd, capture_output=True, timeout=300, text=True)
            
            if result.returncode != 0:
                print(f"yt-dlp error: {result.stderr}")
                return f"Download failed: {result.stderr[:100]}", 500
            
            # Find downloaded file
            downloaded_file = None
            for file in os.listdir(DOWNLOADS_DIR):
                if file.endswith('.mp3'):
                    downloaded_file = os.path.join(DOWNLOADS_DIR, file)
                    break
            
            if not downloaded_file or not os.path.exists(downloaded_file):
                return "File not found after download", 500
            
            # Stream the file
            def generate():
                try:
                    with open(downloaded_file, 'rb') as f:
                        while True:
                            chunk = f.read(65536)
                            if not chunk:
                                break
                            yield chunk
                finally:
                    try:
                        os.remove(downloaded_file)
                    except:
                        pass
            
            filename = f"{clean_filename(title)}.mp3"
            return Response(
                generate(),
                content_type='audio/mpeg',
                headers={
                    'Content-Disposition': f'attachment; filename="{filename}"',
                    'Cache-Control': 'no-store, no-cache'
                }
            )
        
        elif platform == 'deezer':
            # Get preview from Deezer
            api_url = f"https://api.deezer.com/track/{track_id}"
            resp = requests.get(api_url, headers=HEADERS, timeout=10)
            resp.raise_for_status()
            track_data = resp.json()
            
            preview_url = track_data.get('preview', '')
            if not preview_url:
                return "No preview available", 404
            
            audio_response = requests.get(
                preview_url,
                headers=HEADERS,
                timeout=30,
                stream=True
            )
            audio_response.raise_for_status()
            
            filename = f"{clean_filename(title)}.m4a"
            
            def generate():
                try:
                    for chunk in audio_response.iter_content(chunk_size=65536):
                        if chunk:
                            yield chunk
                except:
                    pass
            
            return Response(
                generate(),
                content_type='audio/mp4',
                headers={
                    'Content-Disposition': f'attachment; filename="{filename}"',
                    'Cache-Control': 'no-store, no-cache'
                }
            )
        
        else:
            return "Unknown platform", 400
    
    except subprocess.TimeoutExpired:
        return "Download timed out - video too large", 504
    except FileNotFoundError:
        return "yt-dlp not available. Please try Deezer option.", 503
    except Exception as e:
        print(f"Download error: {e}")
        return f"Error: {str(e)[:80]}", 500


if __name__ == '__main__':
    ensure_downloads_dir()
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False, threaded=True)
