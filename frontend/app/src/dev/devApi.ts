// Client for the backend's dev endpoints (backend/devtools.py): run one Guide tool directly, read the
// session's routing state, reset it. Same /api base as src/api.ts.

import { headers, type SessionSummary, type UiEvent } from '../api'

const BASE = import.meta.env.VITE_API_BASE ?? '/api'

/** Route events from the dev backend carry the line to draw: [[x, y, floor_index], …] in plan metres. */
export type DevEvent = UiEvent & { line?: [number, number, number][] }
export type ToolReply = { result: Record<string, unknown> & { error?: string }; events: DevEvent[] }
export type ToolDefinition = { name: string; description: string; input_schema: Record<string, unknown> }
export type DevState = SessionSummary & {
  profile_fields: { step_free: boolean; min_door_width_m: number | null; avoid_lifts: boolean; forklift: boolean; preset: string }
  closed: string[]
  profile_closed: string[]
  entrance_space: string | null
  unreachable: string[] | null
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(BASE + path, { ...init, headers: await headers(init?.headers) })
  if (!response.ok) {
    const detail = await response.text().catch(() => '')
    throw new Error(`${response.status} ${path}: ${detail.slice(0, 200)}`)
  }
  return response.json() as Promise<T>
}

export const devApi = {
  tool: (id: string, name: string, args: Record<string, unknown> = {}) =>
    request<ToolReply>(`/dev/sessions/${id}/tool`, { method: 'POST', body: JSON.stringify({ name, arguments: args }) }),
  tools: () => request<ToolDefinition[]>('/dev/tools'),
  state: (id: string) => request<DevState>(`/dev/sessions/${id}/state`),
  reset: (id: string) => request<SessionSummary>(`/dev/sessions/${id}/reset`, { method: 'POST' }),
}
