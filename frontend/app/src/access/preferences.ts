// Remembered preferences (access mode; design "Preferences"): `{remember, auto_capture, global, buildings, learned}`.
// Anonymous: this browser's local storage. Signed in: GET/PUT /me/preferences, the server copy wins after sign-in
// (an empty server copy takes this browser's), written back a moment after each change. With `remember` off
// nothing is stored but the two switches, and sessions get no preferences.
// Effective preferences for a building = `global`, overridden field by field by that building's entry.
// `learned` marks the fields the Guide set (a `preference` event, `capture`) until the user changes them by hand; the
// latest capture is shown as a card with Undo (`useLastLearned`). The building on screen (`setHere`) lets the
// Preferences sheet offer that building's own settings beside the general ones.

import { useSyncExternalStore } from 'react'
import { api, type Learned, type Preferences, type PreferenceStore } from '../api'
import { accessState, notify, onAccessChange, openPanel } from './auth'

const KEY = 'ttyb-preferences'
const SAVE_MS = 800

const NO_LEARNED: Learned = { global: [], buildings: {} }
export const EMPTY: PreferenceStore = { remember: true, auto_capture: true, global: {}, buildings: {}, learned: NO_LEARNED }
const LEARNED_MS = 9000

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

const fieldList = (list: unknown): string[] =>
  Array.isArray(list) ? [...new Set(list.map(String).filter((field) => (FIELDS as readonly string[]).includes(field)))] : []

function normalise(data: Partial<PreferenceStore> | null | undefined): PreferenceStore {
  if (!data || typeof data !== 'object') return EMPTY
  const buildings: Record<string, Preferences> = {}
  for (const [id, values] of Object.entries(data.buildings ?? {})) buildings[id] = clean(values as Record<string, unknown>)
  const learnedBuildings: Record<string, string[]> = {}
  for (const [id, list] of Object.entries(data.learned?.buildings ?? {})) {
    const fields = fieldList(list)
    if (fields.length) learnedBuildings[id] = fields
  }
  return {
    remember: data.remember !== false,
    auto_capture: data.auto_capture !== false,
    global: clean(data.global as Record<string, unknown>),
    buildings,
    learned: { global: fieldList(data.learned?.global), buildings: learnedBuildings },
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
  data.remember ? data : { remember: false, auto_capture: data.auto_capture, global: {}, buildings: {}, learned: NO_LEARNED }

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
  update((data) => ({ ...data, global: {}, buildings: {}, learned: NO_LEARNED }))
  setLastLearned(null)
}

/** The fields whose value differs between two sets (a field left out counts as its own value). */
const changedFields = (before: Preferences, after: Preferences) =>
  FIELDS.filter((field) => JSON.stringify(before[field]) !== JSON.stringify(after[field]))

/** The general preferences, set by hand: what changed is no longer "learned". */
export function setGlobal(values: Preferences) {
  update((data) => {
    const changed = changedFields(data.global, values)
    const learned = data.learned ?? NO_LEARNED
    return { ...data, global: values, learned: { ...learned, global: learned.global.filter((field) => !changed.includes(field as never)) } }
  })
}

/** A building's own preferences (its favourites kept), set by hand. */
export function setBuilding(building: string, values: Preferences) {
  update((data) => {
    const before = data.buildings[building] ?? {}
    const changed = changedFields(before, values)
    const learned = data.learned ?? NO_LEARNED
    const left = (learned.buildings[building] ?? []).filter((field) => !changed.includes(field as never))
    const buildings = { ...learned.buildings, [building]: left }
    if (!left.length) delete buildings[building]
    return { ...data, buildings: { ...data.buildings, [building]: { ...values, favourites: before.favourites } }, learned: { ...learned, buildings } }
  })
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

/** Routing fields at their "not set" value. */
const UNSET: Preferences = {
  step_free: false, min_door_width_m: null, avoid_lifts: false, prefer_lifts: false, fewer_doors: false, quiet: false,
  avoid_halls: false, simple_routes: false, avoid_room_types: [], voice: false,
}

/** What goes to the session: the effective preferences, plus "not set" for each routing field the last ones sent
 * had and these lack (Undo, a field set back to General, Forget) — only those, so what the Guide set on the session
 * without remembering it (auto-capture off) stays. */
export function sessionValues(sent: Preferences | null, now: Preferences): Preferences {
  const gone: Preferences = {}
  for (const field of FIELDS) {
    if (sent && field in sent && !(field in now) && field in UNSET) Object.assign(gone, { [field]: UNSET[field] })
  }
  return { ...gone, ...now }
}

// ---- the building on screen, and which part of the Preferences sheet opens

export type Here = { id: string; name: string; roomTypes: string[]; spaceName: (id: string) => string | undefined }
export type PreferencesTab = 'everywhere' | 'here'
let here: Here | null = null
let tab: PreferencesTab = 'everywhere'

export function setHere(next: Here | null) {
  here = next
  if (!next) tab = 'everywhere'
  emit()
}

export const useHere = () => useSyncExternalStore(subscribe, () => here)
export const preferencesTab = () => tab

/** Open the Preferences sheet on its general part or on the building on screen. */
export function openPreferences(which: PreferencesTab = 'everywhere') {
  tab = which === 'here' && here ? 'here' : 'everywhere'
  openPanel('preferences')
}

// ---- what the Guide just learned: a card with Undo

export type LastLearned = { scope: 'global' | 'building'; building: string; buildingName: string | null; said: string[]; undo: () => void }
let lastLearned: LastLearned | null = null
// one Guide turn can send several preference events: they merge into one card, Undo going back to before the first
const MERGE_MS = 1500
let turn: { at: number; before: PreferenceStore; said: Map<string, string> } | null = null
let learnedTimer: ReturnType<typeof setTimeout> | undefined

function setLastLearned(next: LastLearned | null) {
  clearTimeout(learnedTimer)
  lastLearned = next
  emit()
  if (next) learnedTimer = setTimeout(() => setLastLearned(null), LEARNED_MS)
}

export const useLastLearned = () => useSyncExternalStore(subscribe, () => lastLearned)
export const dismissLearned = () => setLastLearned(null)

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

/** A `preference` event from the Guide: merged when remembering and auto-capture are on, its fields marked as
 * learned; the card says what, where (everywhere or this building) and offers Undo. */
export function capture(scope: 'global' | 'building', values: Record<string, unknown>, building: string, spaceName: (id: string) => string | undefined) {
  if (!store.remember || !store.auto_capture) return
  const said: string[] = []
  const favourite = typeof values.favourite === 'string' ? values.favourite : null
  const fields = clean(values)
  delete fields.favourites
  const names = Object.keys(fields)
  const merging = turn !== null && lastLearned !== null && Date.now() - turn.at < MERGE_MS
  if (!merging) turn = { at: Date.now(), before: store, said: new Map() }
  const current = turn!
  for (const [field, value] of Object.entries(fields)) current.said.set(field, LABELS[field]?.(value) ?? field)
  const before = current.before
  update((data) => {
    const own = { ...data.buildings[building] }
    if (favourite) own.favourites = [...new Set([...(own.favourites ?? []), favourite])]
    if (scope === 'building') Object.assign(own, fields)
    const buildings = favourite || scope === 'building' ? { ...data.buildings, [building]: own } : data.buildings
    const learned = data.learned ?? NO_LEARNED
    const marked = scope === 'global'
      ? { ...learned, global: [...new Set([...learned.global, ...names])] }
      : { ...learned, buildings: { ...learned.buildings, [building]: [...new Set([...(learned.buildings[building] ?? []), ...names])] } }
    return { ...data, global: scope === 'global' ? { ...data.global, ...fields } : data.global, buildings, learned: names.length ? marked : learned }
  })
  if (favourite) current.said.set(`favourite:${favourite}`, `favourite ${spaceName(favourite) ?? 'place'}`)
  said.push(...current.said.values()) // the last value of each field this turn
  if (!said.length) return
  setLastLearned({
    // a favourite is always this building's; the fields go where the Guide put them
    scope: favourite && !names.length ? 'building' : scope,
    building,
    buildingName: here?.id === building ? here.name : null,
    said,
    undo: () => {
      replace({ ...before, remember: store.remember, auto_capture: store.auto_capture })
      setLastLearned(null)
      notify('Undone.')
    },
  })
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
