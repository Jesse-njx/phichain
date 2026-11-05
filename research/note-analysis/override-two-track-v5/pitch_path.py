"""Monophonic temporal path with a silence state and separate rearticulation."""
import numpy as np
from scipy.signal import find_peaks

def decode(frames,onsets,times,activity,floor=.34):
    # Input pitch bins are Basic Pitch MIDI 21..108. No fixed high-pitch preference.
    n,p=frames.shape
    scores=np.log(np.maximum(frames,.001)/floor)
    scores[~activity,:]=-20
    scores[:, :22]=-20 # below MIDI 43: outside the configured lead range
    scores[:, 64:]=-20 # above MIDI 84: outside this song's foreground range
    emission=np.c_[np.zeros(n),scores]
    distance=abs(np.arange(p)[:,None]-np.arange(p)[None,:])
    transition=np.full((p+1,p+1),.7)
    transition[1:,1:]=.8+.055*np.minimum(distance,24)
    np.fill_diagonal(transition,0)
    prev=emission[0];back=np.zeros((n,p+1),dtype=np.int16)
    for k in range(1,n):
        # Predicted onset can support a new pitch, but is not required for legato.
        costs=transition.copy();costs[:,1:]*=(1-.55*np.clip(onsets[k],0,1))[None,:]
        possibilities=prev[:,None]-costs
        back[k]=np.argmax(possibilities,axis=0)
        prev=emission[k]+np.max(possibilities,axis=0)
    path=np.empty(n,dtype=np.int16);path[-1]=np.argmax(prev)
    for k in range(n-1,0,-1):path[k-1]=back[k,path[k]]
    changes=np.r_[0,np.flatnonzero(np.diff(path))+1,n]
    notes=[]
    for first,last in zip(changes[:-1],changes[1:]):
        if path[first]==0 or last-first<4:continue
        pitch=int(path[first]-1);f=frames[first:last,pitch]
        if np.mean(f)<floor+.015:continue
        # Separate same-pitch articulations from pitch transitions. Never split
        # a held pitch merely because the mixture or another pitch has a peak.
        peaks,_=find_peaks(onsets[first:last,pitch],height=.5,prominence=.18,distance=5)
        cuts=[first]+[first+int(k) for k in peaks if k>=4 and last-first-k>=4]+[last]
        for start,end in zip(cuts[:-1],cuts[1:]):
            if end-start<4:continue
            onset=float(np.max(onsets[max(0,start-1):min(n,start+2),pitch]))
            notes.append(dict(start_frame=int(start),end_frame=int(end),time_seconds=float(times[start]),
                end_seconds=float(times[min(end,n-1)]),pitches=[pitch+21],model_activation=float(np.mean(frames[start:end,pitch])),
                boundary_kind='same_pitch_rearticulation' if start!=first else 'pitch_transition_or_activity_start',
                learned_onset=onset))
    return notes,path
