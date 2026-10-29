//! Undoable structural edits. Deleted subtrees retain editable object IDs.
use super::*;
use crate::events::{line::SpawnLineEvent, EditorEvent};
use phichain_chart::serialization::SerializedLine;
use undo::Edit;

#[derive(Debug, Clone)]
struct SavedObject {
    id: Entity,
    line: Option<Line>,
    note: Option<Note>,
    event: Option<LineEvent>,
    curve: Option<CurveNoteTrack>,
    order: Option<LineOrder>,
    parent: Option<Entity>,
    event_parent: Option<Entity>,
}
#[derive(Debug, Clone)]
pub struct Subtree {
    objects: Vec<SavedObject>,
    selected: Option<Entity>,
}
impl Subtree {
    fn capture(w: &mut World, root: Entity) -> Self {
        let lines = descendants(w, root);
        let objects = w
            .query::<Entity>()
            .iter(w)
            .filter_map(|id| {
                let e = w.entity(id);
                let parent = e.get::<ChildOf>().map(|p| p.parent());
                let event_parent = e.get::<EventOf>().map(|p| p.target());
                if e.contains::<CurveNote>()
                    || !(lines.contains(&id)
                        || parent.is_some_and(|p| lines.contains(&p))
                        || event_parent.is_some_and(|p| lines.contains(&p)))
                {
                    return None;
                }
                Some(SavedObject {
                    id,
                    line: e.get::<Line>().cloned(),
                    note: e.get::<Note>().copied(),
                    event: e.get::<LineEvent>().copied(),
                    curve: e.get::<CurveNoteTrack>().cloned(),
                    order: e.get::<LineOrder>().copied(),
                    parent,
                    event_parent,
                })
            })
            .collect();
        Self {
            objects,
            selected: w.get_resource::<SelectedLine>().map(|l| l.0),
        }
    }
    fn remove(&self, w: &mut World) {
        let removed: HashSet<_> = self
            .objects
            .iter()
            .filter(|o| o.line.is_some())
            .map(|o| o.id)
            .collect();
        if w.get_resource::<SelectedLine>()
            .is_some_and(|s| removed.contains(&s.0))
        {
            if let Some(other) = w
                .query_filtered::<Entity, (With<Line>, Without<ChildOf>)>()
                .iter(w)
                .find(|e| !removed.contains(e))
            {
                w.resource_mut::<SelectedLine>().0 = other;
            }
        }
        // Unlink first, before removing linked-spawn relationship targets.
        for o in &self.objects {
            w.entity_mut(o.id).remove::<(ChildOf, EventOf)>();
        }
        for o in &self.objects {
            w.entity_mut(o.id).retain::<()>();
        }
    }
    fn restore(&self, w: &mut World) {
        for o in &self.objects {
            let mut e = w.entity_mut(o.id);
            if let Some(line) = &o.line {
                e.insert(line.clone());
            }
            if let Some(order) = o.order {
                if let Some(mut current) = e.get_mut::<LineOrder>() {
                    *current = order;
                }
            }
            if let Some(note) = o.note {
                e.insert(note);
            }
            if let Some(event) = o.event {
                e.insert(event);
            }
            if let Some(curve) = &o.curve {
                e.insert(curve.clone());
            }
        }
        for o in &self.objects {
            if let Some(parent) = o.parent {
                w.entity_mut(o.id).insert(ChildOf(parent));
            }
            if let Some(parent) = o.event_parent {
                w.entity_mut(o.id).insert(EventOf(parent));
            }
        }
        if let Some(selected) = self.selected {
            if w.get::<Line>(selected).is_some() {
                w.insert_resource(SelectedLine(selected));
            }
        }
    }
}

pub fn descendants(w: &mut World, root: Entity) -> HashSet<Entity> {
    let mut set = HashSet::from([root]);
    loop {
        let previous = set.len();
        for (e, p) in w.query_filtered::<(Entity, &ChildOf), With<Line>>().iter(w) {
            if set.contains(&p.parent()) {
                set.insert(e);
            }
        }
        if previous == set.len() {
            return set;
        }
    }
}

#[derive(Debug, Clone)]
pub enum StructureCommand {
    ReparentNote { entity: Entity, from: Entity, to: Entity },
    Create {
        name: String,
        parent: Option<Entity>,
        entity: Option<Entity>,
        saved: Option<Subtree>,
    },
    Remove {
        entity: Entity,
        saved: Option<Subtree>,
    },
    Update {
        entity: Entity,
        from: Line,
        to: Line,
        old_parent: Option<Entity>,
        new_parent: Option<Entity>,
    },
    Reorder {
        from: Vec<(Entity, u64)>,
        to: Vec<(Entity, u64)>,
    },
    CurveUpdate {
        entity: Entity,
        from: CurveNoteTrack,
        to: CurveNoteTrack,
    },
}
impl Edit for StructureCommand {
    type Target = World;
    type Output = ();
    fn edit(&mut self, w: &mut World) {
        match self {
            Self::ReparentNote { entity, to, .. } => { w.entity_mut(*entity).insert(ChildOf(*to)); },
            Self::Create {
                name,
                parent,
                entity,
                saved,
            } => {
                if let Some(saved) = saved {
                    saved.restore(w);
                } else {
                    let mut line = SerializedLine::default();
                    line.line.name = name.clone();
                    for event in &mut line.events {
                        if event.kind.is_opacity() {
                            event.value = phichain_chart::event::LineEventValue::constant(255.0);
                        }
                    }
                    *entity = Some(
                        SpawnLineEvent::builder()
                            .line(line)
                            .maybe_parent(*parent)
                            .build()
                            .run(w),
                    );
                }
            }
            Self::Remove { entity, saved } => {
                *saved = Some(Subtree::capture(w, *entity));
                saved.as_ref().unwrap().remove(w);
            }
            Self::Update {
                entity,
                to,
                new_parent,
                ..
            } => {
                w.entity_mut(*entity).insert(to.clone()).remove::<ChildOf>();
                if let Some(p) = new_parent {
                    w.entity_mut(*entity).insert(ChildOf(*p));
                }
            }
            Self::Reorder { to, .. } => {
                for (e, order) in to {
                    w.get_mut::<LineOrder>(*e).unwrap().0 = *order;
                }
            }
            Self::CurveUpdate { entity, to, .. } => {
                w.entity_mut(*entity).insert(to.clone());
            }
        }
    }
    fn undo(&mut self, w: &mut World) {
        match self {
            Self::ReparentNote { entity, from, .. } => { w.entity_mut(*entity).insert(ChildOf(*from)); },
            Self::Create { entity, saved, .. } => {
                let tree = Subtree::capture(w, entity.unwrap());
                tree.remove(w);
                *saved = Some(tree);
            }
            Self::Remove { saved, .. } => {
                saved.as_ref().unwrap().restore(w);
            }
            Self::Update {
                entity,
                from,
                old_parent,
                ..
            } => {
                w.entity_mut(*entity)
                    .insert(from.clone())
                    .remove::<ChildOf>();
                if let Some(p) = old_parent {
                    w.entity_mut(*entity).insert(ChildOf(*p));
                }
            }
            Self::Reorder { from, .. } => {
                for (e, order) in from {
                    w.get_mut::<LineOrder>(*e).unwrap().0 = *order;
                }
            }
            Self::CurveUpdate { entity, from, .. } => {
                w.entity_mut(*entity).insert(from.clone());
            }
        }
    }
}

pub fn validate_batch(w: &mut World, ops: &[Value]) -> Result<()> {
    let mut parents: std::collections::HashMap<Entity, Option<Entity>> = w
        .query_filtered::<(Entity, Option<&ChildOf>), With<Line>>()
        .iter(w)
        .map(|(e, p)| (e, p.map(|p| p.parent())))
        .collect();
    let mut deleted = HashSet::new();
    for op in ops {
        match op["op"].as_str().unwrap_or("") {
            "delete_line" => {
                let e = entity(op, "id")?;
                if !parents.contains_key(&e) {
                    bail!("Unknown line")
                }
                let tree = descendants(w, e);
                if tree.iter().any(|e| deleted.contains(e)) {
                    bail!("Overlapping line deletions")
                }
                if op["cascade"] != true {
                    let has_content = w
                        .query::<(Option<&ChildOf>, Option<&EventOf>)>()
                        .iter(w)
                        .any(|(p, e)| {
                            p.is_some_and(|p| tree.contains(&p.parent()))
                                || e.is_some_and(|e| tree.contains(&e.target()))
                        });
                    if has_content {
                        bail!("Line has dependent objects; explicit cascade=true is required")
                    }
                }
                deleted.extend(tree);
            }
            "update_line" if op.get("parent_id").is_some() => {
                let e = entity(op, "id")?;
                if !parents.contains_key(&e) {
                    bail!("Unknown line")
                }
                let p = if op["parent_id"].is_null() {
                    None
                } else {
                    Some(entity(op, "parent_id")?)
                };
                if p.is_some_and(|p| !parents.contains_key(&p)) {
                    bail!("Unknown parent line")
                }
                parents.insert(e, p);
            }
            _ => {}
        }
    }
    if !parents
        .iter()
        .any(|(e, p)| p.is_none() && !deleted.contains(e))
    {
        bail!("At least one existing root line must remain")
    }
    for (&line, &parent) in &parents {
        if deleted.contains(&line) {
            continue;
        }
        let mut seen = HashSet::from([line]);
        let mut next = parent;
        while let Some(p) = next {
            if deleted.contains(&p) {
                bail!("Cannot move a line under a deleted line")
            }
            if !seen.insert(p) {
                bail!("Line hierarchy cycle")
            }
            next = *parents.get(&p).context("Unknown parent line")?;
        }
    }
    if !deleted.is_empty() {
        for op in ops {
            if op["op"] == "delete_line" {
                continue;
            }
            for field in ["id", "line_id", "parent_id", "from_id", "to_id"] {
                if op.get(field).is_none() || op[field].is_null() {
                    continue;
                }
                let e = entity(op, field)?;
                let p = w
                    .get::<ChildOf>(e)
                    .map(|p| p.parent())
                    .or_else(|| w.get::<EventOf>(e).map(|p| p.target()));
                if deleted.contains(&e) || p.is_some_and(|p| deleted.contains(&p)) {
                    bail!("Batch also references an object inside a deleted line")
                }
            }
        }
    }
    // Endpoint edits in the same batch must not invalidate an existing or new curve.
    let mut notes: std::collections::HashMap<Entity, Note> = w
        .query::<(Entity, &Note)>()
        .iter(w)
        .map(|(e, n)| (e, *n))
        .collect();
    for op in ops {
        if op["op"] == "update_note" {
            notes.insert(entity(op, "id")?, super::parse_note(&op["note"])?);
        }
        if op["op"] == "delete_note" {
            notes.remove(&entity(op, "id")?);
        }
    }
    let removed_tracks: HashSet<_> = ops
        .iter()
        .filter(|o| o["op"] == "delete_curve_track" || o["op"] == "update_curve_track")
        .map(|o| entity(o, "id"))
        .collect::<Result<_>>()?;
    let mut curves: Vec<_> = w
        .query::<(Entity, &CurveNoteTrack, &ChildOf)>()
        .iter(w)
        .filter(|(e, _, p)| !removed_tracks.contains(e) && !deleted.contains(&p.parent()))
        .map(|(_, t, _)| t.clone())
        .collect();
    for op in ops {
        if op["op"] == "create_curve_track" || op["op"] == "update_curve_track" {
            curves.push(CurveNoteTrack {
                from: Some(entity(op, "from_id")?),
                to: Some(entity(op, "to_id")?),
                options: serde_json::from_value(op["options"].clone())?,
            });
        }
    }
    for track in curves {
        if let Some((from, to)) = track.get_entities() {
            let from = notes.get(&from).context("Curve endpoint deleted")?;
            let to = notes.get(&to).context("Curve endpoint deleted")?;
            let duration = (to.beat - from.beat).value();
            if duration <= 0.0
                || !(1..=256).contains(&track.options.density)
                || duration * track.options.density as f32 > 10000.0
            {
                bail!("Batch would invalidate curve endpoint order or exceed generation limits")
            }
        }
    }
    Ok(())
}

pub fn parse_curve(w: &mut World, op: &Value, line: Entity) -> Result<CurveNoteTrack> {
    let from = entity(op, "from_id")?;
    let to = entity(op, "to_id")?;
    for e in [from, to] {
        if w.get::<CurveNote>(e).is_some()
            || w.get::<Note>(e).is_none()
            || w.get::<ChildOf>(e).map(|p| p.parent()) != Some(line)
        {
            bail!("Curve endpoints must be editable notes on this line")
        }
    }
    if w.get::<Note>(from).unwrap().beat >= w.get::<Note>(to).unwrap().beat {
        bail!("Curve endpoints must be strictly ordered")
    }
    let options: phichain_chart::curve_note_track::CurveNoteTrackOptions =
        serde_json::from_value(op["options"].clone())?;
    if !(1..=256).contains(&options.density) {
        bail!("Curve density must be 1–256")
    }
    let duration = (w.get::<Note>(to).unwrap().beat - w.get::<Note>(from).unwrap().beat).value();
    if duration * options.density as f32 > 10000.0 {
        bail!("Curve generates too many notes")
    }
    let test = Note {
        kind: options.kind,
        beat: Beat::ZERO,
        x: 0.0,
        above: true,
        speed: 1.0,
    };
    super::parse_note(&json!(test))?;
    // Reuse event easing validation, including custom coordinates.
    super::parse_event(
        &json!({"kind":"x","start_beat":[0,0,1],"end_beat":[1,0,1],"value":{"type":"transition","start":0,"end":1,"easing":options.curve}}),
    )?;
    Ok(CurveNoteTrack {
        from: Some(from),
        to: Some(to),
        options,
    })
}
