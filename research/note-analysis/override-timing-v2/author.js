// Invoked through a fresh guarded live chart_script, never written as chart state.
if (Object.keys(chart.notes).length || Object.keys(chart.curve_tracks).length || Object.keys(chart.lines).length > 1) {
  throw Error('Expected a new empty experiment; existing notes are preserved.');
}
chart.lines = {};
chart.events = {};
chart.meta.name = 'Override - Timing v2';
chart.meta.level = 'Analysis / 3 frequency bands';
chart.meta.charter = 'Spectral onset evidence';
input.tracks.forEach((track, i) => {
  const line = 'new:onset_line:' + i;
  chart.lines[line] = api.createLine(track.name, i);
  const constants = {x:track.center, y:-180, rotation:0, speed:10.35, opacity:i===0?180:0};
  Object.entries(constants).forEach(([kind,value]) => {
    chart.events['new:onset_event:' + i + ':' + kind] = {line_id:line,
      event:{kind,start_beat:input.range_start,end_beat:input.range_end,value:{type:'constant',value}}};
  });
});
input.rows.forEach((row,i) => {
  chart.notes['new:onset_note:' + i] = {line_id:'new:onset_line:'+row.track,
    note:{kind:'tap',above:true,beat:row.beat,x:row.x,speed:1}};
});
return {chart,result:{notes:input.rows.length,tracks:3,
  explanation:'Low/mid/high spectral-change evidence; track-local x encodes relative attack strength, not difficulty.',
  diagnostic_only:true}};
