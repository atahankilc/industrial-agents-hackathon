// Access mode over every screen (rendered by Root): the sign-in, set-a-password and Preferences sheets and the quiet
// notice line.
// Renders nothing when the backend has access mode off.

import { useState, type FormEvent } from 'react'
import { openPanel, setPassword, signIn, useAccess } from './auth'
import { PreferencesSheet } from './PreferencesForm'
import { Sheet } from './Sheet'
import './access.css'

export function AccessLayer() {
  const access = useAccess()
  if (!access.mode) return null
  return (
    <div className="access-layer">
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
