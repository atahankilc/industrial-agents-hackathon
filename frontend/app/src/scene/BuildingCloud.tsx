// The building as one THREE.Points draw call. Geometry is uploaded once per cloud; highlights, closures,
// lost access, floor visibility and the floor explode all ease on the GPU via uniforms + a space-state texture.

import { useFrame, useThree } from '@react-three/fiber'
import { useEffect, useMemo, useRef } from 'react'
import * as THREE from 'three'
import type { PointCloud } from '../api'
import { MAX_FLOORS, cloudFragment, cloudVertex } from './shaders'

export const EMERGE_SECONDS = 3.2
const EASE_PER_SECOND = 4

export type SpaceSets = { highlight: number[]; lost: number[]; closed: number[]; route: number[] }

type Props = {
  cloud: PointCloud
  dark: boolean
  sets: SpaceSets
  floorsOn: boolean[]
  explode: number
  density: number
  emergeKey: number
}

/** Deterministic pseudo-random (Park–Miller) so the scatter shell is identical on every load. */
function seeded(seed: number) {
  let state = seed
  return () => (state = (state * 16807) % 2147483647) / 2147483647
}

export function cloudExtent(cloud: PointCloud) {
  const positions = cloud.points.position_cm
  let extent = 1
  for (let i = 0; i < positions.length; i += 3) {
    extent = Math.max(extent, Math.abs(positions[i]) / 100, Math.abs(positions[i + 2]) / 100)
  }
  const top = Math.max(...cloud.floors.map((floor) => floor.elevation_m)) + 3
  return { extent, top }
}

export function BuildingCloud({ cloud, dark, sets, floorsOn, explode, density, emergeKey }: Props) {
  const { size, camera } = useThree()
  const { extent, top } = useMemo(() => cloudExtent(cloud), [cloud])

  const geometry = useMemo(() => {
    const { points, count } = cloud
    const position = new Float32Array(count * 3)
    const scatter = new Float32Array(count * 3)
    const random = seeded(1)
    for (let i = 0; i < count; i++) {
      for (let axis = 0; axis < 3; axis++) position[i * 3 + axis] = points.position_cm[i * 3 + axis] / 100
      const radius = extent * (0.7 + random() * 1.1)
      const theta = random() * Math.PI * 2
      const phi = Math.acos(2 * random() - 1)
      scatter[i * 3] = radius * Math.sin(phi) * Math.cos(theta)
      scatter[i * 3 + 1] = Math.abs(radius * Math.cos(phi)) * 0.5 - extent * 0.15
      scatter[i * 3 + 2] = radius * Math.sin(phi) * Math.sin(theta)
    }
    const result = new THREE.BufferGeometry()
    result.setAttribute('position', new THREE.BufferAttribute(position, 3))
    result.setAttribute('aScatter', new THREE.BufferAttribute(scatter, 3))
    result.setAttribute('aKind', new THREE.BufferAttribute(Float32Array.from(points.kind), 1))
    result.setAttribute('aFloor', new THREE.BufferAttribute(Float32Array.from(points.floor), 1))
    result.setAttribute('aSpace', new THREE.BufferAttribute(Float32Array.from(points.space), 1))
    result.setAttribute('aReveal', new THREE.BufferAttribute(Float32Array.from(points.reveal, (r) => r / 255), 1))
    result.computeBoundingSphere()
    return result
  }, [cloud, extent])

  // Per-space state, eased on the CPU (a few hundred spaces) and uploaded as a 1-row RGBA texture.
  const spaceCount = Math.max(1, cloud.spaces.length)
  const state = useMemo(() => {
    const data = new Uint8Array(spaceCount * 4)
    const texture = new THREE.DataTexture(data, spaceCount, 1, THREE.RGBAFormat)
    texture.minFilter = texture.magFilter = THREE.NearestFilter
    texture.needsUpdate = true
    return { data, texture, current: new Float32Array(spaceCount * 4), target: new Float32Array(spaceCount * 4) }
  }, [spaceCount])

  const material = useMemo(
    () =>
      new THREE.ShaderMaterial({
        vertexShader: cloudVertex,
        fragmentShader: cloudFragment,
        transparent: true,
        depthWrite: false,
        uniforms: {
          uTime: { value: 0 },
          uEmerge: { value: 0 },
          uScanY: { value: -10 },
          uDensity: { value: 1 },
          uExplode: { value: 0 },
          uSize: { value: 2.2 },
          uScale: { value: 1 },
          uAnyHighlight: { value: 0 },
          uAnyRoute: { value: 0 },
          uFloorOn: { value: new Array(MAX_FLOORS).fill(1) },
          uSpaceState: { value: state.texture },
          uInk: { value: new THREE.Color() },
          uDark: { value: 1 },
        },
      }),
    [state.texture],
  )

  useEffect(() => () => geometry.dispose(), [geometry])
  useEffect(() => () => material.dispose(), [material])
  useEffect(() => () => state.texture.dispose(), [state.texture])

  useEffect(() => {
    material.blending = dark ? THREE.AdditiveBlending : THREE.NormalBlending
    material.uniforms.uDark.value = dark ? 1 : 0
    material.uniforms.uInk.value.set(dark ? '#ffffff' : '#000000')
    material.needsUpdate = true
  }, [dark, material])

  useEffect(() => {
    const target = state.target
    target.fill(0)
    const mark = (indices: number[], channel: number) => {
      for (const index of indices) if (index >= 0 && index < spaceCount) target[index * 4 + channel] = 1
    }
    mark(sets.highlight, 0)
    mark(sets.lost, 1)
    mark(sets.closed, 2)
    mark(sets.route, 3)
  }, [sets, spaceCount, state.target])

  const emergeStart = useRef(0)
  useEffect(() => {
    emergeStart.current = performance.now()
  }, [emergeKey, cloud])

  const anyHighlight = sets.highlight.length > 0 ? 1 : 0
  const anyRoute = sets.route.length > 0 ? 1 : 0

  useFrame((frame, delta) => {
    const u = material.uniforms
    const ease = Math.min(1, delta * EASE_PER_SECOND)
    u.uTime.value = frame.clock.elapsedTime
    const emerge = Math.min(1, (performance.now() - emergeStart.current) / 1000 / EMERGE_SECONDS)
    u.uEmerge.value = emerge
    const floors = cloud.floors.length
    u.uScanY.value = -2 + (top + floors * u.uExplode.value + 4) * (1 - Math.pow(1 - emerge, 2))
    u.uExplode.value += (explode - u.uExplode.value) * ease
    u.uDensity.value += (density - u.uDensity.value) * ease
    u.uAnyHighlight.value += (anyHighlight - u.uAnyHighlight.value) * ease
    u.uAnyRoute.value += (anyRoute - u.uAnyRoute.value) * ease
    const floorOn = u.uFloorOn.value as number[]
    for (let i = 0; i < Math.min(floors, MAX_FLOORS); i++) {
      const wanted = floorsOn[i] === false ? 0 : 1
      floorOn[i] += (wanted - floorOn[i]) * ease
    }
    const perspective = camera as THREE.PerspectiveCamera
    u.uScale.value = size.height / (2 * Math.tan((perspective.fov * Math.PI) / 360))

    let changed = false
    const { current, target, data } = state
    for (let i = 0; i < current.length; i++) {
      const next = current[i] + (target[i] - current[i]) * ease
      if (Math.abs(next - current[i]) > 1e-3) {
        current[i] = next
        data[i] = Math.round(next * 255)
        changed = true
      }
    }
    if (changed) state.texture.needsUpdate = true
  })

  return <points geometry={geometry} material={material} frustumCulled={false} />
}
