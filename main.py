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
import numpy as np
import sys
from forcingSort import get_gfs
import obscape
import subprocess
import pandas as pd
import processObs
import utils
import datetime as dt
import postTreatment
import res_plot
# import model

#get gfs and obscape
gfsDf = get_gfs()
now = dt.datetime.now()
_from = now-dt.timedelta(days=30)
obsDf = obscape.getData(now,_from)

#now merge the observed with forecast data

#note the times here are in UTC so I must change them to Africa/Johannesburg 
# before the model is run
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

#process the observations
ecoliPadded = processObs.createTable2(weatherMerged['datetime']).set_index('datetime')
try:
    ecoliDf = processObs.queryDB(_from)
    ecoliDf['datetime']=ecoliDf['datetime'].map(lambda x: x.tz_localize('Africa/Johannesburg'))
    ecoliDf = ecoliDf.pivot(index='datetime', columns=['beach'],values='ecoli').rename_axis(None,axis=1)
    
    
    
    #patch the observations
    mergedEcoli = ecoliDf.combine_first(ecoliPadded)#,
except ValueError:
    print('no observations... moving on')    
    mergedEcoli=ecoliPadded

mergedEcoli['year'] = mergedEcoli.index.year
mergedEcoli['month'] = mergedEcoli.index.month
mergedEcoli['day'] = mergedEcoli.index.day
mergedEcoli['hour'] = mergedEcoli.index.hour
#save to csv
##reanrange columns
cols = list(mergedEcoli.columns.values)
cols = cols[-4::]+cols[0:-4]
mergedEcoli[cols].to_csv('observations/observations.csv',index=False)

#%%
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
cDf[cDf.index==startDate].to_csv('start_files/init_c.csv',index=False)

results = model.run()




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

con = postTreatment.create_con()
# postTreatment.create_sql_table_result(C, con,db='WQ2')
# con.close()












