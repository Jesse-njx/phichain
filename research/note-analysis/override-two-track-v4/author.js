if (Object.keys(chart.notes).length || Object.keys(chart.curve_tracks).length || Object.keys(chart.lines).length>1) {
  throw Error('Only a new empty analysis project is accepted.');
}
chart.lines={};chart.events={};
chart.meta.name='Override - Drums and Main Melody';
chart.meta.level='Analysis / 2 roles / conservative';
chart.meta.charter='HTDemucs + Basic Pitch + voice heuristics';
input.tracks.forEach((track,i)=>{
  const line='new:voice_line:'+i;
  chart.lines[line]=api.createLine(track.name,i);
  Object.entries({x:(i-.5)*500,y:-200,rotation:0,speed:10.35}).forEach(([kind,value])=>{
    chart.events['new:voice_event:'+i+':'+kind]={line_id:line,event:{kind,start_beat:input.start,end_beat:input.end,value:{type:'constant',value}}};
  });
  const intervals=i===0?input.opacity:[{start:input.start,end:input.end,value:0}];
  intervals.forEach((a,j)=>{chart.events['new:voice_alpha:'+i+':'+j]={line_id:line,event:{kind:'opacity',start_beat:a.start,end_beat:a.end,value:{type:'constant',value:a.value}}};});
});
input.events.forEach((e,i)=>{
  const note={kind:e.kind,above:true,beat:e.beat,x:e.x,speed:1};
  if(e.kind==='hold')note.hold_beat=e.hold_beat;
  chart.notes['new:voice_note:'+i]={line_id:'new:voice_line:'+e.track,note};
});
return {chart,result:{events:input.events.length,tracks:2,diagnostic_only:true,
  interpretation:'Conservative drums and main-melody estimates; holds show estimated sustain, horizontal variation follows pitch.'}};
