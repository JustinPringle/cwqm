#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Fri Dec  9 14:48:11 2022

@author: justinpringle
sort the format of the weather forcing
out:
    year month day hour rain wind direction
"""
import pandas as pd
import numpy as np
import os
import getgfs
import datetime as dt
from dateutil import tz

from_zone = tz.gettz('UTC')
to_zone = tz.gettz('Africa/Johannesburg')

def get_gfs(var_list = ['ugrd10m','vgrd10m','apcpsfc'],lat=-29.75,lon = 31,
             forecast_length=48):
    '''
    
    queries the NCEP OPENDap site
    get current to 24hrs forecast gfs wind and rain 

    Parameters
    ----------
    var_list : TYPE, optional
        DESCRIPTION. Variables to extract from GFS. 
        The default is ['ugrd10m','vgrd10m','apcpsfc'].
    lat : TYPE, optional
        DESCRIPTION. Lat and Lon of the data point.
        The default is -29.75lon = 31.

    Returns
    -------
    None.

    '''
    f=getgfs.Forecast("0p25","1hr")
    now = dt.datetime.utcnow()
    future = now+dt.timedelta(hours=forecast_length)

    timeList = pd.date_range(now,periods=forecast_length, freq='1H').to_pydatetime()

    storDict={
        'u10':[],
        'v10':[],
        'rain':[],
        'wind_speed':[],
        'direction':[]}

    for dat in timeList:
        print(dat.strftime('%Y%m%d %H:%M'))
        res = f.get(var_list,dat.strftime('%Y%m%d %H:%M'),lat,lon)
        u = res.variables["ugrd10m"].data.flatten()[0].round(3)
        v = res.variables["vgrd10m"].data.flatten()[0].round(3)
        p = res.variables["apcpsfc"].data.flatten()[0].round(3)
        if p>1000:
            p=0
        
        spd = np.sqrt(u**2+v**2).round(3)
        #this is wind going to... I must convert to coming from to sync with my model treatment 
        direction = ((270-np.degrees(np.arctan2(v,u)))%360).round(3)
        
        storDict['u10'].append(u)
        storDict['v10'].append(v)
        storDict['rain'].append(p)
        storDict['wind_speed'].append(spd)
        storDict['direction'].append(direction)
        
    df = pd.DataFrame(data=storDict)
    df['datetime'] = pd.date_range(now,periods=forecast_length, freq='1H',tz='UTC')
    #replace hour minute second and round to nearest hr
    df['datetime'] = df.datetime.map(lambda t: t.replace(microsecond=0,second=0,minute=0,hour=t.hour) \
                                     +dt.timedelta(hours=t.minute//30))
        
    #convert to local timezone
    # df['datetime']=df['datetime'].map(lambda x: x.tz_convert('Africa/Johannesburg'))
    # df['datetime']=df['datetime'].map(lambda x: x.replace(tzinfo=to_zone))
    df['year']=df['datetime'].dt.year
    df['month']=df['datetime'].dt.month
    df['day']=df['datetime'].dt.day
    df['hour']=df['datetime'].dt.hour
    
    # df[['year','month','day','hour','u10','v10','rain','spd','direction']].to_csv('forcing/gfs.csv')
    
    return df[['datetime','wind_speed','direction','rain']]

def read_raw_weather(fileName):
    '''
    

    Parameters
    ----------
    fileName : string
        full name to file including path.

    Returns
    -------
    formatted data frame.

    '''
    wdf = pd.read_csv(fileName)
    
    wdf['time'] =pd.to_datetime(wdf['# timestamp [sec UTC]'],unit='s',utc=True)
    wdf['datetime'] = wdf['time'].map(lambda x: x.tz_convert('Africa/Johannesburg'))
    
    outDf = wdf[['datetime','Rainfall intensity [mm]','Wind speed [m/s]','Wind direction [deg N]']]
    return outDf
    

def formatDfWeather(df):
    '''
    
    important to check for missing data

    Parameters
    ----------
    df : pandas dataframe
        dataframe containing wind, rain, time .

    Returns
    -------
    formatted dataframe.

    '''
    #fill missing dates
    df = df.set_index('datetime')
    #fill 5 min data
    df = df.asfreq(freq='300S')
    #only fill wind
    df['Wind speed [m/s]'] = (df['Wind speed [m/s]'].ffill()+df['Wind speed [m/s]'].bfill())/2
    df['Rainfall intensity [mm]'] = df['Rainfall intensity [mm]'].fillna(0)
    df = df.reset_index()
    #add hour
    df['hour']=df['datetime'].dt.hour
    df['day'] = df['datetime'].dt.day
    df['month'] = df['datetime'].dt.month
    df['year'] = df['datetime'].dt.year
    #dog work to get east and north
    dirs = df['Wind direction [deg N]'].values
    spd = df['Wind speed [m/s]'].values
    wEL=[]
    wNL=[]
    for i in range(len(dirs)):
        d = dirs[i]
        s = spd[i]
        #check quad
        if d>0 and d<=90:
            #in first quad
            a = np.radians(90-d)
            wE = s*np.sin(a)
            wN = s*np.cos(a)
        elif d>90 and d<=180:
            #in second quad
            a = np.radians(d-90)
            wE = s*np.cos(a)
            wN = -s*np.sin(a)
        elif d>180 and d<=270:
            #in thirdd quad
            a = np.radians(d-180)
            wE = -s*np.sin(a)
            wN = -s*np.cos(a)
        elif d>270 and d<=360:
            a = np.radians(d-270)
            wE = -s*np.cos(a)
            wN = s*np.sin(a)
        
        wEL.append(wE)
        wNL.append(wN)
    df['east']=wEL
    df['north']=wNL
    
    df=df.groupby(['year','month','day','hour'],as_index=False).agg(
        east = pd.NamedAgg(column='east', aggfunc='mean'),
        north = pd.NamedAgg(column='north', aggfunc='mean'),
        rainfall = pd.NamedAgg(column = 'Rainfall intensity [mm]',aggfunc='sum'))
    
    spd=[]
    dirs=[]
    e = df['east'].values
    n = df['north'].values
    for i in range(len(e)):
        s = np.sqrt(e[i]**2+n[i]**2)
        if e[i]>0 and n[i]>0:
            #we are in quad 1
            d = np.degrees(np.arctan(e[i]/n[i]))
        elif e[i]>0 and n[i]<0:
            #quad 2
            d = 90+np.degrees(np.arctan(-n[i]/e[i]))
        elif e[i]<0 and n[i]<0:
            #quad 3
            d = 270-np.degrees(np.arctan(-n[i]/-e[i]))
        elif e[i]<0 and n[i]>0:
            #quad 4
            d = 360-np.degrees(np.arctan(-e[i]/n[i]))
            
        spd.append(s)
        dirs.append(d)
    
    df['wind speed']=spd
    df['direction']=dirs
        
    #now make a new df in case missing dates
    
    pd.date_range(start=df.index[0], end=3, freq="H")
    
    
        
    
    return df
            

def read_raw_umgeni(fileName):
    '''
    

    Parameters
    ----------
    fileName : string
        full path to file.

    Returns
    -------
    formatted dataframe.

    '''
    
    df = pd.read_csv(fileName)
    df['time'] =pd.to_datetime(df['# timestamp [sec UTC]'],unit='s',utc=True)
    df['datetime'] = df['time'].map(lambda x: x.tz_convert('Africa/Johannesburg'))
    
    return df
           
def formatUmgeni(df):
    '''
    
    data coming from obscape

    Parameters
    ----------
    df : pandas dataframe
        dataframe containing umgeni flows

    Returns
    -------
    umgeni dataframe with flows @dT.

    '''
    df['hour']=df['datetime'].dt.hour
    df['day'] = df['datetime'].dt.day
    df['month'] = df['datetime'].dt.month
    df['year'] = df['datetime'].dt.year
    
    df=df.groupby(['year','month','day','hour'],as_index=False).agg(
        level = pd.NamedAgg(column='Water level [m]# ', aggfunc='mean'))
        
    df['flow'] = 20*df['level']
    
    return df

def formatUmgeni_dws(fileName):
    '''
    
    data coming from DWS 

    Parameters
    ----------
    df : pandas dataframe
        dataframe containing umgeni flows

    Returns
    -------
    umgeni dataframe with flows @dT.

    '''
    df = pd.read_csv(fileName)
    
    df=df.groupby(['Year','Month','Day','Hour'],as_index=False).agg(
        level = pd.NamedAgg(column='Flow', aggfunc='mean'))
        
    # df['flow'] = 20*df['level']
    
    return df
                      

fileName = '../test/forcing/weather.csv'
# udf = read_raw_umgeni(fileName)
# df = formatUmgeni_dws('../test/forcing/umgeni_dws.csv')
df = read_raw_weather('../test/forcing/weather.csv')
df2 = formatDfWeather(df)
# print(os.getcwd())

# df2.to_csv('../test/forcing/weatherForce.csv',index=False,float_format='%.3f')

