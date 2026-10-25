// What the plan is currently showing as an answer, built only from the map events of the Guide's replies.

import type { ElsewhereEvent, GuideStep, NextBuilding, RouteLeg, UiEvent } from '../api'

/** Route events carry the line to draw: [[x, y, floor_index], …] in plan metres. */
export type DevEvent = UiEvent & { line?: [number, number, number][] }

export type StoryRoute = {
  line: [number, number, number][]
  legs: RouteLeg[]
  /** the Guide's followable steps, for the route bar and step card (Guide replies only) */
  steps: GuideStep[]
  length_m: number | null
  profile: string | null
  space_path: string[]
  /** the route goes on in a nearby building (route_to_building): its Continue */
  next?: NextBuilding | null
}

export type Story = {
  /** rooms the answer is about: outlined in accent */
  focus: string[]
  /** items the answer is about: a dot on each */
  assets: string[]
  route: StoryRoute | null
  /** rooms that lost access after a change: dashed outline */
  lost: string[]
  /** the answer is in buildings next to this one (search_nearby_buildings) */
  elsewhere?: ElsewhereEvent['buildings'] | null
  /** bumps on every new answer */
  key: number
  /** live tracking (building/useTracking): where you are on the route and which way it goes on; set by the
   * building screen, never by events */
  you?: You
  /** the step being followed (set by the building screen, never by events): drawn on the route band */
  step?: StepView
  /** the step on the card, pinned on the map where it is made (set by the building screen whenever a route is shown) */
  move?: Move
  outdoor?: Outdoor | null
  /** rooms the user might be in, their position not known (set by the building screen from a `maybe_here` event):
   * dashed outlines, and a badge on each that stands them there */
  maybe?: string[]
}

/** The step being followed, in metres along the drawn line: walked up to `done`, the step from `from` to `to`, and
 * where it ends (the next move happens there: `next` is that step, for its arrow). */
export type StepView = { done: number; from: number; to: number; end: [number, number]; floor: number; next: GuideStep | null }

/** `along`: metres along the drawn line (as StepView), so the puck can glide along the route to a new place */
export type Move = { at: [number, number]; floor: number; step: GuideStep; index: number }

export type You = { at: [number, number]; floor: number; ahead: [number, number]; stale: boolean; along?: number }

/** The walk outside to a nearby building (route_to_building), in this building's plan metres; set by the building
 * screen from the route's `next` and the map origin, never by events */
export type Outdoor = { from: [number, number]; to: [number, number]; floor: number; label: string }

export const EMPTY_STORY: Story = { focus: [], assets: [], route: null, lost: [], key: 0 }

/** A route or a highlight is a new answer (replaces the last); lost access adds to it; a change keeps it. Highlights
 * one after another in the same reply are one answer: a later one adds its rooms (the kitchens the Guide asks about
 * and the canteen it found), unless all of them are shown already — then it narrows to them (show_on_map picking one
 * of a search's results). */
export function applyEvents(story: Story, events: DevEvent[]): Story {
  let next = story
  let shown: { focus: string[]; assets: string[] } | null = null // this reply's highlights so far
  for (const event of events) {
    if (event.type === 'highlight' && !event.style && shown) {
      const before = shown
      const narrows = event.space_ids.every((id) => before.focus.includes(id)) && (event.asset_ids ?? []).every((id) => before.assets.includes(id))
      const focus: string[] = narrows ? event.space_ids : [...new Set([...before.focus, ...event.space_ids])]
      const assets: string[] = narrows ? event.asset_ids ?? [] : [...new Set([...before.assets, ...(event.asset_ids ?? [])])]
      shown = { focus, assets }
      next = { ...next, focus, assets }
      continue
    }
    if (event.type === 'highlight' && !event.style) shown = { focus: event.space_ids, assets: event.asset_ids ?? [] }
    else if (event.type === 'route' || event.type === 'route_end' || event.type === 'elsewhere') shown = null
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
          next: event.next_building ?? null,
        },
        lost: [],
        key: next.key + 1,
      }
    } else if (event.type === 'highlight' && event.style === 'lost_access') {
      next = { ...next, lost: event.space_ids, key: next.key + 1 }
    } else if (event.type === 'highlight') {
      next = { focus: event.space_ids, assets: event.asset_ids ?? [], route: null, lost: [], key: next.key + 1 }
    } else if (event.type === 'route_end') {
      next = { ...EMPTY_STORY, key: next.key + 1 }
    } else if (event.type === 'elsewhere') {
      next = { ...EMPTY_STORY, elsewhere: event.buildings, key: next.key + 1 }
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

export const isEmpty = (story: Story) => !story.focus.length && !story.assets.length && !story.route && !story.lost.length && !story.elsewhere?.length
