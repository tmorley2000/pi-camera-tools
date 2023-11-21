#!/usr/bin/python3

import io
import logging
import socketserver
from http import server
from threading import Condition
import threading
import simplejpeg
import numpy as np

from picamera2 import Picamera2
from picamera2.encoders import MJPEGEncoder
from picamera2.encoders import JpegEncoder
from picamera2.encoders import LibavMjpegEncoder
from picamera2.outputs import FileOutput

w=800
h=600
w2=int(w/2)
h2=int(h/2)

PAGE = """\
<html>
<head>
<title>Framing and Focus tool</title>
</head>
<body>
<h1>Framing and Focus tool</h1>
<table>
<tr><td colspan="2"><img src="stream.mjpg" width="{w}" height="{h}" /></td></tr>

<tr><td><img src="stream2.mjpg" width="{w2}" height="{h2}" /></td><td><img src="stream3.mjpg" width="{w2}" height="{h2}" /></td></tr>
<tr><td colspan="2"><img src="stream4.mjpg" width="{w}" height="{h2}" /></td></tr>
<tr><td><img src="stream5.mjpg" width="{w2}" height="{h2}" /></td><td><img src="stream6.mjpg" width="{w2}" height="{h2}" /></td></tr>
</body>
</html>
""".format(w=w,h=h,w2=w2,h2=h2)


class StreamingOutput(io.BufferedIOBase):
    def __init__(self):
        self.frame = None
        self.condition = Condition()

    def write(self, buf):
        with self.condition:
            self.frame = buf
            self.condition.notify_all()

output = StreamingOutput()
output2 = StreamingOutput()
output3 = StreamingOutput()
output4 = StreamingOutput()
output5 = StreamingOutput()
output6 = StreamingOutput()

class StreamingHandler(server.BaseHTTPRequestHandler):
    def do_GET(self):
        streams={'/stream.mjpg':output,
                 '/stream2.mjpg':output2,
                 '/stream3.mjpg':output3,
                 '/stream4.mjpg':output4,
                 '/stream5.mjpg':output5,
                 '/stream6.mjpg':output6,}
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
        elif self.path in streams:
            op=streams[self.path]
            self.send_response(200)
            self.send_header('Age', 0)
            self.send_header('Cache-Control', 'no-cache, private')
            self.send_header('Pragma', 'no-cache')
            self.send_header('Content-Type', 'multipart/x-mixed-replace; boundary=FRAME')
            self.end_headers()
            try:
                while True:
                    with op.condition:
                        op.condition.wait()
                        frame = op.frame
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

picam2 = Picamera2()
r=picam2.sensor_modes[2]
fullsize=picam2.sensor_resolution
streamsize=(w,h)
#picam2.configure(picam2.create_video_configuration({"size": size},raw=r))

#config = picam2.create_video_configuration({"size": fullsize}, lores={"size": streamsize},raw=r,controls={'FrameRate': 10,},buffer_count=3)
config = picam2.create_video_configuration({"size": fullsize}, lores={"size": streamsize},controls={'FrameRate': 12,},buffer_count=2)
picam2.configure(config)


#picam2.start_recording(MJPEGEncoder(), FileOutput(output),name="lores")
#picam2.start_recording(JpegEncoder(), FileOutput(output),name="lores")
picam2.start_recording(LibavMjpegEncoder(), FileOutput(output),name="lores")


try:
    #address = ('', 8000)
    #server = StreamingServer(address, StreamingHandler)
    #server.serve_forever()
    threading.Thread(target=start_server).start()

    counter=0
    while True:
        request = picam2.capture_request()
        if counter%4 == 0:
            array=request.make_array("main")
            f2=np.ascontiguousarray(array[:h2,:w2])
            output2.write(simplejpeg.encode_jpeg(f2, quality=65, colorspace="RGBX", colorsubsampling='420'))
            f3=np.ascontiguousarray(array[:h2,-w2:])
            output3.write(simplejpeg.encode_jpeg(f3, quality=65, colorspace="RGBX", colorsubsampling='420'))
            f4=np.ascontiguousarray(array[int(fullsize[1]/2-95):int(fullsize[1]/2+95),int(fullsize[1]/2-w2):int(fullsize[1]/2+w2)])
            output4.write(simplejpeg.encode_jpeg(f4, quality=65, colorspace="RGBX", colorsubsampling='420'))
            f5=np.ascontiguousarray(array[-h2:,:w2])
            output5.write(simplejpeg.encode_jpeg(f5, quality=65, colorspace="RGBX", colorsubsampling='420'))
            f6=np.ascontiguousarray(array[-h2:,-w2:])
            output6.write(simplejpeg.encode_jpeg(f6, quality=65, colorspace="RGBX", colorsubsampling='420'))
            a=None
        counter+=1
        request.release()

finally:
    picam2.stop_recording()
