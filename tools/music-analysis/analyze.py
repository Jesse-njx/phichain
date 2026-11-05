#!/usr/bin/env python3
"""Local audio evidence -> reviewable note decisions. Does not read/write charts."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

import numpy as np
from scipy.ndimage import gaussian_filter1d, maximum_filter1d, median_filter, uniform_filter1d
from scipy.signal import find_peaks

SR = 22050
HOP = 128
FFT = 2048
STEP = HOP / SR
VERSION = "0.1.0"


def digest(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def number(value, name, low, high):
    if isinstance(value, bool) or not isinstance(value, (float, int)):
        raise ValueError(f"{name} must be a finite number")
    if not math.isfinite(value) or not low <= value <= high:
        raise ValueError(f"{name} must be in [{low}, {high}]")
    return float(value)


def normalized(values, low=10, high=95):
    """Robust relative scale, with constant signals kept constant at zero."""
    values = np.asarray(values, dtype=float)
    a, b = np.percentile(values, [low, high])
    if b - a < 1e-8:
        return np.zeros_like(values)
    return np.clip((values - a) / (b - a), 0, 1)


def db(values):
    return 20 * np.log10(np.maximum(values, 1e-9))


def relative_energy(rms_db, span=36):
    """Exclude silence from the reference so quiet attacks do not saturate."""
    active = rms_db[rms_db > max(float(np.max(rms_db)) - 50, -110)]
    if not len(active):
        return np.zeros_like(rms_db)
    reference = float(np.percentile(active, 95))
    return np.clip((rms_db - reference + span) / span, 0, 1)


def decode(source, destination):
    """One canonical PCM clock for feature extraction and browser playback."""
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        raise ValueError("Install ffmpeg (including ffprobe) and put it on PATH")
    probe = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                            "-of", "json", str(source)], capture_output=True, text=True, timeout=30)
    if probe.returncode:
        raise ValueError("Cannot inspect input audio: " + probe.stderr[-1000:])
    duration = float(json.loads(probe.stdout).get("format", {}).get("duration", 0))
    if not math.isfinite(duration) or not 0 < duration <= 1200:
        raise ValueError("Input must have a known duration of at most 20 minutes")
    result = subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-y", "-i", str(source),
                             "-map", "0:a:0", "-vn", "-ac", "2", "-ar", "44100",
                             "-c:a", "pcm_s16le", str(destination)], capture_output=True, timeout=180)
    if result.returncode:
        raise ValueError("Audio decode failed: " + result.stderr.decode(errors="replace")[-1000:])


def onset_envelope(spectrum):
    # Positive log-frequency change; no center/padding delay hidden by an API.
    log = np.log1p(spectrum * 100)
    # Frequency-local reference suppresses small pitch/vibrato movements that
    # otherwise produce repeated false attacks in sustained harmonic material.
    reference = maximum_filter1d(log[:, :-1], size=3, axis=0)
    return np.r_[0.0, np.maximum(log[:, 1:] - reference, 0).mean(axis=0)]


def peaks(envelope, rms, threshold=0.09):
    if not np.any(envelope > 1e-8) or np.max(rms) < 1e-6:
        return np.array([], dtype=int)
    scale = np.percentile(envelope[envelope > 0], 95)
    env = np.clip(envelope / max(scale, 1e-8), 0, 3)
    baseline = median_filter(env, size=2 * round(0.15 / STEP) + 1)
    indices, _ = find_peaks(env, height=baseline + threshold,
                            prominence=threshold, distance=max(1, round(0.04 / STEP)))
    gate = max(np.max(rms) * 0.006, 1e-6)
    return indices[rms[indices] > gate]


def refine_attack(frame, envelope):
    """Return leading edge of the detected rise, not the end of a centered FFT."""
    left = max(0, frame - round(0.035 / STEP))
    floor = envelope[frame] * 0.2
    cursor = frame
    while cursor > left and envelope[cursor - 1] > floor and envelope[cursor - 1] <= envelope[cursor]:
        cursor -= 1
    # A centered window smears the leading edge backwards. The midpoint is an
    # estimate; preserve the raw peak and report the analysis window separately.
    return max(0.0, (cursor + frame) * STEP / 2)


def pitch_regions(harmonic, rms):
    """Conservative dominant spectral-ridge spans, NOT polyphonic transcription."""
    import librosa
    pitches, magnitudes = librosa.piptrack(S=harmonic, sr=SR, n_fft=FFT,
                                          hop_length=HOP, fmin=90, fmax=2200, threshold=0.18)
    best = magnitudes.argmax(axis=0)
    columns = np.arange(harmonic.shape[1])
    hz = pitches[best, columns]
    dominance = magnitudes[best, columns] / np.maximum(magnitudes.sum(axis=0), 1e-9)
    midi = np.rint(librosa.hz_to_midi(np.maximum(hz, 1)))
    midi = median_filter(midi, size=7)
    valid = (hz > 0) & (rms > max(np.max(rms) * 0.04, 1e-6)) & (dominance > 0.2)
    midi[~valid] = -1
    breaks = np.r_[0, np.flatnonzero(np.diff(midi) != 0) + 1, len(midi)]
    regions = []
    for a, b in zip(breaks[:-1], breaks[1:]):
        if midi[a] >= 0 and (b - a) * STEP >= 0.16:
            regions.append({"start": float(a * STEP), "end": float(b * STEP),
                            "midi": int(midi[a]), "stability": float(np.mean(dominance[a:b]))})
    return regions


def extract(y, stem_audio=None, progress=print):
    import librosa
    progress("Extracting spectral, transient and sustained-tone evidence…")
    spectrum = np.abs(librosa.stft(y, n_fft=FFT, hop_length=HOP))
    rms = librosa.feature.rms(S=spectrum, frame_length=FFT, hop_length=HOP)[0]
    harmonic, percussive = librosa.decompose.hpss(spectrum)
    frequencies = librosa.fft_frequencies(sr=SR, n_fft=FFT)
    layers = {}
    if stem_audio:
        for name, audio in stem_audio.items():
            s = np.abs(librosa.stft(audio, n_fft=FFT, hop_length=HOP))
            layers[name] = (s, librosa.feature.rms(S=s, frame_length=FFT, hop_length=HOP)[0])
    else:
        for name, mask in [("low_percussive", (frequencies >= 30) & (frequencies < 250)),
                           ("mid_percussive", (frequencies >= 250) & (frequencies < 2500)),
                           ("high_percussive", frequencies >= 2500)]:
            band = percussive[mask]
            layers[name] = (band, np.sqrt(np.mean(band ** 2, axis=0)) / np.sqrt(FFT))
        layers["harmonic_texture"] = (harmonic, librosa.feature.rms(
            S=harmonic, frame_length=FFT, hop_length=HOP)[0])
    envelope = onset_envelope(spectrum)
    raw = []
    layer_energy = {}
    for name, (s, energy) in layers.items():
        env = onset_envelope(s)
        positive = env[env > 1e-9]
        strength_scale = float(np.percentile(positive, 95)) if len(positive) else 1
        layer_energy[name] = uniform_filter1d(energy, max(1, round(2 / STEP)))
        for index in peaks(env, energy):
            strength = float(np.clip(env[index] / max(strength_scale, 1e-8), 0, 1))
            raw.append({"time": refine_attack(index, env), "peak": float(index * STEP),
                        "layer": name, "strength": strength, "frame": int(index),
                        "evidence": "spectral_attack"})
    progress("Tracing sustained tone candidates…")
    regions = pitch_regions(harmonic, rms)
    # Keep pitch-change evidence even when its attack is masked by the mix.
    for region in regions:
        t = region["start"]
        if not any(abs(item["time"] - t) <= 0.06 and item["layer"] in
                   ("harmonic_texture", "vocals", "other", "bass") for item in raw):
            raw.append({"time": t, "peak": t, "layer": "tonal_ridge",
                        "strength": min(0.7, region["stability"]), "frame": round(t / STEP),
                        "evidence": "dominant_pitch_change"})
    chroma = librosa.feature.chroma_stft(S=harmonic ** 2, sr=SR, n_fft=FFT, hop_length=HOP, tuning=0)
    mel = librosa.feature.melspectrogram(S=spectrum ** 2, sr=SR, n_fft=FFT, n_mels=32)
    centroid = librosa.feature.spectral_centroid(S=spectrum, sr=SR)[0]
    return {"rms": rms, "onset": envelope, "raw": raw, "regions": regions,
            "chroma": chroma, "mel": mel, "centroid": centroid, "layer_energy": layer_energy}


def structure(features, duration):
    """Unsupervised texture sections + sustained-intensity climax candidates."""
    progress_step = 0.25
    times = np.arange(0, duration, progress_step)
    frames = np.clip(np.rint(times / STEP).astype(int), 0, len(features["rms"]) - 1)
    smooth = max(1, round(1.5 / STEP))
    # Running sums can leave tiny negative roundoff after an isolated impulse.
    rms_db = db(np.sqrt(np.maximum(uniform_filter1d(features["rms"] ** 2, smooth), 0)))
    active_db = rms_db[rms_db > max(float(np.max(rms_db)) - 35, -110)]
    if len(active_db):
        lo, hi = np.percentile(active_db, [10, 95])
        loudness = np.clip((rms_db - lo) / max(hi - lo, 0.5), 0, 1)
    else:
        loudness = np.zeros_like(rms_db)
    activity = normalized(uniform_filter1d(features["onset"], smooth), 10, 95)
    # Effective spectral occupancy, not inferred instrument count.
    mel = features["mel"]
    relative = mel / np.maximum(mel.max(axis=0), 1e-9)
    fullness = normalized(uniform_filter1d((relative > 0.02).mean(axis=0), smooth))
    intensity = np.clip(0.5 * loudness + 0.3 * activity + 0.2 * fullness, 0, 1)
    intensity[rms_db < max(float(np.max(rms_db)) - 48, -110)] = 0
    coarse = intensity[frames]
    # Change in timbre/chroma over adjacent two-second contexts.
    f = np.vstack([np.log1p(mel[:, frames]), features["chroma"][:, frames]])
    f = (f - f.mean(axis=1, keepdims=True)) / np.maximum(f.std(axis=1, keepdims=True), 0.15)
    width = 8
    novelty = np.zeros(len(times))
    for i in range(width, len(times) - width):
        novelty[i] = np.linalg.norm(f[:, i:i + width].mean(axis=1) - f[:, i - width:i].mean(axis=1))
    novelty = gaussian_filter1d(novelty, 1)
    boundary_indices, _ = find_peaks(novelty, distance=round(6 / progress_step),
                                     prominence=max(0.8, float(np.std(novelty) * 0.6)))
    boundaries = [0.0] + [float(times[i]) for i in boundary_indices if 3 <= times[i] <= duration - 3] + [duration]
    sections = []
    for index, (a, b) in enumerate(zip(boundaries[:-1], boundaries[1:])):
        mask = (times >= a) & (times < b)
        value = float(np.mean(coarse[mask])) if np.any(mask) else 0
        sections.append({"id": f"s{index + 1:03}", "start_seconds": round(a, 5),
                         "end_seconds": round(b, 5), "label": f"Section {index + 1}",
                         "intensity": round(value * 100, 1), "climax": False,
                         "provenance": "automatic_texture_boundary", "review_status": "unreviewed",
                         "boundary_uncertainty_seconds": 2.0})
    # A brief loud hit cannot qualify: require sustained contrast and >=4 s span.
    sustained = uniform_filter1d(coarse, max(1, round(min(8, duration / 3) / progress_step)))
    climax = []
    if duration >= 12 and np.max(features["rms"]) > 1e-6 and np.ptp(sustained) >= 0.15:
        threshold = max(0.48, float(np.percentile(sustained, 70)))
        lower = max(0.25, min(threshold - 0.08, float(np.percentile(sustained, 50))))
        high = sustained >= threshold
        # Hysteresis retains the full sustained passage around a high core.
        for i in np.flatnonzero(high):
            left, right = i - 1, i + 1
            while left >= 0 and sustained[left] >= lower:
                high[left] = True
                left -= 1
            while right < len(high) and sustained[right] >= lower:
                high[right] = True
                right += 1
        # Close gaps < 1.5 s while preserving region edges.
        for i in range(1, len(high) - 1):
            if not high[i] and high[i - 1]:
                later = np.flatnonzero(high[i:i + 6])
                if len(later):
                    high[i:i + later[0]] = True
        edges = np.flatnonzero(np.diff(np.r_[False, high, False]))
        for a, b in zip(edges[::2], edges[1::2]):
            start, end = float(times[a]), float(min(b * progress_step, duration))
            if end - start < 4 or end - start > duration * 0.7:
                continue
            peak = a + int(np.argmax(coarse[a:b]))
            contrast = float(np.mean(sustained[a:b]) - np.median(sustained))
            climax.append({"start_seconds": start, "end_seconds": round(end, 5),
                           "peak_seconds": float(times[peak]), "intensity": round(float(np.mean(coarse[a:b])) * 100, 1),
                           "confidence": round(min(0.8, 0.35 + contrast), 3),
                           "provenance": "sustained_acoustic_intensity", "review_status": "unreviewed",
                           "reason": "Sustained loudness, attack activity and spectral fullness above this song's baseline; musical function needs review."})
        for section in sections:
            section["climax"] = any(min(section["end_seconds"], c["end_seconds"]) -
                                     max(section["start_seconds"], c["start_seconds"]) >
                                     (section["end_seconds"] - section["start_seconds"]) / 2 for c in climax)
    timeline = [{"seconds": round(float(t), 3), "intensity": round(float(coarse[i]) * 100, 1),
                 "rms_dbfs": round(float(rms_db[frames[i]]), 2),
                 "attack_activity": round(float(activity[frames[i]]) * 100, 1),
                 "spectral_fullness": round(float(fullness[frames[i]]) * 100, 1)} for i, t in enumerate(times)]
    return sections, climax, timeline, intensity


def decide(features, sections, intensity_curve, duration, threshold=50, min_gap=0.045, bpm=None, offset=0):
    raw = sorted((x for x in features["raw"] if x["time"] < duration), key=lambda x: x["time"])
    groups = []
    # Fixed-width clustering avoids chain-merging a fast run into a single note.
    for candidate in raw:
        if not groups or candidate["time"] - groups[-1][0]["time"] > 0.025:
            groups.append([candidate])
        else:
            groups[-1].append(candidate)
    rms_db = db(features["rms"])
    global_energy = relative_energy(rms_db)
    local_average = uniform_filter1d(rms_db, max(1, round(2 / STEP)))
    local_accent = np.clip((rms_db - local_average + 3) / 12, 0, 1)
    decisions = []
    for index, group in enumerate(groups):
        strongest = max(group, key=lambda x: x["strength"])
        t = float(strongest["time"])
        frame = min(len(rms_db) - 1, strongest["frame"])
        layer = strongest["layer"]
        sources = sorted({x["layer"] for x in group})
        attack = strongest["strength"]
        confidence = min(0.9, 0.3 + 0.45 * attack + 0.05 * (len(sources) - 1))
        if strongest["evidence"] == "dominant_pitch_change":
            confidence = min(confidence, 0.55)
        # Foreground is a two-second energy share among available acoustic layers;
        # there is no claim that a particular instrument is the melody.
        energies = features["layer_energy"]
        energy_total = sum(float(v[frame]) for v in energies.values())
        foreground = float(energies[layer][frame]) / max(energy_total, 1e-8) if layer in energies else 0.2
        support = min(1.0, len(sources) / 3)
        priority = 100 * (0.4 * attack + 0.25 * foreground + 0.2 * confidence + 0.15 * support)
        intensity = 100 * (0.4 * global_energy[frame] + 0.25 * local_accent[frame] +
                           0.2 * attack + 0.15 * intensity_curve[frame])
        section = next(s for s in sections if s["start_seconds"] <= t < s["end_seconds"])
        reasons = ["Audible-attack evidence" if strongest["evidence"] == "spectral_attack" else "Dominant tonal-ridge change (uncertain in polyphony)"]
        if len(sources) > 1:
            reasons.append("Coincident evidence: " + ", ".join(sources))
        if foreground > 0.45:
            reasons.append("Prominent acoustic layer in the surrounding two seconds")
        note = {"id": f"n{index + 1:05}", "time_seconds": round(t, 5),
                "detected_time_seconds": round(t, 5), "peak_time_seconds": round(strongest["peak"], 5),
                "end_seconds": round(t, 5), "suggested_type": "tap", "selected": priority >= threshold,
                "intensity": round(float(np.clip(intensity, 0, 100)), 1), "priority": round(priority, 1),
                "confidence": round(confidence, 3), "timing_resolution_ms": round(STEP * 1000, 2),
                "timing_uncertainty_ms": 50, "layer": layer, "supporting_layers": sources,
                "section_id": section["id"], "reasons": reasons, "review_status": "unreviewed",
                "evidence": {"attack_strength": round(attack, 4), "foreground_share": round(foreground, 4),
                             "local_accent": round(float(local_accent[frame]), 4),
                             "song_relative_energy": round(float(global_energy[frame]), 4)}}
        if bpm:
            beat = (t - offset) * bpm / 60
            grid = round(beat * 4) / 4
            note.update(beat=round(beat, 5), nearest_sixteenth_beat=grid,
                        grid_error_ms=round((beat - grid) * 60 / bpm * 1000, 2))
        decisions.append(note)
    # Small, explicit continuity bonus; do not force all notes in a voice to exist.
    for i, note in enumerate(decisions):
        related = [other for other in decisions[max(0, i - 12):i] if
                   note["time_seconds"] - other["time_seconds"] < 1.25 and other["layer"] == note["layer"]]
        if len(related) >= 2:
            note["priority"] = round(min(100, note["priority"] + 6), 1)
            note["selected"] = note["priority"] >= threshold
            note["reasons"].append("Repeated activity in this acoustic layer")
    # Priority-ordered temporal suppression; this is a configurable selection policy,
    # not a two-finger playability claim and not a requested target note count.
    kept = []
    for note in sorted(decisions, key=lambda n: (-n["priority"], n["time_seconds"])):
        if note["selected"]:
            conflict = next((k for k in kept if abs(k["time_seconds"] - note["time_seconds"]) < min_gap), None)
            if conflict:
                note["selected"] = False
                note["reasons"].append(f"Omitted: within minimum gap of {conflict['id']}")
            else:
                kept.append(note)
        else:
            note["reasons"].append("Omitted: below selection priority threshold")
    # Each stable tonal span can support at most one hold proposal. Reattacks
    # terminate it. Release is not emitted as a separate attack.
    claimed = set()
    for note in decisions:
        if not note["selected"] or not any(s in note["supporting_layers"] for s in
                ("harmonic_texture", "tonal_ridge", "vocals", "bass", "other")):
            continue
        match = next(((j, r) for j, r in enumerate(features["regions"]) if j not in claimed and
                      abs(r["start"] - note["time_seconds"]) < 0.08 and r["stability"] >= 0.3), None)
        if match:
            j, region = match
            later = [n["time_seconds"] for n in decisions if n["selected"] and
                     n["time_seconds"] > note["time_seconds"] + 0.08 and n["layer"] == note["layer"]]
            end = min(region["end"], duration, min(later, default=duration))
            if end - note["time_seconds"] >= 0.3:
                note.update(suggested_type="hold", end_seconds=round(end, 5),
                            sustain_confidence=round(min(0.65, region["stability"]), 3))
                note["reasons"].append("Stable dominant tonal ridge supports a provisional hold; tail needs listening review")
                claimed.add(j)
    return decisions


def load_stems(manifest_path, source_hash, duration):
    """Accept explicitly bound evidence; do not trust same-named files as matches."""
    import librosa
    manifest = json.loads(manifest_path.read_text())
    if manifest.get("source_sha256") != source_hash:
        raise ValueError("Stem manifest does not match the input audio SHA-256")
    if manifest.get("time_origin") != "decoded_audio_start":
        raise ValueError("Stem manifest time_origin must be decoded_audio_start")
    mapping = manifest.get("stems", {})
    if not isinstance(mapping, dict) or not mapping or set(mapping) - {"drums", "bass", "vocals", "other"}:
        raise ValueError("Stem manifest requires a nonempty map of drums/bass/vocals/other")
    audio, provenance = {}, {}
    for name, entry in mapping.items():
        if not isinstance(entry, dict) or not isinstance(entry.get("path"), str):
            raise ValueError(f"Stem {name} requires path and sha256")
        path = (manifest_path.parent / entry["path"]).resolve()
        if digest(path) != entry.get("sha256"):
            raise ValueError(f"Stem hash mismatch: {name}")
        y, _ = librosa.load(path, sr=SR, mono=True)
        if abs(len(y) / SR - duration) > 0.05:
            raise ValueError(f"Stem duration mismatch: {name}; align stems to decoded audio")
        audio[name] = librosa.util.fix_length(y, size=round(duration * SR))
        provenance[name] = {"path": str(path), "sha256": entry["sha256"]}
    return audio, provenance


def apply_review(result, review):
    if review.get("source_sha256") != result["source"]["sha256"]:
        raise ValueError("Review belongs to a different audio file")
    if review.get("analysis_id") != result["analysis_id"]:
        raise ValueError("Review belongs to different analysis settings/version; regenerate it")
    duration = result["source"]["duration_seconds"]
    by_id = {n["id"]: n for n in result["decisions"]}
    edits = review.get("decisions", [])
    if not isinstance(edits, list):
        raise ValueError("Review decisions must be a list")
    seen = set()
    for edit in edits:
        if not isinstance(edit, dict) or edit.get("id") not in by_id or edit["id"] in seen:
            raise ValueError("Unknown or duplicate review decision ID")
        seen.add(edit["id"])
        allowed = {"id", "selected", "intensity", "time_seconds", "end_seconds", "suggested_type", "comment"}
        if set(edit) - allowed:
            raise ValueError("Unknown review decision field")
        note = by_id[edit["id"]]
        patch = {k: v for k, v in edit.items() if k != "id"}
        if "selected" in patch and not isinstance(patch["selected"], bool):
            raise ValueError("selected must be boolean")
        for key in ("time_seconds", "end_seconds", "intensity"):
            if key in patch:
                number(patch[key], key, 0, 100 if key == "intensity" else duration)
        if patch.get("suggested_type", note["suggested_type"]) not in ("tap", "hold"):
            raise ValueError("Only tap/hold decisions are supported")
        if "comment" in patch and (not isinstance(patch["comment"], str) or len(patch["comment"]) > 2000):
            raise ValueError("Review comment must be a string of at most 2000 characters")
        original = {k: note[k] for k in patch if k in note}
        note.update(patch)
        if note["suggested_type"] == "tap":
            note["end_seconds"] = note["time_seconds"]
        elif note["end_seconds"] <= note["time_seconds"]:
            raise ValueError("Hold end must be after its start")
        if note["time_seconds"] >= duration:
            raise ValueError("Note must start before the audio ends")
        note.update(review_status="reviewed", automatic_before_review=original)
    if "sections" in review:
        sections = review["sections"]
        if not isinstance(sections, list) or not sections:
            raise ValueError("Reviewed sections must be a nonempty list covering the audio")
        cursor = 0.0
        for i, section in enumerate(sections):
            a = number(section.get("start_seconds"), "section start", 0, duration)
            b = number(section.get("end_seconds"), "section end", 0, duration)
            if abs(a - cursor) > 0.0001 or b <= a:
                raise ValueError("Reviewed sections must be contiguous, ordered and nonoverlapping")
            if not isinstance(section.get("label"), str) or not section["label"].strip():
                raise ValueError("Each reviewed section needs a label")
            if not isinstance(section.get("climax"), bool):
                raise ValueError("Each reviewed section needs a boolean climax flag")
            cursor = b
        if abs(cursor - duration) > 0.0001:
            raise ValueError("Reviewed sections must cover the complete audio")
        result["automatic_sections"] = result["sections"]
        result["automatic_climax_regions"] = result["climax_regions"]
        result["sections"] = [{**s, "id": f"s{i + 1:03}", "provenance": "review",
                               "review_status": "reviewed"} for i, s in enumerate(sections)]
        result["climax_regions"] = [{"start_seconds": s["start_seconds"], "end_seconds": s["end_seconds"],
                                     "provenance": "review", "review_status": "reviewed", "reason": s["label"]}
                                    for s in result["sections"] if s["climax"]]
    for note in result["decisions"]:
        note["section_id"] = next(s["id"] for s in result["sections"] if
                                  s["start_seconds"] <= note["time_seconds"] < s["end_seconds"])
        bpm = result["parameters"]["bpm"]
        if bpm:
            beat = (note["time_seconds"] - result["parameters"]["offset_seconds"]) * bpm / 60
            grid = round(beat * 4) / 4
            note.update(beat=round(beat, 5), nearest_sixteenth_beat=grid,
                        grid_error_ms=round((beat - grid) * 60 / bpm * 1000, 2))
    result["decisions"].sort(key=lambda n: (n["time_seconds"], n["id"]))


def summarize(result):
    notes = [n for n in result["decisions"] if n["selected"]]
    return {"candidate_count": len(result["decisions"]), "selected_count": len(notes),
            "hold_count": sum(n["suggested_type"] == "hold" for n in notes),
            "section_count": len(result["sections"]), "climax_region_count": len(result["climax_regions"]),
            "reviewed_count": sum(n["review_status"] == "reviewed" for n in result["decisions"])}


def make_click_preview(decoded, destination, decisions):
    import soundfile as sf
    y, sr = sf.read(decoded, dtype="float32", always_2d=True)
    clicks = np.zeros(len(y), dtype=np.float32)
    length = round(sr * 0.025)
    t = np.arange(length) / sr
    tick = np.sin(2 * np.pi * 1800 * t) * np.exp(-t * 180)
    for note in decisions:
        if not note["selected"]:
            continue
        a = round(note["time_seconds"] * sr)
        b = min(len(y), a + length)
        if b > a:
            clicks[a:b] += tick[:b - a] * (0.1 + note["intensity"] / 100 * 0.18)
    mixed = y * 0.72 + clicks[:, None]
    mixed /= max(1.0, float(np.max(np.abs(mixed))) / 0.98)
    sf.write(destination, mixed, sr, subtype="PCM_16")


def run(source, output, *, threshold=50, min_gap=0.045, bpm=None, offset=0,
        stems=None, review=None, progress=print):
    import librosa
    import soundfile as sf
    source, output = Path(source).resolve(), Path(output).resolve()
    number(threshold, "threshold", 0, 100)
    number(min_gap, "min-gap", 0.025, 0.5)
    number(offset, "offset", -1200, 1200)
    if bpm is not None:
        number(bpm, "bpm", 20, 400)
    if not source.is_file():
        raise ValueError("Input audio file does not exist")
    if output.exists():
        raise ValueError("Output directory already exists; choose a new directory to preserve prior reviews")
    source_hash = digest(source)
    parameters = {"priority_threshold": threshold, "minimum_gap_seconds": min_gap,
                  "bpm": bpm, "offset_seconds": offset, "sample_rate": SR,
                  "hop_length": HOP, "fft_size": FFT}
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".music-analysis-", dir=output.parent) as temp:
        folder = Path(temp)
        progress("Decoding audio to a shared PCM timeline…")
        decoded = folder / "audio.wav"
        decode(source, decoded)
        info = sf.info(decoded)
        duration = info.frames / info.samplerate
        if duration < 0.1:
            raise ValueError("Audio must be at least 0.1 seconds")
        y, _ = librosa.load(decoded, sr=SR, mono=True)
        if not np.all(np.isfinite(y)):
            raise ValueError("Decoded audio contains nonfinite samples")
        stem_audio, stem_info = (None, {}) if stems is None else load_stems(Path(stems).resolve(), source_hash, duration)
        features = extract(y, stem_audio, progress)
        progress("Selecting note candidates and sustained-intensity regions…")
        sections, climax, timeline, intensity = structure(features, duration)
        decisions = decide(features, sections, intensity, duration, threshold, min_gap, bpm, offset)
        identity = {"source": source_hash, "parameters": parameters, "stems": stem_info, "version": VERSION,
                    "librosa": librosa.__version__, "numpy": np.__version__}
        # Include actual evidence as well as settings: reviews cannot silently bind
        # to a different decode/implementation with reused sequential IDs.
        identity["decisions"] = decisions
        identity["sections"] = sections
        result = {"schema_version": 1, "analyzer_version": VERSION,
                  "analysis_id": hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest(),
                  "source": {"path": str(source), "sha256": source_hash,
                             "decoded_sha256": digest(decoded), "duration_seconds": duration,
                             "time_origin": "decoded_audio_start"},
                  "parameters": parameters, "stem_provenance": stem_info,
                  "score_definitions": {
                      "intensity": "0–100 within-song acoustic emphasis: 40% relative energy + 25% local accent + 20% attack + 15% section intensity. Not difficulty or MIDI velocity.",
                      "priority": "0–100 selection heuristic: 40% attack + 25% local layer energy share + 20% evidence confidence + 15% coincident-layer support; +6 for repeated layer activity.",
                      "confidence": "Uncalibrated 0–1 evidence score, not probability of musical correctness.",
                      "section_intensity": "50% sustained relative loudness + 30% attack activity + 20% spectral fullness."},
                  "limitations": [
                      "Automatic draft, not verified musical transcription or a finished playable chart.",
                      "Acoustic layers are not reliably identified instruments or perceptual melody voices; HPSS is texture separation.",
                      "Tonal ridges miss polyphonic/legato detail and can follow harmonics; hold tails require review.",
                      "Climax regions measure sustained acoustic emphasis; quiet emotional climaxes and verse/chorus functions require review.",
                      "Timestamps are estimates. 5.8 ms feature spacing does not imply 5.8 ms accuracy; the FFT window is about 93 ms.",
                      "No lane, finger, chord multiplicity or difficulty assignment. Nearby evidence is merged into one attack decision.",
                      "No forced grid snapping or tempo inference. Optional supplied BPM is annotation only.",
                      "Low detector activity is not proof of musical silence; omitted candidates remain inspectable."],
                  "sections": sections, "climax_regions": climax, "timeline": timeline,
                  "decisions": decisions}
        review_data = json.loads(Path(review).read_text()) if review else None
        if review_data is not None:
            apply_review(result, review_data)
        if digest(source) != source_hash:
            raise ValueError("Source changed during analysis; retry with a stable file")
        result["summary"] = summarize(result)
        result["selected_notes"] = [n for n in result["decisions"] if n["selected"]]
        # Carry earlier review corrections into a second browser review/export.
        result["review_template"] = review_data or {"source_sha256": source_hash, "analysis_id": result["analysis_id"], "decisions": []}
        (folder / "analysis.json").write_text(json.dumps(result, indent=2, ensure_ascii=False, allow_nan=False) + "\n")
        (folder / "review-template.json").write_text(json.dumps(result["review_template"], indent=2) + "\n")
        fields = ["id", "selected", "time_seconds", "end_seconds", "suggested_type", "intensity", "priority", "confidence", "layer", "section_id", "review_status", "reasons"]
        for filename, rows in [("decisions.csv", decisions), ("selected-notes.csv", result["selected_notes"])]:
            with (folder / filename).open("w", newline="") as stream:
                writer = csv.DictWriter(stream, fieldnames=fields, extrasaction="ignore")
                writer.writeheader()
                for row in rows:
                    writer.writerow({**row, "reasons": "; ".join(row["reasons"])})
        progress("Building audio comparison and interactive report…")
        make_click_preview(decoded, folder / "with-hits.wav", decisions)
        from report import write_report
        write_report(result, folder / "index.html")
        # Only a fully successful run becomes visible at the requested destination.
        folder.rename(output)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("audio", type=Path, help="MP3/WAV/OGG or another ffmpeg-readable local audio file")
    parser.add_argument("--out", required=True, type=Path, help="New artifact directory, preferably outside the repository")
    parser.add_argument("--threshold", type=float, default=50, help="Selection priority cutoff, 0–100 (default 50)")
    parser.add_argument("--min-gap", type=float, default=0.045, help="Minimum selected attack separation in seconds")
    parser.add_argument("--bpm", type=float, help="Known BPM for beat annotations only; no snapping")
    parser.add_argument("--offset", type=float, default=0, help="Audio seconds of beat zero for --bpm")
    parser.add_argument("--stems", type=Path, help="Source-bound stem manifest; optional, no downloads")
    parser.add_argument("--review", type=Path, help="Source/settings-bound decisions and/or section corrections")
    args = parser.parse_args()
    os.environ.setdefault("NUMBA_CACHE_DIR", str(Path(tempfile.gettempdir()) / "phichain-music-numba"))
    try:
        result = run(args.audio, args.out, threshold=args.threshold, min_gap=args.min_gap,
                     bpm=args.bpm, offset=args.offset, stems=args.stems, review=args.review,
                     progress=lambda message: print(message, file=sys.stderr, flush=True))
    except (ValueError, OSError, subprocess.SubprocessError, ImportError) as error:
        parser.exit(1, f"Analysis failed: {error}\n")
    print(json.dumps({"report": str(args.out.resolve() / "index.html"), **result["summary"]}, indent=2))


if __name__ == "__main__":
    main()
