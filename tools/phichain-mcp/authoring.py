"""rpe-next-style live authoring vocabulary, adapted to PhiChain's native model.

No parallel authoring state: every computation begins with a fresh guarded editor
snapshot and ends in editor-side validation and one shared undo entry.
"""
import copy
import json
import math
import os
from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parent
COLLECTIONS = ('lines', 'notes', 'events', 'curve_tracks')


def pointer_parts(path):
    if not isinstance(path, str) or (path and not path.startswith('/')):
        raise ValueError('Expected a JSON Pointer, e.g. /notes/123/note/x')
    parts = []
    for part in path[1:].split('/') if path else []:
        if '~' in part.replace('~0', '').replace('~1', ''):
            raise ValueError('Invalid JSON Pointer escape')
        parts.append(part.replace('~1', '/').replace('~0', '~'))
    return parts


def read(root, path):
    for part in pointer_parts(path):
        if isinstance(root, list):
            if not part.isdecimal() or str(int(part)) != part or int(part) >= len(root):
                raise ValueError('Unknown array index: ' + path)
            root = root[int(part)]
        elif isinstance(root, dict) and part in root:
            root = root[part]
        else:
            raise ValueError('Unknown path: ' + path)
    return root


def patch(document, operations):
    for op in operations:
        parts = pointer_parts(op['path'])
        if not parts:
            raise ValueError('Patch document fields, not the document root')
        parent_path = '/' + '/'.join(p.replace('~', '~0').replace('/', '~1') for p in parts[:-1]) if len(parts) > 1 else ''
        parent, key = read(document, parent_path), parts[-1]
        action = op['op']
        if isinstance(parent, list):
            if key == '-' and action == 'insert':
                parent.append(copy.deepcopy(op['value']))
                continue
            if not key.isdecimal() or str(int(key)) != key:
                raise ValueError('Invalid array index')
            index = int(key)
            if action == 'insert':
                if index > len(parent): raise ValueError('Array index out of bounds')
                parent.insert(index, copy.deepcopy(op['value']))
            elif index >= len(parent): raise ValueError('Array index out of bounds')
            elif action == 'set': parent[index] = copy.deepcopy(op['value'])
            elif action == 'remove': parent.pop(index)
        elif isinstance(parent, dict):
            if action == 'insert':
                if key in parent: raise ValueError('Insert would overwrite: ' + op['path'])
                parent[key] = copy.deepcopy(op['value'])
            elif key not in parent: raise ValueError('Unknown path: ' + op['path'])
            elif action == 'set': parent[key] = copy.deepcopy(op['value'])
            elif action == 'remove': del parent[key]
        else: raise ValueError('Patch parent must be a collection')
    return document


def compute(mode, document, args):
    node = shutil.which('node')
    if not node:
        raise ValueError('Node.js 22.13+ is required for transform, generate and script; chart_patch needs only Python')
    worker = ROOT / 'authoring-worker.mjs'
    # Permission mode is mandatory. Do not silently run without it on old Node.
    command = [node, '--permission', '--allow-fs-read=' + str(ROOT), '--max-old-space-size=256', str(worker)]
    payload = json.dumps({'mode': mode, 'document': document, 'args': args}, allow_nan=False)
    if len(payload.encode()) > 16 * 1024 * 1024:
        raise ValueError('Computation input exceeds 16 MiB')
    try:
        completed = subprocess.run(command, input=payload, text=True, capture_output=True,
            timeout=args.get('timeout_ms', 10000) / 1000 + 2,
            env={'PATH': os.environ.get('PATH', ''), 'LANG': 'C.UTF-8', 'NODE_NO_WARNINGS': '1'})
    except subprocess.TimeoutExpired as error:
        raise ValueError('Computation timed out; nothing was committed') from error
    if len(completed.stdout.encode()) > 8 * 1024 * 1024:
        raise ValueError('Computation result exceeds 8 MiB')
    try: result = json.loads(completed.stdout)
    except ValueError as error:
        raise ValueError('Node computation failed: ' + completed.stderr[-1200:]) from error
    if completed.returncode or 'error' in result:
        raise ValueError(result.get('error', 'Computation failed'))
    return result


def beat_value(value):
    return value[0] + value[1] / value[2] if isinstance(value, list) else value


def execute(name, args, bridge, catalog):
    if name == 'editor_context':
        result = bridge('get_context', {})
        if 'error' not in result:
            result['authoring_model'] = 'ID-keyed native document; chart_read path="" lists fields'
            result['capabilities'] = [t['name'] for t in catalog]
        return result
    if name in ('chart_tools', 'agent_tools'):
        query = args.get('query', '').lower()
        tools = [t for t in catalog if (not query or query in (t['name'] + ' ' + t['description']).lower()) and (not args.get('names') or t['name'] in args['names'])]
        return {'tools': tools, 'count': len(tools), 'activation': 'All listed tools are already advertised by tools/list'}
    if name == 'chart_templates':
        from agent_server import templates
        return {'templates': templates(), 'schema': 'Use these PhiChain objects, not RPE JSON', 'new_ids': 'Unique new:name aliases, resolved atomically by the editor'}
    if name == 'project_save': return bridge('save', args)
    if name == 'diagnose': return bridge('authoring_diagnose', args)
    if name == 'editor_view':
        return bridge('authoring_view', args)
    # Every remaining read/compute comes from the live editor and exact guard.
    snapshot = bridge('authoring_read', {k: args[k] for k in ('session', 'revision')})
    if 'error' in snapshot: return snapshot
    document = snapshot['document']
    existing_lines = set(document['lines'])
    guards = {k: snapshot[k] for k in ('session', 'revision')}
    if name == 'chart_read':
        value = read(document, args.get('path', ''))
        if not args.get('path'):
            return {**guards, 'fields': list(document), 'counts': {k: len(document[k]) for k in COLLECTIONS}, 'meta': document['meta'], 'bpm_list': document['bpm_list'], 'offset': document['offset']}
        if isinstance(value, dict) and args.get('path', '').count('/') == 1 and args['path'][1:] in COLLECTIONS:
            entries = [{'id': k, 'value': v} for k,v in value.items()]
            total = len(entries)
            entries = entries[args.get('offset',0):args.get('offset',0)+args.get('limit',50)]
            if args.get('fields'):
                for entry in entries:
                    entry['value'] = {p: read(entry['value'], p) for p in args['fields']}
            return {**guards, 'total': total, 'items': entries}
        if isinstance(value, list):
            return {**guards, 'total':len(value), 'items':value[args.get('offset',0):args.get('offset',0)+args.get('limit',50)]}
        return {**guards, 'value':value}
    if name in ('chart_query', 'editor_entities'):
        collection = args.get('collection','lines')
        entries = [{'id':k,'value':v} for k,v in document[collection].items()]
        if name == 'editor_entities':
            query = args.get('query','').lower()
            entries = [e for e in entries if query in str(e['value'].get('name', e['id'])).lower()]
        else:
            for condition in args.get('where',[]):
                def matches(entry):
                    a, b = read(entry['value'], condition['path']), condition['value']
                    return {'eq':lambda:a==b, 'ne':lambda:a!=b, 'lt':lambda:a<b, 'lte':lambda:a<=b, 'gt':lambda:a>b, 'gte':lambda:a>=b, 'contains':lambda:b in a}[condition['op']]()
                entries = [e for e in entries if matches(e)]
            if 'start' in args or 'end' in args:
                if collection not in ('notes','events'): raise ValueError('Beat range queries require notes or events')
                def overlaps(entry):
                    row=entry['value']; obj=row.get('note',row.get('event'))
                    start=beat_value(obj.get('beat',obj.get('start_beat')))
                    end=start+beat_value(obj.get('hold_beat',[0,0,1])) if 'note' in row else beat_value(obj['end_beat'])
                    return end>=args.get('start',-math.inf) and start<args.get('end',math.inf)
                entries=[e for e in entries if overlaps(e)]
            if args.get('sort'):
                def sortkey(entry):
                    value=read(entry['value'],args['sort'])
                    return beat_value(value) if isinstance(value,list) else value
                entries.sort(key=lambda e:(sortkey(e),e['id']))
        total=len(entries); offset=args.get('offset',0); limit=args.get('limit',50)
        entries=entries[offset:offset+limit]
        if args.get('fields'):
            for entry in entries: entry['value']={p:read(entry['value'],p) for p in args['fields']}
        return {**guards,'total':total,'items':entries,'next_offset':offset+limit if offset+limit<total else None}
    if name == 'editor_navigate':
        if args['unit']=='audio_seconds': seconds=args['value']
        elif args['unit']=='chart_seconds': seconds=args['value']+document['offset']/1000
        else:
            target=args['value']; points=document['bpm_list']; seconds=0
            for i,point in enumerate(points):
                start=beat_value(point['beat']); end=beat_value(points[i+1]['beat']) if i+1<len(points) else target
                if target<=start: break
                seconds+=(min(target,end)-start)*60/point['bpm']
                if target<=end: break
            seconds+=document['offset']/1000
        return bridge('preview', {'session':guards['session'],'action':args.get('action','seek'),'time_seconds':seconds})
    statistics={}
    if name == 'chart_patch': document=patch(document,args['operations'])
    elif name in ('chart_transform','chart_generate','chart_script'):
        output=compute(name.removeprefix('chart_'),document,args)
        document=output['document']; statistics=output.get('result')
    elif name == 'bpm_set': document['bpm_list']=args['bpm_list']
    elif name == 'curve_notes':
        alias=args.get('alias','new:curve')
        if alias in document['curve_tracks']: raise ValueError('Curve alias already exists')
        document['curve_tracks'][alias]={'line_id':args['line_id'],'from_id':args['from_id'],'to_id':args['to_id'],'options':args['options']}
    elif name == 'line_manage':
        lines=document['lines']; action=args['action']; target=args.get('line_id')
        if action in ('parent','rename','delete','duplicate') and target not in lines: raise ValueError('Unknown line_id')
        if action=='create':
            alias=args['alias']
            if alias in lines: raise ValueError('Alias already exists')
            lines[alias]={'name':args['name'],'parent_id':args.get('parent_id'),'role':'simple','order':max((l['order'] for l in lines.values()),default=-1)+1}
        elif action=='parent':
            if 'parent_id' not in args: raise ValueError('parent_id is required; null detaches')
            lines[target]['parent_id']=args['parent_id']
        elif action=='rename': lines[target]['name']=args['name']
        elif action=='reorder':
            roots={k for k,l in lines.items() if l['parent_id'] is None}
            if set(args['line_ids'])!=roots or len(args['line_ids'])!=len(roots): raise ValueError('Supply every root line exactly once')
            for i,key in enumerate(args['line_ids']): lines[key]['order']=i
        elif action=='delete':
            deleted={target}
            while True:
                expanded=deleted | {k for k,l in lines.items() if l['parent_id'] in deleted}
                if deleted==expanded: break
                deleted=expanded
            populated=len(deleted)>1 or any(r['line_id'] in deleted for key in COLLECTIONS[1:] for r in document[key].values())
            if populated and not args.get('cascade'): raise ValueError('Dependent objects require cascade=true')
            for key in deleted: del lines[key]
            for key in COLLECTIONS[1:]: document[key]={k:r for k,r in document[key].items() if r['line_id'] not in deleted}
        elif action=='duplicate':
            alias=args['alias']
            if alias in lines or not alias.startswith('new:'): raise ValueError('Supply a unique new:name alias')
            descendants={target}
            while True:
                expanded=descendants|{k for k,l in lines.items() if l['parent_id'] in descendants}
                if descendants==expanded: break
                descendants=expanded
            mapping={key:alias if key==target else alias+':line:'+key for key in descendants}
            for key in descendants:
                row=copy.deepcopy(lines[key]); row['parent_id']=mapping.get(row['parent_id'],row['parent_id']); row['order']=max(l['order'] for l in lines.values())+1
                lines[mapping[key]]=row
            for collection in COLLECTIONS[1:]:
                for key,row in list(document[collection].items()):
                    if row['line_id'] not in descendants: continue
                    new=alias+':'+collection+':'+key; mapping[key]=new
                    duplicate=copy.deepcopy(row); duplicate['line_id']=mapping[row['line_id']]
                    document[collection][new]=duplicate
            for key in list(document['curve_tracks']):
                if key.startswith(alias+':curve_tracks:'):
                    row=document['curve_tracks'][key]
                    row['from_id']=mapping.get(row['from_id'],row['from_id']); row['to_id']=mapping.get(row['to_id'],row['to_id'])
        else: raise ValueError('Unknown line action')
    else: raise ValueError('Unsupported authoring tool: '+name)
    if not isinstance(document,dict): raise ValueError('Script must return a chart document object')
    # Native line constructors normally supply baseline events. Supply only absent
    # channels on NEW lines, so a new carrier actually scrolls and renders. Explicit
    # channels (including zero/negative speed or opacity) remain exactly as supplied.
    if not isinstance(document.get('lines'),dict) or not isinstance(document.get('events'),dict):
        raise ValueError('lines and events must be ID-keyed objects')
    if any(not isinstance(document.get(collection),dict) for collection in COLLECTIONS):
        raise ValueError('Editable collections must be ID-keyed objects')
    if any(not isinstance(row,dict) or not isinstance(row.get('event'),dict) for row in document['events'].values()):
        raise ValueError('Invalid native event row')
    used = {key for collection in COLLECTIONS for key in document[collection]}
    defaults = {'x':0,'y':0,'rotation':0,'opacity':255,'speed':10}
    sequence = 0
    for line_id in sorted(set(document['lines']) - existing_lines):
        channels = {row.get('event',{}).get('kind') for row in document['events'].values() if row.get('line_id')==line_id}
        for kind,value in defaults.items():
            if kind in channels: continue
            while True:
                alias='new:baseline:'+str(sequence); sequence+=1
                if alias not in used: break
            used.add(alias)
            document['events'][alias]={'line_id':line_id,'event':{'kind':kind,'start_beat':[0,0,1],'end_beat':[1,0,1],'value':{'type':'constant','value':value}}}
    # Native validation remains mandatory even for dry runs, including all references.
    result=bridge('authoring_commit',{**guards,'document':document,'dry_run':args['dry_run'],'label':args.get('label',name)})
    if 'error' not in result:
        result['label']=args.get('label',name)
        result['result']=statistics
        result['scope']='Full native candidate validation; not an aesthetic or playability guarantee'
    return result
