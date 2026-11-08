//! GUI-free project creation. File copies/decoding run outside the bridge frame.
use super::*;
use crate::project::ProjectMeta;
use bevy::tasks::{block_on, futures_lite::future, IoTaskPool, Task};

#[derive(Resource)]
struct Creating(Task<Result<PathBuf>>);

pub(super) fn create(world: &mut World, args: &Value) -> Result<Value> {
    let path = absolute_path(args, "path")?;
    let music = absolute_path(args, "music_path")?;
    let illustration = args
        .get("illustration_path")
        .map(|_| absolute_path(args, "illustration_path"))
        .transpose()?;
    let meta: ProjectMeta = args
        .get("meta")
        .map(|value| serde_json::from_value(value.clone()))
        .transpose()?
        .unwrap_or_default();
    if path.symlink_metadata().is_ok() {
        bail!("Project destination must not already exist")
    }
    if !path.parent().is_some_and(|p| p.is_dir()) {
        bail!("Project parent directory must exist")
    }
    let music_ext = extension(&music, &["mp3", "wav", "ogg", "flac"])?;
    let illustration_ext = illustration
        .as_ref()
        .map(|p| extension(p, &["png", "jpg", "jpeg"]))
        .transpose()?;
    begin_lifecycle(world, "create")?;
    let destination = path.clone();
    world.insert_resource(Creating(IoTaskPool::get().spawn(async move {
        create_files(
            destination,
            music,
            music_ext,
            illustration.zip(illustration_ext),
            meta,
        )
    })));
    Ok(json!({"status":"requested","path":path,"next":"editor_status"}))
}

fn absolute_path(args: &Value, key: &str) -> Result<PathBuf> {
    let path = PathBuf::from(
        args[key]
            .as_str()
            .context(format!("{key} must be a path string"))?,
    );
    if !path.is_absolute() {
        bail!("{key} must be absolute")
    }
    Ok(path)
}

fn extension(path: &std::path::Path, allowed: &[&str]) -> Result<String> {
    let ext = path
        .extension()
        .and_then(|s| s.to_str())
        .unwrap_or_default()
        .to_ascii_lowercase();
    if !path.is_file() || !allowed.contains(&ext.as_str()) {
        bail!("Unsupported or missing input file: {}", path.display())
    }
    Ok(ext)
}

fn create_files(
    path: PathBuf,
    music: PathBuf,
    music_ext: String,
    illustration: Option<(PathBuf, String)>,
    meta: ProjectMeta,
) -> Result<PathBuf> {
    // Validate source data before reserving a new directory. No output/audio device.
    let sound = phichain_game::audio::open_and_decode_audio(music.clone())?;
    if sound.duration().is_zero() {
        bail!("Music must contain audio samples")
    }
    drop(sound);
    if let Some((source, _)) = &illustration {
        image::open(source)?;
    }
    std::fs::create_dir(&path).context("Project destination must be new")?;
    let mut created = Vec::new();
    let result = (|| -> Result<()> {
        let mut write = |name: String, bytes: &[u8]| -> Result<()> {
            let file = path.join(name);
            let mut out = std::fs::OpenOptions::new()
                .write(true)
                .create_new(true)
                .open(&file)?;
            created.push(file);
            out.write_all(bytes)?;
            Ok(())
        };
        write(format!("music.{music_ext}"), &std::fs::read(music)?)?;
        if let Some((source, ext)) = illustration {
            write(format!("illustration.{ext}"), &std::fs::read(source)?)?;
        }
        write("meta.json".into(), &serde_json::to_vec_pretty(&meta)?)?;
        write(
            "chart.json".into(),
            &serde_json::to_vec_pretty(&crate::project::new_project_chart())?,
        )?;
        Ok(())
    })();
    if let Err(error) = result {
        for file in created {
            let _ = std::fs::remove_file(file);
        }
        // Do not delete unrelated files if someone wrote into the directory concurrently.
        let _ = std::fs::remove_dir(&path);
        return Err(error);
    }
    Ok(path)
}

pub(super) fn poll(world: &mut World) {
    if world.resource::<Lifecycle>().pending.as_deref() == Some("close")
        && !world.contains_resource::<Project>()
    {
        finish_lifecycle(world, None);
    }
    let Some(mut task) = world.get_resource_mut::<Creating>() else {
        return;
    };
    let Some(result) = block_on(future::poll_once(&mut task.0)) else {
        return;
    };
    world.remove_resource::<Creating>();
    match result {
        Ok(path) => {
            finish_lifecycle(world, None);
            world.resource_mut::<Lifecycle>().created_path = Some(path);
        }
        Err(error) => finish_lifecycle(world, Some(format!("{error:#}"))),
    }
}
