// 2D plan of one floor for the Edit mode: spaces, doors and assets in an SVG (building y up → SVG y down).
// Click selects; drag a selected room's corner (move_vertex), a door along its wall (move_opening) or an asset
// (move_asset); R / Shift+R rotates the selected asset. Drags are previewed locally and sent as one op on drop;
// the backend applies, snaps and validates (core/edits.py, core/validate.py). Wheel zooms, dragging empty space pans.

import { useEffect, useMemo, useRef, useState } from 'react'
import type { AssetJson, BuildingJson, Issue, OpeningJson, Op } from '../api'
import { area, bounds, centroid, nearestEdge, round3, samePoint, snap, svgPoints, type XY } from './geometry'

export type Selection = { kind: 'space' | 'opening' | 'asset'; id: string } | null

type Props = {
  building: BuildingJson
  floorId: string
  issues: Issue[]
  selected: Selection
  onSelect: (selection: Selection) => void
  onOps: (ops: Op[]) => void
}

type View = { x: number; y: number; w: number; h: number }
type Drag =
  | { kind: 'vertex'; from: XY; to: XY; spaceIds: string[] }
  | { kind: 'opening'; id: string; to: XY; a: XY; b: XY }
  | { kind: 'asset'; id: string; to: XY; offset: XY }
  | { kind: 'pan'; start: XY; view: View; moved: boolean; select: Selection }

const PAD_M = 2
const ROTATE_STEP_DEG = 15

function fitView(polygons: XY[][], aspect: number): View {
  if (polygons.length === 0) return { x: -10, y: -10, w: 20, h: 20 }
  const box = bounds(polygons)
  let w = box.maxX - box.minX + 2 * PAD_M
  let h = box.maxY - box.minY + 2 * PAD_M
  if (w / h > aspect) h = w / aspect
  else w = h * aspect
  const cx = (box.minX + box.maxX) / 2
  const cy = -(box.minY + box.maxY) / 2
  return { x: cx - w / 2, y: cy - h / 2, w, h }
}

function doorSegment(opening: OpeningJson, polygonOf: (id: string) => XY[] | undefined): [XY, XY] {
  const inside = opening.space_ids.find((id) => id !== 'outside')
  const polygon = inside ? polygonOf(inside) : undefined
  const [x, y] = opening.position
  if (!polygon) return [[x - opening.width_m / 2, y], [x + opening.width_m / 2, y]]
  const { a, b } = nearestEdge(opening.position, polygon)
  const length = Math.hypot(b[0] - a[0], b[1] - a[1]) || 1
  const ux = (b[0] - a[0]) / length
  const uy = (b[1] - a[1]) / length
  const half = opening.width_m / 2
  return [[x - ux * half, y - uy * half], [x + ux * half, y + uy * half]]
}

export function PlanEditor({ building, floorId, issues, selected, onSelect, onOps }: Props) {
  const svg = useRef<SVGSVGElement>(null)
  const [view, setView] = useState<View | null>(null)
  const [drag, setDrag] = useState<Drag | null>(null)

  const spaces = useMemo(() => building.spaces.filter((space) => space.floor_id === floorId), [building, floorId])
  const openings = useMemo(() => building.openings.filter((item) => item.floor_id === floorId), [building, floorId])
  const assets = useMemo(() => building.assets.filter((item) => item.floor_id === floorId), [building, floorId])
  const polygons = useMemo(() => new Map(spaces.map((space) => [space.id, space.polygon as XY[]])), [spaces])
  const vertices = useMemo(() => spaces.flatMap((space) => space.polygon as XY[]), [spaces])
  const bad = useMemo(() => new Set(issues.filter((item) => item.severity === 'error').flatMap((item) => item.ids)), [issues])

  // Fit the floor when it changes (not on every edit, so the view stays put while you work).
  useEffect(() => {
    const element = svg.current
    const aspect = element ? element.clientWidth / Math.max(1, element.clientHeight) : 1.5
    setView(fitView(spaces.map((space) => space.polygon as XY[]), aspect))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [floorId, building.building.id])

  // Wheel zoom around the pointer (non-passive so the page doesn't scroll).
  useEffect(() => {
    const element = svg.current
    if (!element) return
    const onWheel = (event: WheelEvent) => {
      event.preventDefault()
      setView((current) => {
        if (!current) return current
        const rect = element.getBoundingClientRect()
        const fx = (event.clientX - rect.left) / rect.width
        const fy = (event.clientY - rect.top) / rect.height
        const factor = Math.exp(event.deltaY * 0.0015)
        const w = Math.min(2000, Math.max(2, current.w * factor))
        const h = (current.h / current.w) * w
        return { x: current.x + fx * (current.w - w), y: current.y + fy * (current.h - h), w, h }
      })
    }
    element.addEventListener('wheel', onWheel, { passive: false })
    return () => element.removeEventListener('wheel', onWheel)
  }, [])

  // R / Shift+R rotates the selected asset.
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key.toLowerCase() !== 'r' || selected?.kind !== 'asset' || event.metaKey || event.ctrlKey) return
      if (event.target instanceof HTMLInputElement) return
      const asset = building.assets.find((item) => item.id === selected.id)
      if (!asset) return
      const step = event.shiftKey ? -ROTATE_STEP_DEG : ROTATE_STEP_DEG
      onOps([{ op: 'move_asset', asset_id: asset.id, position: asset.position, rotation_deg: asset.footprint.rotation_deg + step }])
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [selected, building, onOps])

  const toBuilding = (event: { clientX: number; clientY: number }): XY => {
    const element = svg.current!
    const matrix = element.getScreenCTM()!.inverse()
    const point = new DOMPoint(event.clientX, event.clientY).matrixTransform(matrix)
    return [point.x, -point.y]
  }

  const begin = (event: React.PointerEvent, next: Drag) => {
    event.stopPropagation()
    svg.current?.setPointerCapture(event.pointerId)
    setDrag(next)
  }

  const onPointerMove = (event: React.PointerEvent) => {
    if (!drag) return
    const p = toBuilding(event)
    if (drag.kind === 'vertex') {
      const others = vertices.filter((vertex) => !samePoint(vertex, drag.from))
      setDrag({ ...drag, to: snap(p, others) })
    } else if (drag.kind === 'opening') {
      const { point } = nearestEdge(p, [drag.a, drag.b])
      setDrag({ ...drag, to: [round3(point[0]), round3(point[1])] })
    } else if (drag.kind === 'asset') {
      setDrag({ ...drag, to: snap([p[0] - drag.offset[0], p[1] - drag.offset[1]], [], 0.05, 0) })
    } else if (drag.kind === 'pan' && view) {
      const rect = svg.current!.getBoundingClientRect()
      const dx = ((event.clientX - drag.start[0]) / rect.width) * drag.view.w
      const dy = ((event.clientY - drag.start[1]) / rect.height) * drag.view.h
      setView({ ...drag.view, x: drag.view.x - dx, y: drag.view.y - dy })
      if (Math.abs(dx) + Math.abs(dy) > 0.05) setDrag({ ...drag, moved: true })
    }
  }

  const onPointerUp = () => {
    if (!drag) return
    if (drag.kind === 'vertex' && !samePoint(drag.from, drag.to, 0.001)) {
      onOps([{ op: 'move_vertex', floor_id: floorId, from_xy: drag.from, to_xy: drag.to }])
    } else if (drag.kind === 'opening') {
      const opening = building.openings.find((item) => item.id === drag.id)
      if (opening && !samePoint(opening.position, drag.to, 0.001)) onOps([{ op: 'move_opening', opening_id: drag.id, position: drag.to }])
    } else if (drag.kind === 'asset') {
      const asset = building.assets.find((item) => item.id === drag.id)
      if (asset && !samePoint(asset.position, drag.to, 0.001)) onOps([{ op: 'move_asset', asset_id: drag.id, position: drag.to }])
    } else if (drag.kind === 'pan' && !drag.moved) {
      onSelect(drag.select) // a click, not a pan: select what was under the pointer (or nothing)
    }
    setDrag(null)
  }

  // Local preview of the drag in progress.
  const polygonOf = (id: string): XY[] => {
    const polygon = polygons.get(id) ?? []
    if (drag?.kind === 'vertex' && drag.spaceIds.includes(id)) {
      return polygon.map((vertex) => (samePoint(vertex, drag.from) ? drag.to : vertex))
    }
    return polygon
  }
  const openingAt = (opening: OpeningJson): OpeningJson =>
    drag?.kind === 'opening' && drag.id === opening.id ? { ...opening, position: drag.to } : opening
  const assetAt = (asset: AssetJson): AssetJson =>
    drag?.kind === 'asset' && drag.id === asset.id ? { ...asset, position: drag.to } : asset

  if (!view) return <svg ref={svg} className="plan" />
  const unit = view.w / 100 // ~1% of the view width, for handles and labels
  const selectedSpace = selected?.kind === 'space' ? spaces.find((space) => space.id === selected.id) : undefined
  const vertexDrag = drag?.kind === 'vertex' ? drag : null

  return (
    <svg
      ref={svg}
      className={`plan${drag?.kind === 'pan' ? ' panning' : ''}`}
      viewBox={`${view.x} ${view.y} ${view.w} ${view.h}`}
      onPointerDown={(event) => begin(event, { kind: 'pan', start: [event.clientX, event.clientY], view, moved: false, select: null })}
      onPointerMove={onPointerMove}
      onPointerUp={onPointerUp}
    >
      <g className="spaces">
        {spaces.map((space) => {
          const polygon = polygonOf(space.id)
          const classes = ['space', `type-${space.type}`, selected?.id === space.id ? 'selected' : '', bad.has(space.id) ? 'bad' : '']
          return (
            <polygon
              key={space.id}
              className={classes.join(' ')}
              points={svgPoints(polygon)}
              onPointerDown={(event) =>
                begin(event, { kind: 'pan', start: [event.clientX, event.clientY], view, moved: false, select: { kind: 'space', id: space.id } })
              }
            />
          )
        })}
      </g>
      <g className="assets">
        {assets.map((raw) => {
          const asset = assetAt(raw)
          const { width_m: w, depth_m: d, rotation_deg: r } = asset.footprint
          const classes = ['asset', selected?.id === asset.id ? 'selected' : '', bad.has(asset.id) ? 'bad' : '']
          return (
            <g key={asset.id} transform={`translate(${asset.position[0]} ${-asset.position[1]}) rotate(${-r})`}>
              <rect
                className={classes.join(' ')}
                x={-w / 2}
                y={-d / 2}
                width={w}
                height={d}
                onPointerDown={(event) => {
                  onSelect({ kind: 'asset', id: asset.id })
                  const p = toBuilding(event)
                  begin(event, { kind: 'asset', id: asset.id, to: asset.position, offset: [p[0] - asset.position[0], p[1] - asset.position[1]] })
                }}
              >
                <title>{asset.name}</title>
              </rect>
            </g>
          )
        })}
      </g>
      <g className="labels" style={{ fontSize: Math.min(unit * 1.4, 1.2) }}>
        {spaces.filter((space) => space.type !== 'corridor').map((space) => {
          const [x, y] = centroid(polygonOf(space.id))
          return (
            <text key={space.id} x={x} y={-y} textAnchor="middle" dominantBaseline="middle">
              {space.ref ?? space.name}
            </text>
          )
        })}
      </g>
      <g className="openings">
        {openings.map((raw) => {
          const opening = openingAt(raw)
          const [a, b] = doorSegment(opening, (id) => polygons.get(id))
          const classes = ['opening', `kind-${opening.kind}`, selected?.id === opening.id ? 'selected' : '', bad.has(opening.id) ? 'bad' : '']
          return (
            <line
              key={opening.id}
              className={classes.join(' ')}
              x1={a[0]}
              y1={-a[1]}
              x2={b[0]}
              y2={-b[1]}
              onPointerDown={(event) => {
                onSelect({ kind: 'opening', id: opening.id })
                const inside = opening.space_ids.find((id) => id !== 'outside')
                const polygon = inside ? polygons.get(inside) : undefined
                if (!polygon) return
                const edge = nearestEdge(opening.position, polygon)
                begin(event, { kind: 'opening', id: opening.id, to: opening.position, a: edge.a, b: edge.b })
              }}
            >
              <title>{`${opening.kind} · ${opening.width_m} m${opening.step_free ? '' : ' · step'}`}</title>
            </line>
          )
        })}
      </g>
      {selectedSpace && (
        <g className="handles">
          {polygonOf(selectedSpace.id).map((vertex, i) => (
            <circle
              key={i}
              className="handle"
              cx={vertex[0]}
              cy={-vertex[1]}
              r={unit * 0.9}
              onPointerDown={(event) => {
                const original = (selectedSpace.polygon as XY[])[i]
                const spaceIds = spaces.filter((space) => (space.polygon as XY[]).some((p) => samePoint(p, original))).map((space) => space.id)
                begin(event, { kind: 'vertex', from: original, to: original, spaceIds })
              }}
            />
          ))}
        </g>
      )}
      {vertexDrag && selectedSpace && (
        <text className="readout" x={vertexDrag.to[0] + unit * 1.5} y={-vertexDrag.to[1] - unit * 1.5} style={{ fontSize: unit * 1.6 }}>
          {`${vertexDrag.to[0].toFixed(2)}, ${vertexDrag.to[1].toFixed(2)} · ${area(polygonOf(selectedSpace.id)).toFixed(1)} m²`}
        </text>
      )}
    </svg>
  )
}
