// Light / dark / system theme. The choice is a per-viewer convenience in localStorage (guarded: storage can
// throw in private windows); the resolved theme is mirrored on <html data-theme> for the CSS tokens. With no stored
// choice it is dark: the building screen's HUD is designed dark first.

import { useEffect, useState } from 'react'

export type ThemeMode = 'system' | 'light' | 'dark'
const KEY = 'ttyb-theme'
const ORDER: ThemeMode[] = ['system', 'light', 'dark']
// every mounted useTheme follows one choice (the map stays mounted under the building screen)
const listeners = new Set<(mode: ThemeMode) => void>()

function stored(): ThemeMode {
  try {
    const value = localStorage.getItem(KEY)
    return value === 'light' || value === 'system' ? value : 'dark'
  } catch {
    return 'dark'
  }
}

export function useTheme() {
  const [mode, setMode] = useState<ThemeMode>(stored)
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
    try {
      localStorage.setItem(KEY, mode)
    } catch {
      // storage unavailable: the choice just doesn't persist
    }
  }, [dark, mode])

  const cycle = () => {
    const next = ORDER[(ORDER.indexOf(mode) + 1) % ORDER.length]
    listeners.forEach((set) => set(next))
  }
  return { mode, dark, cycle }
}
