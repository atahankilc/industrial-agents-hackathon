// The active route as light: the path draws itself in, comets with fading tails flow along it, and the
// destination pulses. Vertices are the backend's viewer-frame polyline ([x, y, z, floor index]).

import { useFrame, useThree } from '@react-three/fiber'
import { useEffect, useMemo, useRef } from 'react'
import * as THREE from 'three'
import { routeFragment, routeVertex } from './shaders'

const COMETS = 7
const TAIL = 36
const TAIL_SPACING_M = 0.32
const SPEED_M_PER_S = 7
const DRAW_IN_SECONDS = 1.4
const RING_POINTS = 64
const EASE_PER_SECOND = 4

type Props = { vertices: [number, number, number, number][]; dark: boolean; explode: number; routeKey: number }

export function RouteFlow({ vertices, dark, explode, routeKey }: Props) {
  const { size, camera } = useThree()
  const explodeNow = useRef(explode)
  const started = useRef(performance.now())
  useEffect(() => {
    started.current = performance.now()
  }, [routeKey])

  const comets = useMemo(() => {
    const geometry = new THREE.BufferGeometry()
    geometry.setAttribute('position', new THREE.BufferAttribute(new Float32Array(COMETS * TAIL * 3), 3))
    const head = new Float32Array(COMETS * TAIL)
    for (let c = 0; c < COMETS; c++) for (let j = 0; j < TAIL; j++) head[c * TAIL + j] = Math.pow(1 - j / TAIL, 1.6)
    geometry.setAttribute('aHead', new THREE.BufferAttribute(head, 1))
    return geometry
  }, [])
  const ring = useMemo(() => {
    const geometry = new THREE.BufferGeometry()
    geometry.setAttribute('position', new THREE.BufferAttribute(new Float32Array(RING_POINTS * 3), 3))
    geometry.setAttribute('aHead', new THREE.BufferAttribute(new Float32Array(RING_POINTS).fill(0.6), 1))
    return geometry
  }, [])
  const line = useMemo(() => new THREE.BufferGeometry(), [])
  const pointMaterial = useMemo(
    () =>
      new THREE.ShaderMaterial({
        vertexShader: routeVertex,
        fragmentShader: routeFragment,
        transparent: true,
        depthWrite: false,
        depthTest: false,
        uniforms: {
          uScale: { value: 1 },
          uSize: { value: 0.8 },
          uInk: { value: new THREE.Color() },
          uDark: { value: 1 },
          uOpacity: { value: 0 },
        },
      }),
    [],
  )
  const ringMaterial = useMemo(() => pointMaterial.clone(), [pointMaterial])
  const lineMaterial = useMemo(
    () => new THREE.LineBasicMaterial({ transparent: true, depthWrite: false, depthTest: false, opacity: 0 }),
    [],
  )
  const lineObject = useMemo(() => new THREE.Line(line, lineMaterial), [line, lineMaterial])

  useEffect(() => {
    for (const material of [pointMaterial, ringMaterial]) {
      material.blending = dark ? THREE.AdditiveBlending : THREE.NormalBlending
      material.uniforms.uDark.value = dark ? 1 : 0
      material.uniforms.uInk.value.set(dark ? '#ffffff' : '#000000')
    }
    ringMaterial.uniforms.uSize.value = 0.32
    lineMaterial.color.set(dark ? '#ffffff' : '#000000')
  }, [dark, pointMaterial, ringMaterial, lineMaterial])

  useEffect(
    () => () => {
      for (const item of [comets, ring, line, pointMaterial, ringMaterial, lineMaterial]) item.dispose()
    },
    [comets, ring, line, pointMaterial, ringMaterial, lineMaterial],
  )

  const world = useRef<THREE.Vector3[]>([])
  const cumulative = useRef<number[]>([0])
  const tmp = useMemo(() => new THREE.Vector3(), [])

  const layout = () => {
    world.current = vertices.map(([x, y, z, floor]) => new THREE.Vector3(x, y + floor * explodeNow.current, z))
    const lengths = [0]
    for (let i = 1; i < world.current.length; i++) {
      lengths.push(lengths[i - 1] + world.current[i].distanceTo(world.current[i - 1]))
    }
    cumulative.current = lengths
  }

  const along = (distance: number, out: THREE.Vector3) => {
    const lengths = cumulative.current
    const points = world.current
    let i = 1
    while (i < lengths.length - 1 && lengths[i] < distance) i++
    const t = (distance - lengths[i - 1]) / Math.max(lengths[i] - lengths[i - 1], 1e-6)
    return out.lerpVectors(points[i - 1], points[i], Math.min(Math.max(t, 0), 1))
  }

  useFrame((frame, delta) => {
    if (vertices.length < 2) return
    explodeNow.current += (explode - explodeNow.current) * Math.min(1, delta * EASE_PER_SECOND)
    layout()
    const total = cumulative.current[cumulative.current.length - 1] || 1
    const elapsed = (performance.now() - started.current) / 1000
    const drawn = Math.min(1, elapsed / DRAW_IN_SECONDS)
    const reach = total * (1 - Math.pow(1 - drawn, 3))

    // Line drawn up to `reach`.
    const visible: THREE.Vector3[] = []
    for (let i = 0; i < world.current.length && cumulative.current[i] <= reach; i++) visible.push(world.current[i])
    visible.push(along(reach, new THREE.Vector3()))
    line.setFromPoints(visible)
    lineMaterial.opacity = (dark ? 0.7 : 0.8) * drawn

    // Comets: heads spread evenly, tails trail behind, all clipped to the drawn part.
    const positions = comets.attributes.position.array as Float32Array
    const time = frame.clock.elapsedTime
    for (let c = 0; c < COMETS; c++) {
      const headAt = ((c / COMETS) * total + time * SPEED_M_PER_S) % total
      for (let j = 0; j < TAIL; j++) {
        const d = Math.min(Math.max(headAt - j * TAIL_SPACING_M, 0), reach)
        along(d, tmp)
        positions.set([tmp.x, tmp.y + Math.sin(time * 3 + c + j * 0.2) * 0.04, tmp.z], (c * TAIL + j) * 3)
      }
    }
    comets.attributes.position.needsUpdate = true

    // Destination ring: expands and fades, once the path has arrived.
    const end = world.current[world.current.length - 1]
    const phase = (time * 0.6) % 1
    const radius = 0.4 + phase * 2.2
    const ringPositions = ring.attributes.position.array as Float32Array
    for (let k = 0; k < RING_POINTS; k++) {
      const angle = (k / RING_POINTS) * Math.PI * 2
      ringPositions.set([end.x + Math.cos(angle) * radius, end.y - 0.9, end.z + Math.sin(angle) * radius], k * 3)
    }
    ring.attributes.position.needsUpdate = true

    const perspective = camera as THREE.PerspectiveCamera
    const scale = size.height / (2 * Math.tan((perspective.fov * Math.PI) / 360))
    pointMaterial.uniforms.uScale.value = ringMaterial.uniforms.uScale.value = scale
    pointMaterial.uniforms.uOpacity.value = drawn
    ringMaterial.uniforms.uOpacity.value = drawn >= 1 ? (1 - phase) * 0.9 : 0
  })

  if (vertices.length < 2) return null
  return (
    <group renderOrder={2}>
      <primitive object={lineObject} />
      <points geometry={comets} material={pointMaterial} frustumCulled={false} />
      <points geometry={ring} material={ringMaterial} frustumCulled={false} />
    </group>
  )
}
