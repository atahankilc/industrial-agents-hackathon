// Opening a building: its session and plan, fetched once per visit. A tap on the map starts it (prefetch), so the
// download runs while the camera flies in, and the screen that mounts takes the same promise (React's dev double
// mount included). Once the screen is gone the entry is dropped, so the next visit starts a fresh session.

import { api, type Plan } from '../api'

export type Opened = { sessionId: string; plan: Plan }
type Entry = { promise: Promise<Opened>; users: number; timer?: ReturnType<typeof setTimeout> }

const entries = new Map<string, Entry>()
const UNUSED_MS = 10_000 // a prefetch nobody took
const AFTER_MS = 1_000 // after the last screen let go

function entry(id: string): Entry {
  let found = entries.get(id)
  if (!found) {
    const promise = api.createSession(id).then(async ({ session_id }) => ({ sessionId: session_id, plan: await api.plan(session_id) }))
    const created: Entry = { promise, users: 0 }
    promise.catch(() => entries.get(id) === created && entries.delete(id))
    entries.set(id, created)
    found = created
  }
  return found
}

function dropLater(id: string, item: Entry, ms: number) {
  clearTimeout(item.timer)
  item.timer = setTimeout(() => {
    if (!item.users && entries.get(id) === item) entries.delete(id)
  }, ms)
}

export function prefetch(id: string) {
  const item = entry(id)
  if (!item.users) dropLater(id, item, UNUSED_MS)
}

/** The building's session and plan; call `release` when the screen goes. */
export function take(id: string): { promise: Promise<Opened>; release: () => void } {
  const item = entry(id)
  item.users += 1
  clearTimeout(item.timer)
  return {
    promise: item.promise,
    release: () => {
      item.users -= 1
      dropLater(id, item, AFTER_MS)
    },
  }
}
