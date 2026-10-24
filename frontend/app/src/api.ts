// Typed client for the FastAPI backend (backend/app.py), reached through the Vite proxy at /api.

const BASE = import.meta.env.VITE_API_BASE ?? '/api'

/** `location`: real position (centre of the OSM outline) for the kit's OpenStreetMap buildings, else null;
 * `origin` is where the building's own metres start (x east, y north from it), which puts the model on the map;
 * `outline` its footprint, which marks its block on the map. */
export type Building = {
  id: string
  split: string
  name: string | null
  location: {
    lat: number
    lon: number
    address: string | null
    origin?: { lat: number; lon: number }
    /** footprint rings, [lon, lat] */
    outline?: [number, number][][]
    /** from the lowest floor to the top of the highest */
    height_m?: number
  } | null
}

/** core/floorplan.py export: building metres (x right, y up). `center` centres the y-up scene:
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
/** A solid wall piece, outline first then holes (core/floorplan.py `wall_solids`). */
export type PlanWall = { kind: 'exterior' | 'structural' | 'partition'; rings: [number, number][][] }
export type Plan = {
  building: { id: string; name: string; source: string; attribution: string }
  floors: PlanFloor[]
  bounds: [number, number, number, number]
  center: [number, number]
  spaces: PlanSpace[]
  walls: [number, number, number, number][][]
  wall_solids: PlanWall[][]
  /** per floor: the rooms with the wall gaps closed, polygons as [outer, ...holes] (core/floorplan.py `outline`) */
  outlines?: [number, number][][][][]
  /** per floor: where two spaces overlap, diagonal stripes owned alternately by each (core/floorplan.py `overlaps`) */
  overlaps?: { space: string; rings: [number, number][][] }[][]
  openings: PlanOpening[]
  connectors: PlanConnector[]
  assets: PlanAsset[]
  closed: string[]
}

/** core/directions.py: one turn-by-turn leg; `turn` is made at the start of the leg, relative to the way you face. */
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

/** One followable step as the Guide says it (core/directions.guidance): the turn where a person makes it, rounded
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
}
export type HighlightEvent = { type: 'highlight'; space_ids: string[]; style?: 'lost_access' }
export type ChangeEvent = { type: 'change'; summary: string; targets: string[]; space_ids?: string[] }
export type UiEvent = RouteEvent | HighlightEvent | ChangeEvent

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

export type ChatOptions = { channel?: 'text' | 'voice'; photo?: string; onStep?: (step: ChatStep) => void }

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
/** core/validate.py issue; warnings are issues the original building already had. */
export type Issue = { severity: 'error' | 'warning'; code: string; message: string; ids: string[] }
export type DraftState = { draft: { id: string; base: string; name: string; steps: number }; building: BuildingJson; issues: Issue[] }
/** core/edits.py op: {"op": name, ...arguments}. */
export type Op = { op: string; [key: string]: unknown }
/** An open Builder proposal (agent/builder_tools.py); `building` is the draft as it would be after the ops. */
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
export type BuilderStep = { kind: 'tool' | 'tool_done' | 'check'; name: string; input?: Record<string, unknown>; ok?: boolean }

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(BASE + path, {
    ...init,
    headers: { 'content-type': 'application/json', ...init?.headers },
  })
  if (!response.ok) {
    const detail = await response.text().catch(() => '')
    throw new Error(`${response.status} ${path}: ${detail.slice(0, 200)}`)
  }
  return response.json() as Promise<T>
}

export const api = {
  health: () => request<{ ok: boolean; llm: string }>('/health'),
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
  chat: (id: string, message: string) =>
    request<ChatReply>('/chat', { method: 'POST', body: JSON.stringify({ session_id: id, message }) }),
  chatStream,
  createDraft: (base: string) => request<DraftState>('/drafts', { method: 'POST', body: JSON.stringify({ base }) }),
  draft: (id: string) => request<DraftState>(`/drafts/${id}`),
  draftPlan: (id: string) => request<Plan>(`/drafts/${id}/plan`),
  applyOps: (id: string, ops: Op[]) =>
    request<DraftState>(`/drafts/${id}/ops`, { method: 'POST', body: JSON.stringify({ ops }) }),
  undo: (id: string) => request<DraftState>(`/drafts/${id}/undo`, { method: 'POST' }),
  saveDraft: (id: string, name: string) =>
    request<{ building: string; issues: Issue[] }>(`/drafts/${id}/save`, { method: 'POST', body: JSON.stringify({ name }) }),
  builderStream,
  cancelProposal: (id: string, proposalId: string) =>
    request<{ cancelled: string }>(`/drafts/${id}/proposals/${proposalId}/cancel`, { method: 'POST' }),
  applyProposal: (id: string, proposalId: string) =>
    request<DraftState>(`/drafts/${id}/proposals/${proposalId}/apply`, { method: 'POST' }),
  events: (id: string, after: number) =>
    request<{ events: UiEvent[]; next: number }>(`/events?session_id=${encodeURIComponent(id)}&after=${after}`),
}

/** One Guide turn over NDJSON: `onStep` fires while tools run, the promise resolves with the /chat payload. */
async function chatStream(id: string, message: string, options: ChatOptions = {}): Promise<ChatReply> {
  const response = await fetch(BASE + '/chat/stream', {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ session_id: id, message, channel: options.channel ?? 'text', photo: options.photo }),
  })
  if (!response.ok || !response.body) {
    const detail = await response.text().catch(() => '')
    throw new Error(`${response.status} /chat/stream: ${detail.slice(0, 200)}`)
  }
  const reader = response.body.pipeThrough(new TextDecoderStream()).getReader()
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
      else if (item.type === 'reply') return item as unknown as ChatReply
      else if (item.type === 'error') throw new Error(String(item.detail))
    }
    if (done) throw new Error('the reply stream ended early')
  }
}

/** One Builder turn (prompt edit) over NDJSON, parsed like `chatStream`. */
async function builderStream(draftId: string, message: string, onStep?: (step: BuilderStep) => void): Promise<BuilderReply> {
  const response = await fetch(`${BASE}/drafts/${draftId}/chat/stream`, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ message }),
  })
  if (!response.ok || !response.body) {
    const detail = await response.text().catch(() => '')
    throw new Error(`${response.status} /drafts/chat/stream: ${detail.slice(0, 200)}`)
  }
  const reader = response.body.pipeThrough(new TextDecoderStream()).getReader()
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
      else if (item.type === 'error') throw new Error(String(item.detail))
    }
    if (done) throw new Error('the reply stream ended early')
  }
}
