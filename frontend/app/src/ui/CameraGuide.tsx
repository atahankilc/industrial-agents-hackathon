// Camera walk mode: the phone's rear camera fills the screen, the current route leg sits on top as a floor arrow
// and one sentence, and each step is read aloud. "Where am I?" sends a camera frame to the Guide, which reads signs
// and room numbers in it and checks them against the building before answering. The mic takes "next / back /
// repeat" locally and sends anything else to the Guide with the current frame.
// No compass or positioning: the turns are relative to the way you walk (core/directions.py), and you step on.

import { useCallback, useEffect, useRef, useState } from 'react'
import type { RouteLeg } from '../api'
import { silence } from '../voice/tts'
import { hearOnce, say } from '../voice/useVoice'
import type { RouteCardData } from './cards/Cards'
import { legGlyph, legText, TurnIcon } from './TurnIcon'

const NEXT = /\b(next|weiter|nächste|sonraki|ileri|done|okay|ok)\b/i
const BACK = /\b(back|previous|zurück|geri|önceki)\b/i
const REPEAT = /\b(repeat|again|wiederholen|nochmal|tekrar)\b/i

type Props = {
  route: RouteCardData
  lang: string
  /** Ask the Guide (with an optional camera frame as a data URL); resolves with the reply to show and speak. */
  ask: (text: string, photo?: string) => Promise<{ text: string; spoken?: string | null }>
  onClose: () => void
}

function grab(video: HTMLVideoElement | null): string | undefined {
  if (!video || !video.videoWidth) return undefined
  const scale = Math.min(1, 1280 / Math.max(video.videoWidth, video.videoHeight))
  const canvas = document.createElement('canvas')
  canvas.width = Math.round(video.videoWidth * scale)
  canvas.height = Math.round(video.videoHeight * scale)
  canvas.getContext('2d')?.drawImage(video, 0, 0, canvas.width, canvas.height)
  return canvas.toDataURL('image/jpeg', 0.82)
}

export function CameraGuide({ route, lang, ask, onClose }: Props) {
  const video = useRef<HTMLVideoElement>(null)
  const [camera, setCamera] = useState<'starting' | 'on' | 'off'>('starting')
  const [index, setIndex] = useState(0)
  const [muted, setMuted] = useState(false)
  const [busy, setBusy] = useState<'listening' | 'asking' | null>(null)
  const [answer, setAnswer] = useState<string | null>(null)
  const [flash, setFlash] = useState(0)
  const legs = route.legs
  const leg: RouteLeg | undefined = legs[Math.min(index, legs.length - 1)]

  // A new route (the Guide re-routed, e.g. after "the lift is broken") starts from its first step.
  useEffect(() => {
    setIndex(0)
  }, [route.key])

  useEffect(() => {
    let stream: MediaStream | null = null
    let cancelled = false
    const start = async () => {
      if (!navigator.mediaDevices?.getUserMedia) throw new Error('no camera API')
      const media = await navigator.mediaDevices.getUserMedia({
        video: { facingMode: { ideal: 'environment' }, width: { ideal: 1920 } },
        audio: false,
      })
      if (cancelled) return media.getTracks().forEach((track) => track.stop())
      stream = media
      if (video.current) video.current.srcObject = media
      setCamera('on')
    }
    start().catch(() => !cancelled && setCamera('off'))
    return () => {
      cancelled = true
      stream?.getTracks().forEach((track) => track.stop())
      silence()
    }
  }, [])

  const speak = useCallback((text: string) => !muted && say(text, lang), [muted, lang])

  useEffect(() => {
    if (leg) speak(`${index === legs.length - 1 ? '' : `Step ${index + 1}. `}${legText(leg, index === 0)}`)
    // speak on step change only, not when the mute toggle flips
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [index, route.key])

  const go = (delta: number) => {
    setAnswer(null)
    setIndex((current) => Math.max(0, Math.min(legs.length - 1, current + delta)))
  }

  const askGuide = async (text: string) => {
    setBusy('asking')
    setFlash((value) => value + 1)
    try {
      const reply = await ask(text, grab(video.current))
      setAnswer(reply.text)
      speak(reply.spoken ?? reply.text)
    } catch (reason) {
      setAnswer(`Something went wrong: ${String(reason)}`)
    } finally {
      setBusy(null)
    }
  }

  const command = async () => {
    setBusy('listening')
    try {
      const heard = await hearOnce(lang)
      setBusy(null)
      if (!heard) return
      if (REPEAT.test(heard) && leg) speak(legText(leg, index === 0))
      else if (BACK.test(heard)) go(-1)
      else if (NEXT.test(heard) && heard.split(/\s+/).length <= 3) go(1)
      else await askGuide(heard)
    } catch (reason) {
      setBusy(null)
      setAnswer(String(reason instanceof Error ? reason.message : reason))
    }
  }

  useEffect(() => {
    const keys = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose()
      else if (event.key === 'ArrowRight' || event.key === ' ') go(1)
      else if (event.key === 'ArrowLeft') go(-1)
    }
    addEventListener('keydown', keys)
    return () => removeEventListener('keydown', keys)
  })

  if (!leg) return null
  const glyph = legGlyph(leg)
  const last = index === legs.length - 1

  return (
    <div className="camera-guide" role="dialog" aria-modal="true" aria-label={`Walking directions to ${route.to}`}>
      <video ref={video} className={camera === 'on' ? 'on' : ''} autoPlay playsInline muted />
      {camera !== 'on' && (
        <div className="camera-fallback">
          <p className="muted">{camera === 'starting' ? 'Starting camera…' : 'Camera unavailable — directions still work.'}</p>
        </div>
      )}
      <div key={flash} className={flash ? 'shutter' : ''} />

      <header className="cg-top">
        <button type="button" className="cg-round" onClick={onClose} aria-label="Close walking directions">
          <svg viewBox="0 0 16 16" width="16" height="16" aria-hidden="true"><path d="M4 4l8 8M12 4l-8 8" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" /></svg>
        </button>
        <div className="cg-title">
          <span className="cg-kicker">To</span>
          <strong>{route.to}</strong>
        </div>
        <button type="button" className="cg-round" onClick={() => { setMuted((on) => !on); silence() }} aria-label={muted ? 'Unmute directions' : 'Mute directions'} aria-pressed={muted}>
          <svg viewBox="0 0 16 16" width="16" height="16" aria-hidden="true">
            <path d="M2.5 6h2.5L8.5 3v10L5 10H2.5z" fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinejoin="round" />
            {muted ? <path d="M11 6l3.5 4M14.5 6 11 10" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" /> : <path d="M11 5.5a3.5 3.5 0 0 1 0 5M12.8 3.8a6 6 0 0 1 0 8.4" fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" />}
          </svg>
        </button>
      </header>

      {/* The floor arrow: a perspective plane with chevrons flowing in the leg's direction. */}
      <div className={`floor-arrow ${glyph}`} aria-hidden="true">
        <div className="plane">
          {[0, 1, 2, 3].map((i) => <i key={i} style={{ animationDelay: `${i * 0.35}s` }} />)}
        </div>
      </div>

      <section className="cg-card" aria-live="polite">
        <div className="cg-progress" aria-label={`Step ${index + 1} of ${legs.length}`}>
          {legs.map((_, i) => <span key={i} className={i < index ? 'done' : i === index ? 'now' : ''} />)}
        </div>
        <div className="cg-step">
          <span className="cg-glyph"><TurnIcon leg={leg} size={30} /></span>
          <div>
            <p className="cg-text">{legText(leg, index === 0)}</p>
            <p className="cg-meta">
              {last ? 'Destination' : `Step ${index + 1} of ${legs.length - 1}`}
              {leg.floor && <> · {leg.floor}</>}
              {leg.distance_m > 0 && <> · ~{Math.round(leg.distance_m)} m</>}
            </p>
          </div>
        </div>
        {answer && <p className="cg-answer">{answer}</p>}
        <div className="cg-actions">
          <button type="button" onClick={() => go(-1)} disabled={index === 0} aria-label="Previous step">
            <svg viewBox="0 0 16 16" width="16" height="16" aria-hidden="true"><path d="M10 3 5 8l5 5" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" /></svg>
          </button>
          <button type="button" className="cg-ask" onClick={() => void askGuide('Where am I? Use what my camera sees.')} disabled={busy !== null}>
            {busy === 'asking' ? 'Looking…' : 'Where am I?'}
          </button>
          <button type="button" className={`cg-mic ${busy === 'listening' ? 'on' : ''}`} onClick={() => void command()} disabled={busy === 'asking'} aria-label="Say next, back, repeat, or ask a question">
            <svg viewBox="0 0 16 16" width="16" height="16" aria-hidden="true"><path d="M8 10.5a2.5 2.5 0 0 0 2.5-2.5V4a2.5 2.5 0 0 0-5 0v4A2.5 2.5 0 0 0 8 10.5zM3.5 8a4.5 4.5 0 0 0 9 0M8 12.5V15" fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" /></svg>
          </button>
          {last ? (
            <button type="button" className="cg-next" onClick={onClose}>Done</button>
          ) : (
            <button type="button" className="cg-next" onClick={() => go(1)}>Next</button>
          )}
        </div>
      </section>
    </div>
  )
}
