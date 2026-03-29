#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Sun Mar 29 15:33:46 2026

@author: justinpringle
"""

import pandas as pd
import matplotlib.pyplot as plt
import numpy as np



#import beaches

histDF = pd.read_csv('results_historical/wq_by_beach.csv',index_col='datetime')
histDF.index = pd.to_datetime(histDF.index)

obsDf = pd.read_csv('observations/observations.csv',na_values=-9)

obsDf['dtindex']=pd.to_datetime(obsDf[['year', 'month', 'day', 'hour']])
obsDf.set_index('dtindex', inplace=True)
obsDf.drop(['year', 'month', 'day', 'hour'], axis=1, inplace=True)

beach='north'

ecoli_to_plot = histDF[histDF.beach==beach]

rain_to_plot = ecoli_to_plot.resample('D').sum().rain

obs_to_plot = obsDf[beach]


tab_col=['k','r']
tab_style=['-','-']
tab_width=['1','1']
color_P='b'
color_ob='k'
transparency_P=0.5
delta = 1

fig,ax = plt.subplots()
ax.set_title('%s Beach'%beach.capitalize())
ax.set_ylabel(r'eColi $(cfu/100ml)$', fontsize=18, fontfamily='Helvetica Neue',
              color=tab_col[-1])
ax.plot(ecoli_to_plot.index, ecoli_to_plot.ecoli_cfu,
        color=tab_col[-1],
        linestyle=tab_style[-1], linewidth=tab_width[-1])
# ax.set_yscale('log')
# ax.set_xticklabels(ax.get_xticks(), rotation = 45)

fig.autofmt_xdate(bottom=0.2, rotation=30, ha='right')

ax.scatter(obs_to_plot.index, obs_to_plot,s=50,facecolors='none',edgecolor='k')
# ax.bar(dates[0:X.shape[0]], obs[0:X.shape[0]], width=delta*24,
#         facecolor=color_ob, edgecolor=color_ob, alpha=transparency_P)

ax2 = ax.twinx()

ax2.set_ylabel(r'$Rainfall \ (mm)$', fontsize=18, color=color_P)
ax2.bar(rain_to_plot.index, rain_to_plot, width=delta,
        facecolor=color_P, edgecolor=color_P, alpha=transparency_P)
ax2.set_ylim(max(rain_to_plot)*2, min(rain_to_plot))

plt.show()
