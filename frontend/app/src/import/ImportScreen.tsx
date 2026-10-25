// Create a building from floor plans (docs/superpowers/specs/2026-10-25-plan-import-design.md §7): pick PDFs / photos
// → the Creator works (its short sentences stream in) → the building screen opens on the private base `import/<id>`
// straight into the Edit mode, where the Builder corrects it and Save turns it into a building. The Edit mode resumes
// the Creator's draft through its localStorage key (`draft:<base>`, edit/useDraft.ts).
import { FileUp, X } from 'lucide-react'
import { useRef, useState } from 'react'
import { api, type ImportLine } from '../api'
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

type Phase = 'pick' | 'working' | 'no_plan' | 'error'
type Props = { onDone: (base: string) => void; onExit: () => void }

export function ImportScreen({ onDone, onExit }: Props) {
  const [files, setFiles] = useState<File[]>([])
  const [phase, setPhase] = useState<Phase>('pick')
  const [said, setSaid] = useState<string[]>([])
  const [warnings, setWarnings] = useState<string[]>([])
  const [doing, setDoing] = useState<string | null>(null)
  const [message, setMessage] = useState('')
  const [dragging, setDragging] = useState(false)
  const picker = useRef<HTMLInputElement>(null)

  const add = (list: FileList | null) => {
    if (!list) return
    const fresh = Array.from(list).filter((file) => !file.type.startsWith('video/'))
    setFiles((current) => [...current, ...fresh.filter((f) => !current.some((c) => c.name === f.name && c.size === f.size))])
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
        onDone(line.base)
      } else if (line.type === 'no_plan') {
        setMessage(line.reason)
        setPhase('no_plan')
      } else if (line.type === 'error') {
        setMessage(line.detail)
        setPhase('error')
      }
    }
    try {
      await api.importPlans(files, onLine)
    } catch (error) {
      setMessage(String(error))
      setPhase('error')
    }
  }

  return (
    <main className="im">
      <div className="im-inner">
        <button className="im-back" onClick={onExit}>← Buildings</button>
        <header className="im-head">
          <h1>Create from floor plans</h1>
          <p>PDFs, scans or photos of plans — one per floor or all at once. The Creator finds the floors, traces rooms
            and doors, and opens the result for you to correct.</p>
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
                    <span className="im-size">{(file.size / 1024 / 1024).toFixed(1)} MB</span>
                    <button aria-label={`Remove ${file.name}`} onClick={() => setFiles((f) => f.filter((x) => x !== file))}><X /></button>
                  </li>
                ))}
              </ul>
            )}
            <button className="im-go" disabled={!files.length} onClick={start}>Create building</button>
          </>
        )}

        {phase !== 'pick' && (
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
