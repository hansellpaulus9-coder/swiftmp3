from flask import Flask, request, jsonify, render_template, Response
import urllib.parse
import os
import requests
import re
import subprocess
import json
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
import time

app = Flask(__name__, template_folder='templates')

SAFE_HOSTS = {
    'audio-ssl.itunes.apple.com',
    'aod.itunes.apple.com',
    'itunes.apple.com',
    'cdnt-preview.dzcdn.net',
    'cdns-files-d.dzcdn.net',
    'cdn-audio.dzcdn.net'
}

DOWNLOADS_DIR = '/tmp/downloads' if os.name != 'nt' else 'downloads'


def ensure_downloads_dir():
    """Ensure downloads directory exists"""
    Path(DOWNLOADS_DIR).mkdir(exist_ok=True, parents=True)


def is_supported_url(audio_url):
    """Check if URL is safe"""
    try:
        parsed = urllib.parse.urlparse(audio_url)
        host = parsed.netloc.lower()
        if parsed.scheme not in ('http', 'https'):
            return False
        if host in SAFE_HOSTS:
            return True
        return '.dzcdn.net' in host or '.apple.com' in host or 'saavn.com' in host
    except:
        return False


def clean_filename(value):
    """Sanitize filename"""
    safe = re.sub(r'[^a-zA-Z0-9 _-]+', '', value or 'track')
    safe = safe.strip().replace(' ', '_')[:50]
    return safe or 'track'


def format_duration(track_time_ms):
    """Convert milliseconds to MM:SS format"""
    if not track_time_ms:
        return '0:00'
    try:
        numeric_value = int(track_time_ms)
        is_seconds = numeric_value < 60000
        total_seconds = max(numeric_value // 1000, 0) if not is_seconds else max(numeric_value, 0)
        minutes, seconds = divmod(total_seconds, 60)
        return f"{minutes}:{seconds:02d}"
    except:
        return '0:00'


def jiosaavn_search(query):
    """Search JioSaavn for full-length songs"""
    try:
        safe_query = urllib.parse.quote(query.strip())
        api_url = f"https://www.jiosaavn.com/api.php?__call=autocomplete.get&_marker=0&q={safe_query}"
        
        response = requests.get(api_url, timeout=10, headers={
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
        response.raise_for_status()
        data = response.json()
        
        tracks = []
        results = data.get('results', [])
        
        for item in results:
            if item.get('type') != 'song':
                continue
            
            title = item.get('title', 'Unknown')
            song_id = item.get('id', '')
            if not song_id:
                continue
            
            artists = item.get('artists', [])
            artist_name = artists[0].get('name', 'Unknown') if artists else 'Unknown'
            duration = item.get('duration', 0)
            
            tracks.append({
                'id': song_id,
                'title': f"{artist_name} - {title}",
                'duration': format_duration(int(duration) * 1000),
                'source': 'JioSaavn (Full)',
                'platform': 'jiosaavn',
                'quality': '320kbps'
            })
        
        return tracks[:5]
    except Exception as e:
        print(f"JioSaavn search error: {e}")
        return []


def itunes_search(query):
    """Search iTunes API for songs"""
    try:
        safe_query = urllib.parse.quote(query.strip())
        api_url = f"https://itunes.apple.com/search?term={safe_query}&media=music&entity=song&limit=10"
        
        response = requests.get(api_url, timeout=10, headers={'User-Agent': 'Mozilla/5.0'})
        response.raise_for_status()
        res_data = response.json()
        
        tracks = []
        for entry in res_data.get('results', []):
            preview_url = (entry.get('previewUrl') or '').strip()
            if not preview_url:
                continue
            
            title = f"{entry.get('artistName', 'Unknown')} - {entry.get('trackName', 'Unknown')}"
            tracks.append({
                'id': preview_url,
                'title': title,
                'duration': format_duration(entry.get('trackTimeMillis')),
                'source': 'iTunes (Preview)',
                'platform': 'itunes',
                'quality': '128kbps'
            })
        return tracks[:5]
    except Exception as e:
        print(f"iTunes search error: {e}")
        return []


def deezer_search(query):
    """Search Deezer API for songs"""
    try:
        safe_query = urllib.parse.quote(query.strip())
        api_url = f"https://api.deezer.com/search/track?q={safe_query}&limit=10"
        
        response = requests.get(api_url, timeout=10, headers={'User-Agent': 'Mozilla/5.0'})
        response.raise_for_status()
        res_data = response.json()
        
        tracks = []
        for entry in res_data.get('data', []):
            preview_url = (entry.get('preview') or '').strip()
            if not preview_url:
                continue
            
            artist_name = (entry.get('artist') or {}).get('name', 'Unknown')
            title = f"{artist_name} - {entry.get('title', 'Unknown')}"
            tracks.append({
                'id': preview_url,
                'title': title,
                'duration': format_duration(entry.get('duration', 0) * 1000),
                'source': 'Deezer (Preview)',
                'platform': 'deezer',
                'quality': '128kbps'
            })
        return tracks[:5]
    except Exception as e:
        print(f"Deezer search error: {e}")
        return []


@app.route('/')
def home():
    """Serve homepage"""
    return render_template('index.html')


@app.route('/search', methods=['POST'])
def search_tracks():
    """Search for tracks across multiple sources"""
    data = request.get_json()
    query = (data or {}).get('query', '').strip()

    if not query:
        return jsonify({'error': 'Enter a song name first'}), 400

    try:
        tracks = []
        seen_ids = set()
        
        # Search all sources in parallel
        with ThreadPoolExecutor(max_workers=3) as executor:
            futures = {
                executor.submit(jiosaavn_search, query): 'jiosaavn',
                executor.submit(itunes_search, query): 'itunes',
                executor.submit(deezer_search, query): 'deezer'
            }
            
            for future in as_completed(futures):
                try:
                    results = future.result(timeout=15)
                    for track in results:
                        track_id = track['id']
                        if track_id not in seen_ids:
                            seen_ids.add(track_id)
                            tracks.append(track)
                except Exception as e:
                    print(f"Search source error: {e}")
                    continue
        
        if not tracks:
            return jsonify({'error': 'No songs found. Try another search.'}), 404
        
        # Sort: full tracks first, then previews
        tracks.sort(key=lambda x: (x.get('platform') != 'jiosaavn', x['title']))
        
        return jsonify({
            'success': True,
            'tracks': tracks[:15]
        })
    except Exception as e:
        print(f"Search error: {e}")
        return jsonify({'error': 'Search failed. Please try again.'}), 500


def download_jiosaavn(song_id, title):
    """Download from JioSaavn"""
    try:
        # Get song details
        api_url = f"https://www.jiosaavn.com/api.php?__call=song.getDetails&pids={song_id}&_marker=0"
        response = requests.get(api_url, timeout=15, headers={
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'
        })
        response.raise_for_status()
        data = response.json()
        
        if song_id not in data:
            return None
        
        song = data[song_id]
        # Get the highest quality URL
        for quality in ['320kbps', '192kbps', '128kbps', '96kbps']:
            url = song.get('more_info', {}).get(f'{quality}_url', '')
            if url:
                # Decrypt URL if needed
                url = url.replace('_96.mp4', '_320.mp4').replace('_96_', '_320_')
                
                audio_response = requests.get(url, timeout=30, headers={
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'
                }, stream=True)
                audio_response.raise_for_status()
                return audio_response
        
        return None
    except Exception as e:
        print(f"JioSaavn download error: {e}")
        return None


def download_preview(url):
    """Download from preview URL (iTunes/Deezer)"""
    try:
        response = requests.get(url, timeout=30, stream=True, headers={
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'
        })
        response.raise_for_status()
        return response
    except Exception as e:
        print(f"Preview download error: {e}")
        return None


@app.route('/download', methods=['GET'])
def download_track():
    """Download track from various platforms"""
    track_id = (request.args.get('id') or '').strip()
    title = request.args.get('title', 'track')
    platform = (request.args.get('platform') or '').strip()
    
    if not track_id:
        return "Missing track ID", 400
    
    try:
        audio_response = None
        content_type = 'audio/mpeg'
        extension = '.mp3'
        
        # Download based on platform
        if platform == 'jiosaavn':
            audio_response = download_jiosaavn(track_id, title)
            content_type = 'audio/mpeg'
            extension = '.mp3'
        
        elif is_supported_url(track_id):
            audio_response = download_preview(track_id)
            # Detect format from response
            content_type = audio_response.headers.get('Content-Type', 'audio/aac') if audio_response else 'audio/aac'
            if 'aac' in content_type or 'm4a' in content_type:
                extension = '.m4a'
            elif 'mp3' in content_type:
                extension = '.mp3'
        
        if not audio_response:
            return "Track unavailable. Try another source.", 503
        
        filename = f"{clean_filename(title)}{extension}"
        
        def generate():
            try:
                for chunk in audio_response.iter_content(chunk_size=16384):
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
                'Pragma': 'no-cache'
            }
        )
    
    except Exception as e:
        print(f"Download error: {e}")
        return f"Download failed: {str(e)[:50]}", 500


@app.errorhandler(404)
def not_found(error):
    return jsonify({'error': 'Not found'}), 404


@app.errorhandler(500)
def server_error(error):
    return jsonify({'error': 'Server error'}), 500


if __name__ == '__main__':
    ensure_downloads_dir()
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)), debug=False)
