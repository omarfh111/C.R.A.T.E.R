import { useId, useState } from 'react'
import { HAZARD_STYLE } from '../model/constants'
import type { MapModel, MapViewport } from '../model/types'
import { MINIMAP_SIZE, miniMapProjection, miniMapTrail } from './minimapGeometry'

export function MiniMap({ model, viewport, compact, onFit }: {
  model: MapModel; viewport: MapViewport | null; compact: boolean; onFit: () => void
}) {
  const clipId = useId()
  const [expanded, setExpanded] = useState<boolean | null>(null)
  const open = expanded ?? !compact
  const points: { x: number; y: number }[] = [...model.trail, ...model.hazards]
  if (model.rover) {
    const r = model.rover
    points.push({ x: r.x - r.unc, y: r.y - r.unc }, { x: r.x + r.unc, y: r.y + r.unc })
  }
  const { project, spanM, scale } = miniMapProjection(points)
  const trail = miniMapTrail(model.layers.trail ? model.trail : [], project)
  const hazards = model.hazards.filter(h => model.filters[h.type] && h.confidence >= model.minConfidence)
  const rover = model.rover && project(model.rover)
  const topLeft = viewport && project({ x: viewport.minX, y: viewport.maxY })
  const origin = project({ x: 0, y: 0 })
  const lastKnown = ['STALE', 'BLACKOUT', 'TRANSPORT_DOWN'].includes(model.posture)

  return <section className="mc-minimap" aria-label="Mission minimap" data-expanded={open}>
    <button className="mc-minimap__toggle" type="button" aria-label="Toggle mission minimap" aria-expanded={open} aria-controls={`${clipId}-body`} onClick={() => setExpanded(!open)}>
      <span>MINIMAP</span><span aria-hidden="true">{open ? '−' : '+'}</span>
    </button>
    {open && <div className="mc-minimap__body" id={`${clipId}-body`}>
      <div className={`mc-minimap__status${lastKnown ? ' mc-minimap__status--aged' : ''}`}>
        {model.rover ? `${lastKnown ? 'LAST KNOWN' : 'ACCEPTED FIX'} · ${model.rover.seq}` : 'NO ACCEPTED FIX'}
      </div>
      <svg viewBox={`0 0 ${MINIMAP_SIZE} ${MINIMAP_SIZE}`} role="img" aria-label="North-up overview of accepted telemetry in LOCAL_ENU_V1 meters">
        <defs><clipPath id={clipId}><rect width={MINIMAP_SIZE} height={MINIMAP_SIZE} /></clipPath></defs>
        <path className="mc-minimap__grid" d="M40,0V160M80,0V160M120,0V160M0,40H160M0,80H160M0,120H160" />
        <g clipPath={`url(#${clipId})`}>
          {topLeft && viewport && <rect className="mc-minimap__viewport" x={topLeft.x} y={topLeft.y} width={(viewport.maxX - viewport.minX) * scale} height={(viewport.maxY - viewport.minY) * scale}><title>Current tactical map viewport</title></rect>}
          <path className="mc-minimap__trail" d={trail.observed} />
          <path className="mc-minimap__gap" d={trail.gaps}><title>Sequence gaps: path unobserved</title></path>
          <path className="mc-minimap__origin" d={`M${origin.x - 3},${origin.y}h6M${origin.x},${origin.y - 3}v6`}><title>LOCAL_ENU_V1 origin, start marker</title></path>
          {hazards.map(h => {
            const p = project(h), selected = h.key === model.selectedKey
            const shape = h.type === 'crater' ? `M${p.x - 2.5},${p.y}a2.5,2.5 0 1,0 5,0a2.5,2.5 0 1,0 -5,0`
              : h.type === 'rock' ? `M${p.x},${p.y - 3}l3,3l-3,3l-3,-3Z`
                : h.type === 'slope' ? `M${p.x},${p.y - 3}l3,5h-6Z` : `M${p.x - 2.5},${p.y - 2.5}h5v5h-5Z`
            return <g key={h.key}>
              <path d={shape} fill={h.type === 'crater' ? 'none' : HAZARD_STYLE[h.type].color} stroke={HAZARD_STYLE[h.type].color}><title>{`${h.id}: E ${h.x} m, N ${h.y} m; uncertainty radius ${h.unc} m`}</title></path>
              {selected && <circle className="mc-minimap__selection" cx={p.x} cy={p.y} r="6"><title>{`Selected hazard: ${h.id}`}</title></circle>}
            </g>
          })}
          {rover && model.rover && <g className="mc-minimap__rover">
            {model.layers.unc && <circle className="mc-minimap__uncertainty" cx={rover.x} cy={rover.y} r={model.rover.unc * scale} />}
            <circle cx={rover.x} cy={rover.y} r="3.5"><title>{`${model.rover.roverId}: E ${model.rover.x} m, N ${model.rover.y} m; uncertainty radius ${model.rover.unc} m`}</title></circle>
          </g>}
        </g>
        <text className="mc-minimap__north" x="148" y="13">N ↑</text>
      </svg>
      <div className="mc-minimap__footer"><span>{spanM.toFixed(1)} m span</span><button type="button" disabled={!model.rover && !points.length} onClick={onFit}>FIT MISSION</button></div>
      <p>Accepted telemetry · dashed trail = gap</p>
    </div>}
  </section>
}
