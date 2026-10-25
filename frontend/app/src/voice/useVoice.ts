// Voice loop: speech recognition for the user's words (voice/scribe.ts: ElevenLabs Scribe Realtime with the building's
// keyterms, else the browser's SpeechRecognition), the Guide's voice for its reply (voice/tts.ts: ElevenLabs through
// the backend, else the browser's speechSynthesis), and a mic analyser so the orb can follow the user's voice.

import { useCallback, useEffect, useRef, useState } from 'react'
import { interruption, userPart } from './bargeIn'
import { acquireMicrophone, capturing, iOS, releaseMicrophone } from './mic'
import { ScribeRecognition, scribeReady } from './scribe'
import { openSpeech, silence, speakAloud, unlockAudio, type Speech } from './tts'

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

function browserRecognition(): RecognitionCtor | null {
  const scope = window as unknown as { SpeechRecognition?: RecognitionCtor; webkitSpeechRecognition?: RecognitionCtor }
  return scope.SpeechRecognition ?? scope.webkitSpeechRecognition ?? null
}

/** Scribe when the backend offers it (and it hasn't just failed), else the browser's recognition. */
function recognitionCtor(): RecognitionCtor | null {
  return scribeReady() ? ScribeRecognition : browserRecognition()
}

export const voiceSupported = () => recognitionCtor() !== null && 'speechSynthesis' in window

function initialLanguage() {
  const preferred = navigator.language?.slice(0, 2)
  return LANGUAGES.find((language) => language.code.startsWith(preferred))?.code ?? 'en-US'
}

/** Speak once, outside the conversation loop (camera walk mode reads its steps with this). */
export function say(text: string, lang: string, onEnd?: () => void) {
  speakAloud(text, lang, { onEnd })
}

/** One utterance, for short voice commands; resolves with the transcript ('' when nothing was heard). */
export function hearOnce(lang: string): Promise<string> {
  const Ctor = browserRecognition() // relies on the browser ending by itself after one utterance; Scribe never does
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
    silence()
    unlockAudio()
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
  'scribe-unavailable': 'ElevenLabs speech recognition is unreachable right now. Tap the orb to try again.',
}

const END_PAUSE_MS = 1700 // this long without new words, once the user has spoken, ends the utterance
const MID_PAUSE_MS = 2800 // … when the last word leaves the sentence open ("and", "to the", "ve", "um")
const NO_WORDS_MS = 8000 // nothing heard at all after a tap: stop listening
const AUTO_NO_WORDS_MS = 6000 // … after listening started by itself: the conversation is over
const CARRY_PAUSE_MS = 2500 // after talking over the Guide: the words so far are sent unless more follow
const BARGE_GRACE_MS = 1500 // talking over the Guide counts only after its voice has played this long
const BARGE_HOLD_MS = 700 // … and only once the user's words have kept coming this long (one burst is echo or noise)
// Voice on the level meter (0…1, rms × 5): room noise after noise suppression stays well below; a voice is above.
// Words recognised while the meter never heard a voice are noise the recogniser made words of ("thank you").
const VOICE_LEVEL = 0.12
const VOICE_FRAMES = 8 // animation frames above VOICE_LEVEL (about 130 ms) before the listen counts as voiced

// Words a sentence doesn't end on: after one of these the user is mid-thought, so the pause may run longer.
const OPEN_ENDINGS = new Set([
  'and', 'or', 'but', 'to', 'the', 'a', 'an', 'of', 'from', 'in', 'on', 'at', 'with', 'for', 'is', 'um', 'uh', 'er', 'so',
  'und', 'oder', 'aber', 'zum', 'zur', 'der', 'die', 'das', 'den', 'dem', 'ein', 'eine', 'von', 'mit', 'nach', 'im', 'äh', 'ähm',
  've', 'veya', 'ile', 'ama', 'için', 'bir', 'en', 'şey', 'eee', 'ıı', 'hmm', 'yani', 'mı', 'mi', 'mu', 'mü', 'da', 'de',
])
const pauseAfter = (text: string) =>
  OPEN_ENDINGS.has(text.toLowerCase().match(/[\p{L}]+(?=[^\p{L}]*$)/u)?.[0] ?? '') ? MID_PAUSE_MS : END_PAUSE_MS

type SpeakOptions = { conversation?: boolean; waitMs?: number; listenAfter?: () => boolean }

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
  /** the Guide answers aloud; off, replies are text only (the user's choice, remembered on this device) */
  const [speaks, setSpeaksState] = useState(() => readSpeaks())
  const setSpeaks = useCallback((on: boolean) => {
    setSpeaksState(on)
    writeSpeaks(on)
    if (!on) silence()
  }, [])
  /** push to talk (the user's choice, remembered; off by default): listen only while the ball is held, never by
   * itself after a reply and no talking over it; off, a tap listens until silence and the conversation goes on
   * hands-free */
  const [holdToTalk, setHoldState] = useState(() => readFlag(HOLD_KEY, false))
  const setHoldToTalk = useCallback((on: boolean) => {
    setHoldState(on)
    writeFlag(HOLD_KEY, on)
  }, [])
  /** listening and the microphone is really capturing (state 'listening' comes first, while the mic opens) */
  const [hearing, setHearing] = useState(false)
  /** 0…1, read every animation frame by the orb (a ref, not state: it changes 60 times a second). */
  const level = useRef(0)
  const peakLevel = useRef(0) // loudest mic level of the current listen, to tell "silent mic" from "no words"
  const voiced = useRef(0) // frames of the current listen the meter heard a voice in (VOICE_LEVEL)
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

  // barge-in (see `watch`): the recognizer that runs while the Guide speaks, and what the Guide is saying
  const watcher = useRef<Recognition | null>(null)
  const said = useRef('')
  const spokeAt = useRef(0) // when the reply's first sound played
  const [bargeIn, setBargeIn] = useState(false)

  const unwatch = useCallback(() => {
    const recognizer = watcher.current
    watcher.current = null
    recognizer?.abort()
    setBargeIn(false)
  }, [])

  // ---------- mic level (only while listening) ----------

  const stopMeter = useCallback(() => {
    if (!mic.current) return
    cancelAnimationFrame(mic.current.frame)
    void mic.current.context.close()
    mic.current = null
    releaseMicrophone()
  }, [])

  const startMeter = useCallback(async (scribe: boolean) => {
    // iOS captures from one stream at a time: beside the browser's own recognition a meter would take its mic away
    if (mic.current || (iOS && !scribe)) return
    let stream: MediaStream
    try {
      stream = await acquireMicrophone() // Scribe's own stream, never a second capture
    } catch {
      return // the orb still works without a level; recognition reports a real permission problem itself
    }
    if (mic.current || stateRef.current !== 'listening') return releaseMicrophone() // the listen ended meanwhile
    try {
      const context = new AudioContext()
      // started without a tap (listening again after a reply) iOS may keep it suspended: a meter that reads nothing
      // would drop every word, so then there is none
      if (context.state !== 'running') await Promise.race([context.resume(), new Promise((resolve) => setTimeout(resolve, 300))])
      if (context.state !== 'running' || mic.current || stateRef.current !== 'listening') {
        void context.close()
        return releaseMicrophone()
      }
      const analyser = context.createAnalyser()
      analyser.fftSize = 512
      context.createMediaStreamSource(stream).connect(analyser)
      const samples = new Uint8Array(analyser.fftSize)
      const tick = () => {
        // the stream went quiet under us (muted by another capture, an interruption): no meter rather than one that
        // reads silence, which would drop every word as heard without a voice
        if (!capturing(stream) || context.state !== 'running') return stopMeter()
        analyser.getByteTimeDomainData(samples)
        let sum = 0
        for (const sample of samples) sum += ((sample - 128) / 128) ** 2
        const rms = Math.sqrt(sum / samples.length)
        level.current += (Math.min(1, rms * 5) - level.current) * 0.3
        peakLevel.current = Math.max(peakLevel.current, level.current)
        if (level.current > VOICE_LEVEL) voiced.current += 1
        if (mic.current) mic.current.frame = requestAnimationFrame(tick)
      }
      mic.current = { stream, context, frame: requestAnimationFrame(tick) }
    } catch {
      releaseMicrophone()
    }
  }, [stopMeter])

  // ---------- listening ----------

  /** Listen for one utterance. It ends after END_PAUSE_MS without new words (a short pause mid-sentence is fine), on
   * `finish`, or with nothing heard. `auto`: started by itself (after a reply, or by talking over the Guide), so
   * hearing nothing just ends the conversation quietly. `carry`: words already heard while the Guide spoke.
   * `until`: keep listening (again and again) until this time when nothing is heard — the step-by-step guide,
   * waiting for "I'm there" while the user walks. `hold`: push to talk — no timers at all, it ends on `finish`
   * (the ball let go). */
  const listenWith = useCallback(({ auto = false, carry = '', until = 0, hold = false }: { auto?: boolean; carry?: string; until?: number; hold?: boolean } = {}) => {
    const Ctor = recognitionCtor()
    if (!Ctor) {
      setError('Voice input needs Chrome, Edge or Safari.')
      return
    }
    unwatch()
    silence()
    unlockAudio() // listening starts from a tap: the moment to unlock the Guide's voice
    recognition.current?.abort()
    const recognizer = new Ctor()
    recognizer.lang = lang
    recognizer.interimResults = true
    recognizer.continuous = true // our own pause timer decides when the utterance is over
    let finalText = carry ? carry + ' ' : ''
    // words carried over may already be the whole question: send them soon unless more follow
    const later = (ms: number) => (hold ? undefined : setTimeout(() => recognizer.stop(), ms))
    let timer = later(carry ? CARRY_PAUSE_MS : auto ? AUTO_NO_WORDS_MS : NO_WORDS_MS)
    recognizer.onresult = (event) => {
      let heard = ''
      for (let i = event.resultIndex; i < event.results.length; i++) {
        const result = event.results[i]
        if (result.isFinal) finalText += result[0].transcript
        else heard += result[0].transcript
      }
      // the meter hears no voice yet: room noise made into words, which must neither show nor keep the listen open
      if (mic.current && voiced.current < VOICE_FRAMES && !carry) return
      const sofar = (finalText + heard).trim()
      setInterim(sofar)
      setHearing(true)
      if (!mic.current) level.current = 0.45 + Math.random() * 0.4 // no meter: pulse on each recognised word
      clearTimeout(timer)
      timer = later(pauseAfter(sofar)) // stop() still delivers the words in flight
    }
    let failed = false
    let retry = false
    recognizer.onaudiostart = () => {
      setHearing(true)
      if (!meterBlocked.current) void startMeter(Ctor === ScribeRecognition) // after recognition holds the mic, never before
    }
    recognizer.onerror = (event) => {
      console.info('[voice] recognition error:', event.error)
      if (event.error === 'aborted' || (auto && event.error === 'no-speech')) return
      if (event.error === 'audio-capture' && !meterBlocked.current && !retried.current) {
        meterBlocked.current = true
        retried.current = true
        failed = true
        retry = true
        return
      }
      if (event.error === 'scribe-unavailable' && browserRecognition()) {
        failed = true
        retry = true // Scribe now cools off: the retry listens with the browser's recognition
        return
      }
      failed = true
      setError(RECOGNITION_ERRORS[event.error] ?? `Voice input failed (${event.error}). Tap the orb to try again.`)
    }
    recognizer.onend = () => {
      clearTimeout(timer)
      if (recognition.current !== recognizer) return
      recognition.current = null
      const silentMic = mic.current !== null && peakLevel.current < 0.04 // the meter ran and heard nothing
      const unvoiced = mic.current !== null && voiced.current < VOICE_FRAMES && !carry // … or heard no voice
      stopMeter()
      const text = unvoiced ? '' : finalText.trim()
      if (unvoiced && finalText.trim()) console.info('[voice] dropped words heard without a voice:', finalText.trim())
      setInterim('')
      if (stateRef.current !== 'listening') return
      if (retry) {
        console.info('[voice] retrying (without the level meter, or with browser recognition)')
        setTimeout(() => listenRef.current?.({ auto, carry, until, hold }), 150)
        return
      }
      if (!text && !failed && Date.now() < until) {
        listenRef.current?.({ auto: true, until }) // still waiting for the user to get there
        return
      }
      if (text && utter.current(text)) {
        set('thinking')
        return
      }
      set('off')
      // Never end silently: say why nothing was sent (unless the conversation simply went quiet).
      if (!failed && !text && !auto && !hold) {
        setError(silentMic
          ? "I couldn't hear your microphone. Check the input device (macOS: System Settings → Sound → Input), then tap the orb."
          : "I didn't catch that. Tap the orb and try again.")
      }
    }
    recognition.current = recognizer
    peakLevel.current = 0
    voiced.current = 0
    setError(null)
    setInterim('')
    setHearing(false)
    set('listening')
    try {
      recognizer.start()
    } catch {
      clearTimeout(timer)
      set('off')
    }
  }, [lang, set, startMeter, stopMeter, unwatch])

  const listenRef = useRef<typeof listenWith>(null)
  useEffect(() => {
    listenRef.current = listenWith
  }, [listenWith])

  /** Listen for one utterance (a tap on the orb). */
  const listen = useCallback(() => listenWith(), [listenWith])

  /** Listen while the ball is held (push to talk); `finish` on release sends. */
  const hold = useCallback(() => listenWith({ hold: true }), [listenWith])

  /** Stop listening now and send what was heard so far. */
  const finish = useCallback(() => recognition.current?.stop(), [])

  // ---------- barge-in: listening while the Guide answers ----------

  /** While a reply is spoken, recognition runs too: words the Guide isn't saying (voice/bargeIn.ts) cut it off —
   * a stop word just stops it, anything else becomes the next question. */
  const watch = useCallback(() => {
    const Ctor = recognitionCtor()
    if (!Ctor || watcher.current || recognition.current) return
    const recognizer = new Ctor()
    recognizer.lang = lang
    recognizer.interimResults = true
    recognizer.continuous = true
    let talkSince = 0 // "talk" must be heard on results spanning BARGE_HOLD_MS: a stray burst is echo or noise
    recognizer.onresult = (event) => {
      const now = Date.now()
      if (now - spokeAt.current < BARGE_GRACE_MS) return // the echo is loudest as the voice starts
      const results = Array.from(event.results, (result) => result[0].transcript)
      const kind = interruption(userPart(results, said.current), said.current)
      if (kind === 'talk') {
        talkSince ||= now
        if (now - talkSince < BARGE_HOLD_MS) return
      } else talkSince = 0
      if (!kind) return
      unwatch()
      if (kind === 'stop') {
        stopRef.current?.()
        return
      }
      listenRef.current?.({ auto: true, carry: userPart(results, said.current) })
    }
    recognizer.onerror = (event) => console.info('[voice] barge-in recognition:', event.error)
    recognizer.onend = () => {
      if (watcher.current !== recognizer) return
      watcher.current = null
      setBargeIn(false)
      if (stateRef.current === 'speaking') setTimeout(() => watchRef.current?.(), 250) // the browser ended it early
    }
    watcher.current = recognizer
    setBargeIn(true)
    try {
      recognizer.start()
    } catch {
      watcher.current = null
      setBargeIn(false)
    }
  }, [lang, unwatch])

  const watchRef = useRef<typeof watch>(null)
  useEffect(() => {
    watchRef.current = watch
  }, [watch])

  // ---------- speaking ----------

  /** Speak a reply whose sentences are still arriving: `add` each, then `end`. The state stays as it is ("thinking"
   * after a question) until the first sound plays. `conversation`: the reply to a spoken question — from its first
   * sound the user can talk over it, and when it ends the Guide listens again (with `handsFree`); `waitMs`: that
   * listening keeps waiting this long for an answer (a step of the guide, while the user walks); `listenAfter`: asked
   * once the speech ends — listen for an answer anyway (a tapped question whose reply asks something back). */
  const stream = useCallback(
    ({ conversation = false, waitMs = 0, listenAfter }: SpeakOptions = {}): Speech => {
      // replies are text only: nothing is spoken, and the loop goes back to rest once the reply is in
      if (!speaks) return { add: () => {}, end: () => stateRef.current === 'thinking' && set('off') }
      // push to talk: the user holds the ball to answer, so nothing listens by itself
      const free = handsFree && !holdToTalk
      const talk = conversation && free
      said.current = ''
      unwatch()
      const speech = openSpeech(lang, {
        onStart: () => {
          spokeAt.current = Date.now()
          set('speaking')
          // no talking over the reply on iOS: listening keeps the mic open, and iOS then plays the voice at call volume
          if (talk && !iOS) watch()
        },
        onLevel: (value) => { level.current = value },
        onEnd: () => {
          unwatch()
          level.current = 0
          if (stateRef.current === 'thinking') set('off') // nothing was said
          if (stateRef.current !== 'speaking') return
          if (!talk && !(free && listenAfter?.())) return set('off')
          // a moment for the room to go quiet, so the mic doesn't catch the Guide's last word
          setTimeout(() => stateRef.current === 'speaking' && listenRef.current?.({ auto: true, until: waitMs ? Date.now() + waitMs : 0 }), 200)
        },
      })
      return {
        add: (text) => {
          said.current += ' ' + text
          speech.add(text)
        },
        end: () => speech.end(),
      }
    },
    [lang, handsFree, holdToTalk, speaks, set, unwatch, watch],
  )

  const speak = useCallback(
    (text: string, options?: SpeakOptions) => {
      const speech = stream(options)
      speech.add(text)
      speech.end()
    },
    [stream],
  )

  // Listening without the meter has no level signal of its own: let the word pulses decay (speech brings its own).
  useEffect(() => {
    if (state !== 'listening') return
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
    unwatch()
    recognition.current?.abort()
    recognition.current = null
    silence()
    stopMeter()
    setInterim('')
    level.current = 0
  }, [set, stopMeter, unwatch])

  const stopRef = useRef<typeof stop>(null)
  useEffect(() => {
    stopRef.current = stop
  }, [stop])

  /** The sent utterance failed or got no reply to read out. */
  const idle = useCallback(() => {
    if (stateRef.current === 'thinking') set('off')
  }, [set])

  useEffect(() => {
    speechSynthesis.getVoices() // voices load lazily in Chrome
    return () => {
      recognition.current?.abort()
      watcher.current?.abort()
      silence()
      stopMeter()
    }
  }, [stopMeter])

  return {
    state, interim, error, level, lang, setLang, handsFree, setHandsFree, speaks, setSpeaks, holdToTalk, setHoldToTalk,
    bargeIn, hearing, listen, hold, finish, speak, stream, stop, idle,
  }
}

export type Voice = ReturnType<typeof useVoice>

const SPEAKS_KEY = 'ttyb-guide-speaks'
const HOLD_KEY = 'ttyb-guide-hold'
const readSpeaks = () => readFlag(SPEAKS_KEY, true)
const writeSpeaks = (on: boolean) => writeFlag(SPEAKS_KEY, on)
function readFlag(key: string, fallback: boolean) {
  try {
    const value = localStorage.getItem(key)
    return value === null ? fallback : value === 'true'
  } catch {
    return fallback
  }
}
function writeFlag(key: string, on: boolean) {
  try {
    localStorage.setItem(key, String(on))
  } catch {
    // storage unavailable: the choice just isn't remembered
  }
}
