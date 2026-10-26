// Building settings (access mode, admin only): the shield button on the building screen, the Access tool's
// "Members, invites and objects" or the Guide's open_building_settings. Three tabs, one topic each:
// - Access: who can open the building (everyone / members only) and the restricted areas — only what is restricted
//   is listed; "Restrict an area" searches room types and rooms. Saved at once (./useAccessRules.ts, shared with the
//   Edit mode's Access tool); "Show on the plan" opens that tool.
// - People: the members and their groups (PUT /access/members; Remove = no groups), and an invite that returns a
//   sign-in link to pass on (POST /access/invite; no email is sent).
// - Objects: the building's moving objects (./ObjectsSection.tsx).
// Groups already used here (in rules or by members) are offered as one-tap chips.
// A viewer's own preferences for the building are in the Preferences sheet (./PreferencesForm.tsx).

import { Check, Copy, DoorClosed, Globe, Lock, Map, Plus, Search, Shapes, Trash2, UserPlus, UserRound, Users, X } from 'lucide-react'
import { useEffect, useMemo, useState, type FormEvent } from 'react'
import { api, type AccessMember, type AccessRules, type FleetObject, type Plan } from '../api'
import { ObjectsSection } from './ObjectsSection'
import { GroupChips, Sheet } from './Sheet'
import { PUBLIC_GROUP, type AccessRulesState } from './useAccessRules'

const humanise = (type: string) => type.replace(/_/g, ' ').replace(/^\w/, (c) => c.toUpperCase())
const message = (reason: unknown) => (reason instanceof Error ? reason.message : String(reason))
const MATCHES_SHOWN = 12
const TAB_KEY = 'building-settings-tab'

type Tab = 'access' | 'people' | 'objects'
const TABS: { tab: Tab; label: string }[] = [
  { tab: 'access', label: 'Access' },
  { tab: 'people', label: 'People' },
  { tab: 'objects', label: 'Objects' },
]
/** A restricted area: every room of a type, or one room. */
type Area = { kind: 'type'; key: string } | { kind: 'space'; key: string }

function storedTab(): Tab {
  try {
    const tab = sessionStorage.getItem(TAB_KEY)
    return tab === 'people' || tab === 'objects' ? tab : 'access'
  } catch {
    return 'access'
  }
}

export function BuildingSettings({ buildingId, plan, admin, objects, access, onClose, onObjects, onShowOnPlan }: {
  buildingId: string
  plan: Plan | null
  admin: boolean
  /** the building's moving objects, as last polled */
  objects: FleetObject[]
  /** the access rules, shared with the Edit mode's Access tool */
  access: AccessRulesState
  onClose: () => void
  /** objects changed: poll now */
  onObjects: () => void
  /** open the Edit mode's Access tool */
  onShowOnPlan: () => void
}) {
  const [tab, setTab] = useState<Tab>(storedTab)
  const [members, setMembers] = useState<AccessMember[] | null>(null)
  const [membersError, setMembersError] = useState<string | null>(null)
  const pick = (next: Tab) => {
    setTab(next)
    try {
      sessionStorage.setItem(TAB_KEY, next)
    } catch {
      // storage unavailable: the tab is remembered for this sheet only
    }
  }

  // members load once for both tabs: People lists them, Access offers their groups
  useEffect(() => {
    if (!admin) return
    let cancelled = false
    api
      .members(buildingId)
      .then((list) => !cancelled && setMembers(list))
      .catch((reason) => !cancelled && setMembersError(message(reason)))
    return () => {
      cancelled = true
    }
  }, [buildingId, admin])

  // every group in use here, for the one-tap chips
  const known = useMemo(() => {
    const rules = access.rules
    const all = [
      ...(members ?? []).flatMap((member) => member.groups),
      ...Object.values(rules?.room_types ?? {}).flat(),
      ...Object.values(rules?.spaces ?? {}).flat(),
    ]
    return [...new Set(all)].filter((group) => group !== PUBLIC_GROUP).sort()
  }, [members, access.rules])

  return (
    <Sheet title="Building settings" onClose={onClose} wide>
      {admin && (
        <div className="settings">
          {plan && <p className="settings-building">{plan.building.name}</p>}
          <div className="pref-scope settings-tabs" role="tablist" aria-label="Settings">
            {TABS.map(({ tab: value, label }) => (
              <button key={value} type="button" role="tab" aria-selected={tab === value} onClick={() => pick(value)}>
                <span>{label}</span>
              </button>
            ))}
          </div>
          {tab === 'access' && <AccessTab access={access} plan={plan} known={known} onShowOnPlan={onShowOnPlan} />}
          {tab === 'people' && (
            <PeopleTab buildingId={buildingId} members={members} error={membersError} known={known} onMembers={setMembers} onError={setMembersError} />
          )}
          {tab === 'objects' && <ObjectsSection buildingId={buildingId} plan={plan} objects={objects} onChanged={onObjects} />}
        </div>
      )}
    </Sheet>
  )
}

// ---------- Access ----------

function AccessTab({ access, plan, known, onShowOnPlan }: { access: AccessRulesState; plan: Plan | null; known: string[]; onShowOnPlan: () => void }) {
  const { rules, error, saving, save } = access
  // an area just picked, waiting for its first group (a rule without groups is no rule)
  const [adding, setAdding] = useState<Area | null>(null)
  const [searching, setSearching] = useState(false)

  if (!rules) return <p className="sheet-hint">{error ?? 'Loading…'}</p>

  const floorName = (floorId: string) => plan?.floors.find((floor) => floor.id === floorId)?.name ?? ''
  const roomsOfType = (type: string) => rules.space_options.filter((space) => space.room_type === type).length
  const spaceOf = (id: string) => rules.space_options.find((space) => space.id === id)
  const groupsOf = (area: Area) => (area.kind === 'type' ? rules.room_types[area.key] : rules.spaces[area.key]) ?? []
  const setGroups = (area: Area, groups: string[]) => {
    const next: AccessRules = area.kind === 'type'
      ? { ...rules, room_types: { ...rules.room_types, [area.key]: groups } }
      : { ...rules, spaces: { ...rules.spaces, [area.key]: groups } }
    if (groups.length && adding?.key === area.key && adding.kind === area.kind) setAdding(null)
    void save(next)
  }
  const remove = (area: Area) => {
    if (adding?.key === area.key && adding.kind === area.kind) setAdding(null)
    else setGroups(area, [])
  }

  const areas: Area[] = [
    ...Object.entries(rules.room_types).filter(([, groups]) => groups.length).map(([key]): Area => ({ kind: 'type', key })),
    ...Object.entries(rules.spaces).filter(([, groups]) => groups.length).map(([key]): Area => ({ kind: 'space', key })),
  ]
  const shown = adding && !areas.some((area) => area.kind === adding.kind && area.key === adding.key) ? [adding, ...areas] : areas

  return (
    <>
      <h4>Who can open this building</h4>
      <div className="pref-group tone-route">
        <div className="pref-row">
          <div className="pref-scope settings-choice" role="radiogroup" aria-label="Who can open this building">
            <button type="button" role="radio" aria-checked={rules.public} onClick={() => !rules.public && void save({ ...rules, public: true })}>
              <Globe size={15} strokeWidth={2} /><span>Everyone</span>
            </button>
            <button type="button" role="radio" aria-checked={!rules.public} onClick={() => rules.public && void save({ ...rules, public: false })}>
              <Lock size={15} strokeWidth={2} /><span>Members only</span>
            </button>
          </div>
          <p className="sheet-hint settings-note">
            {rules.public ? 'Anyone can find and open it. Restricted areas below stay closed to them.' : 'Only its members (People) and the admin can find and open it.'}
          </p>
        </div>
      </div>

      <h4>Restricted areas{areas.length ? ` · ${areas.length}` : ''}</h4>
      <div className="pref-group tone-leave">
        {shown.length === 0 && (
          <div className="pref-row">
            <span className="pref-label">
              <i className="pref-icon" aria-hidden="true"><Globe size={20} strokeWidth={1.9} /></i>
              <span>Nothing is restricted<small>Every room is open to everyone who can open the building.</small></span>
            </span>
          </div>
        )}
        {shown.map((area) => {
          const space = area.kind === 'space' ? spaceOf(area.key) : undefined
          const groups = groupsOf(area)
          const opened = groups.includes(PUBLIC_GROUP)
          const title = area.kind === 'type' ? `Every ${humanise(area.key).toLowerCase()}` : space?.name ?? area.key
          const hint = area.kind === 'type'
            ? `Room type · ${roomsOfType(area.key)} ${roomsOfType(area.key) === 1 ? 'room' : 'rooms'}`
            : [space?.ref, space && floorName(space.floor_id), opened ? 'open to everyone, whatever its type' : null].filter(Boolean).join(' · ')
          const isNew = adding?.kind === area.kind && adding.key === area.key && !groups.length
          return (
            <div className="pref-row settings-area" key={`${area.kind}:${area.key}`}>
              <span className="pref-label">
                <i className="pref-icon" aria-hidden="true">
                  {area.kind === 'type' ? <Shapes size={20} strokeWidth={1.9} /> : <DoorClosed size={20} strokeWidth={1.9} />}
                </i>
                <span>{title}<small>{isNew ? 'Who may enter? Add a group.' : hint}</small></span>
                <button type="button" className="hud-icon settings-remove" onClick={() => remove(area)}
                  aria-label={isNew ? `Cancel ${title}` : `Open ${title} to everyone`} title={isNew ? 'Cancel' : 'Open to everyone'}>
                  {isNew ? <X size={15} strokeWidth={2} /> : <Trash2 size={15} strokeWidth={2} />}
                </button>
              </span>
              <GroupChips
                label={`Groups for ${title}`}
                placeholder="Add a group, e.g. staff"
                groups={groups}
                suggestions={known}
                autoFocus={isNew}
                onChange={(next) => setGroups(area, next)}
              />
            </div>
          )
        })}
      </div>

      {searching ? (
        <AreaSearch
          rules={rules}
          floorName={floorName}
          roomsOfType={roomsOfType}
          onPick={(area) => {
            setSearching(false)
            if (!groupsOf(area).length) setAdding(area)
          }}
          onClose={() => setSearching(false)}
        />
      ) : (
        <div className="settings-actions">
          <button type="button" className="settings-button" onClick={() => setSearching(true)}>
            <Plus size={16} strokeWidth={2.2} /> Restrict an area
          </button>
          <button type="button" className="settings-button quiet" onClick={onShowOnPlan}>
            <Map size={16} strokeWidth={2} /> Show on the plan
          </button>
        </div>
      )}
      <p className={`settings-status${error ? ' failed' : ''}`} role={error ? 'alert' : 'status'}>
        {error ?? (saving ? 'Saving…' : 'Changes are saved as you make them.')}
      </p>
    </>
  )
}

/** Find a room type or a room to restrict. */
function AreaSearch({ rules, floorName, roomsOfType, onPick, onClose }: {
  rules: NonNullable<AccessRulesState['rules']>
  floorName: (floorId: string) => string
  roomsOfType: (type: string) => number
  onPick: (area: Area) => void
  onClose: () => void
}) {
  const [query, setQuery] = useState('')
  const words = query.trim().toLowerCase().split(/\s+/).filter(Boolean)
  const hit = (text: string) => words.every((word) => text.toLowerCase().includes(word))
  const types = rules.room_type_options.filter((type) => hit(`${humanise(type)} ${type}`))
  const rooms = words.length ? rules.space_options.filter((space) => hit(`${space.name} ${space.ref} ${humanise(space.room_type)} ${floorName(space.floor_id)}`)) : []
  return (
    <div className="settings-search">
      <label className="settings-search-field">
        <Search size={16} strokeWidth={2} aria-hidden="true" />
        <input type="text" value={query} onChange={(event) => setQuery(event.target.value)} onKeyDown={(event) => event.key === 'Escape' && (event.stopPropagation(), onClose())} placeholder="A room type or a room: lab, 0140…" autoFocus aria-label="Find an area" />
        <button type="button" className="hud-icon" onClick={onClose} aria-label="Close the search"><X size={15} strokeWidth={2} /></button>
      </label>
      {types.length > 0 && <p className="settings-search-head">Room types</p>}
      <ul>
        {types.slice(0, MATCHES_SHOWN).map((type) => (
          <li key={`type:${type}`}>
            <button type="button" onClick={() => onPick({ kind: 'type', key: type })}>
              <Shapes size={16} strokeWidth={1.9} aria-hidden="true" />
              <span>Every {humanise(type).toLowerCase()}<small>{roomsOfType(type)} {roomsOfType(type) === 1 ? 'room' : 'rooms'}</small></span>
            </button>
          </li>
        ))}
      </ul>
      {rooms.length > 0 && <p className="settings-search-head">Rooms</p>}
      <ul>
        {rooms.slice(0, MATCHES_SHOWN).map((space) => (
          <li key={`space:${space.id}`}>
            <button type="button" onClick={() => onPick({ kind: 'space', key: space.id })}>
              <DoorClosed size={16} strokeWidth={1.9} aria-hidden="true" />
              <span>{space.name}<small>{[space.ref, humanise(space.room_type), floorName(space.floor_id)].filter(Boolean).join(' · ')}</small></span>
            </button>
          </li>
        ))}
      </ul>
      {rooms.length > MATCHES_SHOWN && <p className="sheet-hint">{rooms.length - MATCHES_SHOWN} more rooms — type more of the name.</p>}
      {!words.length && <p className="sheet-hint">Type to find a single room too.</p>}
      {words.length > 0 && !types.length && !rooms.length && <p className="sheet-hint">Nothing matches “{query.trim()}”.</p>}
    </div>
  )
}

// ---------- People ----------

function PeopleTab({ buildingId, members, error, known, onMembers, onError }: {
  buildingId: string
  members: AccessMember[] | null
  error: string | null
  known: string[]
  onMembers: (update: (list: AccessMember[] | null) => AccessMember[]) => void
  onError: (error: string | null) => void
}) {
  const [inviting, setInviting] = useState(false)
  const change = async (member: AccessMember, groups: string[]) => {
    onError(null)
    try {
      const saved = await api.saveMember({ ...member, groups })
      onMembers((list) => (list ?? []).flatMap((item) => (item.user_id !== member.user_id ? [item] : saved.groups.length ? [saved] : [])))
    } catch (reason) {
      onError(message(reason))
    }
  }

  return (
    <>
      <h4>Members{members?.length ? ` · ${members.length}` : ''}</h4>
      <div className="pref-group tone-guide">
        {!members && !error && <div className="pref-row"><p className="sheet-hint settings-note">Loading…</p></div>}
        {members && members.length === 0 && (
          <div className="pref-row">
            <span className="pref-label">
              <i className="pref-icon" aria-hidden="true"><Users size={20} strokeWidth={1.9} /></i>
              <span>No members yet<small>Invite people and give them groups; groups open restricted areas.</small></span>
            </span>
          </div>
        )}
        {members?.map((member) => (
          <div className="pref-row settings-area" key={member.user_id}>
            <span className="pref-label">
              <i className="pref-icon" aria-hidden="true"><UserRound size={20} strokeWidth={1.9} /></i>
              <span className="settings-email">{member.email}<small>{member.groups.join(', ')}</small></span>
              <button type="button" className="hud-icon settings-remove" onClick={() => void change(member, [])}
                aria-label={`Remove ${member.email}`} title="Remove from this building">
                <Trash2 size={15} strokeWidth={2} />
              </button>
            </span>
            <GroupChips label={`Groups for ${member.email}`} placeholder="Add a group" groups={member.groups} suggestions={known}
              onChange={(groups) => groups.length ? void change(member, groups) : undefined} />
          </div>
        ))}
      </div>
      {error && <p className="sheet-error" role="alert">{error}</p>}
      {inviting ? (
        <Invite buildingId={buildingId} known={known} onClose={() => setInviting(false)}
          onInvited={(member) => onMembers((list) => [...(list ?? []).filter((item) => item.user_id !== member.user_id), member])} />
      ) : (
        <div className="settings-actions">
          <button type="button" className="settings-button" onClick={() => setInviting(true)}>
            <UserPlus size={16} strokeWidth={2.2} /> Invite someone
          </button>
        </div>
      )}
    </>
  )
}

function Invite({ buildingId, known, onInvited, onClose }: { buildingId: string; known: string[]; onInvited: (member: AccessMember) => void; onClose: () => void }) {
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
    <form className="sheet-form settings-invite" onSubmit={submit}>
      <div className="settings-invite-head">
        <h4>Invite someone</h4>
        <button type="button" className="hud-icon" onClick={onClose} aria-label="Close the invite"><X size={15} strokeWidth={2} /></button>
      </div>
      <label className="field">
        <span>Email</span>
        <input type="email" value={email} onChange={(event) => setEmail(event.target.value)} required autoComplete="off" autoFocus placeholder="name@example.com" />
      </label>
      <div className="field">
        <span>Groups</span>
        <GroupChips label="Groups for the invite" placeholder="e.g. staff" groups={groups} suggestions={known} onChange={setGroups} />
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
