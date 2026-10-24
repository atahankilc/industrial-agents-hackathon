// Voice loop on the browser's own speech APIs (free, no keys): SpeechRecognition for the user's words,
// speechSynthesis for the Guide's spoken reply, and a mic analyser so the orb can follow the user's voice.
// It is one adapter: an ElevenLabs session (docs/research/elevenlabs.md) can replace it behind the same shape.

import { useCallback, useEffect, useRef, useState } from 'react'

export type VoiceState = 'off' | 'listening' | 'thinking' | 'speaking'

export const LANGUAGES = [
  { code: 'en-US', label: 'EN' },
  { code: 'de-DE', label: 'DE' },
  { code: 'tr-TR', label: 'TR' },
] as const

// Minimal typing for the (still prefixed in Chrome/Safari) Web Speech recognition API.
type Recognition = {
  lang: string
  interimResults: boolean
  continuous: boolean
  start: () => void
  stop: () => void
  abort: () => void
  onresult: ((event: { resultIndex: number; results: ArrayLike<{ isFinal: boolean; 0: { transcript: string } }> }) => void) | null
  onerror: ((event: { error: string }) => void) | null
  onend: (() => void) | null
  onaudiostart: (() => void) | null
}
type RecognitionCtor = new () => Recognition

function recognitionCtor(): RecognitionCtor | null {
  const scope = window as unknown as { SpeechRecognition?: RecognitionCtor; webkitSpeechRecognition?: RecognitionCtor }
  return scope.SpeechRecognition ?? scope.webkitSpeechRecognition ?? null
}

export const voiceSupported = () => recognitionCtor() !== null && 'speechSynthesis' in window

function initialLanguage() {
  const preferred = navigator.language?.slice(0, 2)
  return LANGUAGES.find((language) => language.code.startsWith(preferred))?.code ?? 'en-US'
}

// Chrome stops long utterances after ~15 s: speak sentence by sentence.
function sentences(text: string) {
  return text.match(/[^.!?]+[.!?]+["')\]]*\s*|[^.!?]+$/g)?.map((part) => part.trim()).filter(Boolean) ?? []
}

function bestVoice(lang: string) {
  const voices = speechSynthesis.getVoices().filter((voice) => voice.lang.replace('_', '-').startsWith(lang.slice(0, 2)))
  const rank = (voice: SpeechSynthesisVoice) =>
    (/natural|neural|premium|enhanced/i.test(voice.name) ? 4 : 0) + (/google/i.test(voice.name) ? 2 : 0) +
    (voice.lang.replace('_', '-') === lang ? 1 : 0) + (voice.localService ? 0 : 1)
  return voices.sort((a, b) => rank(b) - rank(a))[0] ?? null
}

/** Speak once, outside the conversation loop (camera walk mode reads its steps with this). */
export function say(text: string, lang: string, onEnd?: () => void) {
  if (!('speechSynthesis' in window)) return
  speechSynthesis.cancel()
  const parts = sentences(text)
  const voice = bestVoice(lang)
  parts.forEach((part, index) => {
    const utterance = new SpeechSynthesisUtterance(part)
    utterance.lang = lang
    if (voice) utterance.voice = voice
    utterance.rate = 1.04
    if (index === parts.length - 1 && onEnd) utterance.onend = onEnd
    speechSynthesis.speak(utterance)
  })
}

/** One utterance, for short voice commands; resolves with the transcript ('' when nothing was heard). */
export function hearOnce(lang: string): Promise<string> {
  const Ctor = recognitionCtor()
  if (!Ctor) return Promise.reject(new Error('Voice input needs Chrome, Edge or Safari.'))
  return new Promise((resolve, reject) => {
    const recognizer = new Ctor()
    recognizer.lang = lang
    recognizer.interimResults = false
    recognizer.continuous = false
    let heard = ''
    recognizer.onresult = (event) => {
      for (let i = event.resultIndex; i < event.results.length; i++) heard += event.results[i][0].transcript
    }
    recognizer.onerror = (event) => {
      if (event.error !== 'no-speech' && event.error !== 'aborted') reject(new Error(`Voice input failed (${event.error}).`))
    }
    recognizer.onend = () => resolve(heard.trim())
    speechSynthesis.cancel()
    recognizer.start()
  })
}

// Web Speech API error codes → what the person can do about it.
const RECOGNITION_ERRORS: Record<string, string> = {
  'not-allowed': 'Microphone access is blocked. Allow it in the address bar, then tap the orb.',
  'service-not-allowed': 'This browser does not allow speech recognition here. Try Chrome, Edge or Safari.',
  'no-speech': "I didn't hear anything. Tap the orb and speak a little louder.",
  'audio-capture': 'No microphone found. Plug one in or pick an input device, then tap the orb.',
  network: "This browser's speech service is unreachable (Brave and some Chromium builds have none). Try Chrome, Edge or Safari.",
  'language-not-supported': 'This language is not supported for voice here. Pick EN.',
}

type Options = {
  /** A finished utterance. Return true when it was sent (the loop then waits in "thinking"). */
  onUtterance: (text: string) => boolean
}

export function useVoice({ onUtterance }: Options) {
  const [state, setState] = useState<VoiceState>('off')
  const [interim, setInterim] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [lang, setLang] = useState<string>(initialLanguage)
  const [handsFree, setHandsFree] = useState(true)
  /** 0…1, read every animation frame by the orb (a ref, not state: it changes 60 times a second). */
  const level = useRef(0)
  const peakLevel = useRef(0) // loudest mic level of the current listen, to tell "silent mic" from "no words"
  // The level meter opens its own mic stream. If that ever costs recognition the device ("audio-capture"), retry
  // once without it for the rest of the session: hearing the words matters more than the orb's wobble.
  const meterBlocked = useRef(false)
  const retried = useRef(false)
  const recognition = useRef<Recognition | null>(null)
  const stateRef = useRef<VoiceState>('off')
  const mic = useRef<{ stream: MediaStream; context: AudioContext; frame: number } | null>(null)
  const utter = useRef(onUtterance)
  useEffect(() => {
    utter.current = onUtterance
  }, [onUtterance])

  const set = useCallback((next: VoiceState) => {
    stateRef.current = next
    setState(next)
  }, [])

  // ---------- mic level (only while listening) ----------

  const stopMeter = useCallback(() => {
    if (!mic.current) return
    cancelAnimationFrame(mic.current.frame)
    mic.current.stream.getTracks().forEach((track) => track.stop())
    void mic.current.context.close()
    mic.current = null
  }, [])

  const startMeter = useCallback(async () => {
    if (mic.current) return
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true } })
      const context = new AudioContext()
      const analyser = context.createAnalyser()
      analyser.fftSize = 512
      context.createMediaStreamSource(stream).connect(analyser)
      const samples = new Uint8Array(analyser.fftSize)
      const tick = () => {
        analyser.getByteTimeDomainData(samples)
        let sum = 0
        for (const sample of samples) sum += ((sample - 128) / 128) ** 2
        const rms = Math.sqrt(sum / samples.length)
        level.current += (Math.min(1, rms * 5) - level.current) * 0.3
        peakLevel.current = Math.max(peakLevel.current, level.current)
        if (mic.current) mic.current.frame = requestAnimationFrame(tick)
      }
      mic.current = { stream, context, frame: requestAnimationFrame(tick) }
    } catch {
      // the orb still works without a level; recognition reports a real permission problem itself
    }
  }, [])

  // ---------- listening ----------

  const listen = useCallback(() => {
    const Ctor = recognitionCtor()
    if (!Ctor) {
      setError('Voice input needs Chrome, Edge or Safari.')
      return
    }
    speechSynthesis.cancel()
    recognition.current?.abort()
    const recognizer = new Ctor()
    recognizer.lang = lang
    recognizer.interimResults = true
    recognizer.continuous = false
    let finalText = ''
    recognizer.onresult = (event) => {
      let heard = ''
      for (let i = event.resultIndex; i < event.results.length; i++) {
        const result = event.results[i]
        if (result.isFinal) finalText += result[0].transcript
        else heard += result[0].transcript
      }
      setInterim((finalText + heard).trim())
      if (!mic.current) level.current = 0.45 + Math.random() * 0.4 // no meter: pulse on each recognised word
    }
    let failed = false
    let retry = false
    recognizer.onaudiostart = () => {
      if (!meterBlocked.current) void startMeter() // after recognition holds the mic, never before
    }
    recognizer.onerror = (event) => {
      console.info('[voice] recognition error:', event.error)
      if (event.error === 'aborted') return
      if (event.error === 'audio-capture' && !meterBlocked.current && !retried.current) {
        meterBlocked.current = true
        retried.current = true
        failed = true
        retry = true
        return
      }
      failed = true
      setError(RECOGNITION_ERRORS[event.error] ?? `Voice input failed (${event.error}). Tap the orb to try again.`)
    }
    recognizer.onend = () => {
      if (recognition.current !== recognizer) return
      recognition.current = null
      const silentMic = mic.current !== null && peakLevel.current < 0.04 // the meter ran and heard nothing
      stopMeter()
      const text = finalText.trim()
      setInterim('')
      if (stateRef.current !== 'listening') return
      if (retry) {
        console.info('[voice] retrying without the level meter')
        setTimeout(() => listenRef.current?.(), 150)
        return
      }
      if (text && utter.current(text)) {
        set('thinking')
        return
      }
      set('off')
      // Never end silently: say why nothing was sent.
      if (!failed && !text) {
        setError(silentMic
          ? "I couldn't hear your microphone. Check the input device (macOS: System Settings → Sound → Input), then tap the orb."
          : "I didn't catch that. Tap the orb and try again.")
      }
    }
    recognition.current = recognizer
    peakLevel.current = 0
    setError(null)
    setInterim('')
    set('listening')
    try {
      recognizer.start()
    } catch {
      set('off')
    }
  }, [lang, set, startMeter, stopMeter])

  const listenRef = useRef<() => void>(null)
  useEffect(() => {
    listenRef.current = listen
  }, [listen])

  /** Stop listening now and send what was heard so far. */
  const finish = useCallback(() => recognition.current?.stop(), [])

  // ---------- speaking ----------

  const speak = useCallback(
    (text: string) => {
      speechSynthesis.cancel()
      const parts = sentences(text)
      if (!parts.length) {
        set('off')
        return
      }
      const voice = bestVoice(lang)
      set('speaking')
      parts.forEach((part, index) => {
        const utterance = new SpeechSynthesisUtterance(part)
        utterance.lang = lang
        if (voice) utterance.voice = voice
        utterance.rate = 1.04
        utterance.onboundary = () => { level.current = 0.55 + Math.random() * 0.45 }
        utterance.onend = () => {
          if (index < parts.length - 1 || stateRef.current !== 'speaking') return
          level.current = 0
          if (handsFree) listen()
          else set('off')
        }
        speechSynthesis.speak(utterance)
      })
    },
    [lang, handsFree, listen, set],
  )

  // Speech (and listening without the meter) has no level signal of its own: let the word pulses decay.
  useEffect(() => {
    if (state !== 'speaking' && state !== 'listening') return
    let frame = 0
    const decay = () => {
      if (!mic.current) level.current *= 0.9
      frame = requestAnimationFrame(decay)
    }
    frame = requestAnimationFrame(decay)
    return () => cancelAnimationFrame(frame)
  }, [state])

  const stop = useCallback(() => {
    set('off')
    recognition.current?.abort()
    recognition.current = null
    speechSynthesis.cancel()
    stopMeter()
    setInterim('')
    level.current = 0
  }, [set, stopMeter])

  /** The sent utterance failed or got no reply to read out. */
  const idle = useCallback(() => {
    if (stateRef.current === 'thinking') set('off')
  }, [set])

  useEffect(() => {
    speechSynthesis.getVoices() // voices load lazily in Chrome
    return () => {
      recognition.current?.abort()
      speechSynthesis.cancel()
      stopMeter()
    }
  }, [stopMeter])

  return { state, interim, error, level, lang, setLang, handsFree, setHandsFree, listen, finish, speak, stop, idle }
}

export type Voice = ReturnType<typeof useVoice>
