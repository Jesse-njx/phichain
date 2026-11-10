"""Build a Phrase Rhythm Record (PRR, XR1) from audio evidence and a grid.

Implements README sections 3-5: phrase grid (MF3, MF4, MG6, MG7), layer lines
(MR1, MR4), cells (MR2, MR3), readings with thinning and density (MH0, MH1,
MH4), articulation (MH2, MR5-MR7) and anchors (MH3). Rule numbers in comments
refer to README section 4.

The grid comes from a SAR (`grid_from_sar`) or from a plain grid config
(`grid_from_config`, used for corpus songs that have no SAR).
"""
from __future__ import annotations

import bisect
import json
import math
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from fractions import Fraction
from pathlib import Path

import numpy as np
from scipy.signal import find_peaks

DRUMS = ["kick", "snare", "hat"]
PITCHED = ["vocals", "other", "bass"]
LAYERS = DRUMS + PITCHED
CELL_PREFIX = {"kick": "K", "snare": "S", "hat": "H", "bass": "B", "vocals": "V", "other": "O"}
NOTE_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]

# Thresholds (README rules); kept together so the record can cite them.
PARAMS = dict(
    phrase_bars=4,
    attack_rel=0.20,  # rule 2: >= 20% of the layer's bar maximum
    accent_rel=0.60,  # rule 2: >= 60% of the bar maximum, or a downbeat
    presence_rel=0.15,  # tweak: bar maximum >= 15% of the layer's loud-bar level
    triplet_share=0.15,  # rule 1 (tweak: 5% fires on noise; uniform onsets give ~33%)
    thirtysecond_share=0.15,  # rule 1 (tweak: onset share instead of autocorrelation)
    subdiv_min_onsets=4,
    prominence_rel=0.15,  # tweak: peak prominence >= 15% of the bar maximum
    phase_strong_rel=0.5,  # layer phase alignment uses onsets >= 50% of bar max
    leak_margin=1.5,  # a snare/hat label needs 1.5x the kick's median leak
    explained_min=0.90,  # rule 1
    tol_floor_s=0.015,  # tweak: timing tolerance floor
    off_grid_max_per_bar=3,  # rule 3
    swing_min=0.10,  # rule 4, in slots
    sustain_min_slots=2,  # tweak: rule 8 floor (2 sixteenth slots and 120 ms)
    sustain_min_s=0.12,
    gesture_min=3,  # rule 9
    fill_min_diff=3,  # rule 7
)

THINNING = [
    (1, "drop_hats"),
    (2, "accents_only"),
    (3, "gesture_heads_only"),
    (4, "beats_and_anchors_only"),
]


def midi_name(m: int) -> str:
    return f"{NOTE_NAMES[m % 12]}{m // 12 - 1}"


def claim(value, source="measurement", status="measurement-only", evidence=None, note=None):
    out = {"value": value, "source": source, "status": status, "evidence": evidence or []}
    if note:
        out["note"] = note
    return out


# ---------------------------------------------------------------- grid input

@dataclass
class Segment:
    start_s: float
    end_s: float
    bpm: float | None  # None = free rhythm (MG4 without a pulse)
    anchor_s: float | None
    beats_per_bar: int
    id: str = ""

    @property
    def beat_s(self) -> float:
        return 60.0 / self.bpm


@dataclass
class Section:
    id: str
    start_s: float
    end_s: float
    function: str
    group: str | None
    lead_text: str
    climax: bool = False


@dataclass
class Grid:
    bpm: float
    offset_s: float
    segments: list[Segment]
    sections: list[Section]
    climax_s: float | None = None
    source: str = ""

    def sar_beat(self, t: float) -> float:
        return (t - self.offset_s) * self.bpm / 60.0


def parse_meter(text) -> int:
    if not text:
        return 4
    m = re.match(r"\s*(\d+)\s*/\s*(\d+)", str(text))
    return int(m.group(1)) if m else 4


def _val(x):
    return x.get("value") if isinstance(x, dict) and "value" in x else x


def grid_from_sar(sar: dict, duration: float, sar_path: str = "") -> Grid:
    g = sar.get("L0_identity_grid") or sar.get("MG") or {}
    bpm = float(_val(g["bpm"]))
    offset = float(_val(g["beat_zero_offset_seconds"]))
    meter = parse_meter(_val(g.get("meter")))
    segs = []
    ts = _val(g.get("tempo_segments"))
    if isinstance(ts, list) and ts:
        for s in ts:
            a, b = s["seconds"]
            b = duration if b is None else b
            sb = s.get("bpm")
            segs.append(
                Segment(a, b, float(sb) if sb else None, s.get("anchor_seconds"), parse_meter(s.get("meter")) if sb else meter, s.get("id", ""))
            )
    else:
        segs = [Segment(0.0, duration, bpm, offset, meter, "single")]
    form = sar.get("L1_form", {})
    lead_map = _val(sar.get("L3_lead_line", {}).get("lead_layer_by_section", {}))
    sections = []
    for i, s in enumerate(form.get("sections", [])):
        sid = s.get("id") or f"s{i:02d}"
        a, b = s["seconds"]
        b = duration if b is None else b
        func = _val(s.get("function_status")) or s.get("function") or ""
        lead = s.get("lead") or ""
        if isinstance(lead_map, dict) and sid in lead_map:
            lead = str(lead_map[sid])
        if s.get("vocal") is True and "voc" not in lead and "voice" not in lead:
            lead = "voice; " + lead
        sections.append(Section(sid, float(a), float(b), str(func), s.get("group"), str(lead)))
    climax = None
    cc = _val(sar.get("L5_energy", {}).get("climax_candidates"))
    if isinstance(cc, list) and cc and isinstance(cc[0], (list, tuple)):
        climax = offset + float(cc[0][0]) * 60.0 / bpm
    return Grid(bpm, offset, segs, sections, climax, source=sar_path or "SAR")


def grid_from_config(cfg: dict, duration: float) -> Grid:
    """Plain grid: {"bpm", "offset_seconds", "meter", "sections": [{"id", "beats":[a,b], "function", "group", "lead"}]}"""
    bpm = float(cfg["bpm"])
    off = float(cfg.get("offset_seconds", 0.0))
    meter = parse_meter(cfg.get("meter", "4/4"))
    b2s = lambda b: off + b * 60.0 / bpm
    secs = []
    for i, s in enumerate(cfg.get("sections", [])):
        a, b = s["beats"]
        secs.append(
            Section(s.get("id", f"s{i:02d}"), b2s(a), duration if b is None else b2s(b), s.get("function", ""), s.get("group"), s.get("lead", ""))
        )
    if not secs:
        secs = [Section("all", 0.0, duration, "unknown", None, "")]
    return Grid(bpm, off, [Segment(0.0, duration, bpm, off, meter, "single")], secs, None, source="grid config")


def lead_stems(text: str) -> tuple[list[str], str]:
    """Map an ML3 lead description to stems. Returns (stems, status)."""
    t = text.lower()
    if "contradicted" in t:
        return ["vocals", "other"], "contradicted"
    if "voice" in t or "vocal" in t:
        return ["vocals"], "from-sar"
    if not t.strip() or t.strip().startswith("none"):
        return [], "measure"
    if "bass" in t and not any(k in t for k in ("synth", "pad", "guitar", "piano", "lead", "other")):
        return ["bass"], "from-sar"
    return ["other"], "from-sar"


# ---------------------------------------------------------------- bars and phrases

@dataclass
class Bar:
    idx: int
    seg: Segment
    start_s: float
    end_s: float
    section: Section | None = None
    phrase: str = ""

    @property
    def beat_s(self):
        return self.seg.beat_s

    @property
    def bpb(self):
        return self.seg.beats_per_bar


def make_bars(grid: Grid, duration: float) -> list[Bar]:
    bars = []
    for seg in grid.segments:
        if seg.bpm is None:
            continue
        L = seg.beat_s * seg.beats_per_bar
        anchor = seg.anchor_s if seg.anchor_s is not None else grid.offset_s
        k0 = math.ceil((seg.start_s - anchor) / L - 0.02)
        k = k0
        while True:
            a = anchor + k * L
            if a >= min(seg.end_s, duration) - 0.5 * seg.beat_s:
                break
            if a >= -0.02:
                bars.append(Bar(len(bars), seg, a, a + L))
            k += 1
    for b in bars:
        mid = b.start_s + 0.01
        for s in grid.sections:
            if s.start_s - 0.5 * b.beat_s <= mid < s.end_s - 0.5 * b.beat_s:
                b.section = s
                break
    bars = [b for b in bars if b.section is not None]  # outside every section
    for i, b in enumerate(bars):
        b.idx = i
    return bars


def make_phrases(grid: Grid, bars: list[Bar], phrase_bars: int):
    """Phrases (MF3): runs of `phrase_bars` bars inside one section and one
    grid segment, starting at the first bar of the section."""
    phrases = []
    run: list[Bar] = []

    def flush():
        for i in range(0, len(run), phrase_bars):
            chunk = run[i : i + phrase_bars]
            pid = f"P{len(phrases) + 1:02d}"
            for b in chunk:
                b.phrase = pid
            phrases.append(dict(id=pid, bars=chunk, short=len(chunk) < phrase_bars, free=False))

    for b in bars:
        if run and (b.section is not run[-1].section or b.seg is not run[-1].seg):
            flush()
            run = []
        run.append(b)
    if run:
        flush()
    # free-rhythm segments become one free phrase per section overlap
    for seg in grid.segments:
        if seg.bpm is not None:
            continue
        for s in grid.sections:
            a, z = max(seg.start_s, s.start_s), min(seg.end_s, s.end_s)
            if z - a > 0.5:
                phrases.append(dict(id="", bars=[], short=False, free=True, seconds=(a, z), section=s))
    phrases.sort(key=lambda p: p["bars"][0].start_s if p["bars"] else p["seconds"][0])
    for i, p in enumerate(phrases):
        p["id"] = f"P{i + 1:02d}"
        for b in p["bars"]:
            b.phrase = p["id"]
    return phrases


# ---------------------------------------------------------------- slot sets

def slot_fracs(subdivs: list[Fraction]) -> list[Fraction]:
    fr = set()
    for d in subdivs:
        k = 0
        while k * d < 1:
            fr.add(k * d)
            k += 1
    return sorted(fr)


def nominal(subdivs) -> Fraction:
    return min(subdivs)


def tolerance_beats(subdivs, beat_s) -> float:
    fr = slot_fracs(subdivs) + [Fraction(1)]
    min_gap = float(min(b - a for a, b in zip(fr[:-1], fr[1:])))
    tol = max(0.25 * float(nominal(subdivs)), PARAMS["tol_floor_s"] / beat_s)
    return min(tol, 0.45 * min_gap)


def _near(frac, points, w):
    return (np.abs(frac[:, None] - np.asarray(points)[None, :]) <= w).any(axis=1)


def choose_slot_set(onsets_by_layer: dict[str, list[float]]) -> tuple[list[Fraction], dict]:
    """Rule 1, with a control test (tweak). Onsets are beat positions.

    Add 1/6 (triplets, sextuplets) when a layer's onsets near the triplet-only
    positions (1/6, 1/3, 2/3, 5/6 +-1/48 beat) are >= 15% of its onsets, >= 4,
    and at least twice the onsets near equally wide control positions that
    are on neither grid (1/12, 5/12, 7/12, 11/12). Add 1/8 (32nds) for a drum
    layer by the same test on odd 32nds (+-1/64) against the odd sixty-fourths
    between them (1/16, 3/16, ..., half weight). The README's bare 5% share fires on scattered
    detector onsets: uniform onsets put ~33% near a triplet slot."""
    subdivs = [Fraction(1, 4)]
    trip_layers, t32_layers, detail = [], [], {}
    trip_pts = [1 / 6, 1 / 3, 2 / 3, 5 / 6]
    trip_ctl = [1 / 12, 5 / 12, 7 / 12, 11 / 12]
    odd32 = [1 / 8, 3 / 8, 5 / 8, 7 / 8]
    ctl32 = [1 / 16, 3 / 16, 5 / 16, 7 / 16, 9 / 16, 11 / 16, 13 / 16, 15 / 16]
    for layer, pos in onsets_by_layer.items():
        if len(pos) < 4:
            continue
        frac = np.mod(np.asarray(pos, float), 1.0)
        frac = np.where(frac > 1 - 1 / 48, frac - 1, frac)
        nt = int(_near(frac, trip_pts, 1 / 48).sum())
        nc = int(_near(frac, trip_ctl, 1 / 48).sum())
        detail[layer] = dict(onsets=len(frac), triplet=nt, triplet_control=nc)
        if nt >= PARAMS["subdiv_min_onsets"] and nt >= PARAMS["triplet_share"] * len(frac) and nt >= 2 * nc:
            trip_layers.append(layer)
        if layer in DRUMS:
            n32 = int(_near(frac, odd32, 1 / 64).sum())
            c32 = int(_near(frac, ctl32, 1 / 64).sum()) / 2  # twice as many control points
            detail[layer].update(thirtysecond=n32, thirtysecond_control=c32)
            if n32 >= PARAMS["subdiv_min_onsets"] and n32 >= PARAMS["thirtysecond_share"] * len(frac) and n32 >= 2 * c32:
                t32_layers.append(layer)
    if trip_layers:
        subdivs.append(Fraction(1, 6))
    if t32_layers:
        subdivs.append(Fraction(1, 8))
    return subdivs, {"triplet_layers": trip_layers, "thirtysecond_layers": t32_layers, "counts": detail}


# ---------------------------------------------------------------- the builder

@dataclass
class PhraseCtx:
    id: str
    bars: list[Bar]
    section: Section
    subdivs: list[Fraction]
    fracs: list[Fraction]
    slots_per_bar: int
    tol: float  # beats
    swing8: float = 0.0  # beats added to off-beat eighths
    swing16: float = 0.0  # beats added to off-beat sixteenths
    lines: dict = field(default_factory=dict)  # layer -> list[slot dict or None] flat over phrase
    slot_pos: list = field(default_factory=list)  # (bar_i, idx, beat_in_bar)
    slot_time: list = field(default_factory=list)

    def build_slots(self):
        self.slot_pos, self.slot_time = [], []
        for bi, b in enumerate(self.bars):
            i = 0
            for beat in range(b.bpb):
                for f in self.fracs:
                    pos = beat + float(f)
                    shift = 0.0
                    if f == Fraction(1, 2):
                        shift = self.swing8
                    elif f in (Fraction(1, 4), Fraction(3, 4)) and Fraction(1, 6) not in self.subdivs:
                        shift = self.swing16
                    self.slot_pos.append((bi, i, pos))
                    self.slot_time.append(b.start_s + (pos + shift) * b.beat_s)
                    i += 1
        self.slots_per_bar = len(self.fracs) * self.bars[0].bpb

    def slot_name(self, k):
        bi, i, _ = self.slot_pos[k]
        return f"b{bi + 1}.{i}"

    def nearest(self, t) -> tuple[int, float]:
        """Nearest slot index and its distance in beats."""
        k = bisect.bisect_left(self.slot_time, t)
        best = None
        for j in (k - 1, k):
            if 0 <= j < len(self.slot_time):
                d = abs(self.slot_time[j] - t)
                if best is None or d < best[1]:
                    best = (j, d)
        if best is None:
            return -1, 1e9
        return best[0], best[1] / self.bars[0].beat_s


class Builder:
    def __init__(self, ev: dict, grid: Grid, corpus_prior: dict | None = None, phrase_bars: int | None = None, lead_override=None, latency=None, latency_source=None, fit_phase=False):
        self.ev = ev
        self.grid = grid
        self.fps = ev["env_fps"]
        self.env = ev["envelopes"]
        self.rms = ev["rms"]
        self.notes = {k: list(v) for k, v in ev["notes"].items()}
        self.duration = ev["duration"]
        self.prior = corpus_prior
        self.phrase_bars = phrase_bars or PARAMS["phrase_bars"]
        self.lead_override = lead_override  # callable(phrase ctx) -> stems, for corpus runs
        self.latency = latency or {}
        self.latency_source = latency_source
        self.fit_phase = fit_phase
        self.bars = make_bars(grid, self.duration)
        self.presence = {}
        self.drum_peaks = {}
        sixteenth = 15.0 / grid.bpm
        # peaks at least half a sixteenth apart (tweak: flux gives double
        # peaks; a 32nd roll above 150 BPM is read as sixteenths)
        dist = max(1, int(max(0.03, 0.5 * sixteenth) * self.fps))
        e = self.env["mix"]
        pk, props = find_peaks(e, distance=dist, prominence=1e-9)
        self.drum_peaks["mix"] = (pk / self.fps, e[pk], props["prominences"])
        self.drum_label_info = self.label_drum_onsets(dist)
        self.layer_phase = self.align_layers()
        for layer in DRUMS:
            maxima = [self.bar_max(layer, b) for b in self.bars]
            top = np.sort(maxima)[-max(1, len(maxima) // 4) :] if maxima else [1.0]
            self.presence[layer] = float(np.median(top)) if len(top) else 1.0

    # ---- evidence access
    def frames(self, a, z, n):
        return max(0, int(a * self.fps)), min(n, int(math.ceil(z * self.fps)) + 1)

    def bar_max(self, layer, bar: Bar) -> float:
        """Largest onset value of a drum layer (or the mix) in a bar."""
        t, v, _ = self.drum_peaks[layer]
        i, j = np.searchsorted(t, bar.start_s - 0.03), np.searchsorted(t, bar.end_s - 0.03)
        return float(v[i:j].max()) if j > i else 0.0

    def onsets_in(self, layer, a, z, rel=None, ref=None):
        """Drum or mix onset peaks in [a, z) with value >= rel * ref."""
        t, v, pr = self.drum_peaks[layer]
        i, j = np.searchsorted(t, a), np.searchsorted(t, z)
        t, v, pr = t[i:j], v[i:j], pr[i:j]
        if rel is not None:
            keep = (v >= rel * ref) & (pr >= PARAMS["prominence_rel"] * ref)
            t, v = t[keep], v[keep]
        return t, v

    def label_drum_onsets(self, dist):
        """Drum onsets are timed on the broadband drum-stem flux and labelled
        by the rise of each NMF component around them (tweak to rule 5). A
        kick leaks into the snare and hat components (its click); the leak
        ratio is measured on the song's strongest kick onsets and subtracted,
        so a snare label needs snare energy beyond what the kick explains."""
        e = self.env["drums"]
        pk, props = find_peaks(e, distance=dist, prominence=1e-9)
        n = len(e)
        rise = {}
        for layer in DRUMS:
            a = self.env[f"act_{layer}"]
            r = np.empty(len(pk), np.float32)
            for i, p in enumerate(pk):
                # rise from just before the onset to 30 ms after it (the kick's
                # sub-bass needs ~25 ms); a wider window lets a hat onset just
                # before a kick steal the kick's rise
                hi = a[max(0, p - 2) : min(n, p + 7)].max()
                lo = a[max(0, p - 6) : min(n, p + 1)].min()
                r[i] = max(0.0, hi - lo)
            rise[layer] = r
        k = rise["kick"]
        strong_k = k >= np.percentile(k, 75) if len(k) else np.zeros(0, bool)
        info = {}
        if strong_k.sum() >= 8:
            r_sk = float(np.median(rise["snare"][strong_k] / np.maximum(k[strong_k], 1e-9)))
            r_hk = float(np.median(rise["hat"][strong_k] / np.maximum(k[strong_k], 1e-9)))
        else:
            r_sk = r_hk = 0.0
        m = PARAMS["leak_margin"]
        snare = np.maximum(0.0, rise["snare"] - m * r_sk * k)
        pos = snare > 0
        strong_s = pos & (snare >= np.percentile(snare[pos], 75)) & (k < np.percentile(k, 50)) if pos.sum() >= 8 else np.zeros(len(k), bool)
        r_hs = float(np.median(rise["hat"][strong_s]) / max(np.median(snare[strong_s]), 1e-9)) if strong_s.sum() >= 8 else 0.0
        hat = np.maximum(0.0, rise["hat"] - m * (r_hk * k + r_hs * snare))
        t = pk / self.fps
        for layer, v in (("kick", k), ("snare", snare), ("hat", hat)):
            keep = v > 0
            self.drum_peaks[layer] = (t[keep], v[keep], v[keep])
        info = dict(onsets=int(len(pk)), leak_snare_per_kick=round(r_sk, 3), leak_hat_per_kick=round(r_hk, 3), leak_hat_per_snare=round(r_hs, 3))
        return info

    def notes_in(self, layer, a, z):
        return [n for n in self.notes[layer] if a <= n["start"] < z]

    def _strong_times(self, layer, b):
        if layer in DRUMS or layer == "mix":
            t, v, pr = self.drum_peaks[layer]
            i, j = np.searchsorted(t, b.start_s - 0.05), np.searchsorted(t, b.end_s - 0.05)
            if j <= i:
                return np.array([])
            M = v[i:j].max()
            return t[i:j][(v[i:j] >= PARAMS["phase_strong_rel"] * M) & (pr[i:j] >= PARAMS["prominence_rel"] * M)]
        return np.array([n["start"] for n in self.notes[layer] if b.start_s - 0.05 <= n["start"] < b.end_s - 0.05])

    def _phase(self, layer, period_beats):
        """Circular mean deviation (seconds) of a layer's strong onsets from a
        grid of `period_beats`, and the resultant length (0..1)."""
        z, n = [], 0
        for b in self.bars:
            P = period_beats * b.beat_s
            for x in self._strong_times(layer, b):
                z.append(np.exp(2j * np.pi * (x - b.start_s) / P))
        if len(z) < 16:
            return 0.0, 0.0, len(z)
        m = np.mean(z)
        P = period_beats * (self.bars[0].beat_s if self.bars else 0.5)
        return float(np.angle(m) / (2 * np.pi) * P), float(abs(m)), len(z)

    def _shift(self, layer, d):
        if layer in DRUMS or layer == "mix":
            t, v, pr = self.drum_peaks[layer]
            self.drum_peaks[layer] = (t - d, v, pr)
        else:
            self.notes[layer] = [dict(n, start=round(n["start"] - d, 4), end=round(n["end"] - d, 4)) for n in self.notes[layer]]

    def align_layers(self):
        """Phase alignment (tweak, README rule 2a).

        1. Detector latency: each layer detector has a constant latency (the
           NMF kick's sub-bass builds up after the beater click; Basic Pitch
           frames are 11.6 ms). The constants are measured on the corpus, where
           the official chart grid is ground truth (calibrate.py ->
           layer-latency.json), and removed from every song.
        2. Grid phase check: the circular mean of the latency-corrected drum
           onsets on the sixteenth grid. A large value means the grid's beat
           zero is off (NightTheater's SAR beat zero was measured on MP3 stems
           that lag the decoded mix by 25 ms). It is always reported. With
           fit_phase="auto" it is applied when it exceeds 10 ms and the layers
           agree on it; the SAR should still be corrected
           upstream. ("Agree": every layer with a clear sixteenth phase,
           resultant >= 0.5, lies within 12 ms.) Calibration runs use fit_phase=False (the chart grid is
           the truth there).
        Both values are recorded."""
        out = {"latency_source": self.latency_source}
        for layer in DRUMS + PITCHED:
            d = self.latency.get(layer, 0.0)
            if d:
                self._shift(layer, d)
            out[layer] = dict(latency_ms=round(d * 1000, 1))
        if not self.bars:
            return out
        zs, clear = [], []
        for layer in DRUMS + PITCHED:
            d, R, n = self._phase(layer, 0.25)
            out[layer].update(residual_ms=round(d * 1000, 1), resultant=round(R, 2), n=n)
            if n >= 16 and layer in DRUMS:
                zs.append((d, R * n))
            if n >= 16 and R >= 0.5:
                clear.append(d)
        kd, kR, kn = self._phase("kick", 1.0)
        out["kick"].update(beat_phase_ms=round(kd * 1000, 1), beat_resultant=round(kR, 2))
        if zs:
            six = self.bars[0].beat_s / 4
            w = sum(x[1] for x in zs) or 1.0
            g, basis = sum(d * wt for d, wt in zs) / w, "drum sixteenth phase"
            if kn >= 16 and kR >= 0.5:
                # sixteenth-period phases wrap at half a sixteenth; the kick's
                # phase on the beat period picks the wrap (off-beat kicks skew
                # its value, so it is not used as the estimate itself)
                g = min((g + k * six for k in (-1, 0, 1)), key=lambda x: abs(x - kd))
                basis = "drum sixteenth phase, wrap chosen by the kick's beat phase"
            circ = lambda d: abs((d - g + six / 2) % six - six / 2)
            # agreement: every clearly periodic layer (resultant >= 0.5) lies
            # within 12 ms of g modulo a sixteenth
            agree = len(clear) >= 2 and max(circ(d) for d in clear) <= 0.012
            if "kick" not in basis and abs(g) > 0.3 * six:
                agree = False  # ambiguous near half a sixteenth
            apply = self.fit_phase is True or (self.fit_phase == "auto" and abs(g) > 0.010 and agree)
            out["grid_phase"] = dict(shift_ms=round(g * 1000, 1), basis=basis, layers_agree=agree, mode=self.fit_phase, applied=bool(apply))
            if apply:
                for layer in DRUMS + PITCHED + ["mix"]:
                    self._shift(layer, g)
        return out

    # ---- phrase context
    def phrase_ctx(self, p) -> PhraseCtx:
        bars = p["bars"]
        onsets = defaultdict(list)
        for b in bars:
            for layer in DRUMS:
                m = self.bar_max(layer, b)
                if m < PARAMS["presence_rel"] * self.presence[layer]:
                    continue
                t, _ = self.onsets_in(layer, b.start_s - 0.03, b.end_s - 0.03, PARAMS["attack_rel"], m)
                onsets[layer] += list((t - b.start_s) / b.beat_s)
            for layer in PITCHED:
                for n in self.notes_in(layer, b.start_s - 0.03, b.end_s - 0.03):
                    onsets[layer].append((n["start"] - b.start_s) / b.beat_s)
        subdivs, why = choose_slot_set(onsets)
        fracs = slot_fracs(subdivs)
        ctx = PhraseCtx(p["id"], bars, bars[0].section, subdivs, fracs, 0, tolerance_beats(subdivs, bars[0].beat_s))
        ctx.onsets = onsets
        ctx.slot_why = why
        # swing (rule 4): off-beat displacement relative to on-beat displacement
        if Fraction(1, 6) not in subdivs:
            sw = self.estimate_swing(onsets.get("hat", []) + self._lead_onsets(onsets))
            ctx.swing_info = sw
            if sw["consistent"]:
                ctx.swing8 = sw["eighth_shift_beats"]
                ctx.swing16 = sw["sixteenth_shift_beats"]
        else:
            ctx.swing_info = {"consistent": False, "note": "triplet slot set: swing not estimated"}
        ctx.build_slots()
        return ctx

    def _lead_onsets(self, onsets):
        return onsets.get("vocals", []) + onsets.get("other", [])

    @staticmethod
    def estimate_swing(pos):
        pos = np.asarray(pos)
        out = {"consistent": False, "eighth_shift_beats": 0.0, "sixteenth_shift_beats": 0.0}
        if len(pos) < 8:
            out["note"] = "too few onsets"
            return out
        frac = np.mod(pos + 0.125, 1.0) - 0.125  # in [-0.125, 0.875)
        on = frac[np.abs(frac) < 0.0625]
        base = float(np.median(on)) if len(on) >= 3 else 0.0
        e8 = frac[np.abs(frac - 0.5) < 0.125] - 0.5 - base
        s16 = np.concatenate([frac[np.abs(frac - 0.25) < 0.1] - 0.25, frac[np.abs(frac - 0.75) < 0.1] - 0.75]) - base
        res = {}
        for name, d in (("eighth", e8), ("sixteenth", s16)):
            d_slots = d / 0.25
            ok = len(d) >= 6 and abs(np.mean(d_slots)) > PARAMS["swing_min"] and (np.mean(np.sign(d_slots) == np.sign(np.mean(d_slots))) >= 0.7)
            res[name] = (ok, float(np.mean(d)) if len(d) else 0.0, len(d))
        out["eighth_shift_beats"] = round(res["eighth"][1], 4) if res["eighth"][0] else 0.0
        out["sixteenth_shift_beats"] = round(res["sixteenth"][1], 4) if res["sixteenth"][0] else 0.0
        out["consistent"] = bool(res["eighth"][0] or res["sixteenth"][0])
        out["n"] = {"eighth": res["eighth"][2], "sixteenth": res["sixteenth"][2]}
        s = out["eighth_shift_beats"]
        out["swing_ratio"] = round((0.5 + s) / (0.5 - s), 3) if out["consistent"] else 1.0
        return out

    # ---- layer lines (MR1, MR4)
    def drum_line(self, ctx: PhraseCtx, layer):
        n = len(ctx.slot_time)
        line = [None] * n
        off = []
        present = []
        for bi, b in enumerate(ctx.bars):
            m = self.bar_max(layer, b)
            pres = m >= PARAMS["presence_rel"] * self.presence[layer]
            present.append(pres)
            if not pres:
                continue
            t, v = self.onsets_in(layer, b.start_s - 0.03, b.end_s - 0.03, PARAMS["attack_rel"], m)
            for tt, vv in zip(t, v):
                k, d = ctx.nearest(tt)
                if d <= ctx.tol and ctx.slot_pos[k][0] == bi:
                    s = vv / m
                    downbeat = ctx.slot_pos[k][1] == 0
                    cur = line[k]
                    if cur is None or s > cur["s"]:
                        line[k] = {"s": round(float(s), 2), "acc": bool(s >= PARAMS["accent_rel"] or downbeat), "t": float(tt)}
                elif d > ctx.tol:
                    off.append({"layer": layer, "seconds": round(float(tt), 4), "bar": bi + 1, "strength": round(float(vv / m), 2)})
        return line, off, present

    def pitched_line(self, ctx: PhraseCtx, layer):
        n = len(ctx.slot_time)
        line = [None] * n
        off = []
        a, z = ctx.bars[0].start_s - 0.03, ctx.bars[-1].end_s - 0.03
        notes = self.notes_in(layer, a, z)
        bar_max = defaultdict(float)
        for nt in notes:
            bi = max(0, min(len(ctx.bars) - 1, int((nt["start"] - ctx.bars[0].start_s + 0.03) // (ctx.bars[0].end_s - ctx.bars[0].start_s))))
            bar_max[bi] = max(bar_max[bi], max(nt["activation"], nt["onset"]))
        for nt in notes:
            k, d = ctx.nearest(nt["start"])
            if d > ctx.tol:
                off.append({"layer": layer, "seconds": nt["start"], "pitch": midi_name(nt["pitch"])})
                continue
            bi = ctx.slot_pos[k][0]
            s = max(nt["activation"], nt["onset"]) / max(bar_max[bi], 1e-6)
            # quantized end: nearest slot boundary to the note end (may leave the phrase)
            ke, _ = ctx.nearest(nt["end"])
            if nt["end"] > ctx.slot_time[-1] + 0.5 * (ctx.slot_time[-1] - ctx.slot_time[-2]):
                ke = n
                clipped = True
            else:
                clipped = False
            ke = max(ke, k + 1)
            cur = line[k]
            if cur is not None and cur["s"] >= s:
                continue
            line[k] = {
                "s": round(float(min(1.0, s)), 2),
                "acc": bool(s >= PARAMS["accent_rel"] or ctx.slot_pos[k][1] == 0),
                "t": nt["start"],
                "pitch": nt["pitch"],
                "end_slot": ke,
                "end_s": nt["end"],
                "clipped": clipped,
                "kind": nt["kind"],
            }
        # resolve lengths against the next attack (monophonic path, but quantization can collide)
        ks = [k for k in range(n) if line[k]]
        for i, k in enumerate(ks):
            nxt = ks[i + 1] if i + 1 < len(ks) else n
            e = min(line[k]["end_slot"], nxt)
            line[k]["len"] = e - k
            if line[k]["end_slot"] >= nxt and nxt < n:
                same = line[nxt]["pitch"] == line[k]["pitch"]
                line[k]["release"] = "next_attack" if same else "pitch_change"
            elif line[k]["clipped"] or e >= n:
                line[k]["release"] = "phrase_end"
            else:
                line[k]["release"] = "rest"
        return line, off

    def strings(self, ctx, line, sustain=False):
        """Bar strings: X accent, x attack, ~ sustain continues, . rest."""
        n = len(line)
        chars = ["."] * n
        for k in range(n):
            if line[k]:
                chars[k] = "X" if line[k]["acc"] else "x"
                if sustain:
                    for j in range(k + 1, min(n, k + line[k].get("len", 1))):
                        chars[j] = "~"
        spb = ctx.slots_per_bar
        return ["".join(chars[i * spb : (i + 1) * spb]) for i in range(len(ctx.bars))]

    # ---- the whole record
    def build(self, song: str, audio_sha: str, sar_path: str = "", reference_heads=None) -> dict:
        phrases = make_phrases(self.grid, self.bars, self.phrase_bars)
        rec_phrases = []
        ctxs = {}
        # energy terciles per phrase (for the corpus prior key)
        mix_db = {}
        for p in phrases:
            a, z = (p["bars"][0].start_s, p["bars"][-1].end_s) if p["bars"] else p["seconds"]
            i, j = self.frames(a, z, len(self.rms["mix"]))
            mix_db[p["id"]] = float(20 * np.log10(np.mean(self.rms["mix"][i:j]) + 1e-9)) if j > i else -120
        order = sorted(mix_db, key=mix_db.get)
        terc = {pid: ("low", "mid", "high")[min(2, 3 * r // max(1, len(order)))] for r, pid in enumerate(order)}

        for p in phrases:
            if p["free"]:
                rec_phrases.append(self.free_phrase(p, terc))
                continue
            ctx = self.phrase_ctx(p)
            ctxs[p["id"]] = ctx
            rec_phrases.append(self.phrase_record(ctx, p, terc[p["id"]], mix_db[p["id"]]))

        cells, fills, breaks, dominants, dom_changes = self.cells(rec_phrases)
        # anchors need fills and breaks; readings need anchors
        for pr in rec_phrases:
            if pr.get("free_rhythm"):
                continue
            ctx = ctxs[pr["id"]]
            pr["MH3_anchors"] = self.anchors(ctx, pr, rec_phrases, fills, breaks)
            pr["MH0_readings"] = self.readings(ctx, pr)
        self.recurrence(rec_phrases)
        record = dict(
            schema="phrase-rhythm-record/0.1",
            song=song,
            audio=self.ev["audio"],
            audio_sha256=audio_sha,
            sar=sar_path,
            review_status="not reviewed by the user; every claim is measurement-only",
            params=PARAMS,
            grid=dict(
                source=self.grid.source,
                bpm=self.grid.bpm,
                offset_seconds=self.grid.offset_s,
                segments=[dict(id=s.id, seconds=[round(s.start_s, 3), round(s.end_s, 3)], bpm=s.bpm, anchor_seconds=s.anchor_s, beats_per_bar=s.beats_per_bar, free_rhythm=s.bpm is None) for s in self.grid.segments],
                note="beat values use the SAR config grid; seconds are authoritative (macro rule 12)",
            ),
            layer_phase_alignment=self.layer_phase,
            drum_labelling=self.drum_label_info,
            grid_check=self.grid_check(),
            stem_lag_ms=self.ev.get("stem_lag_ms"),
            layers={
                "kick": "drum-stem flux onsets labelled by the NMF kick component rise",
                "snare": "drum-stem flux onsets labelled by the NMF snare component rise beyond the kick's leak",
                "hat": "drum-stem flux onsets labelled by the NMF hat component rise beyond kick and snare leak",
                "bass": "bass stem, Basic Pitch -> monophonic path",
                "vocals": "vocals stem, Basic Pitch -> v5 monophonic path",
                "other": "other stem, Basic Pitch -> v5 monophonic path",
                "mix": "full-mix flux, sanity only",
            },
            MF4_bars=[
                dict(bar=b.idx + 1, seconds=[round(b.start_s, 4), round(b.end_s, 4)], beat=round(self.grid.sar_beat(b.start_s), 3), section=b.section.id if b.section else None, phrase=b.phrase)
                for b in self.bars
            ],
            phrases=rec_phrases,
            MR2_cells=cells,
            MR3_fills_and_breaks=dict(fills=fills, breaks=breaks),
            dominant_cells=dominants,
            dominant_changes_inside_sections=dom_changes,
        )
        return record

    def grid_check(self):
        g = self.layer_phase.get("grid_phase")
        if not g:
            return dict(status="no drums to check against")
        dev = g["shift_ms"]
        return dict(
            grid_phase_ms=dev,
            applied=g["applied"],
            status="ok" if abs(dev) <= 10 else "check",
            note=None if abs(dev) <= 10 else f"latency-corrected drum onsets sit {dev:+.0f} ms from the grid's sixteenths: the grid's beat zero is probably off by that much (correct the SAR upstream)" + ("; applied (fit_phase)" if g["applied"] else "; not applied"),
        )

    def free_phrase(self, p, terc):
        a, z = p["seconds"]
        raw = {}
        for layer in DRUMS:
            t, v = self.onsets_in(layer, a, z)
            if len(v):
                m = v.max()
                keep = v >= PARAMS["attack_rel"] * m
                raw[layer] = [round(float(x), 4) for x in t[keep]]
        for layer in PITCHED:
            raw[layer] = [dict(seconds=n["start"], end=n["end"], pitch=midi_name(n["pitch"])) for n in self.notes_in(layer, a, z)]
        return dict(id=p["id"], section=p["section"].id, function=p["section"].function, seconds=[round(a, 3), round(z, 3)], free_rhythm=True, energy_tercile=terc[p["id"]], raw_events=raw, MH0_readings=[], note="MG4 free-rhythm span: layer lines replaced by raw events (rule 3)")

    def phrase_record(self, ctx: PhraseCtx, p, tercile, mix_db):
        sec = ctx.section
        lines, offs, strings, present = {}, [], {}, {}
        for layer in DRUMS:
            line, off, pres = self.drum_line(ctx, layer)
            lines[layer], present[layer] = line, pres
            offs += off
            strings[layer] = self.strings(ctx, line)
        for layer in PITCHED:
            line, off = self.pitched_line(ctx, layer)
            lines[layer] = line
            offs += off
            strings[layer] = self.strings(ctx, line, sustain=True)
        ctx.lines = lines
        # explained share (rule 1): onsets within tolerance of a slot
        tot = expl = 0
        for layer, pos in ctx.onsets.items():
            for x in pos:
                tot += 1
                frac = x % 1.0
                d = min(abs(frac - float(f)) for f in ctx.fracs + [Fraction(1)])
                expl += d <= ctx.tol
        share = expl / tot if tot else 1.0
        # off-grid per bar (rule 3)
        # rule 3 counts drum onsets only (tweak): sung and Basic Pitch onsets
        # are loose by nature and would flag almost every vocal bar
        offs_per_bar = Counter(o.get("bar") or self._bar_of(ctx, o["seconds"]) for o in offs if o["layer"] in DRUMS)
        # mix sanity
        unexplained = []
        for bi, b in enumerate(ctx.bars):
            m = self.bar_max("mix", b)
            t, v = self.onsets_in("mix", b.start_s - 0.03, b.end_s - 0.03, 0.5, m)
            for tt in t:
                k, d = ctx.nearest(tt)
                if not any(lines[l][k] for l in LAYERS) or d > ctx.tol:
                    unexplained.append(round(float(tt), 4))
        # lead (ML3)
        stems, lead_status = lead_stems(sec.lead_text)
        if self.lead_override:
            stems, lead_status = self.lead_override(ctx, lines)
        if not stems:
            v = sum(1 for k in range(len(lines["vocals"])) if lines["vocals"][k])
            o = sum(1 for k in range(len(lines["other"])) if lines["other"][k])
            stems, lead_status = (["vocals"] if v >= max(4, 0.5 * o) else ["other"]), "measured"
        ctx.lead = stems
        bars_out = {}
        for layer in LAYERS:
            rows = []
            for bi, b in enumerate(ctx.bars):
                spb = ctx.slots_per_bar
                seg = lines[layer][bi * spb : (bi + 1) * spb]
                row = dict(bar=b.idx + 1, string=strings[layer][bi], strength=[x["s"] if x else 0 for x in seg])
                if layer in PITCHED:
                    row["pitches"] = [midi_name(x["pitch"]) for x in seg if x]
                if layer in DRUMS and not present[layer][bi]:
                    row["present"] = False
                if offs_per_bar.get(bi + 1, 0) > PARAMS["off_grid_max_per_bar"]:
                    row["status"] = "contradicted"
                rows.append(row)
            bars_out[layer] = dict(bars=rows, attacks=sum(1 for x in lines[layer] if x))
        sustains = self.sustains(ctx)
        gestures = self.gestures(ctx)
        simult = self.simultaneities(ctx)
        a, z = ctx.bars[0].start_s, ctx.bars[-1].end_s
        return dict(
            id=ctx.id,
            section=sec.id,
            function=sec.function,
            group=sec.group,
            energy_tercile=tercile,
            mix_db=round(mix_db, 1),
            bars=[b.idx + 1 for b in ctx.bars],
            seconds=[round(a, 4), round(z, 4)],
            beats=[round(self.grid.sar_beat(a), 3), round(self.grid.sar_beat(z), 3)],
            short=p["short"],
            section_start=ctx.bars[0].start_s - sec.start_s < 0.5 * ctx.bars[0].beat_s and ctx.bars[0].section is sec and (ctx.bars[0].idx == 0 or self.bars[ctx.bars[0].idx - 1].section is not sec),
            free_rhythm=False,
            MG6_slot_set=dict(
                subdivisions=[str(d) for d in ctx.subdivs],
                slots_per_bar=ctx.slots_per_bar,
                explained_share=round(share, 3),
                flag="below 90%: check grid before use" if share < PARAMS["explained_min"] else None,
                tolerance_ms=round(ctx.tol * ctx.bars[0].beat_s * 1000, 1),
                why=ctx.slot_why,
            ),
            MG7_swing=ctx.swing_info,
            lead=claim(stems, status="contradicted" if lead_status == "contradicted" else "measurement-only", evidence=[f"ML3: {sec.lead_text}" if sec.lead_text else "ML3 absent", lead_status]),
            MR1_layer_lines=bars_out,
            MR4_off_grid=offs,
            unexplained_mix_onsets=unexplained,
            MR5_gestures=gestures,
            MR6_sustains=sustains,
            MR7_simultaneities=simult,
        )

    def _bar_of(self, ctx, t):
        for bi, b in enumerate(ctx.bars):
            if b.start_s - 0.03 <= t < b.end_s - 0.03:
                return bi + 1
        return 0

    # ---- articulation (MR5-MR7)
    def sustains(self, ctx):
        out = []
        for layer in PITCHED:
            line = ctx.lines[layer]
            for k, x in enumerate(line):
                if not x:
                    continue
                length_beats = x["len"] * float(nominal([Fraction(1, 4)]))  # approximate if mixed set
                end_t = ctx.slot_time[k + x["len"]] if k + x["len"] < len(ctx.slot_time) else ctx.bars[-1].end_s
                dur = end_t - ctx.slot_time[k]
                length_beats = dur / ctx.bars[0].beat_s
                # tweak (rule 8): a legato note released by the next attack is
                # not a sustain unless it lasts a beat; otherwise >= 2 slots
                # and 120 ms, released into a rest or the phrase end
                held = x["release"] in ("rest", "phrase_end") or length_beats >= 1.0 - 1e-6
                if held and length_beats >= PARAMS["sustain_min_slots"] * 0.25 - 1e-6 and dur >= PARAMS["sustain_min_s"]:
                    x["sustain"] = True
                    x["length_beats"] = round(length_beats, 4)
                    out.append(dict(layer=layer, slot=ctx.slot_name(k), seconds=round(ctx.slot_time[k], 4), length_beats=round(length_beats, 4), length_s=round(dur, 4), pitch=midi_name(x["pitch"]), release=x["release"]))
        return out

    def gestures(self, ctx):
        out = []
        steps = {float(d) for d in ctx.subdivs}
        for layer in ["kick", "snare", "bass", "vocals", "other"]:
            line = ctx.lines[layer]
            ks = [k for k, x in enumerate(line) if x]
            pos = {k: ctx.slot_pos[k][0] * ctx.bars[0].bpb + ctx.slot_pos[k][2] for k in ks}
            run = []

            def close(run):
                if len(run) >= PARAMS["gesture_min"]:
                    gid = f"G-{layer}-{ctx.id}-{len(out) + 1}"
                    pitches = [line[k].get("pitch") for k in run]
                    kind = "roll" if layer in DRUMS else ("repeat" if len(set(pitches)) == 1 else "run")
                    for k in run:
                        line[k]["gesture"] = gid
                    line[run[0]]["gesture_head"] = True
                    out.append(dict(id=gid, layer=layer, kind=kind, head=ctx.slot_name(run[0]), span=[ctx.slot_name(run[0]), ctx.slot_name(run[-1])], seconds=[round(ctx.slot_time[run[0]], 4), round(ctx.slot_time[run[-1]], 4)], members=len(run), step_beats=round(pos[run[1]] - pos[run[0]], 4), pitches=[midi_name(p) for p in pitches] if layer in PITCHED else None))

            for k in ks:
                if not run:
                    run = [k]
                    continue
                gap = pos[k] - pos[run[-1]]
                ok_gap = any(abs(gap - s) < 1e-6 for s in steps) and (len(run) < 2 or abs(gap - (pos[run[1]] - pos[run[0]])) < 1e-6)
                ok_pitch = True
                if layer in PITCHED:
                    if line[run[-1]].get("sustain"):
                        ok_gap = False
                    ps = [line[j]["pitch"] for j in run] + [line[k]["pitch"]]
                    dif = np.diff(ps)
                    ok_pitch = bool(np.all(dif >= 0) or np.all(dif <= 0))
                if ok_gap and ok_pitch:
                    run.append(k)
                else:
                    close(run)
                    run = [k]
            close(run)
        return out

    def simultaneities(self, ctx):
        out = []
        for k in range(len(ctx.slot_time)):
            at = [l for l in LAYERS if ctx.lines[l][k]]
            if len(at) >= 2 and any(ctx.lines[l][k]["acc"] for l in at):
                out.append(dict(slot=ctx.slot_name(k), seconds=round(ctx.slot_time[k], 4), layers=at, accents=[l for l in at if ctx.lines[l][k]["acc"]]))
        return out

    # ---- cells (MR2, MR3)
    def cells(self, phrases):
        bar_rows = defaultdict(list)  # layer -> [(phrase, bar_i, pattern, slot_sig, row)]
        for pr in phrases:
            if pr.get("free_rhythm"):
                continue
            sig = "+".join(pr["MG6_slot_set"]["subdivisions"])
            for layer in LAYERS:
                for bi, row in enumerate(pr["MR1_layer_lines"][layer]["bars"]):
                    pat = row["string"].replace("X", "x")
                    bar_rows[layer].append((pr, bi, pat, sig, row))
        cells = {}
        for layer, rows in bar_rows.items():
            pre = CELL_PREFIX[layer]
            cnt = Counter((sig, pat) for _, _, pat, sig, _ in rows)
            ordered = sorted(cnt, key=lambda k: (-cnt[k], k))
            base = []  # (sig, pat, id)
            assign = {}
            out = []
            for sig, pat in ordered:
                if set(pat) == {"."}:
                    assign[(sig, pat)] = (f"{pre}-", None)
                    continue
                parent = None
                for bsig, bpat, bid in base:
                    if bsig == sig and len(bpat) == len(pat) and sum(a != b for a, b in zip(bpat, pat)) <= 1:
                        parent = bid
                        break
                if parent:
                    entry = next(c for c in out if c["id"] == parent)
                    vid = f"{parent}v{len(entry['variants']) + 1}"
                    entry["variants"].append(dict(id=vid, pattern=pat, bars=[]))
                    assign[(sig, pat)] = (vid, parent)
                else:
                    cid = f"{pre}{len(base) + 1}"
                    base.append((sig, pat, cid))
                    out.append(dict(id=cid, pattern=pat, slot_set=sig, bars=[], variants=[]))
                    assign[(sig, pat)] = (cid, None)
            for pr, bi, pat, sig, row in rows:
                cid, parent = assign[(sig, pat)]
                row["cell"] = cid
                bar_no = row["bar"]
                if parent:
                    entry = next(c for c in out if c["id"] == parent)
                    next(v for v in entry["variants"] if v["id"] == cid)["bars"].append(bar_no)
                elif not cid.endswith("-"):
                    next(c for c in out if c["id"] == cid)["bars"].append(bar_no)
            cells[layer] = out
        # dominant cell per section, fills, breaks
        dominants = defaultdict(dict)
        by_section = defaultdict(list)
        for pr in phrases:
            if not pr.get("free_rhythm"):
                by_section[pr["section"]].append(pr)
        base_of = lambda cid: cid.split("v")[0] if cid and "v" in cid[1:] else cid
        pat_of = {}
        for layer, cl in cells.items():
            for c in cl:
                pat_of[c["id"]] = c["pattern"]
        dom_changes = []
        for sid, prs in by_section.items():
            for layer in LAYERS:
                ids = [base_of(r["cell"]) for pr in prs for r in pr["MR1_layer_lines"][layer]["bars"] if not r["cell"].endswith("-")]
                if ids:
                    dominants[sid][layer] = Counter(ids).most_common(1)[0][0]
                    per_phrase = []
                    for pr in prs:
                        pi = [base_of(r["cell"]) for r in pr["MR1_layer_lines"][layer]["bars"] if not r["cell"].endswith("-")]
                        if pi:
                            per_phrase.append((pr["id"], Counter(pi).most_common(1)[0][0]))
                    if len({c for _, c in per_phrase}) > 1 and layer in ("kick", "snare", "vocals", "other"):
                        dom_changes.append(dict(section=sid, layer=layer, phrases=per_phrase))
        fills, breaks = [], []
        flat = [pr for pr in phrases if not pr.get("free_rhythm")]
        for pi, pr in enumerate(flat):
            for layer in LAYERS:
                rows = pr["MR1_layer_lines"][layer]["bars"]
                dom = dominants[pr["section"]].get(layer)
                last = rows[-1]
                if dom and not last["cell"].endswith("-") and base_of(last["cell"]) != dom:
                    dp = pat_of.get(dom, "")
                    lp = last["string"].replace("X", "x")
                    if len(dp) == len(lp) and sum(a != b for a, b in zip(dp, lp)) >= PARAMS["fill_min_diff"]:
                        fills.append(dict(layer=layer, phrase=pr["id"], bar=last["bar"], cell=last["cell"], dominant=dom))
                        last["fill"] = True
                # breaks: layer goes silent for a bar after sounding
                seq = [(pr, r) for r in rows]
                prev_row = None
                if pi > 0:
                    prev_row = flat[pi - 1]["MR1_layer_lines"][layer]["bars"][-1]
                for r in rows:
                    if prev_row is not None and not prev_row["cell"].endswith("-") and r["cell"].endswith("-"):
                        breaks.append(dict(layer=layer, kind="stops", bar=r["bar"], phrase=pr["id"]))
                    if prev_row is not None and prev_row["cell"].endswith("-") and not r["cell"].endswith("-"):
                        breaks.append(dict(layer=layer, kind="returns", bar=r["bar"], phrase=pr["id"]))
                    prev_row = r
        return cells, fills, breaks, dict(dominants), dom_changes

    # ---- anchors (MH3)
    def anchors(self, ctx, pr, phrases, fills, breaks):
        out = []

        def add(k, kind, layers=None):
            at = layers if layers is not None else [l for l in LAYERS if ctx.lines[l][k]]
            out.append(dict(slot=ctx.slot_name(k), seconds=round(ctx.slot_time[k], 4), kind=kind, layers=at))

        first_attack = lambda ks: next((k for k in ks if any(ctx.lines[l][k] for l in LAYERS)), None)
        spb = ctx.slots_per_bar
        # phrase downbeat and section arrival
        if any(ctx.lines[l][0] for l in LAYERS):
            add(0, "section_arrival" if pr["section_start"] else "phrase_downbeat")
        elif pr["section_start"]:
            k = first_attack(range(0, ctx.slots_per_bar // ctx.bars[0].bpb))
            if k is not None:
                add(k, "section_arrival")
        # pickup into the next section: last attacks in the final beat of the
        # phrase's last bar when the next phrase starts a section
        idx = [p["id"] for p in phrases].index(pr["id"])
        nxt = phrases[idx + 1] if idx + 1 < len(phrases) else None
        if nxt and not nxt.get("free_rhythm") and nxt.get("section_start"):
            last_beat = range(len(ctx.slot_time) - spb // ctx.bars[0].bpb, len(ctx.slot_time))
            for l in LAYERS:
                ks = [k for k in last_beat if ctx.lines[l][k]]
                if ks:
                    out.append(dict(slot=ctx.slot_name(ks[-1]), seconds=round(ctx.slot_time[ks[-1]], 4), kind="pickup", layers=[l]))
        # fill bars: every attack in the bar, for that layer
        for f in fills:
            if f["phrase"] != pr["id"]:
                continue
            bi = pr["bars"].index(f["bar"])
            for k in range(bi * spb, (bi + 1) * spb):
                if ctx.lines[f["layer"]][k]:
                    out.append(dict(slot=ctx.slot_name(k), seconds=round(ctx.slot_time[k], 4), kind="fill", layers=[f["layer"]]))
        # break edges: last attack before a layer stops; first attack on return
        for br in breaks:
            l = br["layer"]
            if br["kind"] == "returns" and br["phrase"] == pr["id"]:
                bi = pr["bars"].index(br["bar"])
                ks = [k for k in range(bi * spb, (bi + 1) * spb) if ctx.lines[l][k]]
                if ks:
                    out.append(dict(slot=ctx.slot_name(ks[0]), seconds=round(ctx.slot_time[ks[0]], 4), kind="break_edge", layers=[l]))
            if br["kind"] == "stops":
                # the stop bar may be in this phrase or the next one
                stop_bar = br["bar"]
                if stop_bar - 1 in pr["bars"]:
                    bi = pr["bars"].index(stop_bar - 1)
                    ks = [k for k in range(bi * spb, (bi + 1) * spb) if ctx.lines[l][k]]
                    if ks:
                        out.append(dict(slot=ctx.slot_name(ks[-1]), seconds=round(ctx.slot_time[ks[-1]], 4), kind="last_before_rest", layers=[l]))
        # climax entry
        c = self.grid.climax_s
        if c is not None and ctx.slot_time[0] - 0.05 <= c < ctx.bars[-1].end_s:
            k, _ = ctx.nearest(c)
            add(k, "climax_entry")
        # merge per slot
        merged = {}
        for a in out:
            m = merged.setdefault(a["slot"], dict(slot=a["slot"], seconds=a["seconds"], kinds=[], layers=[]))
            if a["kind"] not in m["kinds"]:
                m["kinds"].append(a["kind"])
            for l in a["layers"]:
                if l not in m["layers"]:
                    m["layers"].append(l)
        return sorted(merged.values(), key=lambda a: a["seconds"])

    # ---- readings (MH0, MH1, MH2, MH4)
    def reading_specs(self, ctx):
        L = ctx.lead
        lead = L[0]
        has = lambda l: any(ctx.lines[l])
        kick_or_snare = "kick" if has("kick") else "snare"
        specs = [
            ("R-lead", [(lead, "all")], []),
            ("R-lead+kick", [(lead, "all"), (kick_or_snare, "accents")], [] if kick_or_snare == "kick" else ["no kick in phrase: snare accents instead"]),
            ("R-drums", [("kick", "all"), ("snare", "all")], []),
            ("R-dense", [(lead, "all"), ("bass", "all"), ("kick", "accents"), ("snare", "accents"), ("hat", "accents")], []),
        ]
        for alt in L[1:]:
            specs.append((f"R-lead[{alt}]", [(alt, "all")], ["ML3 contradicted: alternative lead"]))
        return specs

    def readings(self, ctx, pr):
        anchors = {a["slot"]: a for a in pr["MH3_anchors"]}
        out = []
        dur = ctx.bars[-1].end_s - ctx.bars[0].start_s
        for rid, comps, notes in self.reading_specs(ctx):
            follows = [l for l, _ in comps]
            events = []
            for k in range(len(ctx.slot_time)):
                name = ctx.slot_name(k)
                anc = anchors.get(name)
                layers, accents = [], []
                for l, mode in comps:
                    x = ctx.lines[l][k]
                    if not x:
                        continue
                    is_anchor = anc is not None and l in anc["layers"]
                    if mode == "accents" and not x["acc"] and not is_anchor:
                        continue
                    layers.append(l)
                    if x["acc"]:
                        accents.append(l)
                if not layers:
                    continue
                bi, i, pos = ctx.slot_pos[k]
                ev = dict(slot=name, beat=round(self.grid.sar_beat(ctx.slot_time[k]), 4), seconds=round(ctx.slot_time[k], 4), layers=layers)
                if accents:
                    ev["accents"] = accents
                sus = [l for l in layers if l in PITCHED and ctx.lines[l][k].get("sustain")]
                ges = [ctx.lines[l][k]["gesture"] for l in layers if ctx.lines[l][k].get("gesture")]
                if sus:
                    x = ctx.lines[sus[0]][k]
                    ev.update(articulation="sustain", length_beats=x["length_beats"], release=x["release"])
                elif ges:
                    ev.update(articulation="gesture", gesture=ges[0])
                else:
                    ev["articulation"] = "strike"
                if len(layers) >= 2 and accents:
                    ev["simultaneity"] = True
                anchor_layers = anc and [l for l in anc["layers"] if l in follows]
                if anchor_layers:
                    ev["anchor"] = anc["kinds"]
                # thinning level (rule 12): highest level at which the event survives
                keep = 4
                if not anchor_layers:
                    head = any(ctx.lines[l][k].get("gesture_head") for l in layers)
                    member = bool(ges) and not head
                    if all(l == "hat" for l in layers):
                        keep = 0
                    elif not accents:
                        keep = 1
                    elif member:
                        keep = 2
                    elif abs(pos - round(pos)) > 1e-6:
                        keep = 3
                ev["keep_through"] = keep
                events.append(ev)
            r = dict(id=rid, phrase=ctx.id, follows=follows, modes={l: m for l, m in comps}, thinning=[], events=events, density=self.density(events, dur), status="measurement-only", evidence=[f"MR1:{l}:{ctx.id}" for l in follows])
            if notes:
                r["notes"] = notes
            if not events:
                r["rest"] = self.rest_reason(ctx, follows)
            r["thinning_ladder"] = [
                dict(level=lvl, operators=[op for l2, op in THINNING if l2 <= lvl], events=sum(1 for e in events if e["keep_through"] >= lvl), hits_per_s=round(sum(1 for e in events if e["keep_through"] >= lvl) / dur, 2))
                for lvl in range(0, 5)
            ]
            r["corpus_range"] = self.corpus_range(pr["energy_tercile"], r["density"])
            out.append(r)
        return out

    def rest_reason(self, ctx, follows):
        if all(l in DRUMS for l in follows):
            return "drums_out"
        return "followed layers rest (breakdown or layer absent)"

    @staticmethod
    def density(events, dur):
        t = np.array(sorted(e["seconds"] for e in events))
        if len(t) == 0:
            return dict(hits=0, hits_per_s_mean=0.0, hits_per_s_peak=0.0, min_interval_ms=None, chord_fraction=0.0, sustains=0)
        peak = max(np.searchsorted(t, x + 1.0) - i for i, x in enumerate(t))
        return dict(
            hits=len(t),
            hits_per_s_mean=round(len(t) / dur, 2),
            hits_per_s_peak=float(peak),
            min_interval_ms=round(float(np.diff(t).min() * 1000), 1) if len(t) > 1 else None,
            chord_fraction=round(sum(1 for e in events if e.get("simultaneity")) / len(t), 3),
            sustains=sum(1 for e in events if e["articulation"] == "sustain"),
        )

    def corpus_range(self, tercile, density):
        if not self.prior:
            return None
        row = self.prior.get("head_density_by_energy", {}).get(tercile)
        if not row:
            return None
        v = density["hits_per_s_mean"]
        flag = "below corpus p10" if v < row["p10"] else ("above corpus p90" if v > row["p90"] else None)
        return dict(key=f"energy:{tercile}", level="IN", hits_per_s_p25_p75=[row["p25"], row["p75"]], p10_p90=[row["p10"], row["p90"]], flag=flag)

    # ---- recurrence (rule 14) and default readings
    def recurrence(self, phrases):
        groups = defaultdict(lambda: defaultdict(list))  # group -> section -> phrases
        for pr in phrases:
            if pr.get("free_rhythm"):
                continue
            rs = {r["id"]: r for r in pr["MH0_readings"]}
            if rs["R-lead"]["events"]:
                pr["default_reading"] = "R-lead+kick"
            elif rs["R-drums"]["events"]:
                pr["default_reading"] = "R-drums"
            else:
                pr["default_reading"] = None
            g = pr.get("group")
            if g:
                groups[str(g).rstrip("'")][pr["section"]].append(pr)
        for g, secs in groups.items():
            sec_ids = list(secs)
            if len(sec_ids) < 2:
                continue
            first = secs[sec_ids[0]]
            for sid in sec_ids[1:]:
                for i, pr in enumerate(secs[sid]):
                    if i >= len(first):
                        continue
                    ref = first[i]
                    diffs = []
                    lead = pr["lead"]["value"][0]
                    for a, b in zip(ref["MR1_layer_lines"][lead]["bars"], pr["MR1_layer_lines"][lead]["bars"]):
                        if a["cell"].split("v")[0] != b["cell"].split("v")[0] if len(a["cell"]) > 1 else a["cell"] != b["cell"]:
                            diffs.append(dict(bar=b["bar"], ref_bar=a["bar"], layer=lead, cell=b["cell"], ref_cell=a["cell"]))
                    reason = None
                    if ref.get("default_reading") != pr.get("default_reading"):
                        reason = "different measured content (lead or drums absent in one)"
                    pr["recurrence"] = dict(group=g, same_as=ref["id"], default_from_group=ref.get("default_reading"), lead_bar_differences=diffs, reading_differs_reason=reason)
                    if reason is None:
                        pr["default_reading"] = ref.get("default_reading")
