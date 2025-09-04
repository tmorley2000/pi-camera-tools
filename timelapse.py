#!/usr/bin/python3
import time
import datetime
import sys
import os
import argparse
import simplejpeg
import piexif
import piexif.helper
import io
import json

import cv2

from picamera2 import MappedArray, Picamera2
from libcamera import controls, Transform
from picamera2.encoders import H264Encoder

parser = argparse.ArgumentParser(description='Pi Timelapse', formatter_class=argparse.ArgumentDefaultsHelpFormatter)
parser.add_argument('--interval', type=int, default=15, help='Timelapse interval (s)')
parser.add_argument('--binning', type=int, default=2, help='Downscale sensor resolution')
parser.add_argument('--maxgain', type=float, default=12.0, help='Maximum gain')
parser.add_argument('--dirname', type=str, default="imgs/", help='Directory to save images')
parser.add_argument('--filename', type=str, default="%Y/%m/%d/%Y%m%dT%H%M%S.jpg", help='Filename template (parsed with strftime, directories automatically created)')
parser.add_argument('--latest', type=str, default="latest.jpg", help='Name of file to symlink latest image to')
parser.add_argument('--metadata', type=str, default="%Y/%m/%d/metadata.json", help='Separate dump of image metadata')
parser.add_argument('--tuningfile', type=str, default=None, help='Base tuning file for camera, AGC parameters will be overridden')
parser.add_argument('--camera', type=int, default=0, help='Camera Number')
parser.add_argument('--rotate', default=False, help='Rotate image 180', action='store_true')

syncgroup = parser.add_mutually_exclusive_group()
syncgroup.add_argument('--syncserver', default=False, help='Camera Sync, server mode', action='store_true')
syncgroup.add_argument('--syncclient', default=False, help='Camera Sync, client mode', action='store_true')

parser.add_argument('--syncreadyframe', type=int, default=None, help='How many frames for sync server to wait before declaring itself ready')
parser.add_argument('--syncperiod', type=int, default=None, help='How often the sync server should advertise timing')

#parser.add_argument('--font', type=str, default='/usr/share/fonts/truetype/ttf-bitstream-vera/VeraBd.ttf', help='TTF font file for overlay text')
#parser.add_argument('--fontsize', type=int, default=12, help='Font size for overlay text')

parser.add_argument('--debug', default=False, help='Debug mode', action='store_true')

args = parser.parse_args()



if args.tuningfile is None:
    allcams=Picamera2.global_camera_info()

    # Seems global_camera_info initialises the libcamera object so 
    # new tuning file doesn't work!
    # Following from https://github.com/raspberrypi/picamera2/issues/886
    from picamera2.picamera2 import CameraManager
    import gc
    del Picamera2._cm
    Picamera2._cm = None
    gc.collect()
    Picamera2._cm = CameraManager()

    for c in allcams:
        if c['Num']==args.camera:
            args.tuningfile=c['Model']+'.json'

tuning = Picamera2.load_tuning_file(args.tuningfile)
agc = Picamera2.find_tuning_algo(tuning, "rpi.agc")
if "channels" in agc:
    agc["channels"][0]["exposure_modes"]["normal"] = {"shutter": [100,int(args.interval*1000000)], "gain": [1.0,args.maxgain]}
else:
    agc["exposure_modes"]["normal"] = {"shutter": [100,int(args.interval*1000000)], "gain": [1.0,args.maxgain]}

sync=Picamera2.find_tuning_algo(tuning, "rpi.sync")
if args.syncreadyframe:
    sync["ready_frame"]=args.syncreadyframe
if args.syncperiod:
    sync["sync_period"]=5

picam2 = Picamera2(tuning=tuning,camera_num=args.camera)

ctrls={}
ctrls["FrameDurationLimits"]= (int(args.interval*1000000), int(args.interval*1000000))
# Off Fast HighQuality
ctrls["NoiseReductionMode"]=controls.draft.NoiseReductionModeEnum.Off

if args.syncserver:
    ctrls['SyncMode']=controls.rpi.SyncModeEnum.Server
elif args.syncclient:
    ctrls['SyncMode']=controls.rpi.SyncModeEnum.Client

if args.rotate:
    transform=Transform(hflip=True, vflip=True)
else:
    transform=Transform()

size=tuple(int(x/args.binning) for x in picam2.sensor_resolution)

sc=picam2.create_still_configuration({'size':size,'format':'XBGR8888'},controls=ctrls,buffer_count=2,transform=transform)

picam2.configure(sc)

foreground = (255, 255, 255)
background = (0,0,0)

origin = (0, 30)
font = cv2.FONT_HERSHEY_SIMPLEX
scale = 0.7
thickness = 2

def apply_timestamp(request,dt):
    md=request.get_metadata()
    if args.debug:
        print("Cam %d exp %f ag %f dg %f"%(args.camera,md['ExposureTime']/1000000,md['AnalogueGain'],md['DigitalGain']))
    text=[]
    text.append(dt.isoformat())
    text.append("EXP: %f AG: %f DG: %f"%(md['ExposureTime']/1000000,md['AnalogueGain'],md['DigitalGain']))
    text.append("TEMP: %f LUX: %f CT: %d Focus: %d"%(md['SensorTemperature'],md['Lux'],md['ColourTemperature'],md['FocusFoM']))

    with MappedArray(request, "main") as m:
        y=-2
        for a in text:
            (w, h), baseline=cv2.getTextSize(a,font, scale, thickness)
            y+=h+6
            cv2.rectangle(m.array,(0,y+1+baseline),(w+2,y-h-2),background,-1)
            cv2.putText(m.array, a, (1,y), font, scale, foreground, thickness)

JPEG_FORMAT_TABLE = {"XBGR8888": "RGBX",
                "XRGB8888": "BGRX",
                "BGR888": "RGB",
                "RGB888": "BGR"}

def savejpeg(request,name,dt,dirname,filename,linkname=None,mdfilename=None):
    if '/' in filename:
        os.makedirs(os.path.dirname(os.path.join(dirname,filename)),exist_ok=True)
    #request.save(name,os.path.join(dirname,filename))

    jpeg_bytes=simplejpeg.encode_jpeg(request.make_array(name), quality=90, colorspace=JPEG_FORMAT_TABLE[request.config[name]["format"]], colorsubsampling="420")

    metadata=request.get_metadata()
    if "AnalogueGain" in metadata and "DigitalGain" in metadata:
        zero_ifd = {piexif.ImageIFD.Make: "Raspberry Pi",
                    piexif.ImageIFD.Model: picam2.camera.id,
                    piexif.ImageIFD.Software: "Picamera2",
                    piexif.ImageIFD.DateTime: dt.strftime("%Y:%m:%d %H:%M:%S")}
        total_gain = metadata["AnalogueGain"] * metadata["DigitalGain"]
        exif_ifd = {piexif.ExifIFD.DateTimeOriginal: dt.strftime("%Y:%m:%d %H:%M:%S"),
                    piexif.ExifIFD.ExposureTime: (metadata["ExposureTime"], 1000000),
                    piexif.ExifIFD.ISOSpeedRatings: int(total_gain * 100),
                    piexif.ExifIFD.UserComment: piexif.helper.UserComment.dump(json.dumps(metadata,sort_keys=True))}
        exif_bytes = piexif.dump({"0th": zero_ifd, "Exif": exif_ifd})
        new_bytes=io.BytesIO()
        piexif.insert(exif_bytes,jpeg_bytes,new_bytes)

    with open(os.path.join(dirname,filename),"wb") as file:
        file.write(new_bytes.getbuffer())

    if mdfilename is not None:
        with open(os.path.join(dirname,mdfilename),"a+") as mdfile:
            mdfile.seek(0)
            mdstr=mdfile.read()
            try:
                mdjson=json.loads(mdstr)
            except json.decoder.JSONDecodeError:
                print("Invalid or empty metadata json file, resetting")
                mdjson={}
            mdjson[os.path.basename(filename)]=metadata
            mdfile.seek(0)
            mdfile.truncate()
            mdfile.write(json.dumps(mdjson,sort_keys=True))

    if linkname is not None:
        os.symlink(filename,os.path.join(dirname,linkname+".new"))
        os.rename(os.path.join(dirname,linkname+".new"),os.path.join(dirname,linkname))

picam2.start()
mdfilename=None
while True:
    request=picam2.capture_request()
    dt=datetime.datetime.utcnow()
    apply_timestamp(request,dt)
    filename=dt.strftime(args.filename)
    if args.metadata is not None:
        mdfilename=dt.strftime(args.metadata)
    savejpeg(request,"main",dt,args.dirname,filename,args.latest,mdfilename)
    request.release()
