#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Thu Dec 22 07:53:40 2022

@author: justinpringle

here I do some post work on my results
"""
import numpy as np
import pandas as pd
import configparser
# import utm
# import sqlite3
# from mysql.connector import connection
# import pymysql
import sqlalchemy
# import sys
# sys.path.append('../scripts')
from pretreatment import read_weather
from pretreatment import read_grid
from pretreatment import read_obs_params
import utils as ut
import datetime as dt

def gatherObsFile(ini_file='model_ini.ini'):
    '''
    

    Parameters
    ----------
    ini_file : String, optional
        DESCRIPTION. The default is 'model_ini.ini'.

    Returns
    -------
    obslocs dataframe.

    '''
    #link to ini file
    config = configparser.ConfigParser()
    config.read(ini_file)
    file_obs_locs = config.get('input files','fileObsLocs')
    
    #open obs as df
    df = pd.read_csv(file_obs_locs)
    
    return df

def createSQL_db(obsDF,con):
    '''
    creates an sqlite db

    Parameters
    ----------
    df : TYPE
        DESCRIPTION.

    Returns
    -------
    None.

    '''
    
    #add latlon in degs
    obsDegs = utm.to_latlon(obsDF['X'],obsDF['Y'],36,northern=False)
    
    obsDF['LAT']=obsDegs[0]
    obsDF['LON']=obsDegs[1]
    
    obsDF = obsDF.rename(columns={'name':'beach'})
    
    #get obsCols
    obsCols = obsDF.columns
    
    
    #create a db
    # conn = sqlite3.connect('CWQM.db')
    obsDF.to_sql(name='beachLocs',con=con,if_exists='replace')
    # conn.close()
    # c = conn.cursor()
    #create the beach locs table
    # c.execute('CREATE TABLE IF NOT EXISTS beachLocs \
    #           (id , price number)')

# E. coli thresholds (CFU/100 mL) for beach water quality classification.
_WQ_GOOD_THRESHOLD = 250
_WQ_ACCEPT_THRESHOLD = 500


def _replaceitem(x):
    if x < _WQ_GOOD_THRESHOLD:
        return 'Good'
    elif x < _WQ_ACCEPT_THRESHOLD:
        return 'Accept'
    else:
        return 'Bad'

def create_sql_table_result(res_array,con,ini_file='model_ini.ini',db='WQ'):
    '''
    

    Parameters
    ----------
    res_array : TYPE
        DESCRIPTION.
    con : TYPE
        DESCRIPTION.

    Returns
    -------
    None.

    '''
    
    
    # get observations
    config = configparser.ConfigParser()
    config.read(ini_file)
    file_weather_forcing =  config.get('input files', 'fileWeatherForcing')
    file_grid =  config.get('input files', 'fileGrid')
    file_obs_locs = config.get('input files','fileObsLocs')
    ####################
    #
    ####################
    #get weather data, obs info, grid and create dates
    ar_cell_label, ar_cell_coorx, \
        ar_cell_coory, ar_cell_length, \
        ar_cell_bearing = read_grid(file_grid)
        
    ar_rain, ar_wind_spd, ar_wind_dir = read_weather(file_weather_forcing)
    
    ar_obs_names, ar_obs_coorx, ar_obs_coory = read_obs_params(file_obs_locs)
    
    tab_read_dates = np.genfromtxt(file_weather_forcing, delimiter=',',skip_header=1,
                                   dtype=int)
    ar_dates = tab_read_dates[:,0:4]
    
    #######################
    #create a datetime list
    #######################
    dates = [dt.datetime(yr,mn,dy,hr) for yr,mn,dy,hr in ar_dates]
    
    ######################
    # get length of result
    #####################
    resStop = len(res_array)
    
    emptyD = {'datetime':[],
              'beach':[],
              'wq':[]}
    
    num_obs = len(ar_obs_names)
    
    for i in range(num_obs):
        #get cell id
        cellID_obs = ut.findCellID(ar_cell_label, ar_obs_coorx[i], 
                                   ar_obs_coory[i], ar_cell_coorx, \
                                       ar_cell_coory)-1
        xData = res_array[:,cellID_obs]
        xNew = map(_replaceitem,xData)
        datesData = dates[0:resStop]
        beachData = [ar_obs_names[i] for j in range(resStop)]
        
        emptyD['datetime'].extend(datesData)
        emptyD['beach'].extend(beachData)
        emptyD['wq'].extend(xNew)
        # emptyD['wqV'].extend(xData)
        
    
    df = pd.DataFrame.from_dict(emptyD)
    df['Year'] = df['datetime'].dt.year
    df['Month'] = df['datetime'].dt.month
    df['Day'] = df['datetime'].dt.day
    df['Hour'] = df['datetime'].dt.hour
    df[['beach','wq']] = df[['beach','wq']].values.astype(str)
    
    
    # con_db = con.connect()
    
    df[['datetime','Year','Month','Day','Hour','wq','beach']].to_sql(name=db,con=con,if_exists='replace')
    
    # con_db.close()
    # return df



def create_con():
    '''
    

    Returns
    -------
    None.

    '''
               
    database_username = 'justiixl'
    database_password = '6bZ+e-aU(G-V'
    database_ip       = 'justinpringle.com'
    database_name     = 'justiixl_CWQM'
    database_connection = sqlalchemy.create_engine('mysql+mysqlconnector://{0}:{1}@{2}:3306/{3}'.
                                                    format(database_username, database_password, 
                                                          database_ip, database_name))
    
    return database_connection
    
    
    
    #create an empty dict
    #loop over observations and get data and append to list
    
    #
# df = gatherObsFile()
# dfR = create_sql_table_result(results['X'], 'a')


# mydb = connection.MySQLConnection(
#   host="https://wwww.justinpringle.com",
#   user="justiixl",
#   password="6bZ+e-aU(G-V",
#   database="justiixl_CWQM"
# )

# mydb = {
#   'host':"https://wwww.justinpringle.com",
#   'username':"justiixl",
#   'password':"6bZ+e-aU(G-V",
#   'database':"justiixl_CWQM"
# }

# database_username = 'justiixl'
# database_password = '6bZ+e-aU(G-V'
# database_ip       = 'justinpringle.com'
# database_name     = 'justiixl_CWQM'
# database_connection = sqlalchemy.create_engine('mysql+mysqlconnector://{0}:{1}@{2}:3306/{3}'.
#                                                format(database_username, database_password, 
#                                                       database_ip, database_name))

# createSQL_db(df,database_connection)
# database_connection.close()
# print(mydb)



















