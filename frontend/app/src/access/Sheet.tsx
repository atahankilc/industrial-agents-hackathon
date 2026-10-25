// A glass sheet for access mode (sign in, set a password, building settings): from the bottom on phones, a panel on
// the right on wide screens. Same tokens as the HUD (building/hud.css); styles in ./access.css.

import { Plus, X } from 'lucide-react'
import { useEffect, useState, type KeyboardEvent, type ReactNode } from 'react'
import './access.css'

export function Sheet({ title, onClose, children, wide = false }: { title: string; onClose: () => void; children: ReactNode; wide?: boolean }) {
  useEffect(() => {
    const onKey = (event: globalThis.KeyboardEvent) => event.key === 'Escape' && onClose()
    addEventListener('keydown', onKey)
    return () => removeEventListener('keydown', onKey)
  }, [onClose])
  return (
    <>
      <div className="sheet-scrim" onClick={onClose} />
      <section className={`sheet${wide ? ' wide' : ''}`} role="dialog" aria-modal="true" aria-label={title}>
        <header>
          <h2>{title}</h2>
          <button type="button" className="hud-icon" onClick={onClose} aria-label="Close">
            <X size={16} strokeWidth={2} />
          </button>
        </header>
        <div className="sheet-body">{children}</div>
      </section>
    </>
  )
}

/** Access groups as chips: type a name, Enter or comma adds it, × or Backspace on an empty field removes one.
 * `suggestions`: groups already in use here, offered under the field as one-tap chips. */
export function GroupChips({ groups, onChange, placeholder = 'Add a group', label, suggestions = [], autoFocus = false }: {
  groups: string[]
  onChange: (groups: string[]) => void
  placeholder?: string
  label: string
  suggestions?: string[]
  autoFocus?: boolean
}) {
  const [draft, setDraft] = useState('')
  const add = () => {
    const names = draft.split(',').map((name) => name.trim().toLowerCase()).filter(Boolean)
    setDraft('')
    const next = [...new Set([...groups, ...names])]
    if (next.length !== groups.length) onChange(next)
  }
  const onKey = (event: KeyboardEvent<HTMLInputElement>) => {
    if (event.key === 'Enter' || event.key === ',') {
      event.preventDefault()
      add()
    } else if (event.key === 'Backspace' && !draft && groups.length) {
      onChange(groups.slice(0, -1))
    }
  }
  const offered = suggestions.filter((group) => !groups.includes(group))
  const field = (
    <div className="chips">
      {groups.map((group) => (
        <span key={group} className={`chip${group === 'public' ? ' public' : ''}`}>
          {group}
          <button type="button" onClick={() => onChange(groups.filter((item) => item !== group))} aria-label={`Remove ${group}`}>
            <X size={12} strokeWidth={2.4} />
          </button>
        </span>
      ))}
      <input
        value={draft}
        onChange={(event) => setDraft(event.target.value)}
        onKeyDown={onKey}
        onBlur={add}
        placeholder={groups.length ? '' : placeholder}
        aria-label={label}
        autoCapitalize="none"
        autoCorrect="off"
        spellCheck={false}
        autoFocus={autoFocus}
      />
    </div>
  )
  if (!offered.length) return field
  return (
    <div className="chips-with-offers">
      {field}
      <div className="chip-offers" aria-label={`Add to ${label}`}>
        {offered.map((group) => (
          <button key={group} type="button" className="chip-offer" onClick={() => onChange([...groups, group])}>
            <Plus size={12} strokeWidth={2.4} />
            {group}
          </button>
        ))}
      </div>
    </div>
  )
}
