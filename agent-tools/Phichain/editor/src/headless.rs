//! Windowless host for the same native ECS chart, commands and history as the GUI.
use crate::{
    cli::Args,
    editing::history::EditorHistory,
    project::Project,
    selection::SelectedLine,
    timing::{ChartTime, Paused, Timing},
};
use anyhow::Result;
use bevy::{
    app::ScheduleRunnerPlugin,
    prelude::*,
    tasks::{block_on, futures_lite::future, IoTaskPool, Task},
};
use phichain_chart::{bpm_list::BpmList, line::Line, offset::Offset, serialization::PhichainChart};
use phichain_game::audio::{open_and_decode_audio, AudioDuration};
use std::{path::PathBuf, time::Duration};

#[derive(Resource)]
pub(crate) struct Headless;

#[derive(Resource)]
struct Opening(Task<Result<(Project, PhichainChart, Duration)>>);

pub(crate) fn run(args: Args) -> Result<()> {
    let path = args.mcp_endpoint.clone().expect("clap requires endpoint");
    let project = args.project.clone();
    let mut app = App::new();
    app.add_plugins(
        MinimalPlugins.set(ScheduleRunnerPlugin::run_loop(Duration::from_secs_f64(
            1.0 / 60.0,
        ))),
    )
    .insert_resource(args);
    configure(&mut app);
    // Propagate startup failures instead of leaving an unreachable process alive.
    crate::mcp::start_headless_bridge(&mut app, path)?;
    if let Some(path) = project {
        open(app.world_mut(), PathBuf::from(path))?;
    }
    app.run();
    Ok(())
}

pub(crate) fn configure(app: &mut App) {
    app.insert_resource(Headless)
        .init_resource::<EditorHistory>()
        .insert_resource(Timing::new())
        .insert_resource(ChartTime(0.0))
        .insert_resource(Paused(true))
        .add_plugins((
            phichain_game::line::LinePlugin,
            phichain_game::curve_note_track::CurveNoteTrackPlugin,
        ))
        .add_systems(Update, (poll_open, tick).chain());
}

pub(crate) fn open(world: &mut World, path: PathBuf) -> Result<()> {
    crate::mcp::begin_lifecycle(world, "open")?;
    world.insert_resource(Opening(IoTaskPool::get().spawn(async move {
        let project = Project::open(path)?;
        let chart =
            PhichainChart::from_json_str(&std::fs::read_to_string(project.path.chart_path())?)?;
        let sound = open_and_decode_audio(project.path.music_path().unwrap())?;
        Ok((project, chart, sound.duration()))
    })));
    Ok(())
}

fn poll_open(world: &mut World) {
    let Some(mut opening) = world.get_resource_mut::<Opening>() else {
        return;
    };
    let Some(result) = block_on(future::poll_once(&mut opening.0)) else {
        return;
    };
    world.remove_resource::<Opening>();
    match result {
        Ok((project, mut chart, duration)) => {
            chart.bpm_list.compute();
            phichain_game::loader::load(chart, &mut world.commands());
            world.flush();
            if let Some(line) = world
                .query_filtered::<Entity, With<Line>>()
                .iter(world)
                .next()
            {
                world.insert_resource(SelectedLine(line));
            }
            world.insert_resource(project);
            world.insert_resource(AudioDuration(duration));
            world.resource_mut::<EditorHistory>().0.set_saved();
            crate::mcp::finish_lifecycle(world, None);
        }
        Err(error) => crate::mcp::finish_lifecycle(world, Some(format!("{error:#}"))),
    }
}

pub(crate) fn close(world: &mut World) {
    // Preserve runtime observers; remove chart objects and empty entities retained by undo.
    world.flush();
    let entities: Vec<_> = world
        .query::<Entity>()
        .iter(world)
        .filter(|&entity| {
            world.get::<Line>(entity).is_some()
                || world.get::<phichain_chart::note::Note>(entity).is_some()
                || world
                    .get::<phichain_chart::event::LineEvent>(entity)
                    .is_some()
                || world
                    .get::<phichain_game::curve_note_track::CurveNoteTrack>(entity)
                    .is_some()
                || world
                    .inspect_entity(entity)
                    .is_ok_and(|mut components| components.next().is_none())
        })
        .collect();
    for entity in entities {
        if let Ok(entity) = world.get_entity_mut(entity) {
            entity.despawn();
        }
    }
    world.flush();
    world.remove_resource::<Project>();
    world.remove_resource::<BpmList>();
    world.remove_resource::<Offset>();
    world.remove_resource::<SelectedLine>();
    world.remove_resource::<AudioDuration>();
    world.insert_resource(EditorHistory::default());
    world.insert_resource(Timing::new());
    world.insert_resource(ChartTime(0.0));
    world.insert_resource(Paused(true));
}

pub(crate) fn preview(world: &mut World, action: &str, seconds: Option<f32>) {
    let mut timing = world.resource_mut::<Timing>();
    if let Some(seconds) = seconds {
        timing.seek_to(seconds);
    }
    match action {
        "play" if timing.paused() => timing.resume(),
        "pause" if !timing.paused() => timing.pause(),
        _ => {}
    }
    world.resource_mut::<Paused>().0 = world.resource::<Timing>().paused();
    sync_chart_time(world);
}

fn sync_chart_time(world: &mut World) {
    let offset = world.get_resource::<Offset>().map_or(0.0, |o| o.0 / 1000.0);
    world.resource_mut::<ChartTime>().0 = world.resource::<Timing>().now() - offset;
}

fn tick(world: &mut World) {
    if !world.contains_resource::<Project>() {
        return;
    }
    if world.resource_ref::<BpmList>().is_changed() {
        world.resource_mut::<BpmList>().compute();
    }
    let delta = world.resource::<Time<Real>>().delta_secs();
    let duration = world.resource::<AudioDuration>().0.as_secs_f32();
    let mut timing = world.resource_mut::<Timing>();
    if !timing.paused() {
        let next = (timing.now() + delta).min(duration);
        timing.seek_to(next);
        if next >= duration {
            timing.pause();
        }
    }
    world.resource_mut::<Paused>().0 = world.resource::<Timing>().paused();
    sync_chart_time(world);
}
