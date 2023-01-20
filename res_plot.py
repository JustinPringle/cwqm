#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Tue Dec 13 22:35:04 2022

@author: justinpringle
"""
import numpy as np
from scipy.linalg import expm
import configparser
import json
import sys
sys.path.append('../scripts')
from pretreatment import read_global_params
from pretreatment import read_grid
from pretreatment import read_input
from pretreatment import read_weather
from pretreatment import read_river
from pretreatment import read_obs_vals
from pretreatment import read_obs_params
from pretreatment import read_init
import utils as ut
from tqdm import tqdm
import time
import copy
import datetime as dt
import matplotlib.pyplot as plt
from matplotlib.dates import date2num
from matplotlib.colors import LinearSegmentedColormap
import matplotlib.colors as colors
import contextily as cx
import geopandas as gp
import utm
import pandas as pd


def convertRainToDays(dates,rain):
    '''
    

    Parameters
    ----------
    dates : TYPE
        DESCRIPTION.
    rain : TYPE
        DESCRIPTION.

    Returns
    -------
    rDates
    dRain : daily rain

    '''
    newDf = pd.DataFrame({'rain':rain},index=dates)
    
    nnewdf = newDf.resample('D').sum()
    
    rDates = np.asarray([dt.date(i.year,i.month,i.day) for i in nnewdf.index])
    dRain = nnewdf.rain.values
    
    return rDates,dRain

def plot_obs_pred(obs_location,X,ini_file='model_ini.ini'):
    '''
    

    Parameters
    ----------
    obs_location : TYPE
        DESCRIPTION.
    X : TYPE
        DESCRIPTION.
    ini_file : TYPE, optional
        DESCRIPTION. The default is 'model_ini.dat'.

    Returns
    -------
    None.

    '''
    tab_col=['k','r']
    tab_style=['-','-']
    tab_width=['1','1']
    color_P='b'
    color_ob='k'
    transparency_P=0.5
    
    nb_cells = X.shape[1]
    config = configparser.ConfigParser()
    config.read(ini_file)
    
    #input params
    file_params = config.get('input files', 'fileParams')
    file_grid =  config.get('input files', 'fileGrid')
    file_init_conc = config.get('input files','fileInitC')
    file_weather_forcing =  config.get('input files', 'fileWeatherForcing')
    file_inputs =  config.get('input files', 'fileInputs')
    file_rivers = json.loads(config.get('input files', 'fileRivers'))
    file_obs_locs = config.get('input files','fileObsLocs')
    file_obs_vals = config.get('input files','fileObs')
    
    ar_cell_label, ar_cell_coorx, \
        ar_cell_coory, ar_cell_length, \
        ar_cell_bearing = read_grid(file_grid)
        
    ar_rain, ar_wind_spd, ar_wind_dir = read_weather(file_weather_forcing)
    
    ar_obs_names, ar_obs_coorx, ar_obs_coory = read_obs_params(file_obs_locs)
    #read observations (T,nb_obs_locs)
    ar_obs = read_obs_vals(file_obs_vals)
    nb_obs_locs = len(ar_obs_names)
    D = np.zeros((nb_obs_locs,nb_cells))
    
    for i in range(nb_obs_locs):
        #get obs cell loc
        cellID_obs = ut.findCellID(ar_cell_label, ar_obs_coorx[i], 
                                   ar_obs_coory[i], ar_cell_coorx, ar_cell_coory)
        D[i,cellID_obs-1]=1
    
    
    #pick observation
    ob = obs_location
    i = np.where(ar_obs_names==ob)[0][0]
    cellid = ut.findCellID(ar_cell_label, ar_obs_coorx[i], 
                           ar_obs_coory[i], ar_cell_coorx, ar_cell_coory) -1
    
    obs = np.ma.masked_where(-9,ar_obs[0:X.shape[0],i])
    inds = np.where(obs>0)[0]
    obsToPlot = obs[inds].data
    # print(len(obsToPlot))
    
    pred = X[:,cellid]
    
    
    #could move this to own function
    tab_read_dates = np.genfromtxt(file_weather_forcing, delimiter=',',skip_header=1,
                                   dtype=int)
    ar_dates = tab_read_dates[:,0:4]
    dates = [dt.datetime(yr,mn,dy,hr) for yr,mn,dy,hr in ar_dates]
    
    dates_obs=np.asarray(dates)[inds]
    delta = date2num(dates[1]) - date2num(dates[0])
    
    #convert rain to days
    rDates,rRain = convertRainToDays(dates, ar_rain)
    delta = date2num(rDates[1]) - date2num(rDates[0])
    #get index
    finDate = dates[X.shape[0]]
    finDateStr = dt.datetime.strftime(finDate,'%Y-%m-%d')
    finDateDay = dt.date(finDate.year,finDate.month,finDate.day)
    # print([finDateDay])
    rDate_ind = np.where(rDates==finDateDay)[0][0]
    
    rDate_to_plot = rDates[0:rDate_ind]
    rRain_to_plot = rRain[0:rDate_ind]
    
    fig,ax = plt.subplots()
    
    ax.set_title('%s Beach'%obs_location.capitalize())
    ax.set_ylabel(r'eColi $(cfu/100ml)$', fontsize=18, fontfamily='Helvetica Neue',
                  color=tab_col[-1])
    ax.plot(dates[0:X.shape[0]], pred,
            color=tab_col[-1],
            linestyle=tab_style[-1], linewidth=tab_width[-1])
    # ax.set_yscale('log')
    # ax.set_xticklabels(ax.get_xticks(), rotation = 45)

    fig.autofmt_xdate(bottom=0.2, rotation=30, ha='right')
    
    ax.scatter(dates_obs, obsToPlot,s=50,facecolors='none',edgecolor='k')
    # ax.bar(dates[0:X.shape[0]], obs[0:X.shape[0]], width=delta*24,
    #         facecolor=color_ob, edgecolor=color_ob, alpha=transparency_P)
    
    ax2 = ax.twinx()

    ax2.set_ylabel(r'$Rainfall \ (mm)$', fontsize=18, color=color_P)
    ax2.bar(rDate_to_plot, rRain_to_plot, width=delta,
            facecolor=color_P, edgecolor=color_P, alpha=transparency_P)
    ax2.set_ylim(max(rRain_to_plot)*2, min(rRain_to_plot))
    
    plt.show()
    return ax,cellid
# plot('pirates',X)
    
        
def plot_pred(location,X,ini_file='model_ini.dat'):
    '''
    

    Parameters
    ----------
    location : int
        cell id where we want to plot.
    X : TYPE
        DESCRIPTION.
    ini_file : TYPE, optional
        DESCRIPTION. The default is 'model_ini.dat'.

    Returns
    -------
    None.

    '''
    tab_col=['k','r']
    tab_style=['-','-']
    tab_width=['1','1']
    color_P='b'
    color_ob='k'
    transparency_P=0.5
    
    nb_cells = X.shape[1]
    config = configparser.ConfigParser()
    config.read(ini_file)
    
    #input params
    file_params = config.get('input files', 'fileParams')
    file_grid =  config.get('input files', 'fileGrid')
    file_init_conc = config.get('input files','fileInitC')
    file_weather_forcing =  config.get('input files', 'fileWeatherForcing')
    file_inputs =  config.get('input files', 'fileInputs')
    file_rivers = json.loads(config.get('input files', 'fileRivers'))
    file_obs_locs = config.get('input files','fileObsLocs')
    file_obs_vals = config.get('input files','fileObs')
    
    ar_cell_label, ar_cell_coorx, \
        ar_cell_coory, ar_cell_length, \
        ar_cell_bearing = read_grid(file_grid)
        
    ar_rain, ar_wind_spd, ar_wind_dir = read_weather(file_weather_forcing)
    
    pred = X[:,location]
    #could move this to own function
    tab_read_dates = np.genfromtxt(file_weather_forcing, delimiter=',',skip_header=1,
                                   dtype=int)
    ar_dates = tab_read_dates[:,0:4]
    dates = [dt.datetime(yr,mn,dy,hr) for yr,mn,dy,hr in ar_dates]
    
    delta = date2num(dates[1]) - date2num(dates[0])
    
    fig,ax = plt.subplots()
    
    ax.set_ylabel(r'eColi $(cfu/100ml)$', fontsize=18, fontfamily='Helvetica Neue',
                  color=tab_col[-1])
    ax.plot(dates[0:X.shape[0]], pred,
            color=tab_col[-1],
            linestyle=tab_style[-1], linewidth=tab_width[-1])
    ax.set_yscale('log')
    # ax.set_xticklabels(ax.get_xticks(), rotation = 45)

    fig.autofmt_xdate(bottom=0.2, rotation=30, ha='right')
    
    ax2 = ax.twinx()

    ax2.set_ylabel(r'$Rainfall \ (mm)$', fontsize=18, color=color_P)
    ax2.bar(dates[0:X.shape[0]], ar_rain[0:X.shape[0]], width=delta,
            facecolor=color_P, edgecolor=color_P, alpha=transparency_P)
    ax2.set_ylim(max(ar_rain)*2, min(ar_rain))
    
    plt.show()
    return ax,location
        
        
def map_plot(timS,loc,X,results_ini='results.ini',ini_file='model_ini.dat'):
    '''
    

    Parameters
    ----------
    X : TYPE
        DESCRIPTION.
    results_ini : TYPE, optional
        DESCRIPTION. The default is 'results.ini'.

    Returns
    -------
    None.

    '''
    
    
    font = {
        'size':14,
        'family':'Helvetica Neue'}
    #sort out colours, blue for good, yellow for not so good, red for bad
    good =250
    medium = 500
    colorBounds = [0,250,500,1e7] #3bins blue green red
    colorsL = [(0,0,1),(0,1,0),(1,0,0)]
    #jus directly mapping
    
    norm = colors.BoundaryNorm(boundaries=colorBounds,ncolors=4)
    cmap = LinearSegmentedColormap.from_list('ecoli', colorsL, N=3)   
    
    config = configparser.ConfigParser()
    config.read(results_ini)
    file_shore = config.get('shapefiles', 'file_shoreline')
    
    #create geopandas df
    shp_shore = gp.read_file(file_shore)
    
    #get cell locs
    config.read(ini_file)
    file_grid =  config.get('input files', 'fileGrid')
    file_weather_forcing =  config.get('input files', 'fileWeatherForcing')
    
    
    ar_cell_label, ar_cell_coorx, \
        ar_cell_coory, ar_cell_length, \
        ar_cell_bearing = read_grid(file_grid)
    
    ar_cell_latlon = utm.to_latlon(ar_cell_coorx,ar_cell_coory,36,northern=False)
    
    #read weather
    ar_rain, ar_wind_spd, ar_wind_dir = read_weather(file_weather_forcing)
    
    tab_read_dates = np.genfromtxt(file_weather_forcing, delimiter=',',skip_header=1,
                                   dtype=int)
    ar_dates = tab_read_dates[:,0:4]
    
    dates = [dt.datetime(yr,mn,dy,hr) for yr,mn,dy,hr in ar_dates]
    
    tim = dt.datetime.strptime(timS,'%Y-%m-%d %H:%M:%S')
    ind = dates.index(tim)
    
    wd = ar_wind_dir[ind]
    ws = ar_wind_spd[ind]
    #get arrow
    wd_going_to_r = np.radians(270-wd)   
    
    #convert to vector as W = [x,y]
    W = ws*np.array([np.cos(wd_going_to_r),np.sin(wd_going_to_r)])
    
    mappedColours=[]
    
    for i in X[ind,:]:
        if i<=good:
            mappedColours.append('b')
        elif i>good and i<=medium:
            mappedColours.append('g')
        else:
            mappedColours.append('r')
            
    ar_x = ar_cell_latlon[0]
    ar_y = ar_cell_latlon[1]
    #plot it
    fig,ax=plt.subplots()
    handles, labels = ax.get_legend_handles_labels()
    
    shp_shore.plot(figsize=(10,10),ax=ax,color='k',linewidth=0.5)
    point=ax.scatter(ar_y,ar_x,s=2,c=mappedColours,label='ecoli')
    handles.append(ax.scatter([],[],color='b',s=50))
    handles.append(ax.scatter([],[],color='g',s=50))
    handles.append(ax.scatter([],[],color='r',s=50))
    ax.set_title(timS,fontdict=font)
    
    # Shrink current axis by factor
    box = ax.get_position()
    ax.set_position([box.x0-0.5*box.x0, box.y0, box.width , box.height])
    
    ax.legend(handles,[r'Good 0-250',r'Acceptable 250-500',r'Critical >500'],
              prop=font,
              loc='lower left', bbox_to_anchor=(1, 0.1))
    cx.add_basemap(ax,zoom=12,crs=shp_shore.crs)
    
    ### Add wind
    scFac=0.5
    scFacW=1
    
    #make percentage of fig size
    ax2 = fig.add_axes((0.6,0.5,np.abs(scFac*W[1]/ws),np.abs(scFac*W[0]/ws)),polar=True)
    # ax2.
    ax2.annotate("", xy=(wd_going_to_r, scFac), xytext=(0, 0),
                 #xycoords="axes fraction",
                 arrowprops=dict(facecolor='black', shrink=0.0))
    ax2.set_xticklabels(['E' ,'', 'N', '', 'W', '', 'S', ''])
    ax2.set_yticks([1*scFac])
    ax2.set_yticklabels([r'%.2f$ms^{-1}$'%(ws)])
    # ax2.spines['polar'].set_visible(False)
    # fig.colorbar(cm)
    
        
        
        
        