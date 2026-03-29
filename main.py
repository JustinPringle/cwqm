#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Mon Dec  5 20:41:55 2022

@author: justinpringle
This is the main code

1. gather data
2. get forecast
3. generate weather input
4. generate umgeni flows
"""
import logging
import os
import numpy as np
import sys
from forcingSort import get_gfs
import obscape
from urllib.request import urlopen
from urllib.error import URLError, HTTPError
import subprocess
import pandas as pd
import processObs
import utils
import datetime as dt
import postTreatment
import res_plot
from pretreatment import read_obs_params
import configparser

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s %(name)s: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
)
logger = logging.getLogger(__name__)

config = configparser.ConfigParser()
config.read('model_ini.ini')
file_obs_locs = config.get('input files','fileObsLocs')
# import model

#get gfs and obscape
logger.info('Fetching GFS forecast data')
gfsDf = get_gfs()
now = dt.datetime.now()
_from = now-dt.timedelta(days=60)
logger.info('Fetching obscape weather observations')
obsDf = obscape.getData(now,_from)

#now merge the observed with forecast data

#note the times here are in UTC so I must change them to Africa/Johannesburg 
# before the model is run
#%%
weatherMerged = obsDf.merge(gfsDf,
                            on=['datetime','wind_speed','rain','direction'],
                            how='outer')

#save as a csv
#set timezone
weatherMerged['datetime'] = weatherMerged['datetime'].map(lambda x: x.tz_convert('Africa/Johannesburg'))

weatherMerged['year'] = weatherMerged['datetime'].dt.year
weatherMerged['month'] = weatherMerged['datetime'].dt.month
weatherMerged['day'] = weatherMerged['datetime'].dt.day
weatherMerged['hour'] = weatherMerged['datetime'].dt.hour

weatherMerged[['year','month','day','hour','wind_speed','direction','rain']].to_csv('forcing/weather.csv',index=False)

#get umgeni flows
umgeniDf = utils.umgeniFlows(weatherMerged)
umgeniDf['year'] = umgeniDf['datetime'].dt.year
umgeniDf['month'] = umgeniDf['datetime'].dt.month
umgeniDf['day'] = umgeniDf['datetime'].dt.day
umgeniDf['hour'] = umgeniDf['datetime'].dt.hour

#save as csv
umgeniDf[['year','month','day','hour','flow']].to_csv('forcing/umgeni_flow.csv')

#%%
#process the observations
# ar_obs_names, ar_obs_coorx, ar_obs_coory = read_obs_params(file_obs_locs)
ecoliPadded = processObs.createTable2(weatherMerged['datetime']).set_index('datetime')
obsNames = list(ecoliPadded.columns)
try:
    ecoliDf = processObs.queryDB(_from)
    ecoliDf['datetime']=ecoliDf['datetime'].map(lambda x: x.tz_localize('Africa/Johannesburg'))
    ecoliDf = ecoliDf.pivot(index='datetime', columns=['beach'],values='ecoli').rename_axis(None,axis=1)
    #patch the observations
    mergedEcoli = ecoliDf.combine_first(ecoliPadded)
    # combine_first can leave NaN where the DB had data for some beaches
    # but not others at a given timestamp. Replace with -9 (missing convention).
    mergedEcoli[obsNames] = mergedEcoli[obsNames].fillna(-9.0)
except (ValueError, KeyError) as exc:
    logger.warning('No usable observations from DB (%s); proceeding without.', exc)
    mergedEcoli=ecoliPadded

mergedEcoli['year'] = mergedEcoli.index.year
mergedEcoli['month'] = mergedEcoli.index.month
mergedEcoli['day'] = mergedEcoli.index.day
mergedEcoli['hour'] = mergedEcoli.index.hour
#save to csv
##reanrange columns
cols = list(mergedEcoli.columns.values)
cols = cols[-4::]+obsNames
mergedEcoli[cols].to_csv('observations/observations.csv',index=False)

#%%
logger.info('Starting model run')
##### NOW TO THE MODEL ########
import model
#~~~~ read hotstart files ~~~~#
P = np.loadtxt('start_files/p.out')
#read the previous model run and extract C's from this current model start date
cDf =pd.read_csv('start_files/C.csv')
#get start date and load C values at this time
startDate = weatherMerged['datetime'][0].to_pydatetime().strftime('%Y-%m-%d %H:%M:%S+02:00')
# save this to init_c
# cDf['dates']=cDf.index.to_pydatetime()
cDf = cDf.set_index('datetime')
cDf_start = cDf[cDf.index == startDate]
if len(cDf_start) > 0:
    logger.info('Hot-start: loaded saved state for %s', startDate)
    cDf_start.to_csv('start_files/init_c.csv', index=False)
else:
    logger.warning('Start date %s not found in C.csv — keeping existing init_c.csv', startDate)

results = model.run()



#%%
###### Save the model covariance matrix######
np.savetxt('start_files/p.out',results['P_final'],fmt='%.3f')

##### Save final C's
dates = weatherMerged['datetime']
C = results['X'][:-1]
columns = ['%i'%i for i in range(C.shape[1])]
cDfnew = pd.DataFrame(C,columns=columns)
cDfnew=cDfnew.set_index(dates)

#melt the df and save
cDfNewMelt = cDfnew.melt(value_name='ecoli',ignore_index=False)
cDfNewMelt.to_csv('start_files/C.csv',float_format='%.3f')

### POST to SQL
logger.info('Writing results to database')
con = postTreatment.create_con()
postTreatment.create_sql_table_result(C, con,db='WQ2')

ret = os.system('cd /var/www/html/php/ && php wqJSON_generator.php')
if ret != 0:
    logger.warning('PHP JSON generator exited with code %d', ret)

url = 'https://justinpringle.com/woza_ewandle/createJSON/wqJSON_generator.php'
try:
    response = urlopen(url, timeout=30)
    logger.info('JSON generator URL responded with status %s', response.status)
except HTTPError as exc:
    logger.error('JSON generator URL returned HTTP %d: %s', exc.code, exc.reason)
except URLError as exc:
    logger.error('Failed to reach JSON generator URL: %s', exc.reason)
# con.close()












