use bevy::prelude::*;
use clap::Parser;

/// Phichain - Phigros charting toolchain
#[derive(Parser, Resource, Debug)]
#[command(version, about, long_about = None)]
pub struct Args {
    /// Load project from this path when launch
    #[arg(short, long)]
    pub project: Option<String>,

    /// Enable the local MCP bridge and write its credentials to a new endpoint file
    #[arg(long)]
    pub mcp_endpoint: Option<std::path::PathBuf>,

    /// Run the native editing engine without a window, GPU, or audio output device
    #[arg(long, requires = "mcp_endpoint")]
    pub headless: bool,
}

pub struct CliPlugin;

impl Plugin for CliPlugin {
    fn build(&self, app: &mut App) {
        app.insert_resource(Args::parse());
    }
}
