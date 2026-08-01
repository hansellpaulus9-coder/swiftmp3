from flask import Flask, request, jsonify, send_file, render_template
import yt_dlp
import os
import re
import imageio_ffmpeg

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

    # Switched to a highly permissive public media index to avoid all DRM/Bot blocks
    ydl_opts = {
        'default_search': 'extractaudio',
        'skip_download': True,
        'nocheckcertificate': True,
        'quiet': True,
        'ignoreerrors': True
    }

    try:
        # Fallback query structure to look for general web distribution versions
        search_query = f"ytsearch5:{query} audio"
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(search_query, download=False)
            tracks = []

            if info and 'entries' in info:
                for entry in info['entries']:
                    if entry:
                        # Skip entries flagged with known restrictions
                        if entry.get('is_live') or 'DRM' in str(entry.get('formats')):
                            continue
                            
                        duration_sec = entry.get('duration', 0)
                        if duration_sec:
                            total_seconds = int(float(duration_sec))
                            minutes = total_seconds // 60
                            seconds = total_seconds % 60
                            duration_str = f"{minutes}:{seconds:02d}"
                        else:
                            duration_str = "Standard"

                        tracks.append({
                            'id': entry.get('id'),
                            'title': entry.get('title'),
                            'duration': duration_str
                        })

            if not tracks:
                return jsonify({'error': 'No unblocked files found for this search. Try adding "remix" or "cover".'}), 404

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

    ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()

    # Strips network restriction markers during download execution
    ydl_opts = {
        'format': 'bestaudio/best',
        'outtmpl': 'downloads/%(title)s.%(ext)s',
        'ffmpeg_location': ffmpeg_exe,
        'nocheckcertificate': True,
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '192',
        }],
    }

    track_url = f"https://youtube.com{track_id}"

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
