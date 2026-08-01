from flask import Flask, request, jsonify, send_file, render_template
import urllib.request
import urllib.parse
import json
import os
import re

app = Flask(__name__, template_folder='templates')

# Official developer client ID for stable, unblocked requests
JAMENDO_CLIENT_ID = '56d30c95'

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
        # Properly encode spaces and characters to make the url completely safe
        safe_query = urllib.parse.quote(query.strip())
        
        # Fixed the URL structure completely to avoid control character errors
        api_url = f"https://jamendo.com{JAMENDO_CLIENT_ID}&format=json&limit=10&search={safe_query}"

        req = urllib.request.Request(api_url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req) as response:
            res_data = json.loads(response.read().decode('utf-8'))
            
            tracks = []
            if 'results' in res_data:
                for entry in res_data['results']:
                    if entry:
                        duration_sec = entry.get('duration', 0)
                        minutes = duration_sec // 60
                        seconds = duration_sec % 60
                        duration_str = f"{minutes}:{seconds:02d}"

                        tracks.append({
                            'id': entry.get('audio'), 
                            'title': f"{entry.get('artist_name')} - {entry.get('name')}",
                            'duration': duration_str
                        })

            if not tracks:
                return jsonify({'error': 'No tracks found for this search. Try general terms like hiphop, piano, or chill.'}), 404

            return jsonify(tracks)
    except Exception as e:
        return jsonify({'error': f'Search pipeline failed: {str(e)}'}), 500

@app.route('/download', methods=['GET'])
def download_track():
    audio_url = request.args.get('id')
    title = request.args.get('title', 'audio')

    if not audio_url:
        return "Missing download endpoint link", 400

    clean_title = re.sub(r'[\\/*?:"<>|]', '', title)
    output_filename = f"{clean_title}.mp3"

    try:
        req = urllib.request.Request(audio_url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req) as stream:
            return send_file(
                stream, 
                as_attachment=True, 
                download_name=output_filename, 
                mimetype='audio/mpeg'
            )
    except Exception as e:
        return f"Download extraction engine failed: {str(e)}", 500

if __name__ == '__main__':
    if not os.path.exists('downloads'):
        os.makedirs('downloads')
    app.run(host='0.0.0.0', port=5000, debug=False)
