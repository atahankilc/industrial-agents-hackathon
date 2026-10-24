// Typed client for the FastAPI backend (backend/app.py), reached through the Vite proxy at /api.

const BASE = import.meta.env.VITE_API_BASE ?? '/api'

export type Building = { id: string; split: string; name: string | null }

export type Space = { id: string; name: string; ref: string; floor: number; anchor: [number, number] }
export type Floor = { level: number; name: string; elevation_m: number }
export type Connector = { id: string; name: string; kind: string; spaces: number[] }

/** core/pointcloud.py export: viewer frame is y-up, building (x, y, elevation) → (x, elevation, -y), centred. */
export type PointCloud = {
  building: { id: string; name: string; source: string; attribution: string }
  kinds: string[]
  floors: Floor[]
  spaces: Space[]
  connectors?: Connector[]
  center: [number, number]
  count: number
  points: { position_cm: number[]; kind: number[]; floor: number[]; space: number[]; reveal: number[] }
  closed?: string[]
}

export type RouteEvent = {
  type: 'route'
  space_path: string[]
  element_path?: string[]
  length_m?: number
  profile?: string
  vertices?: [number, number, number, number][] // x, y, z, floor index (viewer frame)
}
export type HighlightEvent = { type: 'highlight'; space_ids: string[]; style?: 'lost_access' }
export type ChangeEvent = { type: 'change'; summary: string; targets: string[]; space_ids?: string[] }
export type UiEvent = RouteEvent | HighlightEvent | ChangeEvent

export type ChatReply = {
  reply: string
  tool_calls: { name: string; input: Record<string, unknown> }[]
  events: UiEvent[]
  ungrounded: string[]
}

export type SessionSummary = {
  session_id: string
  building: string
  profile: { step_free: boolean; min_door_width_m: number | null; avoid_lifts: boolean; summary: string }
  applied: { id: string; summary: string }[]
  pending: { id: string; summary: string }[]
  event_count: number
}

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
  points: (id: string) => request<PointCloud>(`/sessions/${id}/points`),
  chat: (id: string, message: string) =>
    request<ChatReply>('/chat', { method: 'POST', body: JSON.stringify({ session_id: id, message }) }),
  events: (id: string, after: number) =>
    request<{ events: UiEvent[]; next: number }>(`/events?session_id=${encodeURIComponent(id)}&after=${after}`),
}
