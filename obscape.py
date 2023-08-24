#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Mon Jan 16 10:44:59 2023

@author: justinpringle
1. Use the api docs from the obscape website
"""
import numpy as np
import json as js
import pandas as pd
from urllib.request import urlopen
import datetime as dt
from zoneinfo import ZoneInfo
from dateutil import tz
import ssl
ssl._create_default_https_context = ssl._create_unverified_context

from_zone = tz.gettz('UTC')
to_zone = tz.gettz('Africa/Johannesburg')


def getData(nowDate,fromDate,stationID=457,hours=168):
    '''
    

    Parameters
    ----------
    fromDate : datetime
        datetime object of the from date.
    stationID : TYPE, optional
        DESCRIPTION. The default is 457.
    hours : TYPE, optional
        DESCRIPTION. The default is 168.

    Returns
    -------
    TYPE
        DESCRIPTION.

    '''
    #store my user data in a dict
    userDict={
        'name':'Justin',
        'api':'JKwPFmFGhRMzaua0pVKsIeIRHnuNOXexHLnn934pUQY5k0dK5X'}
    #this is the ushaka 
    # ushakaID=457
    # hours = 2*168 #(1week)
    
    nowDateStr = nowDate.strftime('%Y-%m-%dT%H:%M:%S')
    fromDateStr = fromDate.strftime('%Y-%m-%dT%H:%M:%S')
    
    url = 'https://obscape.com/portal/api/v3/api?username={name}&project=ethek&key={key}&station={station}&from={_from}&to={_to}'.format(
        name=userDict['name'],key=userDict['api'],station=stationID,_from=fromDateStr,
        _to=nowDateStr)
    
    print(url)
    
    response = urlopen(url)
    
    dataJSON = js.load(response)
    
    data = dataJSON['data']
    
    num_items = len(data)
    
    dfDict ={
        'datetime':[],
        'wind_speed':[],
        'east_wind':[],
        'north_wind':[],
        'wind_direction':[],
        'rain':[]
        }
    
    for i in range(num_items):
        datUTC = data[i]['time']
        wspd = data[i]['windSpeed']
        wdir = data[i]['windDirection']
        rain = data[i]['precipitation']
        ew = data[i]['EastWindSpeed']
        nw = data[i]['NorthWindSpeed']
        
        #check for nans
        if wspd<-100:
            wspd=np.nan
        if ew<-100:
            ew=np.nan
        if nw <-100:
            nw=np.nan
        if wdir<-100:
            wdir=np.nan
        if rain <-100:
            rain=np.nan
        
        #correct times
        datFrom = dt.datetime.utcfromtimestamp(int(datUTC)).replace(tzinfo=from_zone)
        datLocal = datFrom.astimezone(to_zone)
        #I'm working in UTC until I need to show local time
        dfDict['datetime'].append(datFrom)
        dfDict['wind_speed'].append(wspd)
        dfDict['wind_direction'].append(wdir)
        dfDict['east_wind'].append(ew)
        dfDict['north_wind'].append(nw)
        dfDict['rain'].append(rain)
        
    return format1HR(pd.DataFrame(data=dfDict))


def format1HR(df):
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
    
    df['rain'] = df['rain'].fillna(0)
    df = df.reset_index()
    
    #add hour
    df['hour']=df['datetime'].dt.hour
    df['day'] = df['datetime'].dt.day
    df['month'] = df['datetime'].dt.month
    df['year'] = df['datetime'].dt.year
    
    #avg for hour
    df=df.groupby(['year','month','day','hour'],as_index=False).agg(
        east_wind = pd.NamedAgg(column='east_wind', aggfunc='mean'),
        north_wind = pd.NamedAgg(column='north_wind', aggfunc='mean'),
        rain = pd.NamedAgg(column = 'rain',aggfunc='sum'))
    
    spd=[]
    dirs=[]
    e = df['east_wind'].values
    n = df['north_wind'].values
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
            
        spd.append(np.round(s,3))
        dirs.append(np.round(d,3))
    
    df['wind_speed']=spd
    df['direction']=dirs
    
    df['datetime'] = pd.to_datetime(df[['year','month','day','hour']],utc=True)#.map(
        # lambda x: x.tz_convert('Africa/Johannesburg')
        # )
           
    # pd.date_range(start=df.index[0], end=3, freq="H")
    
    return df[['datetime','wind_speed','direction','rain']]

if __name__=='__main__':
    df = getData()
        
        
        
        
        
        
        
        
        
        
        
        
        
