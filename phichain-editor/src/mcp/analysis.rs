//! Background audio features from the same decoder used by editor playback.
use super::*;
use bevy_kira_audio::{prelude::StaticSoundData, AudioSource};
use realfft::RealFftPlanner;
use std::collections::VecDeque;
use undo::Edit;

#[derive(Debug, Clone)]
pub struct SetBpmList {
    pub from: BpmList,
    pub to: BpmList,
}
impl Edit for SetBpmList {
    type Target = World;
    type Output = ();
    fn edit(&mut self, w: &mut World) {
        w.insert_resource(self.to.clone());
    }
    fn undo(&mut self, w: &mut World) {
        w.insert_resource(self.from.clone());
    }
}
pub fn parse_bpm(value: &Value) -> Result<BpmList> {
    let points = value.as_array().context("bpm_list must be an array")?;
    if points.is_empty() || points.len() > 1000 {
        bail!("Provide 1–1000 BPM points")
    }
    super::validate_beats(value)?;
    let list: BpmList = serde_json::from_value(value.clone())?;
    if list.0[0].beat != Beat::ZERO {
        bail!("BPM list must start at beat zero")
    }
    for (i, p) in list.0.iter().enumerate() {
        if !p.bpm.is_finite()
            || !(1.0..=1000.0).contains(&p.bpm)
            || (i > 0 && p.beat <= list.0[i - 1].beat)
        {
            bail!("BPM values must be 1–1000 and beats strictly increasing")
        }
    }
    Ok(list)
}

#[derive(Resource, Default)]
struct Jobs(VecDeque<(String, Arc<Mutex<Value>>)>);
fn number(args: &Value, key: &str, default: f64) -> Result<f64> {
    let value = args
        .get(key)
        .map(|v| v.as_f64().context(format!("{key} must be numeric")))
        .transpose()?
        .unwrap_or(default);
    if !value.is_finite() {
        bail!("{key} must be finite")
    }
    Ok(value)
}
pub fn start(w: &mut World, args: &Value) -> Result<Value> {
    let path = if let Some(path) = args.get("path") {
        PathBuf::from(path.as_str().context("path must be a string")?).canonicalize()?
    } else {
        w.get_resource::<Project>()
            .context("Provide an audio path or open a project")?
            .path
            .music_path()
            .context("Project has no audio")?
    };
    let from = number(args, "from_seconds", 0.0)?;
    let to = number(args, "to_seconds", from + 60.0)?;
    let min = number(args, "bpm_min", 80.0)?;
    let max = number(args, "bpm_max", 240.0)?;
    if from < 0.0 || to <= from || to - from > 600.0 || min < 30.0 || max > 400.0 || min >= max {
        bail!("Invalid audio range (max 600s) or BPM range (30–400)")
    }
    let reference = args
        .get("reference_first_audible_seconds")
        .filter(|v| !v.is_null())
        .map(|_| number(args, "reference_first_audible_seconds", 0.0))
        .transpose()?;
    let lyrics = args.get("lyric_cues").cloned().unwrap_or(json!([]));
    let cues = lyrics.as_array().context("lyric_cues must be an array")?;
    if cues.len() > 5000 {
        bail!("Too many lyric cues")
    }
    for cue in cues {
        if number(cue, "time_seconds", -1.0)? < 0.0
            || cue["text"].as_str().is_none_or(|s| s.len() > 4000)
        {
            bail!("Invalid lyric cue")
        }
    }
    w.init_resource::<Jobs>();
    let mut jobs = w.resource_mut::<Jobs>();
    let running = jobs
        .0
        .iter()
        .filter(|(_, job)| job.lock().unwrap()["state"] == "running")
        .count();
    if running >= 2 {
        bail!("At most two audio analyses may run at once")
    }
    let evicted = if jobs.0.len() >= 16 {
        let i = jobs
            .0
            .iter()
            .position(|(_, job)| job.lock().unwrap()["state"] != "running")
            .context("Analysis cache is busy")?;
        Some(jobs.0.remove(i).unwrap().0)
    } else {
        None
    };
    drop(jobs);
    // Clone the existing decoded sound when analyzing the open project's audio.
    let existing = w
        .get_resource::<Project>()
        .filter(|p| p.path.music_path().as_ref() == Some(&path))
        .and_then(|_| {
            let id = w.get_resource::<phichain_game::audio::AudioAssetId>()?;
            w.get_resource::<Assets<AudioSource>>()?
                .get(id.0)
                .map(|s| s.sound.clone())
        });
    let analysis_id = uuid::Uuid::new_v4().to_string();
    let job = Arc::new(Mutex::new(
        json!({"analysis_id":analysis_id,"state":"running","source_path":path,"decoder":"PhiChain / Kira StaticSoundData"}),
    ));
    w.resource_mut::<Jobs>()
        .0
        .push_back((analysis_id.clone(), job.clone()));
    let worker_args = args.clone();
    std::thread::spawn(move || {
        let result = (|| -> Result<Value> {
            let sound = match existing {
                Some(sound) => sound,
                None => phichain_game::audio::open_and_decode_audio(path.clone())?,
            };
            let mut features = extract(&sound, from, to, min, max)?;
            let native = features["first_audible_seconds"].as_f64();
            features["decoder_timing"] = json!({"native_first_audible_seconds":native,
                "ffmpeg_first_audible_seconds":reference,"estimated_delay_seconds":native.zip(reference).map(|(n,r)|n-r),
                "method":"compare first per-channel sample above amplitude 0.0005; reference is the first 2s of ffmpeg's gapless decode",
                "uncertainty_seconds":0.002,"note":"No correction is applied to native onset times; different threshold crossings can affect the estimate"});
            features["lyric_cues"] = lyrics;
            features["lyric_timing_note"]=json!("Supplied source timestamps are preserved; decoder-delay estimate may suggest a shift, but alignment is not inferred automatically");
            features["request"] = worker_args;
            Ok(features)
        })();
        let mut output = job.lock().unwrap();
        match result {
            Ok(features) => {
                output["state"] = json!("completed");
                output["features"] = features;
            }
            Err(error) => {
                output["state"] = json!("failed");
                output["error"] = json!(error.to_string());
            }
        }
    });
    Ok(
        json!({"analysis_id":analysis_id,"state":"running","next":"read_audio_features","evicted_analysis_id":evicted}),
    )
}

pub fn read(w: &mut World, args: &Value) -> Result<Value> {
    let id = args["analysis_id"]
        .as_str()
        .context("analysis_id required")?;
    let jobs = w
        .get_resource::<Jobs>()
        .context("No audio analyses in this editor session")?;
    let job = jobs
        .0
        .iter()
        .find(|(key, _)| key == id)
        .context("Unknown/evicted analysis; analyses are scoped to this editor process")?
        .1
        .lock()
        .unwrap();
    let mut result = job.clone();
    if result["state"] != "completed" {
        return Ok(result);
    }
    let from = number(args, "from_seconds", 0.0)?;
    let to = number(args, "to_seconds", 1e12)?;
    let offset = args
        .get("onset_offset")
        .map(|v| v.as_u64().context("Invalid onset_offset"))
        .transpose()?
        .unwrap_or(0) as usize;
    let limit = args
        .get("limit")
        .map(|v| v.as_u64().context("Invalid limit"))
        .transpose()?
        .unwrap_or(500) as usize;
    if from < 0.0 || to <= from || !(1..=2000).contains(&limit) {
        bail!("Invalid feature range or limit (1–2000)")
    }
    let features = &mut result["features"];
    let onsets: Vec<_> = features["onsets"]
        .as_array()
        .unwrap()
        .iter()
        .filter(|v| {
            v["time_seconds"]
                .as_f64()
                .is_some_and(|t| t >= from && t < to)
        })
        .cloned()
        .collect();
    let total = onsets.len();
    features["onsets"] = json!(onsets
        .into_iter()
        .skip(offset)
        .take(limit)
        .collect::<Vec<_>>());
    features["onset_page"] = json!({"offset":offset,"total_in_range":total,"next_offset":if offset+limit<total{Some(offset+limit)}else{None}});
    for key in ["energy", "lyric_cues", "section_candidates"] {
        let values: Vec<_> = features[key]
            .as_array()
            .unwrap()
            .iter()
            .filter(|v| {
                v["time_seconds"]
                    .as_f64()
                    .is_some_and(|t| t >= from && t < to)
            })
            .take(2000)
            .cloned()
            .collect();
        features[key] = json!(values);
    }
    Ok(result)
}

fn percentile(values: &[f32], fraction: f32) -> f32 {
    if values.is_empty() {
        return 0.0;
    }
    let mut copy = values.to_vec();
    copy.sort_by(f32::total_cmp);
    copy[((copy.len() - 1) as f32 * fraction) as usize]
}
fn interpolate(values: &[f32], index: f64) -> f64 {
    if index < 0.0 || index >= (values.len().saturating_sub(1)) as f64 {
        return 0.0;
    }
    let a = index.floor() as usize;
    let f = index - a as f64;
    values[a] as f64 * (1.0 - f) + values[a + 1] as f64 * f
}
fn tempo_scores(
    flux: &[f32],
    first: f64,
    hop: f64,
    from: f64,
    to: f64,
    min: f64,
    max: f64,
) -> Vec<(f64, f64, f64)> {
    let score = |bpm: f64| {
        let half = 30.0 / bpm;
        let mut best = (0.0, bpm, 0.0);
        let phases = (half / hop).ceil().max(1.0) as usize;
        for phase in 0..phases {
            let offset = phase as f64 * half / phases as f64;
            let mut t = (from / half).ceil() * half + offset;
            let mut sum = 0.0;
            let mut count = 0;
            while t < to {
                sum += interpolate(flux, (t - first) / hop);
                count += 1;
                t += half;
            }
            if count > 0 {
                let value = sum / count as f64;
                if value > best.0 {
                    best = (value, bpm, offset);
                }
            }
        }
        best
    };
    let mut coarse = Vec::new();
    let mut bpm = min;
    while bpm <= max {
        coarse.push(score(bpm));
        bpm += 0.5;
    }
    coarse.sort_by(|a, b| b.0.total_cmp(&a.0));
    let mut refined = Vec::new();
    for &(_, center, _) in coarse.iter().take(8) {
        let mut bpm = (center - 0.5).max(min);
        while bpm <= (center + 0.5).min(max) + 1e-7 {
            refined.push(score(bpm));
            bpm += 0.1;
        }
    }
    refined.sort_by(|a, b| b.0.total_cmp(&a.0));
    let mut best = Vec::new();
    for candidate in refined {
        if best
            .iter()
            .all(|c: &(f64, f64, f64)| (c.1 - candidate.1).abs() > 1.0)
        {
            best.push(candidate);
        }
        if best.len() == 5 {
            break;
        }
    }
    best
}

fn extract(sound: &StaticSoundData, from: f64, to: f64, min: f64, max: f64) -> Result<Value> {
    let duration = sound.duration().as_secs_f64();
    let to = to.min(duration);
    if to - from < 2.0 {
        bail!("Analyze at least two seconds of available audio")
    }
    let native_rate = sound.sample_rate as usize;
    if native_rate == 0 {
        bail!("Invalid audio sample rate")
    }
    let stride = (native_rate / 22050).max(1);
    let rate = native_rate as f64 / stride as f64;
    let start = (from * native_rate as f64) as usize;
    let stop = (to * native_rate as f64) as usize;
    let first_audible = sound
        .frames
        .iter()
        .position(|f| f.left.abs().max(f.right.abs()) > 0.0005)
        .map(|i| i as f64 / native_rate as f64);
    let mono: Vec<_> = sound.frames[start..stop.min(sound.frames.len())]
        .iter()
        .step_by(stride)
        .map(|f| (f.left + f.right) * 0.5)
        .collect();
    let size = 1024usize;
    let hop = (rate * 0.01).round().max(1.0) as usize;
    let hop_seconds = hop as f64 / rate;
    let mut planner = RealFftPlanner::<f32>::new();
    let fft = planner.plan_fft_forward(size);
    let mut input = fft.make_input_vec();
    let mut output = fft.make_output_vec();
    let mut scratch = fft.make_scratch_vec();
    let window: Vec<_> = (0..size)
        .map(|i| 0.5 - 0.5 * (std::f32::consts::TAU * i as f32 / (size - 1) as f32).cos())
        .collect();
    let mut previous = vec![0.0; output.len()];
    let mut flux = Vec::new();
    let mut times = Vec::new();
    for index in (0..mono.len().saturating_sub(size)).step_by(hop) {
        for i in 0..size {
            input[i] = mono[index + i] * window[i];
        }
        fft.process_with_scratch(&mut input, &mut output, &mut scratch)
            .map_err(|e| anyhow!("FFT: {e}"))?;
        let mut total = 0.0;
        for (i, bin) in output.iter().enumerate() {
            let value = (1.0 + bin.norm() * 10.0).ln();
            if !flux.is_empty() {
                total += (value - previous[i]).max(0.0);
            }
            previous[i] = value;
        }
        flux.push(total);
        times.push(from + (index + size / 2) as f64 / rate);
    }
    let mut prefix = vec![0.0];
    for &value in &flux {
        prefix.push(prefix.last().unwrap() + value);
    }
    let raw = flux.clone();
    for (i, value) in flux.iter_mut().enumerate() {
        let a = i.saturating_sub(15);
        let b = (i + 16).min(raw.len());
        *value = (*value - (prefix[b] - prefix[a]) / (b - a) as f32).max(0.0);
    }
    let threshold = percentile(&flux, 0.65).max(flux.iter().copied().fold(0.0, f32::max) * 0.025);
    let mut peaks: Vec<_> = (1..flux.len().saturating_sub(1))
        .filter(|&i| flux[i] > threshold && flux[i] >= flux[i - 1] && flux[i] > flux[i + 1])
        .collect();
    peaks.sort_by(|&a, &b| flux[b].total_cmp(&flux[a]));
    let mut selected = Vec::new();
    for index in peaks {
        if selected
            .iter()
            .all(|&other: &usize| (times[index] - times[other]).abs() > 0.045)
        {
            selected.push(index);
        }
        if selected.len() == 20000 {
            break;
        }
    }
    selected.sort_unstable();
    let mut onsets = Vec::new();
    for &index in &selected {
        // Refine the FFT-window peak against short-frame energy growth.
        let center = ((times[index] - from) * rate) as usize;
        let a = center.saturating_sub(size / 2);
        let b = (center + size / 2).min(mono.len());
        let step = (rate * 0.001).round().max(1.0) as usize;
        let mut best = (0.0, center);
        for i in (a + step..b.saturating_sub(step)).step_by(step) {
            let before = mono[i - step..i].iter().map(|v| v * v).sum::<f32>() / step as f32;
            let after = mono[i..i + step].iter().map(|v| v * v).sum::<f32>() / step as f32;
            let growth = after - before;
            if growth > best.0 {
                best = (growth, i);
            }
        }
        onsets.push(json!({"time_seconds":from+best.1 as f64/rate,"strength":flux[index],"uncertainty_seconds":0.01}));
    }
    let scores = tempo_scores(&flux, times[0], hop_seconds, from, to, min, max);
    let flux_mean = flux.iter().sum::<f32>() / flux.len().max(1) as f32;
    let first_strong = selected
        .iter()
        .find(|&&i| flux[i] > percentile(&flux, 0.95))
        .map(|&i| times[i])
        .unwrap_or(from);
    let mut candidates = Vec::new();
    for &(score, bpm, _) in &scores {
        let half = 30.0 / bpm;
        let mut sine = 0.0;
        let mut cosine = 0.0;
        for onset in &onsets {
            let t = onset["time_seconds"].as_f64().unwrap();
            let weight = onset["strength"].as_f64().unwrap();
            sine += (t * std::f64::consts::TAU / half).sin() * weight;
            cosine += (t * std::f64::consts::TAU / half).cos() * weight;
        }
        let phase = (sine.atan2(cosine) * half / std::f64::consts::TAU).rem_euclid(half);
        let anchor = phase + ((first_strong - phase) / half).round() * half;
        let concentration = (sine * sine + cosine * cosine).sqrt()
            / onsets
                .iter()
                .map(|v| v["strength"].as_f64().unwrap())
                .sum::<f64>()
                .max(1e-9);
        candidates.push(json!({"bpm":(bpm*10.0).round()/10.0,"grid_fit_score":score/(flux_mean as f64).max(1e-9),"grid_phase_seconds":phase,
            "suggested_offset_seconds":anchor,"suggested_offset_ms":anchor*1000.0,"phase_concentration":concentration,
            "anchor_note":"First strong onset mapped to beat zero; musical downbeat/bar position is unverified"}));
    }
    let ambiguity = scores.first().is_some_and(|&(_, bpm, _)| {
        scores.iter().skip(1).any(|&(score, other, _)| {
            ((other / bpm - 2.0).abs() < 0.03 || (other / bpm - 0.5).abs() < 0.03)
                && score > scores[0].0 * 0.8
        })
    });
    let score = scores.first().map(|s| s.0).unwrap_or(0.0);
    let contrast = (score / ((flux_mean as f64).max(1e-9)) - 1.0).max(0.0);
    let confidence = (contrast / 5.0).clamp(0.0, if ambiguity { 0.65 } else { 0.9 });
    if selected.len() < 4 || flux_mean < 0.00001 {
        candidates.clear();
    }
    let step = (rate * 0.1).round().max(1.0) as usize;
    let energy:Vec<_>=mono.chunks(step).enumerate().map(|(i,chunk)|{
        let rms=(chunk.iter().map(|v|v*v).sum::<f32>()/chunk.len() as f32).sqrt();
        json!({"time_seconds":from+i as f64*step as f64/rate,"rms_db":20.0*rms.max(1e-9).log10(),"peak":chunk.iter().map(|v|v.abs()).fold(0.0,f32::max)})
    }).collect();
    let mut section_changes = Vec::new();
    for i in (20..energy.len().saturating_sub(20)).step_by(10) {
        let before = energy[i - 20..i]
            .iter()
            .map(|e| e["rms_db"].as_f64().unwrap())
            .sum::<f64>()
            / 20.0;
        let after = energy[i..i + 20]
            .iter()
            .map(|e| e["rms_db"].as_f64().unwrap())
            .sum::<f64>()
            / 20.0;
        if (after - before).abs() > 4.0 {
            section_changes.push(json!({"time_seconds":energy[i]["time_seconds"],"energy_change_db":after-before,"type":"energy_change","meaning":"Possible section boundary; no vocal/instrument label inferred"}));
        }
    }
    let clipped = mono.iter().filter(|&&v| v.abs() >= 0.999).count();
    Ok(
        json!({"duration_seconds":duration,"analyzed_from_seconds":from,"analyzed_to_seconds":to,"native_sample_rate":native_rate,
        "feature_sample_rate":rate,"first_audible_seconds":first_audible,"tempo_candidates":candidates,
        "confidence":if candidates.is_empty(){0.0}else{confidence},"confidence_note":"Heuristic grid evidence, not a calibrated probability; half/double tempo and downbeats need musical review",
        "half_double_tempo_ambiguous":ambiguity,"onsets":onsets,"energy":energy,"section_candidates":section_changes,"clipped_sample_fraction":clipped as f64/mono.len().max(1) as f64}),
    )
}

#[cfg(test)]
mod tests {
    use super::*;
    fn click_track(bpm: f64, seconds: f64) -> StaticSoundData {
        let sample_rate = 22050;
        let mut frames = vec![
            bevy_kira_audio::prelude::Frame::from_mono(0.0);
            (sample_rate as f64 * seconds) as usize
        ];
        let mut t = 0.3;
        while t < seconds {
            let start = (t * sample_rate as f64) as usize;
            for i in 0..200 {
                if start + i < frames.len() {
                    frames[start + i] = bevy_kira_audio::prelude::Frame::from_mono(
                        0.7 * (-(i as f32) / 30.0).exp() * (i as f32 * 0.7).cos(),
                    );
                }
            }
            t += 60.0 / bpm;
        }
        StaticSoundData {
            sample_rate,
            frames: frames.into(),
            settings: Default::default(),
            slice: None,
        }
    }
    #[test]
    fn synthetic_clicks_recover_tempo_and_native_onset_anchor() {
        let sound = click_track(120.0, 12.0);
        let features = extract(&sound, 0.0, 12.0, 100.0, 140.0).unwrap();
        let bpm = features["tempo_candidates"][0]["bpm"].as_f64().unwrap();
        assert!((bpm - 120.0).abs() < 0.5, "{features}");
        assert!((features["onsets"][0]["time_seconds"].as_f64().unwrap() - 0.3).abs() < 0.015);
        assert!(
            (features["tempo_candidates"][0]["suggested_offset_seconds"]
                .as_f64()
                .unwrap()
                - 0.3)
                .abs()
                < 0.02
        );
    }
    #[test]
    fn silence_does_not_invent_a_tempo() {
        let mut sound = click_track(120.0, 4.0);
        sound.frames = vec![bevy_kira_audio::prelude::Frame::from_mono(0.0); 88200].into();
        let features = extract(&sound, 0.0, 4.0, 80.0, 240.0).unwrap();
        assert!(features["tempo_candidates"].as_array().unwrap().is_empty());
        assert_eq!(features["confidence"], 0.0);
    }
}
