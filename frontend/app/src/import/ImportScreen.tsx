// Create a building from floor plans (docs/superpowers/specs/2026-10-25-plan-import-design.md §7): pick PDFs / photos
// → the Creator works (its short sentences stream in) → the building screen opens on the private base `import/<id>`
// straight into the Edit mode, where the Builder corrects it and Save turns it into a building. The Edit mode resumes
// the Creator's draft through its localStorage key (`draft:<base>`, edit/useDraft.ts).
import { FileUp, X } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { api, type ImportLine, type ImportPlace, type ImportSuggestion, type PlacedLocation } from '../api'
import { Placement } from '../map/Placement'
import './import.css'

const ACCEPT = '.pdf,image/*,.heic,.heif'
const TOOL_LABEL: Record<string, string> = {
  list_sources: 'Looking at the files',
  view_source: 'Reading a page',
  register_plan: 'Tracing a floor',
  segment: 'Splitting rooms again',
  coarse_rooms: 'Outlining rooms by hand',
  add_rooms: 'Separating merged rooms',
  label_cells: 'Naming rooms and doors',
  set_scale: 'Measuring the scale',
  stack_floors: 'Stacking the floors',
  finish: 'Checking the building',
}

type Phase = 'pick' | 'working' | 'no_plan' | 'error' | 'place'
/** `place`: where on the map the building stands (MapLanding "Create a building here"); then, before Edit mode, the
 * fitted building is shown there to move / turn / scale by hand (map/Placement.tsx). */
/** `draft`: Edit mode's "Add a floor" — the new floors go into that open draft (`levels`: the floors it has). */
type Props = {
  place?: ImportPlace | null; draft?: { id: string; name: string; levels: number[] } | null
  onDone: (base: string) => void; onExit: () => void
}

const keyOf = (file: File) => `${file.name}:${file.size}`

export function ImportScreen({ place, draft, onDone, onExit }: Props) {
  const [placed, setPlaced] = useState<{
    draftId: string; base: string; location: PlacedLocation; locatedBy: 'tap' | 'photos' | 'device' | null; suggestion: ImportSuggestion | null
  } | null>(null)
  const [files, setFiles] = useState<File[]>([])
  // the floor each file is, typed by the user (a PDF's later pages count up from it); new files get the next free one
  const [floorOf, setFloorOf] = useState<Record<string, string>>({})
  const taken = new Set(draft?.levels ?? [])
  const levels = files.map((file) => floorOf[keyOf(file)]?.trim() ?? '')
  const levelProblem = levels.some((level) => !/^-?\d+$/.test(level))
    ? 'Give each file its floor number (0 = ground floor, −1 = basement).'
    : new Set(levels).size !== levels.length ? 'Each file must be a different floor.'
      : levels.some((level) => taken.has(Number(level))) ? `The building already has floor ${levels.filter((level) => taken.has(Number(level))).join(', ')}.`
        : null
  const [phase, setPhase] = useState<Phase>('pick')
  const [said, setSaid] = useState<string[]>([])
  const [warnings, setWarnings] = useState<string[]>([])
  const [doing, setDoing] = useState<string | null>(null)
  const [message, setMessage] = useState('')
  const [dragging, setDragging] = useState(false)
  const picker = useRef<HTMLInputElement>(null)
  const running = useRef<AbortController | null>(null)
  useEffect(() => () => running.current?.abort(), []) // leaving the screen stops the Creator (and its Claude calls)

  const add = (list: FileList | null) => {
    if (!list) return
    const fresh = Array.from(list).filter((file) => !file.type.startsWith('video/'))
    const added = fresh.filter((f) => !files.some((c) => c.name === f.name && c.size === f.size))
    setFiles((current) => [...current, ...added])
    setFloorOf((current) => {
      const next = { ...current }
      const used = new Set([...taken, ...Object.values(next).map(Number)])
      let level = draft?.levels.length ? Math.max(...draft.levels) + 1 : 0
      for (const file of added) {
        while (used.has(level)) level += 1
        next[keyOf(file)] = String(level)
        used.add(level)
      }
      return next
    })
  }

  const start = async () => {
    setPhase('working')
    setSaid([])
    setWarnings([])
    setDoing('Uploading')
    const onLine = (line: ImportLine) => {
      if (line.type === 'warning') setWarnings((w) => [...w, line.detail])
      else if (line.type === 'step' && line.kind === 'say') setSaid((s) => [...s, line.text])
      else if (line.type === 'step' && line.kind === 'tool') setDoing(TOOL_LABEL[line.name] ?? line.name)
      else if (line.type === 'done') {
        localStorage.setItem(`draft:${line.base}`, line.draft_id)
        if (line.location && !draft) {
          setPlaced({ draftId: line.draft_id, base: line.base, location: line.location, locatedBy: line.located_by ?? null, suggestion: line.suggestion ?? null })
          setPhase('place')
        } else onDone(line.base)
      } else if (line.type === 'no_plan') {
        setMessage(line.reason)
        setPhase('no_plan')
      } else if (line.type === 'error') {
        setMessage(line.detail)
        setPhase('error')
      }
    }
    const controller = new AbortController()
    running.current = controller
    try {
      // the browser's position, for when the photos carry no GPS (phone browsers often strip it): asked once, 4 s at most
      const device = draft ? null : await browserPosition()
      await api.importPlans(files, onLine, controller.signal, draft ? null : place, device, draft?.id, levels.map(Number))
    } catch (error) {
      if (controller.signal.aborted) return
      setMessage(error instanceof Error ? error.message : String(error))
      setPhase('error')
    }
  }

  return (
    <main className="im">
      <div className="im-inner">
        <button className="im-back" onClick={onExit}>{draft ? '← Back to editing' : '← Buildings'}</button>
        <header className="im-head">
          <h1>{draft ? 'Add a floor' : 'Create from floor plans'}</h1>
          {draft && <p className="im-place">To {draft.name} — laid onto the building at the floor you give each file</p>}
          {!draft && place && <p className="im-place">At {place.name ?? ('ring' in place ? 'the building you tapped' : 'the spot you tapped')} on the map</p>}
          <p>PDFs, scans or photos of plans, one per floor — say which floor each one is. The Creator traces rooms and
            doors and opens the result for you to correct.</p>
        </header>

        {phase === 'pick' && (
          <>
            <div
              className={`im-drop${dragging ? ' over' : ''}`}
              onClick={() => picker.current?.click()}
              onDragOver={(e) => { e.preventDefault(); setDragging(true) }}
              onDragLeave={() => setDragging(false)}
              onDrop={(e) => { e.preventDefault(); setDragging(false); add(e.dataTransfer.files) }}
              role="button"
              tabIndex={0}
              onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') picker.current?.click() }}
            >
              <FileUp aria-hidden />
              <span>Drop files here or choose them</span>
              <input ref={picker} type="file" multiple accept={ACCEPT} hidden onChange={(e) => { add(e.target.files); e.target.value = '' }} />
            </div>
            {files.length > 0 && (
              <ul className="im-files">
                {files.map((file) => (
                  <li key={file.name + file.size}>
                    <span>{file.name}</span>
                    <label className="im-floor">
                      Floor
                      <input type="number" step={1} value={floorOf[keyOf(file)] ?? ''} aria-label={`Floor of ${file.name}`}
                        onChange={(event) => setFloorOf((current) => ({ ...current, [keyOf(file)]: event.target.value }))} />
                    </label>
                    <span className="im-size">{(file.size / 1024 / 1024).toFixed(1)} MB</span>
                    <button aria-label={`Remove ${file.name}`} onClick={() => setFiles((f) => f.filter((x) => x !== file))}><X /></button>
                  </li>
                ))}
              </ul>
            )}
            {files.length > 0 && levelProblem && <p className="im-warn">{levelProblem}</p>}
            <button className="im-go" disabled={!files.length || Boolean(levelProblem)} onClick={start}>
              {draft ? (files.length > 1 ? 'Add floors' : 'Add floor') : 'Create building'}
            </button>
          </>
        )}

        {phase === 'place' && placed && (
          <Placement draftId={placed.draftId} location={placed.location} target={place && 'ring' in place ? place.ring : null}
            locatedBy={placed.locatedBy} suggestion={placed.suggestion} onDone={() => onDone(placed.base)} />
        )}

        {phase !== 'pick' && phase !== 'place' && (
          <section className="im-work" aria-live="polite">
            {phase === 'working' && <p className="im-doing"><span className="im-pulse" aria-hidden />{doing}…</p>}
            <ol className="im-said">
              {said.map((line, index) => <li key={index}>{line}</li>)}
            </ol>
            {warnings.map((warning) => <p key={warning} className="im-warn">{warning}</p>)}
            {phase === 'no_plan' && <p className="im-end">No floor plan found in these files. {message}</p>}
            {phase === 'error' && <p className="im-end">The import stopped: {message}</p>}
            {(phase === 'no_plan' || phase === 'error') && (
              <button className="im-go" onClick={() => setPhase('pick')}>Try other files</button>
            )}
          </section>
        )}
      </div>
    </main>
  )
}

/** Where the browser is now ({lat, lon}), or null when it can't or won't say within 4 s. */
function browserPosition(): Promise<{ lat: number; lon: number } | null> {
  if (!('geolocation' in navigator)) return Promise.resolve(null)
  return new Promise((resolve) => {
    const timer = setTimeout(() => resolve(null), 4000)
    navigator.geolocation.getCurrentPosition(
      (position) => {
        clearTimeout(timer)
        resolve({ lat: position.coords.latitude, lon: position.coords.longitude })
      },
      () => {
        clearTimeout(timer)
        resolve(null)
      },
      { enableHighAccuracy: true, timeout: 4000, maximumAge: 60000 },
    )
  })
}
