// The microphone, never a virtual device. Chrome records from the input picked for this site, which can be a virtual
// device that carries no voice at all ("Background Music", BlackHole, Teams, Zoom, …): the mic is "on" and only
// silence arrives. Then we ask for the system default input instead, or else the first real one.
//
// One stream for the whole app (Scribe and the orb's level meter both read it): iOS Safari captures from one stream
// at a time and mutes the older one when another opens, so a second open left the next listen with silence. A home
// screen app on iOS also asks again for every new open, so the stream stays warm a while after the last user.

const VIRTUAL = /virtual|background music|blackhole|soundflower|loopback|teams audio|zoomaudio|aggregate/i
const AUDIO: MediaTrackConstraints = { echoCancellation: true, noiseSuppression: true, autoGainControl: true }
const standalone = typeof window !== 'undefined' &&
  (window.matchMedia?.('(display-mode: standalone)').matches || (navigator as { standalone?: boolean }).standalone === true)
const KEEP_MS = standalone ? 120_000 : 8000 // after the last user lets go, the stream stays open this long

/** iPhone / iPad, where only one capture runs at a time (iPadOS reports itself as a Mac with touch). */
export const iOS = typeof navigator !== 'undefined' &&
  (/iPhone|iPad|iPod/.test(navigator.userAgent) || (/Macintosh/.test(navigator.userAgent) && navigator.maxTouchPoints > 1))

// the real input picked last time, asked for straight away (two opens per listen were a noticeable lag)
let chosen: string | null = null
let shared: MediaStream | null = null
let opening: Promise<MediaStream> | null = null
let users = 0
let timer = 0

/** The stream still carries sound: not stopped, and not muted by another capture or an interruption (a call). */
export const capturing = (stream: MediaStream | null) =>
  !!stream && stream.getAudioTracks().some((track) => track.readyState === 'live' && !track.muted)

/** The shared microphone stream; give it back with `releaseMicrophone` (never stop its tracks yourself). */
export async function acquireMicrophone(): Promise<MediaStream> {
  clearTimeout(timer)
  users += 1
  try {
    if (!capturing(shared)) {
      opening ??= open().finally(() => { opening = null })
      const stream = await opening
      if (shared !== stream) {
        shared?.getTracks().forEach((track) => track.stop())
        shared = stream
      }
    }
    return shared!
  } catch (error) {
    releaseMicrophone()
    throw error
  }
}

export function releaseMicrophone() {
  users = Math.max(0, users - 1)
  if (users > 0) return
  clearTimeout(timer)
  timer = window.setTimeout(() => {
    if (users > 0) return
    shared?.getTracks().forEach((track) => track.stop())
    shared = null
  }, KEEP_MS)
}

async function open(): Promise<MediaStream> {
  if (chosen) {
    try {
      return await navigator.mediaDevices.getUserMedia({ audio: { ...AUDIO, deviceId: { exact: chosen } } })
    } catch {
      chosen = null // unplugged: choose again
    }
  }
  const stream = await navigator.mediaDevices.getUserMedia({ audio: AUDIO })
  if (!VIRTUAL.test(stream.getAudioTracks()[0]?.label ?? '')) return stream
  const inputs = (await navigator.mediaDevices.enumerateDevices()).filter((device) => device.kind === 'audioinput')
  const real =
    inputs.find((device) => device.deviceId === 'default' && !VIRTUAL.test(device.label)) ??
    inputs.find((device) => device.label && !VIRTUAL.test(device.label))
  if (!real) return stream
  stream.getTracks().forEach((track) => track.stop())
  console.info('[voice] skipping the virtual input; using', real.label)
  chosen = real.deviceId
  return navigator.mediaDevices.getUserMedia({ audio: { ...AUDIO, deviceId: { exact: real.deviceId } } })
}
