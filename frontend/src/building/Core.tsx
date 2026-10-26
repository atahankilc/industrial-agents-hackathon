// The Core: the Guide's presence and the main control — a soft, grainy ball of colour that flows. A fragment shader
// paints it (domain-warped noise over a four-stop palette, shading for volume, film grain). The palette says what
// the Guide is doing, in the HUD's own colours: a calm blue at rest, the live green while it listens, indigo while
// it works, the route blue while it speaks. The flow quickens with the voice level (useVoice's `level` ref, read
// every frame) and rings outward from the centre on each spoken word. Two ways to talk (the Guide's options):
// `hold` (default) — it listens only while held and letting go sends; pressing while it speaks cuts it off and
// listens. Tap — a tap listens until silence (a long press still sends on release), a tap while it speaks stops it,
// and answering a spoken question you can just talk over it (useVoice barge-in). Without WebGL the rest palette is
// a static CSS gradient. No glow.

import { useEffect, useRef, type KeyboardEvent, type MouseEvent, type PointerEvent, type RefObject } from 'react'
import type { VoiceState } from '../voice/useVoice'
import { reducedMotion } from '../motion'

const HOLD_MS = 350

type Palette = [number, number, number][]
const hex = (value: string): [number, number, number] => [0, 2, 4].map((at) => parseInt(value.slice(at + 1, at + 3), 16) / 255) as [number, number, number]
/** deep → mid → light → pale, per state; the mids are the HUD's --hud-route and --hud-live */
const PALETTES: Record<VoiceState, Palette> = {
  off: ['#283A9E', '#3D6BE0', '#93A9F6', '#E9E3FB'].map(hex),
  listening: ['#06594A', '#0FA67A', '#62D8B5', '#E0F8EF'].map(hex),
  thinking: ['#272A86', '#5A55E6', '#A99EFF', '#EEEBFF'].map(hex),
  speaking: ['#1532B0', '#2F6BFF', '#7FA2FF', '#E6E8FF'].map(hex),
}

const VERTEX = `
attribute vec2 aPos;
varying vec2 vUv;
void main(){ vUv = aPos; gl_Position = vec4(aPos, 0., 1.); }`

const FRAGMENT = `
precision highp float;
varying vec2 vUv;
uniform float uTime, uLevel, uBusy, uSpeak, uPx;
uniform vec3 uC0, uC1, uC2, uC3;
vec2 hash2(vec2 p){ p = vec2(dot(p, vec2(127.1, 311.7)), dot(p, vec2(269.5, 183.3))); return fract(sin(p) * 43758.5453) * 2. - 1.; }
float noise(vec2 p){
  vec2 i = floor(p), f = fract(p), u = f * f * (3. - 2. * f);
  return mix(mix(dot(hash2(i), f), dot(hash2(i + vec2(1, 0)), f - vec2(1, 0)), u.x),
             mix(dot(hash2(i + vec2(0, 1)), f - vec2(0, 1)), dot(hash2(i + vec2(1, 1)), f - vec2(1, 1)), u.x), u.y);
}
float fbm(vec2 p){ float v = 0., a = .5; for (int i = 0; i < 3; i++){ v += a * noise(p); p = p * 1.9 + 7.1; a *= .45; } return v; }
void main(){
  float r = length(vUv);
  float edge = 1. - smoothstep(1. - 2.5 * uPx, 1., r);
  if (edge <= 0.) discard;
  // the surface: a sphere's normal bends the flow toward the rim so it reads round, not flat
  vec2 p = vUv * (1. + .35 * (1. - sqrt(max(0., 1. - r * r))));
  float t = uTime;
  // working: the whole flow turns slowly round the centre
  float a = uBusy * t * .35;
  p = mat2(cos(a), -sin(a), sin(a), cos(a)) * p;
  float warp = .9 + uLevel * 1.6 + uBusy * .6;
  vec2 q = vec2(fbm(p * .8 + vec2(0., t * .21)), fbm(p * .8 + vec2(5.2, -t * .17)));
  float f = fbm(p * .9 + warp * q + vec2(t * .09, t * .05));
  // speaking: soft rings travel outward with the voice
  f += uSpeak * uLevel * .16 * sin(r * 11. - t * 4.);
  float v = smoothstep(0., 1., clamp(.5 + 1.5 * f + .18 * (vUv.y - vUv.x), 0., 1.));
  vec3 c = v < .4 ? mix(uC0, uC1, v / .4) : v < .75 ? mix(uC1, uC2, (v - .4) / .35) : mix(uC2, uC3, (v - .75) / .25);
  // light from the upper left, a darker lower right
  float shade = .93 + .14 * dot(normalize(vec3(vUv, sqrt(max(0., 1. - r * r)))), normalize(vec3(-.45, .55, .7)));
  c *= shade;
  c += (fract(sin(dot(gl_FragCoord.xy + fract(t * 7.) * 91.3, vec2(12.9898, 78.233))) * 43758.5453) - .5) * .045; // grain
  gl_FragColor = vec4(c * edge, edge);
}`

type Props = {
  state: VoiceState
  level: RefObject<number>
  /** a typed question is being answered: the ball works without the voice loop */
  busy: boolean
  size?: 'large' | 'small'
  /** push to talk: listen while held (`onHold`), send on release (`onFinish`) */
  hold?: boolean
  onHold?: () => void
  onListen: () => void
  onFinish: () => void
  onStop: () => void
}

export function Core({ state, level, busy, size = 'large', hold = false, onHold, onListen, onFinish, onStop }: Props) {
  const canvas = useRef<HTMLCanvasElement>(null)
  const pressed = useRef(0)
  const mode = state === 'off' && busy ? 'thinking' : state
  const modeRef = useRef(mode)
  useEffect(() => {
    modeRef.current = mode
  }, [mode])

  useEffect(() => {
    const element = canvas.current
    const gl = element?.getContext('webgl', { premultipliedAlpha: true, antialias: false })
    if (!element || !gl) return // the CSS gradient behind stays
    const compile = (type: number, source: string) => {
      const shader = gl.createShader(type)!
      gl.shaderSource(shader, source)
      gl.compileShader(shader)
      return shader
    }
    const program = gl.createProgram()!
    gl.attachShader(program, compile(gl.VERTEX_SHADER, VERTEX))
    gl.attachShader(program, compile(gl.FRAGMENT_SHADER, FRAGMENT))
    gl.linkProgram(program)
    if (!gl.getProgramParameter(program, gl.LINK_STATUS)) return
    gl.useProgram(program)
    const buffer = gl.createBuffer()
    gl.bindBuffer(gl.ARRAY_BUFFER, buffer)
    gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 1, -1, -1, 1, 1, 1]), gl.STATIC_DRAW)
    const position = gl.getAttribLocation(program, 'aPos')
    gl.enableVertexAttribArray(position)
    gl.vertexAttribPointer(position, 2, gl.FLOAT, false, 0, 0)
    const uniform = (name: string) => gl.getUniformLocation(program, name)
    const [uTime, uLevel, uBusy, uSpeak, uPx] = ['uTime', 'uLevel', 'uBusy', 'uSpeak', 'uPx'].map(uniform)
    const stops = ['uC0', 'uC1', 'uC2', 'uC3'].map(uniform)
    const colour: Palette = PALETTES.off.map((stop) => [...stop] as [number, number, number])
    element.classList.add('ready')

    const fit = () => {
      const dpr = Math.min(2, devicePixelRatio || 1)
      const side = Math.round(element.clientWidth * dpr)
      if (element.width !== side) element.width = element.height = side
      gl.viewport(0, 0, side, side)
      gl.uniform1f(uPx, 2 / Math.max(1, side))
    }

    // Reduced motion slows the drift but keeps the response to the voice: that is feedback, not decoration.
    const reduced = reducedMotion()
    const ease = (from: number, to: number, rate: number, dt: number) => from + (to - from) * (1 - Math.exp(-rate * dt))
    let frame = 0
    let last = performance.now()
    let time = Math.random() * 50
    let energy = 0
    let work = 0
    let speak = 0
    const draw = (now: number) => {
      const dt = Math.min(0.05, (now - last) / 1000)
      last = now
      const current = modeRef.current
      const heard = current === 'listening' || current === 'speaking' ? Math.min(1, level.current ?? 0) : 0
      energy = ease(energy, heard, 10, dt)
      work = ease(work, current === 'thinking' ? 1 : 0, 3, dt)
      speak = ease(speak, current === 'speaking' ? 1 : 0, 4, dt)
      // the colours cross-fade to the state's palette over about half a second
      PALETTES[current].forEach((stop, index) => {
        stop.forEach((channel, at) => (colour[index][at] = ease(colour[index][at], channel, 6, dt)))
        gl.uniform3fv(stops[index], colour[index])
      })
      time += dt * (0.35 + energy * 2.2 + work * 1.1 + (current === 'listening' ? 0.3 : 0)) * (reduced ? 0.4 : 1)
      element.style.setProperty('--swell', (1 + energy * 0.07).toFixed(3))
      fit()
      gl.uniform1f(uTime, time)
      gl.uniform1f(uLevel, energy)
      gl.uniform1f(uBusy, work)
      gl.uniform1f(uSpeak, speak)
      gl.drawArrays(gl.TRIANGLE_STRIP, 0, 4)
      frame = requestAnimationFrame(draw)
    }
    frame = requestAnimationFrame(draw)
    return () => {
      cancelAnimationFrame(frame)
      element.classList.remove('ready')
      gl.deleteProgram(program)
      gl.deleteBuffer(buffer)
    }
  }, [level])

  const pushToTalk = hold && !!onHold
  const label = pushToTalk
    ? mode === 'listening' ? 'Listening. Let go to send' : mode === 'speaking' ? 'Speaking. Hold to talk over it' : mode === 'thinking' ? 'Working' : 'Hold to talk'
    : mode === 'listening' ? 'Listening. Release or tap to send' : mode === 'speaking' ? 'Speaking. Tap to stop' : mode === 'thinking' ? 'Working' : 'Tap or hold to talk'

  // push to talk: listening lasts exactly as long as the press (pointer captured, so letting go anywhere sends)
  const holding = useRef(false)
  const press = () => {
    if (holding.current || mode === 'thinking') return
    holding.current = true
    onHold?.()
  }
  const release = () => {
    if (!holding.current) return
    holding.current = false
    onFinish()
  }
  const handlers = pushToTalk
    ? {
        onPointerDown: (event: PointerEvent<HTMLButtonElement>) => {
          if (event.button !== 0) return
          event.currentTarget.setPointerCapture(event.pointerId)
          press()
        },
        onPointerUp: release,
        onPointerCancel: release,
        onContextMenu: (event: MouseEvent) => event.preventDefault(), // a long touch is the press, not a menu
        onKeyDown: (event: KeyboardEvent) => {
          if (event.key !== 'Enter' && event.key !== ' ') return
          event.preventDefault()
          if (!event.repeat) press()
        },
        onKeyUp: (event: KeyboardEvent) => (event.key === 'Enter' || event.key === ' ') && release(),
        onBlur: release,
      }
    : {
        onPointerDown: (event: PointerEvent<HTMLButtonElement>) => {
          if (event.button !== 0) return
          // a press that starts listening: a quick tap keeps listening until silence, a hold sends on release
          pressed.current = mode === 'off' ? performance.now() : 0
          if (mode === 'off') onListen()
        },
        onPointerUp: () => {
          const startedHere = pressed.current > 0
          const held = startedHere ? performance.now() - pressed.current : 0
          pressed.current = 0
          if (mode === 'listening' && (!startedHere || held > HOLD_MS)) onFinish()
          else if (mode === 'speaking' && !startedHere) onStop()
        },
        onKeyDown: (event: KeyboardEvent) => {
          if (event.key !== 'Enter' && event.key !== ' ') return
          event.preventDefault()
          if (mode === 'off') onListen()
          else if (mode === 'listening') onFinish()
          else if (mode === 'speaking') onStop()
        },
      }

  return (
    <button
      type="button"
      className={`core ${size} ${mode}${pushToTalk ? ' hold' : ''}`}
      aria-label={label}
      title={label}
      disabled={mode === 'thinking'}
      {...handlers}
    >
      <canvas ref={canvas} className="core-ball" aria-hidden="true" />
    </button>
  )
}
