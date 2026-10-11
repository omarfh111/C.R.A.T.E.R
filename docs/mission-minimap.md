# Mission Control minimap

The compact north-up overview appears above the map navigation controls on desktop. It uses the same accepted telemetry model as the tactical map: rover fixes, retained hazards, selected hazard and bounded journal trail. It has no network requests, model dependencies, driving actions or generated measurements.

- The cyan marker is the accepted rover fix. Its uncertainty circle uses the transmitted radius at the overview's metric scale.
- Hazard shapes/colors match the existing map. The selected hazard has an amber ring. Existing type filters, trail and uncertainty layer switches apply.
- Both axes use the same meters-per-pixel scale in LOCAL_ENU_V1. The start-marker origin is included in the extent; the footer gives the overview's east/north span in meters. This is a schematic overview, not imagery or a surveyed terrain map.
- A pale rectangle marks the current tactical map viewport. It is clipped when the tactical map covers more than the overview. Viewport updates share the existing 500 ms Mission Control refresh; they do not create a React update every animation frame.
- Dashed amber trail sections connect accepted fixes separated by sequence gaps. The intervening path is unobserved.
- Stale, blackout and station-disconnected states retain the accepted fix with `LAST KNOWN`. There is no extrapolated position and no inferred failure cause.
- Before the first accepted frame, the panel reports `NO ACCEPTED FIX` and creates no rover or hazard markers.

`FIT MISSION` invokes the existing map fit action. It changes only the view and stops following, just like the existing FIT control. The MINIMAP heading collapses/expands the panel. At widths up to 700 px it starts collapsed; it can be opened with the keyboard or pointer. The small-screen legend yields space while the overview is open. The outage banner and existing navigation remain available.

The canonical WebSocket v1 contract, reducer, radio transport, perception pipeline, assistant security and capture safeguards are unchanged. No new environment variables or launch commands are required. The original two-command model-free Quick Demo supplies the overview automatically.

Uncalibrated external videos can demonstrate image-coordinate detections. They must not populate this metric overview without suitable camera calibration, rectification and rover poses. The synthetic calibrated scene and historical replay retain their existing provenance; an active WebSocket does not certify fresh physical rover measurements.

## Verification

`npm test` covers north/east projection, equal axis scale, extent margins, empty/coincident fixes, sequence gaps, stale retained fixes, hazard filters/selection and collapsible behavior. The real M2 Playwright suite compares overview coordinates and sequence with the actual delivered frames, checks zoom/FIT behavior and responsive layout, and separately retains the strict 30-frame replay acceptance gate and historical timestamp checks.

```powershell
npm test
npm run build
npm run typecheck:e2e
npm run test:e2e
```

Playwright uses isolated loopback test ports. It requires the existing model-free Python environment and Chromium; it does not use Ollama, GPU perception or model downloads.
