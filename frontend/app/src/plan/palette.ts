// Colours of the plan drawing (WebGL + label canvas), light and dark. The CSS tokens in building/screen.css use
// the same values for the chrome around the plan; keep the two in step.

import type { Material } from './furniture'

export type PlanPalette = {
  /** furniture materials (src/plan/furniture.ts) */
  materials: Record<Material, string>
  ground: string
  /** clay model: wall body, furniture, slab edge, contact-shadow strength */
  clay: string
  /** wall tops seen straight from above (2D): a touch darker so they still outline the rooms */
  clayFlat: string
  /** room floors in the one-tone 'clay' colour mode */
  clayFloor: string
  /** model edges: wall/step outlines and (fainter) furniture outlines */
  edge: string
  furniture: string
  slab: string
  ao: number
  /** world grid on the ground plane */
  grid: string
  gridAlpha: number
  sky: string
  bounce: string
  wall: string
  hairline: string
  label: string
  labelSoft: string
  halo: string
  selected: string
  selectedEdge: string
  /** the user: the "you are here" figure's orange (hud.css --hud-me), also on the rooms they might be in */
  me: string
  /** doorway threshold strips (no door leaves: the data has no swing) and building entrances */
  door: string
  entrance: string
  /** access mode: a space this viewer may not enter, a dark neutral floor with nothing on it */
  restricted: string
  /** access mode: moving objects (marker, trail, mission line): a calm violet, apart from the route blue */
  object: string
  fills: Record<Category, string>
}

export type Category = 'walk' | 'core' | 'wet' | 'food' | 'learn' | 'work' | 'industry' | 'tech' | 'home' | 'room'

const BY_ROOM_TYPE: Record<string, Category> = {
  corridor: 'walk',
  lobby: 'walk',
  stairwell: 'core',
  lift: 'core',
  toilet: 'wet',
  bathroom: 'wet',
  locker_room: 'wet',
  kitchen: 'food',
  canteen: 'food',
  lecture_hall: 'learn',
  seminar_room: 'learn',
  meeting_room: 'learn',
  library: 'learn',
  office: 'work',
  lab: 'work',
  quality_lab: 'work',
  makerspace: 'work',
  print_room: 'work',
  production_zone: 'industry',
  assembly_zone: 'industry',
  additive_zone: 'industry',
  warehouse_zone: 'industry',
  logistics_zone: 'industry',
  server_room: 'tech',
  technical_room: 'tech',
  storage: 'tech',
  bedroom: 'home',
  living_room: 'home',
  balcony: 'home',
}

export function categoryOf(type: string, roomType: string): Category {
  if (type === 'corridor' || type === 'hall') return 'walk'
  if (type === 'stair' || type === 'lift') return 'core'
  return BY_ROOM_TYPE[roomType] ?? 'room'
}

export const LIGHT: PlanPalette = {
  materials: {
    wood: '#C9A27A', oak: '#D9B98F', fabric: '#7F9CC9', cushion: '#9BB3D6', linen: '#F4F1EA', blanket: '#E8A88F',
    ceramic: '#FBFBFA', metal: '#B8BCC4', dark: '#5E6168', steel: '#A9AEB6', leaf: '#5FAE6A', pot: '#D07B54',
    red: '#E5544B', screen: '#3C4A63', books: '#C98A5E', rack: '#F2A33A', cardboard: '#D7B07A',
    machine: '#9AA6B6', machineTop: '#C7CED8', glass: '#BFDDF2',
  },
  ground: '#ECE9E3',
  clay: '#F7F6F4',
  clayFlat: '#BDB9B2',
  clayFloor: '#EDEBE7',
  edge: '#B5AFA6',
  furniture: '#ECEAE6',
  slab: '#DCD9D3',
  ao: 0.22,
  grid: '#5A544C',
  gridAlpha: 0.16,
  sky: '#FFFFFF',
  bounce: '#DDD8D0',
  wall: '#3A3A3C',
  hairline: '#9A968F',
  label: '#2C2C2E',
  labelSoft: '#77736C',
  halo: '#FFFFFF',
  selected: '#D7E8FF',
  selectedEdge: '#0A84FF',
  me: '#F2602A',
  door: '#9CC3F0',
  entrance: '#0A84FF',
  restricted: '#6E6B66',
  object: '#7A5CC4',
  fills: {
    walk: '#F7F6F2',
    core: '#DCE3EE',
    wet: '#CBE2FA',
    food: '#FCDDB6',
    learn: '#E0D4F7',
    work: '#D9EFD6',
    industry: '#F1DFBF',
    tech: '#E0DCEB',
    home: '#E2F0D6',
    room: '#F7E0DA',
  },
}

export const DARK: PlanPalette = {
  materials: {
    wood: '#8C6E52', oak: '#9C7F5E', fabric: '#4F6A94', cushion: '#5D769C', linen: '#9E9A92', blanket: '#A36A57',
    ceramic: '#C6C6C8', metal: '#7D818A', dark: '#3A3C42', steel: '#70757E', leaf: '#3F7C4A', pot: '#94553A',
    red: '#B8433C', screen: '#26303F', books: '#8E6243', rack: '#B27628', cardboard: '#957950',
    machine: '#66707D', machineTop: '#868E99', glass: '#6E8AA0',
  },
  ground: '#161618',
  clay: '#8A8A92',
  clayFlat: '#9A9AA2',
  clayFloor: '#3E3E43',
  edge: '#2A2A2E',
  furniture: '#6A6A72',
  slab: '#3A3A40',
  ao: 0.34,
  grid: '#C8CBD6',
  gridAlpha: 0.1,
  sky: '#D5D9E4',
  bounce: '#3A3A42',
  wall: '#B4B4BA',
  hairline: '#6E6E73',
  label: '#F2F2F7',
  labelSoft: '#A1A1A6',
  halo: '#1C1C1E',
  selected: '#123A66',
  selectedEdge: '#409CFF',
  me: '#F2602A',
  door: '#4D78A8',
  entrance: '#409CFF',
  restricted: '#1B1B1E',
  object: '#A08BE8',
  fills: {
    walk: '#4A4A4F',
    core: '#3C4049',
    wet: '#2B3D52',
    food: '#4E3C27',
    learn: '#3E3653',
    work: '#2F4530',
    industry: '#463D2C',
    tech: '#3A3747',
    home: '#34452D',
    room: '#4A3532',
  },
}

export const CATEGORY_LABEL: Record<string, string> = {
  corridor: 'Corridor',
  lobby: 'Lobby',
  stairwell: 'Stairs',
  lift: 'Lift',
  toilet: 'Toilet',
  bathroom: 'Bathroom',
  locker_room: 'Locker room',
  kitchen: 'Kitchen',
  canteen: 'Canteen',
  lecture_hall: 'Lecture hall',
  seminar_room: 'Seminar room',
  meeting_room: 'Meeting room',
  library: 'Library',
  office: 'Office',
  lab: 'Lab',
  quality_lab: 'Quality lab',
  makerspace: 'Makerspace',
  print_room: 'Print room',
  production_zone: 'Production',
  assembly_zone: 'Assembly',
  additive_zone: 'Additive manufacturing',
  warehouse_zone: 'Warehouse',
  logistics_zone: 'Logistics',
  server_room: 'Server room',
  technical_room: 'Technical room',
  storage: 'Storage',
  bedroom: 'Bedroom',
  living_room: 'Living room',
  balcony: 'Balcony',
  generic_room: 'Room',
}
