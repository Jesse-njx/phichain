# Verrückt IN 16.5 — line presentation study

Requested after the user rejected Happy ending presentation revision 01 as still
not viable. This is a reference analysis, not a chart edit or a quality verdict.

[Indexed native video and plots](index.html) · [Original-event measurements](evidence.json)
· [Reproducible evaluator](analyze.py)

## Main finding

The useful unit of design is a **phrase with a changing scene, readable judgment
geometry, and a deliberate entry and exit**. A repeated pulse on two edge lines
does not provide that by itself. Verrückt uses recurring visual families with
variation: diagonal arrays, staggered vertical sweeps, a mildly tilted judgment
plane, opposing top/bottom planes, and a developed return to vertical figures.
These names describe observed geometry, not verified musical section labels.

It does not simply make everything faster or brighter. Some carrier movements
take several beats, some lines remain still, and some resets happen while hidden.
The contrast and the time profile matter more than the number of events.

## Concrete mechanisms

All line IDs below are zero-based indices in the original JSON. Source x/y are
normalized; y increases upward. A beat is60/238=0.252101seconds.

| Time / beats | Observed source behavior | What it teaches us |
|---|---|---|
| 0–9.076s /0–36 | No notes yet. Line0 fades from alpha1 to0, moves while hidden, then returns from alpha0 at beat30 to1 at36, settling at y=.17. Other lines form a66° diagonal array. | Reveal a usable receiving plane as an entrance, rather than displaying every idle carrier permanently. This also shows that purposeful decorative introduction is different from an unused target left behind. |
| 9.076–16.134s /36–64 |113 note heads are distributed across11 internal lines. All judge at y=.17 and rotation0;101 heads have their own carrier alpha<.1. | Internal carrier visibility is not the same thing as visual judgment-plane clarity. Multiple invisible carriers can share an established horizontal receiving plane. Do not solve readability by blindly exposing every note-owning line. Source also intentionally blinks the shared plane at times; this is not a claim of uninterrupted visibility. |
| 19.412–22.185s /77–88 | Vertical lines13/14/15 enter in staggered phases. For line14, beat82→85.9375 moves x−.05→.35. At82.5 it is already .116536; at83 .224740; at84 .325764: rapid travel then progressively slower arrival. Alpha.8 decays to0 by84.46875; the invisible tail settles before reset at86. | Position and opacity describe one gesture: entrance, travel, decay, hidden reset. Neighboring lines echo it one beat apart. This is richer than toggling a fixed line on and off, and the large reset is not a visible jump. |
| 35.294–39.328s /140–156 | Playable line1 moves x.5→.44 over10beats, then returns to.5 over6beats with a different curved profile. The displacement is81 native horizontal units. | A playable carrier can participate in the phrase with asymmetrical departure and return. This slower movement is not a uniform-speed drift and should not be replaced automatically by identical short impulses. |
| 51.681–59.748s /205–237 | Line0 rotates0→−3° (205–213), holds to216, moves to+3° at225, returns to−3° at231, then settles at0 by237. Line2 has a different, overlapping tilt curve. A52° diagonal family appears behind it. | Mild playable-plane motion can carry a whole phrase. Reversal, dwell, response and resolution are distinct; the two planes do not all move in phase. Note directions visibly follow their carriers. |
| 67.563–84.706s /268–336 | Line0 rises from y.2 to.5 by274, holds through276, then separates downward as line1 appears and separates upward. By284 the two are at y.2/.8, with opposing orientation. At288 rotations are10.3125°/169.6875°. A short central flash/reset separates the approach from the split. Arrays around the sides frame the new layout. | The transition changes the playing space itself. Prepare it across the preceding sustain, establish the new pair of targets, then develop that scene. It is not just a new background pasted behind an unchanged lane. |
| 84.706–114.958s /336–456 | The scene returns to a lower horizontal receiving plane with vertical motion families. At384 paired vertical lines12/13 are at x.453/.547, alpha.6; at448 a different four-position distribution uses x.2/.4/.6/.8 and unequal alpha. | A returning visual family can be recognizable without repeating every coordinate or amplitude. Related sections need shared identity and deliberate development. |

These are measured visual mechanisms. Beat anchoring is established by the source;
exact kick/snare/instrument assignments are **not** established by this analysis.
The native video retains audio for manual synchronization review. I inspected
overview and dense frame sequences plus full60fps channel traces, not every frame
of real gameplay, and did not perform a hearing-based musical transcription.

## Why the Happy ending revision falls short

1. **One vocabulary across the song.** Its273 short impulses and two edge flashes
   do not specify which idea introduces, answers, develops or resolves a phrase.
   Disabling the earlier fan removed clutter but left little large-scale contrast.
2. **Accents do not consistently follow the playable gesture.** Selecting a
   signal-supported timestamp is insufficient if the flash goes right while the
   relevant Drag goes left. Direction, recipient and phrase membership also matter.
3. **Movement has too little phrase identity.** The same pre-hit/recovery template
   cannot express every arrival, held pose, directional sweep and scene transition.
4. **The carrier join is part of the arrangement.** An early-visible line can still
   demand an awkward hand relocation at the join. Visibility validation does not
   establish comfort or action continuity.
5. **Technical passing conditions do not judge music.** Exact source onsets, two
   simultaneous objects, non-overlapping events and a valid render cannot establish
   a convincing climax, rhythm interpretation or suitable difficulty.

Do not copy Verrückt's rotations, amplitudes,24 lines or16.5 difficulty into Happy
ending wholesale. Transfer the responsibilities: phrase identity, directional
relationships, motion articulation, controlled visibility and whole-song contrast.
The user's newer feedback and per-family review should determine the new design.

## Provenance and verification limits

Original source: `local/arrangement-training/raw/Verruckt.Raimukun.0/IN.json`, resolved
through its manifest. SHA256:
`f7b8a3318b67b239145b13248d119930afd0ad06e90bee684ae575b09b11aafa`.
Catalog: Verrückt / Raimukun / IN16.5 / Magazet. Source contains1285notes across24lines;
17 lines carry notes somewhere in the song. The official Happy ending IN and its
derived analyses were not accessed.

Video is the existing960×540/60fps native PhiChain render of the cached conversion,
not a screen recording from official Phigros. Source numbers above come directly
from the unmodified original JSON. Native conversion was independently checked:
note time/type/side and local x match, allowing .01 native-unit rounded-coordinate
precision. At60fps over122s, largest original-vs-native differences are x.580units,
y.321units, rotation.084°, opacity.722/255; speed agrees to floating-point precision.
This is sampled conversion evidence, not an exact continuous error bound. Hidden
and off-screen reset coordinates are excluded from the visible positional plots.
Rotation plots include both carrier curves even where one is fading.

All artifacts remain local and ignored. No chart/source edits, publishing or
automated aesthetic improvement loop were performed by this reference study.
