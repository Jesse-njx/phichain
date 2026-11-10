// Computational child process. No editor connection or mutable chart persistence.
import vm from 'node:vm';
import { compileExpression } from './vendor/rpe-next/batch-script.mjs';

let inputText = '';
for await (const chunk of process.stdin) {
  inputText += chunk;
  if (inputText.length > 16 * 1024 * 1024) throw Error('Computation input exceeds 16 MiB');
}
const request = JSON.parse(inputText);
const { mode, document, args } = request;
const clone = value => JSON.parse(JSON.stringify(value));
function pathParts(path) {
  if (typeof path !== 'string' || !path.startsWith('/')) throw Error('Expected JSON Pointer');
  return path.slice(1).split('/').map(s => s.replace(/~1/g, '/').replace(/~0/g, '~'));
}
function get(root, path) {
  for (const part of pathParts(path)) {
    if (!root || !Object.hasOwn(root, part)) throw Error('Unknown path: ' + path);
    root = root[part];
  }
  return root;
}
function set(root, path, value) {
  const parts = pathParts(path), last = parts.pop();
  for (const part of parts) {
    if (!root || !Object.hasOwn(root, part)) throw Error('Unknown field: ' + path);
    root = root[part];
  }
  if (!Object.hasOwn(root, last)) throw Error('Unknown field: ' + path);
  Object.defineProperty(root, last, { value, enumerable: true, configurable: true, writable: true });
}
function fromNumber(value) {
  if (!Number.isFinite(value) || Math.abs(value) > 1000000) throw Error('Invalid beat');
  let whole = Math.floor(value), numerator = Math.round((value - whole) * 10000), denominator = 10000;
  if (numerator === denominator) { whole++; numerator = 0; }
  const gcd = (a,b) => b ? gcd(b,a%b) : a;
  const d = gcd(numerator,denominator);
  return [whole,numerator/d,denominator/d];
}
const beatValue = v => Array.isArray(v) ? v[0] + v[1] / v[2] : Number(v);
function scope(row, id, i, N) {
  const value = row.note ?? row.event ?? row;
  return Object.assign(Object.create(null), Object.fromEntries(Object.entries(value).filter(([,v])=>typeof v==='number')), {
    i,N,u:N<=1?0:i/(N-1), beat:value.beat ? beatValue(value.beat) : value.start_beat ? beatValue(value.start_beat) : 0,
  });
}
let result = {};
try {
  if (mode === 'script') {
    // Only a primitive JSON string crosses into the context. No host objects,
    // functions, require, process, import callback, fetch, or editor APIs supplied.
    const context = vm.createContext({ payload: JSON.stringify({document,input:args.input}) }, { codeGeneration:{strings:false,wasm:false} });
    const prelude = `"use strict";
      const originalStringify = JSON.stringify.bind(JSON);
      const received = JSON.parse(payload);
      delete globalThis.payload;
      const chart = received.document, logs = [];
      const fromNumber = ${fromNumber.toString()};
      const beatValue = v => Array.isArray(v) ? v[0] + v[1] / v[2] : Number(v);
      let sequence = 0;
      const api = Object.freeze({ fromNumber, beatValue,
        clone: value => JSON.parse(originalStringify(value)), report: value => logs.push(value),
        id: prefix => 'new:' + (prefix || 'object') + ':' + (++sequence),
        createNote: (kind='tap',beat=0,x=0,hold=1) => ({kind,above:true,beat:fromNumber(beat),x,speed:1,...(kind==='hold'?{hold_beat:fromNumber(hold)}:{})}),
        createLine: (name='Carrier',order=0,parent_id=null) => ({name,role:'simple',order,parent_id}),
        createEvent: (kind,start,end,from,to,easing={type:'linear'}) => ({kind,start_beat:fromNumber(start),end_beat:fromNumber(end),value:{type:'transition',start:from,end:to,easing}})
      });
      const returned = (function(chart,api,input){\n${args.source}\n})(chart,api,received.input);
      if (returned && typeof returned.then === 'function') throw Error('Async scripts are not supported');
      const output = originalStringify({document:returned?.chart ?? chart,result:returned?.result ?? logs});
      if (output.length > 8*1024*1024) throw Error('Script output exceeds 8 MiB');
      output;`;
    result = JSON.parse(new vm.Script(prelude, {filename:'chart-script.js'}).runInContext(context, {timeout:args.timeout_ms ?? 10000}));
  } else if (mode === 'transform' || mode === 'generate') {
    const collection = get(document,args.path);
    if (!collection || typeof collection!=='object' || Array.isArray(collection)) throw Error('Expected an ID-keyed collection');
    const expressions = Object.entries(args.expressions ?? {}).map(([path,source]) => [path,compileExpression(source)]);
    if (expressions.length>64) throw Error('At most 64 expressions');
    const evaluate = (row,environment) => {
      const values = expressions.map(([path,expression])=>[path,expression(environment)]);
      for (let [path,value] of values) {
        if (/\/(?:beat|start_beat|end_beat|hold_beat)$/.test(path)) value=fromNumber(value);
        set(row,path,value);
      }
      return row;
    };
    if (mode==='transform') {
      const entries=Object.entries(collection), filter=args.where ? compileExpression(args.where) : ()=>true;
      if (args.ids) for(const id of args.ids) if(!Object.hasOwn(collection,id)) throw Error('Unknown target ID: '+id);
      const chosen=entries.filter(([id,row],i)=>(!args.ids || args.ids.includes(id)) && filter(scope(row,id,i,entries.length)));
      if(!chosen.length) throw Error('No matching objects');
      chosen.forEach(([id,row],i)=>{ if(args.remove) delete collection[id]; else collection[id]=evaluate(clone(row),scope(row,id,i,chosen.length)); });
      result={document,result:{count:chosen.length,ids:chosen.map(([id])=>id)}};
    } else {
      const created=[];
      for(let i=0;i<args.count;i++) {
        const id=`new:${args.prefix ?? 'generated'}:${i}`;
        if(Object.hasOwn(collection,id)) throw Error('Alias collision: '+id);
        collection[id]=evaluate(clone(args.template),scope(args.template,id,i,args.count)); created.push(id);
      }
      result={document,result:{count:created.length,aliases:created}};
    }
  } else throw Error('Unknown computation mode');
  const encoded=JSON.stringify(result, (_key,value)=>{if(typeof value==='number'&&!Number.isFinite(value))throw Error('Non-finite result');return value;});
  if(encoded.length>8*1024*1024) throw Error('Computation output exceeds 8 MiB');
  process.stdout.write(encoded);
} catch(error) {
  process.stdout.write(JSON.stringify({error:String(error.message ?? error)}));
  process.exitCode=1;
}
