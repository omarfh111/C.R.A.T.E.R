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
| [`crater-readme-hero.svg`](crater-readme-hero.svg) | 1280×640 | Animated README hero. |
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

`crater-readme-hero.svg` tells the actual product story in one frame: camera capture → local ONNX
detection → calibrated projection into `LOCAL_ENU_V1` → binary encoding → lossy radio with a
simulated blackout → Mission Control. Every figure shown in it is drawn from
[integration validation](../integration-validation.md), and the honest qualifiers (recorded replay,
simulated radio, synthetic scene) are rendered into the artwork rather than left to the caption.

**Motion.** All animation is CSS inside the SVG — no SMIL, no script. Every animated property is
translation, opacity, circle radius or dash offset, so nothing depends on `transform-origin`
resolution and the file stays about 24 KB.

**Accessibility.** The hero carries `role="img"` with `<title>` and `<desc>` through
`aria-labelledby`, and honours `prefers-reduced-motion: reduce` by disabling every animation.

**Static fallback.** The artwork is authored so that its *unanimated* state is already a complete
composition: the rover sits mid-traverse, all three rocks are marked, every readout is populated and
telemetry frames are spread along the signal path. Animation only adds motion on top. If a renderer
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
