#!/usr/bin/env python3
# -*- coding: utf-8 -*-
""" Segmentation methods for 1D signals

This module gathers a collection of functions to detect regions of interest on 1D signals

Authors: Juan Sebastian Ulloa, Sylvain Haupert
License: 3-Clause BSD license
"""
import numpy as np
from scipy import signal
import matplotlib.pyplot as plt
import matplotlib.patches as patches
import pandas as pd

def sinc(s, cutoff, fs, atten=80, transition_bw=0.05, bandpass=True):
    """
    Filter 1D signal with a Kaiser-windowed filter
    
    Parameters: 
        s : ndarray
            input 1D signal
        cutoff : float 
            upper and lower frequencies 
        atten : int 
            attenuation in dB
        transition_bw : float
            transition bandwidth in %. default 5% of total band
        bandpass : bool
            bandpass (True) or bandreject (False) filter, default is bandpass
    Return
        s_filt (array): signal filtered
            
    """
    width = (cutoff[1] - cutoff[0]) * transition_bw
    numtaps, beta = signal.kaiserord(atten, width/(0.5*fs))
    np.ceil(numtaps-1) // 2 * 2 + 1  # round to nearest odd to have Type I filter
    taps = signal.firwin(numtaps, cutoff, window=('kaiser', beta), 
                         scale=False, nyq=0.5*fs, pass_zero=not(bandpass))
    s_filt = signal.lfilter(taps, 1, s)
    return s_filt


def corresp_onset_offset(onset, offset, tmin, tmax):
    """ Check that each onsets have a corresponding offset 

    Parameters
    ----------
        onset: ndarray
            array with onset from find_rois_1d
        offset: ndarray
            array with offset from find_rois_1d
        tmin: float
            Start time of wav file  (in s)
        tmax:
            End time of wav file  (in s)
    Return
    ------
        onset : ndarray
            onset with corresponding offset
        offset : ndarray
            offset with corresponding onset
    """
    if onset[0] > offset[0]:      # check start
        onset = np.insert(onset,0,tmin)
    else:
        pass
    if onset[-1] > offset[-1]:      # check end
        offset = np.append(offset,tmax)
    else:
        pass
    return onset, offset

def energy_windowed(s, wl=512, fs=None):
    """ Computse windowed energy on signal
    
    Computes the energy of the signals by windows of length wl. Used to amplify sectors where the density of energy is higher
    
    Parameters
    ----------
        s : ndarray
            input signal
        wl : float
            length of the window to summarize the rms value
        fs : float
            frequency sampling of the signal, used to keep track of temporal information of the signal

    Returns
    -------
        time : ndarray
            temporal index vector
        s_rms : ndarray
            windowed rms signal
        
    """
    s_aux = np.lib.pad(s, (0, wl-len(s)%wl), 'reflect')  # padding
    s_aux = s_aux**2 
    #  s_aux = np.abs(s_aux) # absolute value. alternative option
    s_aux = np.reshape(s_aux,(int(len(s_aux)/wl),wl))
    s_rms = np.mean(s_aux,1)
    time = np.arange(0,len(s_rms)) * wl / fs + wl*0.5/fs
    return time, s_rms

def find_rois_cwt(s, fs, flims, tlen, th=0, display=False, save_df=False,**kwargs):
    """
    Find region of interest (ROIS) based on predetermined temporal length and frequency limits
    
    The general approach is based on continous wavelet transform following a three step process
        1. Filter the signal with a bandpass sinc filter
        2. Smoothing the signal by convolving it with a Mexican hat wavelet (Ricker wavelet) [See ref 1]
        3. Binarize the signal applying a linear threshold
        
    Parameters
    ----------
        s : ndarray
            input signal
        flims : int
            upper and lower frequencies (in Hz) 
        tlen : int 
            temporal length of signal searched (in s)
        th : float, optional
            threshold to binarize the output
        display: boolean, optional, default is False
            plot results if set to True, default is False
        save_csv: boolean, optional
            save results to csv file
            
    Returns
    -------
        rois : pandas DataFrame
            an object with temporal and frequencial limits of regions of interest            
    
    Reference
    ---------
    [1] Bioinformatics (2006) 22 (17): 2059-2065. DOI:10.1093/bioinformatics/btl355 http://bioinformatics.oxfordjournals.org/content/22/17/2059.long
    """
    # filter signal
    s_filt = sinc(s, flims, fs, atten=80, transition_bw=0.8)
    # rms: calculate window of maximum 5% of tlen. improves speed of cwt
    wl = 2**np.floor(np.log2(tlen*fs*0.05)) 
    t, s_rms = energy_windowed(s_filt, int(wl), fs)
    # find peaks
    cwt_width = [round(tlen*fs/wl/2)]
    npad = 5 ## seems to work with 3, but not sure
    s_rms = np.pad(s_rms, np.int(cwt_width[0]*npad), 'reflect')  ## add pad
    s_cwt = signal.cwt(s_rms, signal.ricker, cwt_width)
    s_cwt = s_cwt[0][np.int(cwt_width[0]*npad):len(s_cwt[0])-np.int(cwt_width[0]*npad)] ## rm pad
    # find onset and offset of sound
    segments_bin = np.array(s_cwt > th)
    onset = t[np.where(np.diff(segments_bin.astype(int)) > 0)]+t[0]  # there is delay because of the diff that needs to  be accounted
    offset = t[np.where(np.diff(segments_bin.astype(int)) < 0)]+t[0]
    # format for output
    if onset.size==0 or offset.size==0:
    # No detection found
        print('Warning: No detection found')
        savefilename=kwargs.pop('savefilename', 'rois.csv')
        df = pd.DataFrame(data=None)
        if save_df==True:
            df.to_csv(savefilename, sep=',',header=False, index=False)

    else:
    # A detection was found, save results to csv
        onset, offset = corresp_onset_offset(onset, offset, tmin=0, tmax=len(s)/fs)
        rois_tf = np.transpose([np.round(onset,5),  
                                np.repeat(flims[0],repeats=len(onset)),
                                np.round(offset,5),   
                                np.repeat(flims[1],repeats=len(onset))])
        cols=['onset','fmin','offset','fmax']
        df = pd.DataFrame(data=rois_tf,columns=cols)
        if save_df==True:
            savefilename=kwargs.pop('savefilename', 'rois.csv')
            df.to_csv(savefilename, sep=',',header=True, index=False)

    # Display
    if display==True: 
        figsize = kwargs.pop('figsize',(12,6))
        cmap = kwargs.pop('cmap','gray')
        nfft = kwargs.pop('nfft',512)
        noverlap = kwargs.pop('noverlap',256)
        # plot
        fig,(ax1,ax2) = plt.subplots(2,1,figsize=figsize)
        ax1.margins(x=0)
        ax1.plot(s_cwt)
        ax1.set_xticks([])
        ax1.set_ylabel('Amplitude')
        ax1.grid(True)
        ax1.hlines(th, 0, len(s_cwt), linestyles='dashed', colors='r')
        ax2.specgram(s, NFFT=nfft, Fs=fs, noverlap=noverlap, cmap=cmap)
        ax2.set_ylabel('Frequency (Hz)')
        ax2.set_xlabel('Time (s)')
        if not(df.empty):
            for idx, _ in df.iterrows():
                xy = (df.onset[idx],df.fmin[idx])
                width = df.offset[idx] - df.onset[idx]
                height = df.fmax[idx] - df.fmin[idx]
                rect = patches.Rectangle(xy,width,height,lw=1,edgecolor='r',facecolor='none')
                ax2.add_patch(rect)
        plt.show()
    return df