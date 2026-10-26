// The Edit mode's Access tool, in the Guide's card (src/edit/EditCard.tsx): who may enter the room tapped on the
// plan — every room of its type, or this room alone (an exception wins over its type; "public" opens one room to
// everyone) — and, with no room picked, whether the building is public at all. Saved at once on the building
// itself (./useAccessRules.ts), not on the copy being edited. Members, invites and moving objects stay in the
// Building settings sheet (./BuildingSettings.tsx), one tap away.

import { Globe, Lock, Settings } from 'lucide-react'
import { GroupChips } from './Sheet'
import { groupsFor, PUBLIC_GROUP, type AccessRulesState } from './useAccessRules'

const humanise = (type: string) => type.replace(/_/g, ' ').replace(/^\w/, (c) => c.toUpperCase())
const list = (groups: string[]) => groups.join(', ')

export function AccessCard({ access, spaceId, spaceName, onSettings }: {
  access: AccessRulesState
  /** the room picked on the plan, if any */
  spaceId: string | null
  /** its name in the draft (a room the edit added is not in the building yet) */
  spaceName: string | null
  onSettings: () => void
}) {
  const { rules, error, saving, save, restricted } = access
  if (!rules) {
    return (
      <div className="inspector">
        <p className="who">Access</p>
        <p className="inspector-note">{error ?? 'Loading who may go where…'}</p>
      </div>
    )
  }
  const space = spaceId ? rules.space_options.find((item) => item.id === spaceId) : undefined
  const status = error ? <p className="edit-problem" role="alert">{error}</p> : saving ? <p className="inspector-note">Saving…</p> : null

  if (spaceId && !space) {
    return (
      <div className="inspector">
        <p className="who">Access</p>
        <p className="inspector-name">{spaceName ?? 'New room'}</p>
        <p className="inspector-note">This room is only in your edited copy. Save the copy as a building first, then set who may enter it there.</p>
      </div>
    )
  }

  if (!space) {
    const count = restricted.size
    return (
      <div className="inspector">
        <p className="who">Access</p>
        <p className="inspector-title"><Lock size={16} />Who may go where</p>
        <p className="inspector-note">
          Tap a room on the plan to choose who may enter it. {count ? `${count} ${count === 1 ? 'room is' : 'rooms are'} restricted — shaded on the plan.` : 'Every room is open to everyone.'}
        </p>
        <div className="fields">
          <label className="field toggle">
            <span>Public</span>
            <input type="checkbox" role="switch" checked={rules.public} onChange={(event) => void save({ ...rules, public: event.target.checked })} />
          </label>
        </div>
        <p className="inspector-note">{rules.public ? 'Anyone can open this building.' : 'Only its members and the admin can open this building.'} Changes apply to the building right away, not to your edited copy.</p>
        {status}
        <button type="button" className="access-settings" onClick={onSettings}><Settings size={15} /> Members, invites and objects</button>
      </div>
    )
  }

  const allowed = groupsFor(rules, space)
  const ofType = rules.room_types[space.room_type] ?? []
  const own = rules.spaces[space.id] ?? []
  return (
    <div className="inspector">
      <p className="who">Access</p>
      <p className="inspector-name">{space.name}</p>
      <p className={`access-status${allowed ? ' restricted' : ''}`}>
        {allowed ? <Lock size={14} strokeWidth={2.2} /> : <Globe size={14} strokeWidth={2.2} />}
        {allowed ? `Only ${list(allowed)}` : 'Open to everyone'}
      </p>
      <div className="fields access-fields">
        {space.room_type && (
          <div className="field">
            <span>Every “{humanise(space.room_type)}”</span>
            <GroupChips label={`Groups for every ${humanise(space.room_type)}`} placeholder="Everyone" groups={ofType}
              onChange={(groups) => void save({ ...rules, room_types: { ...rules.room_types, [space.room_type]: groups } })} />
          </div>
        )}
        <div className="field">
          <span>This room</span>
          <GroupChips label={`Groups for ${space.name}`} placeholder={space.room_type ? 'As its type' : 'Everyone'} groups={own}
            onChange={(groups) => void save({ ...rules, spaces: { ...rules.spaces, [space.id]: groups } })} />
        </div>
      </div>
      <p className="inspector-note">
        Type a group and press Enter, e.g. staff. This room wins over its type{own.includes(PUBLIC_GROUP) ? '' : ' — add “public” to open just this room to everyone'}.
      </p>
      {status}
    </div>
  )
}
