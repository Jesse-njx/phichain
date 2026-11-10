"""Pinned approach plans using original carriers and necessary invisible helpers.

No runtime inference or LLM. A plan records note addresses and the reviewed final
approach interval. Helpers replay the original spatial path on a delayed, faster
clock, then return to the original clock exactly at the judgment time.
"""
import bisect
import copy
import math

HORIZON = 1_000_000_000


class Channel:
    def __init__(self, events, pairs):
        self.events = events
        self.pairs = pairs
        self.starts = [e['startTime'] for e in events]
        if self.starts != sorted(self.starts):
            raise ValueError('Animation channels must be ordered for approach replay')

    def at(self, t):
        if not self.events:
            raise ValueError('Cannot infer a missing animation channel')
        i = max(0,bisect.bisect_right(self.starts,t)-1)
        e = self.events[i]
        u = min(1,max(0,(t-e['startTime'])/(e['endTime']-e['startTime']))) if e['endTime']>e['startTime'] else 1
        return tuple(e[a]+(e[b]-e[a])*u for a,b in self.pairs)

    def pieces(self,a,b):
        points={a,b}
        left=max(0,bisect.bisect_right(self.starts,a)-1)
        right=bisect.bisect_left(self.starts,b)
        for e in self.events[left:right+1]:
            if a<e['startTime']<b:points.add(e['startTime'])
            if a<e['endTime']<b:points.add(e['endTime'])
        points=sorted(points)
        for s,t in zip(points,points[1:]):
            i=max(0,bisect.bisect_right(self.starts,(s+t)/2)-1)
            e=self.events[i]
            def value(at):
                u=min(1,max(0,(at-e['startTime'])/(e['endTime']-e['startTime']))) if e['endTime']>e['startTime'] else 1
                return tuple(e[x]+(e[y]-e[x])*u for x,y in self.pairs)
            yield s,t,value(s),value(t)


def event(s,t,a,b,pairs):
    e={'startTime':s,'endTime':t}
    for (x,y),u,v in zip(pairs,a,b):e[x],e[y]=u,v
    return e


def append_merged(events,e,pairs):
    if e['endTime']<=e['startTime']:return
    if events:
        prev=events[-1]
        # Exact constant merging only: no approximate easing fit or visual drift.
        if prev['endTime']==e['startTime'] and all(prev[x]==prev[y]==e[x]==e[y] for x,y in pairs):
            prev['endTime']=e['endTime']
            return
    events.append(e)


def warped_channel(channel,visible,start,head,end,x,prefix):
    begin=head-(head-start)/x
    out=[]
    if visible>0:out.append(event(0,visible,prefix,prefix,channel.pairs))
    for left,right,scale,shift in [(visible,start,1,0),(start,head,1/x,head-head/x),(head,end,1,0)]:
        if left==start and right==head and begin>start:
            value=channel.at(start)
            append_merged(out,event(start,begin,value,value,channel.pairs),channel.pairs)
        if right>left:
            for a,b,u,v in channel.pieces(left,right):
                append_merged(out,event(a*scale+shift,b*scale+shift,u,v,channel.pairs),channel.pairs)
    value=channel.at(end)
    append_merged(out,event(end,HORIZON,value,value,channel.pairs),channel.pairs)
    return out


def invisible_opacity(events):
    """Never draw helper lines; preserve negative-alpha note-visibility semantics."""
    out=[]
    for e in events:
        s,t,a,b=e['startTime'],e['endTime'],e['start'],e['end']
        if a*b<0:
            cut=s+(t-s)*(-a)/(b-a)
            append_merged(out,event(s,cut,(min(0,a),),(0,),[('start','end')]),[('start','end')])
            append_merged(out,event(cut,t,(0,),(min(0,b),),[('start','end')]),[('start','end')])
        else:
            append_merged(out,event(s,t,(min(0,a),),(min(0,b),),[('start','end')]),[('start','end')])
    return out


def warped_speed(line,visible,start,head,end,x,engine):
    source=line['speedEvents']
    out=[]
    begin=head-(head-start)/x
    def put(a,b,value):
        if b<=a:return
        if out and out[-1]['endTime']==a and out[-1]['value']==value:out[-1]['endTime']=b
        else:out.append({'startTime':a,'endTime':b,'value':value})
    put(0,visible,0)
    for left,right,scale,shift in [(visible,start,1,0),(start,head,1/x,head-head/x),(head,end,1,0)]:
        if left==start and right==head:put(start,begin,0)
        for e in source:
            a,b=max(left,e['startTime']),min(right,e['endTime'])
            if b>a:put(a*scale+shift,b*scale+shift,e['value']/scale)
    put(end,HORIZON,0)
    # Affine endpoint arithmetic can differ by a few ulps. Join explicitly;
    # this is within floating-point timing precision, not a source retiming.
    for a,b in zip(out,out[1:]):
        if not math.isclose(a['endTime'],b['startTime'],rel_tol=0,abs_tol=1e-7):
            raise engine.ProfileError('Helper scroll lost a continuous boundary')
        b['startTime']=a['endTime']
    timeline=engine.Scroll(out,line['bpm'])
    for j,e in enumerate(out):e['floorPosition']=timeline.floors[j]
    return out


def recount(line):
    for key,value in [('numOfNotesAbove',len(line['notesAbove'])),('numOfNotesBelow',len(line['notesBelow'])),
                      ('numOfNotes',len(line['notesAbove'])+len(line['notesBelow']))]:
        if key in line:line[key]=value


def make_helper(line,side,index,start,visible,x,engine):
    note=copy.deepcopy(line[side][index])
    head=note['time']
    end=max(head+note['holdTime'],head)+max(1,line['bpm']/1.875*.05)
    end=min(end,line['speedEvents'][-1]['endTime'])
    helper={k:copy.deepcopy(v) for k,v in line.items() if k not in (*engine.SIDES,*engine.ANIMATIONS,'speedEvents')}
    helper.update(notesAbove=[],notesBelow=[])
    helper[side].append(note)
    helper['speedEvents']=warped_speed(line,visible,start,head,end,x,engine)
    old=engine.Scroll(line['speedEvents'],line['bpm'])
    note['floorPosition']-=old.floor(visible)
    for channel,pairs,prefix in [
        ('judgeLineMoveEvents',[('start','end'),('start2','end2')],(1_000_000,1_000_000)),
        ('judgeLineRotateEvents',[('start','end')],(0,)),
        ('judgeLineDisappearEvents',[('start','end')],(-1,))]:
        # Nonnegative source alpha never hides notes. Its clamp is identically
        # zero, including legacy backwards zero-alpha records: no interpolation
        # or reordering of those original records is needed on a hidden helper.
        if channel == 'judgeLineDisappearEvents' and line[channel] and all(e['start'] >= 0 and e['end'] >= 0 for e in line[channel]):
            events=[]
            if visible>0:events.append(event(0,visible,(-1,),(-1,),pairs))
            events.append(event(visible,HORIZON,(0,),(0,),pairs))
            helper[channel]=events
            continue
        events=warped_channel(Channel(line[channel],pairs),visible,start,head,end,x,prefix)
        helper[channel]=invisible_opacity(events) if channel=='judgeLineDisappearEvents' else events
    recount(helper)
    return helper


def helper_groups(plan,line):
    groups={}
    for n in plan['helpers']:
        key=(line[n['side']][n['note']]['time'],n['start'])
        groups.setdefault(key,[]).append(n)
    result=[]
    for group in groups.values():
        group.sort(key=lambda n:line[n['side']][n['note']]['holdTime'],reverse=True)
        result.append((group,min(n['visible_from'] for n in group)))
    return result


def validate_plan(base,rule,x,engine):
    engine.fields(rule,('schema_version','source_sha256','multiplier_range','plans'),('metadata',),'approach rule')
    if rule['schema_version']!=2:raise engine.ProfileError('Unsupported approach schema')
    low,high=rule['multiplier_range']
    if not 1<=low<=x<=high<=4:raise engine.ProfileError('Approach replay supports speed-up factors within the pinned range')
    if len(rule['plans'])!=len(base['judgeLineList']):raise engine.ProfileError('One approach plan is required per original line')
    lines=set()
    for p in rule['plans']:
        engine.fields(p,('line','whole_line','direct','helpers','preserve','reason'),label='approach line plan')
        i=p['line']
        if type(i)is not int or i in lines or not 0<=i<len(base['judgeLineList']):raise engine.ProfileError('Invalid line plan address')
        lines.add(i)
        if type(p['whole_line'])is not bool:raise engine.ProfileError('whole_line must be boolean')
        if p['whole_line']:
            if p['direct'] or p['helpers'] or p['preserve']:raise engine.ProfileError('Whole-line plan cannot also move individual notes')
            continue
        seen=set()
        for kind in ('direct','helpers','preserve'):
            for n in p[kind]:
                side,j=n['side'],n['note']
                if side not in engine.SIDES or type(j)is not int or not 0<=j<len(base['judgeLineList'][i][side]) or (side,j)in seen:
                    raise engine.ProfileError('Invalid or duplicate planned note')
                seen.add((side,j))
                note=base['judgeLineList'][i][side][j]
                if kind=='direct' and note['type']==3:raise engine.ProfileError('Hold needs a carrier or replay helper')
                if kind=='helpers':
                    for key in ('visible_from','start'):engine.number(n[key],key)
                    if not 0<=n['visible_from']<=n['start']<note['time']:
                        raise engine.ProfileError('Invalid final-approach interval')
        expected={(s,j)for s in engine.SIDES for j in range(len(base['judgeLineList'][i][s]))}
        if seen!=expected:raise engine.ProfileError('Approach plan must account for every original note')


def apply(base,rule,x,engine):
    engine.validate_chart(base)
    validate_plan(base,rule,x,engine)
    if x==1:return copy.deepcopy(base)
    line_policy={'multiplier_range':rule['multiplier_range'],'transparent_tails':False,
                 'review':'Pinned whole-line subset of reviewed approach plan',
                 'lines':[{'line':p['line'],'gain':1 if p['whole_line'] else 0,'reason':p['reason']}for p in rule['plans']]}
    out=engine.transform(base,line_policy,x)
    helpers=[]
    for p in rule['plans']:
        i=p['line']
        if p['whole_line']:continue
        line=out['judgeLineList'][i]
        for n in p['direct']:
            note=line[n['side']][n['note']]
            note['speed']=engine.number(note['speed']*x,'direct note speed')
        moved={s:set()for s in engine.SIDES}
        for group,visible in helper_groups(p,base['judgeLineList'][i]):
            n=group[0]
            original=base['judgeLineList'][i]
            helper=make_helper(original,n['side'],n['note'],n['start'],visible,x,engine)
            shift=engine.Scroll(original['speedEvents'],original['bpm']).floor(visible)
            for extra in group[1:]:
                note=copy.deepcopy(original[extra['side']][extra['note']])
                note['floorPosition']-=shift
                helper[extra['side']].append(note)
            recount(helper)
            helpers.append(helper)
            for n in group:moved[n['side']].add(n['note'])
        for side in engine.SIDES:line[side]=[n for j,n in enumerate(line[side])if j not in moved[side]]
        recount(line)
    out['judgeLineList'].extend(helpers)
    engine.validate_chart(out)
    return out
