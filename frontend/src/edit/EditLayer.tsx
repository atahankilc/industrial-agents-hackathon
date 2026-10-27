// The Edit mode's handles, on the building model itself. An SVG over the plan canvas whose group `align` PlanView
// keeps in register with the current floor's plane (src/plan/PlanView.tsx Align), so everything here is drawn in
// building metres (x east, y north) and turns, tilts and zooms with the model. The model stays the picture (it is
// the draft's plan, redrawn after every change); this layer only adds what you grab:
// - the selected room's outline, its corners (move_vertex) and walls (move_edge), with a live readout;
// - every door on the floor (select, drag along its wall: move_opening); the selected item (drag: move_asset);
// - the Door / Item tools' ghost under the pointer (edit/place.ts) — the click itself is the plan's tap
//   (PlanView onTap → BuildingScreen), so panning, zooming and turning the model keep working while placing;
// - the Builder's proposal as a dashed ghost, and what the validator flags in red;
// - with the Access tool, the rooms only some groups may enter, hatched (src/access/useAccessRules.ts).
// Handles keep their screen size: strokes don't scale, and a corner is a round-capped stroke of almost no length.

import { useEffect, useMemo, useState } from 'react'
import type { BuildingJson, Issue, OpeningJson, Op } from '../api'
import { adjustTrace, area, GRID_M, nearestEdge, outwardNormals, round3, samePoint, snap, traceAt, traceMatrix, type XY } from './geometry'
import { DOOR_WIDTH_M, doorSpot as doorSpotFor, REACH_PX, roomAt as roomFor } from './place'
import type { ItemPreset, Selection, Tool } from './types'

type Props = {
  building: BuildingJson
  floorId: string
  issues: Issue[]
  selected: Selection
  onSelect: (selection: Selection) => void
  onOps: (ops: Op[]) => void
  busy: boolean
  revision: number // bumped on every op response (applied or refused)
  ghost: BuildingJson | null // the Builder's proposal
  tool: Tool
  preset: ItemPreset
  align: React.RefObject<SVGGElement | null> // kept on the floor plane by PlanView
  restricted?: Set<string> // the Access tool: spaces only some groups may enter
  /** the import's plan of this floor, drawn faintly under everything ("trace underneath"); image px → metres */
  /** `adjust`: the trace takes the pointer — drag it, turn it (round handle) or resize it (square handle) onto the
   * rooms; each change is the edit op `set_reference` */
  trace?: { image: string; width: number; height: number; transform: number[][]; opacity: number; adjust?: boolean } | null
}

type TraceDrag = { kind: 'move' | 'turn' | 'scale'; from: XY; base: number[][]; centre: XY }
const HANDLE_PX = 11

type Drag =
  | { kind: 'vertex'; from: XY; to: XY }
  | { kind: 'edge'; spaceId: string; a: XY; b: XY; normal: XY; start: XY; offset: number }
  | { kind: 'opening'; id: string; to: XY; a: XY; b: XY }
  | { kind: 'asset'; id: string; to: XY; offset: XY }

const DOT = 0.0001 // a corner handle: a round-capped stroke this long (metres)

const pts = (polygon: XY[]) => polygon.map(([x, y]) => `${x},${y}`).join(' ')

/** A door's width drawn along edge a–b, centred on `at`. */
function along(at: XY, a: XY, b: XY, width: number): [XY, XY] {
  const length = Math.hypot(b[0] - a[0], b[1] - a[1]) || 1
  const ux = (b[0] - a[0]) / length
  const uy = (b[1] - a[1]) / length
  return [[at[0] - (ux * width) / 2, at[1] - (uy * width) / 2], [at[0] + (ux * width) / 2, at[1] + (uy * width) / 2]]
}

function doorSegment(opening: OpeningJson, polygonOf: (id: string) => XY[] | undefined): [XY, XY] {
  const inner = opening.space_ids.find((id) => id !== 'outside')
  const polygon = inner ? polygonOf(inner) : undefined
  const [x, y] = opening.position
  if (!polygon) return [[x - opening.width_m / 2, y], [x + opening.width_m / 2, y]]
  const { a, b } = nearestEdge(opening.position, polygon)
  return along(opening.position, a, b, opening.width_m)
}

export function EditLayer({ building, floorId, issues, selected, onSelect, onOps, busy, revision, ghost, tool, preset, align, restricted, trace }: Props) {
  const [drag, setDrag] = useState<Drag | null>(null)
  // A dropped edit stays drawn where it was dropped until the backend's answer arrives.
  const [sent, setSent] = useState<Drag | null>(null)
  useEffect(() => setSent(null), [revision])
  const [pointer, setPointer] = useState<XY | null>(null) // building metres under the pointer, for the placing ghosts
  // the trace being moved / turned / resized, and where it lies until the draft has the change
  const [traceDrag, setTraceDrag] = useState<TraceDrag | null>(null)
  const [tracePreview, setTracePreview] = useState<number[][] | null>(null)
  const traceKey = trace ? JSON.stringify(trace.transform) : ''
  useEffect(() => setTracePreview(null), [traceKey, revision])

  const spaces = useMemo(() => building.spaces.filter((space) => space.floor_id === floorId), [building, floorId])
  const openings = useMemo(() => building.openings.filter((item) => item.floor_id === floorId), [building, floorId])
  const polygons = useMemo(() => new Map(spaces.map((space) => [space.id, space.polygon as XY[]])), [spaces])
  const vertices = useMemo(() => spaces.flatMap((space) => space.polygon as XY[]), [spaces])
  const bad = useMemo(() => new Set(issues.filter((item) => item.severity === 'error').flatMap((item) => item.ids)), [issues])

  /** client pixels → building metres on the floor plane, and how many pixels a metre is there */
  const toBuilding = (x: number, y: number): XY | null => {
    const matrix = align.current?.getScreenCTM()
    if (!matrix) return null
    const point = new DOMPoint(x, y).matrixTransform(matrix.inverse())
    return [point.x, point.y]
  }
  const pixelsPerMetre = () => {
    const m = align.current?.getScreenCTM()
    return m ? Math.max(1e-6, Math.min(Math.hypot(m.a, m.b), Math.hypot(m.c, m.d))) : 10
  }

  const doorSpotAt = (p: XY) => doorSpotFor(building, floorId, p, REACH_PX / pixelsPerMetre())
  const roomAt = (p: XY) => roomFor(building, floorId, p)

  // Placing tools: follow the pointer without taking events from the model (pan / zoom / turn keep working).
  useEffect(() => {
    if (tool !== 'door' && tool !== 'item') {
      setPointer(null)
      return
    }
    const onMove = (event: PointerEvent) => {
      if (event.pointerType === 'mouse') setPointer(toBuilding(event.clientX, event.clientY))
    }
    window.addEventListener('pointermove', onMove, { passive: true })
    return () => window.removeEventListener('pointermove', onMove)
  }, [tool]) // eslint-disable-line react-hooks/exhaustive-deps -- toBuilding only reads the align ref

  const begin = (event: React.PointerEvent, next: Drag) => {
    event.stopPropagation()
    if (busy) return
    ;(event.currentTarget as Element).setPointerCapture(event.pointerId)
    setDrag(next)
  }
  const traceNow = trace ? tracePreview ?? trace.transform : null
  const beginTrace = (event: React.PointerEvent, kind: TraceDrag['kind']) => {
    event.stopPropagation()
    const from = toBuilding(event.clientX, event.clientY)
    if (busy || !trace || !traceNow || !from) return
    ;(event.currentTarget as Element).setPointerCapture(event.pointerId)
    setTraceDrag({ kind, from, base: traceNow, centre: traceAt(traceNow, trace.width / 2, trace.height / 2) })
  }
  const onPointerMove = (event: React.PointerEvent) => {
    if (traceDrag) {
      const p = toBuilding(event.clientX, event.clientY)
      if (!p) return
      const { kind, from, base, centre } = traceDrag
      const angleOf = (q: XY) => Math.atan2(q[1] - centre[1], q[0] - centre[0])
      setTracePreview(kind === 'move'
        ? adjustTrace(base, { dx: p[0] - from[0], dy: p[1] - from[1] })
        : kind === 'turn'
          ? adjustTrace(base, { angle: angleOf(p) - angleOf(from), centre })
          : adjustTrace(base, { scale: Math.min(5, Math.max(0.2, Math.hypot(p[0] - centre[0], p[1] - centre[1]) / Math.max(1e-6, Math.hypot(from[0] - centre[0], from[1] - centre[1])))), centre }))
      return
    }
    if (!drag) return
    const p = toBuilding(event.clientX, event.clientY)
    if (!p) return
    if (drag.kind === 'vertex') {
      setDrag({ ...drag, to: snap(p, vertices.filter((vertex) => !samePoint(vertex, drag.from))) })
    } else if (drag.kind === 'edge') {
      const raw = (p[0] - drag.start[0]) * drag.normal[0] + (p[1] - drag.start[1]) * drag.normal[1]
      setDrag({ ...drag, offset: round3(Math.round(raw / GRID_M) * GRID_M) })
    } else if (drag.kind === 'opening') {
      const { point } = nearestEdge(p, [drag.a, drag.b])
      setDrag({ ...drag, to: [round3(point[0]), round3(point[1])] })
    } else {
      setDrag({ ...drag, to: snap([p[0] - drag.offset[0], p[1] - drag.offset[1]], [], 0.05, 0) })
    }
  }
  const onPointerUp = () => {
    if (traceDrag) {
      setTraceDrag(null)
      if (tracePreview && JSON.stringify(tracePreview) !== JSON.stringify(trace?.transform)) {
        onOps([{ op: 'set_reference', floor_id: floorId, transform: tracePreview }])
      }
      return
    }
    if (!drag) return
    const send = (ops: Op[]) => {
      setSent(drag)
      onOps(ops)
    }
    if (drag.kind === 'vertex' && !samePoint(drag.from, drag.to, 0.001)) {
      send([{ op: 'move_vertex', floor_id: floorId, from_xy: drag.from, to_xy: drag.to }])
    } else if (drag.kind === 'edge' && Math.abs(drag.offset) >= 0.001) {
      send([{ op: 'move_edge', space_id: drag.spaceId, edge: [drag.a, drag.b], offset_m: drag.offset }])
    } else if (drag.kind === 'opening') {
      const opening = building.openings.find((item) => item.id === drag.id)
      if (opening && !samePoint(opening.position, drag.to, 0.001)) send([{ op: 'move_opening', opening_id: drag.id, position: drag.to }])
    } else if (drag.kind === 'asset') {
      const asset = building.assets.find((item) => item.id === drag.id)
      if (asset && !samePoint(asset.position, drag.to, 0.001)) send([{ op: 'move_asset', asset_id: drag.id, position: drag.to }])
    }
    setDrag(null)
  }

  // Local preview of the drag in progress, or of the edit sent and not yet answered: corners that move.
  const shown = drag ?? sent
  const moves: [XY, XY][] =
    shown?.kind === 'vertex' ? [[shown.from, shown.to]]
    : shown?.kind === 'edge' ? [shown.a, shown.b].map((corner): [XY, XY] => [corner, [corner[0] + shown.normal[0] * shown.offset, corner[1] + shown.normal[1] * shown.offset]])
    : []
  const polygonOf = (id: string): XY[] => {
    const polygon = polygons.get(id) ?? []
    return moves.length === 0 ? polygon : polygon.map((vertex) => moves.find(([from]) => samePoint(vertex, from))?.[1] ?? vertex)
  }
  const moved = new Set(moves.length ? spaces.filter((space) => (space.polygon as XY[]).some((v) => moves.some(([from]) => samePoint(v, from)))).map((s) => s.id) : [])

  // What the open proposal would change on this floor.
  const proposed = useMemo(() => {
    if (!ghost) return null
    const differs = <T extends { id: string; floor_id: string }>(after: T[], before: T[]) => {
      const old = new Map(before.map((item) => [item.id, JSON.stringify(item)]))
      return after.filter((item) => item.floor_id === floorId && old.get(item.id) !== JSON.stringify(item))
    }
    return {
      spaces: differs(ghost.spaces, building.spaces),
      openings: differs(ghost.openings, building.openings),
      assets: differs(ghost.assets, building.assets),
      polygons: new Map(ghost.spaces.map((space) => [space.id, space.polygon as XY[]])),
    }
  }, [ghost, building, floorId])

  const selecting = tool === 'select'
  const selectedSpace = selected?.kind === 'space' ? spaces.find((space) => space.id === selected.id) : undefined
  const selectedAsset = selected?.kind === 'asset' ? building.assets.find((item) => item.id === selected.id && item.floor_id === floorId) : undefined
  const original = selectedSpace ? (selectedSpace.polygon as XY[]) : []
  const normals = selectedSpace ? outwardNormals(original) : []
  const doorSpot = tool === 'door' && pointer ? doorSpotAt(pointer) : null
  const itemRoom = tool === 'item' && pointer ? roomAt(pointer) : null

  // readout next to what is being dragged, in screen pixels (outside the aligned group, so it stays upright)
  let readout: { at: XY; text: string } | null = null
  if (drag && selectedSpace && (drag.kind === 'vertex' || drag.kind === 'edge')) {
    const anchor: XY = drag.kind === 'vertex' ? drag.to : (() => {
      const [a, b] = moves.map(([, to]) => to)
      return [(a[0] + b[0]) / 2, (a[1] + b[1]) / 2]
    })()
    const m = align.current?.getCTM()
    if (m) {
      const p = new DOMPoint(anchor[0], anchor[1]).matrixTransform(m)
      const size = `${area(polygonOf(selectedSpace.id)).toFixed(1)} m²`
      readout = { at: [p.x, p.y], text: drag.kind === 'edge' ? `${drag.offset >= 0 ? '+' : '−'}${Math.abs(drag.offset).toFixed(2)} m · ${size}` : size }
    }
  }

  return (
    <svg className={`edit-layer tool-${tool}${busy ? ' busy' : ''}`} onPointerMove={onPointerMove} onPointerUp={onPointerUp} onPointerCancel={() => setDrag(null)}>
      <g ref={align}>
        {trace && traceNow && (
          <image
            className={`trace${trace.adjust ? ' adjusting' : ''}`} href={trace.image} width={trace.width} height={trace.height}
            transform={traceMatrix(traceNow)} opacity={trace.opacity} preserveAspectRatio="none"
            pointerEvents={trace.adjust ? 'all' : 'none'} onPointerDown={trace.adjust ? (event) => beginTrace(event, 'move') : undefined}
          />
        )}
        {trace?.adjust && traceNow && (() => {
          const corners = [[0, 0], [trace.width, 0], [trace.width, trace.height], [0, trace.height]].map(([u, v]) => traceAt(traceNow, u, v))
          const m = align.current?.getScreenCTM()
          // the larger axis: on a tilted floor the smaller one squashes the handle to a sliver
          const r = HANDLE_PX / (m ? Math.max(1e-6, Math.hypot(m.a, m.b), Math.hypot(m.c, m.d)) : 10) * 1.6
          const [sx, sy] = corners[2]
          const [tx, ty] = traceAt(traceNow, trace.width / 2, 0)
          return (
            <g className="trace-handles">
              <polygon points={pts(corners)} />
              <rect x={sx - r} y={sy - r} width={2 * r} height={2 * r} onPointerDown={(event) => beginTrace(event, 'scale')}>
                <title>Resize the plan</title>
              </rect>
              <circle cx={tx} cy={ty} r={r} onPointerDown={(event) => beginTrace(event, 'turn')}>
                <title>Turn the plan</title>
              </circle>
            </g>
          )
        })()}
        {/* the Access tool: restricted rooms, hatched (the pattern in metres, so it turns and zooms with the plan) */}
        {tool === 'access' && restricted && (
          <>
            <defs>
              <pattern id="access-hatch" className="access-hatch" patternUnits="userSpaceOnUse" width="0.7" height="0.7" patternTransform="rotate(45)">
                <rect width="0.7" height="0.7" fill="transparent" />
                <line x1="0" y1="0" x2="0" y2="0.7" />
              </pattern>
            </defs>
            {spaces.filter((space) => restricted.has(space.id)).map((space) => (
              <polygon key={`locked-${space.id}`} className="restricted-space" points={pts(space.polygon as XY[])} />
            ))}
          </>
        )}
        {/* what the validator flags */}
        {spaces.filter((space) => bad.has(space.id)).map((space) => (
          <polygon key={`bad-${space.id}`} className="bad-space" points={pts(space.polygon as XY[])} />
        ))}
        {/* rooms reshaped by the drag in progress (the model shows them once the backend has them) */}
        {[...moved].filter((id) => id !== selectedSpace?.id).map((id) => (
          <polygon key={`moved-${id}`} className="moved-space" points={pts(polygonOf(id))} />
        ))}
        {selectedSpace && <polygon className="selected-space" points={pts(polygonOf(selectedSpace.id))} />}

        {/* doors: the selected one drawn, every one grabbable */}
        {openings.map((raw) => {
          const opening = shown?.kind === 'opening' && shown.id === raw.id ? { ...raw, position: shown.to } : raw
          const [a, b] = doorSegment(opening, (id) => polygonOf(id))
          const isSelected = selected?.id === opening.id
          return (
            <g key={opening.id}>
              {(isSelected || bad.has(opening.id)) && (
                <line className={`door-mark${isSelected ? ' selected' : ''}${bad.has(opening.id) ? ' bad' : ''}`} x1={a[0]} y1={a[1]} x2={b[0]} y2={b[1]} />
              )}
              {selecting && (
                <line
                  className="door-hit"
                  x1={a[0]} y1={a[1]} x2={b[0]} y2={b[1]}
                  onPointerDown={(event) => {
                    onSelect({ kind: 'opening', id: opening.id })
                    const inner = opening.space_ids.find((id) => id !== 'outside')
                    const polygon = inner ? polygons.get(inner) : undefined
                    if (!polygon) return
                    const edge = nearestEdge(opening.position, polygon)
                    begin(event, { kind: 'opening', id: opening.id, to: opening.position, a: edge.a, b: edge.b })
                  }}
                >
                  <title>{`${opening.kind} · ${opening.width_m} m — drag along the wall`}</title>
                </line>
              )}
            </g>
          )
        })}

        {/* the selected item: grab it to move it */}
        {selecting && selectedAsset && (() => {
          const asset = shown?.kind === 'asset' && shown.id === selectedAsset.id ? { ...selectedAsset, position: shown.to } : selectedAsset
          const { width_m: w, depth_m: d, rotation_deg: r } = asset.footprint
          return (
            <g transform={`translate(${asset.position[0]} ${asset.position[1]}) rotate(${r})`}>
              <rect
                className="selected-asset"
                x={-w / 2} y={-d / 2} width={w} height={d}
                onPointerDown={(event) => {
                  const p = toBuilding(event.clientX, event.clientY)
                  if (p) begin(event, { kind: 'asset', id: asset.id, to: asset.position, offset: [p[0] - asset.position[0], p[1] - asset.position[1]] })
                }}
              >
                <title>Drag to move · R turns</title>
              </rect>
            </g>
          )
        })()}

        {/* the selected room's walls and corners */}
        {selecting && selectedSpace && original.map((corner, i) => {
          const next = original[(i + 1) % original.length]
          const [a, b] = [polygonOf(selectedSpace.id)[i], polygonOf(selectedSpace.id)[(i + 1) % original.length]]
          const normal = normals[i]
          const active = drag?.kind === 'edge' && samePoint(drag.a, corner) && samePoint(drag.b, next)
          return (
            <line
              key={`edge-${i}`}
              className={`edge-handle${active ? ' active' : ''}`}
              x1={a[0]} y1={a[1]} x2={b[0]} y2={b[1]}
              onPointerDown={(event) => {
                const start = toBuilding(event.clientX, event.clientY)
                if (start) begin(event, { kind: 'edge', spaceId: selectedSpace.id, a: corner, b: next, normal, start, offset: 0 })
              }}
            >
              <title>Drag to move this wall</title>
            </line>
          )
        })}
        {selecting && selectedSpace && polygonOf(selectedSpace.id).map((vertex, i) => (
          <g key={`corner-${i}`} className="corner" onPointerDown={(event) => begin(event, { kind: 'vertex', from: original[i], to: original[i] })}>
            <line className="corner-ring" x1={vertex[0]} y1={vertex[1]} x2={vertex[0] + DOT} y2={vertex[1]} />
            <line className="corner-dot" x1={vertex[0]} y1={vertex[1]} x2={vertex[0] + DOT} y2={vertex[1]} />
            <title>Drag to move this corner</title>
          </g>
        ))}

        {/* the Builder's proposal */}
        {proposed && (
          <g className="proposal">
            {proposed.spaces.map((space) => <polygon key={space.id} className="ghost-space" points={pts(space.polygon as XY[])} />)}
            {proposed.assets.map((asset) => (
              <g key={asset.id} transform={`translate(${asset.position[0]} ${asset.position[1]}) rotate(${asset.footprint.rotation_deg})`}>
                <rect className="ghost-asset" x={-asset.footprint.width_m / 2} y={-asset.footprint.depth_m / 2} width={asset.footprint.width_m} height={asset.footprint.depth_m} />
              </g>
            ))}
            {proposed.openings.map((opening) => {
              const [a, b] = doorSegment(opening, (id) => proposed.polygons.get(id))
              return <line key={opening.id} className="ghost-door" x1={a[0]} y1={a[1]} x2={b[0]} y2={b[1]} />
            })}
          </g>
        )}

        {/* placing */}
        {doorSpot && (() => {
          const [a, b] = along(doorSpot.position, doorSpot.a, doorSpot.b, DOOR_WIDTH_M)
          return <line className="ghost-door placing" x1={a[0]} y1={a[1]} x2={b[0]} y2={b[1]} />
        })()}
        {itemRoom && <polygon className="target-space" points={pts(itemRoom.polygon as XY[])} />}
        {tool === 'item' && pointer && (
          <rect className={`ghost-item${itemRoom ? '' : ' nowhere'}`} x={pointer[0] - preset.width_m / 2} y={pointer[1] - preset.depth_m / 2}
            width={preset.width_m} height={preset.depth_m} />
        )}
      </g>
      {readout && (
        <text className="readout" x={readout.at[0] + 14} y={readout.at[1] - 14}>{readout.text}</text>
      )}
    </svg>
  )
}
