#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Fri Dec  9 11:25:18 2022

@author: justinpringle
"""
import numpy as np
from scipy.linalg import expm as expm
import configparser
import json
import sys
sys.path.append('../scripts')

# ---------------------------------------------------------------------------
# Model constants
# ---------------------------------------------------------------------------
# Cross-sectional area of each coastal cell (m²). Used in residence-time calc.
CELL_XSECT = 200

# Process noise scaling factor: Q = I * e_load * Q_FAC
Q_FAC = 0.8

# Observation noise scaling factor: R = I * obs * R_FAC
R_FAC = 5000

# E. coli dilution factor applied to river mean loads read from config.
# Divides the raw ecoli_mean values (CFU/100mL) by this factor.
ECOLI_RIVER_SCALE = 250
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


def createA(cell_lengths,w_flag,wind,Cac,Td):
    '''
    

    Parameters
    ----------
    cell_lengths: array (N,)
        array containing N cell lengths and use to calc Volume.
    w_flag : array (N,)
        +1 or -1 based on upcell or down cell advection.
    wind : array (N,)
        wind speed.
    Td: float
        decay time scale
    Cac: float
        wind speed factor

    Returns
    -------
    Matrix A (N,N).

    '''
    nb_cells = len(cell_lengths)
    
    ao = -1/Td
    A = np.diag([ao for i in range(nb_cells)])
    for cell in range(nb_cells):
        Tadv_inv=Cac*wind[cell]/cell_lengths[cell]*3600
        A[cell,cell]-=Tadv_inv
        if w_flag[cell]>0:
            if cell == 0:
                continue
            else:
                A[cell,cell-1]=Tadv_inv#Cac*wind[cell]/cell_lengths[cell]*3600
        
        if w_flag[cell]<0:
            if cell ==nb_cells-1:
                continue
            else:
                A[cell,cell+1]=Tadv_inv#Cac*wind[cell]/cell_lengths[cell]*3600
                
    return A

def createB(Q,cell_lengths,xsect=CELL_XSECT):
    '''
    

    Parameters
    ----------
    Q : array (N,) or (N,nb_rivs)
        array containing flows from SWD or rivers
        If rivers then needs special treatment.
    cell_lengths : array (N,)
        length of each cell.
    xsect : float, optional
        cross sectional area of each cell. The default is 200.

    Returns
    -------
    B: (N,N) or B(N,N,nb_rivs)

    '''
    #check if rivers
    rivFlag = len(Q.shape)
    
    nb_cells = len(cell_lengths)
    
    if rivFlag == 1:
        #we are working with swd flows
        #set an empty list for point source time scales (inverted)
        Tp_inv = []
        for cell in range(nb_cells):
            if Q[cell]==0:
                Tp_inv.append(0)
            else:
                Tp = cell_lengths[cell]*xsect/Q[cell]
                Tp_inv.append(1/Tp)
      
        B = np.diag(Tp_inv)
    else:
        #we have rivers
        nb_rivs = Q.shape[1]
        B = np.zeros((nb_cells,nb_cells,nb_rivs))
        for riv in range(nb_rivs):
            # Tp_inv = []
            for cell in range(nb_cells):
                if Q[cell]==0:
                    Tp_inv=0
                else:
                    Tp = cell_lengths[cell]*xsect/Q[cell]
                    Tp_inv = 1/Tp
            
                B[cell,cell,riv]=Tp_inv
    
    return B

def createH(A,phi,B):
    '''
    

    Parameters
    ----------
    A : array (N,N)
        advection array.
    phi : array (N,N)
        state transition matrix.
    B: array (N,N)
        point source time scales

    Returns
    -------
    H

    '''
    nb_cells = A.shape[0]
    I = np.identity(nb_cells)
    
    h1 = phi-I
    h2 = np.dot(np.linalg.inv(A),h1)
    H = np.dot(h2,B)       
    
    return H

def kf_update(x_,ar_obs_cells,D,P,Q,R,niter=50,mardon_iter=True):
    '''
    

    Parameters
    ----------
    x_ : array (N,)
        contains eColi predictions.
    ar_obs_cells : array (M,)
        contains observations at locations.
    D : array (M,N)
        observation locations in cell coords
    niter : int, optional
        number of iterations for the kalman filter. The default is 50.

    Returns
    -------
    x_updated.
    P

    '''
    nb_cells = len(x_)
    nb_obs = len(ar_obs_cells)
    
    K = np.zeros((nb_cells,nb_obs))
    #use Mardons iterate over observations to avoid negative 
    if mardon_iter:
        for obs in range(D.shape[0]):
            flag=1
            fac=1
            for i in range(niter):
                k1 = np.dot(P,D[obs].T)
                k2 = np.dot(D[obs],np.dot(P,D[obs].T))+R[obs,obs]
                k3 = 1/k2#np.linalg.inv(k2)
    
                K_t = np.dot(k1,k3)
                x_update = x_ + fac*np.dot(K_t,ar_obs_cells[obs]-np.dot(D[obs],x_))
                for xx in x_update:
                    if xx<0:
                        #we must keep looping
                        flag =1
                        fac*=0.8
                        break
                    else:
                        flag=0
                K[:,obs]=K_t[:]
    else:
        k1 = np.dot(P,D.T)
        k2 = np.dot(D,np.dot(P,D.T))+R
        k3 = np.linalg.inv(k2)
        K = np.dot(k1,k3)
        x_update = x_ + np.dot(K,ar_obs_cells-np.dot(D,x_))
        
    Pk = np.dot(np.eye(nb_cells)-np.dot(K,D),P)
    
    return x_update,Pk,K

def run(ini_file='model_ini.ini'):
    '''
    

    Parameters
    ----------
    ini_file : string, filename
        DESCRIPTION. The default is 'model_ini.dat'.

    Returns
    -------
    None.

    '''
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
    file_cov_matrix = config.get('input files','fileCov')
    
    #Pretreament
    Cac,Td,dT = read_global_params(file_params)
    
    ar_cell_label, ar_cell_coorx, \
        ar_cell_coory, ar_cell_length, \
        ar_cell_bearing = read_grid(file_grid)
        
    nb_cells = len(ar_cell_label)
    
    ar_init_concs = read_init(file_init_conc)
    
    
    
    #~~~~~ create Input array ~~~~#
    ar_in_names, ar_in_coorx, ar_in_coory, ar_in_catch, ar_in_qFac, \
        ar_in_mean_ecoli, ar_in_std_ecoli,ar_in_bflow = read_input(file_inputs)
    #1 were there is SWD input eg... [0 0 0 1 0 0 ] 
    U_SWD = np.zeros(len(ar_cell_label))
    e_SWD = np.zeros(len(ar_cell_label))
    e_std_SWD = np.zeros(len(ar_cell_label))
    bflow_SWD = np.zeros(len(ar_cell_label))
    catch_SWD = np.zeros(len(ar_cell_label))
    qFac_SWD = np.zeros(len(ar_cell_label))
    
    for i in range(len(ar_in_names)):
        XIn = ar_in_coorx[i]
        YIn = ar_in_coory[i]
        
        cellNum = ut.findCellID(ar_cell_label, XIn, YIn, ar_cell_coorx, ar_cell_coory)
        U_SWD[cellNum-1]=1
        e_SWD[cellNum-1] = ar_in_mean_ecoli[i]
        e_std_SWD[cellNum-1] = ar_in_std_ecoli[i]
        catch_SWD[cellNum-1]=ar_in_catch[i]
        qFac_SWD[cellNum-1]=ar_in_qFac[i]
        bflow_SWD[cellNum-1]=ar_in_bflow[i]
        
    #~~~~ Read in the weather ~~~~#
    ar_rain, ar_wind_spd, ar_wind_dir = read_weather(file_weather_forcing)
   
    
    #~~~~ Read in river data ~~~#
    #get rivers as list from config file and get number of rivers
    riv_list = json.loads(config.get('rivers','riverList'))
    num_rivs = len(riv_list)
    #create an array (num_rivs,)
    x_river = np.asarray(json.loads(config.get('river locs','X')))
    y_river = np.asarray(json.loads(config.get('river locs','Y')))
    
    e_riv_mean = np.asarray(json.loads(config.get('river e load','ecoli_mean')))/ECOLI_RIVER_SCALE
    e_riv_std = np.asarray(json.loads(config.get('river e load','ecoli_std')))
    
    #use the first list to create a river array
    ar_riv1 = read_river(file_rivers[0])
    ar_rivers = np.zeros((len(ar_riv1),num_rivs))
    ar_e_riv = np.zeros((len(ar_cell_label),num_rivs))
    ar_e_std_riv = np.zeros((len(ar_cell_label),num_rivs))
    U_rivers = np.zeros((len(ar_cell_label),num_rivs))
    
    #loop over rivers and store their data (time,num_rivs)
    for riv in range(num_rivs):
        ar_riv = read_river(file_rivers[riv])
        ar_rivers[:,riv] = ar_riv
        
        
        #get X and Y coords for each river
        cellID_riv = ut.findCellID(ar_cell_label,x_river[riv],
                                   y_river[riv], ar_cell_coorx,
                                   ar_cell_coory)
        U_rivers[cellID_riv-1,riv]=1
        ar_e_riv[cellID_riv-1,riv]=e_riv_mean[riv]
        ar_e_std_riv[cellID_riv-1,riv]=e_riv_std[riv]
    
    #~~~ Format observation ~~~#
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
    
    reset_p = config.getboolean('input files', 'resetP', fallback=False)
    # print(reset_p)
    if reset_p:
        # Initialise P from scratch: P_0 = diag(C0^2), assuming initial
        # error variance proportional to the square of the initial state.
        # Cells with zero concentration get a small default variance (1.0).
        p_diag = np.where(ar_init_concs > 0, ar_init_concs ** 2, 1.0)
        P = np.diag(p_diag)
        print('p starting from scratch')
        np.savetxt('start_files/p_init.out', P, fmt='%.2f')
    else:
        P = np.loadtxt(file_cov_matrix)

    #~~~~ Create a parameter dictionary ~~~~#
    nb_time_steps = ar_rivers.shape[0]
    execParams = {
        'Cac':Cac,
        'Td':Td,
        'dT':dT,
        'C0':ar_init_concs,
        'nb_time_steps':nb_time_steps,
        'U_SWD':U_SWD,
        'in_bflow':bflow_SWD,
        'e_SWD':e_SWD,
        'e_std_SWD':e_std_SWD,
        'catch_SWD':catch_SWD,
        'qFac_SWD':qFac_SWD,
        'U_rivers':U_rivers,
        'nb_rivs':num_rivs,
        'river_flow':ar_rivers,
        'rain':ar_rain,
        'wind':ar_wind_spd,
        'wind_dir':ar_wind_dir,
        'cell_lengths':ar_cell_length,
        'cell_bear':ar_cell_bearing,
        'cell_labels':ar_cell_label,
        'in_mean_ecoli':ar_in_mean_ecoli,
        'in_std_ecol':ar_in_std_ecoli,
        'riv_mean_ecoli':ar_e_riv,
        'riv_std_ecoli':ar_e_std_riv,
        'D':D,
        'ar_obs':ar_obs,
        'P':P
        
        }

    A = _exec(execParams)
    
    return A


    
def _exec(params):
    '''
    

    Parameters
    ----------
    params : Dictionary
        contains keys with values:
            Cac - wind reduction coeff [init value]
            Td - decay time scale [init value]
            dT - time step [hrs]
            U - SWD inputs [(M,) array, M = No of SWDs]
            wind - wind (K,) array, K = No of time steps
            rain - rain intensity mm/hr (K,) array
            cell_lengths - length of the cells used to calc Tadv,Tp
            cell_bearing - bearing clockwise relative to true north

    Returns
    -------
    ar_predictions.

    '''
    #get some initial vals
    nb_time_steps = params['nb_time_steps']
    Cac = params['Cac']
    Td = params['Td']
    dT = params['dT']
    C0 = params['C0']
    wind_spd = params['wind']
    wind_dir = params['wind_dir']
    cell_lengths = params['cell_lengths']
    cell_bearing = params['cell_bear']
    cell_labels = params['cell_labels']
    rain = params['rain']
    nb_cells = len(cell_labels)
    #river flow is an array [T,num_rivs]
    riverQ = params['river_flow']
    nb_rivs = params['nb_rivs']
    U_riv = params['U_rivers']
    e_riv = params['riv_mean_ecoli']
    e_std_riv = params['riv_std_ecoli']
    
    #SWD inputs
    U_SWD = params['U_SWD']
    e_SWD = params['e_SWD']
    e_std_SWD = params['e_std_SWD']
    catch_SWD = params['catch_SWD']
    qFac_SWD = params['qFac_SWD']
    bflow = params['in_bflow']
    
    #Observations
    D = params['D']
    ar_obs_vals = params['ar_obs']
    
    #for each time step (use tqdm for progess bar):
    xk = np.zeros((nb_time_steps+1,nb_cells))
    xk[0,:]=C0
    x_old=copy.deepcopy(C0)
    x_k_no_update = np.zeros((nb_time_steps+1,nb_cells))
    x_k_no_update[0,:]=C0
    
    # P,Q and R init matrices
    P = params['P']
    P_new = copy.deepcopy(P)
    Q_fac = Q_FAC
    R_fac = R_FAC
    alpha=1
    alpha2=1
    for t in tqdm(range(nb_time_steps),
                   ascii=True,desc='Simulation',unit=' step'):
        
    #get cell length
    
    #get wind spd and direction
        ws = wind_spd[t]
        wd = wind_dir[t]
    #project onto cell get flag and speed as arrays (N,)
        w_flag,wsp = ut.getWindAdv(cell_labels,cell_bearing,
                            cell_lengths,ws, wd)
        
        A = createA(cell_labels,w_flag,wsp,Cac,Td)
        
        phi = expm(A*dT)
    #get rainfall
        rn = rain[t]
        Q_SWD = rn*qFac_SWD*catch_SWD/1000 + bflow*3600
    # #get river flow
        rivQ = riverQ[t]
        Q_riv = copy.deepcopy(U_riv)
        for riv in range(nb_rivs):
            Q_riv[:,riv] = U_riv[:,riv]*rivQ[riv]*3600
        
        B_SWD = createB(Q_SWD,cell_lengths)        
        B_rivs = createB(Q_riv,cell_lengths)
        
    #now work out the loads from SWD and Q
        H_SWD = createH(A,phi,B_SWD)
        
        
        if t == 0:
            x = np.dot(phi,C0)
        else:
            #predict x
            
            e_SWD_temp = np.zeros(nb_cells)
            for cell in range(len(e_SWD_temp)):
                if e_SWD[cell]>0:
                    lgn=np.exp(np.random.normal(loc=np.log(e_SWD[cell]),
                                                         scale=np.log(e_std_SWD[cell])))
                    # print(lgn)
                    e_SWD_temp[cell] = lgn
            
            # break
            # break
            x = np.dot(phi,x) + np.dot(H_SWD,e_SWD)
            #create covariance as factor of point source loading
            Q = np.eye(nb_cells)*e_SWD*Q_fac
            #loop over the rivers
            for riv in range(nb_rivs):
                e_riv_temp = e_riv[:,riv]
                e_std_temp = e_std_riv[:,riv]
                e_riv_temp_ar=np.zeros(nb_cells)
                for cell in range(nb_cells):
                    # print(cell)
                    if e_riv_temp[cell]>0:
                        lgn=np.exp(np.random.normal(loc=np.log(e_riv_temp[cell]),
                                                             scale=np.log(e_std_temp[cell])))
                        e_riv_temp_ar[cell] = lgn
                # print(e_riv_temp_ar[cell])
                # break
            # break
                Q+=np.eye(nb_cells)*e_riv_temp
                H_riv = createH(A,phi,B_rivs[:,:,riv])
                x += np.dot(H_riv,e_riv_temp)
            
            x_k_no_update[t+1,:]=x[:]
        # update P use exponential decay weighting
            P_new = alpha*np.dot(phi,np.dot(P_new,phi.T))+Q+(1-alpha)*P_new
        # check for obs — use only valid (> 0, non-NaN) observations
        obs_raw = ar_obs_vals[t,:]
        valid = (~np.isnan(obs_raw)) & (obs_raw > 0)
        if np.any(valid):
            obs = obs_raw[valid]
            D_valid = D[valid, :]
            R = np.eye(len(obs))*obs*R_fac
            x_update,P_new,K_new = kf_update(x,obs,D_valid,P_new,Q,R,mardon_iter=False)
            
            #set new x
            x = alpha2*x_update[:]+(1-alpha2)*x
            # x = kalmanFilt(x,)
            xk[t+1,:]=x
            K_old = copy.deepcopy(K_new)
            # break
        else:
            x = alpha2*x+(1-alpha2)*x_old
            xk[t+1,:] = x
            x_old=copy.deepcopy(x)
        P_old = copy.deepcopy(P_new)
        
        
    resultOut={
        'X':xk,
        'X_nkf':x_k_no_update,
        'P_final':P_new,
        'P_prev':P_old,
        # 'K_final':K_new,
        # 'K_prev':K_old,
        'Q':Q}
        # 'R':R}
    
    return resultOut
    
# results=run()
    
    


    
    
    
    