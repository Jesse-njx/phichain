use crate::editing::{
    command::{line::EditLine, EditorCommand},
    DoCommand,
};
use crate::selection::SelectedLine;
use bevy::prelude::*;
use egui::Ui;
use phichain_chart::{
    line::{Line, LineRole},
    note::Note,
};

pub fn line_inspector(
    In(mut ui): In<Ui>,
    mut line_query: Query<&mut Line>,
    notes: Query<&ChildOf, With<Note>>,
    selected_line: Res<SelectedLine>,
    mut commands: MessageWriter<DoCommand>,
) -> Result {
    let mut line = line_query.get_mut(selected_line.0)?;
    ui.label(t!("tab.inspector.line.title"));
    ui.separator();
    egui::Grid::new("inspector_grid")
        .num_columns(2)
        .spacing([20.0, 2.0])
        .striped(true)
        .show(&mut ui, |ui| {
            ui.label(t!("tab.inspector.line.name"));
            let buffer_id = egui::Id::new(("line-name-buffer", selected_line.0));
            let mut name = ui
                .data(|data| data.get_temp::<String>(buffer_id))
                .unwrap_or_else(|| line.name.clone());
            let response = ui.text_edit_singleline(&mut name);
            if response.has_focus() {
                ui.data_mut(|data| data.insert_temp(buffer_id, name.clone()));
            }
            if response.lost_focus() {
                ui.data_mut(|data| data.remove::<String>(buffer_id));
                if name != line.name {
                    let from = line.clone();
                    line.name = name;
                    commands.write(DoCommand(EditorCommand::EditLine(EditLine {
                        entity: selected_line.0,
                        from,
                        to: line.clone(),
                    })));
                }
            }
            ui.end_row();
            ui.label("Role");
            let from = line.clone();
            egui::ComboBox::from_id_salt(("line_role", selected_line.0))
                .selected_text(line.role.label())
                .show_ui(ui, |ui| {
                    for role in LineRole::ALL {
                        ui.selectable_value(&mut line.role, role, role.label())
                            .on_hover_text(role.description());
                    }
                });
            ui.end_row();
            if *line != from {
                commands.write(DoCommand(EditorCommand::EditLine(EditLine {
                    entity: selected_line.0,
                    from,
                    to: line.clone(),
                })));
            }
        });
    ui.label(line.role.description());
    ui.small(
        "Role labels describe authoring intent. They do not change playback or allocate carriers.",
    );
    if line.role == LineRole::Decorative && notes.iter().any(|p| p.parent() == selected_line.0) {
        ui.colored_label(egui::Color32::YELLOW, "This decorative line still contains playable notes. Move them to a Simple or Complex line, or change this role. They still count and must be played.");
    }
    ui.small("Early-visible notes are playable at their later hit times; animation does not make them fake notes.");
    Ok(())
}
