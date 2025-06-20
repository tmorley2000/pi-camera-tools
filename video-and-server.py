import time
import datetime
import io
import logging
import socketserver
import threading
from http import server
from threading import Condition

from picamera2 import Picamera2
from picamera2.encoders import H264Encoder, MJPEGEncoder
from picamera2.outputs import FileOutput,SplittableOutput

# Get Picamera2 to encode an H264 stream, and encode another MJPEG one "manually".

PAGE = """\
<html>
<head>
<title>picamera2 MJPEG streaming demo</title>
</head>
<body>
<h1>Picamera2 MJPEG Streaming Demo</h1>
<img src="stream.mjpg" width="480" height="270" />
</body>
</html>
"""

class StreamingOutput(io.BufferedIOBase):
    def __init__(self):
        self.frame = None
        self.condition = Condition()

    def write(self, buf):
        with self.condition:
            self.frame = buf
            self.condition.notify_all()

class StreamingHandler(server.BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == '/':
            self.send_response(301)
            self.send_header('Location', '/index.html')
            self.end_headers()
        elif self.path == '/index.html':
            content = PAGE.encode('utf-8')
            self.send_response(200)
            self.send_header('Content-Type', 'text/html')
            self.send_header('Content-Length', len(content))
            self.end_headers()
            self.wfile.write(content)
        elif self.path == '/stream.mjpg':
            self.send_response(200)
            self.send_header('Age', 0)
            self.send_header('Cache-Control', 'no-cache, private')
            self.send_header('Pragma', 'no-cache')
            self.send_header('Content-Type', 'multipart/x-mixed-replace; boundary=FRAME')
            self.end_headers()
            try:
                while True:
                    with output.condition:
                        output.condition.wait()
                        frame = output.frame
                    self.wfile.write(b'--FRAME\r\n')
                    self.send_header('Content-Type', 'image/jpeg')
                    self.send_header('Content-Length', len(frame))
                    self.end_headers()
                    self.wfile.write(frame)
                    self.wfile.write(b'\r\n')
            except Exception as e:
                logging.warning(
                    'Removed streaming client %s: %s',
                    self.client_address, str(e))
        else:
            self.send_error(404)
            self.end_headers()


class StreamingServer(socketserver.ThreadingMixIn, server.HTTPServer):
    allow_reuse_address = True
    daemon_threads = True

def start_server():
    address = ('', 8000)
    server = StreamingServer(address, StreamingHandler)
    print(server.__dict__.keys())
    server.serve_forever()

def genfilename():
    dt=datetime.datetime.utcnow()
    return dt.strftime("imgs/%Y%m%dT%H%M%S.h264")

picam2 = Picamera2()
fullsize=picam2.sensor_resolution
config = picam2.create_video_configuration({"size": (1920, 1080)}, lores={"size": (int(1920/4), int(1080/4))},sensor={'output_size':fullsize})
picam2.configure(config)

h264_encoder = H264Encoder()
h264_output = SplittableOutput(output=FileOutput(genfilename()))

mjpeg_encoder = MJPEGEncoder()
mjpeg_encoder.framerate = 30
mjpeg_encoder.size = config["lores"]["size"]
mjpeg_encoder.format = config["lores"]["format"]
mjpeg_encoder.bitrate = 5000000
output=StreamingOutput()
mjpeg_encoder.output = FileOutput(output)
mjpeg_encoder.start()

picam2.start_recording(h264_encoder, h264_output)

def mjpegpush():
    while True:
        print("frame")
        request = picam2.capture_request()
        mjpeg_encoder.encode("lores", request)
        request.release()
        time.sleep(1)


try:
    threading.Thread(target=start_server).start()
    threading.Thread(target=mjpegpush).start()

    while True:
        time.sleep(60)
        h264_output.split_output(FileOutput(genfilename()))
	
finally:
    picam2.stop_recording()



mjpeg_encoder.stop()
picam2.stop_recording()
