from flask import Flask, request, jsonify, render_template, Response
import urllib.parse
import os
import requests
import re

app = Flask(__name__, template_folder='templates')

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
}


def clean_filename(value):
    safe = re.sub(r'[^a-zA-Z0-9 _-]+', '', value or 'track')
    return safe.strip().replace(' ', '_')[:60] or 'track'


def format_duration(sec):
    try:
        s = int(sec) if sec else 0
        m, s = divmod(s, 60)
        return f"{m}:{s:02d}"
    except:
        return "0:00"


def search_deezer(query):
    """Search Deezer - Best free API for music"""
    try:
        url = f"https://api.deezer.com/search?q={urllib.parse.quote(query)}&limit=20"
        resp = requests.get(url, headers=HEADERS, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        
        tracks = []
        for item in data.get('data', []):
            track_id = item.get('id')
            if not track_id:
                continue
            
            artist = item.get('artist', {})
            artist_name = artist.get('name', 'Unknown') if isinstance(artist, dict) else 'Unknown'
            title = item.get('title', '')
            duration = item.get('duration', 0)
            
            tracks.append({
                'id': str(track_id),
                'title': f"{artist_name} - {title}",
                'duration': format_duration(duration),
                'source': 'Deezer (Full)',
                'platform': 'deezer',
                'quality': '320kbps'
            })
        
        return tracks[:15]
    except Exception as e:
        print(f"Deezer error: {e}")
        return []


def search_spotify(query):
    """Search Spotify preview (fallback)"""
    try:
        url = f"https://api.spotify.com/v1/search?q={urllib.parse.quote(query)}&type=track&limit=20"
        resp = requests.get(url, headers=HEADERS, timeout=10)
        
        if resp.status_code != 200:
            return []
        
        data = resp.json()
        tracks = []
        
        for item in data.get('tracks', {}).get('items', []):
            if not item.get('preview_url'):
                continue
            
            artists = item.get('artists', [])
            artist_name = artists[0].get('name', 'Unknown') if artists else 'Unknown'
            title = item.get('name', '')
            duration = item.get('duration_ms', 0)
            
            tracks.append({
                'id': item['preview_url'],
                'title': f"{artist_name} - {title}",
                'duration': format_duration(duration // 1000),
                'source': 'Spotify (Preview)',
                'platform': 'spotify',
                'quality': '128kbps'
            })
        
        return tracks[:10]
    except:
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
        # Search Deezer first
        tracks = search_deezer(query)
        
        # Add Spotify if needed
        if len(tracks) < 10:
            tracks.extend(search_spotify(query))
        
        if not tracks:
            return jsonify({'error': 'No songs found'}), 404
        
        return jsonify({'success': True, 'tracks': tracks[:20]})
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
        # Download from Deezer
        if platform == 'deezer':
            api_url = f"https://api.deezer.com/track/{track_id}"
            resp = requests.get(api_url, headers=HEADERS, timeout=10)
            resp.raise_for_status()
            track_data = resp.json()
            
            # Get preview or full stream
            preview_url = track_data.get('preview')
            if not preview_url:
                return "No preview", 404
            
            audio = requests.get(preview_url, headers=HEADERS, timeout=30, stream=True)
            audio.raise_for_status()
            
            ext = '.m4a'
            ctype = 'audio/aac'
        
        # Download from Spotify
        elif platform == 'spotify':
            audio = requests.get(track_id, headers=HEADERS, timeout=30, stream=True)
            audio.raise_for_status()
            
            ext = '.mp3'
            ctype = 'audio/mpeg'
        
        else:
            return "Unknown platform", 400
        
        filename = f"{clean_filename(title)}{ext}"
        
        def generate():
            for chunk in audio.iter_content(chunk_size=65536):
                if chunk:
                    yield chunk
        
        return Response(
            generate(),
            content_type=ctype,
            headers={'Content-Disposition': f'attachment; filename="{filename}"'}
        )
    
    except Exception as e:
        print(f"Error: {e}")
        return f"Download failed: {str(e)[:60]}", 500


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
