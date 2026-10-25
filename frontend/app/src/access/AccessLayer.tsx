// Access mode over every screen (rendered by Root): the sign-in, set-a-password and Preferences sheets, the quiet
// notice line, and on the landing (map / list, no building open) an account button top right — the building screen
// has the same items in its "…" menu.
// Renders nothing when the backend has access mode off.

import { KeyRound, LogIn, LogOut, SlidersHorizontal, UserRound } from 'lucide-react'
import { useState, type FormEvent } from 'react'
import { openPanel, setPassword, signIn, signOut, useAccess } from './auth'
import { PreferencesSheet } from './PreferencesForm'
import { Sheet } from './Sheet'
import './access.css'

export function AccessLayer({ landing = false }: { landing?: boolean }) {
  const access = useAccess()
  if (!access.mode) return null
  return (
    <div className="access-layer">
      {landing && <Account />}
      {access.panel === 'signin' && <SignIn />}
      {access.panel === 'password' && access.email && <SetPassword email={access.email} />}
      {access.panel === 'preferences' && <PreferencesSheet />}
      {access.notice && (
        <p className="access-notice" role="status">
          {access.notice}
        </p>
      )}
    </div>
  )
}

/** The landing's account button: Sign in, or the signed-in email with Preferences, Set a password and Sign out. */
function Account() {
  const access = useAccess()
  const [open, setOpen] = useState(false)
  const pick = (action: () => void) => () => {
    setOpen(false)
    action()
  }
  if (!access.email) {
    return (
      <button type="button" className="account-button" onClick={() => openPanel('signin')}>
        <LogIn size={16} strokeWidth={2} />
        Sign in
      </button>
    )
  }
  return (
    <div className="account-corner">
      <button type="button" className="account-button" aria-haspopup="menu" aria-expanded={open} onClick={() => setOpen((value) => !value)}>
        <UserRound size={16} strokeWidth={2} />
        <span className="account-email">{access.email}</span>
        {access.admin && <em className="account-role">admin</em>}
      </button>
      {open && (
        <div className="account-menu" role="menu">
          <button type="button" role="menuitem" onClick={pick(() => openPanel('preferences'))}>
            <SlidersHorizontal size={16} strokeWidth={2} />
            Preferences
          </button>
          {access.needsPassword && (
            <button type="button" role="menuitem" onClick={pick(() => openPanel('password'))}>
              <KeyRound size={16} strokeWidth={2} />
              Set a password
            </button>
          )}
          <button type="button" role="menuitem" onClick={pick(() => void signOut())}>
            <LogOut size={16} strokeWidth={2} />
            Sign out
          </button>
          {access.admin && <p className="account-hint">Access, members and objects: open a building → ⋯ → Building settings.</p>}
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
