// The Guide's voice presence: a WebGL particle sphere (same language as the building's point cloud).
// Thousands of soft sprites on a sphere, displaced in the vertex shader by 3D simplex noise; the state blends
// (smoothed on the CPU) drive the motion:
//   off — slow breathing drift · listening — the surface boils with the mic level · thinking — latitude bands
//   orbit against each other with a scan line · speaking — radial waves on every spoken word.
// A rim (fresnel) term and depth fade give it volume; a CSS glow behind the canvas swells with the level.
// Colour: --accent when the theme defines one, else --ink. Additive blending on dark backgrounds, normal on light.

import { useEffect, useRef, type RefObject } from 'react'
import * as THREE from 'three'
import type { VoiceState } from '../voice/useVoice'

const GOLDEN = Math.PI * (3 - Math.sqrt(5))

/*
 * 3D simplex noise (mod289 / permute / taylorInvSqrt / snoise), compact form, adapted from
 * webgl-noise: https://github.com/stegu/webgl-noise (fork of https://github.com/ashima/webgl-noise).
 *
 * Copyright (C) 2011 by Ashima Arts (Simplex noise)
 * Copyright (C) 2011-2016 by Stefan Gustavson (Classic noise and others)
 *
 * Permission is hereby granted, free of charge, to any person obtaining a copy
 * of this software and associated documentation files (the "Software"), to deal
 * in the Software without restriction, including without limitation the rights
 * to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
 * copies of the Software, and to permit persons to whom the Software is
 * furnished to do so, subject to the following conditions:
 *
 * The above copyright notice and this permission notice shall be included in
 * all copies or substantial portions of the Software.
 *
 * THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
 * IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
 * FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
 * AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
 * LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
 * OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
 * THE SOFTWARE.
 */
const NOISE = /* glsl */ `
vec3 mod289(vec3 x){return x-floor(x*(1./289.))*289.;}
vec4 mod289(vec4 x){return x-floor(x*(1./289.))*289.;}
vec4 permute(vec4 x){return mod289(((x*34.)+1.)*x);}
vec4 taylorInvSqrt(vec4 r){return 1.79284291400159-.85373472095314*r;}
float snoise(vec3 v){
  const vec2 C=vec2(1./6.,1./3.);const vec4 D=vec4(0.,.5,1.,2.);
  vec3 i=floor(v+dot(v,C.yyy));vec3 x0=v-i+dot(i,C.xxx);
  vec3 g=step(x0.yzx,x0.xyz);vec3 l=1.-g;vec3 i1=min(g.xyz,l.zxy);vec3 i2=max(g.xyz,l.zxy);
  vec3 x1=x0-i1+C.xxx;vec3 x2=x0-i2+C.yyy;vec3 x3=x0-D.yyy;
  i=mod289(i);
  vec4 p=permute(permute(permute(i.z+vec4(0.,i1.z,i2.z,1.))+i.y+vec4(0.,i1.y,i2.y,1.))+i.x+vec4(0.,i1.x,i2.x,1.));
  float n_=.142857142857;vec3 ns=n_*D.wyz-D.xzx;
  vec4 j=p-49.*floor(p*ns.z*ns.z);vec4 x_=floor(j*ns.z);vec4 y_=floor(j-7.*x_);
  vec4 x=x_*ns.x+ns.yyyy;vec4 y=y_*ns.x+ns.yyyy;vec4 h=1.-abs(x)-abs(y);
  vec4 b0=vec4(x.xy,y.xy);vec4 b1=vec4(x.zw,y.zw);
  vec4 s0=floor(b0)*2.+1.;vec4 s1=floor(b1)*2.+1.;vec4 sh=-step(h,vec4(0.));
  vec4 a0=b0.xzyw+s0.xzyw*sh.xxyy;vec4 a1=b1.xzyw+s1.xzyw*sh.zzww;
  vec3 p0=vec3(a0.xy,h.x);vec3 p1=vec3(a0.zw,h.y);vec3 p2=vec3(a1.xy,h.z);vec3 p3=vec3(a1.zw,h.w);
  vec4 norm=taylorInvSqrt(vec4(dot(p0,p0),dot(p1,p1),dot(p2,p2),dot(p3,p3)));
  p0*=norm.x;p1*=norm.y;p2*=norm.z;p3*=norm.w;
  vec4 m=max(.6-vec4(dot(x0,x0),dot(x1,x1),dot(x2,x2),dot(x3,x3)),0.);m=m*m;
  return 42.*dot(m*m,vec4(dot(p0,x0),dot(p1,x1),dot(p2,x2),dot(p3,x3)));
}`

const VERTEX = /* glsl */ `
${NOISE}
uniform float uTime, uLevel, uListen, uThink, uSpeak, uSize, uDpr, uFade;
attribute float aSeed;
varying float vAlpha;

vec3 rotY(vec3 p, float a){ float c=cos(a), s=sin(a); return vec3(c*p.x+s*p.z, p.y, -s*p.x+c*p.z); }

void main(){
  vec3 dir = normalize(position);
  // thinking: bands of latitude orbit in alternating directions
  float band = floor((dir.y + 1.) * 5.);
  float orbit = uThink * uTime * (0.7 + mod(band, 3.) * 0.45) * (mod(band, 2.) < 1. ? 1. : -1.);
  dir = rotY(dir, orbit);

  float t = uTime;
  float n1 = snoise(dir * 1.7 + vec3(0., t * 0.22, t * 0.15));     // slow body
  float n2 = snoise(dir * 4.2 + vec3(t * 0.9, -t * 0.6, t * 0.7));  // fine boil
  float wave = sin(t * 11. - (dir.y + 1.) * 6.5);                    // speaking: waves top → bottom
  float r = 1.
    + n1 * (0.05 + uThink * 0.03)
    + uListen * uLevel * (0.12 + 0.30 * (0.5 + 0.5 * n2))
    + uSpeak * uLevel * 0.22 * (0.55 + 0.45 * wave)
    + uListen * 0.03 * n2;
  // a thin shell of loose particles drifting off the surface
  r += step(0.93, aSeed) * (0.08 + 0.12 * fract(aSeed * 91.7 + t * 0.07)) * (0.6 + uLevel);

  vec3 p = dir * r;
  vec4 view = modelViewMatrix * vec4(p, 1.);
  gl_Position = projectionMatrix * view;

  vec3 n = normalize(mat3(modelViewMatrix) * p);
  float depth = clamp(n.z * 0.5 + 0.5, 0., 1.);  // front = 1
  float rim = pow(1. - abs(n.z), 2.2);           // edge-on = 1
  float scan = uThink * smoothstep(0.07, 0., abs(dir.y - sin(t * 1.7) * 0.85));
  vAlpha = ((0.04 + depth * 0.42 + rim * 0.32) * (0.8 + 0.4 * uLevel) + scan * 0.5) * uFade;
  gl_PointSize = uSize * uDpr * (0.55 + depth * 0.75 + rim * 0.35 + scan * 0.9 + uLevel * 0.35)
    * (0.7 + 0.6 * fract(aSeed * 13.1));
}`

const FRAGMENT = /* glsl */ `
uniform vec3 uColor;
varying float vAlpha;
void main(){
  vec2 c = gl_PointCoord - 0.5;
  float d = dot(c, c) * 4.;
  float core = exp(-d * 6.);          // bright centre
  float halo = exp(-d * 1.6) * 0.18;  // soft bloom
  float a = (core + halo) * vAlpha;
  if (a < 0.01) discard;
  gl_FragColor = vec4(uColor, a);
}`

function themeColour(element: Element) {
  const style = getComputedStyle(element)
  const value = style.getPropertyValue('--accent').trim() || style.getPropertyValue('--ink').trim() || '#000'
  const colour = new THREE.Color()
  try {
    colour.setStyle(value)
  } catch {
    colour.set('#000')
  }
  return colour
}

type Props = {
  state: VoiceState
  level: RefObject<number>
  size?: number
  onClick?: () => void
  label: string
  className?: string
  disabled?: boolean
}

export function VoiceOrb({ state, level, size = 132, onClick, label, className = '', disabled }: Props) {
  const host = useRef<HTMLButtonElement>(null)
  const glow = useRef<HTMLSpanElement>(null)
  const stateRef = useRef(state)
  useEffect(() => {
    stateRef.current = state
  }, [state])

  useEffect(() => {
    const element = host.current
    if (!element) return
    const small = size < 80
    const count = small ? 320 : size < 180 ? 1300 : 1700
    let renderer: THREE.WebGLRenderer
    try {
      renderer = new THREE.WebGLRenderer({ alpha: true, antialias: false, powerPreference: 'low-power' })
    } catch {
      return // no WebGL: the button and its glow still work
    }
    const dpr = Math.min(2, devicePixelRatio || 1)
    renderer.setPixelRatio(dpr)
    renderer.setSize(size, size)
    element.prepend(renderer.domElement)

    const scene = new THREE.Scene()
    const camera = new THREE.PerspectiveCamera(32, 1, 0.1, 20)
    camera.position.set(0, 0, 4.9)

    const positions = new Float32Array(count * 3)
    const seeds = new Float32Array(count)
    for (let i = 0; i < count; i++) {
      const y = 1 - (i / (count - 1)) * 2
      const r = Math.sqrt(1 - y * y)
      const theta = GOLDEN * i
      positions.set([Math.cos(theta) * r, y, Math.sin(theta) * r], i * 3)
      seeds[i] = Math.abs(Math.sin(i * 12.9898) * 43758.5453) % 1
    }
    const geometry = new THREE.BufferGeometry()
    geometry.setAttribute('position', new THREE.BufferAttribute(positions, 3))
    geometry.setAttribute('aSeed', new THREE.BufferAttribute(seeds, 1))

    const uniforms = {
      uTime: { value: 0 },
      uLevel: { value: 0 },
      uListen: { value: 0 },
      uThink: { value: 0 },
      uSpeak: { value: 0 },
      uSize: { value: small ? 2 : 2.6 * Math.sqrt(size / 160) },
      uFade: { value: 1 },
      uDpr: { value: dpr },
      uColor: { value: new THREE.Color() },
    }
    const material = new THREE.ShaderMaterial({
      uniforms, vertexShader: VERTEX, fragmentShader: FRAGMENT, transparent: true, depthWrite: false,
    })
    const applyTheme = () => {
      const colour = themeColour(element)
      uniforms.uColor.value = colour
      const light = colour.r * 0.299 + colour.g * 0.587 + colour.b * 0.114 > 0.5 // light ink = dark background
      material.blending = light ? THREE.AdditiveBlending : THREE.NormalBlending
      uniforms.uFade.value = light ? 1 : 0.7 // dark dots on paper stack up faster than light on black
      material.needsUpdate = true
      const rgb = [colour.r, colour.g, colour.b].map((channel) => Math.round(channel * 255)).join(', ')
      element.style.setProperty('--orb-glow', `rgba(${rgb}, ${light ? 0.3 : 0.12})`)
    }
    applyTheme()
    const themeWatch = new MutationObserver(applyTheme)
    themeWatch.observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme', 'style', 'class'] })
    const scheme = matchMedia('(prefers-color-scheme: dark)')
    scheme.addEventListener('change', applyTheme)

    const points = new THREE.Points(geometry, material)
    points.rotation.x = 0.35
    scene.add(points)

    // Reduced motion slows the drift but keeps the response to the voice: that is feedback, not decoration.
    const reduced = matchMedia('(prefers-reduced-motion: reduce)').matches
    let frame = 0
    let last = performance.now()
    let time = 0
    let energy = 0
    const ease = (from: number, to: number, rate: number, dt: number) => from + (to - from) * (1 - Math.exp(-rate * dt))
    const draw = (now: number) => {
      const dt = Math.min(0.05, (now - last) / 1000)
      last = now
      const current = stateRef.current
      time += dt * (reduced ? 0.35 : 1)
      energy = ease(energy, level.current ?? 0, 14, dt)
      uniforms.uTime.value = time
      uniforms.uLevel.value = energy
      uniforms.uListen.value = ease(uniforms.uListen.value, current === 'listening' ? 1 : 0, 5, dt)
      uniforms.uThink.value = ease(uniforms.uThink.value, current === 'thinking' ? 1 : 0, 3, dt)
      uniforms.uSpeak.value = ease(uniforms.uSpeak.value, current === 'speaking' ? 1 : 0, 5, dt)
      points.rotation.y += dt * (current === 'thinking' ? 0.9 : current === 'off' ? 0.2 : 0.4) * (reduced ? 0.3 : 1)
      const swell = current === 'off' ? 0.9 + Math.sin(time * 1.3) * 0.05 : 1 + energy * 0.6 + uniforms.uThink.value * 0.1
      if (glow.current) {
        glow.current.style.transform = `scale(${swell.toFixed(3)})`
        glow.current.style.opacity = String(current === 'off' ? 0.6 : 0.85 + energy * 0.15)
      }
      renderer.render(scene, camera)
      frame = requestAnimationFrame(draw)
    }
    frame = requestAnimationFrame(draw)

    return () => {
      cancelAnimationFrame(frame)
      themeWatch.disconnect()
      scheme.removeEventListener('change', applyTheme)
      geometry.dispose()
      material.dispose()
      renderer.dispose()
      renderer.domElement.remove()
    }
  }, [size, level])

  return (
    <button
      ref={host}
      type="button"
      className={`orb ${state} ${className}`.trim()}
      style={{ width: size, height: size }}
      onClick={onClick}
      disabled={disabled}
      aria-label={label}
      title={label}
    >
      <span ref={glow} className="orb-glow" aria-hidden="true" />
    </button>
  )
}
