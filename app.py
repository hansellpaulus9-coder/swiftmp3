from flask import Flask, request, jsonify, render_template, redirect, Response
import urllib.parse
import os
import requests
import re

app = Flask(__name__, template_folder='templates')
SAFE_PREVIEW_HOSTS = {
    'audio-ssl.itunes.apple.com',
    'aod.itunes.apple.com',
    'itunes.apple.com',
    'cdnt-preview.dzcdn.net'
}


def is_supported_preview_url(audio_url):
    parsed = urllib.parse.urlparse(audio_url)
    host = parsed.netloc.lower()
    if parsed.scheme not in ('http', 'https'):
        return False
    if host in SAFE_PREVIEW_HOSTS:
        return True
    return host.endswith('.dzcdn.net') or host.endswith('.apple.com')


def clean_filename(value):
    safe = re.sub(r'[^a-zA-Z0-9 _-]+', '', value or 'preview')
    safe = safe.strip().replace(' ', '_')
    return safe or 'preview'


def format_duration(track_time_ms):
    if not track_time_ms:
        return '3:00'

    numeric_value = int(track_time_ms)
    is_seconds = numeric_value < 60000
    total_seconds = max(numeric_value // 1000, 0) if not is_seconds else max(numeric_value, 0)
    minutes, seconds = divmod(total_seconds, 60)
    return f"{minutes}:{seconds:02d}"


def itunes_search(query):
    safe_query = urllib.parse.quote(query.strip())
    api_url = f"https://itunes.apple.com/search?term={safe_query}&media=music&entity=song&limit=10"

    response = requests.get(api_url, timeout=15, headers={'User-Agent': 'Mozilla/5.0'})
    response.raise_for_status()
    res_data = response.json()

    tracks = []
    for entry in res_data.get('results', []):
        preview_url = (entry.get('previewUrl') or '').strip()
        if not preview_url or not is_supported_preview_url(preview_url):
            continue

        title = f"{entry.get('artistName', 'Unknown Artist')} - {entry.get('trackName', 'Unknown Track')}"
        tracks.append({
            'id': preview_url,
            'title': title,
            'duration': format_duration(entry.get('trackTimeMillis'))
        })
    return tracks


def deezer_search(query):
    safe_query = urllib.parse.quote(query.strip())
    api_url = f"https://api.deezer.com/search/track?q={safe_query}"

    response = requests.get(api_url, timeout=15, headers={'User-Agent': 'Mozilla/5.0'})
    response.raise_for_status()
    res_data = response.json()

    tracks = []
    for entry in res_data.get('data', []):
        preview_url = (entry.get('preview') or '').strip()
        if not preview_url or not is_supported_preview_url(preview_url):
            continue

        artist_name = (entry.get('artist') or {}).get('name', 'Unknown Artist')
        title = f"{artist_name} - {entry.get('title', 'Unknown Track')}"
        tracks.append({
            'id': preview_url,
            'title': title,
            'duration': format_duration(entry.get('duration') * 1000)
        })
    return tracks


@app.route('/')
def home():
    return render_template('index.html')


@app.route('/search', methods=['POST'])
def search_tracks():
    data = request.get_json()
    query = (data or {}).get('query', '')

    if not query:
        return jsonify({'error': 'Search query is empty'}), 400

    normalized_query = query.strip()
    if not normalized_query:
        return jsonify({'error': 'Search query is empty'}), 400

    try:
        tracks = []
        seen_ids = set()

        for provider in (itunes_search, deezer_search):
            for track in provider(normalized_query):
                track_id = track['id']
                if track_id in seen_ids:
                    continue
                seen_ids.add(track_id)
                tracks.append(track)

                if len(tracks) >= 10:
                    break
            if len(tracks) >= 10:
                break

        if not tracks:
            return jsonify({'error': 'No public preview tracks were available for that query.'}), 404

        return jsonify({
            'preview_only': True,
            'tracks': tracks
        })
    except Exception:
        return jsonify({'error': 'The public music catalog is temporarily unavailable. Please refresh and try again.'}), 500


@app.route('/download', methods=['GET'])
def download_track():
    audio_url = (request.args.get('id') or '').strip()
    title = request.args.get('title', 'preview')

    if not audio_url:
        return "Missing file target link", 400

    if not is_supported_preview_url(audio_url):
        return "This media link is not a supported public preview URL.", 400

    try:
        remote = requests.get(audio_url, timeout=30, stream=True, headers={'User-Agent': 'Mozilla/5.0'})
        remote.raise_for_status()

        content_type = remote.headers.get('Content-Type', 'audio/aac')
        filename = f"{clean_filename(title)}_preview.m4a"

        return Response(
            remote.iter_content(chunk_size=8192),
            content_type=content_type,
            headers={
                'Content-Disposition': f'attachment; filename="{filename}"',
                'Cache-Control': 'no-store'
            }
        )
    except Exception:
        return "Download request failed.", 500


if __name__ == '__main__':
    if not os.path.exists('downloads'):
        os.makedirs('downloads')
    app.run(host='0.0.0.0', port=5000, debug=False)
