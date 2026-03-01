#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Mon Jan 16 10:44:59 2023

@author: justinpringle
Fetch real-time weather observations from the obscape.com API.
"""
import logging
import numpy as np
import json as js
import pandas as pd
from urllib.request import urlopen
from urllib.error import URLError, HTTPError
import datetime as dt
from dateutil import tz

logger = logging.getLogger(__name__)

from_zone = tz.gettz('UTC')
to_zone = tz.gettz('Africa/Johannesburg')

# Sentinel value used by the obscape API to flag missing / invalid readings.
_MISSING_THRESHOLD = -100
# Timeout in seconds for HTTP requests to the obscape API.
_REQUEST_TIMEOUT = 30


def getData(nowDate: dt.datetime, fromDate: dt.datetime,
            stationID: int = 457, hours: int = 168) -> pd.DataFrame:
    '''
    Fetch wind and rain observations from the obscape API.

    Parameters
    ----------
    nowDate : datetime
        End of the requested data window (UTC).
    fromDate : datetime
        Start of the requested data window (UTC).
    stationID : int, optional
        Obscape station ID for wind data. Default is 457 (Ushaka).
    hours : int, optional
        Legacy parameter kept for API compatibility. Default is 168.

    Returns
    -------
    pd.DataFrame
        Hourly DataFrame with columns: datetime, wind_speed, direction, rain.

    Raises
    ------
    HTTPError
        If the obscape API returns a non-2xx response.
    URLError
        If the obscape API cannot be reached.
    '''
    import os
    api_name = os.environ.get('OBSCAPE_USERNAME', 'Justin')
    api_key = os.environ.get('OBSCAPE_API_KEY', '')

    nowDateStr = nowDate.strftime('%Y-%m-%dT%H:%M:%S')
    fromDateStr = fromDate.strftime('%Y-%m-%dT%H:%M:%S')

    url = (
        'https://obscape.com/portal/api/v3/api'
        '?username={name}&project=ethek&key={key}'
        '&station={station}&from={_from}&to={_to}'
    ).format(name=api_name, key=api_key, station=stationID,
             _from=fromDateStr, _to=nowDateStr)

    #rain from durban point Durban_Point
    urlRain = (
        'https://obscape.com/portal/api/v3/api'
        '?username={name}&project=ethek&key={key}'
        '&ref={ref}&device={device}&from={_from}&to={_to}'
    ).format(name=api_name, key=api_key, ref='Durban_Point',
             device='rain', _from=fromDateStr, _to=nowDateStr)

    logger.info('Fetching wind data from obscape (station %d)', stationID)
    response = urlopen(url, timeout=_REQUEST_TIMEOUT)
    logger.info('Fetching rain data from obscape (Durban_Point)')
    responseR = urlopen(urlRain, timeout=_REQUEST_TIMEOUT)

    dataJSON = js.load(response)
    dataJSONRain = js.load(responseR)
    
    data = dataJSON['data']
    dataR = dataJSONRain['data']
    
    num_items = len(data)
    num_items_rain = len(dataR)
    
    dfDict ={
        'datetime':[],
        'wind_speed':[],
        'east_wind':[],
        'north_wind':[],
        'wind_direction':[]
        # 'rain':[]
        }
    
    for i in range(num_items):
        datUTC = data[i]['time']
        wspd = data[i]['windSpeed']
        wdir = data[i]['windDirection']
        # rain = data[i]['precipitation']
        ew = data[i]['EastWindSpeed']
        nw = data[i]['NorthWindSpeed']
        
        #check for nans (API uses values below _MISSING_THRESHOLD to flag bad data)
        if wspd < _MISSING_THRESHOLD:
            wspd = np.nan
        if ew < _MISSING_THRESHOLD:
            ew = np.nan
        if nw < _MISSING_THRESHOLD:
            nw = np.nan
        if wdir < _MISSING_THRESHOLD:
            wdir = np.nan

        #correct times (work in UTC internally)
        datFrom = dt.datetime.utcfromtimestamp(int(datUTC)).replace(tzinfo=from_zone)
        dfDict['datetime'].append(datFrom)
        dfDict['wind_speed'].append(wspd)
        dfDict['wind_direction'].append(wdir)
        dfDict['east_wind'].append(ew)
        dfDict['north_wind'].append(nw)
        # dfDict['rain'].append(rain)
    
    dataWeather = format1HRW(pd.DataFrame(data=dfDict))
    
    #get rain
    dfDictR = {
        'datetime':[],
        'rain':[]
        }
    
    for i in range(num_items_rain):
        rain = dataR[i]['precipitation']
        datUTC = dataR[i]['time']
        
        if rain < _MISSING_THRESHOLD:
            rain = np.nan

        datFrom = dt.datetime.utcfromtimestamp(int(datUTC)).replace(tzinfo=from_zone)
        dfDictR['datetime'].append(datFrom)
        dfDictR['rain'].append(rain)
        
    dataRain = format1HRR(pd.DataFrame(data=dfDictR))
    
    dfAll = dataWeather.merge(dataRain,on='datetime')
    
        
    return dfAll


def format1HRW(df):
    '''
    

    Parameters
    ----------
    df : Dataframe
        dataframe containing weather data.

    Returns
    -------
    formatted df.

    '''
    #fill missing dates
    df = df.set_index('datetime')
    #fill 5 min data
    df.resample('300S')
    # df = df.asfreq(freq='300S')
    #only fill wind first inbetweens then forwards (i.e. end of df) and backwards (ie nans at beginning of df)
    df['wind_speed'] = (df['wind_speed'].ffill()+df['wind_speed'].bfill())/2
    df['wind_speed'] = (df['wind_speed'].ffill())
    df['wind_speed'] =df['wind_speed'].bfill()
    
    df['east_wind'] = (df['east_wind'].ffill()+df['east_wind'].bfill())/2
    df['east_wind'] = df['east_wind'].ffill()
    df['east_wind'] = df['east_wind'].bfill()
    
    df['north_wind'] = (df['north_wind'].ffill()+df['north_wind'].bfill())/2
    df['north_wind'] = df['north_wind'].ffill()
    df['north_wind'] = df['north_wind'].bfill()
    
    # df['rain'] = df['rain'].fillna(0)
    df = df.reset_index()
    
    #add hour
    df['hour']=df['datetime'].dt.hour
    df['day'] = df['datetime'].dt.day
    df['month'] = df['datetime'].dt.month
    df['year'] = df['datetime'].dt.year
    
    #avg for hour
    df=df.groupby(['year','month','day','hour'],as_index=False).agg(
        east_wind = pd.NamedAgg(column='east_wind', aggfunc='mean'),
        north_wind = pd.NamedAgg(column='north_wind', aggfunc='mean'))#,
        #rain = pd.NamedAgg(column = 'rain',aggfunc='sum'))
    
    e = df['east_wind'].values
    n = df['north_wind'].values
    spd = np.round(np.sqrt(e**2 + n**2), 3)
    # Convert (east, north) vector to meteorological bearing (clockwise from N).
    # np.arctan2 handles all quadrants including e==0 or n==0.
    dirs = np.round((90 - np.degrees(np.arctan2(n, e))) % 360, 3)
    
    df['wind_speed'] = spd
    df['direction'] = dirs
    
    df['datetime'] = pd.to_datetime(df[['year','month','day','hour']],utc=True)#.map(
        # lambda x: x.tz_convert('Africa/Johannesburg')
        # )
           
    # pd.date_range(start=df.index[0], end=3, freq="H")
    
    return df[['datetime','wind_speed','direction']]

def format1HRR(df):
    '''
    

    Parameters
    ----------
    df : Dataframe
        dataframe containing weather data.

    Returns
    -------
    formatted df.

    '''
    #fill missing dates
    df = df.set_index('datetime')
    #fill 5 min data
    df.resample('300S')
    
    
    
    df['rain'] = df['rain'].fillna(0)
    df = df.reset_index()
    
    #add hour
    df['hour']=df['datetime'].dt.hour
    df['day'] = df['datetime'].dt.day
    df['month'] = df['datetime'].dt.month
    df['year'] = df['datetime'].dt.year
    
    #avg for hour
    df=df.groupby(['year','month','day','hour'],as_index=False).agg(
        rain = pd.NamedAgg(column = 'rain',aggfunc='sum'))
    
    
    
    df['datetime'] = pd.to_datetime(df[['year','month','day','hour']],utc=True)#.map(
        # lambda x: x.tz_convert('Africa/Johannesburg')
        # )
           
    # pd.date_range(start=df.index[0], end=3, freq="H")
    
    return df[['datetime','rain']]

if __name__=='__main__':
    df = getData()
        
        
        
        
        
        
        
        
        
        
        
        
        
