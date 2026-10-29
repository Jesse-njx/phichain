//! Read-only sampling of selected notes, using the renderer's event and scroll math.
use super::quality::{position, LineInfo};
use super::*;
use phichain_chart::constants::CANVAS_WIDTH;
use phichain_game::core::{distance_at, SpeedSegment};
use std::collections::{BTreeSet, HashMap};

pub(super) fn inspect(w: &mut World, args: &Value, data: &Value) -> Result<Value> {
    check_revision(args, data)?;
    idle(w)?;
    let from = args["from_seconds"]
        .as_f64()
        .context("from_seconds is required")?;
    let to = args["to_seconds"]
        .as_f64()
        .context("to_seconds is required")?;
    let count = args
        .get("frames")
        .map(|v| v.as_u64().context("frames must be an integer"))
        .transpose()?
        .unwrap_or(6);
    if !from.is_finite()
        || !to.is_finite()
        || from < 0.0
        || to > 86400.0
        || to <= from
        || to - from > 12.0
        || !(2..=12).contains(&count)
    {
        bail!("Use a range inside 0–86400 seconds, at most 12 seconds long, and 2–12 frames")
    }
    let mut ids = if let Some(ids) = args.get("note_ids") {
        ids.as_array()
            .context("note_ids must be an array")?
            .iter()
            .map(|v| entity(&json!({"id":v}), "id"))
            .collect::<Result<Vec<_>>>()?
    } else {
        w.query_filtered::<Entity, (
            With<Note>,
            With<Selected>,
            Without<CurveNote>,
            Without<Pending>,
        )>()
        .iter(w)
        .collect()
    };
    if ids.is_empty() || ids.len() > 32 {
        bail!("Select or supply 1–32 editable note IDs")
    }
    ids.sort_by_key(|e| e.to_bits());
    if ids.windows(2).any(|pair| pair[0] == pair[1]) {
        bail!("Duplicate note IDs")
    }
    let mut notes = Vec::new();
    for e in ids {
        if w.get::<CurveNote>(e).is_some() || w.get::<Pending>(e).is_some() {
            bail!("Generated or pending notes are not inspectable targets")
        }
        notes.push((
            e,
            *w.get::<Note>(e).context("Unknown note ID")?,
            w.get::<ChildOf>(e).context("Note has no line")?.parent(),
        ));
    }
    let mut lines: HashMap<_, _> = w
        .query::<(Entity, &Line, Option<&ChildOf>)>()
        .iter(w)
        .map(|(e, _, p)| {
            (
                e,
                LineInfo {
                    parent: p.map(|p| p.parent()),
                    events: vec![],
                },
            )
        })
        .collect();
    for (event, parent) in w
        .query_filtered::<(&LineEvent, &EventOf), Without<Pending>>()
        .iter(w)
    {
        if let Some(l) = lines.get_mut(&parent.target()) {
            l.events.push(*event);
        }
    }
    let mut related = HashSet::new();
    for (_, _, line) in &notes {
        let mut next = Some(*line);
        let mut seen = HashSet::new();
        while let Some(e) = next {
            if !seen.insert(e) {
                bail!("Line hierarchy cycle")
            }
            related.insert(e);
            next = lines.get(&e).context("Unknown carrier or ancestor")?.parent;
        }
    }
    if related.len() > 128 {
        bail!("At most 128 carrier/ancestor lines can be inspected")
    }
    let mut related: Vec<_> = related.into_iter().collect();
    related.sort_by_key(|e| e.to_bits());
    let bpm = w.resource::<BpmList>();
    let offset = w.resource::<Offset>().0 / 1000.0;
    let height = CANVAS_WIDTH * 9.0 / 16.0;
    let pixel = |p: Vec2| json!({"x":(p.x / CANVAS_WIDTH + 0.5)*960.0,"y":(0.5-p.y/height)*540.0});
    let point = |line, beat, p| position(&lines, line, beat, p, height, &mut HashSet::new());
    let mut speeds = HashMap::new();
    for &e in &related {
        let mut segments: Vec<_> = lines[&e]
            .events
            .iter()
            .filter(|v| v.kind.is_speed())
            .map(|v| SpeedSegment {
                start_time: bpm.time_at(v.start_beat),
                end_time: bpm.time_at(v.end_beat),
                start_value: v.value.start(),
                end_value: v.value.end(),
            })
            .collect();
        segments.sort_by(|a, b| a.start_time.total_cmp(&b.start_time));
        speeds.insert(e, segments);
    }
    // Quantize samples to the exact 30 fps render lattice, relative to `from`.
    let times: Vec<_> = (0..count)
        .map(|i| from + ((to - from) * 30.0 * i as f64 / (count - 1) as f64).round() / 30.0)
        .collect();
    if let Some(duration) = w.get_resource::<phichain_game::audio::AudioDuration>() {
        if times.last().unwrap() + 1.0 / 30.0 > duration.0.as_secs_f64() {
            bail!("Inspection frames must be inside the audio duration")
        }
    }
    let mut frames = Vec::new();
    for &seconds in &times {
        let time = seconds as f32 - offset;
        let beat: f32 = bpm.beat_at(time).into();
        let mut ns = Vec::new();
        for (e, n, line) in &notes {
            let hit = bpm.time_at(n.beat);
            let end = match n.kind {
                NoteKind::Hold { hold_beat } => bpm.time_at(n.beat + hold_beat),
                _ => hit,
            };
            let scroll = |t| distance_at(&speeds[line], t) * height * (120.0 / 900.0);
            let raw_y = (scroll(hit) - scroll(time)) * n.speed;
            let holding = matches!(n.kind, NoteKind::Hold { .. });
            let y = if holding { raw_y.max(0.0) } else { raw_y };
            let tail_y = (scroll(end) - scroll(time)) * n.speed;
            let sign = if n.above { 1.0 } else { -1.0 };
            let (head, _, _) = point(*line, beat, Vec2::new(n.x, y * sign))?;
            let (tail, _, _) = point(*line, beat, Vec2::new(n.x, tail_y * sign))?;
            let visible = time <= end
                && if holding {
                    tail_y - y >= 0.0
                } else {
                    raw_y >= 0.0
                };
            ns.push(json!({"id":id(*e),"line_id":id(*line),"head":pixel(head),"tail":holding.then(||pixel(tail)),
                "visible_by_timing_and_cover":visible,"head_in_view":head.x.abs()<=CANVAS_WIDTH/2.0 && head.y.abs()<=height/2.0,
                "approach_distance":raw_y,"judged":time>hit}));
        }
        let mut ls = Vec::new();
        for &e in &related {
            let (origin, alpha, speed) = point(e, beat, Vec2::ZERO)?;
            let (axis, _, _) = point(e, beat, Vec2::X)?;
            let angle = (axis - origin).to_angle().to_degrees();
            ls.push(json!({"id":id(e),"origin":pixel(origin),"rotation_degrees":angle,"opacity":alpha/255.0,"scroll_speed":speed}));
        }
        frames
            .push(json!({"time_seconds":seconds,"chart_time_seconds":time,"notes":ns,"lines":ls}));
    }
    let mut targets = Vec::new();
    for (e, n, line) in &notes {
        let (landing, _, _) = point(*line, n.beat.value(), Vec2::new(n.x, 0.0))?;
        targets.push(json!({"id":id(*e),"line_id":id(*line),"note":n,"hit_seconds":bpm.time_at(n.beat)+offset,"landing":pixel(landing)}));
    }
    let related_ids: BTreeSet<_> = related.iter().map(|e| id(*e)).collect();
    let line_rows: Vec<_> = data["lines"]
        .as_array()
        .unwrap()
        .iter()
        .filter(|l| related_ids.contains(l["id"].as_str().unwrap()))
        .map(|l| {
            let mut l = l.clone();
            l["editable_note_count"] = json!(data["notes"]
                .as_array()
                .unwrap()
                .iter()
                .filter(|n| n["line_id"] == l["id"])
                .count());
            l
        })
        .collect();
    let from_beat: f32 = bpm.beat_at(from as f32 - offset).into();
    let to_beat: f32 = bpm.beat_at(*times.last().unwrap() as f32 - offset).into();
    let all_events: Vec<_> = data["events"]
        .as_array()
        .unwrap()
        .iter()
        .filter(|v| related_ids.contains(v["line_id"].as_str().unwrap()))
        .collect();
    // Include overlapping events and the latest inherited value per line/channel.
    let mut inherited: HashMap<(String, String), (&Value, f64)> = HashMap::new();
    let mut events = Vec::new();
    for row in all_events {
        let ev = &row["event"];
        let start = beat_value(&ev["start_beat"]);
        let end = beat_value(&ev["end_beat"]);
        if start <= to_beat as f64 && end >= from_beat as f64 {
            events.push(row.clone());
        } else if end < from_beat as f64 {
            let key = (row["line_id"].to_string(), ev["kind"].to_string());
            if inherited.get(&key).is_none_or(|(_, old)| end > *old) {
                inherited.insert(key, (row, end));
            }
        }
    }
    events.extend(inherited.into_values().map(|(v, _)| v.clone()));
    events.sort_by(|a, b| a["id"].as_str().cmp(&b["id"].as_str()));
    let event_count = events.len();
    events.truncate(4000);
    let chart = w
        .run_system_once(|c: SerializeChartParam, l: SerializeLineParam| serialize_chart(c, l))
        .map_err(|e| anyhow!("{e}"))?;
    let project = w.resource::<Project>();
    Ok(
        json!({"session":data["session"],"revision":data["revision"],"width":960,"height":540,"fps":30,
        "notes":targets,"lines":line_rows,"events":events,"event_count":event_count,"events_truncated":event_count>4000,"frames":frames,
        "coordinates":"pixels, top-left origin; diagnostic geometry uses native event/scroll math at 16:9",
        "limitations":["Targets are editable notes only; rendered scene includes generated curves and all other notes.","Timing/cover visibility is not an occlusion or playability test.","Source events include overlapping and latest inherited events; scroll samples integrate the full live history.","Rendering uses default renderer styling, not the editor's custom skin or UI."],
        "_render_snapshot":{"chart":chart,"meta":project.meta,"music_path":project.path.music_path(),"illustration_path":project.path.illustration_path()}}),
    )
}
