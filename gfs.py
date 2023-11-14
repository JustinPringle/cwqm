#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Fri Jan 13 11:11:27 2023

@author: justinpringle

#note 'apcpsfc', '** surface total precipitation [kg/m^2] ' this equates to mm (kg/m2/rho*1000)
"""
import getgfs
import numpy as np
import datetime as dt
import pandas as pd

f=getgfs.Forecast("0p25","1hr")

var_list = ['ugrd10m','vgrd10m','apcpsfc']
lat=-29.75
lon = 31

now = dt.datetime.utcnow()
future = now+dt.timedelta(hours=24)

timeList = pd.date_range(now,periods=24, freq='1H').to_pydatetime()

storDict={
    'u10':[],
    'v10':[],
    'rain':[],
    'spd':[],
    'direction':[]}

for dat in timeList:
    print(dat.strftime('%Y%m%d %H:%I'))
    res = f.get(var_list,dat.strftime('%Y%m%d %H:%I'),lat,lon)
    u = res.variables["ugrd10m"].data.flatten()[0]
    v = res.variables["vgrd10m"].data.flatten()[0]
    p = res.variables["apcpsfc"].data.flatten()[0]
    print('here')
    if p>1000:
        p=0
#    print(p)
    spd = np.sqrt(u**2+v**2)
    #this is wind going to... I must convert to coming from to sync with my model treatment 
    direction = (270-np.degrees(np.arctan2(v,u)))%360
    
    storDict['u10'].append(u)
    storDict['v10'].append(v)
    storDict['rain'].append(p)
    storDict['spd'].append(spd)
    storDict['direction'].append(direction)
    
