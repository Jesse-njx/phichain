use super::*;

fn runtime() -> App {
    let mut app = App::new();
    app.add_plugins(MinimalPlugins);
    crate::headless::configure(&mut app);
    app.init_resource::<Lifecycle>()
        .add_systems(Update, lifecycle::poll);
    app
}

fn call(app: &mut App, tool: &str, args: Value) -> Result<Value> {
    handle(app.world_mut(), &json!({"tool":tool,"arguments":args}))
}

fn settled(app: &mut App) -> Value {
    let deadline = Instant::now() + Duration::from_secs(5);
    loop {
        app.update();
        let status = call(app, "editor_status", json!({})).unwrap();
        if status["pending"].is_null() {
            return status;
        }
        assert!(
            Instant::now() < deadline,
            "lifecycle did not complete: {status}"
        );
        std::thread::sleep(Duration::from_millis(1));
    }
}

fn wav(path: &std::path::Path) {
    let mut out = hound::WavWriter::create(
        path,
        hound::WavSpec {
            channels: 1,
            sample_rate: 8000,
            bits_per_sample: 16,
            sample_format: hound::SampleFormat::Int,
        },
    )
    .unwrap();
    for _ in 0..16000 {
        out.write_sample(0i16).unwrap();
    }
    out.finalize().unwrap();
}

#[test]
fn headless_create_import_edit_history_save_reopen_without_devices() {
    let dir = tempfile::tempdir().unwrap();
    let music = dir.path().join("input.WAV");
    wav(&music);
    let original = std::fs::read(&music).unwrap();
    let path = dir.path().join("project");
    let mut app = runtime();
    let status = call(&mut app, "editor_status", json!({})).unwrap();
    assert_eq!(status["headless"], true);
    assert!(status["project"].is_null());
    call(
        &mut app,
        "create_project",
        json!({"path":path,"music_path":music}),
    )
    .unwrap();
    assert!(call(
        &mut app,
        "create_project",
        json!({"path":dir.path().join("other"),"music_path":music})
    )
    .is_err());
    assert!(call(&mut app, "open_project", json!({"path":path})).is_err());
    let status = settled(&mut app);
    assert!(status["last_error"].is_null(), "{status}");
    assert_eq!(status["created_path"], json!(path));
    assert!(status["project"].is_null());
    assert_eq!(std::fs::read(path.join("music.wav")).unwrap(), original);
    assert_eq!(std::fs::read(music).unwrap(), original);
    call(&mut app, "open_project", json!({"path":path})).unwrap();
    let status = settled(&mut app);
    assert!(status["last_error"].is_null(), "{status}");
    let data = &status["project"];
    assert_eq!(data["audio_duration_seconds"], 2.0);
    assert_eq!(data["saved"], true);
    let initial_session = data["session"].clone();
    call(&mut app, "apply_edits", json!({"session":data["session"],"revision":data["revision"],"operations":[
        {"op":"create_note","line_id":data["lines"][0]["id"],"note":{"kind":"tap","above":true,"beat":[1,0,1],"x":42,"speed":1}}
    ]})).unwrap();
    let data = call(&mut app, "get_context", json!({})).unwrap();
    assert_eq!(data["note_count"], 1);
    assert!(call(&mut app, "close_project", data.clone()).is_err());
    call(&mut app, "history", json!({"session":data["session"],"revision":data["revision"],"action":"undo","author":"agent"})).unwrap();
    let data = call(&mut app, "get_context", json!({})).unwrap();
    assert_eq!(data["note_count"], 0);
    call(&mut app, "history", json!({"session":data["session"],"revision":data["revision"],"action":"redo","author":"agent"})).unwrap();
    let data = call(&mut app, "get_context", json!({})).unwrap();
    call(
        &mut app,
        "preview",
        json!({"session":data["session"],"action":"seek","time_seconds":1.0}),
    )
    .unwrap();
    assert_eq!(
        call(&mut app, "get_context", json!({})).unwrap()["time_seconds"],
        1.0
    );
    call(
        &mut app,
        "preview",
        json!({"session":data["session"],"action":"play"}),
    )
    .unwrap();
    app.update();
    call(
        &mut app,
        "preview",
        json!({"session":data["session"],"action":"pause"}),
    )
    .unwrap();
    call(&mut app, "save", data).unwrap();
    let data = call(&mut app, "get_context", json!({})).unwrap();
    call(&mut app, "close_project", data).unwrap();
    assert_eq!(
        app.world_mut().query::<&Line>().iter(app.world()).count(),
        0
    );
    assert_eq!(
        app.world_mut().query::<&Note>().iter(app.world()).count(),
        0
    );
    call(&mut app, "open_project", json!({"path":path})).unwrap();
    let status = settled(&mut app);
    assert!(status["last_error"].is_null(), "{status}");
    assert_eq!(status["project"]["note_count"], 1);
    assert_ne!(status["project"]["session"], initial_session);
    assert!(!app
        .world()
        .contains_resource::<bevy::render::renderer::RenderDevice>());
    assert!(!app.world().contains_resource::<bevy_kira_audio::Audio>());
    assert_eq!(
        app.world_mut().query::<&Window>().iter(app.world()).count(),
        0
    );
}

#[test]
fn headless_invalid_import_and_open_recover_without_overwriting() {
    let dir = tempfile::tempdir().unwrap();
    let music = dir.path().join("bad.mp3");
    std::fs::write(&music, "invalid audio").unwrap();
    let path = dir.path().join("project");
    let mut app = runtime();
    call(
        &mut app,
        "create_project",
        json!({"path":path,"music_path":music}),
    )
    .unwrap();
    assert!(settled(&mut app)["last_error"].is_string());
    assert!(!path.exists());
    std::fs::create_dir(&path).unwrap();
    std::fs::write(path.join("keep"), "original").unwrap();
    assert!(call(
        &mut app,
        "create_project",
        json!({"path":path,"music_path":music})
    )
    .is_err());
    assert_eq!(
        std::fs::read_to_string(path.join("keep")).unwrap(),
        "original"
    );
    call(&mut app, "open_project", json!({"path":path})).unwrap();
    let status = settled(&mut app);
    assert!(status["last_error"].is_string());
    assert!(status["project"].is_null());
    assert!(call(
        &mut app,
        "create_project",
        json!({"path":"relative","music_path":music})
    )
    .is_err());
}

#[test]
fn headless_requires_explicit_endpoint() {
    use clap::Parser;
    assert!(crate::cli::Args::try_parse_from(["phichain", "--headless"]).is_err());
    assert!(
        crate::cli::Args::try_parse_from([
            "phichain",
            "--headless",
            "--mcp-endpoint",
            "endpoint.json"
        ])
        .unwrap()
        .headless
    );
}
