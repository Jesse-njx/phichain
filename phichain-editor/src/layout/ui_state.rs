use crate::identifier::{Identifier, IntoIdentifier};
use crate::tab::{EditorTab, TabRegistry};
use bevy::prelude::{Resource, World};
use egui_dock::{DockArea, DockState, NodeIndex, Style};
use serde::{Deserialize, Serialize};

struct TabViewer<'a> {
    world: &'a mut World,
    registry: &'a mut TabRegistry,
}

#[derive(Resource, Clone, Serialize, Deserialize)]
pub struct UiState {
    pub state: DockState<Identifier>,
    #[serde(default)]
    pub density_panel_initialized: bool,
}

impl Default for UiState {
    fn default() -> Self {
        let mut state = DockState::new(vec![EditorTab::Game.into_identifier()]);
        let tree = state.main_surface_mut();
        let [game, timeline] = tree.split_left(
            NodeIndex::root(),
            2.0 / 3.0,
            vec![
                EditorTab::Timeline.into_identifier(),
                EditorTab::Settings.into_identifier(),
            ],
        );

        let [_line_list, _timeline] = tree.split_left(
            timeline,
            1.0 / 4.0,
            vec![EditorTab::LineList.into_identifier()],
        );

        let [_, inspector] = tree.split_below(
            game,
            2.0 / 5.0,
            vec![EditorTab::Inspector.into_identifier()],
        );
        let [inspector, _density] =
            tree.split_below(inspector, 0.74, vec![EditorTab::Density.into_identifier()]);
        tree.split_right(
            inspector,
            1.0 / 2.0,
            vec![EditorTab::TimelineSetting.into_identifier()],
        );

        Self {
            state,
            density_panel_initialized: true,
        }
    }
}

impl UiState {
    /// Upgrade saved layouts once, preserving the existing editor panes.
    pub fn initialize_density_panel(&mut self) {
        if self.density_panel_initialized {
            return;
        }
        self.density_panel_initialized = true;
        if self
            .state
            .find_tab(&EditorTab::Density.into_identifier())
            .is_some()
        {
            return;
        }
        let tree = self.state.main_surface_mut();
        if let Some((inspector, _)) = tree.find_tab(&EditorTab::Inspector.into_identifier()) {
            let settings = tree.find_tab(&EditorTab::TimelineSetting.into_identifier());
            let target = inspector
                .parent()
                .filter(|parent| settings.is_some_and(|(node, _)| node.parent() == Some(*parent)))
                .unwrap_or(inspector);
            tree.split_below(target, 0.74, vec![EditorTab::Density.into_identifier()]);
        }
    }

    pub fn ui(&mut self, world: &mut World, registry: &mut TabRegistry, ctx: &mut egui::Context) {
        let mut tab_viewer = TabViewer { world, registry };

        DockArea::new(&mut self.state)
            .style(Style::from_egui(ctx.style().as_ref()))
            .show(ctx, &mut tab_viewer);
    }
}

impl egui_dock::TabViewer for TabViewer<'_> {
    type Tab = Identifier;

    fn title(&mut self, tab: &mut Self::Tab) -> egui::WidgetText {
        t!(format!("tab.{tab}.title").as_str()).into()
    }
    fn ui(&mut self, ui: &mut egui::Ui, tab: &mut Self::Tab) {
        self.registry.tab_ui(ui, self.world, tab);
    }

    fn closeable(&mut self, tab: &mut Self::Tab) -> bool {
        self.allowed_in_windows(tab)
    }

    fn allowed_in_windows(&self, tab: &mut Self::Tab) -> bool {
        tab.to_string() != EditorTab::Game.into_identifier().to_string()
    }

    fn clear_background(&self, tab: &Self::Tab) -> bool {
        *tab != EditorTab::Game.into_identifier() && *tab != EditorTab::Timeline.into_identifier()
    }

    fn scroll_bars(&self, tab: &Self::Tab) -> [bool; 2] {
        if *tab == EditorTab::Game.into_identifier()
            || *tab == EditorTab::Timeline.into_identifier()
        {
            [false, false]
        } else {
            [true, true]
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn density_panel_upgrades_old_layout_once_and_respects_later_closure() {
        let mut old = UiState::default();
        old.density_panel_initialized = false;
        let tab = EditorTab::Density.into_identifier();
        old.state.remove_tab(old.state.find_tab(&tab).unwrap());
        old.initialize_density_panel();
        let position = old.state.find_tab(&tab).unwrap();
        // The density pane spans both lower-right settings panes.
        let inspector = old
            .state
            .find_tab(&EditorTab::Inspector.into_identifier())
            .unwrap();
        let settings = old
            .state
            .find_tab(&EditorTab::TimelineSetting.into_identifier())
            .unwrap();
        assert_eq!(inspector.1.parent(), settings.1.parent());
        assert_eq!(inspector.1.parent().unwrap().parent(), position.1.parent());
        old.state.remove_tab(position);
        old.initialize_density_panel();
        assert!(old.state.find_tab(&tab).is_none());
        assert!(
            serde_json::to_value(&old).unwrap()["density_panel_initialized"]
                .as_bool()
                .unwrap()
        );
    }
}
