//! Opt-in loopback bridge. All world access stays on Bevy's main thread.
use crate::cli::Args;
use crate::editing::command::{
    event::{CreateEvent, EditEvent, RemoveEvent},
    meta::{EditMeta, EditOffset},
    note::{CreateNote, EditNote, RemoveNote},
    CommandSequence, EditorCommand,
};
use crate::editing::{history::EditorHistory, pending::Pending, DoCommand};
use crate::project::Project;
use crate::selection::{Selected, SelectedLine};
use crate::timing::{ChartTime, Pause, Paused, Resume, SeekTo, Timing};
use anyhow::{anyhow, bail, Context, Result};
use bevy::{ecs::system::RunSystemOnce, prelude::*};
use phichain_chart::{
    beat::Beat,
    bpm_list::BpmList,
    event::LineEvent,
    line::Line,
    note::{Note, NoteKind},
    offset::Offset,
};
use phichain_game::{
    curve_note_track::{CurveNote, CurveNoteTrack},
    event::EventOf,
    line::LineOrder,
    serialization::{serialize_chart, SerializeChartParam, SerializeLineParam},
};
use serde_json::{json, Value};
use std::{
    collections::{hash_map::DefaultHasher, HashSet},
    hash::{Hash, Hasher},
    io::{BufRead, BufReader, Read, Write},
    net::{TcpListener, TcpStream},
    path::PathBuf,
    sync::{
        atomic::{AtomicBool, Ordering},
        mpsc, Arc, Mutex,
    },
    time::{Duration, Instant},
};

pub(crate) mod analysis;
mod quality;
mod motion;
mod animation;
pub(crate) mod authoring;
pub(crate) mod structure;

pub struct McpPlugin;

#[derive(Resource, Default)]
struct Lifecycle {
    pending: Option<String>,
    error: Option<String>,
}
fn loading_result(
    event: On<phichain_game::loader::nonblocking::ProjectLoadingResult>,
    mut state: ResMut<Lifecycle>,
) {
    state.pending = None;
    state.error = event.0.as_ref().err().map(ToString::to_string);
}

struct Request {
    body: Value,
    reply: mpsc::SyncSender<Value>,
    deadline: Instant,
}
#[derive(Resource)]
struct Bridge {
    requests: Mutex<mpsc::Receiver<Request>>,
    endpoint: PathBuf,
    token: String,
    stopped: Arc<AtomicBool>,
}
impl Drop for Bridge {
    fn drop(&mut self) {
        self.stopped.store(true, Ordering::Relaxed);
        // Only remove our own descriptor, even if the path was replaced externally.
        if std::fs::read(&self.endpoint)
            .ok()
            .and_then(|b| serde_json::from_slice::<Value>(&b).ok())
            .is_some_and(|v| v["token"] == self.token)
        {
            let _ = std::fs::remove_file(&self.endpoint);
        }
    }
}

impl Plugin for McpPlugin {
    fn build(&self, app: &mut App) {
        let Some(path) = app.world().resource::<Args>().mcp_endpoint.clone() else {
            return;
        };
        match start_bridge(path) {
            Ok(bridge) => {
                app.insert_resource(bridge)
                    .init_resource::<Lifecycle>()
                    .add_observer(loading_result)
                    .add_systems(Last, process_requests);
            }
            Err(error) => error!("Cannot start PhiChain MCP bridge: {error:#}"),
        }
    }
}

fn start_bridge(path: PathBuf) -> Result<Bridge> {
    let listener = TcpListener::bind(("127.0.0.1", 0))?;
    let token = uuid::Uuid::new_v4().to_string();
    let descriptor =
        json!({"port":listener.local_addr()?.port(), "token":token, "pid":std::process::id()});
    // Never follow a pre-existing symlink or silently replace another editor's endpoint.
    let mut options = std::fs::OpenOptions::new();
    options.write(true).create_new(true);
    #[cfg(unix)]
    {
        use std::os::unix::fs::OpenOptionsExt;
        options.mode(0o600);
    }
    let mut file = options
        .open(&path)
        .context("Endpoint file must not already exist")?;
    file.write_all(serde_json::to_string(&descriptor)?.as_bytes())?;
    listener.set_nonblocking(true)?;
    let (sender, receiver) = mpsc::sync_channel(16);
    let stopped = Arc::new(AtomicBool::new(false));
    let thread_stop = stopped.clone();
    let thread_token = token.clone();
    std::thread::spawn(move || {
        while !thread_stop.load(Ordering::Relaxed) {
            match listener.accept() {
                Ok((mut stream, _)) => {
                    let response = serve(&mut stream, &thread_token, &sender)
                        .unwrap_or_else(|e| json!({"error":e.to_string()}));
                    let _ = writeln!(stream, "{}", response);
                }
                Err(e) if e.kind() == std::io::ErrorKind::WouldBlock => {
                    std::thread::sleep(Duration::from_millis(10))
                }
                Err(_) => break,
            }
        }
    });
    info!("PhiChain MCP endpoint written to {}", path.display());
    Ok(Bridge {
        requests: Mutex::new(receiver),
        endpoint: path,
        token,
        stopped,
    })
}

fn serve(stream: &mut TcpStream, token: &str, sender: &mpsc::SyncSender<Request>) -> Result<Value> {
    stream.set_nonblocking(false)?;
    stream.set_read_timeout(Some(Duration::from_secs(2)))?;
    stream.set_write_timeout(Some(Duration::from_secs(2)))?;
    let mut body = String::new();
    BufReader::new((&mut *stream).take(16_777_217)).read_line(&mut body)?;
    if body.len() > 16_777_216 {
        bail!("Bridge request exceeds 16 MiB")
    }
    let body_bytes = body.len();
    let body: Value = serde_json::from_str(&body)?;
    if body_bytes > 1_048_576 && body["tool"] != "authoring_commit" { bail!("Request exceeds 1 MiB") }
    if body["token"].as_str() != Some(token) {
        bail!("Invalid bridge token")
    }
    let (reply, response) = mpsc::sync_channel(1);
    sender
        .try_send(Request {
            body,
            reply,
            deadline: Instant::now() + Duration::from_secs(10),
        })
        .map_err(|_| anyhow!("Editor request queue is full"))?;
    response
        .recv_timeout(Duration::from_secs(10))
        .context("Editor did not respond; re-read state before retrying any edit")
}

fn process_requests(world: &mut World) {
    // One request per frame: audio/game systems see edits before the next response.
    let request = world
        .resource::<Bridge>()
        .requests
        .lock()
        .unwrap()
        .try_recv()
        .ok();
    if let Some(request) = request {
        let response = if Instant::now() >= request.deadline {
            json!({"error":"Request expired before execution; no changes applied"})
        } else {
            handle(world, &request.body).unwrap_or_else(|e| json!({"error":e.to_string()}))
        };
        let _ = request.reply.send(response);
    }
}

fn id(entity: Entity) -> String {
    entity.to_bits().to_string()
}
fn entity(args: &Value, key: &str) -> Result<Entity> {
    let bits = args[key]
        .as_str()
        .context(format!("{key} must be an ID string"))?
        .parse()?;
    Entity::try_from_bits(bits).context("Invalid entity ID")
}

fn snapshot(world: &mut World) -> Result<Value> {
    let project = world
        .get_resource::<Project>()
        .context("Open a project in PhiChain first")?
        .clone();
    let mut lines: Vec<_> = world.query::<(Entity, &Line, Option<&ChildOf>, Option<&LineOrder>)>().iter(world)
        .map(|(e,l,p,o)| json!({"id":id(e),"name":l.name,"role":l.role,"parent_id":p.map(|p|id(p.parent())),"order":o.map(|o|o.0)})).collect();
    let mut notes: Vec<_> = world
        .query_filtered::<(Entity, &Note, &ChildOf), (Without<CurveNote>, Without<Pending>)>()
        .iter(world)
        .map(|(e, n, p)| json!({"id":id(e),"line_id":id(p.parent()),"note":n}))
        .collect();
    let mut events: Vec<_> = world
        .query_filtered::<(Entity, &LineEvent, &EventOf), Without<Pending>>()
        .iter(world)
        .map(|(e, v, p)| json!({"id":id(e),"line_id":id(p.target()),"event":v}))
        .collect();
    let mut tracks: Vec<_> = world.query::<(Entity, &CurveNoteTrack, &ChildOf)>().iter(world)
        .map(|(e,t,p)|json!({"id":id(e),"line_id":id(p.parent()),"from_id":t.from.map(id),"to_id":t.to.map(id),"options":t.options})).collect();
    for values in [&mut lines, &mut notes, &mut events, &mut tracks] {
        values.sort_by(|a, b| a["id"].as_str().cmp(&b["id"].as_str()));
    }
    let mut data = json!({"session":project.id.to_string(),"project_path":project.path.0,"music_path":project.path.music_path(),"history_cursor":world.get_resource::<EditorHistory>().map(|h|format!("{:?}",h.0.head())),"meta":project.meta,"bpm_list":world.get_resource::<BpmList>(),"offset":world.get_resource::<Offset>(),"lines":lines,"notes":notes,"events":events,"curve_tracks":tracks});
    let mut hash = DefaultHasher::new();
    data.to_string().hash(&mut hash);
    data["revision"] = json!(format!("{:016x}", hash.finish()));
    Ok(data)
}

fn check_revision(args: &Value, data: &Value) -> Result<()> {
    if args["session"] != data["session"] || args["revision"] != data["revision"] {
        bail!("Chart changed or project reopened. Read context/section again and regenerate the edits.")
    }
    Ok(())
}

fn idle(world: &mut World) -> Result<()> {
    if world.query::<&Pending>().iter(world).next().is_some() {
        bail!("Finish the active mouse edit before applying MCP changes")
    }
    if world
        .get_resource::<ButtonInput<MouseButton>>()
        .is_some_and(|input| input.get_pressed().next().is_some())
        || world
            .query::<&bevy_egui::EguiContext>()
            .iter(world)
            .any(|ctx| ctx.get().is_using_pointer() || ctx.get().wants_keyboard_input())
    {
        bail!("Finish the active mouse/text interaction before applying MCP changes")
    }
    if world
        .get_resource::<Messages<DoCommand>>()
        .is_some_and(|messages| !messages.is_empty())
    {
        bail!("Human edit commands are settling; read state again before applying changes")
    }
    Ok(())
}

fn reset_inspector_latches(world: &mut World) {
    // Inspectors retain the pre-interaction value even while idle. External edits
    // must invalidate it so the next human undo starts from the agent's result.
    for ctx in world.query::<&bevy_egui::EguiContext>().iter(world) {
        ctx.get().data_mut(|data| {
            data.remove::<Note>(egui::Id::new("note"));
            data.remove::<LineEvent>(egui::Id::new("event"));
            data.remove::<Line>(egui::Id::new("line"));
            data.remove::<(crate::project::ProjectMeta, f32)>(egui::Id::new(
                "chart-basic-settings",
            ));
        });
    }
}

fn context(world: &mut World, data: &Value) -> Value {
    let selected: Vec<_> = world
        .query_filtered::<Entity, With<Selected>>()
        .iter(world)
        .map(id)
        .collect();
    let history = world.get_resource::<EditorHistory>();
    let mut selection = json!({});
    for key in ["notes", "events", "curve_tracks"] {
        selection[key] = json!(data[key]
            .as_array()
            .unwrap()
            .iter()
            .filter(|item| item["id"]
                .as_str()
                .is_some_and(|id| selected.iter().any(|s| s == id)))
            .collect::<Vec<_>>());
    }
    json!({
        "session": data["session"], "revision": data["revision"],
        "meta": data["meta"], "project_path": data["project_path"], "music_path": data["music_path"],
        "bpm_list": data["bpm_list"], "offset": data["offset"],
        "lines": data["lines"], "note_count": data["notes"].as_array().map(Vec::len),
        "event_count": data["events"].as_array().map(Vec::len), "selected_ids": selected, "selection": selection,
        "selected_line_id": world.get_resource::<SelectedLine>().map(|l|id(l.0)),
        "time_seconds": world.get_resource::<Timing>().map(|t|t.now()),
        "chart_time_seconds": world.get_resource::<ChartTime>().map(|t|t.0),
        "audio_duration_seconds": world.get_resource::<phichain_game::audio::AudioDuration>().map(|d|d.0.as_secs_f64()),
        "current_beat": world.get_resource::<ChartTime>().zip(world.get_resource::<BpmList>()).map(|(t,b)|b.beat_at_f32(t.0)),
        "paused": world.get_resource::<Paused>().map(|p|p.0),
        "can_undo": history.map(|h|h.0.can_undo()), "can_redo": history.map(|h|h.0.can_redo()),
        "undo_author": history.and_then(|h| h.next_author(false)),
        "redo_author": history.and_then(|h| h.next_author(true)),
        "saved": history.map(|h|h.0.is_saved())
    })
}

fn handle(world: &mut World, request: &Value) -> Result<Value> {
    let method = request["tool"].as_str().context("Missing tool")?;
    let args = &request["arguments"];
    // Lifecycle tools must also work on the home screen, before any project exists.
    match method {
        "analyze_audio" => return analysis::start(world, args),
        "read_audio_features" => return analysis::read(world, args),
        "editor_status" => {
            let project = if world.contains_resource::<Project>() {
                let data = snapshot(world)?;
                Some(context(world, &data))
            } else {
                None
            };
            let state = world.get_resource::<Lifecycle>();
            return Ok(json!({"connected":true,"pid":std::process::id(),
                "version":env!("CARGO_PKG_VERSION"),"executable":std::env::current_exe().ok(),
                "project":project,"pending":state.and_then(|s|s.pending.as_ref()),
                "last_error":state.and_then(|s|s.error.as_ref())}));
        }
        "open_project" => {
            if world.contains_resource::<Project>() {
                bail!("Close the current project first; unsaved work is never discarded")
            }
            if world
                .get_resource::<Lifecycle>()
                .is_some_and(|s| s.pending.is_some())
            {
                bail!("A project lifecycle request is still pending")
            }
            let path = PathBuf::from(args["path"].as_str().context("path must be a string")?)
                .canonicalize()?;
            let project = Project::open(path.clone())?;
            phichain_chart::serialization::PhichainChart::from_json_str(&std::fs::read_to_string(
                project.path.chart_path(),
            )?)?;
            world.init_resource::<Lifecycle>();
            world.resource_mut::<Lifecycle>().pending = Some("open".into());
            world.resource_mut::<Lifecycle>().error = None;
            world.write_message(crate::project::LoadProject(path.clone()));
            return Ok(json!({"status":"requested","path":path,"next":"editor_status"}));
        }
        _ => {}
    }
    let data = snapshot(world)?;
    match method {
        "get_context" => Ok(context(world, &data)),
        "authoring_read" => {
            check_revision(args, &data)?; idle(world)?;
            Ok(json!({"session":data["session"],"revision":data["revision"],"document":authoring::document(&data)}))
        },
        "authoring_commit" => authoring::commit(world, args, &data),
        "authoring_diagnose" => { check_revision(args,&data)?; quality::validate_chart(world,args,&data) },
        "authoring_view" => { check_revision(args,&data)?; quality::select_objects(world,args,&data) },
        "close_project" => {
            check_revision(args, &data)?;
            idle(world)?;
            if !world.resource::<EditorHistory>().0.is_saved() {
                bail!("Save the current project before closing it")
            }
            world.write_message(crate::project::UnloadProject);
            Ok(json!({"status":"requested","next":"editor_status"}))
        }
        "project_snapshot" => {
            check_revision(args, &data)?;
            idle(world)?;
            let chart = world
                .run_system_once(|c: SerializeChartParam, l: SerializeLineParam| {
                    serialize_chart(c, l)
                })
                .map_err(|e| anyhow!("{e}"))?;
            let project = world.resource::<Project>();
            Ok(
                json!({"session":data["session"],"revision":data["revision"],"chart":chart,
                "meta":project.meta,"music_path":project.path.music_path(),
                "illustration_path":project.path.illustration_path()}),
            )
        }
        "read_section" => read_section(&data, args),
        "inspect_motion" => motion::inspect(world, args, &data),
        "animate_selection" => animation::animate(world, args, &data),
        "validate_chart" => quality::validate_chart(world, args, &data),
        "select_objects" => quality::select_objects(world, args, &data),
        "set_editor_view" => quality::set_editor_view(world, args, &data),
        "apply_edits" => apply_edits(world, args, &data, false),
        "validate_edits" => apply_edits(world, args, &data, true),
        "set_bpm_list" => apply_edits(
            world,
            &json!({"session":args["session"],"revision":args["revision"],"operations":[{"op":"set_bpm_list","bpm_list":args["bpm_list"]}]}),
            &data,
            false,
        ),
        "preview" => {
            if args["session"] != data["session"] {
                bail!("Project changed; read context again")
            }
            if !world.contains_resource::<phichain_game::audio::InstanceHandle>() {
                bail!("Audio is not ready")
            }
            let action = args["action"].as_str().context("Missing preview action")?;
            if !["play", "pause", "seek"].contains(&action) {
                bail!("action must be play, pause, or seek")
            }
            let seconds = args
                .get("time_seconds")
                .map(|v| v.as_f64().context("time_seconds must be a number"))
                .transpose()?;
            if let Some(seconds) = seconds {
                if !seconds.is_finite() || seconds < 0.0 || seconds > f32::MAX as f64 {
                    bail!("Invalid preview time")
                }
                world.write_message(SeekTo(seconds as f32));
            }
            match args["action"].as_str() {
                Some("play") => {
                    if world.get_resource::<Paused>().is_some_and(|p| p.0) {
                        world.trigger(Resume);
                    }
                }
                Some("pause") => {
                    if world.get_resource::<Paused>().is_some_and(|p| !p.0) {
                        world.trigger(Pause);
                    }
                }
                Some("seek") => {
                    if seconds.is_none() {
                        bail!("seek requires time_seconds")
                    }
                }
                _ => bail!("action must be play, pause, or seek"),
            }
            Ok(
                json!({"status":"requested","action":args["action"],"time_seconds":seconds,"session":data["session"]}),
            )
        }
        "history" => {
            check_revision(args, &data)?;
            idle(world)?;
            let redo = match args["action"].as_str() {
                Some("undo") => false,
                Some("redo") => true,
                _ => bail!("action must be undo or redo"),
            };
            let author = match args["author"].as_str() {
                Some(author @ ("agent" | "human")) => author,
                _ => bail!("author must be agent or human"),
            };
            let history = world.resource::<EditorHistory>();
            if !(if redo {
                history.0.can_redo()
            } else {
                history.0.can_undo()
            }) {
                bail!("No history entry available")
            }
            if history.next_author(redo) != Some(author) {
                bail!("Next history entry belongs to {}; requested {}. No changes made",
                    history.next_author(redo).unwrap(), author)
            }
            world.resource_scope(
                |w, mut h: Mut<EditorHistory>| {
                    if redo {
                        h.redo(w)
                    } else {
                        h.undo(w)
                    }
                },
            );
            reset_inspector_latches(world);
            let data = snapshot(world)?;
            Ok(context(world, &data))
        }
        "save" => {
            check_revision(args, &data)?;
            idle(world)?;
            let chart = world
                .run_system_once(|c: SerializeChartParam, l: SerializeLineParam| {
                    serialize_chart(c, l)
                })
                .map_err(|e| anyhow!("{e}"))?;
            let project = world.resource::<Project>();
            std::fs::write(project.path.chart_path(), serde_json::to_vec(&chart)?)?;
            std::fs::write(project.path.meta_path(), serde_json::to_vec(&project.meta)?)?;
            world.resource_mut::<EditorHistory>().0.set_saved();
            Ok(json!({"saved":true,"session":data["session"],"revision":data["revision"]}))
        }
        _ => bail!("Unknown tool: {method}"),
    }
}

fn read_section(data: &Value, args: &Value) -> Result<Value> {
    let start = args
        .get("start_beat")
        .map(|v| v.as_f64().context("start_beat must be numeric"))
        .transpose()?
        .unwrap_or(0.0);
    let end = args
        .get("end_beat")
        .map(|v| v.as_f64().context("end_beat must be numeric"))
        .transpose()?
        .unwrap_or(start + 32.0);
    if !start.is_finite() || !end.is_finite() || end <= start {
        bail!("end_beat must exceed start_beat")
    }
    let line = args
        .get("line_id")
        .map(|v| v.as_str().context("line_id must be an ID string"))
        .transpose()?;
    if let Some(line) = line {
        if !data["lines"]
            .as_array()
            .unwrap()
            .iter()
            .any(|l| l["id"] == line)
        {
            bail!("Unknown line_id")
        }
    }
    let mut result = json!({"session":data["session"],"revision":data["revision"],"start_beat":start,"end_beat":end,"lines":data["lines"],"bpm_list":data["bpm_list"],"offset":data["offset"],"curve_tracks":data["curve_tracks"]});
    for (key, field) in [("notes", "note"), ("events", "event")] {
        let values: Vec<_> = data[key]
            .as_array()
            .unwrap()
            .iter()
            .filter(|v| {
                if line.is_some_and(|line| v["line_id"] != line) {
                    return false;
                }
                let item = &v[field];
                let (from, to) = if field == "note" {
                    let b = beat_value(&item["beat"]);
                    let h = item.get("hold_beat").map(beat_value).unwrap_or(0.0);
                    (b, b + h)
                } else {
                    (
                        beat_value(&item["start_beat"]),
                        beat_value(&item["end_beat"]),
                    )
                };
                from < end && to >= start
            })
            .cloned()
            .collect();
        result[key] = json!(values);
    }
    Ok(result)
}
fn beat_value(v: &Value) -> f64 {
    v[0].as_f64().unwrap_or(0.0) + v[1].as_f64().unwrap_or(0.0) / v[2].as_f64().unwrap_or(1.0)
}

// Beat's repository deserializer panics on denominator zero. Validate raw JSON first.
fn validate_beats(value: &Value) -> Result<()> {
    match value {
        Value::Object(map) => {
            for (key, value) in map {
                if ["beat", "hold_beat", "start_beat", "end_beat"].contains(&key.as_str()) {
                    let b = value
                        .as_array()
                        .context("Beat must be [whole, numerator, denominator]")?;
                    if b.len() != 3 {
                        bail!("Beat must have three integers")
                    }
                    let parts: Vec<_> = b
                        .iter()
                        .map(|v| v.as_i64().context("Beat entries must be integers"))
                        .collect::<Result<_>>()?;
                    if !(-1_000_000..=1_000_000).contains(&parts[0])
                        || parts[1] < 0
                        || parts[1] >= parts[2]
                        || !(1..=10_000).contains(&parts[2])
                    {
                        bail!("Beat values out of range; denominator must be positive")
                    }
                } else {
                    validate_beats(value)?;
                }
            }
        }
        Value::Array(values) => {
            for v in values {
                validate_beats(v)?;
            }
        }
        _ => {}
    }
    Ok(())
}

fn apply_edits(world: &mut World, args: &Value, data: &Value, dry_run: bool) -> Result<Value> {
    check_revision(args, data)?;
    idle(world)?;
    validate_beats(args)?;
    let ops = args["operations"]
        .as_array()
        .context("operations must be an array")?;
    if ops.is_empty() || ops.len() > 1000 {
        bail!("Provide 1–1000 operations")
    }
    structure::validate_batch(world, ops)?;
    let mut commands = Vec::new();
    let mut touched = HashSet::new();
    let mut summary = Vec::new();
    for op in ops {
        let action = op["op"].as_str().context("Missing operation op")?;
        let mut change = json!({"op":action});
        match action {
            "create_line" => {
                let name = op["name"]
                    .as_str()
                    .context("Line name must be a string")?
                    .to_owned();
                if name.trim().is_empty() || name.len() > 256 {
                    bail!("Line name must be 1–256 bytes")
                }
                let parent = match op.get("parent_id") {
                    None | Some(Value::Null) => None,
                    _ => Some(entity(op, "parent_id")?),
                };
                if parent.is_some_and(|p| world.get::<Line>(p).is_none()) {
                    bail!("Unknown parent line")
                }
                commands.push(EditorCommand::McpStructure(
                    structure::StructureCommand::Create {
                        name: name.clone(),
                        parent,
                        entity: None,
                        saved: None,
                    },
                ));
                change["after"] = json!({"name":name,"parent_id":parent.map(id)});
            }
            "update_line" | "delete_line" => {
                let target = entity(op, "id")?;
                if !touched.insert(target) {
                    bail!("Each target may appear only once per batch")
                }
                let from = world.get::<Line>(target).context("Unknown line")?.clone();
                change["id"] = json!(id(target));
                change["before"] = json!(from);
                if action == "delete_line" {
                    commands.push(EditorCommand::McpStructure(
                        structure::StructureCommand::Remove {
                            entity: target,
                            saved: None,
                        },
                    ));
                } else {
                    let name = op["name"]
                        .as_str()
                        .context("Line name must be a string")?
                        .to_owned();
                    if name.trim().is_empty() || name.len() > 256 {
                        bail!("Line name must be 1–256 bytes")
                    }
                    let old_parent = world.get::<ChildOf>(target).map(|p| p.parent());
                    let new_parent = match op.get("parent_id") {
                        None => old_parent,
                        Some(Value::Null) => None,
                        _ => Some(entity(op, "parent_id")?),
                    };
                    let to = Line { name, role: from.role };
                    change["after"] = json!(to);
                    commands.push(EditorCommand::McpStructure(
                        structure::StructureCommand::Update {
                            entity: target,
                            from,
                            to,
                            old_parent,
                            new_parent,
                        },
                    ));
                }
            }
            "reorder_lines" => {
                if ops.iter().any(|o| {
                    ["create_line", "update_line", "delete_line"]
                        .contains(&o["op"].as_str().unwrap_or(""))
                }) || ops.iter().filter(|o| o["op"] == "reorder_lines").count() > 1
                {
                    bail!("Reordering must be separate from structural line edits")
                }
                let roots: Vec<_> = world
                    .query_filtered::<(Entity, &LineOrder), (With<Line>, Without<ChildOf>)>()
                    .iter(world)
                    .map(|(e, o)| (e, o.0))
                    .collect();
                let values = op["line_ids"]
                    .as_array()
                    .context("line_ids must be an array")?;
                let to: Vec<_> = values
                    .iter()
                    .enumerate()
                    .map(|(i, v)| Ok((entity(&json!({"id":v}), "id")?, i as u64)))
                    .collect::<Result<_>>()?;
                let keys: HashSet<_> = to.iter().map(|(e, _)| *e).collect();
                if keys.len() != to.len() || keys != roots.iter().map(|(e, _)| *e).collect() {
                    bail!("Provide every root line exactly once")
                }
                commands.push(EditorCommand::McpStructure(
                    structure::StructureCommand::Reorder { from: roots, to },
                ));
            }
            "create_curve_track" | "update_curve_track" | "delete_curve_track" => {
                use crate::editing::command::curve_note_track::{
                    CreateCurveNoteTrack, RemoveCurveNoteTrack,
                };
                if action == "create_curve_track" {
                    let line = entity(op, "line_id")?;
                    if world.get::<Line>(line).is_none() {
                        bail!("Unknown line")
                    }
                    let track = structure::parse_curve(world, op, line)?;
                    change["line_id"] = json!(id(line));
                    commands.push(EditorCommand::CreateCurveNoteTrack(
                        CreateCurveNoteTrack::new(line, track),
                    ));
                } else {
                    let target = entity(op, "id")?;
                    if !touched.insert(target) {
                        bail!("Each target may appear only once per batch")
                    }
                    let from = world
                        .get::<CurveNoteTrack>(target)
                        .context("Unknown curve track")?
                        .clone();
                    change["id"] = json!(id(target));
                    if action == "delete_curve_track" {
                        commands.push(EditorCommand::RemoveCurveNoteTrack(
                            RemoveCurveNoteTrack::new(target),
                        ));
                    } else {
                        let line = world
                            .get::<ChildOf>(target)
                            .context("Track has no line")?
                            .parent();
                        let to = structure::parse_curve(world, op, line)?;
                        commands.push(EditorCommand::McpStructure(
                            structure::StructureCommand::CurveUpdate {
                                entity: target,
                                from,
                                to,
                            },
                        ));
                    }
                }
            }
            "create_note" | "create_event" => {
                let line = entity(op, "line_id")?;
                if world.get::<Line>(line).is_none() {
                    bail!("line_id is not a current line")
                }
                change["line_id"] = json!(id(line));
                if action == "create_note" {
                    let note = parse_note(&op["note"])?;
                    commands.push(EditorCommand::CreateNote(CreateNote::new(line, note)));
                    change["after"] = json!(note);
                } else {
                    let event = parse_event(&op["event"])?;
                    commands.push(EditorCommand::CreateEvent(CreateEvent::new(line, event)));
                    change["after"] = json!(event);
                }
            }
            "update_note" | "delete_note" | "update_event" | "delete_event" => {
                let target = entity(op, "id")?;
                if !touched.insert(target) {
                    bail!("Each target may appear only once per batch")
                }
                change["id"] = json!(id(target));
                if action.ends_with("note") {
                    if world.get::<CurveNote>(target).is_some() {
                        bail!("Generated curve notes cannot be edited directly")
                    }
                    let from = *world
                        .get::<Note>(target)
                        .context("id is not a current note")?;
                    let parent = world
                        .get::<ChildOf>(target)
                        .context("Note has no line")?
                        .parent();
                    if world.get::<Line>(parent).is_none() {
                        bail!("Note parent is not a line")
                    }
                    change["before"] = json!(from);
                    if action == "update_note" {
                        let to = parse_note(&op["note"])?;
                        commands.push(EditorCommand::EditNote(EditNote::new(target, from, to)));
                        change["after"] = json!(to);
                    } else {
                        if world
                            .query::<&CurveNoteTrack>()
                            .iter(world)
                            .any(|t| t.from == Some(target) || t.to == Some(target))
                        {
                            bail!("Cannot delete a curve track endpoint")
                        }
                        commands.push(EditorCommand::RemoveNote(RemoveNote::new(target)));
                    }
                } else {
                    let from = *world
                        .get::<LineEvent>(target)
                        .context("id is not a current line event")?;
                    let parent = world
                        .get::<EventOf>(target)
                        .context("Event has no line")?
                        .target();
                    if world.get::<Line>(parent).is_none() {
                        bail!("Event parent is not a line")
                    }
                    change["before"] = json!(from);
                    if action == "update_event" {
                        let to = parse_event(&op["event"])?;
                        commands.push(EditorCommand::EditEvent(EditEvent::new(target, from, to)));
                        change["after"] = json!(to);
                    } else {
                        commands.push(EditorCommand::RemoveEvent(RemoveEvent::new(target)));
                    }
                }
            }
            "set_bpm_list" => {
                if ops.iter().filter(|o| o["op"] == "set_bpm_list").count() > 1 {
                    bail!("Only one set_bpm_list per batch")
                }
                let from = world.resource::<BpmList>().clone();
                let to = analysis::parse_bpm(&op["bpm_list"])?;
                change["before"] = json!(from);
                change["after"] = json!(to);
                commands.push(EditorCommand::SetBpmList(analysis::SetBpmList { from, to }));
            }
            "set_offset" => {
                if ops.iter().filter(|o| o["op"] == "set_offset").count() > 1 {
                    bail!("Only one set_offset per batch")
                }
                let from = world.resource::<Offset>().0;
                let to: f32 = serde_json::from_value(op["offset"].clone())?;
                if !to.is_finite() {
                    bail!("Offset must be finite")
                }
                commands.push(EditorCommand::EditOffset(EditOffset::new(from, to)));
                change["before"] = json!(from);
                change["after"] = json!(to);
            }
            "set_meta" => {
                if ops.iter().filter(|o| o["op"] == "set_meta").count() > 1 {
                    bail!("Only one set_meta per batch")
                }
                let from = world.resource::<Project>().meta.clone();
                let to = serde_json::from_value(op["meta"].clone())?;
                change["before"] = json!(from);
                change["after"] = json!(to);
                commands.push(EditorCommand::EditMeta(EditMeta::new(from, to)));
            }
            _ => bail!("Unsupported operation: {action}"),
        }
        summary.push(change);
    }
    // Build and validate commands without executing them during agent planning.
    if dry_run {
        return Ok(
            json!({"session":data["session"],"revision":data["revision"],
            "valid":true,"changes":summary,"undo_steps":0,
            "limitations":["Structural edit validation, not prospective rendered geometry"]}),
        );
    }
    // No mutation until the entire batch is validated.
    world.resource_scope(|w, mut h: Mut<EditorHistory>| {
        h.edit(w, EditorCommand::AgentSequence(CommandSequence(commands)));
        if let Some(EditorCommand::AgentSequence(sequence)) =
            h.0.entries().last().map(|entry| entry.as_ref())
        {
            for (command, change) in sequence.0.iter().zip(summary.iter_mut()) {
                match command {
                    EditorCommand::CreateNote(c) => change["id"] = json!(c.note_entity.map(id)),
                    EditorCommand::CreateEvent(c) => change["id"] = json!(c.event_entity.map(id)),
                    EditorCommand::CreateCurveNoteTrack(c) => {
                        change["id"] = json!(c.track_entity.map(id))
                    }
                    EditorCommand::McpStructure(structure::StructureCommand::Create {
                        entity,
                        ..
                    }) => change["id"] = json!(entity.map(id)),
                    _ => {}
                }
            }
        }
    });
    reset_inspector_latches(world);
    let after = snapshot(world)?;
    Ok(
        json!({"session":after["session"],"revision":after["revision"],"changes":summary,"undo_steps":1}),
    )
}
fn parse_note(value: &Value) -> Result<Note> {
    let note: Note = serde_json::from_value(value.clone())?;
    if !note.x.is_finite() || !note.speed.is_finite() || note.speed <= 0.0 {
        bail!("Note x must be finite and speed positive")
    }
    if note.beat < Beat::ZERO {
        bail!("Note beat must be nonnegative")
    }
    if let NoteKind::Hold { hold_beat } = note.kind {
        if hold_beat <= Beat::ZERO {
            bail!("Hold duration must be positive")
        }
    }
    Ok(note)
}
fn parse_event(value: &Value) -> Result<LineEvent> {
    let event: LineEvent = serde_json::from_value(value.clone())?;
    if event.start_beat < Beat::ZERO
        || event.end_beat < event.start_beat
        || !event.value.start().is_finite()
        || !event.value.end().is_finite()
    {
        bail!("Invalid event range or value")
    }
    if let phichain_chart::easing::Easing::Custom { x1, y1, x2, y2 } = event.value.easing() {
        if ![x1, y1, x2, y2].iter().all(|v| v.is_finite()) {
            bail!("Custom easing coordinates must be finite")
        }
    }
    match event.value.easing() {
        phichain_chart::easing::Easing::Elastic { omega }
            if !omega.is_finite() || omega.abs() < 0.001 =>
        {
            bail!("Elastic omega must be finite and nonzero")
        }
        phichain_chart::easing::Easing::Steps { count } if !(1..=10000).contains(&count) => {
            bail!("Steps count must be 1–10000")
        }
        _ => {}
    }
    Ok(event)
}

#[cfg(test)]
mod tests {
    use super::*;
    use phichain_chart::{
        beat,
        project::{ProjectMeta, ProjectPath},
    };

    #[test]
    fn human_line_role_changes_invalidate_guard_and_mcp_rename_preserves_role() {
        let (mut app, line) = editor(); let w = app.world_mut();
        let before = snapshot(w).unwrap();
        w.get_mut::<Line>(line).unwrap().role = phichain_chart::line::LineRole::Complex;
        let after = snapshot(w).unwrap();
        assert_ne!(before["revision"], after["revision"]);
        assert_eq!(after["lines"][0]["role"], "complex");
        let ops=json!([{"op":"update_line","id":id(line),"name":"Renamed"}]);
        assert!(call(w,"apply_edits",json!({"session":before["session"],"revision":before["revision"],"operations":ops})).is_err());
        let args=edits(w,ops);call(w,"apply_edits",args).unwrap();
        assert_eq!(w.get::<Line>(line).unwrap().role,phichain_chart::line::LineRole::Complex);
    }

    #[test]
    fn animation_rejects_incompatible_groups_dependencies_and_budget_without_mutation() {
        let (mut app, line) = editor(); let w = app.world_mut();
        let other = w.spawn(Line::default()).id();
        let a=w.spawn((parse_note(&note(10)).unwrap(),ChildOf(line))).id();
        let b=w.spawn((parse_note(&note(20)).unwrap(),ChildOf(other))).id();
        let event=json!({"kind":"x","start_beat":[0,0,1],"end_beat":[4,0,1],"value":{"type":"constant","value":120}});
        let before=snapshot(w).unwrap();
        let args=json!({"session":before["session"],"revision":before["revision"],"dry_run":false,
            "groups":[{"carrier_id":id(line),"note_ids":[id(a)],"events":[event.clone()]}]});
        let mut bad=args.clone(); bad["line_budget"]=json!(1);
        assert!(call(w,"animate_selection",bad).is_err());
        let mut bad=args.clone(); bad["groups"].as_array_mut().unwrap().push(json!({"carrier_id":id(other),"note_ids":[id(b)],"events":[event.clone(),event.clone()]}));
        assert!(call(w,"animate_selection",bad).is_err()); assert_eq!(snapshot(w).unwrap(),before);
        let child=w.spawn((Line::default(),ChildOf(line))).id();
        let mut bad=args.clone();bad["revision"]=snapshot(w).unwrap()["revision"].clone();
        assert!(call(w,"animate_selection",bad).is_err());w.despawn(child);
        w.spawn((parse_event(&event).unwrap(),EventOf(other)));
        let before=snapshot(w).unwrap();
        let mut bad=args; bad["revision"]=before["revision"].clone();bad["groups"][0]["note_ids"]=json!([id(a),id(b)]);
        assert!(call(w,"animate_selection",bad).is_err());assert_eq!(snapshot(w).unwrap(),before);
    }

    #[test]
    fn animation_groups_merge_atomically_preserve_notes_and_undo() {
        let (mut app, line) = editor(); let w = app.world_mut();
        let other = w.spawn(Line::default()).id();
        let a = w.spawn((parse_note(&note(10)).unwrap(), ChildOf(line))).id();
        let b = w.spawn((parse_note(&note(20)).unwrap(), ChildOf(other))).id();
        let before_note = *w.get::<Note>(b).unwrap();
        let before = snapshot(w).unwrap();
        let mut args = json!({"session":before["session"],"revision":before["revision"],"dry_run":true,
            "groups":[{"carrier_id":id(line),"note_ids":[id(a),id(b)],"events":[
                {"kind":"speed","start_beat":[0,0,1],"end_beat":[8,0,1],"value":{"type":"constant","value":0}},
                {"kind":"speed","start_beat":[8,0,1],"end_beat":[9,0,1],"value":{"type":"constant","value":-12}},
                {"kind":"speed","start_beat":[9,0,1],"end_beat":[30,0,1],"value":{"type":"constant","value":2.4}}
            ]}]});
        call(w,"animate_selection",args.clone()).unwrap();
        assert_eq!(snapshot(w).unwrap(),before);
        let mut bad=args.clone(); bad["groups"][0]["note_ids"]=json!([id(a)]);
        // Destination ownership includes future notes, not only passage judgments.
        let future=w.spawn((parse_note(&note(50)).unwrap(),ChildOf(line))).id();
        let current=snapshot(w).unwrap(); bad["revision"]=current["revision"].clone();
        assert!(call(w,"animate_selection",bad).is_err()); w.despawn(future);
        for mutation in [json!({"start_beat":[0,0,0]}),json!({"end_beat":[0,0,1]})] {
            let mut bad=args.clone(); for (k,v) in mutation.as_object().unwrap() { bad["groups"][0]["events"][0][k]=v.clone(); }
            assert!(call(w,"animate_selection",bad).is_err());
        }
        args["dry_run"]=json!(false);
        let applied=call(w,"animate_selection",args.clone()).unwrap();
        assert_eq!(applied["undo_steps"],1); assert_eq!(applied["new_lines"],0);
        assert_eq!(w.get::<ChildOf>(b).unwrap().parent(),line);
        assert_eq!(json!(w.get::<Note>(b).unwrap()),json!(before_note));
        assert!(call(w,"animate_selection",args).is_err());
        call(w,"history",json!({"session":applied["session"],"revision":applied["revision"],"action":"undo","author":"agent"})).unwrap();
        assert_eq!(w.get::<ChildOf>(b).unwrap().parent(),other);
        assert_eq!(w.query::<&LineEvent>().iter(w).count(),0);
        let undone=snapshot(w).unwrap();
        call(w,"history",json!({"session":undone["session"],"revision":undone["revision"],"action":"redo","author":"agent"})).unwrap();
        assert_eq!(w.get::<ChildOf>(b).unwrap().parent(),line);
        assert_eq!(w.query::<&LineEvent>().iter(w).count(),3);
    }

    fn editor() -> (App, Entity) {
        let mut app = App::new();
        app.add_plugins(phichain_game::line::LinePlugin);
        app.insert_resource(Project {
            id: uuid::Uuid::new_v4(),
            path: ProjectPath(PathBuf::from("unused")),
            meta: ProjectMeta::default(),
        });
        app.insert_resource(BpmList::default())
            .insert_resource(Offset::default())
            .init_resource::<EditorHistory>();
        let line = app.world_mut().spawn(Line::default()).id();
        (app, line)
    }
    fn note(beat: i32) -> Value {
        json!({"kind":"tap","above":true,"beat":[beat,0,1],"x":0.0,"speed":1.0})
    }
    fn edits(world: &mut World, operations: Value) -> Value {
        let data = snapshot(world).unwrap();
        json!({"session":data["session"],"revision":data["revision"],"operations":operations})
    }
    fn call(world: &mut World, tool: &str, arguments: Value) -> Result<Value> {
        handle(world, &json!({"tool":tool,"arguments":arguments}))
    }
    #[test]
    fn authoring_document_creates_dependencies_moves_ids_and_undo_redo_atomically() {
        let (mut app, line) = editor(); let w=app.world_mut();
        let n=w.spawn((parse_note(&note(8)).unwrap(),ChildOf(line),Selected)).id();
        w.insert_resource(SelectedLine(line));
        let before=snapshot(w).unwrap();
        let mut doc=authoring::document(&before);
        doc["lines"]["new:carrier"]=json!({"name":"Motion","role":"complex","parent_id":id(line),"order":1});
        doc["notes"][id(n)]["line_id"]=json!("new:carrier");
        doc["notes"][id(n)]["note"]["x"]=json!(120);
        doc["notes"]["new:hold"]=json!({"line_id":"new:carrier","note":{"kind":"hold","above":true,"beat":[9,0,1],"hold_beat":[2,0,1],"x":-50,"speed":1}});
        doc["events"]["new:motion"]=json!({"line_id":"new:carrier","event":{"kind":"x","start_beat":[4,0,1],"end_beat":[8,0,1],"value":{"type":"transition","start":-200,"end":0,"easing":{"type":"ease_out_sine"}}}});
        let args=json!({"session":before["session"],"revision":before["revision"],"dry_run":true,"document":doc});
        let dry=call(w,"authoring_commit",args.clone()).unwrap(); assert_eq!(dry["undo_steps"],0);
        assert_eq!(snapshot(w).unwrap(),before);
        let mut actual=args.clone();actual["dry_run"]=json!(false);
        let result=call(w,"authoring_commit",actual.clone()).unwrap();
        assert_eq!(result["undo_steps"],1);
        let carrier=entity(&json!({"id":result["created_ids"]["new:carrier"]}),"id").unwrap();
        let hold=entity(&json!({"id":result["created_ids"]["new:hold"]}),"id").unwrap();
        assert_eq!(w.get::<ChildOf>(n).unwrap().parent(),carrier);
        assert_eq!(w.get::<Note>(n).unwrap().x,120.);
        assert_eq!(w.get::<Note>(n).unwrap().beat,beat!(8));
        assert!(w.get::<Selected>(n).is_some());
        assert!(call(w,"authoring_commit",actual).is_err());
        w.resource_scope(|w,mut h:Mut<EditorHistory>|h.undo(w));
        assert_eq!(snapshot(w).unwrap()["notes"],before["notes"]);
        assert_eq!(w.get::<ChildOf>(n).unwrap().parent(),line);
        assert!(w.get::<Note>(hold).is_none()); assert!(w.get::<Line>(carrier).is_none());
        w.resource_scope(|w,mut h:Mut<EditorHistory>|h.redo(w));
        assert!(w.get::<Note>(hold).is_some()); assert_eq!(w.get::<ChildOf>(n).unwrap().parent(),carrier);
        assert_eq!(w.resource::<EditorHistory>().next_author(false),Some("agent"));
        // Native renderer serialization sees the same live result.
        let captured=snapshot(w).unwrap();
        let live=call(w,"project_snapshot",json!({"session":captured["session"],"revision":captured["revision"]})).unwrap();
        assert!(live["chart"].is_object());
    }

    #[test]
    fn authoring_rejects_invalid_candidates_and_pending_state_without_partial_changes() {
        let (mut app,line)=editor();let w=app.world_mut();
        let n=w.spawn((parse_note(&note(4)).unwrap(),ChildOf(line))).id();
        let before=snapshot(w).unwrap();let valid=authoring::document(&before);
        let mut candidates=vec![];
        let mut v=valid.clone();v["notes"][id(n)]["line_id"]=json!("new:missing");candidates.push(v);
        let mut v=valid.clone();v["lines"][id(line)]["parent_id"]=json!(id(line));candidates.push(v);
        let mut v=valid.clone();v["notes"][id(n)]["note"]["beat"]=json!([0,1,0]);candidates.push(v);
        let mut v=valid.clone();v["notes"][id(n)]["note"]["isFake"]=json!(1);candidates.push(v);
        let mut v=valid.clone();v["meta"]["unknown"]=json!(true);candidates.push(v);
        let mut v=valid.clone();v["notes"]["123"]=json!({"line_id":id(line),"note":note(8)});candidates.push(v);
        let mut v=valid.clone();v["lines"]=json!({});candidates.push(v);
        for doc in candidates {
            let args=json!({"session":before["session"],"revision":before["revision"],"dry_run":false,"document":doc});
            assert!(call(w,"authoring_commit",args).is_err());assert_eq!(snapshot(w).unwrap(),before);
            assert_eq!(w.resource::<EditorHistory>().0.len(),0);
        }
        w.entity_mut(n).insert(Pending);
        let data=snapshot(w).unwrap();
        assert!(call(w,"authoring_commit",json!({"session":data["session"],"revision":data["revision"],"dry_run":false,"document":valid})).is_err());
    }

    #[test]
    fn authoring_checks_curve_ownership_and_noop_has_no_history() {
        let (mut app,line)=editor();let w=app.world_mut();
        let a=w.spawn((parse_note(&note(4)).unwrap(),ChildOf(line))).id();
        let b=w.spawn((parse_note(&note(8)).unwrap(),ChildOf(line))).id();
        let track=w.spawn((CurveNoteTrack{from:Some(a),to:Some(b),options:Default::default()},ChildOf(line))).id();
        let data=snapshot(w).unwrap(); let doc=authoring::document(&data);
        let args=json!({"session":data["session"],"revision":data["revision"],"dry_run":false,"document":doc});
        assert_eq!(call(w,"authoring_commit",args.clone()).unwrap()["undo_steps"],0);
        let mut bad=args.clone();bad["document"]["notes"].as_object_mut().unwrap().remove(&id(a));
        assert!(call(w,"authoring_commit",bad).is_err());
        assert!(w.get::<CurveNoteTrack>(track).is_some());
        let mut valid=args;valid["document"]["notes"][id(a)]["note"]["x"]=json!(50);
        call(w,"authoring_commit",valid).unwrap();assert_eq!(w.get::<Note>(a).unwrap().x,50.);
        let current=snapshot(w).unwrap();let mut decimal=authoring::document(&current);
        decimal["notes"][id(a)]["note"]["x"]=json!(0.1);
        call(w,"authoring_commit",json!({"session":current["session"],"revision":current["revision"],"dry_run":false,"document":decimal})).unwrap();
        assert_eq!(w.get::<Note>(a).unwrap().x,0.1_f32);
    }

    #[test]
    fn motion_inspection_uses_hidden_carriers_parent_rotation_and_offset_without_mutation() {
        use phichain_chart::event::{LineEventKind, LineEventValue};
        let (mut app, parent) = editor();
        let w = app.world_mut();
        w.insert_resource(Offset(500.0));
        let child = w.spawn((Line::default(), ChildOf(parent))).id();
        let n = w.spawn((Note::new(NoteKind::Tap, true, beat!(4), 100.0, 1.0), ChildOf(child), Selected)).id();
        let h = w.spawn((Note::new(NoteKind::Hold { hold_beat: beat!(2) }, false, beat!(2), 0.0, 1.0), ChildOf(child))).id();
        for (line,kind,value) in [(parent,LineEventKind::Rotation,90.0),(child,LineEventKind::X,200.0),
                (child,LineEventKind::Opacity,0.0),(child,LineEventKind::Speed,0.0)] {
            w.spawn((LineEvent {kind,start_beat:beat!(0),end_beat:beat!(10),value:LineEventValue::constant(value)}, EventOf(line)));
        }
        let before = snapshot(w).unwrap();
        let args = json!({"session":before["session"],"revision":before["revision"],"from_seconds":0.5,"to_seconds":1.5,"frames":3});
        let result = call(w,"inspect_motion",args.clone()).unwrap();
        assert_eq!(result["notes"].as_array().unwrap().len(),1);
        assert_eq!(result["notes"][0]["id"],id(n));
        assert_eq!(result["lines"].as_array().unwrap().len(),2);
        for frame in result["frames"].as_array().unwrap() {
            let head=&frame["notes"][0]["head"];
            assert!((head["x"].as_f64().unwrap()-480.0).abs()<0.01);
            assert!((head["y"].as_f64().unwrap()-(270.0-300.0*960.0/1350.0)).abs()<0.01);
            assert_eq!(frame["notes"][0]["visible_by_timing_and_cover"],true);
        }
        assert_eq!(result["frames"][0]["chart_time_seconds"],0.0);
        assert_eq!(before,snapshot(w).unwrap());
        assert!(w.get::<Selected>(n).is_some());
        assert_eq!(w.resource::<EditorHistory>().0.len(),0);
        let mut explicit=args.clone(); explicit["note_ids"]=json!([id(h)]);
        let holds=call(w,"inspect_motion",explicit).unwrap();
        assert!(holds["frames"][0]["notes"][0]["tail"].is_object());
        for change in [json!({"revision":"stale"}),json!({"note_ids":[]}),json!({"note_ids":[id(n),id(n)]}),
                json!({"note_ids":[id(parent)]}),json!({"frames":13}),json!({"to_seconds":20.0}),json!({"from_seconds":-1.0}),json!({"from_seconds":1e100,"to_seconds":1e100})] {
            let mut bad=args.clone();for (k,v) in change.as_object().unwrap(){bad[k]=v.clone();}
            assert!(call(w,"inspect_motion",bad).is_err());
        }
        assert_eq!(before,snapshot(w).unwrap());
    }

    #[test]
    fn history_requires_matching_author_and_preserves_provenance() {
        let (mut app, line) = editor();
        let w = app.world_mut();
        let args = edits(w, json!([{"op":"create_note","line_id":id(line),"note":note(4)}]));
        call(w, "apply_edits", args).unwrap();
        let offset = w.resource::<Offset>().0;
        w.resource_scope(|w, mut h: Mut<EditorHistory>| {
            h.edit(w, EditorCommand::EditOffset(EditOffset::new(offset, offset + 10.0)));
        });
        for (action, author) in [("undo", "human"), ("undo", "agent"),
                                 ("redo", "agent"), ("redo", "human")] {
            let data = call(w, "get_context", json!({})).unwrap();
            assert_eq!(data[format!("{}_author", action)], author);
            for wrong in [Value::Null, json!("invalid"), json!(if author == "agent" { "human" } else { "agent" })] {
                let args = json!({"session":data["session"],"revision":data["revision"],"action":action,"author":wrong});
                assert!(call(w, "history", args).is_err());
                assert_eq!(snapshot(w).unwrap()["revision"], data["revision"]);
            }
            call(w, "history", json!({"session":data["session"],"revision":data["revision"],"action":action,"author":author})).unwrap();
        }
        // Human UI undo and a new human edit must not inherit agent provenance.
        w.resource_scope(|w, mut h: Mut<EditorHistory>| {
            h.undo(w);
            h.undo(w);
            h.edit(w, EditorCommand::EditOffset(EditOffset::new(offset, offset + 20.0)));
        });
        let data = call(w, "get_context", json!({})).unwrap();
        assert_eq!(data["undo_author"], "human");
        assert!(data["redo_author"].is_null());
    }

    #[test]
    fn preflight_validates_without_changing_chart_or_history() {
        let (mut app, line) = editor();
        let w = app.world_mut();
        let before = snapshot(w).unwrap();
        let args = edits(
            w,
            json!([{"op":"create_note","line_id":id(line),"note":note(4)}]),
        );
        let result = call(w, "validate_edits", args.clone()).unwrap();
        assert_eq!(result["undo_steps"], 0);
        assert_eq!(snapshot(w).unwrap(), before);
        let mut invalid = args.clone();
        invalid["operations"]
            .as_array_mut()
            .unwrap()
            .push(json!({"op":"delete_note","id":"0"}));
        assert!(call(w, "validate_edits", invalid).is_err());
        assert_eq!(snapshot(w).unwrap(), before);
        let applied = call(w, "apply_edits", args.clone()).unwrap();
        assert_eq!(applied["undo_steps"], 1);
        assert!(call(w, "validate_edits", args).is_err());
        call(
            w,
            "history",
            json!({"session":applied["session"],"revision":applied["revision"],"action":"undo","author":"agent"}),
        )
        .unwrap();
        assert_eq!(snapshot(w).unwrap()["notes"], before["notes"]);
    }

    #[test]
    fn batch_is_one_undo_step_and_created_ids_survive_redo() {
        let (mut app, line) = editor();
        let w = app.world_mut();
        let args = edits(
            w,
            json!([{"op":"create_note","line_id":id(line),"note":note(4)},{"op":"create_note","line_id":id(line),"note":note(8)}]),
        );
        let result = call(w, "apply_edits", args).unwrap();
        assert_eq!(result["undo_steps"], 1);
        assert_eq!(w.resource::<EditorHistory>().0.len(), 1);
        let created = entity(&result["changes"][0], "id").unwrap();
        assert!(w.get::<Note>(created).is_some());
        let data = snapshot(w).unwrap();
        call(
            w,
            "history",
            json!({"action":"undo","author":"agent","session":data["session"],"revision":data["revision"]}),
        )
        .unwrap();
        assert_eq!(w.query::<&Note>().iter(w).count(), 0);
        let data = snapshot(w).unwrap();
        call(
            w,
            "history",
            json!({"action":"redo","author":"agent","session":data["session"],"revision":data["revision"]}),
        )
        .unwrap();
        assert_eq!(w.query::<&Note>().iter(w).count(), 2);
        assert!(w.get::<Note>(created).is_some());
    }
    #[test]
    fn invalid_later_operation_leaves_entire_batch_unapplied() {
        let (mut app, line) = editor();
        let w = app.world_mut();
        let args = edits(
            w,
            json!([{"op":"create_note","line_id":id(line),"note":note(1)},{"op":"delete_note","id":id(line)}]),
        );
        assert!(call(w, "apply_edits", args).is_err());
        assert_eq!(w.query::<&Note>().iter(w).count(), 0);
        assert_eq!(w.resource::<EditorHistory>().0.len(), 0);
    }
    #[test]
    fn stale_human_edits_and_reopened_projects_are_rejected() {
        let (mut app, line) = editor();
        let w = app.world_mut();
        let args = edits(
            w,
            json!([{"op":"create_note","line_id":id(line),"note":note(1)}]),
        );
        w.spawn((
            Note::new(NoteKind::Tap, true, beat!(2), 0.0, 1.0),
            ChildOf(line),
        ));
        assert!(call(w, "apply_edits", args).is_err());
        let args = edits(
            w,
            json!([{"op":"create_note","line_id":id(line),"note":note(1)}]),
        );
        w.resource_mut::<Project>().id = uuid::Uuid::new_v4();
        assert!(call(w, "apply_edits", args).is_err());
    }
    #[test]
    fn malformed_beats_never_reach_panicking_deserializer() {
        let (mut app, line) = editor();
        let w = app.world_mut();
        for beat in [
            json!([1, 0, 0]),
            json!([1, 0, -1]),
            json!([1, 0]),
            json!([i64::MIN, 0, 1]),
            json!([1, 1, 1_000_000]),
        ] {
            let mut n = note(1);
            n["beat"] = beat;
            let args = edits(w, json!([{"op":"create_note","line_id":id(line),"note":n}]));
            assert!(call(w, "apply_edits", args).is_err());
        }
        assert_eq!(w.query::<&Note>().iter(w).count(), 0);
    }
    #[test]
    fn reads_overlap_holds_and_events_without_generated_notes() {
        let (mut app, line) = editor();
        let w = app.world_mut();
        let n = w
            .spawn((
                Note::new(
                    NoteKind::Hold {
                        hold_beat: beat!(8),
                    },
                    true,
                    beat!(2),
                    0.0,
                    1.0,
                ),
                ChildOf(line),
            ))
            .id();
        w.spawn((
            Note::new(NoteKind::Tap, true, beat!(5), 0.0, 1.0),
            ChildOf(line),
            CurveNote(n),
        ));
        let event = LineEvent {
            kind: phichain_chart::event::LineEventKind::X,
            start_beat: beat!(0),
            end_beat: beat!(16),
            value: phichain_chart::event::LineEventValue::constant(0.0),
        };
        w.spawn((event, EventOf(line)));
        let result = call(
            w,
            "read_section",
            json!({"start_beat":4,"end_beat":8,"line_id":id(line)}),
        )
        .unwrap();
        assert_eq!(result["notes"].as_array().unwrap().len(), 1);
        assert_eq!(result["notes"][0]["id"], id(n));
        assert_eq!(result["events"].as_array().unwrap().len(), 1);
    }
    #[test]
    fn duplicate_targets_curve_endpoints_and_pending_edits_are_rejected() {
        let (mut app, line) = editor();
        let w = app.world_mut();
        let n = w
            .spawn((
                Note::new(NoteKind::Tap, true, beat!(2), 0.0, 1.0),
                ChildOf(line),
            ))
            .id();
        let args = edits(
            w,
            json!([{"op":"update_note","id":id(n),"note":note(3)},{"op":"delete_note","id":id(n)}]),
        );
        assert!(call(w, "apply_edits", args).is_err());
        w.spawn((CurveNoteTrack::start(n), ChildOf(line)));
        let args = edits(w, json!([{"op":"delete_note","id":id(n)}]));
        assert!(call(w, "apply_edits", args).is_err());
        w.entity_mut(n).insert(Pending);
        let args = edits(
            w,
            json!([{"op":"create_note","line_id":id(line),"note":note(3)}]),
        );
        assert!(call(w, "apply_edits", args).is_err());
        assert_eq!(w.get::<Note>(n).unwrap().beat, beat!(2));
    }
    #[test]
    fn event_edit_delete_and_undo_restore_relationships() {
        let (mut app, line) = editor();
        let w = app.world_mut();
        let event = json!({"kind":"speed","start_beat":[0,0,1],"end_beat":[4,0,1],"value":{"type":"constant","value":10.0}});
        let args = edits(
            w,
            json!([{"op":"create_event","line_id":id(line),"event":event}]),
        );
        let result = call(w, "apply_edits", args).unwrap();
        let e = entity(&result["changes"][0], "id").unwrap();
        let mut event = event;
        event["value"]["value"] = json!(20.0);
        let args = edits(w, json!([{"op":"update_event","id":id(e),"event":event}]));
        call(w, "apply_edits", args).unwrap();
        assert_eq!(w.get::<LineEvent>(e).unwrap().value.start(), 20.0);
        let args = edits(w, json!([{"op":"delete_event","id":id(e)}]));
        call(w, "apply_edits", args).unwrap();
        assert!(w.get::<LineEvent>(e).is_none());
        w.resource_scope(|w, mut h: Mut<EditorHistory>| h.undo(w));
        assert_eq!(w.get::<EventOf>(e).unwrap().target(), line);
        assert_eq!(w.get::<LineEvent>(e).unwrap().value.start(), 20.0);
    }
    #[test]
    fn save_serializes_live_chart_and_marks_history_saved() {
        let (mut app, line) = editor();
        let w = app.world_mut();
        let temp = std::env::temp_dir().join(format!("phichain-mcp-test-{}", uuid::Uuid::new_v4()));
        std::fs::create_dir(&temp).unwrap();
        w.resource_mut::<Project>().path = ProjectPath(temp.clone());
        let args = edits(
            w,
            json!([{"op":"create_note","line_id":id(line),"note":note(3)}]),
        );
        call(w, "apply_edits", args).unwrap();
        let data = snapshot(w).unwrap();
        call(
            w,
            "save",
            json!({"session":data["session"],"revision":data["revision"]}),
        )
        .unwrap();
        let chart = phichain_chart::serialization::PhichainChart::from_json_str(
            &std::fs::read_to_string(temp.join("chart.json")).unwrap(),
        )
        .unwrap();
        assert_eq!(chart.lines[0].notes.len(), 1);
        assert!(w.resource::<EditorHistory>().0.is_saved());
        std::fs::remove_dir_all(temp).unwrap();
    }
    #[test]
    fn bridge_authentication_and_endpoint_cleanup() {
        let path = std::env::temp_dir().join(format!(
            "phichain-mcp-endpoint-{}.json",
            uuid::Uuid::new_v4()
        ));
        let bridge = start_bridge(path.clone()).unwrap();
        let descriptor: Value = serde_json::from_slice(&std::fs::read(&path).unwrap()).unwrap();
        #[cfg(unix)]
        {
            use std::os::unix::fs::PermissionsExt;
            assert_eq!(
                std::fs::metadata(&path).unwrap().permissions().mode() & 0o777,
                0o600
            );
        }
        let mut connection =
            TcpStream::connect(("127.0.0.1", descriptor["port"].as_u64().unwrap() as u16)).unwrap();
        connection
            .set_read_timeout(Some(Duration::from_secs(2)))
            .unwrap();
        writeln!(
            connection,
            "{}",
            json!({"token":"wrong","tool":"get_context","arguments":{}})
        )
        .unwrap();
        let mut response = String::new();
        BufReader::new(connection).read_line(&mut response).unwrap();
        assert!(response.contains("Invalid bridge token"));
        assert!(bridge.requests.lock().unwrap().try_recv().is_err());
        drop(bridge);
        assert!(!path.exists());
    }
    #[test]
    fn stdio_mcp_edits_live_bevy_world_end_to_end() {
        let (mut app, _) = editor();
        let path =
            std::env::temp_dir().join(format!("phichain-mcp-e2e-{}.json", uuid::Uuid::new_v4()));
        app.insert_resource(start_bridge(path.clone()).unwrap())
            .add_systems(Last, process_requests);
        let adapter =
            PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../tools/phichain-mcp/server.py");
        let script = r#"
import json, subprocess, sys
p = subprocess.Popen([sys.executable, sys.argv[1], '--endpoint', sys.argv[2]], stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
def rpc(method, params):
    p.stdin.write(json.dumps({'jsonrpc':'2.0','id':1,'method':method,'params':params})+'\n'); p.stdin.flush()
    response = json.loads(p.stdout.readline())
    assert 'error' not in response, response
    return response['result']
def tool(name, args):
    result = rpc('tools/call', {'name':name,'arguments':args})
    assert not result['isError'], result
    return result['structuredContent']
rpc('initialize', {'protocolVersion':'2025-11-25'})
assert {'get_context','read_section','inspect_motion','preview_passage','animate_selection','apply_edits','preview','history','save'} == {t['name'] for t in rpc('tools/list', {})['tools']}
ctx = tool('get_context', {})
result = tool('apply_edits', {'session':ctx['session'],'revision':ctx['revision'],'operations':[{'op':'create_note','line_id':ctx['lines'][0]['id'],'note':{'kind':'tap','above':True,'beat':[4,1,2],'x':120,'speed':1}}]})
note_id = result['changes'][0]['id']
section = tool('read_section', {'start_beat':4,'end_beat':5})
assert section['notes'][0]['id'] == note_id, section
ctx = tool('history', {'session':result['session'],'revision':result['revision'],'action':'undo','author':'agent'})
assert tool('read_section', {'start_beat':4,'end_beat':5})['notes'] == []
ctx = tool('history', {'session':ctx['session'],'revision':ctx['revision'],'action':'redo','author':'agent'})
assert tool('read_section', {'start_beat':4,'end_beat':5})['notes'][0]['id'] == note_id
p.stdin.close()
assert p.wait(timeout=2) == 0
# Exercise the new flavour over real stdio -> authenticated bridge -> Bevy.
from pathlib import Path
p = subprocess.Popen([sys.executable, str(Path(sys.argv[1]).with_name('agent_server.py')), '--endpoint', sys.argv[2]], stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
rpc('initialize', {'protocolVersion':'2025-11-25'})
assert 'chart_script' in {t['name'] for t in rpc('tools/list', {})['tools']}
ctx = tool('editor_context', {})
g = {k:ctx[k] for k in ('session','revision')}
args = {**g, 'dry_run':True, 'operations':[{'op':'set','path':'/notes/'+note_id+'/note/x','value':240}]}
assert tool('chart_patch',args)['undo_steps'] == 0
assert tool('chart_read',{**g,'path':'/notes/'+note_id+'/note/x'})['value'] == 120
args['dry_run'] = False
changed = tool('chart_patch',args)
g = {k:changed[k] for k in ('session','revision')}
changed = tool('chart_transform',{**g,'dry_run':False,'path':'/notes','ids':[note_id],'expressions':{'/note/x':'-x'}})
g = {k:changed[k] for k in ('session','revision')}
source = 'chart.lines["new:carrier"]=api.createLine("Independent",99); chart.notes[input.note_id].line_id="new:carrier"; api.report({moved:1});'
changed = tool('chart_script',{**g,'dry_run':False,'source':source,'input':{'note_id':note_id}})
carrier = changed['created_ids']['new:carrier']
g = {k:changed[k] for k in ('session','revision')}
row = tool('chart_read',{**g,'path':'/notes/'+note_id})['value']
assert row['line_id'] == carrier and row['note']['x'] == -240, row
ctx = tool('history',{**g,'action':'undo','author':'agent'})
g = {k:ctx[k] for k in ('session','revision')}
assert tool('chart_read',{**g,'path':'/notes/'+note_id})['value']['line_id'] != carrier
ctx = tool('history',{**g,'action':'redo','author':'agent'})
g = {k:ctx[k] for k in ('session','revision')}
assert tool('chart_read',{**g,'path':'/notes/'+note_id})['value']['line_id'] == carrier
# Large generation exercises a candidate exceeding the public 1 MiB call size.
template = {'line_id':carrier,'note':{'kind':'tap','above':True,'beat':[0,0,1],'x':0,'speed':1}}
generated = tool('chart_generate',{**g,'dry_run':False,'path':'/notes','count':10000,'template':template,'expressions':{'/note/beat':'100+i/4'}})
assert len(generated['created_ids']) == 10000
ctx = tool('editor_context',{})
assert ctx['note_count'] == 10001, ctx['note_count']
g = {k:generated[k] for k in ('session','revision')}
ctx = tool('history',{**g,'action':'undo','author':'agent'})
assert tool('editor_context',{})['note_count'] == 1
p.stdin.close()
assert p.wait(timeout=2) == 0
"#;
        let mut child = std::process::Command::new("python3")
            .arg("-c")
            .arg(script)
            .arg(adapter)
            .arg(&path)
            .stdout(std::process::Stdio::piped())
            .stderr(std::process::Stdio::piped())
            .spawn()
            .unwrap();
        let deadline = Instant::now() + Duration::from_secs(40);
        while child.try_wait().unwrap().is_none() {
            if Instant::now() > deadline {
                child.kill().unwrap();
                panic!("MCP integration timed out")
            }
            app.update();
            std::thread::sleep(Duration::from_millis(10));
        }
        let output = child.wait_with_output().unwrap();
        assert!(
            output.status.success(),
            "{}",
            String::from_utf8_lossy(&output.stderr)
        );
        assert_eq!(
            app.world_mut().query::<&Note>().iter(app.world()).count(),
            1
        );
        drop(app);
        assert!(!path.exists());
    }
    #[test]
    fn human_interactions_block_writes_and_agent_edits_reset_inspector_baselines() {
        let (mut app, line) = editor();
        let w = app.world_mut();
        let ctx = bevy_egui::EguiContext::default();
        let cached: Note = serde_json::from_value(note(1)).unwrap();
        ctx.get()
            .data_mut(|data| data.insert_temp(egui::Id::new("note"), cached));
        let context_entity = w.spawn(ctx).id();
        let mut mouse = ButtonInput::<MouseButton>::default();
        mouse.press(MouseButton::Left);
        w.insert_resource(mouse);
        let args = edits(
            w,
            json!([{"op":"create_note","line_id":id(line),"note":note(4)}]),
        );
        assert!(call(w, "apply_edits", args.clone()).is_err());
        w.resource_mut::<ButtonInput<MouseButton>>()
            .release(MouseButton::Left);
        call(w, "apply_edits", args).unwrap();
        assert!(w
            .get::<bevy_egui::EguiContext>(context_entity)
            .unwrap()
            .get()
            .data(|data| data.get_temp::<Note>(egui::Id::new("note")))
            .is_none());
    }
    #[test]
    fn no_op_human_history_entry_invalidates_agent_revision() {
        let (mut app, line) = editor();
        let w = app.world_mut();
        let args = edits(
            w,
            json!([{"op":"create_note","line_id":id(line),"note":note(4)}]),
        );
        let offset = w.resource::<Offset>().0;
        w.resource_scope(|w, mut h: Mut<EditorHistory>| {
            h.edit(
                w,
                EditorCommand::EditOffset(EditOffset::new(offset, offset)),
            )
        });
        assert!(call(w, "apply_edits", args).is_err());
    }
    #[test]
    fn preview_validates_before_queuing_seek_and_checks_project_session() {
        let (mut app, _) = editor();
        let w = app.world_mut();
        w.insert_resource(phichain_game::audio::InstanceHandle(Handle::default()));
        w.init_resource::<Messages<SeekTo>>();
        let data = snapshot(w).unwrap();
        assert!(call(
            w,
            "preview",
            json!({"session":data["session"],"action":"invalid","time_seconds":3.0})
        )
        .is_err());
        assert!(call(
            w,
            "preview",
            json!({"session":"old-project","action":"seek","time_seconds":3.0})
        )
        .is_err());
        assert!(w.resource::<Messages<SeekTo>>().is_empty());
        assert!(call(
            w,
            "preview",
            json!({"session":data["session"],"action":"seek"})
        )
        .is_err());
        call(
            w,
            "preview",
            json!({"session":data["session"],"action":"seek","time_seconds":3.0}),
        )
        .unwrap();
        assert_eq!(w.resource::<Messages<SeekTo>>().len(), 1);
    }
    #[test]
    fn lifecycle_status_works_without_project_and_unsaved_close_is_blocked() {
        let mut empty = App::new();
        let status = call(empty.world_mut(), "editor_status", json!({})).unwrap();
        assert_eq!(status["connected"], true);
        assert!(status["project"].is_null());
        let (mut app, line) = editor();
        app.add_message::<crate::project::UnloadProject>();
        let w = app.world_mut();
        let args = edits(
            w,
            json!([{"op":"create_note","line_id":id(line),"note":note(1)}]),
        );
        call(w, "apply_edits", args).unwrap();
        let data = snapshot(w).unwrap();
        let guard = json!({"session":data["session"],"revision":data["revision"]});
        assert!(call(w, "close_project", guard.clone())
            .unwrap_err()
            .to_string()
            .contains("Save"));
        let snap = call(w, "project_snapshot", guard.clone()).unwrap();
        assert_eq!(
            snap["chart"]["lines"][0]["notes"].as_array().unwrap().len(),
            1
        );
        assert!(!w.resource::<EditorHistory>().0.is_saved());
        w.resource_mut::<EditorHistory>().0.set_saved();
        call(w, "close_project", guard).unwrap();
        assert_eq!(
            w.resource::<Messages<crate::project::UnloadProject>>()
                .len(),
            1
        );
    }
    #[test]
    fn line_creation_reparent_reorder_and_subtree_undo_preserve_ids() {
        let (mut app, root) = editor();
        let w = app.world_mut();
        w.insert_resource(SelectedLine(root));
        let args = edits(w, json!([{"op":"create_line","name":"second"}]));
        let result = call(w, "apply_edits", args).unwrap();
        let second = entity(&result["changes"][0], "id").unwrap();
        let args = edits(
            w,
            json!([{"op":"create_line","name":"child","parent_id":id(second)}]),
        );
        let result = call(w, "apply_edits", args).unwrap();
        let child = entity(&result["changes"][0], "id").unwrap();
        let args = edits(
            w,
            json!([{"op":"create_note","line_id":id(child),"note":note(1)}]),
        );
        let result = call(w, "apply_edits", args).unwrap();
        let n = entity(&result["changes"][0], "id").unwrap();
        let args = edits(w, json!([{"op":"delete_line","id":id(second)}]));
        assert!(call(w, "apply_edits", args).is_err());
        let before = snapshot(w).unwrap();
        let args = edits(
            w,
            json!([{"op":"update_line","id":id(second),"name":"cycle","parent_id":id(child)}]),
        );
        assert!(call(w, "apply_edits", args).is_err());
        assert_eq!(before["revision"], snapshot(w).unwrap()["revision"]);
        w.resource_mut::<SelectedLine>().0 = child;
        let args = edits(
            w,
            json!([{"op":"delete_line","id":id(second),"cascade":true}]),
        );
        call(w, "apply_edits", args).unwrap();
        assert!(w.get::<Line>(second).is_none());
        assert!(w.get::<Note>(n).is_none());
        assert_eq!(w.resource::<SelectedLine>().0, root);
        w.resource_scope(|w, mut h: Mut<EditorHistory>| h.undo(w));
        assert_eq!(w.get::<ChildOf>(child).unwrap().parent(), second);
        assert_eq!(w.get::<Note>(n).unwrap().beat, phichain_chart::beat!(1));
        assert_eq!(w.resource::<SelectedLine>().0, child);
        w.resource_scope(|w, mut h: Mut<EditorHistory>| h.redo(w));
        assert!(w.get::<Note>(n).is_none());
        w.resource_scope(|w, mut h: Mut<EditorHistory>| h.undo(w));
        let args = edits(
            w,
            json!([{"op":"reorder_lines","line_ids":[id(second),id(root)]}]),
        );
        call(w, "apply_edits", args).unwrap();
        assert_eq!(w.get::<LineOrder>(second).unwrap().0, 0);
        let args = edits(
            w,
            json!([{"op":"delete_line","id":id(root),"cascade":true},{"op":"delete_line","id":id(second),"cascade":true}]),
        );
        assert!(call(w, "apply_edits", args).is_err());
    }
    #[test]
    fn curve_operations_are_guarded_undoable_and_validation_includes_generated_notes() {
        let (mut app, line) = editor();
        let w = app.world_mut();
        let args = edits(
            w,
            json!([{"op":"create_note","line_id":id(line),"note":note(0)},{"op":"create_note","line_id":id(line),"note":note(2)}]),
        );
        let result = call(w, "apply_edits", args).unwrap();
        let a = result["changes"][0]["id"].clone();
        let b = result["changes"][1]["id"].clone();
        let options = json!({"kind":"drag","density":2,"curve":{"type":"linear"}});
        let args = edits(
            w,
            json!([{"op":"create_curve_track","line_id":id(line),"from_id":a,"to_id":b,"options":options}]),
        );
        let result = call(w, "apply_edits", args).unwrap();
        let track = entity(&result["changes"][0], "id").unwrap();
        let validation = call(w, "validate_chart", json!({"end_beat":3})).unwrap();
        assert_eq!(validation["generated_notes_checked"], 3);
        w.resource_scope(|w, mut h: Mut<EditorHistory>| h.undo(w));
        assert!(w.get::<CurveNoteTrack>(track).is_none());
        w.resource_scope(|w, mut h: Mut<EditorHistory>| h.redo(w));
        assert!(w.get::<CurveNoteTrack>(track).is_some());
        let before = snapshot(w).unwrap();
        let args = edits(
            w,
            json!([{"op":"update_curve_track","id":id(track),"from_id":b,"to_id":a,"options":options}]),
        );
        assert!(call(w, "apply_edits", args).is_err());
        assert_eq!(before["revision"], snapshot(w).unwrap()["revision"]);
        let args = edits(w, json!([{"op":"delete_curve_track","id":id(track)}]));
        call(w, "apply_edits", args).unwrap();
        w.resource_scope(|w, mut h: Mut<EditorHistory>| h.undo(w));
        assert!(w.get::<CurveNoteTrack>(track).is_some());
    }
    #[test]
    fn quality_checks_hold_boundaries_contacts_and_ancestor_positions() {
        let (mut app, line) = editor();
        let w = app.world_mut();
        let args = edits(
            w,
            json!([{"op":"create_line","name":"child","parent_id":id(line)}]),
        );
        let result = call(w, "apply_edits", args).unwrap();
        let child = entity(&result["changes"][0], "id").unwrap();
        let mut hold = note(1);
        hold["kind"] = json!("hold");
        hold["hold_beat"] = json!([4, 0, 1]);
        let args = edits(
            w,
            json!([
                {"op":"create_note","line_id":id(child),"note":hold},
                {"op":"create_note","line_id":id(child),"note":note(2)},
                {"op":"create_note","line_id":id(line),"note":note(2)},
                {"op":"create_event","line_id":id(line),"event":{"kind":"x","start_beat":[0,0,1],"end_beat":[10,0,1],"value":{"type":"constant","value":2000}}}
            ]),
        );
        call(w, "apply_edits", args).unwrap();
        let validation = call(w, "validate_chart", json!({"end_beat":3})).unwrap();
        assert_eq!(validation["maximum_contacts"], 3);
        let codes: HashSet<_> = validation["findings"]
            .as_array()
            .unwrap()
            .iter()
            .map(|v| v["code"].as_str().unwrap())
            .collect();
        assert!(codes.contains("hold_crosses_boundary"));
        assert!(codes.contains("offscreen_hit"));
        assert!(codes.contains("contact_demand"));
    }
    #[test]
    fn selection_and_view_do_not_change_chart_revision_and_invalid_view_is_atomic() {
        let (mut app, line) = editor();
        app.add_message::<SeekTo>()
            .init_resource::<crate::timeline::settings::TimelineSettings>()
            .init_resource::<crate::layout::ui_state::UiState>();
        let w = app.world_mut();
        let args = edits(
            w,
            json!([{"op":"create_note","line_id":id(line),"note":note(1)}]),
        );
        let result = call(w, "apply_edits", args).unwrap();
        let n = result["changes"][0]["id"].clone();
        let before = snapshot(w).unwrap();
        call(
            w,
            "select_objects",
            json!({"session":before["session"],"ids":[n],"line_id":id(line)}),
        )
        .unwrap();
        assert_eq!(before["revision"], snapshot(w).unwrap()["revision"]);
        assert!(call(
            w,
            "set_editor_view",
            json!({"session":before["session"],"zoom":3,"layout":"invalid"})
        )
        .is_err());
        assert_eq!(
            w.resource::<crate::timeline::settings::TimelineSettings>()
                .zoom,
            2.0
        );
        call(
            w,
            "set_editor_view",
            json!({"session":before["session"],"zoom":3,"focus_beat":4,"layout":"preview"}),
        )
        .unwrap();
        assert_eq!(w.resource::<Messages<SeekTo>>().len(), 1);
        assert_eq!(before["revision"], snapshot(w).unwrap()["revision"]);
    }
    #[test]
    fn bpm_replacement_is_atomic_undoable_and_recomputes_timing() {
        let (mut app, _) = editor();
        let w = app.world_mut();
        let before = snapshot(w).unwrap();
        let args = json!({"session":before["session"],"revision":before["revision"],"bpm_list":[{"beat":[0,0,1],"bpm":150},{"beat":[8,0,1],"bpm":180}]});
        let result = call(w, "set_bpm_list", args.clone()).unwrap();
        assert_eq!(result["undo_steps"], 1);
        assert!((w.resource::<BpmList>().time_at(phichain_chart::beat!(11)) - 4.2).abs() < 0.001);
        assert!(call(w, "set_bpm_list", args).is_err());
        w.resource_scope(|w, mut h: Mut<EditorHistory>| h.undo(w));
        assert_eq!(w.resource::<BpmList>().0[0].bpm, 120.0);
        w.resource_scope(|w, mut h: Mut<EditorHistory>| h.redo(w));
        assert_eq!(w.resource::<BpmList>().0[1].bpm, 180.0);
        let before = snapshot(w).unwrap();
        for points in [
            json!([]),
            json!([{"beat":[1,0,1],"bpm":120}]),
            json!([{"beat":[0,0,1],"bpm":120},{"beat":[0,0,1],"bpm":150}]),
            json!([{"beat":[0,0,1],"bpm":0}]),
            json!([{"beat":[0,0,0],"bpm":120}]),
        ] {
            assert!(call(
                w,
                "set_bpm_list",
                json!({"session":before["session"],"revision":before["revision"],"bpm_list":points})
            )
            .is_err());
            assert_eq!(before["revision"], snapshot(w).unwrap()["revision"]);
        }
    }
}
