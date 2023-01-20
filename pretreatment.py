#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Fri Dec  9 08:03:33 2022

@author: justinpringle
functions to pretreat the data, load grids and inputs etc
"""
import numpy as np

############
# the grid #
############

def read_global_params(fileName):
    '''
    Read the file that specifies the parameters of the model, which
    are globally applied to all cells in the model.

    Parameters
    ----------
    fileName : string
        Full name of the parameter file (incl. path)
    
    Returns
    ----------
    Cac: float
        wind reduction coeff.
    Td: float
        decay time 
        (hr)
    '''
    file_read = open(fileName,'r')
    tab_read = file_read.readlines()
    #first row contains var names
    for line in tab_read[1::]:
        temp = line.split()
        Cac = float(temp[0])
        Td = float(temp[1])
        dT = float(temp[2])
        
    return Cac,Td,dT
    
def read_grid(fileName):
    '''
    Read the grid into various arrays
    
    Parameters
    ----------
    fileName: string
        full name of the grid file incl path
        
    Returns
    -------
    ar_cell_label: (N,) int array
        labels for each cell
    ar_coorx: (N,) float array
        x coords for each cell centre
        Longitude in UTM proj
    ar_coory: (N,) float array
        y coords for each cell centre
        Lattitude in UTM proj   
    ar_bearing: (N,) float array
        bearing of cell relative to True North
        degrees
    ar_length: (N,)
        length of cell
        meters
        
    '''
    
    tab_read = np.genfromtxt(fileName, delimiter=',',skip_header=1)
    ar_cell_label = np.array(tab_read[:,0],int)
    ar_cell_coorx = np.array(tab_read[:,1],float)
    ar_cell_coory = np.array(tab_read[:,2],float)
    ar_cell_length = np.array(tab_read[:,3],float)
    ar_cell_bearing = np.array(tab_read[:,4],float)
    
    return ar_cell_label, ar_cell_coorx, ar_cell_coory, ar_cell_length,ar_cell_bearing

def read_input(fileName):
    '''
    Read the grid into various arrays
    
    Parameters
    ----------
    fileName: string
        full name of the grid file incl path
        
    Returns
    -------
    ar_in_names: (M,) string array
    ar_in_coorx: (M,) float array
        x coords for each input
        Longitude in UTM proj
    ar_in_coory: (M,) float array
        y coords for each input
        Lattitude in UTM
    ar_in_catch: (M,) float array
        catchment area for each outfall
        m^2
    '''
    #I'm using strings here to include names of the inputs
    tab_read=np.genfromtxt(fileName,delimiter=',',skip_header=1,
                            dtype='|U12',autostrip=True)
    ar_in_names = np.array(tab_read[:,1])
    ar_in_coorx = np.array(tab_read[:,2],float)
    ar_in_coory = np.array(tab_read[:,3],float)
    ar_in_catch = np.array(tab_read[:,4],float)
    ar_in_qFac = np.array(tab_read[:,5],float)
    ar_in_mean_ecoli = np.array(tab_read[:,6],float)
    ar_in_std_ecoli = np.array(tab_read[:,7],float)
    ar_in_bflow = np.array(tab_read[:,8],float)
    
    return ar_in_names, ar_in_coorx, ar_in_coory, \
        ar_in_catch, ar_in_qFac,ar_in_mean_ecoli, ar_in_std_ecoli, ar_in_bflow
    
def read_init(fileName):
    '''
    

    Parameters
    ----------
    fileName : string
        full name of initial condition file.

    Returns
    -------
    ar_init_conc : array (N,)

    '''
    tab_read = np.genfromtxt(fileName, delimiter=',',skip_header=1)
    ar_init_conc = np.array(tab_read[:,1])
    
    return ar_init_conc
    
def read_weather(fileName):
    '''
    reads weather csv file and converts to usuable array with time step dT

    Parameters
    ----------
    filename : string
        full name of weather file incl path.
    

    Returns
    -------
    ar_rain: (N,) float array
        rainfall in mm
        N is number of time steps
    ar_wind: (N,) float array
        wind speed in m/s
        N is the number of time steps
    ar_wDir: (N,) float array
        wind direction in degrees TN
    ar_year
    ar_month
    ar_day
    ar_hour
    '''
    
    tab_read = np.genfromtxt(fileName, delimiter=',',skip_header=1)
    ar_rain = np.array(tab_read[:,6])
    ar_wind_spd = np.array(tab_read[:,4])
    ar_wind_dir = np.array(tab_read[:,5])
    
    return ar_rain, ar_wind_spd, ar_wind_dir

def read_river(fileName):
    '''
    

    Parameters
    ----------
    fileName : string
        full file name of river data.

    Returns
    -------
    ar_river: (N,) float array
        umgeni data at dT

    '''
    tab_read = np.genfromtxt(fileName, delimiter=',',skip_header=1)
    ar_river = np.array(tab_read[:,4])
    
    return ar_river

def read_obs_vals(fileName):
    '''
    

    Parameters
    ----------
    fileName : string
        full file name of the observational data.

    Returns
    -------
    ar_obs_vals

    '''
    tab_read = np.genfromtxt(fileName, delimiter=',',skip_header=1)
    ar_obs_vals=tab_read[:,4::]
    
    return ar_obs_vals

def read_obs_params(fileName):
    '''
    
    read the param file that stores the observations and there locs
    
    Parameters
    ----------
    fileName : string
        full file name of the observational data.

    Returns
    -------
    ar_obs_names
    ar_obs_coorx
    ar_obs_coory

    '''
    tab_read=np.genfromtxt(fileName,delimiter=',',skip_header=1,
                            dtype='|U12',autostrip=True)
    ar_obs_names = np.array(tab_read[:,1])
    ar_obs_coorx = np.array(tab_read[:,2],float)
    ar_obs_coory = np.array(tab_read[:,3],float)
    
    return ar_obs_names, ar_obs_coorx, ar_obs_coory
