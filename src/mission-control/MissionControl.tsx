import { useEffect, useRef, useState } from 'react'
import { THRESHOLDS } from './model/constants'
import { deriveComms } from './model/derive'
import { sgn } from './model/format'
import {
  ageView, demoTickLabel, inspectorView, linkView, mapHazards, outageBanner, postureSubline, roverView, sortedInventory, typeCounts, type SortMode,
} from './model/presenters'
import type { HazardFilters, MapLayers, MapModel } from './model/types'
import type { MissionTelemetry } from './hooks/useMissionTelemetry'
import { useNow, useViewportWidth } from './hooks/useNow'
import { TacticalMap, type TacticalMapHandle } from './map/TacticalMapView'
import { MissionHeader } from './components/MissionHeader'
import { CommsPanel, PacketPanel, RoverPanel } from './components/StatusPanels'
import { MapBrackets, MapLegend, MapNav, MapTitle, OutageBanner } from './components/MapOverlays'
import { EventStream, HazardInspector, HazardInventory, type EventFilter } from './components/IntelPanels'
import './mission-control.css'

export type MissionControlProps = {
  /** From `useMissionTelemetry()`. All operational displays derive from this. */
  telemetry: MissionTelemetry
  /** Wire to `useIntroPlayback().replayIntro`. Button hidden when omitted. */
  onReplayIntro?: () => void
  /** True while the lunar intro overlay is covering the dashboard. On true→false the map replays its boot reveal. */
  introActive?: boolean
  /** Extra classes on the root, e.g. the existing `dashboard-shell` / `dashboard-shell--intro-active` crossfade classes. */
  className?: string
  /** Mirrors the existing `<main inert>` while the intro is visible. */
  inert?: boolean
  staleThresholdMs?: number
  agedHazardMs?: number
}

const ALL_TYPES: HazardFilters = { crater: true, rock: true, slope: true, unknown: true }
const ALL_LAYERS: MapLayers = { trail: true, unc: true, rings: true, envelope: true, cog: true }

export function MissionControl({
  telemetry, onReplayIntro, introActive = false, className = '', inert = false,
  staleThresholdMs = THRESHOLDS.staleMs, agedHazardMs = THRESHOLDS.agedHazardMs,
}: MissionControlProps) {
  const now = useNow(500)
  const vw = useViewportWidth()
  const mapRef = useRef<TacticalMapHandle>(null)
  const cursorRef = useRef<{ x: number; y: number } | null>(null)
  const scaleRef = useRef(0)
  const [selectedKey, setSelectedKey] = useState<string | null>(null)
  const [hoverKey, setHoverKey] = useState<string | null>(null)
  const [follow, setFollow] = useState(true)
  const [filters, setFilters] = useState<HazardFilters>(ALL_TYPES)
  const [layers, setLayers] = useState<MapLayers>(ALL_LAYERS)
  const [evFilter, setEvFilter] = useState<EventFilter>('ALL')
  const [sort, setSort] = useState<SortMode>('RECENT')
  const [demoOpen, setDemoOpen] = useState(false)

  const { state: tel, journal: j, intervalMs } = telemetry

  // New telemetry session (DEMO restart / source change): clear selection and resume following.
  useEffect(() => { setSelectedKey(null); mapRef.current?.setFollow(true) }, [j])
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') setSelectedKey(null) }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])
  const wasIntro = useRef(introActive)
  useEffect(() => {
    if (wasIntro.current && !introActive) mapRef.current?.reboot()
    wasIntro.current = introActive
  }, [introActive])

  const d = deriveComms(tel, j, now, intervalMs, staleThresholdMs)
  const f = d.frame
  const hazards = mapHazards(tel, j, now)
  const model: MapModel = {
    trail: j.trail, hazards, selectedKey, posture: d.posture, lastRxMs: d.lastRxMs, maxSpeed: j.maxSpeedMps,
    layers, filters, minConfidence: 0, agedHazardMs, recoveryStartMs: j.recoveryStartMs, intervalMs,
    rover: f && d.lastRxMs != null ? {
      x: f.roverPosition.xM, y: f.roverPosition.yM, unc: f.positionUncertaintyRadiusM, seq: f.sequence, roverId: f.roverId,
      cog: j.cogRad, latencyMs: d.lastRxMs - Date.parse(f.capturedAt),
    } : null,
  }

  const stale = !!f && (d.posture === 'BLACKOUT' || d.posture === 'TRANSPORT_DOWN' || d.posture === 'STALE')
  const banner = outageBanner(d, j, now)
  const selected = hazards.find((h) => h.key === selectedKey) ?? null
  const inventory = sortedInventory(hazards, filters, sort, f?.roverPosition.xM ?? 0, f?.roverPosition.yM ?? 0)
  const c = cursorRef.current
  const cfg = telemetry.mockConfig

  return (
    <div className={`mc ${className}`.trim()} inert={inert} aria-hidden={inert || undefined}>
      <MissionHeader
        posture={d.posture}
        postureSub={postureSubline(d, j, now)}
        sourceMode={telemetry.mode}
        utc={new Date(now).toISOString().slice(11, 21)}
        wide={vw >= 1560}
        onReplayIntro={onReplayIntro}
        demo={telemetry.demo && cfg ? {
          open: demoOpen, onToggle: () => setDemoOpen((o) => !o), presetId: telemetry.demo.presetId,
          onPick: (id) => { telemetry.demo?.restart(id); setDemoOpen(false) },
          tickLabel: demoTickLabel(j, now, cfg), showTick: vw >= 1240,
        } : undefined}
      />

      <aside className="mc-rail mc-rail--left">
        <RoverPanel rover={roverView(d, j)} age={ageView(d)} stale={stale} blackout={d.posture === 'BLACKOUT' || d.posture === 'TRANSPORT_DOWN'} />
        <CommsPanel link={linkView(tel, d, j, now)} packets={j.packets} spans={j.spans} nowMs={now} />
        <PacketPanel
          received={tel.received} accepted={tel.accepted} invalid={tel.invalid} duplicates={tel.duplicates}
          outOfOrder={tel.outOfOrder} sequenceGaps={tel.sequenceGaps}
          rover={f ? { sent: f.link.packetsSent, lost: f.link.packetsLost, seq: f.sequence } : null}
        />
      </aside>

      <main className="mc-map">
        <TacticalMap
          ref={mapRef}
          model={model}
          onHover={setHoverKey}
          onSelect={setSelectedKey}
          onCursor={(p) => { cursorRef.current = p }}
          onFollowChange={setFollow}
          onFrame={({ scale }) => { scaleRef.current = scale }}
        />
        <MapBrackets />
        <MapTitle layers={layers} onToggle={(k) => setLayers((l) => ({ ...l, [k]: !l[k] }))} />
        <MapLegend zoomText={scaleRef.current ? `${scaleRef.current.toFixed(0)} px/m · drag to pan · scroll to zoom` : ''} />
        {banner && <OutageBanner banner={banner} top={vw - 650 > 1100 ? 120 : 160} />}
        {telemetry.configurationError && <div className="mc-config-error" role="alert">{telemetry.configurationError}</div>}
        <MapNav
          cursorText={c ? `E ${sgn(c.x)}  N ${sgn(c.y)} m` : 'E —  N — m'}
          follow={follow}
          onZoomIn={() => mapRef.current?.zoomBy(1.4)}
          onZoomOut={() => mapRef.current?.zoomBy(1 / 1.4)}
          onFit={() => mapRef.current?.fit([...j.trail, ...hazards])}
          onToggleFollow={() => mapRef.current?.setFollow(!follow)}
        />
      </main>

      <aside className="mc-rail mc-rail--right">
        <HazardInspector
          view={selected ? inspectorView(selected, j, d, agedHazardMs) : null}
          onClear={() => setSelectedKey(null)}
          onCenter={() => selected && mapRef.current?.centerOn(selected.x, selected.y)}
        />
        <HazardInventory
          items={inventory} total={hazards.length} counts={typeCounts(hazards)} filters={filters} sort={sort}
          selectedKey={selectedKey} hoverKey={hoverKey} agedMs={agedHazardMs}
          onToggleType={(t) => setFilters((p) => ({ ...p, [t]: !p[t] }))}
          onToggleSort={() => setSort((s) => (s === 'RECENT' ? 'NEAREST' : 'RECENT'))}
          onSelect={(h) => { setSelectedKey(h.key); mapRef.current?.centerOn(h.x, h.y) }}
          onHover={setHoverKey}
        />
        <EventStream events={j.events} filter={evFilter} onFilter={setEvFilter} />
      </aside>
    </div>
  )
}
