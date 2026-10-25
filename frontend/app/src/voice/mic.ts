// The microphone, never a virtual device. Chrome records from the input picked for this site, which can be a virtual
// device that carries no voice at all ("Background Music", BlackHole, Teams, Zoom, …): the mic is "on" and only
// silence arrives. Then we ask for the system default input instead, or else the first real one.

const VIRTUAL = /virtual|background music|blackhole|soundflower|loopback|teams audio|zoomaudio|aggregate/i

// the real input picked last time, asked for straight away (two opens per listen were a noticeable lag)
let chosen: string | null = null

export async function openMicrophone(audio: MediaTrackConstraints): Promise<MediaStream> {
  if (chosen) {
    try {
      return await navigator.mediaDevices.getUserMedia({ audio: { ...audio, deviceId: { exact: chosen } } })
    } catch {
      chosen = null // unplugged: choose again
    }
  }
  const stream = await navigator.mediaDevices.getUserMedia({ audio })
  if (!VIRTUAL.test(stream.getAudioTracks()[0]?.label ?? '')) return stream
  const inputs = (await navigator.mediaDevices.enumerateDevices()).filter((device) => device.kind === 'audioinput')
  const real =
    inputs.find((device) => device.deviceId === 'default' && !VIRTUAL.test(device.label)) ??
    inputs.find((device) => device.label && !VIRTUAL.test(device.label))
  if (!real) return stream
  stream.getTracks().forEach((track) => track.stop())
  console.info('[voice] skipping the virtual input; using', real.label)
  chosen = real.deviceId
  return navigator.mediaDevices.getUserMedia({ audio: { ...audio, deviceId: { exact: real.deviceId } } })
}
