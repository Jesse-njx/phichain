//! Explicit motion groups on existing, fully owned carriers. Never allocates a line per note.
use super::*;

pub fn animate(w: &mut World, args: &Value, data: &Value) -> Result<Value> {
    check_revision(args, data)?;
    idle(w)?;
    validate_beats(args)?;
    let dry_run = args["dry_run"]
        .as_bool()
        .context("dry_run must be explicit")?;
    let budget = args
        .get("line_budget")
        .map(|v| v.as_u64().context("Invalid line_budget"))
        .transpose()?
        .unwrap_or(24);
    let total = data["lines"].as_array().unwrap().len();
    if budget == 0 || budget > 1024 || total > budget as usize {
        bail!("Chart has {total} total lines (including decorative lines); explicitly choose an adequate line_budget")
    }
    let groups = args["groups"]
        .as_array()
        .context("groups must be an array")?;
    if groups.is_empty() || groups.len() > 24 {
        bail!("Supply 1–24 motion groups")
    }
    let mut commands = Vec::new();
    let mut used_notes = HashSet::new();
    let mut used_lines = HashSet::new();
    let mut reports = Vec::new();
    for group in groups {
        let carrier = entity(group, "carrier_id")?;
        if w.get::<Line>(carrier).is_none() {
            bail!("Unknown carrier")
        }
        let values = group["note_ids"]
            .as_array()
            .context("Explicit note_ids required")?;
        if values.is_empty() || values.len() > 1000 {
            bail!("Supply 1–1000 notes per group")
        }
        let mut notes = HashSet::new();
        let mut lines = HashSet::from([carrier]);
        for value in values {
            let e = entity(&json!({"id":value}), "id")?;
            if !used_notes.insert(e) || !notes.insert(e) {
                bail!("Duplicate note across motion groups")
            }
            if w.get::<Note>(e).is_none() || w.get::<CurveNote>(e).is_some() {
                bail!("Only editable notes can join motion groups")
            }
            let parent = w.get::<ChildOf>(e).context("Note has no carrier")?.parent();
            lines.insert(parent);
        }
        // Full carrier ownership avoids guessing visibility from judgment times. This
        // includes future notes and hold tails, even during zero/negative scrolling.
        for line in &lines {
            if !used_lines.insert(*line) {
                bail!("A carrier cannot serve two groups")
            }
            for (e, parent) in w.query::<(Entity, &ChildOf)>().iter(w) {
                if parent.parent() == *line && !notes.contains(&e) {
                    bail!("Carrier {} has unselected notes, child lines or curve dependencies; include all notes or isolate it first", id(*line))
                }
            }
        }
        let signature = |line: Entity| {
            let parent = w.get::<ChildOf>(line).map(|p| p.parent());
            let mut events: Vec<String> = data["events"]
                .as_array()
                .unwrap()
                .iter()
                .filter(|e| e["line_id"] == id(line))
                .map(|e| e["event"].to_string())
                .collect();
            events.sort();
            (parent, events)
        };
        let reference = signature(carrier);
        if lines.iter().any(|line| signature(*line) != reference) {
            bail!("Cannot merge carriers with different parents or event timelines; equal motion direction alone is insufficient")
        }
        let events = group["events"]
            .as_array()
            .context("events must be an array")?;
        if events.is_empty() || events.len() > 512 {
            bail!("Supply 1–512 events per group")
        }
        let parsed: Vec<LineEvent> = events.iter().map(parse_event).collect::<Result<_>>()?;
        for (i, a) in parsed.iter().enumerate() {
            if a.end_beat <= a.start_beat {
                bail!("Animation events need positive duration")
            }
            if parsed
                .iter()
                .skip(i + 1)
                .any(|b| a.kind == b.kind && a.start_beat < b.end_beat && b.start_beat < a.end_beat)
            {
                bail!("Animation events overlap on the same channel")
            }
        }
        let channels: HashSet<String> = events
            .iter()
            .map(|e| e["kind"].as_str().unwrap().to_owned())
            .collect();
        // Each supplied channel is a complete replacement timeline. No implicit
        // event clipping or restoration which could alter scroll integrals.
        let removed: Vec<_> = data["events"]
            .as_array()
            .unwrap()
            .iter()
            .filter(|e| {
                e["line_id"] == id(carrier)
                    && channels.contains(e["event"]["kind"].as_str().unwrap())
            })
            .collect();
        for event in &removed {
            commands.push(EditorCommand::RemoveEvent(RemoveEvent::new(entity(
                event, "id",
            )?)));
        }
        for event in parsed {
            commands.push(EditorCommand::CreateEvent(CreateEvent::new(carrier, event)));
        }
        for note in &notes {
            let from = w.get::<ChildOf>(*note).unwrap().parent();
            if from != carrier {
                commands.push(EditorCommand::McpStructure(
                    structure::StructureCommand::ReparentNote {
                        entity: *note,
                        from,
                        to: carrier,
                    },
                ));
            }
        }
        let mut source_lines: Vec<_> = lines.iter().map(|e| id(*e)).collect();
        source_lines.sort();
        reports.push(json!({"carrier_id":id(carrier),"note_ids":values,"source_line_ids":source_lines,
            "replaced_channels":channels,"removed_event_ids":removed.iter().map(|e|e["id"].clone()).collect::<Vec<_>>(),
            "events":events,"ownership":"entire carrier timeline, including early appearances and hold tails"}));
    }
    if commands.len() > 4000 {
        bail!("Animation exceeds 4000 commands")
    }
    if !dry_run {
        w.resource_scope(|w, mut h: Mut<EditorHistory>| {
            h.edit(w, EditorCommand::AgentSequence(CommandSequence(commands)))
        });
        reset_inspector_latches(w);
    }
    let after = snapshot(w)?;
    Ok(
        json!({"session":after["session"],"revision":after["revision"],"dry_run":dry_run,
        "groups":reports,"total_lines":total,"new_lines":0,"line_budget":budget,"undo_steps":if dry_run {0}else{1},
        "notes_preserved":true,"limitations":["Source lines remain in the chart; no automatic deletion or approximate trajectory fitting.","Supplied channels replace their full timelines. Review early appearances and landings using inspect_motion/preview_passage."]}),
    )
}
