// The phone's compass: which way you face, in degrees clockwise from north, and how far the phone's back looks up
// or down. Held flat, you face where the top of the screen points; held up (as you look through it), where its back
// points. Android gives an absolute orientation (alpha, beta, gamma from north); iOS gives webkitCompassHeading
// after asking, and the question has to come from a tap. Magnetic north: the declination (a few degrees) is not
// corrected. UNVERIFIED: iOS's heading with the phone held up (it is documented for the top of the device).

type IOSOrientation = DeviceOrientationEvent & { webkitCompassHeading?: number }
export type Facing = { heading: number; pitch: number }

const rad = Math.PI / 180

/** A phone or tablet that may have a compass (desktops expose the API but never send a reading). */
export const compassLikely = () =>
  typeof window !== 'undefined' && 'DeviceOrientationEvent' in window && matchMedia('(pointer: coarse)').matches

/** iOS asks before sharing orientation; call it from a tap. Elsewhere this resolves at once. */
export async function askForCompass(): Promise<boolean> {
  if (typeof DeviceOrientationEvent === 'undefined') return false
  const ask = (DeviceOrientationEvent as unknown as { requestPermission?: () => Promise<string> }).requestPermission
  if (!ask) return true
  try {
    return (await ask()) === 'granted'
  } catch {
    return false
  }
}

const screenAngle = () => screen.orientation?.angle ?? 0

/** Which way the phone faces, from its orientation (degrees; alpha from north, counter-clockwise): the top of the
 * screen when it lies flatter than upright, else its back, and the back's tilt above the horizon (radians). */
function facing(alpha: number, beta: number, gamma: number): Facing {
  const [a, b, g] = [alpha * rad, beta * rad, gamma * rad]
  // the device's back (-z) in the earth's frame: east, north, up
  const east = -Math.sin(g) * Math.cos(a) - Math.cos(g) * Math.sin(b) * Math.sin(a)
  const north = -Math.sin(g) * Math.sin(a) + Math.cos(g) * Math.sin(b) * Math.cos(a)
  const up = -Math.cos(g) * Math.cos(b)
  const pitch = Math.asin(Math.max(-1, Math.min(1, up)))
  // flat: its top (+y, east -sin a cos b, north cos a cos b), turned by the screen's own rotation
  if (Math.abs(Math.cos(b)) > Math.hypot(east, north)) return { heading: (((-alpha + screenAngle()) % 360) + 360) % 360, pitch }
  return { heading: ((Math.atan2(east, north) / rad) % 360 + 360) % 360, pitch }
}

/** Calls back with every reading until the returned stop is called. */
export function watchCompass(onFacing: (facing: Facing) => void): () => void {
  const absolute = 'ondeviceorientationabsolute' in window
  const onAbsolute = (event: DeviceOrientationEvent) => {
    if (event.alpha === null || event.beta === null || event.gamma === null) return
    onFacing(facing(event.alpha, event.beta, event.gamma))
  }
  const onIOS = (event: IOSOrientation) => {
    const heading = event.webkitCompassHeading
    if (typeof heading !== 'number' || Number.isNaN(heading) || event.beta === null || event.gamma === null) return
    const pitch = Math.asin(Math.max(-1, Math.min(1, -Math.cos(event.gamma * rad) * Math.cos(event.beta * rad))))
    onFacing({ heading: (heading + screenAngle()) % 360, pitch })
  }
  if (absolute) window.addEventListener('deviceorientationabsolute', onAbsolute as EventListener)
  else window.addEventListener('deviceorientation', onIOS as EventListener)
  return () => {
    window.removeEventListener('deviceorientationabsolute', onAbsolute as EventListener)
    window.removeEventListener('deviceorientation', onIOS as EventListener)
  }
}

/** A camera turn (radians; 0 looks along scene -Z, the plan's north, and it grows anticlockwise seen from above)
 * for a compass heading. */
export const turnFor = (heading: number) => -heading * rad

/** The short way from one angle to another (radians, -π..π). */
export const shortest = (from: number, to: number) => Math.atan2(Math.sin(to - from), Math.cos(to - from))
