// What the plan is currently showing as an answer, built only from map events (dev-panel tool calls and Guide
// replies alike), so a hand-made answer looks exactly like one the Guide will give.

import type { GuideStep, RouteLeg } from '../api'
import type { DevEvent } from './devApi'

export type StoryRoute = {
  line: [number, number, number][]
  legs: RouteLeg[]
  /** the Guide's followable steps, for the next-move card (Guide replies only; empty from dev-panel tools) */
  steps: GuideStep[]
  length_m: number | null
  profile: string | null
  space_path: string[]
}

export type Story = {
  /** rooms the answer is about: outlined in accent */
  focus: string[]
  /** items the answer is about: a dot on each */
  assets: string[]
  route: StoryRoute | null
  /** rooms that lost access after a change: dashed outline */
  lost: string[]
  /** bumps on every new answer */
  key: number
  /** live tracking (building/useTracking): where you are on the route and which way it goes on; set by the
   * building screen, never by events */
  you?: You
}

export type You = { at: [number, number]; floor: number; ahead: [number, number]; stale: boolean }

export const EMPTY_STORY: Story = { focus: [], assets: [], route: null, lost: [], key: 0 }

/** A route or a highlight is a new answer (replaces the last); lost access adds to it; a change keeps it. */
export function applyEvents(story: Story, events: DevEvent[]): Story {
  let next = story
  for (const event of events) {
    if (event.type === 'route') {
      const path = event.space_path ?? []
      const last = path[path.length - 1]
      next = {
        focus: last && last !== 'outside' ? [last] : [],
        assets: [],
        route: {
          line: event.line ?? [],
          legs: event.legs ?? [],
          steps: event.steps ?? [],
          length_m: event.length_m ?? null,
          profile: event.profile ?? null,
          space_path: path,
        },
        lost: [],
        key: next.key + 1,
      }
    } else if (event.type === 'highlight' && event.style === 'lost_access') {
      next = { ...next, lost: event.space_ids, key: next.key + 1 }
    } else if (event.type === 'highlight') {
      next = { focus: event.space_ids, assets: [], route: null, lost: [], key: next.key + 1 }
    }
  }
  return next
}

export const showAssets = (story: Story, assets: { id: string; space: string }[]): Story => ({
  focus: [...new Set(assets.map((asset) => asset.space))],
  assets: assets.map((asset) => asset.id),
  route: null,
  lost: [],
  key: story.key + 1,
})

export const showRooms = (story: Story, ids: string[]): Story => ({ focus: ids, assets: [], route: null, lost: [], key: story.key + 1 })

export const isEmpty = (story: Story) => !story.focus.length && !story.assets.length && !story.route && !story.lost.length
