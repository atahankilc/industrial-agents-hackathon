// A building's access rules for the Edit mode's Access tool (./AccessCard.tsx): loaded from GET /access/building,
// every change saved straight away with PUT /access/building (admin only). The rules belong to the building
// itself, not to the draft copy the Edit mode reshapes, so they apply at once. `restricted` is what the plan marks:
// the spaces only some groups may enter, worked out like backend/api/access.py BuildingAccess.groups_for.

import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { api, type AccessRules, type BuildingAccess } from '../api'

export const PUBLIC_GROUP = 'public'

const message = (reason: unknown) => {
  const text = reason instanceof Error ? reason.message : String(reason)
  const match = text.match(/"detail":\s*"((?:[^"\\]|\\.)*)"/)
  return match ? JSON.parse(`"${match[1]}"`) : text
}

/** Drop rules with no groups (no rule = public). */
export function cleaned(rules: Record<string, string[]>) {
  return Object.fromEntries(Object.entries(rules).filter(([, groups]) => groups.length))
}

/** The groups that may enter a space, or null when everyone may (backend/api/access.py groups_for). */
export function groupsFor(rules: AccessRules, space: { id: string; room_type: string }): string[] | null {
  const own = rules.spaces[space.id]
  const groups = own?.length ? own : rules.room_types[space.room_type]
  return !groups?.length || groups.includes(PUBLIC_GROUP) ? null : groups
}

export function useAccessRules(buildingId: string, active: boolean) {
  const [loaded, setLoaded] = useState<BuildingAccess | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)
  const [version, setVersion] = useState(0)
  const sent = useRef(0) // the newest save; an older answer arriving late is ignored

  useEffect(() => {
    if (!active) return
    let cancelled = false
    setError(null)
    api
      .accessBuilding(buildingId)
      .then((data) => !cancelled && setLoaded(data))
      .catch((reason) => !cancelled && setError(message(reason)))
    return () => {
      cancelled = true
    }
  }, [buildingId, active, version])

  /** Save the rules now; shown at once, put back if the backend refuses. */
  const save = useCallback(async (next: AccessRules) => {
    if (!loaded) return
    const before = loaded
    const id = ++sent.current
    setLoaded({ ...loaded, ...next })
    setSaving(true)
    setError(null)
    try {
      const saved = await api.saveAccessBuilding(buildingId, { public: next.public, room_types: cleaned(next.room_types), spaces: cleaned(next.spaces) })
      if (id === sent.current) setLoaded((current) => (current ? { ...current, public: saved.public, room_types: saved.room_types, spaces: saved.spaces } : current))
    } catch (reason) {
      if (id === sent.current) {
        setLoaded(before)
        setError(message(reason))
      }
    } finally {
      if (id === sent.current) setSaving(false)
    }
  }, [buildingId, loaded])

  // another building's rules (the screen moved on before this one's arrived) are not shown
  const rules = loaded?.building === buildingId ? loaded : null
  const restricted = useMemo(
    () => new Set(rules ? rules.space_options.filter((space) => groupsFor(rules, space)).map((space) => space.id) : []),
    [rules],
  )

  return { rules, error, saving, save, restricted, reload: useCallback(() => setVersion((value) => value + 1), []) }
}

export type AccessRulesState = ReturnType<typeof useAccessRules>
