// Typed client for the FastAPI backend (backend/api/, routes in backend/api/routes/), reached through the Vite proxy at /api.

import type { Layout } from './map/board'

const BASE = import.meta.env.VITE_API_BASE ?? '/api'
/** the API base as an absolute URL (for commands shown to the admin, e.g. the object simulator) */
export const apiUrl = () => new URL(BASE, location.origin).href.replace(/\/$/, '')

/** `location`: real position (centre of the OSM outline) for the kit's OpenStreetMap buildings, else null;
 * `origin` is where the building's own metres start (x east, y north from it), which puts the model on the map;
 * `outline` its footprint, which marks its block on the map. */
export type BuildingKind = 'campus' | 'factory' | 'home' | 'real' | 'saved'

export type Building = {
  id: string
  split: string
  name: string | null
  /** what the landing list filters by (backend/api/sessions.py building_kind); null for an unknown source */
  kind: BuildingKind | null
  /** the owning organisation's slug (access mode; docs/product/organizations.md), null = the platform's */
  org?: string | null
  location: {
    lat: number
    lon: number
    address: string | null
    origin?: { lat: number; lon: number }
    /** footprint rings, [lon, lat] */
    outline?: [number, number][][]
    /** from the lowest floor to the top of the highest */
    height_m?: number
    /** degrees counter-clockwise from east to the building's x axis (backend/core/geoplace.py); absent = 0 (kit buildings) */
    bearing?: number
  } | null
}

/** Where a new building stands (POST /imports/stream `place`): the tapped OSM footprint, or a point on open ground. */
export type ImportPlace = { ring: [number, number][]; name?: string } | { point: [number, number]; name?: string }
export type ImportSuggestion = { ring?: [number, number][]; point?: [number, number]; name: string | null }
/** A placed building's position (backend/core/geoplace.py location_for) as the import returns it. */
export type PlacedLocation = NonNullable<Building['location']> & {
  origin: { lat: number; lon: number }
  bearing: number
  outline: [number, number][][]
  fit: { scale: number; iou?: number; low_confidence?: boolean } | null
}

/** backend/core/floorplan.py export: building metres (x right, y up). `center` centres the y-up scene:
 * X = x - center[0], Z = -y - center[1]. */
export type PlanFloor = { id: string; level: number; name: string; elevation_m: number; height_m: number }
export type PlanSpace = {
  id: string
  floor: number
  type: string
  room_type: string
  name: string
  ref: string
  polygon: [number, number][]
  area_m2: number
  label: [number, number]
  label_room_m: number
}
export type PlanOpening = {
  id: string
  floor: number
  kind: 'door' | 'opening' | 'entrance'
  position: [number, number]
  width_m: number
  step_free: boolean
  spaces: string[]
  entrance: boolean
  /** wall direction (degrees) at the opening; the data has no swing side or hinge */
  angle: number
  /** first drawn space (an entrance's indoor space) */
  space: string | null
}
export type PlanConnector = { id: string; name: string; kind: 'stairs' | 'lift'; spaces: string[]; step_free: boolean }
export type PlanAsset = {
  id: string
  floor: number
  space: string
  category: 'furniture' | 'fixture' | 'machine' | 'equipment'
  type: string
  name: string
  position: [number, number]
  size: [number, number]
  rotation_deg: number
}
/** A solid wall piece, outline first then holes (backend/core/floorplan.py `wall_solids`). */
export type PlanWall = { kind: 'exterior' | 'structural' | 'partition'; rings: [number, number][][] }
export type Plan = {
  building: { id: string; name: string; source: string; attribution: string }
  floors: PlanFloor[]
  bounds: [number, number, number, number]
  center: [number, number]
  spaces: PlanSpace[]
  walls: [number, number, number, number][][]
  wall_solids: PlanWall[][]
  /** per floor: the rooms with the wall gaps closed, polygons as [outer, ...holes] (backend/core/floorplan.py `outline`) */
  outlines?: [number, number][][][][]
  /** per floor: where two spaces overlap, diagonal stripes owned alternately by each (backend/core/floorplan.py `overlaps`) */
  overlaps?: { space: string; rings: [number, number][][] }[][]
  openings: PlanOpening[]
  connectors: PlanConnector[]
  assets: PlanAsset[]
  closed: string[]
  /** access mode: spaces this viewer may not enter, outline only (building metres), drawn darkened */
  restricted?: { id: string; floor: number; polygon: [number, number][] }[]
}

/** backend/core/directions.py: one turn-by-turn leg; `turn` is made at the start of the leg, relative to the way you face. */
export type RouteLeg = {
  kind: 'door' | 'connector' | 'exit' | 'arrive'
  to: string
  to_id: string
  floor: string | null
  distance_m: number
  turn: 'straight' | 'left' | 'right' | 'back'
  turn_deg: number | null
  via?: string
  via_kind?: string
  up?: boolean
  floors?: number
}

/** One followable step as the Guide says it (backend/core/directions.guidance): the turn where a person makes it, rounded
 * metres, the door and a landmark next to it; `text` is the Guide's sentence for it. */
export type GuideStep = {
  kind: RouteLeg['kind']
  turn: RouteLeg['turn']
  metres: number
  to: string
  to_id: string
  floor: string | null
  door?: string
  landmark?: string | null
  via?: string
  via_kind?: string
  up?: boolean
  floors?: number
  /** how many route legs this step covers (backend/core/directions.maneuvers joins straight-on doors), and doors passed */
  legs?: number
  doors?: number
  text: string
}

export type RouteEvent = {
  type: 'route'
  space_path: string[]
  element_path?: string[]
  length_m?: number
  profile?: string
  legs?: RouteLeg[]
  steps?: GuideStep[]
  /** route_to_building: this route ends at the exit, the rest is in a nearby building (backend/agents/campus.py) */
  next_building?: NextBuilding
  /** the living building (backend/core/live.py): what the route goes round or passes right now */
  live?: RouteLive
  /** the app moved the route round something that blocked it (backend/api/live/ live_check) */
  reroute?: { by: LiveRef[]; was_m?: number | null }
}
export type LiveRef = { id: string; name: string; kind: string; state?: string; space?: string; effect?: 'blocked' | 'wait' | 'squeeze' | 'wet_floor' }
export type RouteLive = { avoided?: LiveRef[]; passing?: LiveRef[]; detour_m?: number; without_live_m?: number; blocked_by?: LiveRef[] }
/** The rest of a route in a nearby building: across outside from `from` to `to` ([lon, lat] of the two entrances),
 * then in through `entrance` to `destination`. */
export type NextBuilding = {
  building: string
  name: string
  destination: string
  destination_name: string
  entrance: string
  entrance_space: string
  outdoor_m: number
  heading: string
  from: [number, number]
  to: [number, number]
}
export type HighlightEvent = { type: 'highlight'; space_ids: string[]; asset_ids?: string[]; style?: 'lost_access' }
/** search_nearby_buildings: matches in buildings next to this one, nearest first */
export type ElsewhereEvent = {
  type: 'elsewhere'
  query: string
  buildings: { building: string; name: string; distance_m: number; total: number; first: string | null }[]
}
export type UserLocation = { space_id: string; name: string; ref?: string | null; floor: string }
export type ChangeEvent = { type: 'change'; summary: string; targets: string[]; space_ids?: string[] }
/** Access mode: the Guide heard a preference to remember (backend/agents/tools/ remember_preference / set_preference);
 * `values` holds the changed fields, or `favourite` (a space id, always per building). */
export type PreferenceEvent = { type: 'preference'; scope: 'global' | 'building'; values: Record<string, unknown> }
/** The Guide switched the app to the Edit mode (backend/agents/tools/ open_edit_mode); `request` goes on to the Builder. */
export type EditModeEvent = { type: 'edit_mode'; request: string | null }
/** The Guide opened the Building settings (backend/agents/tools/ open_building_settings): the app shows them to the admin. */
export type SettingsEvent = { type: 'settings' }
/** The user told the Guide where they are (backend/agents/tools/ set_my_location): the "you are here" figure goes there. */
export type LocationEvent = { type: 'location'; space_id: string }
/** The user's position is needed but not known (backend/agents/tools/ suggest_my_location, or a route from "here"): rooms
 * they might be in — the Guide's guesses, else the entrances — marked after the answer; a tap stands them there. */
export type MaybeHereEvent = { type: 'maybe_here'; space_ids: string[]; source: 'guide' | 'entrances' }
/** The Guide talked about another step of the route being followed (backend/agents/tools/ show_route_step): the step card
 * goes there. */
export type RouteStepEvent = { type: 'route_step'; index: number }
/** The Guide ended the route (backend/agents/tools/ end_route): off the map, the step guide stops; `space_id`: where the
 * user is now (the destination when `arrived`, or the place they named), the figure goes there. */
export type RouteEndEvent = { type: 'route_end'; arrived: boolean; space_id?: string }

/** The Guide opened a nearby building (backend/agents/tools/ open_nearby_building): the app goes there, continuing a route
 * to it (route_to_building's `next_building`) when one is on the map. */
export type OpenBuildingEvent = { type: 'open_building'; building: string; name: string }

export type UiEvent = RouteEvent | HighlightEvent | ChangeEvent | PreferenceEvent | ElsewhereEvent | EditModeEvent | SettingsEvent | LocationEvent | MaybeHereEvent | RouteStepEvent | RouteEndEvent | OpenBuildingEvent

export type ChatReply = {
  reply: string
  tool_calls: { name: string; input: Record<string, unknown> }[]
  events: UiEvent[]
  ungrounded: string[]
  spoken?: string | null
}

/** Live progress of a turn (POST /chat/stream): a tool starting / finishing, or a self-check re-run. */
export type ChatStep =
  | { kind: 'tool'; name: string; input: Record<string, unknown> }
  | { kind: 'tool_done'; name: string; ok: boolean }
  | { kind: 'check'; name: 'profile' | 'grounding' }

/** `onSay`: voice turns only — each sentence of the spoken reply as soon as it may be said (before the reply);
 * together they are the whole spoken reply. */
export type ChatOptions = {
  channel?: 'text' | 'voice'
  /** voice channel: false when the message was tapped, not transcribed (no transcript rewrite) */
  heard?: boolean
  /** the space or asset id selected on the plan while asking, so "this room" / "there" mean it */
  selected?: string
  photo?: string
  /** the step card's step (0-based) while the user follows a route step by step, so the Guide knows where they are */
  routeStep?: number
  onStep?: (step: ChatStep) => void
  onSay?: (text: string) => void
}

export type SessionSummary = {
  session_id: string
  building: string
  profile: { step_free: boolean; min_door_width_m: number | null; avoid_lifts: boolean; summary: string }
  applied: { id: string; summary: string }[]
  pending: { id: string; summary: string }[]
  event_count: number
}

/** building.json as served by /drafts (docs/kit/data-format.md). */
export type SpaceJson = { id: string; floor_id: string; type: string; room_type: string; name: string; ref: string | null; polygon: [number, number][] }
export type OpeningJson = { id: string; floor_id: string; space_ids: string[]; kind: string; position: [number, number]; width_m: number; step_free: boolean }
export type AssetJson = {
  id: string; name: string; category: string; type: string; space_id: string; floor_id: string; position: [number, number]
  footprint: { width_m: number; depth_m: number; rotation_deg: number }
}
export type BuildingJson = {
  building: { id: string; name: string; source: string }
  floors: { id: string; level: number; name: string }[]
  spaces: SpaceJson[]
  openings: OpeningJson[]
  vertical_connectors: { id: string; space_ids: string[] }[]
  assets: AssetJson[]
}
/** backend/core/validate.py issue; warnings are issues the original building already had. */
export type Issue = { severity: 'error' | 'warning'; code: string; message: string; ids: string[] }
export type DraftState = { draft: { id: string; base: string; name: string; steps: number }; building: BuildingJson; issues: Issue[] }
/** backend/core/edits.py op: {"op": name, ...arguments}. */
export type Op = { op: string; [key: string]: unknown }
/** An open Builder proposal (backend/agents/builder_tools.py); `building` is the draft as it would be after the ops. */
export type Proposal = {
  id: string
  summary: string
  ops: Op[]
  new_problems: string[]
  effect: { changed_spaces: { id: string; name: string; area_before: number; area_after: number }[]; added: Record<string, number>; removed: Record<string, number> }
  building: BuildingJson
}
export type BuilderReply = {
  reply: string
  tool_calls: { name: string; input: unknown }[]
  proposal: Proposal | null
  applied: string | null
  state: DraftState
}
export type ImportLine =
  | { type: 'warning'; detail: string }
  | { type: 'step'; kind: 'say'; text: string }
  | { type: 'step'; kind: 'tool'; name: string; level?: number }
  | { type: 'step'; kind: 'tool_done'; name: string; ok: boolean }
  | {
      type: 'done'; draft_id: string; base: string; name: string; issues: Issue[]; notes: unknown; location?: PlacedLocation | null
      /** how the position was found: the map tap, the photos' GPS, or the browser's position */
      located_by?: 'tap' | 'photos' | 'device' | null
      /** the tapped building and the photos disagree: the building the photos point at */
      suggestion?: ImportSuggestion | null
    }
  | { type: 'no_plan'; reason: string }
  | { type: 'error'; detail: string }
export type BuilderStep = { kind: 'tool' | 'tool_done' | 'check'; name: string; input?: Record<string, unknown>; ok?: boolean }

// ---- access mode (src/access/auth.ts): the bearer token of the signed-in user, a gate that holds requests while a
// stored sign-in is being restored, and what a 401 does. With access mode off none of this is ever set.

let token: string | null = null
let gate: Promise<unknown> | null = null
let onUnauthorized: (() => void) | null = null

export const auth = {
  setToken: (next: string | null) => void (token = next),
  /** requests wait for `promise` (a stored session being restored), then go with whatever token it left */
  setGate: (promise: Promise<unknown> | null) => void (gate = promise),
  onUnauthorized: (handler: (() => void) | null) => void (onUnauthorized = handler),
}

/** An API error with its HTTP status; 403 carries the admin-only message. */
/** One floor's straightened source plan from the import (backend/core/plan_import/reference.py): a JPEG data URL and the 2×3
 * transform from its pixels to the building's metres (x right, y up). */
export type FloorReference = {
  floor_id: string
  level: number
  image: string
  transform: [[number, number, number], [number, number, number]]
}

export class ApiError extends Error {
  status: number
  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

/** A Guide / Builder turn that failed on the server, e.g. the Claude API credit ran out (backend/api/service_errors.py):
 * `message` is a sentence to show as is; `code` is credits | auth | busy | unavailable | offline | internal | conflict. */
export class ServiceError extends Error {
  code: string
  constructor(message: string, code: string) {
    super(message)
    this.code = code
  }
}

function streamError(item: Record<string, unknown>): ServiceError {
  return new ServiceError(String(item.message ?? item.detail), String(item.code ?? 'internal'))
}

/** JSON headers plus the bearer token when signed in. */
export async function headers(extra?: HeadersInit): Promise<HeadersInit> {
  if (gate) await gate.catch(() => undefined)
  return { 'content-type': 'application/json', ...(token ? { authorization: `Bearer ${token}` } : {}), ...extra }
}

async function failed(response: Response, path: string): Promise<ApiError> {
  const detail = await response.text().catch(() => '')
  if (response.status === 401 && token) onUnauthorized?.()
  if (response.status === 403) return new ApiError(403, 'Only the building admin can do this')
  try {
    const body = JSON.parse(detail) as { detail?: unknown; code?: unknown }
    if (typeof body.code === 'string' && typeof body.detail === 'string') return new ApiError(response.status, body.detail) // readable already
  } catch {
    // not JSON: fall through to the raw text
  }
  return new ApiError(response.status, `${response.status} ${path}: ${detail.slice(0, 200)}`)
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(BASE + path, { ...init, headers: await headers(init?.headers) })
  if (!response.ok) throw await failed(response, path)
  return response.json() as Promise<T>
}

/** GET /config: whether access mode is on, and the public Supabase values to sign in with. Never gated. */
export type AppConfig = { access_mode: false } | { access_mode: true; supabase_url: string; supabase_anon_key: string }
async function config(): Promise<AppConfig> {
  const response = await fetch(BASE + '/config')
  if (!response.ok) return { access_mode: false } // an older backend without /config: access mode is off
  return response.json() as Promise<AppConfig>
}

/** GET /me */
export type Me = { user_id: string | null; email: string | null; admin: boolean; anonymous: boolean; buildings: Record<string, string[]>; orgs?: Record<string, OrgRole> }
/** A building's listing (backend/api/access.py): on the main map, opened by link or its org's map, or members only. */
export type Listing = 'listed' | 'unlisted' | 'private'
/** GET /access/building: the rules plus what the editor offers. `public` = not private (the older flag). */
export type AccessRules = { public: boolean; listing?: Listing; org?: string | null; room_types: Record<string, string[]>; spaces: Record<string, string[]> }
export type AccessSpaceOption = { id: string; name: string; ref: string; room_type: string; floor_id: string }
export type BuildingAccess = AccessRules & { building: string; room_type_options: string[]; space_options: AccessSpaceOption[] }
/** Remembered preferences (design "Preferences"); a field left out = not set. */
export type Preferences = {
  step_free?: boolean
  min_door_width_m?: number | null
  avoid_lifts?: boolean
  avoid_room_types?: string[]
  prefer_lifts?: boolean
  fewer_doors?: boolean
  quiet?: boolean
  avoid_halls?: boolean
  simple_routes?: boolean
  language?: string
  reply_style?: 'brief' | 'detailed'
  voice?: boolean
  /** per building only: saved places (space ids) */
  favourites?: string[]
}
/** Which fields the Guide set (heard from the user) and nobody has changed since, everywhere and per building. */
export type Learned = { global: string[]; buildings: Record<string, string[]> }
export type PreferenceStore = { remember: boolean; auto_capture: boolean; global: Preferences; buildings: Record<string, Preferences>; learned?: Learned }

/** backend/api/fleet.py `Fleet.public`: a moving object; trail and mission `line` points are [x, y, floor index]. */
export type ObjectKind = 'forklift' | 'robot' | 'agv' | 'cart' | 'other'
export type ObjectAttributes = { width_m: number; step_free_only: boolean; can_use_lifts: boolean; can_use_stairs: boolean; avoid_room_types: string[] }
export type FleetObject = {
  id: string
  building: string
  name: string
  kind: ObjectKind
  attributes: ObjectAttributes
  position: { floor_id: string; floor: number | null; x: number; y: number; heading_deg: number | null; t: number; space_id: string | null } | null
  trail: [number, number, number | null][]
  mission: {
    mission_id: string
    version: number
    status: 'active' | 'done' | 'cancelled'
    to: { space_id: string; name: string }
    length_m: number
    line?: [number, number, number][]
  } | null
  /** only in the reply that created it */
  token?: string
}
export type DispatchResult = { reachable: boolean; object: FleetObject; reason?: string; to?: string; length_m?: number }

/** backend/api/live/ `LiveWorld.snapshot`: connected things, as last reported (points are plan metres + floor index). */
export type LiveKind = 'forklift' | 'agv' | 'delivery_robot' | 'cleaning_robot' | 'pallet' | 'cart' | 'pallet_jack' | 'device'
export type LiveDevice = {
  id: string
  name: string
  kind: LiveKind
  label: string
  /** "sim": the demo simulation; "device": a real device posting its position */
  source: 'sim' | 'device'
  /** how it reports: telematics, fleet manager, Wi-Fi, BLE tag, API */
  link: string
  state: string
  moving: boolean
  position: { x: number; y: number; floor: number | null; floor_id: string; heading_deg: number | null; space_id: string | null; space: string | null }
  footprint: { length_m: number; width_m: number }
  report_every_s: number
  reported_ago_s: number
  /** the world's clock at the last report: changes with every report */
  reported_at: number
  /** the last 50 m of reports, oldest first */
  trail: [number, number, number | null][]
  /** where a moving thing drives next (≈ 12 m) */
  ahead: [number, number, number | null][]
  to: string | null
  /** it cuts walks of this space for the viewer right now */
  blocking: { space: string; space_id: string; cuts: number } | null
  /** a thing left behind: seconds until it is picked up (simulated) */
  left_s: number | null
  dropped: boolean
}
export type LiveHazard = { id: string; name: string; kind: 'wet_floor'; floor: number | null; polygon: [number, number][] }
export type LiveSnapshot = {
  building: string
  t: number
  speed: number
  paused: boolean
  flavour: 'factory' | 'home' | 'other'
  simulated: boolean
  devices: LiveDevice[]
  hazards: LiveHazard[]
  /** the free width this viewer needs to pass (m): what `blocking` was judged with */
  clearance_m: number
  /** the route on this viewer's map was cut: the new route (already in the session) */
  reroute?: RouteEvent & { line?: [number, number, number][]; message: string }
  /** cut with no way round */
  alert?: { by: LiveRef[]; message: string }
  /** a detour that is no longer needed: POST /live/shorter takes it */
  suggestion?: { message: string; save_m: number }
}
export type LiveAction = 'speed' | 'pause' | 'resume' | 'drop' | 'clear' | 'block_route' | 'reset'

export type AccessMember = { user_id: string; email: string; building: string; groups: string[] }

/** Organisations and their maps (backend/api/routes/orgs.py, maps.py; docs/product/organizations.md). */
export type OrgRole = 'viewer' | 'editor' | 'owner'
export type Org = { slug: string; name: string; verified: boolean; role?: OrgRole | null }
export type OrgMember = { org: string; user_id: string; email: string; role: OrgRole | null }
export type OrgDetail = Org & { buildings: { id: string; listing: Listing }[]; members?: OrgMember[] }
export type MapVisibility = 'private' | 'link' | 'public'
export type OrgMapSummary = { slug: string; name: string; visibility: MapVisibility; buildings: number }
/** GET /maps/{slug}: the buildings this viewer may open; `token` (editors only) is the share link's key; `layout`
 * the island board as its editors arranged it (src/map/board.ts). */
export type OrgMapView = {
  slug: string
  name: string
  org: Org
  visibility: MapVisibility
  buildings: Building[]
  layout: Layout
  can_edit: boolean
  token?: string | null
}
const json = (method: string, body: unknown): RequestInit => ({ method, body: JSON.stringify(body) })
const part = encodeURIComponent

export const api = {
  config,
  me: () => request<Me>('/me'),
  accessBuilding: (building: string) => request<BuildingAccess>(`/access/building?building=${encodeURIComponent(building)}`),
  saveAccessBuilding: (building: string, rules: AccessRules) =>
    request<AccessRules & { building: string }>('/access/building', { method: 'PUT', body: JSON.stringify({ building, ...rules }) }),
  members: (building: string) => request<AccessMember[]>(`/access/members?building=${encodeURIComponent(building)}`),
  saveMember: (member: AccessMember) => request<AccessMember>('/access/members', { method: 'PUT', body: JSON.stringify(member) }),
  invite: (email: string, building: string, groups: string[], redirectTo: string) =>
    request<AccessMember & { link: string }>('/access/invite', {
      method: 'POST',
      body: JSON.stringify({ email, building, groups, redirect_to: redirectTo }),
    }),
  orgs: () => request<Org[]>('/orgs'),
  org: (slug: string) => request<OrgDetail>(`/orgs/${part(slug)}`),
  createOrg: (slug: string, name: string) => request<OrgDetail>('/orgs', json('POST', { slug, name })),
  inviteToOrg: (org: string, email: string, role: OrgRole, redirectTo: string) =>
    request<OrgMember & { link: string }>(`/orgs/${part(org)}/invite`, json('POST', { email, role, redirect_to: redirectTo })),
  setOrgMember: (member: OrgMember) => request<OrgMember>(`/orgs/${part(member.org)}/members`, json('PUT', member)),
  setOrgBuilding: (org: string, building: string, listing: Listing) =>
    request<AccessRules & { building: string }>(`/orgs/${part(org)}/buildings`, json('PUT', { building, listing })),
  orgMaps: (org: string) => request<OrgMapSummary[]>(`/orgs/${part(org)}/maps`),
  createMap: (org: string, slug: string, name: string) => request<OrgMapView>(`/orgs/${part(org)}/maps`, json('POST', { slug, name })),
  map: (slug: string, key: string | null) => request<OrgMapView>(`/maps/${part(slug)}${key ? `?k=${part(key)}` : ''}`),
  updateMap: (slug: string, change: { name?: string; visibility?: MapVisibility; layout?: Layout }) => request<OrgMapView>(`/maps/${part(slug)}`, json('PUT', change)),
  renewMapLink: (slug: string) => request<OrgMapView>(`/maps/${part(slug)}/link`, { method: 'POST' }),
  setMapBuilding: (slug: string, building: string, on: boolean) =>
    request<OrgMapView>(`/maps/${part(slug)}/buildings`, json('PUT', { building, on })),
  deleteMap: (slug: string) => request<{ deleted: string }>(`/maps/${part(slug)}`, { method: 'DELETE' }),
  myPreferences: () => request<Partial<PreferenceStore>>('/me/preferences'),
  saveMyPreferences: (store: PreferenceStore) => request<PreferenceStore>('/me/preferences', { method: 'PUT', body: JSON.stringify(store) }),
  sessionPreferences: (id: string, values: Preferences, autoCapture: boolean) =>
    request<SessionSummary>(`/sessions/${id}/preferences`, { method: 'PUT', body: JSON.stringify({ values, auto_capture: autoCapture }) }),
  live: (building: string, sessionId: string | null) =>
    request<LiveSnapshot>(`/live?building=${encodeURIComponent(building)}${sessionId ? `&session_id=${encodeURIComponent(sessionId)}` : ''}`),
  liveControl: (body: { building: string; action: LiveAction; value?: number; floor?: number; x?: number; y?: number; session_id?: string; kind?: 'pallet' | 'forklift' }) =>
    request<{ ok: boolean; speed: number; paused: boolean }>('/live/control', { method: 'POST', body: JSON.stringify(body) }),
  liveShorter: (sessionId: string) =>
    request<{ events: UiEvent[] }>('/live/shorter', { method: 'POST', body: JSON.stringify({ session_id: sessionId }) }),
  objects: (building: string) => request<FleetObject[]>(`/objects?building=${encodeURIComponent(building)}`),
  createObject: (building: string, name: string, kind: ObjectKind, attributes: ObjectAttributes) =>
    request<FleetObject>('/objects', { method: 'POST', body: JSON.stringify({ building, name, kind, attributes }) }),
  importForklifts: (building: string) =>
    request<FleetObject[]>('/objects/import-forklifts', { method: 'POST', body: JSON.stringify({ building }) }),
  deleteObject: (id: string) => request<{ deleted: string }>(`/objects/${encodeURIComponent(id)}`, { method: 'DELETE' }),
  dispatch: (id: string, destination: string) =>
    request<DispatchResult>(`/objects/${encodeURIComponent(id)}/mission`, { method: 'POST', body: JSON.stringify({ destination }) }),
  cancelMission: (id: string) => request<FleetObject>(`/objects/${encodeURIComponent(id)}/mission`, { method: 'DELETE' }),
  /** `tts`: the backend has an ElevenLabs key, so the Guide speaks with its voice (voice/tts.ts); `stt`: the user's
   * words go to ElevenLabs Scribe (voice/scribe.ts) */
  health: () => request<{ ok: boolean; llm: string; tts?: boolean; stt?: boolean }>('/health'),
  /** a single-use Scribe Realtime token and the session building's keyterms (backend/api/stt.py) */
  sttToken: (sessionId?: string) =>
    request<{ token: string; keyterms: string[] }>('/stt/token', { method: 'POST', body: JSON.stringify({ session_id: sessionId }) }),
  buildings: () => request<Building[]>('/buildings'),
  createSession: (building?: string) =>
    request<{ session_id: string; building: string }>('/sessions', {
      method: 'POST',
      body: JSON.stringify({ building }),
    }),
  session: (id: string) => request<SessionSummary>(`/sessions/${id}`),
  switchBuilding: (id: string, building: string) =>
    request<SessionSummary>(`/sessions/${id}/building`, { method: 'PUT', body: JSON.stringify({ building }) }),
  plan: (id: string) => request<Plan>(`/sessions/${id}/plan`),
  /** the "you are here" figure's room (null = taken away): the Guide routes from there without asking; `point`
   * (plan metres) is where in the room it stands, so a route's line starts there */
  setLocation: (id: string, spaceId: string | null, point: [number, number] | null = null) =>
    request<{ location: UserLocation | null }>(`/sessions/${id}/location`, { method: 'PUT', body: JSON.stringify({ space_id: spaceId, point }) }),
  /** the user ended the route in the app: the Guide no longer sees it on the map */
  endRoute: (id: string) => request<{ ended: boolean }>(`/sessions/${id}/route`, { method: 'DELETE' }),
  /** coming over from a nearby building: placed at `entrance`, the route on to `destination` as events */
  arrive: (id: string, entrance: string, destination: string, fromSession: string | null) =>
    request<{ route: { reachable: boolean; reason?: string; about_m?: number }; location: UserLocation; events: UiEvent[] }>(`/sessions/${id}/arrive`, {
      method: 'POST',
      body: JSON.stringify({ entrance, destination, from_session: fromSession }),
    }),
  chat: (id: string, message: string) =>
    request<ChatReply>('/chat', { method: 'POST', body: JSON.stringify({ session_id: id, message }) }),
  chatStream,
  createDraft: (base: string) => request<DraftState>('/drafts', { method: 'POST', body: JSON.stringify({ base }) }),
  draft: (id: string) => request<DraftState>(`/drafts/${id}`),
  draftPlan: (id: string) => request<Plan>(`/drafts/${id}/plan`),
  /** Fit the draft's building onto another OSM footprint (the "did you mean" building). */
  fitDraft: (id: string, ring: [number, number][], name: string | null) =>
    request<DraftState>(`/drafts/${id}/fit`, { method: 'POST', body: JSON.stringify({ ring, name }) }),
  /** Where the draft's building stands on the map, set by hand (scale relative to now, within 0.75–1.25). */
  setDraftLocation: (id: string, body: { origin: { lat: number; lon: number }; bearing_deg: number; scale: number }) =>
    request<DraftState>(`/drafts/${id}/location`, { method: 'PUT', body: JSON.stringify(body) }),
  /** The import's straightened plan per floor, for Edit mode's reference panel and trace ([] when none). */
  draftReferences: (id: string) => request<{ floors: FloorReference[] }>(`/drafts/${id}/references`).then((body) => body.floors),
  applyOps: (id: string, ops: Op[]) =>
    request<DraftState>(`/drafts/${id}/ops`, { method: 'POST', body: JSON.stringify({ ops }) }),
  undo: (id: string) => request<DraftState>(`/drafts/${id}/undo`, { method: 'POST' }),
  /** `map`: the organisation's map the building was made from (?map=); the new building goes onto it */
  saveDraft: (id: string, name: string, map?: string | null) =>
    request<{ building: string; issues: Issue[] }>(`/drafts/${id}/save`, { method: 'POST', body: JSON.stringify({ name, map: map ?? null }) }),
  builderStream,
  importPlans,
  /** Delete a building saved from the Edit mode or an import (user/<slug>); a version it replaced comes back. */
  deleteBuilding: (id: string) => request<{ deleted: string }>(`/buildings/${id}`, { method: 'DELETE' }),
  cancelProposal: (id: string, proposalId: string) =>
    request<{ cancelled: string }>(`/drafts/${id}/proposals/${proposalId}/cancel`, { method: 'POST' }),
  applyProposal: (id: string, proposalId: string) =>
    request<DraftState>(`/drafts/${id}/proposals/${proposalId}/apply`, { method: 'POST' }),
  events: (id: string, after: number) =>
    request<{ events: UiEvent[]; next: number }>(`/events?session_id=${encodeURIComponent(id)}&after=${after}`),
  speech,
}

/** One piece of a spoken reply as MP3 bytes in the ElevenLabs voice (POST /tts, backend/api/tts.py). */
async function speech(text: string, lang: string, signal?: AbortSignal): Promise<ArrayBuffer> {
  const response = await fetch(BASE + '/tts', {
    method: 'POST',
    headers: await headers(),
    body: JSON.stringify({ text, lang }),
    signal,
  })
  if (!response.ok) {
    const detail = await response.text().catch(() => '')
    throw new Error(`${response.status} /tts: ${detail.slice(0, 200)}`)
  }
  return response.arrayBuffer()
}

// The server sends a line at least every 10 s while a turn runs (a "ping" while the model thinks). A phone that locked
// or lost its network mid-turn never gets an error, only silence: after this long without a byte the turn has failed.
const STALL_MS = 45_000
const LOST = 'The connection to the Guide was lost. Send it again.'

/** Fetch an NDJSON stream whose reads give up after STALL_MS of silence (the request is aborted, then LOST). */
async function watchedStream(path: string, init: RequestInit) {
  const controller = new AbortController()
  let timer = 0
  const arm = () => {
    clearTimeout(timer)
    timer = window.setTimeout(() => controller.abort(), STALL_MS)
  }
  arm()
  let response: Response
  try {
    response = await fetch(BASE + path, { ...init, signal: controller.signal })
  } catch (error) {
    clearTimeout(timer)
    throw controller.signal.aborted ? new Error(LOST) : error
  }
  if (!response.ok || !response.body) {
    clearTimeout(timer)
    throw await failed(response, path)
  }
  const reader = response.body.pipeThrough(new TextDecoderStream()).getReader()
  return {
    read: async () => {
      arm()
      try {
        const chunk = await reader.read()
        if (chunk.done) clearTimeout(timer)
        return chunk
      } catch (error) {
        clearTimeout(timer)
        throw controller.signal.aborted ? new Error(LOST) : error
      }
    },
    close: () => {
      clearTimeout(timer)
      controller.abort()
    },
  }
}

/** One Guide turn over NDJSON: `onStep` fires while tools run, the promise resolves with the /chat payload. */
async function chatStream(id: string, message: string, options: ChatOptions = {}): Promise<ChatReply> {
  const reader = await watchedStream('/chat/stream', {
    method: 'POST',
    headers: await headers(),
    body: JSON.stringify({ session_id: id, message, channel: options.channel ?? 'text', heard: options.heard, selected: options.selected, photo: options.photo, route_step: options.routeStep }),
  })
  try {
    return await readChat(reader, options)
  } finally {
    reader.close()
  }
}

async function readChat(reader: { read: () => Promise<ReadableStreamReadResult<string>> }, options: ChatOptions): Promise<ChatReply> {
  let buffer = ''
  for (;;) {
    const { value, done } = await reader.read()
    buffer += value ?? ''
    const lines = buffer.split('\n')
    buffer = done ? '' : lines.pop() ?? ''
    for (const line of lines) {
      if (!line.trim()) continue
      const item = JSON.parse(line) as { type: string } & Record<string, unknown>
      if (item.type === 'step') options.onStep?.(item as unknown as ChatStep)
      else if (item.type === 'say') options.onSay?.(String(item.text))
      else if (item.type === 'reply') return item as unknown as ChatReply
      else if (item.type === 'error') throw streamError(item)
    }
    if (done) throw new Error('the reply stream ended early')
  }
}

/** One Builder turn (prompt edit) over NDJSON, parsed like `chatStream`. */
async function builderStream(draftId: string, message: string, onStep?: (step: BuilderStep) => void): Promise<BuilderReply> {
  const reader = await watchedStream(`/drafts/${draftId}/chat/stream`, {
    method: 'POST',
    headers: await headers(),
    body: JSON.stringify({ message }),
  })
  try {
    return await readBuilder(reader, onStep)
  } finally {
    reader.close()
  }
}

async function readBuilder(reader: { read: () => Promise<ReadableStreamReadResult<string>> }, onStep?: (step: BuilderStep) => void): Promise<BuilderReply> {
  let buffer = ''
  for (;;) {
    const { value, done } = await reader.read()
    buffer += value ?? ''
    const lines = buffer.split('\n')
    buffer = done ? '' : lines.pop() ?? ''
    for (const line of lines) {
      if (!line.trim()) continue
      const item = JSON.parse(line) as { type: string } & Record<string, unknown>
      if (item.type === 'step') onStep?.(item as unknown as BuilderStep)
      else if (item.type === 'reply') return item as unknown as BuilderReply
      else if (item.type === 'error') throw streamError(item)
    }
    if (done) throw new Error('the reply stream ended early')
  }
}

/** Floor plans → the Creator → a draft (POST /imports/stream, multipart). Every NDJSON line goes to `onLine`; a stream
 *  that ends without its last line (done / no_plan / error) throws. `signal` aborts the request (the backend then
 *  stops the Creator). */
async function importPlans(
  files: File[], onLine: (line: ImportLine) => void, signal?: AbortSignal, place?: ImportPlace | null,
  device?: { lat: number; lon: number } | null, draft?: string | null, levels?: number[], org?: string | null,
): Promise<void> {
  const form = new FormData()
  for (const file of files) form.append('files', file, file.name)
  if (place) form.append('place', JSON.stringify('ring' in place ? { ring: place.ring } : { point: place.point }))
  if (device) form.append('device', JSON.stringify(device))
  if (draft) form.append('draft', draft) // Edit mode's "Add a floor": into the open draft, one undo step
  if (levels) form.append('levels', JSON.stringify(levels)) // the floor of each file, as the user said
  if (org) form.append('org', org) // access mode: the organisation the new building belongs to
  const { 'content-type': _json, ...auth } = (await headers()) as Record<string, string> // the browser sets the multipart boundary
  const response = await fetch(BASE + '/imports/stream', { method: 'POST', body: form, headers: auth, signal })
  if (!response.ok || !response.body) throw await failed(response, '/imports/stream')
  const reader = response.body.pipeThrough(new TextDecoderStream()).getReader()
  let buffer = ''
  let ended = false
  for (;;) {
    const { value, done } = await reader.read()
    buffer += value ?? ''
    const lines = buffer.split('\n')
    buffer = done ? '' : lines.pop() ?? ''
    for (const line of lines) {
      if (!line.trim()) continue
      const item = JSON.parse(line) as ImportLine
      ended ||= item.type === 'done' || item.type === 'no_plan' || item.type === 'error'
      onLine(item)
    }
    if (done) {
      if (!ended) throw new Error('the import stream ended early (connection lost); try again')
      return
    }
  }
}
