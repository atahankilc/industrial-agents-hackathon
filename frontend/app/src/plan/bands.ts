// Shared drawing helpers for lines over the plan (the Guide's route in src/dev/StoryLayer.tsx, moving objects in
// ./ObjectsLayer.tsx): flat bands with round joints, and the camera zoom in steps so bands keep a steady pixel width.

import { useFrame, useThree } from '@react-three/fiber'
import { useState } from 'react'
import * as THREE from 'three'

const JOINT_SIDES = 12

/** A flat band `width` wide along scene points (X, Z) at height y, round joints; `along` = metres from the start. */
export function ribbon(points: [number, number][], width: number, y: number) {
  const positions: number[] = []
  const along: number[] = []
  const half = width / 2
  let distance = 0
  const disc = (X: number, Z: number, at: number) => {
    for (let i = 0; i < JOINT_SIDES; i++) {
      const a = (i / JOINT_SIDES) * Math.PI * 2
      const b = ((i + 1) / JOINT_SIDES) * Math.PI * 2
      positions.push(X, y, Z, X + Math.cos(b) * half, y, Z + Math.sin(b) * half, X + Math.cos(a) * half, y, Z + Math.sin(a) * half)
      along.push(at, at, at)
    }
  }
  for (let i = 0; i < points.length; i++) {
    const [X, Z] = points[i]
    disc(X, Z, distance)
    if (i + 1 === points.length) break
    const [X2, Z2] = points[i + 1]
    const length = Math.hypot(X2 - X, Z2 - Z)
    if (length < 1e-6) continue
    const nx = (-(Z2 - Z) / length) * half
    const nz = ((X2 - X) / length) * half
    const end = distance + length
    positions.push(X + nx, y, Z + nz, X2 + nx, y, Z2 + nz, X2 - nx, y, Z2 - nz, X + nx, y, Z + nz, X2 - nx, y, Z2 - nz, X - nx, y, Z - nz)
    along.push(distance, end, end, distance, end, distance)
    distance = end
  }
  const geometry = new THREE.BufferGeometry()
  geometry.setAttribute('position', new THREE.Float32BufferAttribute(positions, 3))
  geometry.setAttribute('along', new THREE.Float32BufferAttribute(along, 1))
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
