# C.R.A.T.E.R. brand assets

Original identity for the C.R.A.T.E.R. lunar hazard reconnaissance system. Every asset here is a
self-contained SVG: no remote fonts, no external images, no scripts, no JavaScript, no tracking.
These files are documentation and branding only — they are not imported by the React application,
and they do not affect the favicon, the UI, or any runtime behaviour.

## Assets

| File | Size | Use |
|---|---|---|
| [`crater-mark.svg`](crater-mark.svg) | 64×64 | Primary icon. Works on dark and light backgrounds. |
| [`crater-mark-mono.svg`](crater-mark-mono.svg) | 64×64 | Single-colour icon drawn in `currentColor`. |
| [`crater-logo.svg`](crater-logo.svg) | 460×132 | Horizontal lockup — mark, wordmark and descriptor on a dark panel. |
| [`crater-readme-hero.svg`](crater-readme-hero.svg) | 1280×640 | Animated README hero — the automatic incident dialogue, end to end. |
| [`crater-hero-static.svg`](crater-hero-static.svg) | 1280×640 | Motion-free variant of the hero, for slides, print and PDF export. |

`crater-mark-mono.svg` inherits the surrounding `color` when it is inlined in HTML or imported as a
component. Referenced as `<img src="...">` it has no inheriting context and renders in the browser's
default text colour — so use it inlined, or use `crater-mark.svg` for `<img>`.

## What the mark means

A **navigation reticle** (the rotated square already used by the Mission Control header symbol)
frames **concentric crater rings** seen from above, crossed by a **dashed rover traverse** that
terminates at an **amber node**: the acquired hazard fix. It compresses the whole product into one
glyph — a route across lunar terrain, and the one thing on it that matters.

The mark is original work. It is not derived from, and shares no paths with, any other project's
artwork.

## Palette

Taken directly from the running dashboard's tokens in
[`src/mission-control/mission-control.css`](../../src/mission-control/mission-control.css), so the
documentation and the product read as one system.

| Token | Value | Role |
|---|---|---|
| Lunar base | `#03070c` | Page and panel ground |
| Panel | `#060f16` | Raised surfaces |
| Telemetry cyan | `#9bddea` | Primary accent, structure, data |
| Cyan highlight | `#c9f3fa` | Live values, emphasis |
| Kicker cyan | `#86c9d7` | Section labels |
| Hazard amber | `#f2b54a` | Detected hazards, degraded link, blackout |
| Alert red | `#ef5b4c` | Reserved for failure states |
| Text | `#e9f0f3` | Body |
| Steel / muted / dim | `#a5b9c4` / `#8fa6b2` / `#5f7581` | Secondary and tertiary text |
| Hairline | `rgba(145,214,229,0.14)` | Rules, borders |

Amber is a hazard and degradation colour only. It is never decorative.

## Typography

The assets request `Space Grotesk` (display) and `IBM Plex Mono` (technical readouts) to match the
application, then fall back through system stacks. **No font is fetched** — an SVG embedded in a
README cannot load one, so the fallback is the normal rendering path outside the app.

## The hero

`crater-readme-hero.svg` tells the newest product story in one frame, over a single 24-second
cycle: **rover detects → radio blackout → incident recorded → robot asks AI → post-capture AI
analysis → Mission Control displays the answer.** Three panels carry it — the rover field view, the
`ROBOT INCIDENT DIALOGUE` journal, and the Mission Control reply — above a six-stage rail with a
playhead that lands on each beat as it happens.

Every label and figure is drawn from the shipped implementation and its
[target-PC evidence](../validation/incident-dialogue/evidence.md): the incident kind
`telemetry_stale` and trigger `capture_stale` are real detector outputs, the question is the exact
server-chosen text for that kind, the job states are the real UI strings, and the measured
post-capture analysis time and warm generation throughput are the recorded ones.

Four honest constraints are rendered into the artwork rather than left to the caption. The dialogue
is **text**, never voice. The rail's `CAPTURE ENDS · AI ADMITTED` gate sits between the robot's
question and the analysis, because generation is admitted only once capture has finished. Every
generated answer carries `UNVERIFIED GENERATED EXPLANATION` with its `[S1]` citation. And
`NO ROVER COMMAND` states that nothing here drives the rover.

**Motion.** All animation is CSS inside the SVG — no SMIL, no script. Every animated property is
translation, opacity, circle radius or dash offset, so nothing depends on `transform-origin`
resolution and the file stays about 37 KB. One 24-second cycle drives every element, so the beats
stay in step with each other and with the rail playhead instead of drifting on separate loops.
Each state swap — `LIVE`/`STALE`, the job-state chips, the narration band — is authored as a clean
hand-off, with the outgoing element fully faded before the incoming one begins.

**Accessibility.** The hero carries `role="img"` with `<title>` and `<desc>` through
`aria-labelledby`, and honours `prefers-reduced-motion: reduce` by disabling every animation.

**Static fallback.** The artwork is authored so that its *unanimated* state is already a complete
composition — the resolved end of the story, not an empty stage. The rover sits mid-traverse with
all three rocks marked, the incident record is fully written, the question is fully typed, the job
reads `ANALYSIS COMPLETE`, the cited reply and its source line are shown, and the rail is fully
wiped with the playhead resting on the final beat. Animation only adds motion on top. If a renderer
strips the `<style>` block, or the reader prefers reduced motion, the hero degrades to that
composition rather than to a broken or empty frame.

`crater-hero-static.svg` is generated from the animated file by removing its motion rules and
nothing else. [`build-static-hero.py`](build-static-hero.py) performs that transformation; it is
documentation tooling, touches nothing outside this folder, and is not part of the M1/M2/M3 runtime
or CI. Regenerate after editing the hero:

```powershell
python docs\brand\build-static-hero.py
```

To confirm the two files are in sync without writing anything:

```powershell
python docs\brand\build-static-hero.py --check
```

## Using these assets

- Keep the mark's clear space at least one quarter of its width on every side.
- Do not recolour the mark outside the palette above, rotate it, or set it on a mid-tone background
  where the cyan loses contrast — use `crater-mark-mono.svg` instead.
- Do not add a drop shadow, outline or gradient to the mark.
- Do not stretch any asset: all five have a `viewBox` and scale correctly from their intrinsic
  aspect ratio.
- Write the name as **C.R.A.T.E.R.** — full stops, no spaces.
