// Shared drawing helpers for lines over the plan (the Guide's route in src/dev/StoryLayer.tsx, moving objects in
// ./ObjectsLayer.tsx): flat bands with round joints, and the camera zoom in steps so bands keep a steady pixel width.

import { useFrame, useThree } from '@react-three/fiber'
import { useState } from 'react'
import * as THREE from 'three'

const JOINT_SIDES = 12

/** A flat band `width` wide along scene points (X, Z) at height y, round joints; `along` = metres from the start,
 * `across` = metres off the centre line (both exact inside the joints too, so a shader can draw marks on the band). */
export function ribbon(points: [number, number][], width: number, y: number) {
  const positions: number[] = []
  const along: number[] = []
  const across: number[] = []
  const half = width / 2
  let distance = 0
  // a joint's along / across follow the direction it is drawn in (the segment after it; the last one: before it)
  const disc = (X: number, Z: number, at: number, tx: number, tz: number) => {
    const corner = (a: number) => {
      const ox = Math.cos(a) * half
      const oz = Math.sin(a) * half
      positions.push(X + ox, y, Z + oz)
      along.push(at + ox * tx + oz * tz)
      across.push(-ox * tz + oz * tx)
    }
    for (let i = 0; i < JOINT_SIDES; i++) {
      positions.push(X, y, Z)
      along.push(at)
      across.push(0)
      corner(((i + 1) / JOINT_SIDES) * Math.PI * 2)
      corner((i / JOINT_SIDES) * Math.PI * 2)
    }
  }
  let tx = 1
  let tz = 0
  for (let i = 0; i < points.length; i++) {
    const [X, Z] = points[i]
    const next = points.slice(i + 1).find(([X2, Z2]) => Math.hypot(X2 - X, Z2 - Z) >= 1e-6)
    if (next) {
      const length = Math.hypot(next[0] - X, next[1] - Z)
      tx = (next[0] - X) / length
      tz = (next[1] - Z) / length
    }
    disc(X, Z, distance, tx, tz)
    if (i + 1 === points.length) break
    const [X2, Z2] = points[i + 1]
    const length = Math.hypot(X2 - X, Z2 - Z)
    if (length < 1e-6) continue
    const nx = (-(Z2 - Z) / length) * half
    const nz = ((X2 - X) / length) * half
    const end = distance + length
    positions.push(X + nx, y, Z + nz, X2 + nx, y, Z2 + nz, X2 - nx, y, Z2 - nz, X + nx, y, Z + nz, X2 - nx, y, Z2 - nz, X - nx, y, Z - nz)
    along.push(distance, end, end, distance, end, distance)
    across.push(half, half, -half, half, -half, -half)
    distance = end
  }
  const geometry = new THREE.BufferGeometry()
  geometry.setAttribute('position', new THREE.Float32BufferAttribute(positions, 3))
  geometry.setAttribute('along', new THREE.Float32BufferAttribute(along, 1))
  geometry.setAttribute('across', new THREE.Float32BufferAttribute(across, 1))
  return geometry
}

/** Camera zoom (px per metre) in half-octave steps, so bands keep a steady pixel width; re-renders only the user. */
export function useZoomStep() {
  const camera = useThree((state) => state.camera) as THREE.OrthographicCamera
  const [step, setStep] = useState(() => quantise(camera.zoom))
  useFrame(() => {
    const next = quantise(camera.zoom)
    if (next !== step) setStep(next)
  })
  return step
}
const quantise = (zoom: number) => Math.pow(2, Math.round(Math.log2(Math.max(zoom, 0.5)) * 2) / 2)
