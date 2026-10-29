#!/usr/bin/env python3
"""Experimental rpe-next-style authoring MCP for the live PhiChain editor."""
import argparse
import copy
import json
import sys

import authoring
import server

obj, tool = server.obj, server.tool
S, N, ID, BEAT, GUARD = server.STRING, server.NUMBER, server.ID, server.BEAT, server.GUARD
BOOL = {'type':'boolean'}
COLLECTION = {'enum':list(authoring.COLLECTIONS)}
PATH = {'type':'string','description':'JSON Pointer into the ID-keyed document; e.g. /notes/123/note/x. Escape ~ as ~0 and / as ~1.'}
PAGING = {'offset':{'type':'integer','minimum':0},'limit':{'type':'integer','minimum':1,'maximum':200}}
DRY = {'dry_run':{'type':'boolean','description':'Required: true validates without chart/history changes; false commits one shared agent undo entry.'},'label':{'type':'string','maxLength':160}}
READ = {**GUARD}
WRITE = {**GUARD,**DRY}
IDS = {'type':'array','items':S,'minItems':1,'maxItems':10000,'uniqueItems':True}
EXPRS = {'type':'object','additionalProperties':{'type':'string'},'description':'Relative JSON Pointer to safe numeric expression; /note/x: -x, /note/beat: beat+i/4. i/N/u describe selected order. Values are evaluated from the original row.'}
PARENT = {'oneOf':[S,{'type':'null'}]}
EASING_NAMES = ['linear'] + ['ease_'+direction+'_'+family for family in ('sine','quad','cubic','quart','quint','expo','circ','back','elastic','bounce') for direction in ('in','out','in_out')]
EASING = {'oneOf':[obj({'type':{'enum':EASING_NAMES}},('type',)),obj({'type':{'const':'custom'},**{k:N for k in ('x1','y1','x2','y2')}},('type','x1','y1','x2','y2')),obj({'type':{'const':'steps'},'count':{'type':'integer','minimum':1,'maximum':10000}},('type','count')),obj({'type':{'const':'elastic'},'omega':{'type':'number','exclusiveMinimum':0}},('type','omega'))]}
CURVE = copy.deepcopy(server.CURVE_OPTIONS)
CURVE['properties']['curve']=EASING


def guarded(properties, write=False, required=()):
    return obj({**(WRITE if write else READ),**properties},('session','revision',*(('dry_run',) if write else ()),*required))


EXTRA_TOOLS = [
 tool('editor_context','Start here. Live session/revision, selected IDs, lines, BPM/offset, time, undo author and available tools. No offline chart state.',obj({}),True),
 tool('chart_templates','Complete PhiChain native templates, valid easing shapes and script API. RPE JSON fields and fake notes are not accepted by this native editor.',obj({}),True),
 tool('chart_read','Read a guarded live native document by JSON Pointer. Root returns counts/metadata; /notes, /lines, /events and /curve_tracks return ID-keyed rows with pagination. Specific paths return exact data. No implicit visual-lifetime filtering.',guarded({'path':PATH,**PAGING,'fields':{'type':'array','items':PATH,'maxItems':30}}),True),
 tool('chart_query','Query one native collection with field predicates, beat overlap, sort and projection. Returns stable editable IDs. Time overlap is not visible lifetime. For notes 1–41, explicitly choose ordering and limit=41; do not substitute beats.',guarded({'collection':COLLECTION,'start':N,'end':N,**PAGING,'sort':PATH,'fields':{'type':'array','items':PATH,'maxItems':30},'where':{'type':'array','maxItems':20,'items':obj({'path':PATH,'op':{'enum':['eq','ne','lt','lte','gt','gte','contains']},'value':{}},('path','op','value'))}},required=('collection',)),True),
 tool('chart_patch','Atomically set/remove/insert document fields via JSON Pointer. Modify only requested fields. insert adds new:name objects; new lines and dependent notes/events can be inserted together. Editor validates all identities/references before one shared undo step.',guarded({'operations':{'type':'array','minItems':1,'maxItems':2000,'items':{'oneOf':[obj({'op':{'enum':['set','insert']},'path':PATH,'value':{}},('op','path','value')),obj({'op':{'const':'remove'},'path':PATH},('op','path'))]}}},True,('operations',)),destructive=True),
 tool('chart_transform','Host-evaluated batch numeric changes/removal across an ID-keyed collection. ids and where intersect. Paths relative to each row, e.g. /note/x. Numeric native fields plus beat,i,N,u and sin/cos/clamp/lerp/ease are available. One candidate/undo step; full references validated. Requires Node.js 22.13+.',guarded({'path':{'enum':['/'+k for k in authoring.COLLECTIONS]},'ids':IDS,'where':S,'expressions':EXPRS,'remove':BOOL},True,('path',)),destructive=True),
 tool('chart_generate','Append 1–10,000 complete native template rows with numeric expressions. /note/beat and event beat fields accept numeric results converted to canonical beat fractions. Unique new:prefix:i aliases resolve in one native commit. Requires Node.js 22.13+.',guarded({'path':{'enum':['/'+k for k in authoring.COLLECTIONS]},'count':{'type':'integer','minimum':1,'maximum':10000},'template':{'type':'object'},'expressions':EXPRS,'prefix':{'type':'string','maxLength':40}},True,('path','count','template')),destructive=True),
 tool('chart_script','Run synchronous JavaScript over a freshly captured complete native chart document. chart contains ID-keyed lines/notes/events/curve_tracks, meta,bpm_list,offset. api provides constructors, id(), fromNumber(), beatValue(), clone(), report(). Return {chart,result} or mutate chart. No editor/DOM/require/process/network/file APIs exposed; computation is timed and Node permission-restricted. Full native validation and one shared undo step. Use dry_run first. No parallel persistent chart state.',guarded({'source':{'type':'string','maxLength':200000},'input':{},'timeout_ms':{'type':'integer','minimum':100,'maximum':30000}},True,('source',)),destructive=True),
 tool('line_manage','Native ID-preserving line create/duplicate/delete/reorder/parent/rename. Duplicate copies a complete subtree and remaps curve references. New lines use new:name alias and receive missing baseline channels (opacity 255, speed 10, position/rotation zero). Explicit channels are preserved. Delete populated subtrees requires cascade=true. Parent changes preserve local coordinates, not screen-space motion.',guarded({'action':{'enum':['create','duplicate','delete','reorder','parent','rename']},'line_id':ID,'alias':S,'name':{'type':'string','maxLength':256},'parent_id':PARENT,'line_ids':IDS,'cascade':BOOL},True,('action',)),destructive=True),
 tool('bpm_set','Set a complete BPM list; first point at beat zero, strictly increasing, 1–1000 BPM. Uses native timing and shared undo.',guarded({'bpm_list':server.BPM_LIST},True,('bpm_list',)),destructive=True),
 tool('curve_notes','Create a native generated curve track between two existing editable notes on one line. Endpoints remain unchanged, generated notes are derived and not directly editable. For arbitrary note sequences use chart_generate/chart_script.',guarded({'line_id':ID,'from_id':ID,'to_id':ID,'options':CURVE,'alias':S},True,('line_id','from_id','to_id','options')),destructive=True),
 tool('editor_entities','Find named native lines or editable IDs without confusing numeric names with beats. Uses the guarded live document.',guarded({'collection':COLLECTION,'query':S,**PAGING}),True),
 tool('editor_navigate','Seek shared preview using explicit audio_seconds, chart_seconds or global_beat; convert using native BPM/offset. Does not retime chart objects.',guarded({'unit':{'enum':['audio_seconds','chart_seconds','global_beat']},'value':{'type':'number','minimum':0},'action':{'enum':['seek','play','pause']}},required=('unit','value'))),
 tool('editor_view','Select explicit native object IDs and optionally a line in the shared editor. Does not mutate chart data. Requires an idle editor.',guarded({'ids':{'type':'array','items':ID,'maxItems':1000,'uniqueItems':True},'line_id':ID},required=('ids',))),
 tool('diagnose','Run native chart validation on this guarded live revision. Structural/motion warnings are not an aesthetic or human-playability proof.',guarded({}),True),
 tool('chart_tools','Return actual available command schemas. All are already callable through tools/list; no second model loop or hidden command activation.',obj({'query':S,'names':{'type':'array','items':S,'maxItems':50}}),True),
 tool('agent_tools','Discover actual advertised tool names, descriptions and schemas. Does not activate hidden tools.',obj({'query':S,'names':{'type':'array','items':S,'maxItems':50}}),True),
 tool('project_save','Save the live editor project using current session/revision. Use when requested. Other writes remain in memory until save/autosave.',guarded({}),destructive=True),
]
TOOLS = server.TOOLS + EXTRA_TOOLS
BY_NAME = {t['name']:t for t in TOOLS}
assert len(BY_NAME)==len(TOOLS)
INSTRUCTIONS = '''Use the live PhiChain editor as the only source of truth. Start with editor_context, then chart_read/chart_query and relevant parent/event data. Notes means playable note objects, not beats. New object keys use unique new:name aliases and can reference each other in one candidate. Prefer chart_patch for local fields, chart_transform for repeated changes, chart_generate for sequences, chart_script for arbitrary multi-object algorithms. Read chart_templates before constructing objects. Always validate with dry_run=true first; then commit with current session/revision and dry_run=false. Dry runs are computations, not prepared-plan tokens. Writes use native PhiChain data, not RPE JSON. Preserve judgments unless explicitly requested. Review actual renders using inspect_motion/preview_passage; include full visibility and hold tails. Reread on stale state. After timeouts inspect before retrying. Shared undo requires matching human/agent author. Save only when requested.'''


def templates():
    return {
      'line':{'name':'Carrier','role':'simple','parent_id':None,'order':0},
      'note':{'line_id':'<existing ID or new:line>','note':{'kind':'tap','above':True,'beat':[0,0,1],'x':0,'speed':1}},
      'hold':{'line_id':'<existing ID or new:line>','note':{'kind':'hold','hold_beat':[1,0,1],'above':True,'beat':[0,0,1],'x':0,'speed':1}},
      'event':{'line_id':'<existing ID or new:line>','event':{'kind':'x','start_beat':[0,0,1],'end_beat':[4,0,1],'value':{'type':'transition','start':0,'end':100,'easing':{'type':'linear'}}}},
      'curve_track':{'line_id':'<line ID>','from_id':'<note ID>','to_id':'<note ID>','options':{'kind':'drag','density':16,'curve':{'type':'linear'}}},
      'easing_schema':EASING,
      'script_api':{'createNote':'(kind="tap",beat=0,x=0,hold=1) -> note value; wrap with {line_id,note}', 'createLine':'(name="Carrier",order=0,parent_id=null) -> line row', 'createEvent':'(kind,startBeat,endBeat,startValue,endValue,easing={type:"linear"}) -> event value; wrap with {line_id,event}', 'fromNumber':'numeric beat -> canonical [whole,numerator,denominator] (1/10000 resolution)', 'beatValue':'beat array -> number','id':'(prefix) -> local new: alias; avoid existing aliases','clone':'JSON clone','report':'append a JSON result'},
      'new_line_defaults':'New lines receive missing x/y/rotation=0, opacity=255, speed=10 channels. Explicit channels are preserved. Changes appear in dry-run diffs.',
      'limits':{'editable_objects':20000,'mcp_request_bytes':1048576,'candidate_bridge_bytes':16777216,'script_output_bytes':8388608,'script_timeout_ms':[100,30000]},
    }


class AgentServer(server.Server):
    def __init__(self, endpoint, renderer=None):
        super().__init__(endpoint,renderer,catalog=TOOLS,executor=self.execute,instructions=INSTRUCTIONS)
    def execute(self,name,args):
        if name=='line_manage':
            required={'create':['alias','name'],'duplicate':['line_id','alias'],'delete':['line_id'],'reorder':['line_ids'],'parent':['line_id','parent_id'],'rename':['line_id','name']}[args['action']]
            for key in required:
                if key not in args: raise ValueError(key+' is required for '+args['action'])
        if name=='chart_transform' and not args.get('remove') and not args.get('expressions'):
            raise ValueError('Supply expressions or remove=true')
        if name in ('chart_transform','chart_generate'):
            for value in args.get('expressions',{}).values():
                if not isinstance(value,str): raise ValueError('Expressions must be strings')
        return authoring.execute(name,args,lambda method,arguments:server.call_editor(self.endpoint,method,arguments),TOOLS)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--endpoint',required=True)
    parser.add_argument('--renderer')
    options=parser.parse_args()
    instance=AgentServer(options.endpoint,options.renderer)
    for line in sys.stdin:
        try:
            if len(line.encode('utf-8'))>server.MAX_MESSAGE: raise ValueError('MCP request exceeds 1 MiB')
            request=json.loads(line,parse_constant=lambda v:(_ for _ in ()).throw(ValueError('Invalid number: '+v)))
            response=instance.dispatch(request) if isinstance(request,dict) else instance.error(None,-32600,'Request must be an object')
        except (ValueError,RecursionError) as error: response=instance.error(None,-32700,str(error))
        if response is not None: print(json.dumps(response,ensure_ascii=False,allow_nan=False),flush=True)


if __name__=='__main__': main()
