use super::*;
use phichain_chart::{
    constants::{CANVAS_HEIGHT, CANVAS_WIDTH},
    event::{EventEvaluationResult, LineEventKind},
};
use std::collections::HashMap;

pub fn select_objects(w: &mut World, args: &Value, data: &Value) -> Result<Value> {
    if args["session"] != data["session"] {
        bail!("Project changed; read context again")
    }
    idle(w)?;
    let values = args["ids"].as_array().context("ids must be an array")?;
    if values.len() > 1000 {
        bail!("Select at most 1000 objects")
    }
    let targets: Vec<_> = values
        .iter()
        .map(|v| entity(&json!({"id":v}), "id"))
        .collect::<Result<_>>()?;
    for &e in &targets {
        if !(w.get::<Note>(e).is_some()
            || w.get::<LineEvent>(e).is_some()
            || w.get::<CurveNoteTrack>(e).is_some())
            || w.get::<CurveNote>(e).is_some()
        {
            bail!("Unknown or generated selection target")
        }
    }
    let line = args
        .get("line_id")
        .map(|_| entity(args, "line_id"))
        .transpose()?;
    if line.is_some_and(|e| w.get::<Line>(e).is_none()) {
        bail!("Unknown line")
    }
    let old: Vec<_> = w
        .query_filtered::<Entity, With<Selected>>()
        .iter(w)
        .collect();
    for e in old {
        w.entity_mut(e).remove::<Selected>();
    }
    for e in targets {
        w.entity_mut(e).insert(Selected);
    }
    if let Some(e) = line {
        w.insert_resource(SelectedLine(e));
    }
    Ok(context(w, data))
}

pub fn set_editor_view(w: &mut World, args: &Value, data: &Value) -> Result<Value> {
    use crate::layout::ui_state::UiState;
    use crate::timeline::settings::TimelineSettings;
    if args["session"] != data["session"] {
        bail!("Project changed; read context again")
    }
    idle(w)?;
    let zoom = args
        .get("zoom")
        .map(|v| v.as_f64().context("zoom must be numeric"))
        .transpose()?;
    if zoom.is_some_and(|v| !v.is_finite() || !(0.1..=5.0).contains(&v)) {
        bail!("Zoom must be 0.1–5")
    }
    let density = args
        .get("density")
        .map(|v| v.as_u64().context("density must be an integer"))
        .transpose()?;
    if density.is_some_and(|v| !(1..=256).contains(&v)) {
        bail!("Density must be 1–256")
    }
    let focus = args
        .get("focus_beat")
        .map(|v| v.as_f64().context("focus_beat must be numeric"))
        .transpose()?;
    if focus.is_some_and(|v| !v.is_finite() || !(0.0..=1000000.0).contains(&v)) {
        bail!("Invalid focus beat")
    }
    let layout = args
        .get("layout")
        .map(|v| v.as_str().context("layout must be a string"))
        .transpose()?;
    if layout.is_some_and(|s| !["default", "preview"].contains(&s)) {
        bail!("Unknown layout")
    }
    let spectrogram = args
        .get("show_spectrogram")
        .map(|v| v.as_bool().context("show_spectrogram must be boolean"))
        .transpose()?;
    if w.get_resource::<TimelineSettings>().is_none() {
        bail!("Timeline settings unavailable")
    }
    if layout.is_some() && w.get_resource::<UiState>().is_none() {
        bail!("Layout unavailable")
    }
    let mut settings = w.resource_mut::<TimelineSettings>();
    if let Some(v) = zoom {
        settings.zoom = v as f32;
    }
    if let Some(v) = density {
        settings.density = v as u32;
    }
    if let Some(v) = spectrogram {
        settings.show_spectrogram = v;
    }
    if let Some(layout) = layout {
        *w.resource_mut::<UiState>() = if layout == "default" {
            UiState::default()
        } else {
            UiState {
                state: egui_dock::DockState::new(vec!["game".into()]),
            }
        };
    }
    if let Some(beat) = focus {
        let seconds = w.resource::<BpmList>().time_at(Beat::from(beat as f32))
            + w.resource::<Offset>().0 / 1000.0;
        if w.get_resource::<Paused>().is_some_and(|p| !p.0) {
            w.trigger(Pause);
        }
        w.write_message(SeekTo(seconds));
    }
    let settings = w.resource::<TimelineSettings>();
    Ok(
        json!({"status":"requested","zoom":settings.zoom,"density":settings.density,"show_spectrogram":settings.show_spectrogram,"focus_beat":focus,"layout":layout}),
    )
}

fn evaluated(events: &[LineEvent], kind: LineEventKind, beat: f32, default: f32) -> f32 {
    events
        .iter()
        .filter(|e| e.kind == kind)
        .map(|e| e.evaluate_inclusive(beat))
        .max()
        .unwrap_or(EventEvaluationResult::Unaffected)
        .value()
        .unwrap_or(default)
}
#[derive(Clone)]
struct LineInfo {
    parent: Option<Entity>,
    events: Vec<LineEvent>,
}
fn position(
    lines: &HashMap<Entity, LineInfo>,
    line: Entity,
    beat: f32,
    point: Vec2,
    height: f32,
    seen: &mut HashSet<Entity>,
) -> Result<(Vec2, f32, f32)> {
    if !seen.insert(line) {
        bail!("Line hierarchy cycle")
    }
    let info = lines.get(&line).context("Note has unknown line")?;
    let x = evaluated(&info.events, LineEventKind::X, beat, 0.0);
    let y = evaluated(&info.events, LineEventKind::Y, beat, 0.0) * height / CANVAS_HEIGHT;
    let angle = evaluated(&info.events, LineEventKind::Rotation, beat, 0.0).to_radians();
    let rotation = Mat2::from_angle(angle);
    let local = rotation * point + Vec2::new(x, y);
    let opacity = evaluated(&info.events, LineEventKind::Opacity, beat, 0.0);
    let speed = evaluated(&info.events, LineEventKind::Speed, beat, 10.0);
    if let Some(parent) = info.parent {
        let (global, _, _) = position(lines, parent, beat, local, height, seen)?;
        // Line alpha does not propagate to children in the current game renderer.
        Ok((global, opacity, speed))
    } else {
        Ok((local, opacity, speed))
    }
}

pub fn validate_chart(w: &mut World, args: &Value, data: &Value) -> Result<Value> {
    let start = args
        .get("start_beat")
        .and_then(Value::as_f64)
        .unwrap_or(0.0);
    let end = args
        .get("end_beat")
        .and_then(Value::as_f64)
        .unwrap_or(1000001.0);
    let ratio = args
        .get("aspect_ratio")
        .and_then(Value::as_f64)
        .unwrap_or(16.0 / 9.0);
    let limit = args
        .get("max_contacts")
        .and_then(Value::as_u64)
        .unwrap_or(2);
    if !start.is_finite()
        || !end.is_finite()
        || start < 0.0
        || end <= start
        || !ratio.is_finite()
        || !(0.2..=5.0).contains(&ratio)
        || !(1..=10).contains(&limit)
    {
        bail!("Invalid validation range, aspect ratio or contact limit")
    }
    let height = CANVAS_WIDTH / ratio as f32;
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
    for (event, parent) in w.query::<(&LineEvent, &EventOf)>().iter(w) {
        if let Some(line) = lines.get_mut(&parent.target()) {
            line.events.push(*event);
        }
    }
    let mut notes: Vec<_> = w
        .query_filtered::<(Entity, &Note, &ChildOf), (Without<CurveNote>, Without<Pending>)>()
        .iter(w)
        .map(|(e, n, p)| (Some(e), *n, p.parent(), false))
        .collect();
    // Generate curves from current endpoints, even before the render cache refreshes.
    for (track, parent) in w.query::<(&CurveNoteTrack, &ChildOf)>().iter(w) {
        if let Some((from, to)) = track.get_entities() {
            if let (Some(from), Some(to)) = (w.get::<Note>(from), w.get::<Note>(to)) {
                if (1..=256).contains(&track.options.density)
                    && (to.beat - from.beat).value().abs() * track.options.density as f32 <= 10000.0
                {
                    notes.extend(
                        phichain_chart::curve_note_track::generate_notes(
                            *from,
                            *to,
                            &track.options,
                        )
                        .into_iter()
                        .map(|n| (None, n, parent.parent(), true)),
                    );
                }
            }
        }
    }
    notes.sort_by(|a, b| a.1.beat.cmp(&b.1.beat));
    let mut findings = Vec::new();
    let mut count = 0;
    let mut generated = 0;
    let mut maximum = 0;
    let mut duplicate: HashSet<String> = HashSet::new();
    let mut hits: std::collections::BTreeMap<Beat, Vec<(Option<Entity>, Entity, Vec2)>> =
        std::collections::BTreeMap::new();
    let mut previous_strikes: HashMap<(Entity, i32), (f32, Option<Entity>)> = HashMap::new();
    let mut add = |severity: &str,
                   code: &str,
                   e: Option<Entity>,
                   line: Entity,
                   beat: f32,
                   message: String| {
        if findings.len() < 2000 {
            findings.push(json!({"severity":severity,"code":code,"id":e.map(id),"line_id":id(line),"beat":beat,"message":message}));
        }
    };
    let duration = w
        .get_resource::<phichain_game::audio::AudioDuration>()
        .map(|d| d.0.as_secs_f32());
    let bpm = w.resource::<BpmList>();
    let offset = w.resource::<Offset>().0 / 1000.0;
    for &(e, n, line, is_generated) in &notes {
        let beat = n.beat.value();
        let tail = if let NoteKind::Hold { hold_beat } = n.kind {
            (n.beat + hold_beat).value()
        } else {
            beat
        };
        if beat as f64 >= end || (tail as f64) < start {
            continue;
        }
        count += 1;
        if is_generated {
            generated += 1;
        }
        if tail as f64 > end {
            add(
                "warning",
                "hold_crosses_boundary",
                e,
                line,
                beat,
                format!("Hold ends at beat {tail}, beyond requested end {end}"),
            );
        }
        let (point, opacity, speed) = position(
            &lines,
            line,
            beat,
            Vec2::new(n.x, 0.0),
            height,
            &mut HashSet::new(),
        )?;
        hits.entry(n.beat).or_default().push((e, line, point));
        if point.x.abs() > CANVAS_WIDTH / 2.0 || point.y.abs() > height / 2.0 {
            add(
                "warning",
                "offscreen_hit",
                e,
                line,
                beat,
                format!("Hit center is outside the {ratio:.3} aspect viewport"),
            );
        }
        if opacity <= 0.0 {
            add(
                "warning",
                "invisible_line",
                e,
                line,
                beat,
                "Judge line is invisible at this note's hit time".into(),
            );
        }
        if speed <= 0.0 {
            add(
                "warning",
                "nonpositive_scroll_speed",
                e,
                line,
                beat,
                "Line scroll speed is zero or negative".into(),
            );
        }
        let key = format!("{line:?}:{:?}:{}:{}", n.beat, n.x, n.above);
        if !duplicate.insert(key) {
            add(
                "warning",
                "duplicate_note",
                e,
                line,
                beat,
                "Multiple notes share beat, side and local x".into(),
            );
        }
        let seconds = bpm.time_at(n.beat) + offset;
        let tail_seconds = bpm.time_at(Beat::from(tail)) + offset;
        if matches!(n.kind, NoteKind::Tap | NoteKind::Flick) {
            if let Some((previous, _)) =
                previous_strikes.insert((line, (n.x / 10.0).round() as i32), (seconds, e))
            {
                let gap = seconds - previous;
                if gap > 0.0 && gap < 0.035 {
                    add(
                        "warning",
                        "rapid_repeat",
                        e,
                        line,
                        beat,
                        format!(
                            "Repeated strike in the same local lane after {:.1} ms",
                            gap * 1000.0
                        ),
                    );
                }
            }
        }
        if seconds < 0.0 || duration.is_some_and(|d| tail_seconds > d + 0.01) {
            add(
                "error",
                "outside_audio",
                e,
                line,
                beat,
                "Note/hold lies outside the audio duration".into(),
            );
        }
    }
    for (beat, group) in hits {
        for (i, (e, line, point)) in group.iter().take(256).enumerate() {
            for (_, other, other_point) in group.iter().take(i) {
                if other != line && point.distance(*other_point) < 20.0 {
                    add("warning","near_coincident_hit",*e,*line,beat.value(),"Different judge lines place simultaneous hit centers within 20 viewport units".into());
                }
            }
        }
    }
    // At each onset, active holds plus incoming notes form a conservative contact bound.
    let mut schedule: std::collections::BTreeMap<Beat, (usize, usize, usize)> =
        std::collections::BTreeMap::new();
    for (_, n, _, _) in &notes {
        schedule.entry(n.beat).or_default().0 += 1;
        if let NoteKind::Hold { hold_beat } = n.kind {
            schedule.entry(n.beat).or_default().1 += 1;
            schedule.entry(n.beat + hold_beat).or_default().2 += 1;
        }
    }
    let mut active = 0usize;
    for (time, (incoming, starting, ending)) in schedule {
        active = active.saturating_sub(ending);
        if (time.value() as f64) >= start && (time.value() as f64) < end && incoming > 0 {
            let contacts = incoming + active;
            maximum = maximum.max(contacts);
            if contacts > limit as usize {
                let line = notes.iter().find(|(_, n, _, _)| n.beat == time).unwrap().2;
                add("warning","contact_demand",None,line,time.value(),format!("Conservative demand: {contacts} contacts (limit {limit}); drags may be shared by one finger"));
            }
        }
        active += starting;
    }
    for (&line, info) in &lines {
        for kind in [LineEventKind::Opacity, LineEventKind::Speed] {
            if !info.events.iter().any(|e| e.kind == kind) {
                add(
                    "warning",
                    "missing_line_event",
                    None,
                    line,
                    start as f32,
                    format!("Missing {kind:?} event"),
                );
            }
        }
        for (i, a) in info.events.iter().enumerate() {
            for b in &info.events[i + 1..] {
                if a.kind == b.kind
                    && a.start_beat < b.end_beat
                    && b.start_beat < a.end_beat
                    && (a.start_beat.value() as f64) < end
                    && (b.end_beat.value() as f64) > start
                {
                    add(
                        "warning",
                        "overlapping_events",
                        None,
                        line,
                        a.start_beat.value().max(b.start_beat.value()),
                        format!(
                            "Overlapping {:?} events use PhiChain's maximum-value precedence",
                            a.kind
                        ),
                    );
                }
            }
        }
    }
    let errors = findings.iter().filter(|v| v["severity"] == "error").count();
    Ok(
        json!({"session":data["session"],"revision":data["revision"],"start_beat":start,"end_beat":end,
        "notes_checked":count,"generated_notes_checked":generated,"maximum_contacts":maximum,"contact_model":"conservative onsets plus active holds; not a playability proof",
        "aspect_ratio":ratio,"valid":errors==0,"errors":errors,"findings":findings,"findings_truncated":findings.len()==2000}),
    )
}
