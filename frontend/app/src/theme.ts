// Light / dark / system theme. The choice is a per-viewer convenience in localStorage (guarded: storage can
// throw in private windows); the resolved theme is mirrored on <html data-theme> for the CSS tokens.

import { useEffect, useState } from 'react'

export type ThemeMode = 'system' | 'light' | 'dark'
const KEY = 'ttyb-theme'
const ORDER: ThemeMode[] = ['system', 'light', 'dark']

function stored(): ThemeMode {
  try {
    const value = localStorage.getItem(KEY)
    return value === 'light' || value === 'dark' ? value : 'system'
  } catch {
    return 'system'
  }
}

export function useTheme() {
  const [mode, setMode] = useState<ThemeMode>(stored)
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

  const cycle = () => setMode((current) => ORDER[(ORDER.indexOf(current) + 1) % ORDER.length])
  return { mode, dark, cycle }
}
