import { useEffect, useRef } from 'react'
import { MC_COLORS, THRESHOLDS } from '../model/constants'
import type { ageView, linkView, roverView } from '../model/presenters'
import type { OutageSpan, PacketMark } from '../model/types'
import { drawReceptionStrip } from '../map/receptionStrip'

type RoverProps = {
  rover: ReturnType<typeof roverView>
  age: ReturnType<typeof ageView>
  /** Interrupted transport or stale telemetry: last known position and dimmed values. */
  stale: boolean
  blackout: boolean
}

export function RoverPanel({ rover, age, stale, blackout }: RoverProps) {
  const head = stale
    ? { label: 'LAST KNOWN POSITION', color: blackout ? MC_COLORS.red : MC_COLORS.amber, value: MC_COLORS.steel }
    : { label: 'ROVER', color: MC_COLORS.kicker, value: MC_COLORS.text }
  const r = rover
  return (
    <section className="mc-section mc-section--rover" aria-label="Rover">
      <div className="mc-rover__head">
        <span style={{ color: head.color }}>{head.label}</span>
        <span className="mc-rover__seq">SEQ {r?.seq ?? '—'}</span>
      </div>
      <span className="mc-rover__id">{r?.id ?? 'awaiting rover'}</span>
      <div className="mc-enu">
        {([['EAST', r?.e], ['NORTH', r?.n], ['UP', r?.u]] as const).map(([axis, v]) => (
          <div key={axis} className="mc-enu__cell">
            <span className="mc-enu__axis">{axis}</span>
            <span className="mc-enu__value" style={{ color: head.value }}>{v ?? '—'}</span>
          </div>
        ))}
      </div>
      <dl className="mc-kv" style={{ margin: 0 }}>
        <dt>Position ±</dt><dd>{r?.unc ?? '—'}</dd>
        <dt>Course (derived)</dt><dd>{r?.cog ?? '—'}</dd>
        <dt>Capture · rover</dt><dd>{r?.captured ?? '—'}</dd>
        <dt>Receipt · MC</dt><dd>{r?.received ?? '—'}</dd>
        <dt>Rx − capture</dt><dd style={{ color: r?.late ? MC_COLORS.amber : undefined }}>{r?.latency ?? '—'}</dd>
      </dl>
      <div className="mc-age">
        <div className="mc-age__head"><span>INFORMATION AGE</span><span style={{ color: age.color }}>{age.state}</span></div>
        <div className="mc-age__readout">
          <span className="mc-age__value" style={{ color: age.color }}>{age.value}</span>
          <span className="mc-age__unit">s since last<br />accepted frame</span>
        </div>
        <div className="mc-age__bar">
          <div className="mc-age__fill" style={{ width: `${age.pct}%`, background: age.color, boxShadow: `0 0 10px ${age.color}` }} />
          <div className="mc-age__tick" style={{ left: `${age.degradedPct}%` }} />
        </div>
        <div className="mc-age__scale"><span>degraded @ {age.degradedS} s</span><span>stale @ {age.staleS} s</span></div>
      </div>
    </section>
  )
}

type CommsProps = { link: ReturnType<typeof linkView>; packets: PacketMark[]; spans: OutageSpan[]; nowMs: number }

export function CommsPanel({ link, packets, spans, nowMs }: CommsProps) {
  const stripRef = useRef<HTMLCanvasElement>(null)
  useEffect(() => {
    if (stripRef.current) drawReceptionStrip(stripRef.current, packets, spans, nowMs, THRESHOLDS.stripWindowMs)
  }, [packets, spans, nowMs])
  return (
    <section className="mc-section" aria-label="Communications">
      <span className="mc-kicker">COMMUNICATIONS</span>
      <div className="mc-link">
        <div className="mc-link__cell">
          <span className="mc-link__label">MC TRANSPORT</span>
          <span className="mc-link__status" style={{ color: link.transport.color }}><span className="mc-link__dot" style={{ background: link.transport.color }} />{link.transport.label}</span>
          <span className="mc-link__meta">{link.transport.since}</span>
        </div>
        <div className="mc-link__cell">
          <span className="mc-link__label">ROVER LINK · REPORTED</span>
          <span className="mc-link__status" style={{ color: link.rover.color }}><span className="mc-link__dot" style={{ border: `1px solid ${link.rover.color}` }} />{link.rover.label}</span>
          <span className="mc-link__meta">{link.rover.asOf}</span>
        </div>
      </div>
      {link.mismatch && <div className="mc-link__warn">The rover's last report predates the station transport interruption. Current radio status is unknown.</div>}
      <div className="mc-strip">
        <div className="mc-strip__head"><span>RECEPTION · 60 s</span><span>YIELD {link.yieldText}</span></div>
        <canvas ref={stripRef} className="mc-strip__canvas" aria-hidden="true" />
        <div className="mc-strip__legend">
          <span><span className="mc-strip__key" style={{ background: MC_COLORS.cyan }} />accepted</span>
          <span><span className="mc-strip__key" style={{ background: MC_COLORS.amber }} />late</span>
          <span><span className="mc-strip__key" style={{ background: MC_COLORS.steel }} />dup</span>
          <span><span className="mc-strip__key" style={{ background: MC_COLORS.red }} />invalid</span>
          <span><span className="mc-strip__key mc-strip__key--down" />transport down</span>
        </div>
      </div>
    </section>
  )
}

type PacketProps = {
  received: number; accepted: number; invalid: number; duplicates: number; outOfOrder: number; sequenceGaps: number
  rover: { sent: number; lost: number; seq: number } | null
}

export function PacketPanel({ received, accepted, invalid, duplicates, outOfOrder, sequenceGaps, rover }: PacketProps) {
  const T = MC_COLORS.text
  const counters: [string, number, string][] = [
    ['RECEIVED', received, T], ['ACCEPTED', accepted, MC_COLORS.cyan], ['INVALID', invalid, invalid ? MC_COLORS.red : T],
    ['DUPLICATE', duplicates, duplicates ? MC_COLORS.silver : T], ['OUT-OF-ORDER', outOfOrder, outOfOrder ? MC_COLORS.amber : T],
    ['SEQ GAPS*', sequenceGaps, sequenceGaps ? MC_COLORS.amber : T],
  ]
  return (
    <section className="mc-section" aria-label="Packet accounting">
      <span className="mc-kicker">PACKET ACCOUNTING</span>
      <div className="mc-counters">
        {counters.map(([label, value, color]) => (
          <div key={label} className="mc-counter">
            <span className="mc-counter__label" title={label === 'SEQ GAPS*' ? 'Inferred from accepted sequence numbers; not a definitive lost-packet count' : undefined}>{label}</span>
            <span className="mc-counter__value" style={{ color }}>{value}</span>
          </div>
        ))}
      </div>
      <div className="mc-rover-counters">
        <div className="mc-rover-counters__head"><span>ROVER-REPORTED</span><span>{rover ? `AS OF SEQ ${rover.seq}` : ''}</span></div>
        <div className="mc-rover-counters__values">
          <span><i>sent </i>{rover?.sent ?? '—'}</span>
          <span><i>lost </i>{rover?.lost ?? '—'}</span>
          <span><i>loss </i>{rover ? ((rover.sent ? (rover.lost / rover.sent) * 100 : 0).toFixed(1) + '%') : '—'}</span>
        </div>
      </div>
    </section>
  )
}
