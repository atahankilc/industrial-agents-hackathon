// ElevenLabs Scribe Realtime for the user's words, behind the browser's SpeechRecognition shape (start / stop / abort,
// onresult / onerror / onend), so useVoice's listening, pause timer and barge-in run on it unchanged. The microphone
// streams straight to ElevenLabs as 16 kHz PCM; our backend only hands out a single-use token and the building's
// keyterms (POST /stt/token, backend/api/stt.py), so room and machine names are heard right. Committed segments become
// final results, the running partial transcript the one interim result. When Scribe is off or fails, useVoice uses
// the browser's own recognition (error "scribe-unavailable").

import { api } from '../api'
import { acquireMicrophone, releaseMicrophone } from './mic'

const SOCKET = 'wss://api.elevenlabs.io/v1/speech-to-text/realtime'
const RATE = 16000
const COMMIT_WAIT_MS = 800 // after stop(): wait this long for the last committed segment (else the partial counts)
const COOL_OFF_MS = 60_000 // after a failure, the browser's recognition for a minute

// ---------- availability ----------

let available = false
let offUntil = 0
if (typeof window !== 'undefined') {
  api.health().then((health) => { available = Boolean(health.stt) }, () => {})
}

/** Scribe can be used now: the backend has a key and this browser can capture and process audio. */
export function scribeReady() {
  return available && Date.now() >= offUntil && typeof AudioWorkletNode !== 'undefined' && !!navigator.mediaDevices?.getUserMedia
}

function coolOff() {
  offUntil = Date.now() + COOL_OFF_MS
}

// ---------- tokens: one fetched ahead, so listening starts without a round trip ----------

type Grant = { token: string; keyterms: string[] }
let session: string | null = null
let ahead: Promise<Grant> | null = null

const grant = () => api.sttToken(session ?? undefined)

/** The conversation whose building's keyterms Scribe should use (BuildingScreen sets it). */
export function setScribeSession(id: string | null) {
  if (id === session) return
  session = id
  ahead = null
  if (id && scribeReady()) prefetch()
}

function prefetch() {
  ahead = grant()
  ahead.catch(() => { ahead = null })
}

function takeGrant(): Promise<Grant> {
  const next = ahead ?? grant()
  ahead = null
  void next.then(() => prefetch(), () => {}) // tokens last 15 minutes and one is used per connection
  return next
}

// ---------- microphone → 16 kHz PCM ----------

// Averages the input over each 16 kHz sample (a box filter against aliasing) and posts 100 ms of int16 at a time.
const WORKLET = `
class Pcm16 extends AudioWorkletProcessor {
  constructor() { super(); this.step = sampleRate / ${RATE}; this.acc = 0; this.sum = 0; this.count = 0; this.out = new Int16Array(${RATE / 10}); this.n = 0 }
  process(inputs) {
    const channel = inputs[0][0]
    if (!channel) return true
    for (let i = 0; i < channel.length; i++) {
      this.sum += channel[i]; this.count++; this.acc += 1
      if (this.acc < this.step) continue
      this.acc -= this.step
      this.out[this.n++] = Math.max(-1, Math.min(1, this.sum / this.count)) * 0x7fff
      this.sum = 0; this.count = 0
      if (this.n === this.out.length) { this.port.postMessage(this.out.buffer, [this.out.buffer]); this.out = new Int16Array(${RATE / 10}); this.n = 0 }
    }
    return true
  }
}
registerProcessor('pcm16', Pcm16)`

let workletUrl: string | null = null

type Mic = { node: AudioWorkletNode; source: MediaStreamAudioSourceNode }

// One audio graph for every listen (the barge-in watcher and the listener can overlap for a moment), on the app's one
// microphone stream (voice/mic.ts): opening them costs a few hundred milliseconds, so both stay for the next listen.
let context: Promise<AudioContext> | null = null

function captureContext(): Promise<AudioContext> {
  context ??= (async () => {
    const created = new AudioContext()
    workletUrl ??= URL.createObjectURL(new Blob([WORKLET], { type: 'text/javascript' }))
    await created.audioWorklet.addModule(workletUrl)
    return created
  })()
  context.catch(() => { context = null })
  return context
}

// A tap's pointerdown starts the listen, but on a touch screen only its pointerup / touchend count as the gesture that
// lets iOS run a new AudioContext: resume the capture graph then (a suspended one sends Scribe nothing).
if (typeof window !== 'undefined') {
  const wake = () => void context?.then((created) => {
    if (created.state !== 'running') return created.resume()
  }).catch(() => {})
  for (const type of ['pointerup', 'touchend', 'click']) window.addEventListener(type, wake, { capture: true, passive: true })
}

async function openMic(onChunk: (pcm: ArrayBuffer) => void): Promise<Mic> {
  const stream = await acquireMicrophone()
  let shared: AudioContext
  try {
    shared = await captureContext()
  } catch (error) {
    releaseMicrophone()
    throw error
  }
  if (shared.state !== 'running') void shared.resume() // interrupted (iOS: a call, another app's audio)
  const node = new AudioWorkletNode(shared, 'pcm16')
  node.port.onmessage = (event) => onChunk(event.data as ArrayBuffer)
  const source = shared.createMediaStreamSource(stream)
  source.connect(node)
  return { node, source }
}

function closeMic(mic: Mic | null) {
  if (!mic) return
  mic.node.port.onmessage = null
  mic.source.disconnect()
  mic.node.disconnect()
  releaseMicrophone()
}

function base64(buffer: ArrayBuffer) {
  const bytes = new Uint8Array(buffer)
  let binary = ''
  for (let i = 0; i < bytes.length; i += 0x8000) binary += String.fromCharCode(...bytes.subarray(i, i + 0x8000))
  return btoa(binary)
}

// ---------- the recogniser ----------

type Result = { isFinal: boolean; 0: { transcript: string } }
type ResultEvent = { resultIndex: number; results: ArrayLike<Result> }

export class ScribeRecognition {
  lang = 'en-US'
  interimResults = true // Scribe always sends partial transcripts
  continuous = true // and always listens until stopped
  onresult: ((event: ResultEvent) => void) | null = null
  onerror: ((event: { error: string }) => void) | null = null
  onend: (() => void) | null = null
  onaudiostart: (() => void) | null = null

  private socket: WebSocket | null = null
  private mic: Mic | null = null
  private pending: string[] = [] // audio captured before the socket opened
  private finals: string[] = []
  private partial = ''
  private stopping = false
  private done = false
  private commitTimer = 0

  start() {
    void this.run()
  }

  private async run() {
    try {
      // the microphone first, so nothing said while the connection opens is lost
      this.mic = await openMic((pcm) => this.send(pcm))
    } catch (error) {
      const name = (error as DOMException)?.name
      return this.fail(name === 'NotAllowedError' ? 'not-allowed' : name === 'NotFoundError' ? 'audio-capture' : 'scribe-unavailable')
    }
    if (this.done) {
      closeMic(this.mic)
      this.mic = null
      return
    }
    this.onaudiostart?.()
    let granted: Grant
    try {
      granted = await takeGrant()
    } catch {
      return this.fail('scribe-unavailable')
    }
    if (this.done) return
    const query = new URLSearchParams({
      model_id: 'scribe_v2_realtime', token: granted.token, audio_format: `pcm_${RATE}`, commit_strategy: 'manual',
      language_code: this.lang.slice(0, 2),
    })
    for (const term of granted.keyterms) query.append('keyterms', term)
    const socket = new WebSocket(`${SOCKET}?${query}`)
    this.socket = socket
    socket.onopen = () => {
      for (const chunk of this.pending) socket.send(chunk)
      this.pending = []
      if (this.stopping) this.commit()
    }
    socket.onmessage = (event) => this.receive(JSON.parse(event.data as string))
    socket.onclose = () => {
      if (!this.done) this.fail('scribe-unavailable')
    }
  }

  private send(pcm: ArrayBuffer) {
    if (this.done || this.stopping) return
    const message = JSON.stringify({ message_type: 'input_audio_chunk', audio_base_64: base64(pcm), commit: false, sample_rate: RATE })
    if (this.socket?.readyState === WebSocket.OPEN) this.socket.send(message)
    else this.pending.push(message)
  }

  private receive(message: { message_type: string; text?: string; error?: string }) {
    if (this.done) return
    if (message.message_type === 'partial_transcript') {
      // Scribe repeats the same partial about once a second through silence: only new words are a result, or the
      // listener's end-of-utterance pause would never come
      if ((message.text ?? '') === this.partial) return
      this.partial = message.text ?? ''
      this.emit(this.finals.length)
    } else if (message.message_type === 'committed_transcript') {
      if (message.text?.trim()) this.finals.push(message.text.trim())
      this.partial = ''
      this.emit(Math.max(0, this.finals.length - 1))
      if (this.stopping) this.finish()
    } else if (message.error) {
      console.info('[voice] Scribe:', message.message_type, message.error)
      if (message.message_type === 'insufficient_audio_activity') return this.fail('no-speech')
      this.fail('scribe-unavailable')
    }
  }

  private emit(resultIndex: number) {
    const results: Result[] = this.finals.map((transcript) => ({ isFinal: true, 0: { transcript: transcript + ' ' } }))
    if (this.partial) results.push({ isFinal: false, 0: { transcript: this.partial } })
    this.onresult?.({ resultIndex, results })
  }

  /** Stop listening; the words still being transcribed arrive as a last final result, then onend. */
  stop() {
    if (this.done || this.stopping) return
    this.stopping = true
    closeMic(this.mic)
    this.mic = null
    if (!this.partial) return this.finish() // nothing in flight
    if (this.socket?.readyState === WebSocket.OPEN) this.commit()
    this.commitTimer = window.setTimeout(() => this.finish(), COMMIT_WAIT_MS)
  }

  private commit() {
    // 100 ms of silence carries the commit
    const silence = base64(new Int16Array(RATE / 10).buffer)
    this.socket?.send(JSON.stringify({ message_type: 'input_audio_chunk', audio_base_64: silence, commit: true, sample_rate: RATE }))
  }

  abort() {
    if (this.done) return
    this.fail('aborted')
  }

  private fail(error: string) {
    if (this.done) return
    if (error === 'scribe-unavailable') coolOff() // so the next recogniser is the browser's
    this.onerror?.({ error })
    this.finish()
  }

  private finish() {
    if (this.done) return
    this.done = true
    clearTimeout(this.commitTimer)
    closeMic(this.mic)
    this.mic = null
    const socket = this.socket
    this.socket = null
    if (socket) {
      socket.onclose = null
      socket.close()
    }
    // after stop(), a pending interim result counts as heard: its commit did not come back in time
    if (this.stopping && this.partial) {
      this.finals.push(this.partial)
      this.partial = ''
      this.emit(this.finals.length - 1)
    }
    setTimeout(() => this.onend?.(), 0)
  }
}
