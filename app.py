from flask import Flask, request, jsonify, render_template, Response
import urllib.parse
import os
import requests
import re
from pathlib import Path
import time

app = Flask(__name__, template_folder='templates')

DOWNLOADS_DIR = '/tmp/downloads' if os.name != 'nt' else 'downloads'

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
    'Accept': '*/*',
    'Referer': 'https://tubidy.cc/'
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


def search_musify(query):
    """
    Search Musify API - has full MP3 downloads
    """
    try:
        safe_query = urllib.parse.quote(query.strip())
        # Musify API endpoint
        url = f"https://api.musify.club/search?q={safe_query}&type=tracks&limit=20"
        
        response = requests.get(url, headers=HEADERS, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        tracks = []
        for track in data.get('data', []):
            track_id = track.get('id', '')
            if not track_id:
                continue
            
            title = track.get('title', '')
            artist = track.get('artist', '')
            if isinstance(artist, dict):
                artist = artist.get('name', 'Unknown')
            
            duration = track.get('duration', 0)
            download_url = track.get('url', '')
            
            if not download_url or not download_url.startswith('http'):
                continue
            
            tracks.append({
                'id': download_url,
                'title': f"{artist} - {title}",
                'duration': format_duration(duration),
                'source': 'Musify',
                'platform': 'musify',
                'quality': '320kbps',
                'full_track': True
            })
        
        return tracks[:15]
    except Exception as e:
        print(f"Musify search error: {e}")
        return []


def search_audiotube(query):
    """
    Search AudioTube API - has MP3 downloads
    """
    try:
        safe_query = urllib.parse.quote(query.strip())
        url = f"https://audiotube.blueemedia.eu/search?q={safe_query}&type=track"
        
        response = requests.get(url, headers=HEADERS, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        tracks = []
        for track in data.get('results', []):
            track_id = track.get('id', '')
            if not track_id:
                continue
            
            title = track.get('name', '')
            artist = track.get('artist', '')
            if isinstance(artist, dict):
                artist = artist.get('name', 'Unknown')
            
            duration = track.get('duration', 0)
            
            tracks.append({
                'id': track_id,
                'title': f"{artist} - {title}",
                'duration': format_duration(duration),
                'source': 'AudioTube',
                'platform': 'audiotube',
                'quality': '192kbps',
                'full_track': True
            })
        
        return tracks[:15]
    except Exception as e:
        print(f"AudioTube search error: {e}")
        return []


def search_deezer_preview(query):
    """
    Fallback: Deezer previews (30 seconds)
    """
    try:
        safe_query = urllib.parse.quote(query.strip())
        url = f"https://api.deezer.com/search?q={safe_query}&limit=10"
        
        response = requests.get(url, headers=HEADERS, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        tracks = []
        for track in data.get('data', []):
            preview = track.get('preview', '')
            if not preview or not preview.startswith('http'):
                continue
            
            artist = track.get('artist', {}).get('name', 'Unknown') if isinstance(track.get('artist'), dict) else 'Unknown'
            title = track.get('title', '')
            duration = track.get('duration', 0)
            
            tracks.append({
                'id': preview,
                'title': f"{artist} - {title}",
                'duration': format_duration(duration),
                'source': 'Deezer Preview (30s)',
                'platform': 'preview',
                'quality': '128kbps',
                'full_track': False
            })
        
        return tracks[:10]
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
        
        # Try Musify first (usually most reliable)
        musify_tracks = search_musify(query)
        all_tracks.extend(musify_tracks)
        
        # Try AudioTube
        if len(all_tracks) < 8:
            audio_tracks = search_audiotube(query)
            all_tracks.extend(audio_tracks)
        
        # Add Deezer previews as fallback
        if len(all_tracks) < 15:
            deezer_tracks = search_deezer_preview(query)
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
        return jsonify({'error': f'Error: {str(e)[:50]}'}), 500


@app.route('/download', methods=['GET'])
def download_track():
    track_id = (request.args.get('id') or '').strip()
    title = request.args.get('title', 'track')
    platform = (request.args.get('platform') or '').strip()
    
    if not track_id:
        return "Missing track", 400
    
    try:
        audio_response = None
        content_type = 'audio/mpeg'
        extension = '.mp3'
        download_url = track_id
        
        # For Musify, download_url is already in track_id
        if platform == 'musify':
            if not track_id.startswith('http'):
                return "Invalid URL", 400
            audio_response = requests.get(
                track_id,
                headers=HEADERS,
                timeout=120,
                stream=True,
                allow_redirects=True
            )
            audio_response.raise_for_status()
        
        # For AudioTube, we need to get download URL
        elif platform == 'audiotube':
            try:
                url = f"https://audiotube.blueemedia.eu/track/{track_id}"
                resp = requests.get(url, headers=HEADERS, timeout=10)
                resp.raise_for_status()
                track_data = resp.json()
                
                download_url = track_data.get('mp3', '')
                if not download_url:
                    # Try to extract from response
                    download_url = track_id  # fallback
                
                audio_response = requests.get(
                    download_url,
                    headers=HEADERS,
                    timeout=120,
                    stream=True,
                    allow_redirects=True
                )
                audio_response.raise_for_status()
            except:
                # If AudioTube fails, treat as preview
                audio_response = requests.get(
                    track_id,
                    headers=HEADERS,
                    timeout=30,
                    stream=True
                )
                audio_response.raise_for_status()
        
        # For preview URLs
        elif platform == 'preview':
            audio_response = requests.get(
                track_id,
                headers=HEADERS,
                timeout=30,
                stream=True,
                allow_redirects=True
            )
            audio_response.raise_for_status()
            content_type = audio_response.headers.get('Content-Type', 'audio/aac')
            if 'm4a' in content_type.lower() or 'aac' in content_type.lower():
                extension = '.m4a'
        
        else:
            # Generic download
            audio_response = requests.get(
                track_id,
                headers=HEADERS,
                timeout=120,
                stream=True,
                allow_redirects=True
            )
            audio_response.raise_for_status()
        
        if not audio_response:
            return "Failed to get track", 503
        
        filename = f"{clean_filename(title)}{extension}"
        
        def generate():
            chunk_count = 0
            try:
                for chunk in audio_response.iter_content(chunk_size=65536):
                    if chunk:
                        chunk_count += 1
                        yield chunk
                        # Safety check: don't stream more than 500MB
                        if chunk_count > 8000:
                            break
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
        return f"Download failed: {str(e)[:80]}", 500


if __name__ == '__main__':
    ensure_downloads_dir()
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False, threaded=True)
