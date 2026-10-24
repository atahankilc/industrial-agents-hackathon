// Canvas, orbit controls and a camera rig that flies smoothly to what the Guide is talking about. The rig
// yields to the user: any drag cancels the flight, and slow auto-rotation resumes only after a quiet spell.

import { OrbitControls } from '@react-three/drei'
import { Canvas, useFrame, useThree } from '@react-three/fiber'
import { useEffect, useRef } from 'react'
import * as THREE from 'three'
import type { OrbitControls as OrbitControlsImpl } from 'three-stdlib'
import type { PointCloud } from '../api'
import { BuildingCloud, cloudExtent, type SpaceSets } from './BuildingCloud'
import { RouteFlow } from './RouteFlow'

export type Focus = { nonce: number; target: [number, number, number]; distance: number }

const IDLE_ROTATE_AFTER_MS = 9000
const PHONE_MAX_PX = 760
const FLY_EASE_PER_SECOND = 2.4

type Props = {
  cloud: PointCloud
  dark: boolean
  sets: SpaceSets
  floorsOn: boolean[]
  explode: number
  density: number
  emergeKey: number
  route: { vertices: [number, number, number, number][]; key: number } | null
  focus: Focus | null
  inset?: boolean // small preview canvas (Edit mode): no chat-panel offset
}

function CameraRig({ focus, cloud, inset }: { focus: Focus | null; cloud: PointCloud; inset?: boolean }) {
  const { camera, controls } = useThree() as { camera: THREE.PerspectiveCamera; controls: OrbitControlsImpl | null }
  const goal = useRef<{ target: THREE.Vector3; position: THREE.Vector3 } | null>(null)
  const lastInteraction = useRef(performance.now())

  // Keep the building centred in the area the chat panel leaves free (desktop): shift the principal point.
  const { size } = useThree()
  useEffect(() => {
    const panel = !inset && size.width > PHONE_MAX_PX ? Math.min(400, size.width * 0.36) + 16 : 0
    camera.filmOffset = (panel / 2 / size.width) * camera.getFilmWidth()
    camera.updateProjectionMatrix()
  }, [size, camera, inset])

  // Overview pose for each new building: the whole bounding sphere in view, looking down at ~35°.
  useEffect(() => {
    const { extent, top } = cloudExtent(cloud)
    const radius = Math.hypot(extent, top / 2)
    const distance = (radius / Math.sin((camera.fov * Math.PI) / 360)) * 1.05
    const target = new THREE.Vector3(0, top / 3, 0)
    camera.position.copy(target).add(new THREE.Vector3(0.62, 0.55, 0.56).normalize().multiplyScalar(distance))
    controls?.target.copy(target)
    goal.current = null
  }, [cloud, camera, controls])

  useEffect(() => {
    if (!focus || !controls) return
    const target = new THREE.Vector3(...focus.target)
    const direction = camera.position.clone().sub(controls.target).normalize()
    direction.y = Math.max(direction.y, 0.55) // keep looking down onto the floor plan
    direction.normalize()
    goal.current = { target, position: target.clone().add(direction.multiplyScalar(focus.distance)) }
    lastInteraction.current = performance.now()
  }, [focus, camera, controls])

  useEffect(() => {
    if (!controls) return
    const onStart = () => {
      goal.current = null
      lastInteraction.current = performance.now()
      controls.autoRotate = false
    }
    controls.addEventListener('start', onStart)
    return () => controls.removeEventListener('start', onStart)
  }, [controls])

  useFrame((_, delta) => {
    if (!controls) return
    if (goal.current) {
      const ease = Math.min(1, delta * FLY_EASE_PER_SECOND)
      controls.target.lerp(goal.current.target, ease)
      camera.position.lerp(goal.current.position, ease)
      if (camera.position.distanceTo(goal.current.position) < 0.05) goal.current = null
      lastInteraction.current = performance.now()
    }
    controls.autoRotate = !goal.current && performance.now() - lastInteraction.current > IDLE_ROTATE_AFTER_MS
  })
  return null
}

export function Scene({ cloud, dark, sets, floorsOn, explode, density, emergeKey, route, focus, inset }: Props) {
  const background = dark ? '#000000' : '#ffffff'
  return (
    <Canvas
      className="scene"
      dpr={[1, 2]}
      camera={{ fov: 45, near: 0.1, far: 5000, position: [60, 60, 60] }}
      gl={{ antialias: true, powerPreference: 'high-performance' }}
    >
      <color attach="background" args={[background]} />
      <BuildingCloud
        cloud={cloud}
        dark={dark}
        sets={sets}
        floorsOn={floorsOn}
        explode={explode}
        density={density}
        emergeKey={emergeKey}
      />
      {route && <RouteFlow vertices={route.vertices} dark={dark} explode={explode} routeKey={route.key} />}
      <OrbitControls makeDefault enableDamping dampingFactor={0.08} autoRotateSpeed={0.35} maxPolarAngle={Math.PI * 0.49} />
      <CameraRig focus={focus} cloud={cloud} inset={inset} />
    </Canvas>
  )
}
