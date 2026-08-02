from flask import Flask, request, jsonify, render_template, redirect
import urllib.parse
import os
import requests

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

    if not audio_url:
        return "Missing file target link", 400

    if not is_supported_preview_url(audio_url):
        return "This media link is not a supported public preview URL.", 400

    try:
        return redirect(audio_url, code=307)
    except Exception:
        return "Download request failed.", 500


if __name__ == '__main__':
    if not os.path.exists('downloads'):
        os.makedirs('downloads')
    app.run(host='0.0.0.0', port=5000, debug=False)
