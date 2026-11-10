"""Audio evidence for the Phrase Rhythm Record (PRR).

Produces, per song, the raw per-layer evidence that the builder classifies on
the grid. Nothing here knows about bars or slots.

- Demucs htdemucs stems (cached), 20 Hz high-pass (macro rule 14).
- Drum-stem band onset envelopes: kick, snare, hat (rule 5).
- Basic Pitch frame activations on bass, vocals and other (cached .npz).
- Monophonic pitch paths (the v5 decoder, range-parameterized) for the lead
  candidates (vocals, other) and the bass.
- A full-mix onset envelope as the sanity layer.

Run with the music-flow-study venv (librosa, demucs, basic-pitch, onnxruntime):
    main/research/music-flow-study/.venv/bin/python
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import subprocess
import sys
from pathlib import Path

os.environ.setdefault("NUMBA_CACHE_DIR", "/private/tmp/phichain-music-numba")
logging.disable(logging.WARNING)

import numpy as np
import soundfile as sf
from scipy.ndimage import binary_closing, uniform_filter1d
from scipy.signal import butter, find_peaks, sosfiltfilt

REPO = Path(__file__).resolve().parents[2]
TORCH_HOME = REPO / "research/music-flow-study/model-cache/torch"

SR = 22050
HOP = 110  # 4.99 ms envelope frames
ENV_FPS = SR / HOP

# Basic Pitch frequency limits per stem, as in override-voices-v3.
BP_LIMITS = {"vocals": (90, 1600), "bass": (35, 500), "other": (65, 2400)}
# Monophonic decoder pitch ranges (MIDI) per stem.
PATH_RANGES = {"vocals": (43, 88), "other": (43, 96), "bass": (24, 60)}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def load_mono(path: Path, sr: int = SR) -> np.ndarray:
    import librosa

    y, _ = librosa.load(str(path), sr=sr, mono=True)
    return y.astype(np.float32)


def highpass(y: np.ndarray, sr: int = SR, hz: float = 20.0) -> np.ndarray:
    sos = butter(2, hz / (sr / 2), btype="highpass", output="sos")
    return sosfiltfilt(sos, y).astype(np.float32)


# ---------------------------------------------------------------- stems

def separate(audio: Path, work: Path) -> dict[str, Path]:
    """Run Demucs htdemucs once per audio file; return stem paths."""
    out = work / "stems"
    stem_dir = out / "htdemucs" / audio.stem
    names = ["drums", "bass", "vocals", "other"]
    if not all((stem_dir / f"{n}.wav").exists() for n in names):
        env = dict(os.environ, TORCH_HOME=str(TORCH_HOME))
        device = "mps"
        try:
            import torch

            if not torch.backends.mps.is_available():
                device = "cpu"
        except Exception:
            device = "cpu"
        cmd = [sys.executable, "-m", "demucs", "-n", "htdemucs", "-d", device, "-o", str(out), str(audio)]
        log = work / "demucs.log"
        with open(log, "w") as f:
            subprocess.run(cmd, check=True, stdout=f, stderr=subprocess.STDOUT, env=env)
    return {n: stem_dir / f"{n}.wav" for n in names}


# ---------------------------------------------------------------- alignment

def align_lag(mix: np.ndarray, stem_sum: np.ndarray, max_lag_s: float = 0.1) -> int:
    """Samples to roll the stems by so they line up with the decoded mix.
    MP3 decoders disagree about encoder delay: Demucs (ffmpeg) and librosa
    differ by ~25 ms on the pilot songs (Override v3 saw the same 1105 samples
    at 44.1 kHz)."""
    from scipy.signal import correlate

    m = int(max_lag_s * SR)
    n = len(mix)
    a = int(min(n * 0.3, 30 * SR))
    b = int(min(n - m - 1, a + 30 * SR))
    if b - a < 5 * SR:
        a, b = m, n - m - 1
    c = correlate(mix[a - m : b + m], stem_sum[a:b], mode="valid")
    return int(np.argmax(c) - m)


def roll(y: np.ndarray, lag: int) -> np.ndarray:
    out = np.zeros_like(y)
    if lag >= 0:
        out[lag:] = y[: len(y) - lag]
    else:
        out[:lag] = y[-lag:]
    return out


# ---------------------------------------------------------------- envelopes

def drum_activations(drums: np.ndarray, iters: int = 60) -> dict[str, np.ndarray]:
    """Kick / snare / hat activations of the drum stem by NMF with three
    spectral templates initialized from band shapes (plus one free component
    for cymbals, toms and broadband clicks). Templates adapt for the first half
    of the iterations. Returns the smoothed activations at ENV_FPS.

    The activations are used to *label* drum onsets, not to time them: the
    kick component's sub-bass peaks 20-30 ms after the beater click, and the
    click itself lands in the snare or free component (Override, NightTheater).
    Timing comes from the broadband drum-stem flux (prr_build.Builder)."""
    import librosa

    S = np.abs(librosa.stft(drums, n_fft=1024, hop_length=HOP))
    f = librosa.fft_frequencies(sr=SR, n_fft=1024)
    lf = np.log(np.maximum(f, 20))

    def bump(lo, hi):
        w = np.exp(-0.5 * ((lf - np.log(np.sqrt(lo * hi))) / (0.5 * np.log(hi / lo))) ** 2)
        return w / w.sum()

    W = np.stack([bump(40, 120), bump(150, 400) + 0.7 * bump(1500, 5000), bump(6000, 12000), np.ones_like(f) / len(f)], 1)
    rng = np.random.default_rng(0)
    H = rng.random((W.shape[1], S.shape[1])) + 0.1
    for it in range(iters):
        H *= (W.T @ S) / (W.T @ W @ H + 1e-9)
        if it < iters // 2:
            W *= (S @ H.T) / (W @ H @ H.T + 1e-9)
            W /= W.sum(0, keepdims=True)
    return {f"act_{name}": uniform_filter1d(H[k], 3).astype(np.float32) for k, name in enumerate(["kick", "snare", "hat"])}


def linear_flux(y: np.ndarray, lo: float, hi: float) -> np.ndarray:
    """Linear-magnitude spectral flux in a band (log flux peaks early)."""
    import librosa

    S = np.abs(librosa.stft(y, n_fft=1024, hop_length=HOP))
    freqs = librosa.fft_frequencies(sr=SR, n_fft=1024)
    band = (freqs >= lo) & (freqs < hi)
    return np.maximum(0.0, np.diff(S[band], axis=1, prepend=S[band][:, :1])).sum(axis=0).astype(np.float32)


def rms_env(y: np.ndarray) -> np.ndarray:
    n = len(y) // HOP
    frames = y[: n * HOP].reshape(n, HOP)
    return np.sqrt((frames ** 2).mean(axis=1) + 1e-12).astype(np.float32)


# ---------------------------------------------------------------- Basic Pitch

def basic_pitch_frames(stem: Path, name: str, work: Path) -> dict:
    cache = work / f"bp-{name}.npz"
    digest = sha256(stem)
    if cache.exists():
        z = np.load(cache)
        if str(z["source_sha256"]) == digest:
            return {"note": z["note"], "onset": z["onset"]}
    import onnxruntime as ort

    ort.disable_telemetry_events()
    from basic_pitch import ICASSP_2022_MODEL_PATH
    from basic_pitch.inference import Model, run_inference

    model = Model(ICASSP_2022_MODEL_PATH)
    out = run_inference(str(stem), model)
    lo, hi = BP_LIMITS[name]
    note, onset = out["note"], out["onset"]
    # Restrict to the stem's frequency limits (bins are MIDI 21..108).
    midi = np.arange(21, 109)
    hz = 440.0 * 2 ** ((midi - 69) / 12)
    mask = (hz >= lo) & (hz <= hi)
    note = note * mask[None, :]
    onset = onset * mask[None, :]
    np.savez_compressed(cache, note=note, onset=onset, source_sha256=digest)
    return {"note": note, "onset": onset}


def frame_times(n: int) -> np.ndarray:
    from basic_pitch.note_creation import model_frames_to_time

    return np.asarray(model_frames_to_time(n))


def decode_path(frames, onsets, activity, lo_midi, hi_midi, floor=0.34):
    """Monophonic temporal path with a silence state and same-pitch
    rearticulation. This is the v5 decoder (override-two-track-v5/pitch_path.py)
    with the pitch range as a parameter instead of Override's fixed range."""
    n, p = frames.shape
    scores = np.log(np.maximum(frames, 0.001) / floor)
    scores[~activity, :] = -20
    scores[:, : max(0, lo_midi - 21)] = -20
    scores[:, hi_midi - 21 + 1 :] = -20
    emission = np.c_[np.zeros(n), scores]
    distance = abs(np.arange(p)[:, None] - np.arange(p)[None, :])
    transition = np.full((p + 1, p + 1), 0.7)
    transition[1:, 1:] = 0.8 + 0.055 * np.minimum(distance, 24)
    np.fill_diagonal(transition, 0)
    prev = emission[0]
    back = np.zeros((n, p + 1), dtype=np.int16)
    for k in range(1, n):
        costs = transition.copy()
        costs[:, 1:] *= (1 - 0.55 * np.clip(onsets[k], 0, 1))[None, :]
        poss = prev[:, None] - costs
        back[k] = np.argmax(poss, axis=0)
        prev = emission[k] + np.max(poss, axis=0)
    path = np.empty(n, dtype=np.int16)
    path[-1] = np.argmax(prev)
    for k in range(n - 1, 0, -1):
        path[k - 1] = back[k, path[k]]
    changes = np.r_[0, np.flatnonzero(np.diff(path)) + 1, n]
    notes = []
    for first, last in zip(changes[:-1], changes[1:]):
        if path[first] == 0 or last - first < 4:
            continue
        pitch = int(path[first] - 1)
        f = frames[first:last, pitch]
        if np.mean(f) < floor + 0.015:
            continue
        peaks, _ = find_peaks(onsets[first:last, pitch], height=0.5, prominence=0.18, distance=5)
        cuts = [first] + [first + int(k) for k in peaks if k >= 4 and last - first - k >= 4] + [last]
        for start, end in zip(cuts[:-1], cuts[1:]):
            if end - start < 4:
                continue
            onset = float(np.max(onsets[max(0, start - 1) : min(n, start + 2), pitch]))
            notes.append(
                dict(
                    start_frame=int(start),
                    end_frame=int(end),
                    pitch=pitch + 21,
                    activation=float(np.mean(frames[start:end, pitch])),
                    onset=onset,
                    kind="rearticulation" if start != first else "pitch_change_or_entry",
                )
            )
    return notes


# ---------------------------------------------------------------- driver

def extract(audio: Path, work: Path, log=print) -> dict:
    """Return the evidence dict; cached as work/evidence.npz + evidence.json."""
    work.mkdir(parents=True, exist_ok=True)
    meta_path = work / "evidence.json"
    env_path = work / "evidence.npz"
    digest = sha256(audio)
    if meta_path.exists() and env_path.exists():
        meta = json.loads(meta_path.read_text())
        if meta.get("audio_sha256") == digest and meta.get("version") == 6:
            z = np.load(env_path)
            meta["envelopes"] = {k[4:]: z[k] for k in z.files if k.startswith("env_")}
            meta["rms"] = {k[4:]: z[k] for k in z.files if k.startswith("rms_")}
            return meta
    log(f"separating {audio.name}")
    raw_stems = separate(audio, work)
    mix = highpass(load_mono(audio))
    st = {n: highpass(load_mono(p)) for n, p in raw_stems.items()}
    n = min(len(mix), *(len(y) for y in st.values()))
    mix = mix[:n]
    lag = align_lag(mix, sum(y[:n] for y in st.values()))
    st = {k: roll(y[:n], lag) for k, y in st.items()}
    aligned = work / "aligned"
    aligned.mkdir(exist_ok=True)
    stems = {}
    for k, y in st.items():
        stems[k] = aligned / f"{k}.wav"
        sf.write(stems[k], y, SR)
    envelopes = drum_activations(st["drums"])
    envelopes["drums"] = linear_flux(st["drums"], 30, 11000)
    envelopes["mix"] = linear_flux(mix, 30, 11000)
    rms = {n: rms_env(y) for n, y in st.items()}
    rms["mix"] = rms_env(mix)
    notes = {}
    for name in ["vocals", "other", "bass"]:
        log(f"basic pitch {name}")
        bp = basic_pitch_frames(stems[name], name, work)
        t = frame_times(len(bp["note"]))
        idx = np.clip(np.round(t * ENV_FPS).astype(int), 0, len(rms["mix"]) - 1)
        ref = np.percentile(rms[name], 95) + 1e-9
        mref = np.percentile(rms["mix"], 95) + 1e-9
        ratio = rms[name][idx] / np.maximum(rms["mix"][idx], 1e-8)
        active = (rms[name][idx] > ref * 10 ** (-28 / 20)) & (ratio > 0.12) & (rms["mix"][idx] > mref * 10 ** (-45 / 20))
        active = binary_closing(active, structure=np.ones(5))
        lo, hi = PATH_RANGES[name]
        cache = work / f"path-{name}.json"
        key = sha256(work / f"bp-{name}.npz") + f":{lag}:{lo}:{hi}"
        if cache.exists() and json.loads(cache.read_text()).get("key") == key:
            raw = json.loads(cache.read_text())["notes"]
        else:
            raw = decode_path(bp["note"], bp["onset"], active, lo, hi, floor=0.34 if name == "vocals" else 0.36)
            cache.write_text(json.dumps(dict(key=key, notes=raw)))
        notes[name] = [
            dict(
                start=round(float(t[n["start_frame"]]), 4),
                end=round(float(t[min(n["end_frame"], len(t) - 1)]), 4),
                pitch=n["pitch"],
                activation=round(n["activation"], 3),
                onset=round(n["onset"], 3),
                kind=n["kind"],
            )
            for n in raw
        ]
    meta = dict(
        version=6,
        stem_lag_ms=round(lag / SR * 1000, 2),
        audio=str(audio),
        audio_sha256=digest,
        duration=len(mix) / SR,
        env_fps=ENV_FPS,
        stems={n: str(p) for n, p in stems.items()},
        notes=notes,
        methods=dict(
            stems="Demucs htdemucs, 20 Hz high-pass",
            drums="onsets from the drum-stem linear flux; labels from NMF kick/snare/hat activations (adaptive band templates)",
            alignment="stems rolled to the decoded mix by cross-correlation",
            pitched="Basic Pitch 0.4.0 ICASSP 2022 ONNX frames -> v5 monophonic path decoder",
            mix="full-mix linear spectral flux (sanity layer only)",
        ),
    )
    meta_path.write_text(json.dumps(meta, ensure_ascii=False))
    np.savez_compressed(
        env_path,
        **{f"env_{k}": v for k, v in envelopes.items()},
        **{f"rms_{k}": v for k, v in rms.items()},
    )
    meta["envelopes"] = envelopes
    meta["rms"] = rms
    return meta
