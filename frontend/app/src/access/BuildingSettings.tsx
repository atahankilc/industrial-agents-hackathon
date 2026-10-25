// Building settings (menu → "Building settings", access mode): one component per section. Everyone gets My
// preferences (this building's overrides, src/access/PreferencesForm.tsx); the admin also gets Access, Members and
// Objects (src/access/ObjectsSection.tsx).
// Access: the building public or not, room-type rules (a room type restricted to groups) and per-space exceptions
// (groups, or the reserved group "public" to open one space); Save → PUT /access/building.
// Members: who has groups here (PUT /access/members, no groups removes them) and an invite that returns a sign-in
// link to pass on (POST /access/invite; no email is sent).

import { Check, Copy } from 'lucide-react'
import { useEffect, useMemo, useState, type FormEvent } from 'react'
import { api, type AccessMember, type AccessRules, type BuildingAccess, type FleetObject, type Plan } from '../api'
import { ObjectsSection } from './ObjectsSection'
import { BuildingPreferencesSection } from './PreferencesForm'
import { GroupChips, Sheet } from './Sheet'

const humanise = (type: string) => type.replace(/_/g, ' ').replace(/^\w/, (c) => c.toUpperCase())
const message = (reason: unknown) => (reason instanceof Error ? reason.message : String(reason))
const SPACES_SHOWN = 40

export function BuildingSettings({ buildingId, plan, admin, objects, onClose, onSaved, onObjects }: {
  buildingId: string
  plan: Plan | null
  admin: boolean
  /** the building's moving objects, as last polled */
  objects: FleetObject[]
  onClose: () => void
  /** access rules saved: the plan reloads */
  onSaved: () => void
  /** objects changed: poll now */
  onObjects: () => void
}) {
  return (
    <Sheet title="Building settings" onClose={onClose} wide>
      <BuildingPreferencesSection buildingId={buildingId} plan={plan} />
      {admin && (
        <>
          <AccessSection buildingId={buildingId} onSaved={onSaved} />
          <MembersSection buildingId={buildingId} />
          <ObjectsSection buildingId={buildingId} plan={plan} objects={objects} onChanged={onObjects} />
        </>
      )}
    </Sheet>
  )
}

/** Drop rules with no groups (no rule = public). */
function cleaned(rules: Record<string, string[]>) {
  return Object.fromEntries(Object.entries(rules).filter(([, groups]) => groups.length))
}

function AccessSection({ buildingId, onSaved }: { buildingId: string; onSaved: () => void }) {
  const [loaded, setLoaded] = useState<BuildingAccess | null>(null)
  const [rules, setRules] = useState<AccessRules | null>(null)
  const [query, setQuery] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [state, setState] = useState<'idle' | 'saving' | 'saved'>('idle')

  useEffect(() => {
    let cancelled = false
    api
      .accessBuilding(buildingId)
      .then((data) => {
        if (cancelled) return
        setLoaded(data)
        setRules({ public: data.public, room_types: data.room_types, spaces: data.spaces })
      })
      .catch((reason) => !cancelled && setError(message(reason)))
    return () => {
      cancelled = true
    }
  }, [buildingId])

  const spaces = useMemo(() => {
    if (!loaded || !rules) return []
    const words = query.trim().toLowerCase().split(/\s+/).filter(Boolean)
    const matches = loaded.space_options.filter((space) => {
      const text = `${space.name} ${space.ref} ${space.room_type} ${space.id}`.toLowerCase()
      return words.every((word) => text.includes(word))
    })
    // spaces with an exception first, so the ones set are always in view
    return [...matches.filter((space) => rules.spaces[space.id]), ...matches.filter((space) => !rules.spaces[space.id])]
  }, [loaded, rules, query])

  if (error && !rules) return <section className="sheet-section"><h3>Access</h3><p className="sheet-error">{error}</p></section>
  if (!loaded || !rules) return <section className="sheet-section"><h3>Access</h3><p className="sheet-hint">Loading…</p></section>

  const edit = (next: AccessRules) => {
    setRules(next)
    setState('idle')
  }
  const save = async () => {
    setState('saving')
    setError(null)
    try {
      const saved = await api.saveAccessBuilding(buildingId, { public: rules.public, room_types: cleaned(rules.room_types), spaces: cleaned(rules.spaces) })
      setRules({ public: saved.public, room_types: saved.room_types, spaces: saved.spaces })
      setState('saved')
      onSaved()
    } catch (reason) {
      setError(message(reason))
      setState('idle')
    }
  }

  return (
    <section className="sheet-section">
      <h3>Access</h3>
      <label className="toggle-row">
        <span>
          Public building
          <small>{rules.public ? 'Anyone can open it.' : 'Only members of this building and the admin can open it.'}</small>
        </span>
        <input type="checkbox" role="switch" checked={rules.public} onChange={(event) => edit({ ...rules, public: event.target.checked })} />
      </label>

      <h4>Room types</h4>
      <p className="sheet-hint">Every space is public until restricted. Restrict a room type to groups, e.g. it, staff.</p>
      {loaded.room_type_options.length === 0 && <p className="sheet-hint">This building has no room types.</p>}
      <ul className="rule-list">
        {loaded.room_type_options.map((type) => (
          <li key={type}>
            <span className="rule-name">{humanise(type)}</span>
            <GroupChips
              label={`Groups for ${humanise(type)}`}
              placeholder="Public"
              groups={rules.room_types[type] ?? []}
              onChange={(groups) => edit({ ...rules, room_types: { ...rules.room_types, [type]: groups } })}
            />
          </li>
        ))}
      </ul>

      <h4>Single spaces</h4>
      <p className="sheet-hint">An exception wins over its room type. The group “public” opens one space to everyone.</p>
      <label className="field">
        <span>Find a space</span>
        <input type="search" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Name, ref or type" />
      </label>
      <ul className="rule-list">
        {spaces.slice(0, SPACES_SHOWN).map((space) => (
          <li key={space.id}>
            <span className="rule-name">
              {space.name}
              <small>{[space.ref, space.room_type && humanise(space.room_type), space.floor_id].filter(Boolean).join(' · ')}</small>
            </span>
            <GroupChips
              label={`Groups for ${space.name}`}
              placeholder="As its room type"
              groups={rules.spaces[space.id] ?? []}
              onChange={(groups) => edit({ ...rules, spaces: { ...rules.spaces, [space.id]: groups } })}
            />
          </li>
        ))}
      </ul>
      {spaces.length > SPACES_SHOWN && <p className="sheet-hint">{spaces.length - SPACES_SHOWN} more — narrow the search.</p>}
      {spaces.length === 0 && <p className="sheet-hint">No space matches.</p>}

      {error && <p className="sheet-error" role="alert">{error}</p>}
      <button type="button" className="hud-primary" onClick={() => void save()} disabled={state === 'saving'}>
        {state === 'saving' ? 'Saving…' : state === 'saved' ? <><Check size={16} strokeWidth={2.4} /> Saved</> : 'Save access'}
      </button>
    </section>
  )
}

function MembersSection({ buildingId }: { buildingId: string }) {
  const [members, setMembers] = useState<AccessMember[] | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    api
      .members(buildingId)
      .then((list) => !cancelled && setMembers(list))
      .catch((reason) => !cancelled && setError(message(reason)))
    return () => {
      cancelled = true
    }
  }, [buildingId])

  const change = async (member: AccessMember, groups: string[]) => {
    setError(null)
    try {
      const saved = await api.saveMember({ ...member, groups })
      setMembers((list) => (list ?? []).flatMap((item) => (item.user_id !== member.user_id ? [item] : saved.groups.length ? [saved] : [])))
    } catch (reason) {
      setError(message(reason))
    }
  }

  return (
    <section className="sheet-section">
      <h3>Members</h3>
      {!members && !error && <p className="sheet-hint">Loading…</p>}
      {members && members.length === 0 && <p className="sheet-hint">No members yet. Invite someone below.</p>}
      {members && members.length > 0 && (
        <ul className="rule-list">
          {members.map((member) => (
            <li key={member.user_id}>
              <span className="rule-name">{member.email}</span>
              <GroupChips label={`Groups for ${member.email}`} placeholder="No groups removes" groups={member.groups} onChange={(groups) => void change(member, groups)} />
            </li>
          ))}
        </ul>
      )}
      {error && <p className="sheet-error" role="alert">{error}</p>}
      <Invite buildingId={buildingId} onInvited={(member) => setMembers((list) => [...(list ?? []).filter((item) => item.user_id !== member.user_id), member])} />
    </section>
  )
}

function Invite({ buildingId, onInvited }: { buildingId: string; onInvited: (member: AccessMember) => void }) {
  const [email, setEmail] = useState('')
  const [groups, setGroups] = useState<string[]>([])
  const [link, setLink] = useState<string | null>(null)
  const [copied, setCopied] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const submit = async (event: FormEvent) => {
    event.preventDefault()
    setBusy(true)
    setError(null)
    setLink(null)
    setCopied(false)
    try {
      const { link: next, ...member } = await api.invite(email.trim(), buildingId, groups, location.origin)
      setLink(next)
      if (member.groups.length) onInvited(member)
      setEmail('')
      setGroups([])
    } catch (reason) {
      setError(message(reason))
    } finally {
      setBusy(false)
    }
  }
  const copy = async () => {
    if (!link) return
    try {
      await navigator.clipboard.writeText(link)
      setCopied(true)
    } catch {
      setError('Could not copy. Select the link and copy it by hand.')
    }
  }

  return (
    <form className="sheet-form invite" onSubmit={submit}>
      <h4>Invite</h4>
      <label className="field">
        <span>Email</span>
        <input type="email" value={email} onChange={(event) => setEmail(event.target.value)} required autoComplete="off" />
      </label>
      <div className="field">
        <span>Groups in this building</span>
        <GroupChips label="Groups for the invite" placeholder="e.g. staff" groups={groups} onChange={setGroups} />
      </div>
      {error && <p className="sheet-error" role="alert">{error}</p>}
      <button type="submit" className="hud-primary" disabled={busy || !email.includes('@')}>
        {busy ? 'Creating the link…' : 'Create invite link'}
      </button>
      {link && (
        <div className="link-box">
          <p className="sheet-hint">No email is sent. Pass this link on; it signs them in once.</p>
          <div>
            <input readOnly value={link} onFocus={(event) => event.target.select()} aria-label="Invite link" />
            <button type="button" className="hud-icon" onClick={() => void copy()} aria-label="Copy the link">
              {copied ? <Check size={15} strokeWidth={2.4} /> : <Copy size={15} strokeWidth={2} />}
            </button>
          </div>
        </div>
      )}
    </form>
  )
}
