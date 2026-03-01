#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Fri Dec  9 07:46:50 2022

@author: justinpringle
utility functions
"""
import numpy as np
import pandas as pd
from typing import Tuple


def getDist(x1: float, y1: float, x2: float, y2: float) -> float:
    '''
    Compute Euclidean distance between two points.

    Parameters
    ----------
    x1, y1 : float
        Coordinates of the first point.
    x2, y2 : float
        Coordinates of the second point.

    Returns
    -------
    float
        Distance between the two points.
    '''
    dist = np.sqrt((x2-x1)**2+(y2-y1)**2)
    return dist


def findCellID(ar_cell_label: np.ndarray, XIn: float, YIn: float,
               ar_coorx: np.ndarray, ar_coory: np.ndarray) -> int:
    '''
    Find the cell ID whose centre is closest to (XIn, YIn).

    Parameters
    ----------
    ar_cell_label : array (N,) int
        Cell IDs.
    XIn : float
        X coordinate of the query point (UTM, metres).
    YIn : float
        Y coordinate of the query point (UTM, metres).
    ar_coorx : array (N,) float
        X coordinates of cell centres (UTM, metres).
    ar_coory : array (N,) float
        Y coordinates of cell centres (UTM, metres).

    Returns
    -------
    int
        Label of the nearest cell.

    Raises
    ------
    ValueError
        If no cell centre is within one cell-length of (XIn, YIn).
    '''
    nCells = len(ar_cell_label)
    dX = ar_coorx[1]-ar_coorx[0]
    dY = ar_coory[1]-ar_coory[0]
    #length of cell
    dC = np.sqrt(dX**2+dY**2)

    cellPos = None
    for i in range(nCells):
        dist = getDist(XIn, YIn, ar_coorx[i], ar_coory[i])
        if dist < dC:
            cellPos = ar_cell_label[i]

    if cellPos is None:
        raise ValueError(
            'No cell found within one cell-length of (%.1f, %.1f).' % (XIn, YIn)
        )
    return cellPos

def getWindAdv(ar_cell_label: np.ndarray, ar_cell_bearing: np.ndarray,
               ar_cell_length: np.ndarray, wind_spd: float,
               wind_dir: float) -> Tuple[np.ndarray, np.ndarray]:
    '''
    Project wind velocity onto each cell's along-cell direction.

    Parameters
    ----------
    ar_cell_label : array (N,)
        Cell IDs.
    ar_cell_bearing : array (N,)
        Bearing of each cell clockwise from True North (degrees).
    ar_cell_length : array (N,)
        Length of each cell (metres); used to compute the projection.
    wind_spd : float
        Wind speed (m/s).
    wind_dir : float
        Wind direction relative to True North (degrees, meteorological
        convention — direction wind is coming *from*).

    Returns
    -------
    ar_wind_flag : array (N,)
        +1 where wind has a positive along-cell component (S→N),
        -1 where it has a negative component, 0 when wind is calm.
    ar_wind_along_cell : array (N,)
        Magnitude of the wind projection onto each cell (m/s).
    '''
    #get math wind direction (anticlockwise from positive x axis)
    #change wind vector to be pointing IN the direction the wind is going i.e. add 180 degrees
    wd_going_to_r = np.radians(270-wind_dir)

    #convert to vector as W = [x,y]
    W = wind_spd*np.array([np.cos(wd_going_to_r),np.sin(wd_going_to_r)])

    ar_wind_along_cell = []
    ar_wind_flag = []
    for cell in range(len(ar_cell_label)):
        # get the bearing, convert to math degrees
        bear_r = np.radians(90-ar_cell_bearing[cell])

        # convert cell to vector [x,y]
        C = ar_cell_length[cell]*np.array([np.cos(bear_r),np.sin(bear_r)])

        # calc projection using dot product: W_proj = (C·W / C·C) * C
        W_proj = np.dot(C,W)/np.dot(C,C)*C
        ar_wind_along_cell.append(np.linalg.norm(W_proj))

        # calc sign: +1 or -1 as W_proj·C / (||W_proj|| ||C||)
        # Guard against zero wind projection to avoid division by zero.
        norm_proj = np.linalg.norm(W_proj)
        if norm_proj == 0:
            flag = 0.0
        else:
            flag = np.round(np.dot(W_proj,C)/norm_proj/np.linalg.norm(C))
        ar_wind_flag.append(flag)

    return np.asarray(ar_wind_flag), np.asarray(ar_wind_along_cell)
    

def umgeniFlows(weatherDf: pd.DataFrame, period: str = 'monthly') -> pd.DataFrame:
    '''
    Estimate Umgeni River flow combining Mardon (2003) monthly base flows
    with a rational-method storm-flow contribution.

    Parameters
    ----------
    weatherDf : pd.DataFrame
        Must contain columns 'datetime' (timezone-aware) and 'rain' (mm/hr).
    period : str, optional
        Reserved for future sub-monthly modes. Default is 'monthly'.

    Returns
    -------
    pd.DataFrame
        Columns: 'datetime', 'flow' (m³/s).
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
        
        
        
     
        
        
        
        
        
        
        
        
        
    
    