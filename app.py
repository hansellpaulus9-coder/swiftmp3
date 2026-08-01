from flask import Flask, request, jsonify, send_file, render_template
import urllib.request
import urllib.parse
import json
import os
import re

app = Flask(__name__, template_folder='templates')

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/search', methods=['POST'])
def search_tracks():
    data = request.get_json()
    query = data.get('query', '')

    if not query:
        return jsonify({'error': 'Search query is empty'}), 400

    try:
        # Securely parse the artist or song name for the web link
        safe_query = urllib.parse.quote(query.strip())
        
        # Connects to the public, unblocked Audiomack mobile search stream index
        api_url = f"https://audiomack.com{safe_query}&limit=5"

        headers = {
            'User-Agent': 'Mozilla/5.0 (Linux; Android 10; Mobile) AppleWebKit/537.36',
            'Accept': 'application/json'
        }

        req = urllib.request.Request(api_url, headers=headers)
        
        with urllib.request.urlopen(req, timeout=15) as response:
            res_data = json.loads(response.read().decode('utf-8'))
            
            tracks = []
            # Extract the actual music track results from Audiomack's system
            if 'results' in res_data and 'songs' in res_data['results']:
                for entry in res_data['results']['songs']:
                    if entry:
                        # Grab the streaming music file source link
                        stream_url = entry.get('streaming_url') or entry.get('url')
                        if not stream_url:
                            continue

                        tracks.append({
                            'id': stream_url, 
                            'title': f"{entry.get('artist')} - {entry.get('title')}",
                            'duration': entry.get('duration_string', 'Standard')
                        })

            if not tracks:
                return jsonify({'error': 'Could not find this track on the open index. Double-check your spelling!'}), 404

            return jsonify(tracks)
    except Exception as e:
        return jsonify({'error': 'Search pipeline refreshed. Please try running your search again in a moment.'}), 500

@app.route('/download', methods=['GET'])
def download_track():
    audio_url = request.args.get('id')
    title = request.args.get('title', 'audio')

    if not audio_url:
        return "Missing download stream target link", 400

    clean_title = re.sub(r'[\\/*?:"<>|]', '', title)
    output_filename = f"{clean_title}.mp3"

    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
        req = urllib.request.Request(audio_url, headers=headers)
        with urllib.request.urlopen(req, timeout=30) as stream:
            return send_file(
                stream, 
                as_attachment=True, 
                download_name=output_filename, 
                mimetype='audio/mpeg'
            )
    except Exception as e:
        return f"Download server extraction failed: {str(e)}", 500

if __name__ == '__main__':
    if not os.path.exists('downloads'):
        os.makedirs('downloads')
    app.run(host='0.0.0.0', port=5000, debug=False)
