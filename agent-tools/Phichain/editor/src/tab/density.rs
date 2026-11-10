use crate::editing::pending::Pending;
use crate::timing::{ChartTime, SeekTo};
use bevy::prelude::*;
use egui::{Align2, Color32, FontId, Sense, Stroke, Ui};
use phichain_chart::{bpm_list::BpmList, note::Note, offset::Offset};
use phichain_game::audio::AudioDuration;

struct Density {
    counts: Vec<usize>,
    duration: f32,
    bin_seconds: f32,
    total: usize,
}

impl Density {
    fn from_times(times: &[f32], duration: f32) -> Self {
        let duration = times
            .iter()
            .copied()
            .filter(|t| t.is_finite())
            .fold(duration.max(1.0), |end, t| end.max(t + 0.001))
            .ceil();
        // One-second bins for ordinary songs; bound work for unusually long charts.
        let bins = (duration.ceil() as usize).clamp(1, 4096);
        let bin_seconds = (duration / bins as f32).max(1.0);
        let mut counts = vec![0; bins];
        for &time in times.iter().filter(|t| t.is_finite()) {
            let index = ((time.max(0.0) / bin_seconds) as usize).min(bins - 1);
            counts[index] += 1;
        }
        Self {
            counts,
            duration,
            bin_seconds,
            total: times.len(),
        }
    }

    fn bin_duration(&self, index: usize) -> f32 {
        (self.duration - index as f32 * self.bin_seconds)
            .min(self.bin_seconds)
            .max(0.001)
    }

    fn nps(&self, index: usize) -> f32 {
        self.counts[index] as f32 / self.bin_duration(index)
    }
}

pub fn density_tab(
    In(mut ui): In<Ui>,
    notes: Query<&Note, Without<Pending>>,
    bpm: Res<BpmList>,
    offset: Res<Offset>,
    time: Res<ChartTime>,
    audio: Option<Res<AudioDuration>>,
    mut seek: MessageWriter<SeekTo>,
) {
    let offset_seconds = offset.0 / 1000.0;
    let times: Vec<_> = notes
        .iter()
        .map(|n| bpm.time_at(n.beat) + offset_seconds)
        .collect();
    let audio_end = audio.as_ref().map(|a| a.0.as_secs_f32()).unwrap_or(0.0);
    let density = Density::from_times(&times, audio_end);
    let peak = (0..density.counts.len())
        .map(|i| density.nps(i))
        .fold(0.0_f32, f32::max);
    ui.horizontal(|ui| {
        ui.strong(t!("tab.density.total", count = density.total));
        ui.separator();
        ui.label(t!("tab.density.peak", value = format!("{peak:.1}")));
    });
    let size = egui::vec2(
        ui.available_width().max(1.0),
        ui.available_height().max(60.0),
    );
    let (rect, response) = ui.allocate_exact_size(size, Sense::click_and_drag());
    let plot = rect.shrink2(egui::vec2(4.0, 4.0));
    let plot = egui::Rect::from_min_max(plot.min, plot.max - egui::vec2(0.0, 16.0));
    let painter = ui.painter_at(rect);
    painter.rect_filled(plot, 2.0, ui.visuals().extreme_bg_color);
    let ceiling = peak.ceil().max(1.0);
    for fraction in [0.0, 0.5, 1.0] {
        let y = plot.bottom() - plot.height() * fraction;
        painter.hline(
            plot.x_range(),
            y,
            Stroke::new(0.5_f32, ui.visuals().widgets.noninteractive.bg_stroke.color),
        );
    }
    let now = time.0 + offset_seconds;
    let current_bin = (now.max(0.0) / density.bin_seconds) as usize;
    for (i, &count) in density.counts.iter().enumerate() {
        if count == 0 {
            continue;
        }
        let start = i as f32 * density.bin_seconds;
        let end = (start + density.bin_seconds).min(density.duration);
        let x0 = egui::lerp(plot.x_range(), start / density.duration);
        let x1 = egui::lerp(plot.x_range(), end / density.duration);
        let height = density.nps(i) / ceiling * plot.height();
        let color = if i == current_bin {
            Color32::from_rgb(243, 199, 94)
        } else {
            ui.visuals().selection.bg_fill
        };
        painter.rect_filled(
            egui::Rect::from_min_max(
                egui::pos2(x0, plot.bottom() - height),
                egui::pos2(x1.max(x0 + 0.5), plot.bottom()),
            ),
            0.0,
            color,
        );
    }
    let x = egui::lerp(plot.x_range(), (now / density.duration).clamp(0.0, 1.0));
    painter.vline(x, plot.y_range(), Stroke::new(1.5_f32, Color32::WHITE));
    for (fraction, seconds) in [
        (0.0, 0.0),
        (0.5, density.duration / 2.0),
        (1.0, density.duration),
    ] {
        let align = if fraction == 0.0 {
            Align2::LEFT_TOP
        } else if fraction == 1.0 {
            Align2::RIGHT_TOP
        } else {
            Align2::CENTER_TOP
        };
        painter.text(
            egui::pos2(egui::lerp(plot.x_range(), fraction), plot.bottom() + 3.0),
            align,
            format!("{}:{:02}", seconds as u32 / 60, seconds as u32 % 60),
            FontId::proportional(10.0),
            ui.visuals().weak_text_color(),
        );
    }
    if let Some(pos) = response.hover_pos() {
        let seconds = ((pos.x - plot.left()) / plot.width()).clamp(0.0, 1.0) * density.duration;
        let i = ((seconds / density.bin_seconds) as usize).min(density.counts.len() - 1);
        response.clone().on_hover_text(t!(
            "tab.density.hover",
            start = format!("{:.1}", i as f32 * density.bin_seconds),
            end = format!(
                "{:.1}",
                ((i + 1) as f32 * density.bin_seconds).min(density.duration)
            ),
            count = density.counts[i],
            nps = format!("{:.1}", density.nps(i))
        ));
    }
    if response.clicked() || response.dragged() {
        if let Some(pos) = response.interact_pointer_pos() {
            let seconds = ((pos.x - plot.left()) / plot.width()).clamp(0.0, 1.0) * density.duration;
            seek.write(SeekTo(seconds.min(if audio_end > 0.0 {
                audio_end
            } else {
                density.duration
            })));
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn density_counts_simultaneous_notes_once_each_and_keeps_silent_sections() {
        let d = Density::from_times(&[0.1, 0.1, 2.4, 3.0], 5.0);
        assert_eq!(d.counts, [2, 0, 1, 1, 0]);
        assert_eq!(d.total, 4);
        assert_eq!(d.nps(0), 2.0);
    }

    #[test]
    fn density_handles_empty_charts_boundaries_and_long_charts() {
        assert_eq!(Density::from_times(&[], 0.0).counts, [0]);
        let d = Density::from_times(&[-0.1, 1.0, 2.0], 2.0);
        assert_eq!(d.counts.iter().sum::<usize>(), 3);
        assert_eq!(d.counts[1], 1);
        assert_eq!(d.counts[2], 1);
        assert_eq!(
            Density::from_times(&[100_000.0], 100_001.0).counts.len(),
            4096
        );
    }
}
