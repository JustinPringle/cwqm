#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Fri Dec  9 07:46:50 2022

@author: justinpringle
utility functions
"""
import numpy as np
import pandas as pd

def getDist(x1,y1,x2,y2):
    '''
    compute distance between two points
    '''
    dist = np.sqrt((x2-x1)**2+(y2-y1)**2)
    return dist

def findCellID(ar_cell_label,XIn,YIn,ar_coorx,ar_coory):
    '''
    finds the cell ID closest to (XIn, YIn)
    
    ar_cell: (N,) int array
        contains cell IDs
    ar_coorx: (N,) float array
        contains x co-ordinate of each cell (m)
        Longitude expressed in UTM projection
    ar_coory: (N,) float array
        contains y co-ordinate of each cell (m)
        Lattitude expressed in UTM projection
    XIn: float
        contains x co-ord for inputs
        Longitude expressed in same proj as ar_coorx
    YIn: float
        contains y co-ord for inputs
        Lattitude expressed in same proj as ar_coorx
    '''
    
    nCells = len(ar_cell_label)
    dX = ar_coorx[1]-ar_coorx[0]
    dY = ar_coory[1]-ar_coory[0]
    #length of cell
    dC = np.sqrt(dX**2+dY**2)
    
    for i in range(nCells):
        dist = getDist(XIn, YIn, ar_coorx[i], ar_coory[i])
        
        if dist<dC:
            cellPos = ar_cell_label[i]
            
    return cellPos

def getWindAdv(ar_cell_label,ar_cell_bearing,ar_cell_length,wind_spd,wind_dir):
    '''
    

    Parameters
    ----------
    ar_cell_label : array (N,)
        cell ID's.
    ar_cell_bearing : array(N,)
        bearing of all the cells clockwise from North.
    ar_cell_len : array (N,)
        length of each cell
        used to calculate the projection of wind on sp(cell).
    wind_spd : float
        wind speed in m/s.
    wind_dir: float
        wind direction relative to true north

    Returns
    -------
    ar_wind_along_cell: array (N,)
        projection of the wind on the sp(cell)
    
    ar_wind_flag: array(N,)
        1 for positive defined wind direction
        -1 for negative defined wind direction
        default +: from South to North

    '''
    
    #get math wind direction (anticlockwise from positive x axis)
    #change wind vector to be pointing IN the direction the wind is going i.e. add 180 degrees
    
    wd_going_to_r = np.radians(270-wind_dir)   
    
    #convert to vector as W = [x,y]
    W = wind_spd*np.array([np.cos(wd_going_to_r),np.sin(wd_going_to_r)])
    
    #stor empty list
    ar_wind_along_cell = []
    ar_wind_flag=[]
    #for each cell
    for cell in range(len(ar_cell_label)):
    # get the bearing, convert to math degrees 
        bear_r = np.radians(90-ar_cell_bearing[cell])
        
    #convert to cell (C) to vector [x,y]
        C = ar_cell_length[cell]*np.array([np.cos(bear_r),np.sin(bear_r)])
        
    #calc projection using dot product as W_proj = C.W/C.C*C
        W_proj = np.dot(C,W)/np.dot(C,C)*C
        ar_wind_along_cell.append(np.linalg.norm(W_proj))
    #calc +1 or -1 as W_proj.C/(||W_proj||||C||)
        flag = np.round(np.dot(W_proj,C)/np.linalg.norm(W_proj)/np.linalg.norm(C))
        ar_wind_flag.append(flag)
    
    return np.asarray(ar_wind_flag),np.asarray(ar_wind_along_cell)
    

def umgeniFlows(weatherDf,period='monthly'):
    '''
    use monthly base flows from Mardon (2003) and storm flows

    Parameters
    ----------
    weatherDf : dataframe 
        containing weather data.
    period : TYPE, optional
        DESCRIPTION. The default is 'monthly'.

    Returns
    -------
    None.

    '''
    dates = weatherDf['datetime']
    rain = weatherDf['rain'].values
    monthlyFlows = {
        'Jan':15,
        'Feb':28,
        'Mar':24,
        'Apr':14,
        'May':4,
        'Jun':3,
        'Jul':5,
        'Aug':3,
        'Sep':3,
        'Oct':4,
        'Nov':5,
        'Dec':8
        }
    
    A = 340 #km2 -> 10000m2 in 1km2, 3600s in hr, 1000mm in m.... 1/360*Q[m3/s] = CI[1/1000*1/3600]A[10000]
    C = 0.1
    alpha=0.01
    flowStor=[]
    bStor = []
    for dat,r in zip(dates,rain):
        #get month as string and get base flow
        mn = dat.strftime('%b')
        bFlow = monthlyFlows[mn]
        
        Q = C*r*A/3.6
        
        # flow = bFlow+Q
        flowStor.append(Q)
        bStor.append(bFlow)
        
    
    #smooth baseflow
    bFlowS = [bStor[0]]# = np.asarray(bStor)
    for i in range(1, len(bStor)):
        smooth = alpha * bStor[i - 1] + (1 - alpha) * bFlowS[i - 1]
        bFlowS.append(smooth)
    
    flowStor=np.asarray(bFlowS)+np.asarray(flowStor)
    
    df = pd.DataFrame(data={
        'datetime':weatherDf['datetime'],
        'flow':flowStor})
    
    return df
        
        
        
     
        
        
        
        
        
        
        
        
        
    
    