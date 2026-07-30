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
        'default_search': 'ytsearch5',
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
                        minutes = duration_sec // 60
                        seconds = duration_sec % 60
                        duration_str = f"{minutes}:{seconds:02d}"

                        tracks.append({
                            'id': entry.get('id'),
                            'title': entry.get('title'),
                            'duration': duration_str
                        })

            return jsonify(tracks)
    except Exception as e:
        return jsonify({'error': f'Search failed: {str(e)}'}), 500

@app.route('/download', methods=['GET'])
def download_track():
    video_id = request.args.get('id')
    title = request.args.get('title', 'audio')

    if not video_id:
        return "Missing video ID", 400

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

    video_url = video_id if video_id.startswith("http") else f"https://www.youtube.com/watch?v={video_id}"

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(video_url, download=True)
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
