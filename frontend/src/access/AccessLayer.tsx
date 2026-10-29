// The settings corner over every screen (rendered by Root): a button top right whose menu has the theme and, in
// access mode, Preferences and the account (sign in, set a password, sign out). On the landing (the map) it is a
// pill; over a building a round button beside the HUD's top line.
// Access mode also brings the sign-in, set-a-password and Preferences sheets and the quiet notice line.

import { AudioLines, Building2, KeyRound, LogIn, LogOut, Moon, Settings, SlidersHorizontal, Sun, SunMoon, UserRound, X } from 'lucide-react'
import { useEffect, useRef, useState, type FormEvent } from 'react'
import { useTheme } from '../theme'
import { openPanel, setPassword, signIn, signOut, useAccess } from './auth'
import { PreferencesSheet } from './PreferencesForm'
import { dismissLearned, openPreferences, useLastLearned } from './preferences'
import { Sheet } from './Sheet'
import './access.css'

const THEME_ICON = { system: SunMoon, light: Sun, dark: Moon }
const THEME_LABEL = { system: 'Theme: system', light: 'Theme: light', dark: 'Theme: dark' }

export function AccessLayer({ landing = false }: { landing?: boolean }) {
  const access = useAccess()
  return (
    <div className="access-layer">
      <Corner compact={!landing} />
      {access.mode && access.panel === 'signin' && <SignIn />}
      {access.mode && access.panel === 'password' && access.email && <SetPassword email={access.email} />}
      {access.mode && access.panel === 'preferences' && <PreferencesSheet />}
      {access.mode && <LearnedCard />}
      {access.mode && access.notice && (
        <p className="access-notice" role="status">
          {access.notice}
        </p>
      )}
    </div>
  )
}

/** What the Guide just learned from the user: what, where it applies (everywhere or this building only), with Undo
 * and a way to the Preferences part it went into. */
function LearnedCard() {
  const learned = useLastLearned()
  if (!learned) return null
  const where = learned.scope === 'global' ? 'Everywhere' : `Only in ${learned.buildingName ?? 'this building'}`
  return (
    <aside className="learned-card" role="status" aria-label="The Guide remembered">
      <i className="learned-icon" aria-hidden="true"><AudioLines size={16} strokeWidth={2.2} /></i>
      <div className="learned-text">
        <p className="learned-title">
          Remembered <em>{where}</em>
        </p>
        <p className="learned-what">{learned.said.join(' · ')}</p>
        <div className="learned-actions">
          <button type="button" onClick={learned.undo}>Undo</button>
          <button type="button" onClick={() => { dismissLearned(); openPreferences(learned.scope === 'global' ? 'everywhere' : 'here') }}>See preferences</button>
        </div>
      </div>
      <button type="button" className="hud-icon" aria-label="Dismiss" onClick={dismissLearned}>
        <X size={14} strokeWidth={2.2} />
      </button>
    </aside>
  )
}

/** The organisations sheet (?view=org, src/org/OrgScreen.tsx), opened the way Root reads the address. */
function openOrganisations() {
  const params = new URLSearchParams(location.search)
  for (const key of ['view', 'org', 'building', 'edit']) params.delete(key)
  params.set('view', 'org')
  history.pushState(null, '', `${location.pathname}?${params}`)
  dispatchEvent(new PopStateEvent('popstate'))
}

/** The settings button top right: the theme, and in access mode Preferences and the account. */
function Corner({ compact }: { compact: boolean }) {
  const access = useAccess()
  const theme = useTheme()
  const [open, setOpen] = useState(false)
  const corner = useRef<HTMLDivElement>(null)
  // a press anywhere else, or Escape, closes the menu
  useEffect(() => {
    if (!open) return
    const onDown = (event: PointerEvent) => {
      if (!corner.current?.contains(event.target as Node)) setOpen(false)
    }
    const onKey = (event: KeyboardEvent) => event.key === 'Escape' && setOpen(false)
    addEventListener('pointerdown', onDown, true)
    addEventListener('keydown', onKey)
    return () => {
      removeEventListener('pointerdown', onDown, true)
      removeEventListener('keydown', onKey)
    }
  }, [open])
  const pick = (action: () => void) => () => {
    setOpen(false)
    action()
  }
  const ThemeIcon = THEME_ICON[theme.mode]
  const Icon = access.mode ? UserRound : Settings
  const label = access.mode ? (access.email ?? 'Account') : 'Settings'
  return (
    <div ref={corner} className={`account-corner${compact ? ' compact' : ''}`}>
      <button
        type="button"
        className="account-button"
        aria-haspopup="menu"
        aria-expanded={open}
        aria-label={compact ? label : undefined}
        title={compact ? label : undefined}
        onClick={() => setOpen((value) => !value)}
      >
        <Icon size={compact ? 19 : 16} strokeWidth={2} />
        {!compact && <span className="account-email">{label}</span>}
        {!compact && access.admin && <em className="account-role">admin</em>}
      </button>
      {open && (
        <div className="account-menu" role="menu">
          {compact && access.email && <p className="account-line" title={access.email}>{access.email}</p>}
          {/* the theme cycles in place, so the menu stays open */}
          <button type="button" role="menuitem" onClick={theme.cycle}>
            <ThemeIcon size={16} strokeWidth={2} />
            {THEME_LABEL[theme.mode]}
          </button>
          {access.mode && (
            <button type="button" role="menuitem" onClick={pick(() => openPreferences())}>
              <SlidersHorizontal size={16} strokeWidth={2} />
              Preferences
            </button>
          )}
          {access.mode && !access.email && (
            <button type="button" role="menuitem" onClick={pick(() => openPanel('signin'))}>
              <LogIn size={16} strokeWidth={2} />
              Sign in
            </button>
          )}
          {access.email && (
            <button type="button" role="menuitem" onClick={pick(openOrganisations)}>
              <Building2 size={16} strokeWidth={2} />
              Organisations
            </button>
          )}
          {access.email && access.needsPassword && (
            <button type="button" role="menuitem" onClick={pick(() => openPanel('password'))}>
              <KeyRound size={16} strokeWidth={2} />
              Set a password
            </button>
          )}
          {access.email && (
            <button type="button" role="menuitem" onClick={pick(() => void signOut())}>
              <LogOut size={16} strokeWidth={2} />
              Sign out
            </button>
          )}
          {/* signed out the Preferences are kept in this browser's local storage (./preferences.ts) */}
          {access.mode && !access.email && <p className="account-hint">Signed out, your preferences stay in this browser.</p>}
          {access.admin && !compact && <p className="account-hint">Access, members and objects: open a building and tap the shield button, or ask the Guide.</p>}
        </div>
      )}
    </div>
  )
}

function SignIn() {
  const [email, setEmail] = useState('')
  const [password, setPasswordText] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const submit = async (event: FormEvent) => {
    event.preventDefault()
    setBusy(true)
    setError(await signIn(email, password))
    setBusy(false)
  }
  return (
    <Sheet title="Sign in" onClose={() => openPanel(null)}>
      <form className="sheet-form" onSubmit={submit}>
        <p className="sheet-hint">Members and the building admin sign in to see restricted areas.</p>
        <label className="field">
          <span>Email</span>
          <input type="email" autoComplete="username" value={email} onChange={(event) => setEmail(event.target.value)} required autoFocus />
        </label>
        <label className="field">
          <span>Password</span>
          <input type="password" autoComplete="current-password" value={password} onChange={(event) => setPasswordText(event.target.value)} required />
        </label>
        {error && <p className="sheet-error" role="alert">{error}</p>}
        <button type="submit" className="hud-primary" disabled={busy || !email || !password}>
          {busy ? 'Signing in…' : 'Sign in'}
        </button>
      </form>
    </Sheet>
  )
}

function SetPassword({ email }: { email: string }) {
  const [password, setPasswordText] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const submit = async (event: FormEvent) => {
    event.preventDefault()
    setBusy(true)
    setError(await setPassword(password))
    setBusy(false)
  }
  return (
    <Sheet title="Set a password" onClose={() => openPanel(null)}>
      <form className="sheet-form" onSubmit={submit}>
        <p className="sheet-hint">You are signed in as {email} from your invite. Choose a password to sign in with next time.</p>
        <input type="email" autoComplete="username" value={email} readOnly hidden />
        <label className="field">
          <span>New password</span>
          <input type="password" autoComplete="new-password" value={password} onChange={(event) => setPasswordText(event.target.value)} minLength={6} required autoFocus />
        </label>
        {error && <p className="sheet-error" role="alert">{error}</p>}
        <button type="submit" className="hud-primary" disabled={busy || password.length < 6}>
          {busy ? 'Saving…' : 'Set password'}
        </button>
        <button type="button" className="sheet-quiet" onClick={() => openPanel(null)}>
          Later
        </button>
      </form>
    </Sheet>
  )
}
