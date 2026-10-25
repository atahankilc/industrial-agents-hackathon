// Remembered preferences (access mode; design "Preferences"): `{remember, auto_capture, global, buildings}`.
// Anonymous: this browser's local storage. Signed in: GET/PUT /me/preferences, the server copy wins after sign-in
// (an empty server copy takes this browser's), written back a moment after each change. With `remember` off
// nothing is stored but the two switches, and sessions get no preferences.
// Effective preferences for a building = `global`, overridden field by field by that building's entry.

import { useSyncExternalStore } from 'react'
import { api, type Preferences, type PreferenceStore } from '../api'
import { accessState, notify, onAccessChange } from './auth'

const KEY = 'ttyb-preferences'
const SAVE_MS = 800

export const EMPTY: PreferenceStore = { remember: true, auto_capture: true, global: {}, buildings: {} }

/** Routing and talking fields, in the order the settings show them; favourites are per building, kept apart. */
export const FIELDS = [
  'step_free', 'min_door_width_m', 'avoid_lifts', 'prefer_lifts', 'fewer_doors', 'quiet', 'avoid_halls',
  'simple_routes', 'avoid_room_types', 'language', 'reply_style', 'voice',
] as const
export type Field = (typeof FIELDS)[number]

let store: PreferenceStore = readLocal()
let signedIn: string | null = null
let saveTimer: ReturnType<typeof setTimeout> | undefined
const listeners = new Set<() => void>()

function emit() {
  listeners.forEach((listener) => listener())
}

const subscribe = (listener: () => void) => {
  listeners.add(listener)
  return () => void listeners.delete(listener)
}

export function usePreferences(): PreferenceStore {
  return useSyncExternalStore(subscribe, () => store)
}

/** Only the known fields, with sane types (what the Guide sends may carry others, e.g. `forklift`). */
function clean(values: Record<string, unknown> | undefined): Preferences {
  const out: Preferences = {}
  if (!values) return out
  for (const field of ['step_free', 'avoid_lifts', 'prefer_lifts', 'fewer_doors', 'quiet', 'avoid_halls', 'simple_routes', 'voice'] as const) {
    if (typeof values[field] === 'boolean') out[field] = values[field] as boolean
  }
  if ('min_door_width_m' in values) {
    const width = Number(values.min_door_width_m)
    out.min_door_width_m = values.min_door_width_m === null || !width || width < 0 ? null : width
  }
  if (Array.isArray(values.avoid_room_types)) out.avoid_room_types = values.avoid_room_types.map(String)
  if (typeof values.language === 'string' && values.language.trim()) out.language = values.language.trim()
  if (values.reply_style === 'brief' || values.reply_style === 'detailed') out.reply_style = values.reply_style
  if (Array.isArray(values.favourites)) out.favourites = [...new Set(values.favourites.map(String))]
  return out
}

function normalise(data: Partial<PreferenceStore> | null | undefined): PreferenceStore {
  if (!data || typeof data !== 'object') return EMPTY
  const buildings: Record<string, Preferences> = {}
  for (const [id, values] of Object.entries(data.buildings ?? {})) buildings[id] = clean(values as Record<string, unknown>)
  return {
    remember: data.remember !== false,
    auto_capture: data.auto_capture !== false,
    global: clean(data.global as Record<string, unknown>),
    buildings,
  }
}

function readLocal(): PreferenceStore {
  try {
    const raw = localStorage.getItem(KEY)
    return raw ? normalise(JSON.parse(raw)) : EMPTY
  } catch {
    return EMPTY
  }
}

/** What may be stored: everything, or with `remember` off only the switches. */
const storable = (data: PreferenceStore): PreferenceStore =>
  data.remember ? data : { remember: false, auto_capture: data.auto_capture, global: {}, buildings: {} }

function persist() {
  clearTimeout(saveTimer)
  const data = storable(store)
  if (!signedIn) {
    try {
      localStorage.setItem(KEY, JSON.stringify(data))
    } catch {
      // storage unavailable: kept for this page only
    }
    return
  }
  const who = signedIn
  saveTimer = setTimeout(() => {
    if (signedIn !== who) return
    api.saveMyPreferences(data).catch(() => notify('Could not save your preferences.'))
  }, SAVE_MS)
}

function replace(next: PreferenceStore, save = true) {
  store = next
  emit()
  if (save) persist()
}

export function update(change: (data: PreferenceStore) => PreferenceStore) {
  replace(change(store))
}

/** Forget everything: no preferences, no favourites (the switches stay as they are). */
export function forgetAll() {
  update((data) => ({ ...data, global: {}, buildings: {} }))
}

/** global ← building, field by field; favourites left out (they are not routing input). */
export function effective(data: PreferenceStore, building: string): Preferences {
  if (!data.remember) return {}
  const own = { ...data.buildings[building] }
  delete own.favourites
  const values = { ...data.global, ...own }
  if (!values.language) delete values.language // "here" chosen but left empty: no language preference
  return values
}

const LABELS: Record<string, (value: unknown) => string> = {
  step_free: (on) => (on ? 'step-free routes' : 'routes with steps allowed'),
  min_door_width_m: (width) => (width ? `doors at least ${width} m wide` : 'any door width'),
  avoid_lifts: (on) => (on ? 'no lifts' : 'lifts allowed'),
  prefer_lifts: (on) => (on ? 'lifts over stairs' : 'stairs are fine'),
  fewer_doors: (on) => (on ? 'fewer doors' : 'any number of doors'),
  quiet: (on) => (on ? 'quiet route' : 'any route'),
  avoid_halls: (on) => (on ? 'avoid halls' : 'halls are fine'),
  simple_routes: (on) => (on ? 'simple routes' : 'shortest routes'),
  avoid_room_types: (rooms) => (Array.isArray(rooms) && rooms.length ? `avoid ${rooms.map((room) => String(room).replace(/_/g, ' ')).join(', ')}` : 'no rooms avoided'),
  language: (language) => `language ${language}`,
  reply_style: (style) => `${style} replies`,
  voice: (on) => (on ? 'spoken replies' : 'no spoken replies'),
}

/** A `preference` event from the Guide: merged when remembering and auto-capture are on; a quiet line says what. */
export function capture(scope: 'global' | 'building', values: Record<string, unknown>, building: string, spaceName: (id: string) => string | undefined) {
  if (!store.remember || !store.auto_capture) return
  const said: string[] = []
  const favourite = typeof values.favourite === 'string' ? values.favourite : null
  const fields = clean(values)
  for (const [field, value] of Object.entries(fields)) said.push(LABELS[field]?.(value) ?? field)
  update((data) => {
    const own = { ...data.buildings[building] }
    if (favourite) own.favourites = [...new Set([...(own.favourites ?? []), favourite])]
    if (scope === 'building') Object.assign(own, fields)
    const buildings = favourite || scope === 'building' ? { ...data.buildings, [building]: own } : data.buildings
    return { ...data, global: scope === 'global' ? { ...data.global, ...fields } : data.global, buildings }
  })
  if (favourite) said.push(`favourite ${spaceName(favourite) ?? 'place'}`)
  if (said.length) notify(`Remembered${scope === 'building' && !favourite ? ' for this building' : ''}: ${said.join(', ')}`)
}

// ---- follow the viewer: local copy when anonymous, the server copy when signed in

async function viewer(email: string | null) {
  if (email === signedIn) return
  clearTimeout(saveTimer)
  signedIn = email
  if (!email) {
    replace(readLocal(), false)
    return
  }
  try {
    const server = await api.myPreferences()
    if (signedIn !== email) return
    if (server && Object.keys(server).length) replace(normalise(server), false)
    else replace(readLocal()) // nothing on the server yet: this browser's preferences become the account's
  } catch {
    // the server copy is unavailable: keep what this page has, without overwriting the account's
  }
}

onAccessChange(() => {
  const access = accessState()
  if (access.mode) void viewer(access.email)
})
