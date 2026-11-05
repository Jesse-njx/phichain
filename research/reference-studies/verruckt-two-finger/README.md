# Verrückt IN — two-finger action study

Follow-up, 2026-11-02: the user subsequently authorized one short, static-note Override example. See `../../override-gesture-sample/README.md` for the deeper within-gesture geometry analysis and an 8-beat draft. Earlier study-only scope below is historical. The three rejected drafts remain rejected.

Study date: 2026-11-02. Current task is study and instruction correction only. All three Override drafts were rejected. No new arrangement is authored here.

## Evidence and scope

Local catalog: Verrückt by Raimukun, IN 16.5, chart credited to Magazet. Official-format data comes from the cached community resource mirror; the exact source hash is recorded below. Source JSON is preserved. The entire chart was decoded: 837 Tap, 398 Drag, 50 Hold, zero Flick; BPM 238.

Source: `../../overnight-study/corpus/chart/Verruckt.Raimukun.0/IN.json`; acquisition manifest: `../../overnight-study/corpus/manifest.json`. Hash: `f7b8a3318b67b239145b13248d119930afd0ad06e90bee684ae575b09b11aafa`. The source offset is zero. Times below are chart/audio seconds. Screen x uses a centered 1350-wide coordinate system and includes the judgment-time carrier transform, not just local note x.

The cached native conversion was rendered in full, 960×540 at 60 fps, without hit effects. Fifteen overview samples and dense samples for two specific phrases were inspected, alongside a prior 40–56 second render. This is not a claim of watching every frame, hearing/transcribing every sound, having handcam evidence, or playtesting. Candidate L/R labels are an interpretation of geometry and phrase continuity, not fields encoded in the source.

## 1. One hand repeats while the other travels; then roles exchange

At 12.226891–12.605042, a plausible alternating assignment is R L R L R L R. The left-hand positions are approximately −228, −228, −221. The right-hand positions are +1, +202, +14, +508. That is a locally stable left hand with a traveling right hand.

At 12.731092–13.109244, the roles exchange: L R L R L R L. The right-hand positions stay near +270, +270, +263; the left hand visits +48, −140, +34, −438. Left/right ownership cannot be reconstructed merely by splitting the screen at zero.

The interleaved hit interval is about 63.025 ms; each hand's alternating strikes are about 126.050 ms apart. These numbers describe this reference at its tempo, not recommended thresholds for Override. The transferable rule is to compose relationships between hands: anchor, moving answer, and role exchange. Requiring every finger to move at every hit would erase this pattern.

## 2. Alternate complete contact gestures; let the other hand take the next hit

| Time (s) | Type | Actual x | Candidate hand | Role |
|---:|---|---:|:---:|---|
| 43.613445 | tap | -104.7 | L | Fresh gesture entrance |
| 43.676471 | drag | -219.1 | L | Continue the same contact |
| 43.739496 | drag | -335.7 | L | Continue the same contact |
| 43.802521 | drag | -451.9 | L | Continue the same contact |
| 43.865546 | tap | 491.5 | R | Fresh gesture entrance |
| 43.928571 | drag | 379.7 | R | Continue the same contact |
| 43.991597 | drag | 268.8 | R | Continue the same contact |
| 44.054622 | drag | 164.6 | R | Continue the same contact |
| 44.117647 | tap | -146.9 | L | Fresh gesture entrance |
| 44.180672 | drag | -253.9 | L | Continue the same contact |
| 44.243697 | drag | -351.6 | L | Continue the same contact |
| 44.306723 | drag | -461.4 | L | Continue the same contact |

The first left sweep ends at 43.802521. The next chronological Tap is only 63.025 ms later, but it can belong to the RIGHT hand, which starts its own sweep. The left hand next strikes at 44.117647: 315.126 ms after its own last Drag. The intervening right-hand gesture supplies recovery time without inserting an arbitrary empty musical slot.

The key is gesture ownership, not simply whether a Tap follows a Drag in the global note list. This is not a license to copy a universal 315 ms minimum: recoveries depend on musical grouping, movement and the intended gesture.

## 3. Ordinary alternating taps can move both hands substantially

At 41.848739–42.289916, plausible hands are R L R L R L R L. Their separate routes are:

- R: +372 → +141 → +324 → +507.
- L: −467 → −165 → −337 → −509.

This creates finger travel through the arrangement of successive hit positions. Cosmetic approach swaying is not needed to create that hand movement. The reference does have line motion and special passages elsewhere; studying its hand paths does not imply copying its presentation or claiming all its notes fall on an entirely static scene.

## 4. Contrast is intentional

Around 49.411765–50.357143, the chart alternates taps at approximately −175 and +175. Movement contracts into fixed stations for a short passage. That is a meaningful contrast with the preceding wide travel, not a reason to reject every stationary moment. A whole-chart demand that both fingers always travel would be the wrong rule.

## Corrections to our authoring method

- Begin with the musical action phrase, then assign whole gestures and fresh hits to hands. After a sustained contact or terminal Flick, inspect the next action of that SAME hand.
- Never use a merely positive release gap as proof of natural play. Do not terminate a contact at an arbitrary off-rhythm instant just to squeeze in the next tap.
- Drag → terminal Flick may naturally finish a gesture. Do not automatically follow it with a same-finger immediate repress. A complete short gesture followed by a naturally spaced hit can work, including at the same location. This rule comes from the user's feedback; Verrückt contains no Flicks and cannot verify the Flick case itself.
- Use the free opposite hand to keep the musical rhythm going while the gesture hand releases and relocates. Evaluate whether that allocation is actually available through the next phrase.
- Use ordinary straight approach by default. The player's hands moving across hit positions is different from note sprites sliding during approach. Exceptional note animation needs a specific musical reason.
- A valid chart, exact landings, maximum two contacts and a render are necessary technical evidence, not an endorsement of arrangement quality.

## Concrete failures in the rejected Override drafts

A assigns a left-hand terminal Flick at beat 154.75 followed by a left-hand Tap at beat 155: only 73.529 ms between them. Its audit subtracted an arbitrary release allowance and still reported a positive gap. That passed a bookkeeping test while missing the unintuitive release/repress. Similar cases occur at 170.75→171 and 186.75→187.

C has a left-hand final Drag at 65.75 followed by a fresh Hold head at 66, and at 137.75 followed by Tap at 138. These are also 73.529 ms gaps. A Hold head still requires a fresh hit. No further rewrite of these rejected arrangements is authorized by the current study-only request.

## Current workspace state

The three original authoring sessions are closed. Before the user's study-only clarification arrived, cosmetic approach slides were removed and saved for A and B via temporary maintenance sessions; those sessions were closed immediately. C was not changed. B's actual moving-contact gameplay remains. The original Override project is unchanged. Further work is limited to these study notes and local/AGENTS.md until the user requests a new chart edit.
