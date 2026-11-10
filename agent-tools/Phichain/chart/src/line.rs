use serde::{Deserialize, Serialize};

/// Authoring intent only; gameplay still uses ordinary line events and playable notes.
#[derive(Debug, Clone, Copy, Default, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum LineRole {
    #[default]
    Simple,
    Complex,
    Decorative,
}

impl LineRole {
    pub const ALL: [Self; 3] = [Self::Simple, Self::Complex, Self::Decorative];
    pub fn label(self) -> &'static str {
        match self {
            Self::Simple => "Simple",
            Self::Complex => "Complex",
            Self::Decorative => "Decorative",
        }
    }
    pub fn description(self) -> &'static str {
        match self {
            Self::Simple => "Shared movement and scrolling for playable notes.",
            Self::Complex => "Independent note choreography. Intended for one active note at a time, including its early appearance and hold tail.",
            Self::Decorative => "Visual line effects, intended to carry no playable notes.",
        }
    }
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[cfg_attr(feature = "bevy", derive(bevy::prelude::Component))]
#[cfg_attr(
    feature = "bevy",
    require(
        bevy::prelude::Sprite,
        bevy::prelude::Pickable,
        LinePosition,
        LineRotation,
        LineOpacity,
        LineSpeed,
    )
)]
pub struct Line {
    pub name: String,
    #[serde(default)]
    pub role: LineRole,
}

impl Default for Line {
    fn default() -> Self {
        Self {
            name: "Unnamed Line".to_owned(),
            role: LineRole::Simple,
        }
    }
}

// TODO: types below should be moved to phichain-game

#[cfg(feature = "bevy")]
#[derive(bevy::prelude::Component, Debug, Default)]
pub struct LinePosition(pub bevy::prelude::Vec2);

#[cfg(feature = "bevy")]
#[derive(bevy::prelude::Component, Debug, Default)]
pub struct LineRotation(pub f32);

#[cfg(feature = "bevy")]
#[derive(bevy::prelude::Component, Debug, Default)]
pub struct LineOpacity(pub f32);

/// This will not affect line entity, it is only used to show realtime speed of lines in [phichain::tab::line_list]
#[cfg(feature = "bevy")]
#[derive(bevy::prelude::Component, Debug, Default)]
pub struct LineSpeed(pub f32);

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn old_lines_default_to_simple_and_roles_round_trip() {
        let old: Line = serde_json::from_str(r#"{"name":"Old line"}"#).unwrap();
        assert_eq!(old.role, LineRole::Simple);
        for role in LineRole::ALL {
            let line = Line {
                name: "Carrier".into(),
                role,
            };
            let restored: Line =
                serde_json::from_str(&serde_json::to_string(&line).unwrap()).unwrap();
            assert_eq!(restored, line);
        }
    }
}
