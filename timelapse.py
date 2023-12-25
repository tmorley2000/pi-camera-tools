#!/usr/bin/python3
import time
import datetime
import sys
import os
import argparse

import cv2

from picamera2 import MappedArray, Picamera2
from libcamera import controls
from picamera2.encoders import H264Encoder

parser = argparse.ArgumentParser(description='Pi Timelapse', formatter_class=argparse.ArgumentDefaultsHelpFormatter)
parser.add_argument('--interval', type=int, default=15, help='Timelapse interval (s)')
parser.add_argument('--maxgain', type=float, default=12.0, help='Maximum gain')
parser.add_argument('--dirname', type=str, default="imgs/", help='Directory to save images')
parser.add_argument('--filename', type=str, default="%Y/%m/%d/%Y%m%dT%H%M%S.jpg", help='Filename template (parsed with strftime, directories automatically created)')
parser.add_argument('--latest', type=str, default="latest.jpg", help='Name of file to symlink latest image to')
parser.add_argument('--tuningfile', type=str, default="imx477_scientific.json", help='Base tuning file for camera, AGC parameters will be overridden')

#parser.add_argument('--font', type=str, default='/usr/share/fonts/truetype/ttf-bitstream-vera/VeraBd.ttf', help='TTF font file for overlay text')
#parser.add_argument('--fontsize', type=int, default=12, help='Font size for overlay text')

args = parser.parse_args()

tuning = Picamera2.load_tuning_file(args.tuningfile)
algo = Picamera2.find_tuning_algo(tuning, "rpi.agc")
if "channels" in algo:
    algo["channels"][0]["exposure_modes"]["normal"] = {"shutter": [100,int(args.interval*1000000)], "gain": [1.0,args.maxgain]}
else:
    algo["exposure_modes"]["normal"] = {"shutter": [100,int(args.interval*1000000)], "gain": [1.0,args.maxgain]}

picam2 = Picamera2(tuning=tuning)

crtl={}
crtl["FrameDurationLimits"]= (int(args.interval*1000000), int(args.interval*1000000))
# Off Fast HighQuality
crtl["NoiseReductionMode"]=controls.draft.NoiseReductionModeEnum.Off
sc=picam2.create_still_configuration({'size':(2028,1520),'format':'XBGR8888'},controls=crtl,buffer_count=2)

#sys.exit(0)

picam2.configure(sc)

foreground = (255, 255, 255)
background = (0,0,0)

origin = (0, 30)
font = cv2.FONT_HERSHEY_SIMPLEX
scale = 0.7
thickness = 2



def apply_timestamp(request,dt):
    md=request.get_metadata()
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
        


x=0
picam2.start()
while True:
    r=picam2.capture_request()
    dt=datetime.datetime.utcnow()
    apply_timestamp(r,dt)
    filename=dt.strftime(args.filename)
    if '/' in filename:
        os.makedirs(os.path.dirname(os.path.join(args.dirname,filename)),exist_ok=True)
    r.save("main",os.path.join(args.dirname,filename))
    os.symlink(filename,os.path.join(args.dirname,args.latest+".new"))
    os.rename(os.path.join(args.dirname,args.latest+".new"),os.path.join(args.dirname,args.latest))

    r.release()
