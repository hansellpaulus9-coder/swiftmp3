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
        # Clean up the search string spaces for a smooth URL link
        safe_query = urllib.parse.quote(query.strip())
        
        # Open public music search mirror - 100% unrestricted access for cloud applications
        api_url = f"https://freemusicarchive.org{safe_query}&limit=10"

        req = urllib.request.Request(api_url, headers={'User-Agent': 'Mozilla/5.0'})
        
        with urllib.request.urlopen(req, timeout=15) as response:
            res_data = json.loads(response.read().decode('utf-8'))
            
            tracks = []
            if 'aTracks' in res_data:
                for entry in res_data['aTracks']:
                    if entry:
                        # Capture the high-speed direct MP3 file download line
                        download_url = entry.get('track_file_url')
                        if not download_url:
                            continue

                        tracks.append({
                            'id': download_url, 
                            'title': f"{entry.get('artist_name')} - {entry.get('track_title')}",
                            'duration': entry.get('track_duration', '3:00')
                        })

            if not tracks:
                return jsonify({'error': 'No tracks found matching your query on the open public network.'}), 404

            return jsonify(tracks)
    except Exception as e:
        return jsonify({'error': 'The network path is adjusting. Please refresh and try your search again.'}), 500

@app.route('/download', methods=['GET'])
def download_track():
    audio_url = request.args.get('id')
    title = request.args.get('title', 'audio')

    if not audio_url:
        return "Missing file target link", 400

    clean_title = re.sub(r'[\\/*?:"<>|]', '', title)
    output_filename = f"{clean_title}.mp3"

    try:
        req = urllib.request.Request(audio_url, headers={'User-Agent': 'Mozilla/5.0'})
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
