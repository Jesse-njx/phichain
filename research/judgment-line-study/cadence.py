"""Measure whole-chart scene occupancy and episode cadence from the frozen sources."""
from concurrent.futures import ProcessPoolExecutor
import hashlib
import json
from pathlib import Path

import numpy as np

from analyze import Line, ROOT, line_visible

STEP = 0.05
WINDOW = 0.5
SAMPLES = 10
CHANNELS = ("travel", "turn", "alpha")
LOW = np.array([0.015, 2.0, 0.05])[:, None]
HIGH = np.array([0.12, 18.0, 0.30])[:, None]


def approach(line):
    # Project every note's head on the last 1.5 s, including hidden carriers.
    hit = np.array([n['t'] for n in line.notes])
    times = np.maximum(0, hit[:, None] - np.linspace(1.5, 0, 31))
    x, y, r, _, _ = line.pose(times)
    theta = np.deg2rad(r)
    u = np.array([n['positionX'] / 18 for n in line.notes])[:, None]
    factor = np.array([1 if n['type'] == 3 else n['speed'] for n in line.notes])[:, None]
    front = .6 * (line.floor(hit)[:, None] - line.floor(times)) * factor
    side = np.array([1 if n['side'] == 'notesAbove' else -1 for n in line.notes])[:, None]
    hold = np.array([n['type'] == 3 for n in line.notes])[:, None]
    front = np.where(hold, np.maximum(front, 0), front)
    dist = front * side
    xx = x + u*np.cos(theta) - dist*(9/16)*np.sin(theta)
    yy = y + u*(16/9)*np.sin(theta) + dist*np.cos(theta)
    visible = ((xx >= 0) & (xx <= 1) & (yy >= 0) & (yy <= 1) &
               (front >= -1e-6))
    suffix = np.logical_and.accumulate(visible[:, ::-1], axis=1)[:, ::-1]
    idx = np.argmax(suffix, axis=1)
    rows = np.arange(len(hit))
    valid = visible[:, -1] & (hit - times[rows,idx] >= .149)
    dx = (xx - xx[rows,idx,None])*(16/9)
    dy = yy - yy[rows,idx,None]
    ex, ey = dx[:, -1:], dy[:, -1:]
    norm = ex*ex + ey*ey
    proj = np.clip((dx*ex+dy*ey)/np.maximum(norm,1e-10), 0, 1)
    bend = np.max(np.where(suffix, np.hypot(dx-proj*ex, dy-proj*ey), 0),axis=1)
    span = np.max(np.where(suffix, dx,-np.inf),axis=1)-np.min(np.where(suffix, dx,np.inf),axis=1)
    ex,ey=ex[:,0],ey[:,0]
    straight = valid & (ey < -.12) & (span < .05)
    sideward = valid & (abs(ex)>=.15) & (abs(ex)>=abs(ey))
    rising = valid & (ey>=.15)
    curved = valid & (bend>=.06)
    return valid,straight,sideward,rising,curved


def starts(mask, join=1):
    active = np.flatnonzero(mask)
    if not len(active):return []
    return active[np.r_[True,np.diff(active)>join+1]].tolist()


def intervals(mask):
    return (np.diff(starts(mask))*WINDOW).tolist()


def contiguous(mask):
    edges = np.flatnonzero(np.diff(np.r_[False,mask,False]))
    return zip(edges[::2],edges[1::2])


def high_points(values, prominence):
    # Confirm a peak only after a rise and subsequent fall of this size.
    low = high = float(values[0])
    peak = 0
    rising = False
    for i,v in enumerate(values):
        if not rising:
            low = min(low,v)
            if v-low>=prominence:
                rising,high,peak=True,v,i
        elif v>=high:
            high,peak=v,i
        elif high-v>=prominence:
            yield peak
            rising,low=False,v


def regular_intervals(indices):
    dt=np.diff(indices)*STEP
    keep=np.zeros(len(dt),bool)
    for i in range(len(dt)-2):
        three=dt[i:i+3]
        if three.min()>=.15-1e-8 and three.max()<=2 and np.ptp(three)<=max(.051,.2*np.median(three)):
            keep[i:i+3]=True
    return dt[keep].tolist()


def cycles(x,y,r,alpha,on_screen):
    output={'flash':[], 'rock':[], 'dip':[]}
    for a,b in contiguous(on_screen):
        armed=False; pulses=[]
        for j,v in enumerate(alpha[a:b]):
            if v<=.10:
                armed=True
            elif armed and v>=.25:
                pulses.append(j)
                armed=False
        output['flash'].extend(regular_intervals(pulses))
    visible=on_screen & (alpha>.05)
    for a,b in contiguous(visible):
        theta=np.rad2deg(np.unwrap(np.deg2rad(r[a:b])*2)/2)
        output['rock'].extend(regular_intervals(list(high_points(theta,5))))
    level=abs((r+90)%180-90)<=15
    for a,b in contiguous(visible & level):
        output['dip'].extend(regular_intervals(list(high_points(-y[a:b],.03))))
    return output


def chart(rec):
    raw=Path(rec['path']).read_bytes()
    assert hashlib.sha256(raw).hexdigest()==rec['sha256']
    doc=json.loads(raw); lines=[Line(row,doc['formatVersion']) for row in doc['judgeLineList']]
    first=min(n['t'] for l in lines for n in l.notes)
    last=max(n['end'] for l in lines for n in l.notes)
    bins=int(np.floor((last-first)/WINDOW))
    ts=first+np.arange(bins*SAMPLES+1)*STEP
    # Whole-chart line roles. Aggregate each channel across lines with max, never sum.
    activity=np.zeros((2,3,bins))
    presence=np.zeros((2,bins),bool)
    heads=np.zeros(bins,bool); special_heads=np.zeros(bins,bool)
    totals=np.zeros(11,int)
    judging=np.zeros(bins,bool); judging_motion=np.zeros(bins,bool)
    periods={key:[] for key in [f"{role}_{kind}" for role in ("carrier","bg") for kind in ("flash","rock","dip")]}
    for line in lines:
        role=int(not bool(line.notes))
        x,y,r,alpha,_=line.pose(ts)
        alpha=np.clip(alpha,0,1)
        on_screen=line_visible(x,y,r)
        vis=(alpha>.05)&on_screen
        for kind,values in cycles(x,y,r,alpha,on_screen).items():
            periods[("bg" if role else "carrier")+"_"+kind].extend(values)
        pair=vis[:-1]&vis[1:]
        # Shortest signed turn of an unoriented stroke. Resolve normal translation at mid-angle.
        dr=(np.diff(r)+90)%180-90
        angle=np.deg2rad(r[:-1]+dr/2)
        normal=-np.diff(x)*(16/9)*np.sin(angle)+np.diff(y)*np.cos(angle)
        alpha_pair=on_screen[:-1]&on_screen[1:]&(vis[:-1]|vis[1:])
        diffs=np.stack([abs(normal)*pair, abs(dr)*pair, abs(np.diff(alpha))*alpha_pair])
        variations=diffs.reshape(3,bins,SAMPLES).sum(axis=2)
        activity[role]=np.maximum(activity[role],variations)
        presence[role]|=(vis[:-1]|vis[1:]).reshape(bins,SAMPLES).any(axis=1)
        if line.notes:
            valid,straight,sideward,rising,curved=approach(line)
            rare=sideward|rising|curved
            rhit = line.pose(np.array([n['t'] for n in line.notes]))
            level = abs((rhit[2]+90)%180-90)<=10
            totals += [len(line.notes),sum(valid),sum(straight),sum(sideward),sum(rising),sum(curved),sum(rare),sum(level),sum(rhit[3]<=.01),sum(abs(rhit[4])<.01),sum(rhit[4]<-.01)]
            idx=np.floor((np.array([n['t'] for n in line.notes])-first)/WINDOW).astype(int)
            inside=(idx>=0)&(idx<bins)
            heads[idx[inside&valid]]=True;special_heads[idx[inside&rare]]=True
            receiving=np.zeros(bins,bool); receiving[idx[inside]]=True
            for n in line.notes:
                if n['type']==3:
                    i,j=np.floor((np.array([n['t'],n['end']])-first)/WINDOW).astype(int)
                    receiving[max(0,i):min(bins,j+1)]=True
            judging |= receiving
            judging_motion |= receiving & (variations>=LOW).any(axis=0)
    moving=(activity>=LOW).any(axis=1)
    strong=(activity>=HIGH).any(axis=1)
    any_strong=strong.any(axis=0)
    labels={}
    for k,val in zip(['carrier','background'],range(2)):
        labels[k+'_present']=presence[val];labels[k+'_motion']=moving[val];labels[k+'_strong']=strong[val]
    labels['motion']=moving.any(axis=0);labels['strong']=any_strong
    labels['sensitive']=(activity>=HIGH*.75).any(axis=(0,1))
    labels['strict']=(activity>=HIGH*1.25).any(axis=(0,1))
    labels['note_head']=heads;labels['note_special']=special_heads
    labels['judging']=judging; labels['judging_motion']=judging_motion
    for i,channel in enumerate(CHANNELS):
        labels[channel]=(activity[:,i]>=LOW[i]).any(axis=0)
        labels['strong_'+channel]=(activity[:,i]>=HIGH[i]).any(axis=0)
    # Signatures count newly strong channels even if another strong channel continues.
    # A frame gets one onset even if multiple channels enter together.
    type_entries=np.zeros(bins,bool)
    for role in range(2):
        for channel in range(3):
            type_entries[starts(activity[role,channel]>=HIGH[channel])]=True
    return dict(id=rec['id'],title=rec['title'],difficulty=rec['difficulty'],first=first,last=last,bins=bins,
                counts=totals.tolist(), windows={k:''.join('1' if v else '0' for v in arr) for k,arr in labels.items()},
                channel_entries=np.flatnonzero(type_entries).tolist(),
                periods={k:[len(v),float(np.median(v)) if v else None] for k,v in periods.items()})


if __name__=='__main__':
    records=json.loads((ROOT/'inventory.json').read_text())['charts']
    with ProcessPoolExecutor(max_workers=4) as pool: rows=list(pool.map(chart,records,chunksize=2))
    (ROOT/'cadence-windows.json').write_text(json.dumps(rows,ensure_ascii=False,separators=(',',':')))
    print('Verified sources and scanned',len(rows),'charts,',sum(row['bins'] for row in rows),'half-second windows.')
