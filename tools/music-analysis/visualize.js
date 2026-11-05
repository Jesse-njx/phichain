// Runs ONLY inside the existing guarded live chart_script tool.
if (Object.keys(chart.notes).length || Object.keys(chart.curve_tracks).length || Object.keys(chart.lines).length > 1) {
  throw Error('A new empty experiment project is required; no authored objects are replaced');
}
// Replace only the empty project's default carrier/events. This diagnostic
// arrangement intentionally uses fixed tracks, not a two-finger gameplay design.
chart.lines = {};
chart.events = {};
chart.meta.name = input.title;
chart.meta.level = 'Analysis / ' + input.tracks.length + ' ' + input.group_by + ' tracks';
chart.meta.charter = 'Audio analysis visualization';
input.tracks.forEach((track, i) => {
  const line = 'new:viz_line:' + i;
  chart.lines[line] = api.createLine(track.name, i);
  for (const [kind, value] of Object.entries({x:track.center, y:-180, rotation:0, speed:10.35})) {
    chart.events['new:viz_event:' + i + ':' + kind] = {line_id:line,
      event:{kind, start_beat:input.range_start, end_beat:input.range_end, value:{type:'constant',value}}};
  }
  const intervals = i === 0 ? input.opacity : [{start:input.range_start, end:input.range_end, value:0}];
  intervals.forEach((item,j) => {
    chart.events['new:viz_opacity:' + i + ':' + j] = {line_id:line,
      event:{kind:'opacity', start_beat:item.start, end_beat:item.end, value:{type:'constant',value:item.value}}};
  });
});
input.rows.forEach((row, i) => {
  const note = {kind:row.kind, above:true, beat:row.beat, x:row.x, speed:1};
  if (row.kind === 'hold') note.hold_beat = row.hold_beat;
  chart.notes['new:viz_note:' + i] = {line_id:'new:viz_line:' + row.track, note};
});
return {chart, result:{notes:input.rows.length, tracks:input.tracks.length,
  grouping:input.group_by, intensity:'Left to right within each track, 0 to 100',
  climax:'Shared judgment line brightens during candidate climax regions',
  diagnostic_only:true}};
