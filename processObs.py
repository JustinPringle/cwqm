#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Mon Dec 12 15:20:28 2022

@author: justinpringle
read observation .csv file
order observations into array (N,M)
    N - number of obs
    M - obs locations
"""
import logging
import pandas as pd
import numpy as np
import datetime as dt
import json as js
from urllib.request import urlopen
from urllib.error import URLError, HTTPError
import configparser
from pretreatment import read_obs_params

logger = logging.getLogger(__name__)

# Timeout in seconds for HTTP requests to the observations API.
_REQUEST_TIMEOUT = 30

def queryDB(_from):
    '''
    
    query my data base
    get the observations in local time zone: Africa/Johannesburg

    Returns
    -------
    None.

    '''
    
    _fromStr = _from.strftime('%Y-%m-%dT%H:%M:%S')
    url = 'http://justinpringle.com/woza_ewandle/getObs/getObs.php?from={_from}'.format(
        _from=_fromStr)
    logger.info('Querying observations from %s', _fromStr)
    try:
        response = urlopen(url, timeout=_REQUEST_TIMEOUT)
    except HTTPError as exc:
        raise RuntimeError(
            'Observations API returned HTTP %d: %s' % (exc.code, exc.reason)
        ) from exc
    except URLError as exc:
        raise RuntimeError(
            'Could not reach observations API: %s' % exc.reason
        ) from exc

    dataJSON = js.load(response)
    num_items = len(dataJSON)
    logger.info('Received %d observation records', num_items)
    
    obsDict = {
        'datetime':[],
        'beach':[],
        'ecoli':[]
        }
    
    for i in range(num_items):
        datUTC = dataJSON[i]['datetime']
        beach = dataJSON[i]['beach']
        ecoli = dataJSON[i]['ecoli']
        
        obsDict['beach'].append(beach)
        obsDict['ecoli'].append(ecoli)
        
        datFrom = dt.datetime.strptime(datUTC, '%Y-%m-%d %H:%M:%S')
        
        obsDict['datetime'].append(datFrom)
        
    return pd.DataFrame(data=obsDict)
    

def readObs(fileName):
    '''
    

    Parameters
    ----------
    fileName : string
        full name incl path of observation file.

    Returns
    -------
    pandas datafram.

    '''
    
    df = pd.read_csv(fileName)
    
    return df

def createTable(fileName):
    '''
    
    I am making the data conform to my simulation date range and time step
    
    Parameters
    ----------
    df : pandas dataframe
        dataframe containing raw data.

    Returns
    -------
    save observational data.

    '''
    fileName = 'ecoli.csv'

    df = readObs(fileName)
    df['date'] = pd.to_datetime(df[['Year','Month','Day','Hour']])
    df2 = df.pivot(index=['date'],columns=['Location'],values='eColi').reset_index()
    
    #note columns order should follow obLocs.csv
    df2 = df2.reindex(['Year','Month','Day','Hour','point','ushaka','south','north','pirates','country club'],axis=1)
    # if you want to save the data
    # data = df2.to_csv('ecoli_sorted.csv',index=False)
    
    start = dt.datetime(2022,1,1)
    end = dt.datetime(2022,12,8)
    index = pd.date_range(start,end, freq='H')
    
    df4 = pd.DataFrame({'date':index})
      
    
    merged = pd.merge(df4, df2,how='outer',on=['date']).fillna(-9)
    merged['Year'] = merged['date'].dt.year
    merged['Month'] = merged['date'].dt.month
    merged['Day'] = merged['date'].dt.day
    merged['Hour']= merged['date'].dt.hour
    
    merged = merged.reindex(['Year','Month','Day','Hour','point','ushaka','south','north','pirates','country club'],axis=1)
    
    merged.to_csv('observations/ecoli_sorted.csv',index=False)  
    
    
 
def createTable2(dates,ini_file='model_ini.ini'):
    '''
    

    Parameters
    ----------
    dates : TYPE
        DESCRIPTION.
    observedDf : TYPE
        DESCRIPTION.

    Returns
    -------
    -9 padded dataframe for observation locations.

    '''
    config = configparser.ConfigParser()
    config.read(ini_file)
    
    file_obs_locs = config.get('input files','fileObsLocs')
    
    ar_obs_names, ar_obs_coorx, ar_obs_coory = read_obs_params(file_obs_locs)
    
    #create dataframe
    table = pd.DataFrame(dates)
    for name in ar_obs_names:
        table[name]=-9
        
    
    return table
    
    


