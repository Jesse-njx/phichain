//! Candidate-document writes: validate completely, then one native history entry.
//! IDs remain stable. `new:` aliases allow new lines and their objects in one commit.
use super::*;
use serde::{Deserialize, Serialize};
use std::collections::{BTreeMap, HashMap};
use undo::Edit;

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Document {
    lines: BTreeMap<String, LineRow>,
    notes: BTreeMap<String, NoteRow>,
    events: BTreeMap<String, EventRow>,
    curve_tracks: BTreeMap<String, CurveRow>,
    meta: crate::project::ProjectMeta,
    bpm_list: Value,
    offset: f32,
}
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct LineRow {
    name: String,
    role: phichain_chart::line::LineRole,
    parent_id: Option<String>,
    order: u64,
}
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct NoteRow {
    line_id: String,
    note: Value,
}
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct EventRow {
    line_id: String,
    event: Value,
}
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct CurveRow {
    line_id: String,
    from_id: Option<String>,
    to_id: Option<String>,
    options: Value,
}

pub fn document(data: &Value) -> Value {
    let mut doc = json!({"meta":data["meta"],"offset":data["offset"],"bpm_list":data["bpm_list"]});
    for key in ["lines", "notes", "events", "curve_tracks"] {
        let mut rows = serde_json::Map::new();
        for row in data[key].as_array().unwrap() {
            let mut value = row.as_object().unwrap().clone();
            let id = value.remove("id").unwrap().as_str().unwrap().to_owned();
            if key == "lines" && value.get("order").is_none_or(Value::is_null) {
                value.insert("order".into(), json!(0));
            }
            rows.insert(id, Value::Object(value));
        }
        doc[key] = Value::Object(rows);
    }
    doc
}

fn same_shape(a: &Value, b: &Value) -> bool {
    match (a, b) {
        (Value::Number(_), Value::Number(_)) => true,
        (Value::Array(a), Value::Array(b)) => {
            a.len() == b.len() && a.iter().zip(b).all(|(a, b)| same_shape(a, b))
        }
        (Value::Object(a), Value::Object(b)) => {
            a.len() == b.len()
                && a.iter()
                    .all(|(k, a)| b.get(k).is_some_and(|b| same_shape(a, b)))
        }
        (Value::Null, Value::Null)
        | (Value::Bool(_), Value::Bool(_))
        | (Value::String(_), Value::String(_)) => true,
        _ => false,
    }
}

fn equivalent(a: &Value, b: &Value) -> bool {
    match (a, b) {
        (Value::Number(a), Value::Number(b)) => a.as_f64() == b.as_f64(),
        (Value::Array(a), Value::Array(b)) => {
            a.len() == b.len() && a.iter().zip(b).all(|(a, b)| equivalent(a, b))
        }
        (Value::Object(a), Value::Object(b)) => {
            a.len() == b.len()
                && a.iter()
                    .all(|(k, a)| b.get(k).is_some_and(|b| equivalent(a, b)))
        }
        _ => a == b,
    }
}

fn keys(doc: &Document) -> Vec<(&str, &str)> {
    doc.lines
        .keys()
        .map(|s| (s.as_str(), "lines"))
        .chain(doc.notes.keys().map(|s| (s.as_str(), "notes")))
        .chain(doc.events.keys().map(|s| (s.as_str(), "events")))
        .chain(
            doc.curve_tracks
                .keys()
                .map(|s| (s.as_str(), "curve_tracks")),
        )
        .collect()
}
fn validate_document(next: &Document, before: &Document) -> Result<()> {
    if next.lines.is_empty() || keys(next).len() > 20000 {
        bail!("Keep at least one line; maximum 20,000 editable objects")
    }
    if !next.offset.is_finite() {
        bail!("Offset must be finite")
    }
    analysis::parse_bpm(&next.bpm_list)?;
    let previous: HashMap<_, _> = keys(before).into_iter().collect();
    let mut seen = HashSet::new();
    for (id, kind) in keys(next) {
        if !seen.insert(id) {
            bail!("Duplicate object ID: {id}")
        }
        if let Some(old) = previous.get(id) {
            if *old != kind {
                bail!("Cannot change object type: {id}")
            }
        } else if !id.starts_with("new:")
            || id.len() < 5
            || id.len() > 80
            || !id
                .bytes()
                .all(|b| b.is_ascii_alphanumeric() || b"_:-".contains(&b))
        {
            bail!("Unknown ID {id}; new objects require unique new:name aliases")
        }
    }
    let mut root_orders = HashSet::new();
    for (key, line) in &next.lines {
        if line.name.trim().is_empty() || line.name.len() > 256 {
            bail!("Line names must be 1–256 bytes")
        }
        if line.parent_id.is_none() && !root_orders.insert(line.order) {
            bail!("Root line orders must be unique")
        }
        let mut chain = HashSet::from([key.as_str()]);
        let mut parent = line.parent_id.as_deref();
        while let Some(p) = parent {
            if !chain.insert(p) {
                bail!("Line hierarchy cycle")
            }
            parent = next
                .lines
                .get(p)
                .context("Unknown parent line")?
                .parent_id
                .as_deref();
        }
    }
    if !next.lines.values().any(|l| l.parent_id.is_none()) {
        bail!("Keep at least one root line")
    }
    for row in next.notes.values() {
        if !next.lines.contains_key(&row.line_id) {
            bail!("Note references unknown line")
        }
        validate_beats(&row.note)?;
        parse_note(&row.note)?;
    }
    for row in next.events.values() {
        if !next.lines.contains_key(&row.line_id) {
            bail!("Event references unknown line")
        }
        validate_beats(&row.event)?;
        parse_event(&row.event)?;
    }
    for row in next.curve_tracks.values() {
        if !next.lines.contains_key(&row.line_id) {
            bail!("Curve references unknown line")
        }
        let options: phichain_chart::curve_note_track::CurveNoteTrackOptions =
            serde_json::from_value(row.options.clone())?;
        if !(1..=256).contains(&options.density) {
            bail!("Curve density must be 1–256")
        }
        parse_note(&json!(Note {
            kind: options.kind,
            above: true,
            beat: Beat::ZERO,
            x: 0.,
            speed: 1.
        }))?;
        parse_event(
            &json!({"kind":"x","start_beat":[0,0,1],"end_beat":[1,0,1],"value":{"type":"transition","start":0,"end":1,"easing":options.curve}}),
        )?;
        match (&row.from_id, &row.to_id) {
            (Some(from), Some(to)) => {
                let a = next.notes.get(from).context("Unknown curve start")?;
                let b = next.notes.get(to).context("Unknown curve end")?;
                if a.line_id != row.line_id || b.line_id != row.line_id {
                    bail!("Curve endpoints must remain on its line")
                }
                let duration = (parse_note(&b.note)?.beat - parse_note(&a.note)?.beat).value();
                if duration <= 0. || duration * options.density as f32 > 10000. {
                    bail!("Invalid curve duration or generation limit")
                }
            }
            (Some(from), None)
                if before
                    .curve_tracks
                    .values()
                    .any(|v| v.from_id.as_ref() == Some(from) && v.to_id.is_none()) =>
            {
                if next
                    .notes
                    .get(from)
                    .is_none_or(|n| n.line_id != row.line_id)
                {
                    bail!("Invalid incomplete curve")
                }
            }
            _ => bail!("Curve endpoints must be explicit"),
        }
    }
    Ok(())
}

#[derive(Clone)]
pub struct DocumentEdit {
    label: String,
    before: Document,
    after: Document,
    ids: BTreeMap<String, Entity>,
    selected_line: Option<Entity>,
    selected: Vec<Entity>,
}
impl std::fmt::Debug for DocumentEdit {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.debug_struct("AuthoringChange")
            .field("label", &self.label)
            .field("objects_before", &keys(&self.before).len())
            .field("objects_after", &keys(&self.after).len())
            .finish()
    }
}

impl DocumentEdit {
    fn apply(&mut self, w: &mut World, forward: bool) {
        // Allocation happens only inside the history edit, after all validation.
        for (key, _) in keys(&self.after) {
            if !self.ids.contains_key(key) {
                self.ids.insert(key.to_owned(), w.spawn_empty().id());
            }
        }
        let wanted = if forward { &self.after } else { &self.before };
        let wanted_keys: HashSet<_> = keys(wanted).into_iter().map(|(s, _)| s).collect();
        // Generated notes are derived state, regenerated by native curve systems.
        let generated: Vec<_> = w
            .query_filtered::<Entity, With<CurveNote>>()
            .iter(w)
            .collect();
        for e in generated {
            w.entity_mut(e).despawn();
        }
        for e in self.ids.values() {
            w.entity_mut(*e).remove::<(ChildOf, EventOf)>();
        }
        for (key, e) in &self.ids {
            if !wanted_keys.contains(key.as_str()) {
                w.entity_mut(*e).retain::<()>();
            }
        }
        for (key, row) in &wanted.lines {
            let e = self.ids[key];
            w.entity_mut(e).insert(Line {
                name: row.name.clone(),
                role: row.role,
            });
            if w.get::<LineOrder>(e).is_none() {
                w.entity_mut(e).insert(LineOrder(row.order));
            }
            w.get_mut::<LineOrder>(e).unwrap().0 = row.order;
        }
        for (key, row) in &wanted.notes {
            w.entity_mut(self.ids[key])
                .insert(parse_note(&row.note).expect("validated note"));
        }
        for (key, row) in &wanted.events {
            w.entity_mut(self.ids[key])
                .insert(parse_event(&row.event).expect("validated event"));
        }
        for (key, row) in &wanted.curve_tracks {
            w.entity_mut(self.ids[key])
                .remove::<phichain_game::curve_note_track::CurveNoteCache>()
                .insert(CurveNoteTrack {
                    from: row.from_id.as_ref().map(|s| self.ids[s]),
                    to: row.to_id.as_ref().map(|s| self.ids[s]),
                    options: serde_json::from_value(row.options.clone())
                        .expect("validated options"),
                });
        }
        for (key, row) in &wanted.lines {
            if let Some(parent) = &row.parent_id {
                w.entity_mut(self.ids[key])
                    .insert(ChildOf(self.ids[parent]));
            }
        }
        for (key, row) in &wanted.notes {
            w.entity_mut(self.ids[key])
                .insert(ChildOf(self.ids[&row.line_id]));
        }
        for (key, row) in &wanted.events {
            w.entity_mut(self.ids[key])
                .insert(EventOf(self.ids[&row.line_id]));
        }
        for (key, row) in &wanted.curve_tracks {
            w.entity_mut(self.ids[key])
                .insert(ChildOf(self.ids[&row.line_id]));
        }
        w.insert_resource(analysis::parse_bpm(&wanted.bpm_list).expect("validated BPM"));
        w.insert_resource(Offset(wanted.offset));
        w.resource_mut::<Project>().meta = wanted.meta.clone();
        let selected = self
            .selected_line
            .filter(|e| w.get::<Line>(*e).is_some())
            .unwrap_or_else(|| {
                self.ids[wanted
                    .lines
                    .iter()
                    .find(|(_, l)| l.parent_id.is_none())
                    .unwrap()
                    .0]
            });
        w.insert_resource(SelectedLine(selected));
        for e in &self.selected {
            if w.get::<Note>(*e).is_some()
                || w.get::<LineEvent>(*e).is_some()
                || w.get::<CurveNoteTrack>(*e).is_some()
            {
                w.entity_mut(*e).insert(Selected);
            }
        }
    }
}
impl Edit for DocumentEdit {
    type Target = World;
    type Output = ();
    fn edit(&mut self, w: &mut World) {
        self.apply(w, true);
    }
    fn undo(&mut self, w: &mut World) {
        self.apply(w, false);
    }
}

pub fn commit(w: &mut World, args: &Value, data: &Value) -> Result<Value> {
    check_revision(args, data)?;
    idle(w)?;
    let dry = args["dry_run"]
        .as_bool()
        .context("dry_run must be explicit")?;
    let label = args
        .get("label")
        .map(|v| v.as_str().context("label must be a string"))
        .transpose()?
        .unwrap_or("Agent authoring");
    if label.is_empty() || label.len() > 640 {
        bail!("Invalid authoring label")
    }
    let candidate = &args["document"];
    validate_beats(candidate)?;
    let before_value = document(data);
    let before: Document = serde_json::from_value(before_value.clone())?;
    let mut after: Document = serde_json::from_value(candidate.clone())?;
    validate_document(&after, &before)?;
    for row in after.notes.values_mut() {
        row.note = json!(parse_note(&row.note)?);
    }
    for row in after.events.values_mut() {
        row.event = json!(parse_event(&row.event)?);
    }
    for row in after.curve_tracks.values_mut() {
        let parsed: phichain_chart::curve_note_track::CurveNoteTrackOptions =
            serde_json::from_value(row.options.clone())?;
        row.options = json!(parsed);
    }
    let normalized = serde_json::to_value(&after)?;
    // Numeric native values round to f32. Compare field shapes to reject loss,
    // then diff normalized values so harmless int/float spellings are no-ops.
    if !same_shape(candidate, &normalized) {
        bail!("Unknown, missing or noncanonical document fields")
    }
    let mut changes = Vec::new();
    for key in ["lines", "notes", "events", "curve_tracks"] {
        let old = before_value[key].as_object().unwrap();
        let new = normalized[key].as_object().unwrap();
        for id in old
            .keys()
            .chain(new.keys())
            .collect::<std::collections::BTreeSet<_>>()
        {
            if !equivalent(&json!(old.get(id)), &json!(new.get(id))) {
                changes.push(
                    json!({"collection":key,"id":id,"before":old.get(id),"after":new.get(id)}),
                );
            }
        }
    }
    for key in ["meta", "offset", "bpm_list"] {
        if !equivalent(&before_value[key], &normalized[key]) {
            changes.push(json!({"field":key,"before":before_value[key],"after":normalized[key]}));
        }
    }
    if dry || changes.is_empty() {
        return Ok(
            json!({"session":data["session"],"revision":data["revision"],"dry_run":dry,"changes":changes,"undo_steps":0,"created_ids":{}}),
        );
    }
    let ids = keys(&before)
        .into_iter()
        .map(|(s, _)| Ok((s.to_owned(), entity(&json!({"id":s}), "id")?)))
        .collect::<Result<_>>()?;
    let edit = DocumentEdit {
        label: label.to_owned(),
        before,
        after,
        ids,
        selected_line: w.get_resource::<SelectedLine>().map(|s| s.0),
        selected: w
            .query_filtered::<Entity, With<Selected>>()
            .iter(w)
            .collect(),
    };
    let mut created = json!({});
    w.resource_scope(|w, mut history: Mut<EditorHistory>| {
        history.edit(
            w,
            EditorCommand::AgentSequence(CommandSequence(vec![EditorCommand::McpDocument(edit)])),
        );
        if let Some(EditorCommand::AgentSequence(seq)) =
            history.0.entries().last().map(|e| e.as_ref())
        {
            if let EditorCommand::McpDocument(edit) = &seq.0[0] {
                for (key, e) in &edit.ids {
                    if key.starts_with("new:") {
                        created[key] = json!(id(*e));
                    }
                }
            }
        }
    });
    reset_inspector_latches(w);
    let after = snapshot(w)?;
    Ok(
        json!({"session":after["session"],"revision":after["revision"],"changes":changes,"created_ids":created,"undo_steps":1,"dry_run":false}),
    )
}
