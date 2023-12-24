#!/usr/bin/python3
import time
import datetime
import sys

import cv2

from picamera2 import MappedArray, Picamera2
from libcamera import controls
from picamera2.encoders import H264Encoder

fd=15.0

tuning = Picamera2.load_tuning_file("imx477_scientific.json")
algo = Picamera2.find_tuning_algo(tuning, "rpi.agc")
if "channels" in algo:
    algo["channels"][0]["exposure_modes"]["normal"] = {"shutter": [100,int(fd*1000000)], "gain": [1.0,12.0]}
else:
    algo["exposure_modes"]["normal"] = {"shutter": [100,int(fd*1000000)], "gain": [1.0,12.0]}


#picam2 = Picamera2(tuning="imx477_scientific-20sec.json")
picam2 = Picamera2(tuning=tuning)

crtl={}
crtl["FrameDurationLimits"]= (int(fd*1000000), int(fd*1000000))
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
    r.save("main",dt.isoformat()+".jpg")
    r.release()
