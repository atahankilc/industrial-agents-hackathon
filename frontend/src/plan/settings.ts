// Look-and-feel options of the plan. Fixed defaults for now (the Lab panel that switched them live was removed).

export type PlanSettings = {
  /** wall cut height in metres: lower shows more, higher reads more like rooms */
  wallHeight: number
  furniture: 'full' | 'off'
  /** floor colour: by what the room is used for, or one clay tone like an architectural model */
  colours: 'use' | 'clay'
  /** map-style pins for toilets, lifts, stairs, food and entrances */
  pins: boolean
  /** tint the room under the mouse (desktop) */
  hover: boolean
}

export const DEFAULT_SETTINGS: PlanSettings = {
  wallHeight: 0.85,
  furniture: 'full',
  colours: 'use',
  pins: false,
  hover: false,
}
