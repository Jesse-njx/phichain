use crate::editing::command::EditorCommand;
use bevy::prelude::*;
use undo::History;

#[derive(Resource, Default)]
pub struct EditorHistory(pub History<EditorCommand>);

impl EditorHistory {
    /// Author of the next entry affected by a single undo or redo.
    pub fn next_author(&self, redo: bool) -> Option<&'static str> {
        let head = self.0.head().index;
        let index = if redo { head } else { head.checked_sub(1)? };
        self.0.get_entry(index).map(|entry| match entry.as_ref() {
            EditorCommand::AgentSequence(_) => "agent",
            _ => "human",
        })
    }

    pub fn edit(&mut self, world: &mut World, edit: EditorCommand) {
        info!("Executing command {:?}", edit);
        self.0.edit(world, edit);
    }

    pub fn undo(&mut self, world: &mut World) {
        info!("Undo");
        self.0.undo(world);
    }

    pub fn redo(&mut self, world: &mut World) {
        info!("Redo");
        self.0.redo(world);
    }
}
