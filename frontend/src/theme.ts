// Light / dark / system theme. Every load starts dark, whatever the OS colour scheme or an earlier choice: the
// building screen's HUD is designed dark first. The settings menu still cycles it for the session; the resolved
// theme is mirrored on <html data-theme> for the CSS tokens (index.html starts it dark, so the first paint is too).

import { useEffect, useState } from 'react'

export type ThemeMode = 'system' | 'light' | 'dark'
const ORDER: ThemeMode[] = ['system', 'light', 'dark']
// every mounted useTheme follows one choice (the map stays mounted under the building screen)
const listeners = new Set<(mode: ThemeMode) => void>()
let current: ThemeMode = 'dark'

export function useTheme() {
  const [mode, setMode] = useState<ThemeMode>(() => current)
  useEffect(() => {
    listeners.add(setMode)
    return () => void listeners.delete(setMode)
  }, [])
  const [systemDark, setSystemDark] = useState(() => matchMedia('(prefers-color-scheme: dark)').matches)

  useEffect(() => {
    const query = matchMedia('(prefers-color-scheme: dark)')
    const onChange = (event: MediaQueryListEvent) => setSystemDark(event.matches)
    query.addEventListener('change', onChange)
    return () => query.removeEventListener('change', onChange)
  }, [])

  const dark = mode === 'dark' || (mode === 'system' && systemDark)
  useEffect(() => {
    document.documentElement.dataset.theme = dark ? 'dark' : 'light'
  }, [dark])

  const cycle = () => {
    const next = ORDER[(ORDER.indexOf(mode) + 1) % ORDER.length]
    current = next
    listeners.forEach((set) => set(next))
  }
  return { mode, dark, cycle }
}
