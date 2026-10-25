// Edit mode's reference: the import's straightened plan of the floor being edited, beside the editor
// (docs/superpowers/specs/2026-10-25-plan-reference-and-location-design.md). Wheel zooms around the pointer, drag
// pans; the header holds the "trace underneath" switch and its opacity (EditLayer draws the trace).
import { Minus, Plus, RotateCcw, RotateCw, X } from 'lucide-react'
import { adjustTrace, traceAt } from './geometry'
import { useEffect, useRef, useState } from 'react'
import type { FloorReference } from '../api'

export type Trace = { on: boolean; opacity: number; adjust?: boolean } // adjust: move / turn / resize it on the plan

type Props = {
  reference: FloorReference | null
  floorName: string
  style: React.CSSProperties // where the panel sits (BuildingScreen keeps the edit card and the editor clear)
  trace: Trace
  onTrace: (trace: Trace) => void
  onClose: () => void
  /** the trace turned / resized by the buttons (about its centre): the new 2×3 transform of this floor's plan */
  onAdjust?: (transform: number[][]) => void
}

type View = { scale: number; x: number; y: number }
const FIT: View = { scale: 1, x: 0, y: 0 }

// where the user put the window and how wide (dragged by its header, resized by its corner); null: BuildingScreen's spot
type Box = { left: number; top: number; width: number }
const BOX_KEY = 'edit.referenceBox'
const MIN_WIDTH = 240

function storedBox(): Box | null {
  try {
    const box = JSON.parse(localStorage.getItem(BOX_KEY) ?? 'null') as Box | null
    if (!box || ![box.left, box.top, box.width].every(Number.isFinite)) return null
    // still on this screen
    return { width: Math.min(box.width, innerWidth - 16), left: Math.min(Math.max(0, box.left), innerWidth - 120), top: Math.min(Math.max(0, box.top), innerHeight - 80) }
  } catch {
    return null
  }
}

export function ReferencePanel({ reference, floorName, style, trace, onTrace, onClose, onAdjust }: Props) {
  const [view, setView] = useState<View>(FIT)
  const panel = useRef<HTMLElement>(null)
  const [box, setBox] = useState<Box | null>(storedBox)
  const moving = useRef<{ x: number; y: number; from: Box; kind: 'move' | 'size' } | null>(null)
  useEffect(() => {
    try {
      if (box) localStorage.setItem(BOX_KEY, JSON.stringify(box))
    } catch {
      // storage unavailable: the window just goes back to its spot next time
    }
  }, [box])
  /** Start moving (header) or resizing (corner grip) the window, from where it is drawn now. */
  const grab = (event: React.PointerEvent, kind: 'move' | 'size') => {
    if (kind === 'move' && (event.target as Element).closest('button, input, label')) return
    const element = panel.current
    const parent = element?.offsetParent?.getBoundingClientRect()
    if (!element || !parent) return
    const rect = element.getBoundingClientRect()
    event.preventDefault()
    event.currentTarget.setPointerCapture(event.pointerId)
    moving.current = { x: event.clientX, y: event.clientY, kind, from: { left: rect.left - parent.left, top: rect.top - parent.top, width: rect.width } }
  }
  const follow = (event: React.PointerEvent) => {
    const start = moving.current
    if (!start) return
    const dx = event.clientX - start.x
    const dy = event.clientY - start.y
    setBox(start.kind === 'move'
      ? { ...start.from, left: Math.max(0, start.from.left + dx), top: Math.max(0, start.from.top + dy) }
      : { ...start.from, width: Math.max(MIN_WIDTH, Math.min(innerWidth - start.from.left - 8, start.from.width + dx)) })
  }
  const release = () => (moving.current = null)
  const drag = useRef<{ x: number; y: number; from: View } | null>(null)
  const size = useImageSize(reference?.image) // the panel hugs the plan: no empty band above or below it
  useEffect(() => setView(FIT), [reference?.floor_id])

  const zoom = (event: React.WheelEvent<HTMLDivElement>) => {
    const box = event.currentTarget.getBoundingClientRect()
    const px = event.clientX - box.left
    const py = event.clientY - box.top
    setView((current) => {
      const scale = Math.min(8, Math.max(0.5, current.scale * Math.exp(-event.deltaY * 0.0015)))
      const k = scale / current.scale
      return { scale, x: px - (px - current.x) * k, y: py - (py - current.y) * k }
    })
  }

  return (
    <aside ref={panel} className="edit-reference" aria-label="Reference plan"
      style={box ? { ...style, left: box.left, top: box.top, width: box.width, right: 'auto', bottom: 'auto' } : style}>
      <header className="edit-reference-grab" onPointerDown={(event) => grab(event, 'move')} onPointerMove={follow} onPointerUp={release}
        onDoubleClick={(event) => !(event.target as Element).closest('button, input, label') && setBox(null)}
        title="Drag to move · double-click to put it back">
        <p className="who">Reference · {floorName}</p>
        {reference && (
          <label className="edit-trace">
            <input type="checkbox" checked={trace.on} onChange={(event) => onTrace({ ...trace, on: event.target.checked })} />
            Trace
            <input
              type="range" min={0.1} max={0.8} step={0.05} value={trace.opacity} disabled={!trace.on}
              aria-label="Trace opacity" onChange={(event) => onTrace({ ...trace, opacity: Number(event.target.value) })}
            />
          </label>
        )}
        {reference && trace.on && (
          <label className="edit-trace" title="Drag the plan on the editor, turn it with the round handle, resize it with the square one">
            <input type="checkbox" checked={Boolean(trace.adjust)} onChange={(event) => onTrace({ ...trace, adjust: event.target.checked })} />
            Adjust
          </label>
        )}
        <button type="button" className="hud-icon" onClick={onClose} aria-label="Close the reference">
          <X size={16} />
        </button>
      </header>
      {reference && trace.on && trace.adjust && onAdjust && size && (() => {
        const centre = traceAt(reference.transform, size.width / 2, size.height / 2)
        const turn = (degrees: number) => onAdjust(adjustTrace(reference.transform, { angle: (degrees * Math.PI) / 180, centre }))
        const resize = (factor: number) => onAdjust(adjustTrace(reference.transform, { scale: factor, centre }))
        return (
          <div className="edit-trace-adjust" role="toolbar" aria-label="Adjust the trace" title="Shift-click for bigger steps · or drag the plan on the editor">
            <span>Turn</span>
            <button type="button" className="hud-icon" aria-label="Turn left" onClick={(event) => turn(event.shiftKey ? 10 : 1)}><RotateCcw size={15} /></button>
            <button type="button" className="hud-icon" aria-label="Turn right" onClick={(event) => turn(event.shiftKey ? -10 : -1)}><RotateCw size={15} /></button>
            <span>Size</span>
            <button type="button" className="hud-icon" aria-label="Smaller" onClick={(event) => resize(event.shiftKey ? 0.9 : 0.98)}><Minus size={15} /></button>
            <button type="button" className="hud-icon" aria-label="Bigger" onClick={(event) => resize(event.shiftKey ? 1.1 : 1.02)}><Plus size={15} /></button>
          </div>
        )
      })()}
      <div
        className="edit-reference-view"
        style={size ? { aspectRatio: `${size.width} / ${size.height}` } : undefined}
        onWheel={zoom}
        onPointerDown={(event) => {
          event.currentTarget.setPointerCapture(event.pointerId)
          drag.current = { x: event.clientX, y: event.clientY, from: view }
        }}
        onPointerMove={(event) => {
          const start = drag.current
          if (start) setView({ ...start.from, x: start.from.x + event.clientX - start.x, y: start.from.y + event.clientY - start.y })
        }}
        onPointerUp={() => (drag.current = null)}
        onDoubleClick={() => setView(FIT)}
      >
        {reference ? (
          <img
            src={reference.image} alt={`Plan of ${floorName}`} draggable={false}
            style={{ transform: `translate(${view.x}px, ${view.y}px) scale(${view.scale})` }}
          />
        ) : (
          <p className="edit-reference-empty">No plan image for this floor</p>
        )}
      </div>
      <span className="edit-reference-size" role="separator" aria-label="Resize the reference"
        onPointerDown={(event) => grab(event, 'size')} onPointerMove={follow} onPointerUp={release} />
    </aside>
  )
}

/** An image's pixel size once it has loaded (the trace's SVG <image> needs it); null before / without one. */
export function useImageSize(src: string | undefined): { width: number; height: number } | null {
  const [size, setSize] = useState<{ src: string; width: number; height: number } | null>(null)
  useEffect(() => {
    if (!src) return
    const image = new Image()
    image.onload = () => setSize({ src, width: image.naturalWidth, height: image.naturalHeight })
    image.src = src
    return () => {
      image.onload = null
    }
  }, [src])
  return size && size.src === src ? { width: size.width, height: size.height } : null
}
