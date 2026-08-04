from flask import Flask, request, jsonify, render_template, Response
import urllib.parse
import os
import requests
import re
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
import base64
import json

app = Flask(__name__, template_folder='templates')

DOWNLOADS_DIR = '/tmp/downloads' if os.name != 'nt' else 'downloads'

# Headers to bypass API blocks
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': '*/*',
    'Accept-Language': 'en-US,en;q=0.9',
    'Referer': 'https://www.jiosaavn.com/',
    'Origin': 'https://www.jiosaavn.com'
}


def ensure_downloads_dir():
    Path(DOWNLOADS_DIR).mkdir(exist_ok=True, parents=True)


def clean_filename(value):
    safe = re.sub(r'[^a-zA-Z0-9 _-]+', '', value or 'track')
    safe = safe.strip().replace(' ', '_')[:50]
    return safe or 'track'


def format_duration(seconds):
    if not seconds:
        return '0:00'
    try:
        s = int(seconds)
        minutes, secs = divmod(s, 60)
        return f"{minutes}:{secs:02d}"
    except:
        return '0:00'


def get_jiosaavn_song_url(song_id):
    """
    Get actual downloadable MP3 URL from JioSaavn using their API
    """
    try:
        # Get song details from JioSaavn API
        url = f"https://www.jiosaavn.com/api.php?__call=song.getDetails&pids={song_id}"
        
        response = requests.get(url, headers=HEADERS, timeout=15)
        response.raise_for_status()
        data = response.json()
        
        if song_id not in data:
            return None
        
        song = data[song_id]
        
        # Try to get download URL from media URLs
        media_url = song.get('media_url', '')
        if media_url and media_url.startswith('http'):
            # Media URL might be encrypted, try direct approach
            download_url = media_url
            if download_url:
                return download_url
        
        # Try alternative: get from more_info
        more_info = song.get('more_info', {})
        for quality in ['320', '192', '128', '96']:
            url_key = f'vcode{quality}url' if quality != '320' else 'vcode320url'
            if url_key in more_info:
                url_val = more_info[url_key]
                if url_val and url_val.startswith('http'):
                    return url_val
        
        # Last resort: construct URL from song info
        if song.get('id') and song.get('music_id'):
            # JioSaavn MP3 URL format
            base_url = f"https://aac.saavncdn.com/"
            song_path = song.get('encrypted_media_url', '')
            if song_path:
                return base_url + song_path
        
        return None
        
    except Exception as e:
        print(f"Error getting JioSaavn URL: {e}")
        return None


def search_jiosaavn(query):
    """
    Search JioSaavn for full-length songs
    """
    try:
        safe_query = urllib.parse.quote(query.strip())
        url = f"https://www.jiosaavn.com/api.php?__call=autocomplete.get&_marker=0&q={safe_query}"
        
        response = requests.get(url, headers=HEADERS, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        tracks = []
        for result in data.get('results', []):
            if result.get('type') != 'song':
                continue
            
            song_id = result.get('id', '')
            if not song_id:
                continue
            
            title = result.get('title', '')
            artist = result.get('artists', [{}])[0].get('name', 'Unknown') if result.get('artists') else 'Unknown'
            duration = result.get('duration', 0)
            
            tracks.append({
                'id': song_id,
                'title': f"{artist} - {title}",
                'duration': format_duration(duration),
                'source': 'JioSaavn',
                'platform': 'jiosaavn',
                'quality': '320kbps',
                'full_track': True
            })
        
        return tracks[:10]
    except Exception as e:
        print(f"JioSaavn search error: {e}")
        return []


def search_spotify_preview(query):
    """
    Search for preview tracks as fallback
    """
    try:
        # Using Deezer API as fallback for previews
        safe_query = urllib.parse.quote(query.strip())
        url = f"https://api.deezer.com/search?q={safe_query}&limit=5"
        
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        tracks = []
        for track in data.get('data', []):
            preview = track.get('preview', '')
            if not preview:
                continue
            
            artist = track.get('artist', {}).get('name', 'Unknown')
            title = track.get('title', '')
            duration = track.get('duration', 0)
            
            tracks.append({
                'id': preview,
                'title': f"{artist} - {title}",
                'duration': format_duration(duration),
                'source': 'Deezer Preview',
                'platform': 'preview',
                'quality': '128kbps',
                'full_track': False
            })
        
        return tracks[:5]
    except Exception as e:
        print(f"Preview search error: {e}")
        return []


@app.route('/')
def home():
    return render_template('index.html')


@app.route('/search', methods=['POST'])
def search_tracks():
    data = request.get_json()
    query = (data or {}).get('query', '').strip()
    
    if not query:
        return jsonify({'error': 'Enter a song name first'}), 400
    
    try:
        tracks = []
        
        # Search JioSaavn first (full tracks)
        jio_tracks = search_jiosaavn(query)
        tracks.extend(jio_tracks)
        
        # Add previews as fallback
        if len(tracks) < 5:
            preview_tracks = search_spotify_preview(query)
            tracks.extend(preview_tracks)
        
        if not tracks:
            return jsonify({'error': 'No songs found. Try another search.'}), 404
        
        # Sort: full tracks first
        tracks.sort(key=lambda x: (not x.get('full_track'), x['title']))
        
        return jsonify({
            'success': True,
            'tracks': tracks[:15]
        })
    except Exception as e:
        print(f"Search error: {e}")
        return jsonify({'error': 'Search failed. Please try again.'}), 500


@app.route('/download', methods=['GET'])
def download_track():
    track_id = (request.args.get('id') or '').strip()
    title = request.args.get('title', 'track')
    platform = (request.args.get('platform') or '').strip()
    
    if not track_id:
        return "Missing track ID", 400
    
    try:
        audio_response = None
        content_type = 'audio/mpeg'
        extension = '.mp3'
        
        if platform == 'jiosaavn':
            # Get actual download URL from JioSaavn
            download_url = get_jiosaavn_song_url(track_id)
            
            if not download_url:
                return "Could not get download URL. Try another song.", 503
            
            # Download the MP3
            audio_response = requests.get(
                download_url,
                headers=HEADERS,
                timeout=60,
                stream=True,
                allow_redirects=True
            )
            audio_response.raise_for_status()
            
        elif platform == 'preview':
            # Download preview (30 seconds)
            audio_response = requests.get(
                track_id,
                headers=HEADERS,
                timeout=30,
                stream=True
            )
            audio_response.raise_for_status()
            content_type = audio_response.headers.get('Content-Type', 'audio/aac')
            if 'm4a' in content_type or 'aac' in content_type:
                extension = '.m4a'
        
        if not audio_response:
            return "Track unavailable", 503
        
        filename = f"{clean_filename(title)}{extension}"
        
        def generate():
            try:
                for chunk in audio_response.iter_content(chunk_size=32768):
                    if chunk:
                        yield chunk
            except Exception as e:
                print(f"Stream error: {e}")
        
        return Response(
            generate(),
            content_type=content_type,
            headers={
                'Content-Disposition': f'attachment; filename="{filename}"',
                'Cache-Control': 'no-store, no-cache',
                'Pragma': 'no-cache',
                'Content-Type': content_type
            }
        )
    
    except Exception as e:
        print(f"Download error: {e}")
        return f"Download failed: {str(e)[:60]}", 500


if __name__ == '__main__':
    ensure_downloads_dir()
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
