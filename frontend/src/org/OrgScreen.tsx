// Organisations (docs/product/organizations.md, backend/api/routes/orgs.py and maps.py): ?view=org lists the viewer's
// organisations and starts a new one; ?view=org&org=<slug> is one organisation's settings over the map: its maps (who
// opens them, the share link, which buildings are on them), its buildings (who finds and opens each) and, for its
// owners, its people. Which org owns a building is the admin's call, so buildings are only listed here, never added.

import { Check, Copy, Globe, Link2, Lock, Map as MapIcon, Plus, Trash2, UserPlus, UserRound, X } from 'lucide-react'
import { useCallback, useEffect, useState, type FormEvent } from 'react'
import { refreshOrgs, useAccess } from '../access/auth'
import { Sheet } from '../access/Sheet'
import {
  api,
  type Building,
  type Listing,
  type MapVisibility,
  type Org,
  type OrgDetail,
  type OrgMapSummary,
  type OrgMember,
  type OrgMapView,
  type OrgRole,
} from '../api'
import './org.css'

const message = (reason: unknown) => {
  const text = reason instanceof Error ? reason.message : String(reason)
  const match = text.match(/"detail":\s*"((?:[^"\\]|\\.)*)"/)
  return match ? JSON.parse(`"${match[1]}"`) : text
}

/** An address from a name, as the backend takes it (orgs.py SLUG): lowercase letters, digits, inner hyphens. */
const slugOf = (name: string) =>
  name.normalize('NFKD').replace(/[̀-ͯ]/g, '').toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '').slice(0, 40).replace(/-+$/, '')

const LISTINGS: { value: Listing; label: string }[] = [
  { value: 'listed', label: 'Main map' },
  { value: 'unlisted', label: 'By link' },
  { value: 'private', label: 'Members' },
]
const VISIBILITIES: { value: MapVisibility; label: string; Icon: typeof Globe; note: string }[] = [
  { value: 'private', label: 'Members', Icon: Lock, note: 'Only the organisation’s people open it.' },
  { value: 'link', label: 'Link', Icon: Link2, note: 'Anyone with the link opens it.' },
  { value: 'public', label: 'Everyone', Icon: Globe, note: 'Anyone who knows its address opens it.' },
]
const ROLES: { value: OrgRole; label: string }[] = [
  { value: 'viewer', label: 'Viewer' },
  { value: 'editor', label: 'Editor' },
  { value: 'owner', label: 'Owner' },
]

const mapUrl = (slug: string, key: string | null | undefined) =>
  `${location.origin}${location.pathname}?map=${encodeURIComponent(slug)}${key ? `&k=${encodeURIComponent(key)}` : ''}`

export function OrgScreen(props: {
  slug: string | null
  onExit: () => void
  onOpenMap: (map: string, key: string | null) => void
  onOpenOrg: (org: string) => void
}) {
  // the HUD's tokens (building/hud.css) live on .access-layer: outside the building screen and the map, the sheet needs it
  return <div className="access-layer"><OrgSheets {...props} /></div>
}

function OrgSheets({ slug, onExit, onOpenMap, onOpenOrg }: {
  slug: string | null
  onExit: () => void
  onOpenMap: (map: string, key: string | null) => void
  onOpenOrg: (org: string) => void
}) {
  const access = useAccess()
  if (!access.mode) return <Sheet title="Organisations" onClose={onExit} wide><p className="sheet-hint">Organisations need accounts, and this app runs without them.</p></Sheet>
  if (!access.email) return <Sheet title="Organisations" onClose={onExit} wide><p className="sheet-hint">{access.checking ? 'Loading…' : 'Sign in to see your organisations.'}</p></Sheet>
  return slug ? <OrgSettings key={slug} slug={slug} onExit={onExit} onOpenMap={onOpenMap} /> : <OrgList onExit={onExit} onOpenOrg={onOpenOrg} />
}

// ---------- the list, and a new organisation ----------

function OrgList({ onExit, onOpenOrg }: { onExit: () => void; onOpenOrg: (org: string) => void }) {
  const [orgs, setOrgs] = useState<Org[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [name, setName] = useState('')
  const [address, setAddress] = useState<string | null>(null) // null: follows the name
  const [busy, setBusy] = useState(false)
  useEffect(() => {
    api.orgs().then(setOrgs).catch((reason) => setError(message(reason)))
  }, [])
  const slug = address ?? slugOf(name)
  const create = async (event: FormEvent) => {
    event.preventDefault()
    setBusy(true)
    setError(null)
    try {
      const made = await api.createOrg(slug, name.trim())
      await refreshOrgs()
      onOpenOrg(made.slug)
    } catch (reason) {
      setError(message(reason))
      setBusy(false)
    }
  }
  return (
    <Sheet title="Organisations" onClose={onExit} wide>
      <div className="settings">
        <h4>Yours{orgs?.length ? ` · ${orgs.length}` : ''}</h4>
        <div className="pref-group tone-guide">
          {!orgs && !error && <div className="pref-row"><p className="sheet-hint settings-note">Loading…</p></div>}
          {orgs?.length === 0 && <div className="pref-row"><p className="sheet-hint settings-note">You are in no organisation yet.</p></div>}
          {orgs?.map((org) => (
            <button key={org.slug} type="button" className="pref-row org-row" onClick={() => onOpenOrg(org.slug)}>
              <span className="pref-label">
                <span>{org.name}<small>{[org.role ?? 'admin', org.verified ? 'verified' : null].filter(Boolean).join(' · ')}</small></span>
              </span>
            </button>
          ))}
        </div>
        <form className="sheet-form settings-invite" onSubmit={create}>
          <h4>New organisation</h4>
          <p className="sheet-hint">You become its owner. The admin hands it its buildings and verifies it before any goes on the main map.</p>
          <label className="field">
            <span>Name</span>
            <input value={name} onChange={(event) => setName(event.target.value)} required maxLength={120} placeholder="e.g. TU München" />
          </label>
          <label className="field">
            <span>Address</span>
            <input value={slug} onChange={(event) => setAddress(slugOf(event.target.value))} required maxLength={40} placeholder="e.g. tum"
              autoCapitalize="none" autoCorrect="off" spellCheck={false} />
          </label>
          {error && <p className="sheet-error" role="alert">{error}</p>}
          <button type="submit" className="hud-primary" disabled={busy || !name.trim() || !slug}>{busy ? 'Creating…' : 'Create organisation'}</button>
        </form>
      </div>
    </Sheet>
  )
}

// ---------- one organisation ----------

function OrgSettings({ slug, onExit, onOpenMap }: { slug: string; onExit: () => void; onOpenMap: (map: string, key: string | null) => void }) {
  const access = useAccess()
  const [org, setOrg] = useState<OrgDetail | null>(null)
  const [maps, setMaps] = useState<OrgMapSummary[] | null>(null)
  const [names, setNames] = useState<Record<string, string>>({})
  const [error, setError] = useState<string | null>(null)
  const load = useCallback(() => {
    api.org(slug).then(setOrg).catch((reason) => setError(message(reason)))
    api.orgMaps(slug).then(setMaps).catch((reason) => setError(message(reason)))
  }, [slug])
  useEffect(load, [load])
  useEffect(() => {
    api.buildings().then((list: Building[]) => setNames(Object.fromEntries(list.map((b) => [b.id, b.name ?? b.id])))).catch(() => undefined)
  }, [])

  const editor = access.admin || org?.role === 'editor' || org?.role === 'owner'
  const owner = access.admin || org?.role === 'owner'
  const nameOf = (id: string) => names[id] ?? id

  const setListing = async (building: string, listing: Listing) => {
    setError(null)
    try {
      await api.setOrgBuilding(slug, building, listing)
      setOrg((current) => current && { ...current, buildings: current.buildings.map((b) => (b.id === building ? { ...b, listing } : b)) })
    } catch (reason) {
      setError(message(reason))
    }
  }

  if (!org) return <Sheet title="Organisation" onClose={onExit} wide><p className="sheet-hint">{error ?? 'Loading…'}</p></Sheet>
  return (
    <Sheet title={org.name} onClose={onExit} wide>
      <div className="settings">
        <p className="settings-building">{[org.role ?? 'admin', org.verified ? 'verified' : 'not verified yet'].join(' · ')}</p>
        {error && <p className="sheet-error" role="alert">{error}</p>}

        <h4>Maps{maps?.length ? ` · ${maps.length}` : ''}</h4>
        <div className="pref-group tone-route">
          {maps?.length === 0 && <div className="pref-row"><p className="sheet-hint settings-note">No map yet.{editor ? ' Make one, put buildings on it and share its link.' : ''}</p></div>}
          {maps?.map((map) => (
            <MapRow key={map.slug} summary={map} editor={editor} owner={owner} buildings={org.buildings.map((b) => b.id)} nameOf={nameOf}
              onOpen={onOpenMap} onChanged={load} onError={setError} />
          ))}
        </div>
        {editor && <NewMap org={slug} onMade={load} onError={setError} />}

        <h4>Buildings{org.buildings.length ? ` · ${org.buildings.length}` : ''}</h4>
        <div className="pref-group tone-guide">
          {org.buildings.length === 0 && (
            <div className="pref-row"><p className="sheet-hint settings-note">No building yet. The admin gives an organisation its buildings.</p></div>
          )}
          {org.buildings.map((building) => (
            <div className="pref-row org-building" key={building.id}>
              <span className="pref-label"><span>{nameOf(building.id)}</span></span>
              {editor ? (
                <div className="pref-scope" role="radiogroup" aria-label={`Who finds ${nameOf(building.id)}`}>
                  {LISTINGS.map(({ value, label }) => (
                    <button key={value} type="button" role="radio" aria-checked={building.listing === value}
                      onClick={() => building.listing !== value && void setListing(building.id, value)}>{label}</button>
                  ))}
                </div>
              ) : (
                <small>{LISTINGS.find((item) => item.value === building.listing)?.label}</small>
              )}
            </div>
          ))}
        </div>
        {editor && !org.verified && <p className="sheet-hint settings-note">Putting a building on the main map needs a verified organisation; ask the admin.</p>}

        {owner && org.members && <People org={slug} members={org.members} onChanged={load} onError={setError} />}
      </div>
    </Sheet>
  )
}

function MapRow({ summary, editor, owner, buildings, nameOf, onOpen, onChanged, onError }: {
  summary: OrgMapSummary
  editor: boolean
  owner: boolean
  /** the organisation's own buildings, offered for the map */
  buildings: string[]
  nameOf: (id: string) => string
  onOpen: (map: string, key: string | null) => void
  onChanged: () => void
  onError: (error: string | null) => void
}) {
  const [open, setOpen] = useState(false)
  const [view, setView] = useState<OrgMapView | null>(null)
  const [copied, setCopied] = useState(false)
  useEffect(() => {
    if (!open || view) return
    api.map(summary.slug, null).then(setView).catch((reason) => onError(message(reason)))
  }, [open, view, summary.slug, onError])
  const act = async (work: () => Promise<OrgMapView>) => {
    onError(null)
    try {
      setView(await work())
      setCopied(false)
      onChanged()
    } catch (reason) {
      onError(message(reason))
    }
  }
  const copy = async () => {
    const current = view ?? (await api.map(summary.slug, null))
    try {
      await navigator.clipboard.writeText(mapUrl(current.slug, current.visibility === 'link' ? current.token : null))
      setCopied(true)
    } catch {
      onError('Could not copy. Open the map and copy its address by hand.')
    }
  }
  const on = new Set(view?.buildings.map((b) => b.id) ?? [])
  const offered = [...new Set([...buildings, ...on])]
  const visibility = view?.visibility ?? summary.visibility
  const count = view?.buildings.length ?? summary.buildings
  return (
    <div className="pref-row org-map">
      <span className="pref-label">
        <i className="pref-icon" aria-hidden="true"><MapIcon size={20} strokeWidth={1.9} /></i>
        <span>{view?.name ?? summary.name}<small>{`${count} ${count === 1 ? 'building' : 'buildings'} · ${VISIBILITIES.find((v) => v.value === visibility)!.label.toLowerCase()}`}</small></span>
      </span>
      <div className="settings-actions">
        <button type="button" className="settings-button" onClick={() => onOpen(summary.slug, view?.visibility === 'link' ? view.token ?? null : null)}>Open</button>
        <button type="button" className="settings-button quiet" onClick={() => void copy()}>
          {copied ? <Check size={15} strokeWidth={2.4} /> : <Copy size={15} strokeWidth={2} />} Copy link
        </button>
        {editor && <button type="button" className="settings-button quiet" aria-expanded={open} onClick={() => setOpen((value) => !value)}>{open ? 'Done' : 'Edit'}</button>}
      </div>
      {open && view && (
        <div className="org-map-edit">
          <div className="pref-scope settings-choice" role="radiogroup" aria-label="Who opens this map">
            {VISIBILITIES.map(({ value, label, Icon }) => (
              <button key={value} type="button" role="radio" aria-checked={visibility === value}
                onClick={() => visibility !== value && void act(() => api.updateMap(summary.slug, { visibility: value }))}>
                <Icon size={15} strokeWidth={2} /><span>{label}</span>
              </button>
            ))}
          </div>
          <p className="sheet-hint settings-note">
            {VISIBILITIES.find((v) => v.value === visibility)!.note} Unlisted buildings on it open for whoever opens the map; private ones only for the organisation’s people.
          </p>
          {visibility === 'link' && (
            <button type="button" className="sheet-quiet" onClick={() => void act(() => api.renewMapLink(summary.slug))}>New link (the old one stops working)</button>
          )}
          <ul className="org-map-buildings">
            {offered.map((id) => (
              <li key={id}>
                <label>
                  <input type="checkbox" checked={on.has(id)} onChange={(event) => void act(() => api.setMapBuilding(summary.slug, id, event.target.checked))} />
                  <span>{nameOf(id)}</span>
                </label>
              </li>
            ))}
            {offered.length === 0 && <li className="sheet-hint">The organisation has no buildings to put on it yet.</li>}
          </ul>
          {owner && (
            <button type="button" className="sheet-quiet" onClick={() => void act(async () => {
              await api.deleteMap(summary.slug)
              return view
            })}>
              <Trash2 size={14} strokeWidth={2} /> Delete this map
            </button>
          )}
        </div>
      )}
    </div>
  )
}

function NewMap({ org, onMade, onError }: { org: string; onMade: () => void; onError: (error: string | null) => void }) {
  const [name, setName] = useState('')
  const [busy, setBusy] = useState(false)
  const submit = async (event: FormEvent) => {
    event.preventDefault()
    setBusy(true)
    onError(null)
    try {
      await api.createMap(org, slugOf(`${org}-${name}`), name.trim())
      setName('')
      onMade()
    } catch (reason) {
      onError(message(reason))
    } finally {
      setBusy(false)
    }
  }
  return (
    <form className="org-new-map" onSubmit={submit}>
      <input value={name} onChange={(event) => setName(event.target.value)} placeholder="New map, e.g. Garching campus" maxLength={120} aria-label="Name of the new map" />
      <button type="submit" className="settings-button" disabled={busy || !name.trim()}><Plus size={16} strokeWidth={2.2} /> Make</button>
    </form>
  )
}

function People({ org, members, onChanged, onError }: { org: string; members: OrgMember[]; onChanged: () => void; onError: (error: string | null) => void }) {
  const [inviting, setInviting] = useState(false)
  const change = async (member: OrgMember, role: OrgRole | null) => {
    onError(null)
    try {
      await api.setOrgMember({ ...member, role })
      onChanged()
    } catch (reason) {
      onError(message(reason))
    }
  }
  return (
    <>
      <h4>People · {members.length}</h4>
      <div className="pref-group tone-leave">
        {members.map((member) => (
          <div className="pref-row org-building" key={member.user_id}>
            <span className="pref-label">
              <i className="pref-icon" aria-hidden="true"><UserRound size={20} strokeWidth={1.9} /></i>
              <span className="settings-email">{member.email}</span>
            </span>
            <div className="pref-scope" role="radiogroup" aria-label={`Role of ${member.email}`}>
              {ROLES.map(({ value, label }) => (
                <button key={value} type="button" role="radio" aria-checked={member.role === value}
                  onClick={() => member.role !== value && void change(member, value)}>{label}</button>
              ))}
            </div>
            <button type="button" className="hud-icon settings-remove" onClick={() => void change(member, null)} aria-label={`Remove ${member.email}`} title="Remove from the organisation">
              <Trash2 size={15} strokeWidth={2} />
            </button>
          </div>
        ))}
      </div>
      {inviting ? (
        <Invite org={org} onClose={() => setInviting(false)} onInvited={onChanged} />
      ) : (
        <div className="settings-actions">
          <button type="button" className="settings-button" onClick={() => setInviting(true)}><UserPlus size={16} strokeWidth={2.2} /> Invite someone</button>
        </div>
      )}
    </>
  )
}

function Invite({ org, onInvited, onClose }: { org: string; onInvited: () => void; onClose: () => void }) {
  const [email, setEmail] = useState('')
  const [role, setRole] = useState<OrgRole>('viewer')
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
      const made = await api.inviteToOrg(org, email.trim(), role, location.origin)
      setLink(made.link)
      setEmail('')
      onInvited()
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
    <form className="sheet-form settings-invite" onSubmit={submit}>
      <div className="settings-invite-head">
        <h4>Invite someone</h4>
        <button type="button" className="hud-icon" onClick={onClose} aria-label="Close the invite"><X size={15} strokeWidth={2} /></button>
      </div>
      <label className="field">
        <span>Email</span>
        <input type="email" value={email} onChange={(event) => setEmail(event.target.value)} required autoComplete="off" autoFocus placeholder="name@example.com" />
      </label>
      <div className="pref-scope" role="radiogroup" aria-label="Role">
        {ROLES.map(({ value, label }) => (
          <button key={value} type="button" role="radio" aria-checked={role === value} onClick={() => setRole(value)}>{label}</button>
        ))}
      </div>
      {error && <p className="sheet-error" role="alert">{error}</p>}
      <button type="submit" className="hud-primary" disabled={busy || !email.includes('@')}>{busy ? 'Creating the link…' : 'Create invite link'}</button>
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
