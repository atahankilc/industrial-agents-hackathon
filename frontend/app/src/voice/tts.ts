// The Guide's voice: ElevenLabs through the backend (POST /tts, backend/tts.py) when it has a key, otherwise — and
// whenever a request fails — the browser's own speechSynthesis. One voice for the whole app, like speechSynthesis:
// speaking again (or `silence()`) stops whatever is still speaking. A reply can be spoken while it is still being
// written: `openSpeech` takes sentences as they arrive (the Guide's `say` lines, api.ts chatStream).

import { api } from '../api'

type Handlers = {
  /** the first sound plays (ElevenLabs audio takes a moment to arrive) */
  onStart?: () => void
  /** everything was spoken (`end()` was called); not called when the speech was cut off */
  onEnd?: () => void
  /** 0…1 every animation frame while speaking, for the orb */
  onLevel?: (level: number) => void
}

/** A reply being spoken: `add` more text as it arrives, `end` once there is no more. */
export type Speech = { add: (text: string) => void; end: () => void }

type Run = {
  stopped: boolean
  controller: AbortController
  source: AudioBufferSourceNode | null
  frame: number
  /** wakes the speaking loop when it waits for text */
  wake: () => void
}

/** Sentences; a period inside a number ("Room 2.03") does not end one. */
export function sentences(text: string) {
  return text.match(/.+?(?:[.!?]+["')\]]*(?=\s|$)|$)/gs)?.map((part) => part.trim()).filter(Boolean) ?? []
}

// A short first piece starts the voice sooner; the rest goes in fewer, longer requests (better flow, fewer calls).
const PIECE_CHARS = 220

// ---------- ElevenLabs availability ----------

const COOL_OFF_MS = 15_000 // after a piece failed twice, use the browser voice for a while before trying again
const SHORT_CHARS = 24 // a first sentence this short ("Step 2.") goes with the next one, not as a clip of its own
let cloud: Promise<boolean> | null = null
let cloudOffUntil = 0

function cloudVoice(): Promise<boolean> {
  if (Date.now() < cloudOffUntil) return Promise.resolve(false)
  cloud ??= api.health().then(
    (health) => Boolean(health.tts),
    () => {
      cloud = null // backend unreachable: ask again next time
      return false
    },
  )
  return cloud
}

// ---------- audio output ----------

let output: { context: AudioContext; analyser: AnalyserNode } | null = null

function audioOutput() {
  if (!output) {
    const context = new AudioContext()
    const analyser = context.createAnalyser()
    analyser.fftSize = 512
    analyser.connect(context.destination)
    output = { context, analyser }
  }
  return output
}

/** Browsers keep audio locked until the user taps or types: unlock it on the first gesture. */
export function unlockAudio() {
  if (typeof AudioContext === 'undefined') return
  const { context } = audioOutput()
  if (context.state === 'suspended') void context.resume()
}

if (typeof window !== 'undefined') {
  for (const type of ['pointerdown', 'keydown']) window.addEventListener(type, unlockAudio, { capture: true, passive: true })
}

async function audioReady() {
  if (typeof AudioContext === 'undefined') return false
  const { context } = audioOutput()
  if (context.state !== 'running') await Promise.race([context.resume(), new Promise((resolve) => setTimeout(resolve, 300))])
  return context.state === 'running'
}

function play(buffer: AudioBuffer, run: Run, onLevel?: (level: number) => void) {
  const { context, analyser } = audioOutput()
  return new Promise<void>((resolve) => {
    const source = context.createBufferSource()
    source.buffer = buffer
    source.connect(analyser)
    run.source = source
    const samples = new Uint8Array(analyser.fftSize)
    let level = 0
    const tick = () => {
      analyser.getByteTimeDomainData(samples)
      let sum = 0
      for (const sample of samples) sum += ((sample - 128) / 128) ** 2
      level += (Math.min(1, Math.sqrt(sum / samples.length) * 4) - level) * 0.35
      onLevel?.(level)
      run.frame = requestAnimationFrame(tick)
    }
    source.onended = () => {
      cancelAnimationFrame(run.frame)
      run.source = null
      resolve()
    }
    source.start()
    run.frame = requestAnimationFrame(tick)
  })
}

// ---------- browser voice (fallback) ----------

function bestVoice(lang: string) {
  const voices = speechSynthesis.getVoices().filter((voice) => voice.lang.replace('_', '-').startsWith(lang.slice(0, 2)))
  const rank = (voice: SpeechSynthesisVoice) =>
    (/natural|neural|premium|enhanced/i.test(voice.name) ? 4 : 0) + (/google/i.test(voice.name) ? 2 : 0) +
    (voice.lang.replace('_', '-') === lang ? 1 : 0) + (voice.localService ? 0 : 1)
  return voices.sort((a, b) => rank(b) - rank(a))[0] ?? null
}

// ---------- the one voice ----------

let current: Run | null = null

/** Stop speaking now (both voices). */
export function silence() {
  if (current) {
    const run = current
    current = null
    run.stopped = true
    run.controller.abort()
    try {
      run.source?.stop()
    } catch {
      // not started yet
    }
    cancelAnimationFrame(run.frame)
    run.wake()
  }
  if ('speechSynthesis' in window) speechSynthesis.cancel()
}

/** Start speaking a reply (BCP 47 `lang`) whose text arrives in parts, cutting off anything still speaking. */
export function openSpeech(lang: string, handlers: Handlers = {}): Speech {
  silence()
  const queue: string[] = [] // sentences not handed to a voice yet
  let ended = false
  let wake: (() => void) | null = null
  const nudge = () => {
    const resume = wake
    wake = null
    resume?.()
  }
  const signal = () => new Promise<void>((resolve) => { wake = resolve })
  const run: Run = { stopped: false, controller: new AbortController(), source: null, frame: 0, wake: nudge }
  current = run
  let started = false
  const start = () => {
    if (started) return
    started = true
    handlers.onStart?.()
  }
  const finish = () => {
    if (current === run) current = null
    handlers.onLevel?.(0)
    handlers.onEnd?.()
  }

  // ElevenLabs: each piece is fetched while the one before it plays; text that arrives meanwhile is fetched at once.
  type Fetched = { text: string; audio: Promise<AudioBuffer> }
  let cloudMode = false
  let first = true
  let pending: Fetched | null = null
  const refill = () => {
    if (!cloudMode || pending || !queue.length) return
    let text = queue.shift()!
    if (!first) while (queue.length && text.length + queue[0].length < PIECE_CHARS) text += ' ' + queue.shift()
    else if (text.length < SHORT_CHARS && queue.length) text += ' ' + queue.shift()
    pending = { text, audio: fetchAudio(text) }
  }
  const fetchAudio = (text: string) => {
    const audio = api.speech(text, lang, run.controller.signal).then((bytes) => audioOutput().context.decodeAudioData(bytes))
    audio.catch(() => {}) // a failure surfaces when it is awaited, never as an unhandled rejection
    return audio
  }

  const speakCloud = async () => {
    cloudMode = true
    for (;;) {
      if (run.stopped) return
      refill()
      if (!pending) {
        if (ended) return
        await signal()
        continue
      }
      const fetched: Fetched = pending
      let buffer: AudioBuffer
      try {
        // one retry first: a single hiccup should not hand the rest of the reply to the browser voice
        buffer = await fetched.audio.catch((error) => {
          if (run.stopped) throw error
          console.info('[voice] ElevenLabs piece failed, retrying once:', error)
          return fetchAudio(fetched.text)
        })
      } catch (error) {
        queue.unshift(fetched.text) // the browser voice says it instead
        pending = null
        cloudMode = false
        throw error
      }
      pending = null
      first = false
      refill() // the next piece downloads while this one plays
      if (run.stopped) return
      start()
      await play(buffer, run, handlers.onLevel)
    }
  }

  // Browser voice: one utterance per sentence (Chrome stops long utterances after ~15 s), queued as text arrives.
  const speakBrowser = async () => {
    const synth = 'speechSynthesis' in window
    const voice = synth ? bestVoice(lang) : null
    let level = 0 // no audio signal here: pulse on each spoken word, then decay
    const decay = () => {
      level *= 0.9
      handlers.onLevel?.(level)
      run.frame = requestAnimationFrame(decay)
    }
    run.frame = requestAnimationFrame(decay)
    let speaking = 0
    for (;;) {
      if (run.stopped) return
      while (queue.length) {
        const text = queue.shift()!
        if (!synth) continue
        const utterance = new SpeechSynthesisUtterance(text)
        utterance.lang = lang
        if (voice) utterance.voice = voice
        utterance.rate = 1.04
        utterance.onboundary = () => { level = 0.55 + Math.random() * 0.45 }
        utterance.onend = utterance.onerror = () => {
          speaking -= 1
          nudge()
        }
        speaking += 1
        start()
        speechSynthesis.speak(utterance)
      }
      if (ended && speaking <= 0) break
      await signal()
    }
    cancelAnimationFrame(run.frame)
  }

  void (async () => {
    if ((await cloudVoice()) && (await audioReady()) && !run.stopped) {
      try {
        await speakCloud()
        if (!run.stopped) finish()
        return
      } catch (error) {
        if (run.stopped) return
        console.info('[voice] ElevenLabs voice failed, using the browser voice:', error)
        cloudOffUntil = Date.now() + COOL_OFF_MS
      }
    }
    if (run.stopped) return
    await speakBrowser()
    if (!run.stopped) finish()
  })()

  return {
    add: (text) => {
      if (run.stopped) return
      queue.push(...sentences(text))
      refill()
      nudge()
    },
    end: () => {
      ended = true
      nudge()
    },
  }
}

/** Speak `text` (BCP 47 `lang`) in one go, cutting off anything still speaking. */
export function speakAloud(text: string, lang: string, handlers: Handlers = {}) {
  const speech = openSpeech(lang, handlers)
  speech.add(text)
  speech.end()
}
