import subprocess
import sounddevice as sd
import numpy as np
import threading
import http.server
import socketserver
import urllib.parse
import os

from led_controller import LEDController

YOUTUBE_URL = ""
SAMPLE_RATE = 48000
LIB_DIR = os.path.expanduser("/home/sm/Music")
HTML_FILE = "templates/audio_player.html"

LED_PINS = [14, 15, 18, 23, 24, 25, 7, 8, 1, 12]

volume = 1.0
paused = False
yt_proc = None
ffmpeg_proc = None

sd.default.device = "hw:2,0"
sd.default.blocksize = 1024

PORT = 8080

led_controller = LEDController(LED_PINS, smoothing=0.5, gain=1.5)


def load_html_template():
    try:
        with open(HTML_FILE, 'r', encoding='utf-8') as f:
            return f.read()
    except FileNotFoundError:
        return "<html><body><h1>Error</h1><p>HTML template file not found!</p></body></html>"


def start_stream(url):
    global yt_proc, ffmpeg_proc, YOUTUBE_URL
    stop_stream()
    YOUTUBE_URL = url

    yt_dlp_cmd = [
        "yt-dlp", "--no-playlist", "-f", "bestaudio", "-o", "-", YOUTUBE_URL
    ]

    ffmpeg_cmd = [
        "ffmpeg",
        "-i", "pipe:0",
        "-vn",
        "-acodec", "pcm_s16le",
        "-ar", str(SAMPLE_RATE),
        "-ac", "2",
        "-f", "s16le",
        "pipe:1"
    ]

    print("Launching yt-dlp and ffmpeg...")
    yt_proc = subprocess.Popen(yt_dlp_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    ffmpeg_proc = subprocess.Popen(ffmpeg_cmd, stdin=yt_proc.stdout, stdout=subprocess.PIPE, stderr=subprocess.PIPE)


def stop_stream():
    global yt_proc, ffmpeg_proc
    if yt_proc:
        yt_proc.kill()
        yt_proc = None
    if ffmpeg_proc:
        ffmpeg_proc.kill()
        ffmpeg_proc = None
    print("Stream stopped")


def audio_callback(outdata, frames, time, status):
    global volume, paused, ffmpeg_proc
    if status:
        print("Sounddevice status:", status)

    if paused or not ffmpeg_proc:
        outdata[:] = np.zeros((frames, 2), dtype=np.float32)
        return

    bytes_needed = frames * 2 * 2
    data = ffmpeg_proc.stdout.read(bytes_needed)

    if not data:
        print("No data received. Stopping stream.")
        outdata[:] = np.zeros((frames, 2), dtype=np.float32)
        return

    if len(data) < bytes_needed:
        #print("short read")
        data += b'\x00' * (bytes_needed - len(data))
        outdata[:] = np.frombuffer(data, dtype=np.int16).reshape(-1, 2) / 32768.0 * volume
        return

    audio = np.frombuffer(data, dtype=np.int16).reshape(-1, 2).astype(np.float32) / 32768.0
    #print(data)
    led_controller.update(audio)
    outdata[:] = audio * volume


class Handler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        global volume, paused
        parsed_path = urllib.parse.urlparse(self.path)
        query = urllib.parse.parse_qs(parsed_path.query)

        if parsed_path.path == "/":
            self.send_response(200)
            self.send_header("Content-type", "text/html")
            self.end_headers()
            html_content = load_html_template()
            self.wfile.write(html_content.encode('utf-8'))
            return

        elif parsed_path.path == "/play":
            url = query.get("url", [""])[0]
            if url:
                start_stream(url)
                paused = False
                #self.respond("Playing URL: " + url)
                self.send_response(302)
                self.send_header("Location", "/")
                self.end_headers()
                return
            else:
                self.respond("Missing URL")

        elif parsed_path.path == "/pause":
            paused = True
            #self.respond("Paused")
            self.send_response(302)
            self.send_header("Location", "/")
            self.end_headers()
            return

        elif parsed_path.path == "/resume":
            paused = False
            #self.respond("Resumed")
            self.send_response(302)
            self.send_header("Location", "/")
            self.end_headers()
            return

        elif parsed_path.path == "/stop":
            stop_stream()
            #self.respond("Stopped")
            self.send_response(302)
            self.send_header("Location", "/")
            self.end_headers()
            return

        elif parsed_path.path == "/volume":
            val = query.get("value", [""])[0]
            if val == "up":
                volume = min(2.0, volume + 0.1)
            elif val == "down":
                volume = max(0.0, volume - 0.1)
            else:
                try:
                    volume = float(val)
                except:
                    pass
            self.send_response(302)
            self.send_header("Location", "/")
            self.end_headers()

        elif parsed_path.path == "/library":
            try:
                files = [f for f in os.listdir(LIB_DIR) if f.lower().endswith(('.mp3', '.wav', '.flac', '.aac'))]
            except Exception as e:
                self.respond(f"Error reading library: {e}")
                return
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(b"<html><body><h1>Library</h1><ul>")
            for f in files:
                self.wfile.write(f"<li><a href='/play_local?file={urllib.parse.quote(f)}'>{f}</a></li>".encode())
            self.wfile.write(b"</ul></body></html>")
            return

        elif parsed_path.path == "/play_local":
            fname = query.get("file", [""])[0]
            if fname:
                start_local_stream(urllib.parse.unquote(fname))
                paused = False
                #self.respond("Playing local file: " + fname)
                self.send_response(302)
                self.send_header("Location", "/")
                self.end_headers()
                return
            else:
                self.respond("Missing file name")
        if parsed_path.path == "/style.css":
            try:
                css_path = os.path.join("templates", "style.css")
                with open(css_path, "rb") as f:
                    self.send_response(200)
                    self.send_header("Content-Type", "text/css")
                    self.end_headers()
                    self.wfile.write(f.read())
            except FileNotFoundError:
                self.send_error(404, "style.css not found")
            return
        else:
            self.send_error(404, "Not Found")


    def respond(self, message):
        self.send_response(200)
        self.send_header("Content-type", "text/plain")
        self.end_headers()
        self.wfile.write(message.encode())


def start_local_stream(filename):
    global yt_proc, ffmpeg_proc, is_local
    path = os.path.join(LIB_DIR, filename)
    if not os.path.isfile(path):
        print(f"Local file not found: {path}")
        return
    stop_stream()
    is_local = True
    yt_proc = None
    ffmpeg_cmd = [
        "ffmpeg", "-re", "-i", path,
        "-vn", "-acodec", "pcm_s16le",
        "-ar", str(SAMPLE_RATE), "-ac", "2",
        "-f", "s16le", "pipe:1"
    ]
    print("Launching ffmpeg_proc for local file...")
    ffmpeg_proc = subprocess.Popen(ffmpeg_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)


def run_server():
    with socketserver.TCPServer(("", PORT), Handler) as httpd:
        print(f"Control server running on port {PORT}")
        httpd.serve_forever()


def run_app():
    threading.Thread(target=run_server, daemon=True).start()

    try:
        with sd.OutputStream(samplerate=SAMPLE_RATE, channels=2, dtype='float32', callback=audio_callback):
            while True:
                sd.sleep(1000)
    except KeyboardInterrupt:
        print("Stopped by user.")
    except Exception as e:
        print("Error occurred:", e)
    finally:
        stop_stream()
        print("Processes terminated.")


if __name__ == "__main__":
    run_app()
