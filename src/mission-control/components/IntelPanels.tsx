import { HAZARD_STYLE, HAZARD_TYPES } from '../model/constants'
import { ageStr, clkS, sgn } from '../model/format'
import type { inspectorView, SortMode } from '../model/presenters'
import type { HazardFilters, HazardType, JournalEvent, MapHazard } from '../model/types'
import { hazardVars, HazardGlyph } from './HazardGlyph'

type InspectorProps = { view: ReturnType<typeof inspectorView> | null; onClear: () => void; onCenter: () => void }

export function HazardInspector({ view: v, onClear, onCenter }: InspectorProps) {
  return (
    <section className="mc-inspector" aria-label="Hazard inspector" style={v ? { ...hazardVars(v.type), background: `linear-gradient(180deg, rgba(${v.rgb},0.07), transparent)` } : undefined}>
      <div className="mc-row">
        <span className="mc-kicker">HAZARD INSPECTOR</span>
        {v && <button type="button" className="mc-inspector__clear" onClick={onClear}>CLEAR · ESC</button>}
      </div>
      {!v ? (
        <div className="mc-inspector__empty">
          <strong>No hazard selected</strong>
          <span>Select a marker on the map or a row in the inventory to inspect its latest accepted observation.</span>
        </div>
      ) : (
        <div className="mc-inspector__body">
          <div className="mc-inspector__id">
            <span className="mc-inspector__badge"><HazardGlyph type={v.type} large /></span>
            <div className="mc-inspector__names"><strong>{v.id}</strong><span>{v.typeLabel}</span></div>
            {v.aged && <span className="mc-tag-aged">AGED</span>}
          </div>
          <div className="mc-conf">
            <div className="mc-conf__row"><span>CONFIDENCE</span><span>{v.conf}</span></div>
            <div className="mc-conf__bar"><div style={{ width: `${v.confPct}%` }} /></div>
          </div>
          <dl className="mc-kv" style={{ margin: 0 }}>
            <dt>E · N · U</dt><dd className="mc-num">{v.pos}</dd>
            <dt>Uncertainty</dt><dd>{v.unc}</dd>
            <dt>Observed · rover clk</dt><dd>{v.observed}</dd>
            <dt>Observation age</dt><dd className="mc-num" style={{ color: v.ageColor }}>{v.age}</dd>
            <dt>From rover fix</dt><dd>{v.range}</dd>
            <dt>First accepted</dt><dd>{v.first}</dd>
            <dt>Observations</dt><dd>{v.count}</dd>
          </dl>
          <button type="button" className="mc-inspector__center" onClick={onCenter}>CENTER ON MAP</button>
        </div>
      )}
    </section>
  )
}

type InventoryProps = {
  items: MapHazard[]
  total: number
  counts: Record<HazardType, number>
  filters: HazardFilters
  sort: SortMode
  selectedKey: string | null
  hoverKey: string | null
  agedMs: number
  onToggleType: (t: HazardType) => void
  onToggleSort: () => void
  onSelect: (h: MapHazard) => void
  onHover: (key: string | null) => void
}

export function HazardInventory({ items, total, counts, filters, sort, selectedKey, hoverKey, agedMs, onToggleType, onToggleSort, onSelect, onHover }: InventoryProps) {
  return (
    <section className="mc-inventory" aria-label="Hazard inventory">
      <div className="mc-inventory__top">
        <div className="mc-row"><span className="mc-kicker">HAZARD INVENTORY</span><span className="mc-inventory__count">{total} TRACKED</span></div>
        <div className="mc-inventory__filters">
          {HAZARD_TYPES.map((t) => (
            <button key={t} type="button" aria-pressed={filters[t]} className={`mc-type-chip${filters[t] ? ' mc-type-chip--on' : ''}`} style={hazardVars(t)} onClick={() => onToggleType(t)}>
              {HAZARD_STYLE[t].label} <i>{counts[t]}</i>
            </button>
          ))}
          <button type="button" className="mc-sort" onClick={onToggleSort}>↕ {sort}</button>
        </div>
        <div className="mc-inv-grid mc-inv-head"><span /><span>ID</span><span>CONF</span><span>E, N ± m</span><span>AGE</span></div>
      </div>
      <div className="mc-inventory__list">
        {items.length === 0 && <div className="mc-inventory__empty">No hazard observations accepted yet.</div>}
        {items.map((h) => {
          const sel = h.key === selectedKey
          const aged = h.ageMs > agedMs
          const cls = ['mc-inv-grid', 'mc-inv-row', sel && 'mc-inv-row--sel', !sel && h.key === hoverKey && 'mc-inv-row--hover', aged && !sel && 'mc-inv-row--aged'].filter(Boolean).join(' ')
          return (
            <div key={h.key} className={cls} style={hazardVars(h.type)} role="button" tabIndex={0} aria-pressed={sel}
              onClick={() => onSelect(h)} onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onSelect(h) } }}
              onMouseEnter={() => onHover(h.key)} onMouseLeave={() => onHover(null)}>
              <HazardGlyph type={h.type} />
              <span className="mc-inv-row__id">{h.id} <i>{HAZARD_STYLE[h.type].label}</i></span>
              <span className="mc-num">{h.confidence.toFixed(2)}</span>
              <span className="mc-num mc-inv-row__pos">{`${sgn(h.x, 1)}, ${sgn(h.y, 1)} ±${h.unc.toFixed(1)}`}</span>
              <span className="mc-num" style={{ color: aged ? '#f2b54a' : '#8fa6b2' }}>{ageStr(Math.max(0, h.ageMs))}</span>
            </div>
          )
        })}
      </div>
    </section>
  )
}

export type EventFilter = 'ALL' | 'ALERTS' | 'HAZARDS'
const matches = (e: JournalEvent, f: EventFilter) =>
  f === 'ALL' ? true : f === 'ALERTS' ? e.level === 'crit' || e.level === 'warn' || e.level === 'ok' : e.kind === 'hazard'

export function EventStream({ events, filter, onFilter }: { events: JournalEvent[]; filter: EventFilter; onFilter: (f: EventFilter) => void }) {
  const view = events.filter((e) => matches(e, filter)).slice(0, 120)
  return (
    <section className="mc-events" aria-label="Event stream">
      <div className="mc-events__top">
        <span className="mc-kicker">EVENT STREAM</span>
        <div className="mc-events__tabs">
          {(['ALL', 'ALERTS', 'HAZARDS'] as const).map((k) => (
            <button key={k} type="button" aria-pressed={filter === k} onClick={() => onFilter(k)}>{k}</button>
          ))}
        </div>
      </div>
      <div className="mc-events__list" role="log" aria-live="off">
        {view.map((e) => (
          <div key={e.id} className={`mc-ev mc-ev--${e.level}`}>
            <span className="mc-ev__time">{clkS(e.t)}</span>
            <span className="mc-ev__tag">{e.tag}</span>
            <span className="mc-ev__msg">{e.msg}</span>
          </div>
        ))}
      </div>
    </section>
  )
}
