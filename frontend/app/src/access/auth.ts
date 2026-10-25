// Access mode, client side (docs/superpowers/specs/2026-10-25-access-profiles-design.md): GET /config on start; when
// the backend has access mode on, a Supabase client (loaded lazily, its own chunk) signs in with email + password and
// every API request carries the access token (src/api.ts `auth`). Off = one small request, nothing else: no client,
// no login item, nothing rendered.
// A link from the admin (invite or magic link) lands on the app with the session in the URL; supabase-js picks it
// up. An invite has no password yet, so the app offers to set one.
// `version` goes up whenever the viewer changes (signed in, signed out, another account): the building list and the
// open plan reload on it, and the backend re-filters the session for the new viewer on that request.

import type { SupabaseClient } from '@supabase/supabase-js'
import { useSyncExternalStore } from 'react'
import { api, auth } from '../api'

export type Panel = 'signin' | 'password' | 'preferences' | null

export type AccessState = {
  /** the backend runs access mode */
  mode: boolean
  /** signed-in account, or null */
  email: string | null
  /** the admin (GET /me) */
  admin: boolean
  /** arrived from an invite: the account has no password yet */
  needsPassword: boolean
  /** bumps when the viewer changes */
  version: number
  /** the sign-in / set-password / preferences sheet that is open */
  panel: Panel
  /** a quiet one-line message (signed out by the server, an expired link) */
  notice: string | null
}

let state: AccessState = { mode: false, email: null, admin: false, needsPassword: false, version: 0, panel: null, notice: null }
const listeners = new Set<() => void>()
let client: SupabaseClient | null = null
let userId: string | null = null
let started = false
let noticeTimer: ReturnType<typeof setTimeout> | undefined

const NEEDS_PASSWORD_KEY = 'ttyb-needs-password'
const NOTICE_MS = 5000

function set(patch: Partial<AccessState>) {
  state = { ...state, ...patch }
  listeners.forEach((listener) => listener())
}

const subscribe = (listener: () => void) => {
  listeners.add(listener)
  return () => void listeners.delete(listener)
}

/** For other stores (./preferences.ts): the state now, and a listener for changes. */
export const accessState = () => state
export const onAccessChange = subscribe

export function useAccess(): AccessState {
  return useSyncExternalStore(subscribe, () => state)
}

export function notify(notice: string | null) {
  clearTimeout(noticeTimer)
  set({ notice })
  if (notice) noticeTimer = setTimeout(() => set({ notice: null }), NOTICE_MS)
}

export const openPanel = (panel: Panel) => set({ panel })

function storedFlag(key: string) {
  try {
    return sessionStorage.getItem(key) === 'true'
  } catch {
    return false
  }
}
function storeFlag(key: string, on: boolean) {
  try {
    if (on) sessionStorage.setItem(key, 'true')
    else sessionStorage.removeItem(key)
  } catch {
    // storage unavailable: the flag lasts this page only
  }
}

/** A sign-in supabase-js kept in local storage (its default key `sb-<project>-auth-token`), or one in the URL. */
function maySignIn() {
  if (/access_token=|refresh_token=/.test(location.hash) || /[?&]code=/.test(location.search)) return true
  try {
    return Object.keys(localStorage).some((key) => /^sb-.+-auth-token$/.test(key))
  } catch {
    return false
  }
}

/** Read the link the app was opened from, before supabase-js clears it from the URL. */
function readLink() {
  const params = new URLSearchParams(location.hash.slice(1))
  if (params.get('type') === 'invite') storeFlag(NEEDS_PASSWORD_KEY, true)
  const error = params.get('error_description') ?? params.get('error')
  if (error) {
    notify(params.get('error_code') === 'otp_expired' ? 'This sign-in link has expired. Ask for a new one.' : error.replace(/\+/g, ' '))
    history.replaceState(null, '', location.pathname + location.search)
  }
}

/** Load /config once and, in access mode, the Supabase client and any stored sign-in. */
export function startAccess() {
  if (started) return
  started = true
  // requests wait only when there may be a sign-in to restore; with none they go straight away
  let release: () => void = () => undefined
  if (maySignIn()) auth.setGate(new Promise<void>((resolve) => (release = resolve)))
  const done = () => {
    auth.setGate(null)
    release()
  }
  api
    .config()
    .then(async (config) => {
      if (!config.access_mode) return done()
      readLink()
      set({ mode: true, needsPassword: storedFlag(NEEDS_PASSWORD_KEY) })
      auth.onUnauthorized(() => {
        void client?.auth.signOut({ scope: 'local' })
        notify('You were signed out. Sign in again to see restricted areas.')
      })
      const { createClient } = await import('@supabase/supabase-js')
      client = createClient(config.supabase_url, config.supabase_anon_key)
      client.auth.onAuthStateChange((event, session) => {
        auth.setToken(session?.access_token ?? null)
        if (event === 'INITIAL_SESSION') return // the restore below handles it
        const next = session?.user ?? null
        // supabase-js runs this inside its auth lock: work that calls back into it waits for the next tick
        setTimeout(() => void viewerChanged(next?.id ?? null, next?.email ?? null), 0)
      })
      const { data } = await client.auth.getSession()
      auth.setToken(data.session?.access_token ?? null)
      const user = data.session?.user
      // the restored viewer is the first one: nothing loaded so far needs reloading (requests waited at the gate)
      const restoring = viewerChanged(user?.id ?? null, user?.email ?? null, false)
      done()
      await restoring
    })
    .catch(() => done())
}

async function viewerChanged(id: string | null, email: string | null, reload = true) {
  if (id === userId) return
  userId = id
  const version = state.version + (reload ? 1 : 0)
  if (!id) {
    storeFlag(NEEDS_PASSWORD_KEY, false)
    set({ email: null, admin: false, needsPassword: false, version })
    return
  }
  const needsPassword = storedFlag(NEEDS_PASSWORD_KEY)
  set({ email, admin: false, needsPassword, panel: needsPassword ? 'password' : state.panel === 'signin' ? null : state.panel, version })
  try {
    const me = await api.me()
    if (userId === id) set({ admin: me.admin })
  } catch {
    // /me failed (a 401 signs out on its own); the account just isn't treated as admin
  }
}

export async function signIn(email: string, password: string): Promise<string | null> {
  if (!client) return 'Sign-in is not available.'
  const { error } = await client.auth.signInWithPassword({ email: email.trim(), password })
  return error ? error.message : null
}

export async function signOut() {
  storeFlag(NEEDS_PASSWORD_KEY, false)
  await client?.auth.signOut()
}

export async function setPassword(password: string): Promise<string | null> {
  if (!client) return 'Sign-in is not available.'
  const { error } = await client.auth.updateUser({ password })
  if (error) return error.message
  storeFlag(NEEDS_PASSWORD_KEY, false)
  set({ needsPassword: false, panel: null })
  notify('Password set. Use it to sign in next time.')
  return null
}
