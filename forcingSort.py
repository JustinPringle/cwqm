#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Fri Dec  9 14:48:11 2022

@author: justinpringle
sort the format of the weather forcing
out:
    year month day hour rain wind direction
"""
import logging
import json as js
import pandas as pd
import numpy as np
import os
import datetime as dt
from urllib.request import urlopen
from urllib.error import URLError, HTTPError
from dateutil import tz

logger = logging.getLogger(__name__)

from_zone = tz.gettz('UTC')
to_zone = tz.gettz('Africa/Johannesburg')

# NOMADS OpenDAP service was shut down on 24 Feb 2026 (SCN25-81).
# GFS forecast data is now fetched from the Open-Meteo API, which provides
# the same GFS-seamless model output for a single lat/lon point as JSON.
_OPENMETEO_URL = (
    'https://api.open-meteo.com/v1/forecast'
    '?latitude={lat}&longitude={lon}'
    '&hourly=wind_speed_10m,wind_direction_10m,precipitation'
    '&wind_speed_unit=ms'
    '&timezone=UTC'
    '&forecast_days={days}'
)
_REQUEST_TIMEOUT = 30

def get_gfs(var_list=None, lat=-29.75, lon=31, forecast_length=48):
    '''
    Fetch GFS forecast wind and rain from the Open-Meteo API.

    The original implementation queried the NCEP NOMADS OpenDAP service,
    which was permanently shut down on 24 Feb 2026. Open-Meteo provides
    the same GFS-seamless data as hourly JSON for a single lat/lon point
    with no API key required.

    Parameters
    ----------
    var_list : ignored
        Kept for backward compatibility.
    lat : float, optional
        Latitude of the forecast point. Default is -29.75 (Durban).
    lon : float, optional
        Longitude of the forecast point. Default is 31.
    forecast_length : int, optional
        Number of hourly steps to return. Default is 48.

    Returns
    -------
    pd.DataFrame
        Columns: datetime (UTC timezone-aware), wind_speed (m/s),
        direction (degrees from N, meteorological), rain (mm/hr).
    '''
    # Open-Meteo works in whole days; request enough to cover forecast_length.
    forecast_days = min(int(np.ceil(forecast_length / 24)) + 1, 16)

    url = _OPENMETEO_URL.format(lat=lat, lon=lon, days=forecast_days)

    logger.info('Fetching GFS forecast via Open-Meteo for %d hours from %s',
                forecast_length,
                dt.datetime.now(dt.timezone.utc).strftime('%Y-%m-%d %H:%M UTC'))
    try:
        response = urlopen(url, timeout=_REQUEST_TIMEOUT)
    except HTTPError as exc:
        raise RuntimeError(
            'Open-Meteo API returned HTTP %d: %s' % (exc.code, exc.reason)
        ) from exc
    except URLError as exc:
        raise RuntimeError(
            'Could not reach Open-Meteo API: %s' % exc.reason
        ) from exc

    data = js.load(response)
    hourly = data['hourly']

    # Trim to requested length and replace any null values.
    def _clean(values, fill):
        return [fill if v is None else v for v in values[:forecast_length]]

    spd  = np.array(_clean(hourly['wind_speed_10m'],    np.nan), dtype=float).round(3)
    dirs = np.array(_clean(hourly['wind_direction_10m'], np.nan), dtype=float).round(3)
    rain = np.array(_clean(hourly['precipitation'],      0.0),   dtype=float).round(3)

    times = pd.to_datetime(hourly['time'][:forecast_length], utc=True)

    df = pd.DataFrame({
        'datetime':   times,
        'wind_speed': spd,
        'direction':  dirs,
        'rain':       rain,
    })

    return df[['datetime', 'wind_speed', 'direction', 'rain']]

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
    
    e = df['east'].values
    n = df['north'].values
    spd = np.sqrt(e**2 + n**2)
    # Convert (east, north) vector to meteorological bearing (clockwise from N).
    # np.arctan2 handles all quadrants including e==0 or n==0.
    dirs = (90 - np.degrees(np.arctan2(n, e))) % 360

    df['wind speed'] = spd
    df['direction'] = dirs
        
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
                      
if __name__=='__main__':
    fileName = '../test/forcing/weather.csv'
# udf = read_raw_umgeni(fileName)
# df = formatUmgeni_dws('../test/forcing/umgeni_dws.csv')
    df = read_raw_weather('../test/forcing/weather.csv')
    df2 = formatDfWeather(df)
# print(os.getcwd())

# df2.to_csv('../test/forcing/weatherForce.csv',index=False,float_format='%.3f')

