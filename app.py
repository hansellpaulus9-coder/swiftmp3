from flask import Flask, request, jsonify, send_file, render_template
import yt_dlp
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

    ydl_opts = {
        'default_search': 'scsearch5',
        'skip_download': True,
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(query, download=False)
            tracks = []

            if 'entries' in info:
                for entry in info['entries']:
                    if entry:
                        duration_sec = entry.get('duration', 0)
                        if duration_sec:
                            # Safely convert to a whole number integer to prevent the float formatting error
                            total_seconds = int(float(duration_sec))
                            minutes = total_seconds // 60
                            seconds = total_seconds % 60
                            duration_str = f"{minutes}:{seconds:02d}"
                        else:
                            duration_str = "Unknown"

                        tracks.append({
                            'id': entry.get('webpage_url') or entry.get('id'),
                            'title': entry.get('title'),
                            'duration': duration_str
                        })

            return jsonify(tracks)
    except Exception as e:
        return jsonify({'error': f'Search failed: {str(e)}'}), 500

@app.route('/download', methods=['GET'])
def download_track():
    track_id = request.args.get('id')
    title = request.args.get('title', 'audio')

    if not track_id:
        return "Missing track ID", 400

    clean_title = re.sub(r'[\\/*?:"<>|]', '', title)
    output_filename = f"{clean_title}.mp3"

    ydl_opts = {
        'format': 'bestaudio/best',
        'outtmpl': 'downloads/%(title)s.%(ext)s',
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '192',
        }],
    }

    track_url = track_id if track_id.startswith("http") else f"https://soundcloud.com{track_id}"

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(track_url, download=True)
            downloaded_file = ydl.prepare_filename(info)
            base, ext = os.path.splitext(downloaded_file)
            mp3_file = base + '.mp3'

            if os.path.exists(mp3_file):
                return send_file(mp3_file, as_attachment=True, download_name=output_filename)
            else:
                return "File processing error", 500
    except Exception as e:
        return f"Download failed: {str(e)}", 500

if __name__ == '__main__':
    if not os.path.exists('downloads'):
        os.makedirs('downloads')
    app.run(host='0.0.0.0', port=5000, debug=False)

