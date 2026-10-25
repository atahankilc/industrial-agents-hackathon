// What the Guide is doing, in words: tool calls from /chat/stream become a live checklist, and the finished turn
// suggests follow-ups. Both are derived from tool names/inputs and UI events only — never from guessed facts.

import type { ChatReply, ChatStep, UiEvent } from '../api'

export type Step = { key: number; label: string; tool: string; state: 'running' | 'done' | 'failed' }

const clip = (value: unknown, length = 38) => {
  const text = String(value ?? '').replace(/\s*\[[^\]]+\]/g, '').trim()
  return text.length > length ? `${text.slice(0, length - 1)}…` : text
}

export function stepLabel(step: ChatStep): string {
  if (step.kind === 'check') {
    return step.name === 'grounding' ? 'Double-checking facts against the building' : 'Re-checking with your profile'
  }
  const input = step.kind === 'tool' ? step.input : {}
  switch (step.name) {
    case 'building_overview': return 'Reading the building overview'
    case 'search': return `Searching for “${clip(input.query)}”`
    case 'locate': return `Locating ${clip(input.query)}`
    case 'count_assets': return `Counting ${clip(input.asset_type)}`
    case 'room_facts': return `Checking ${clip(input.space)}`
    case 'find_route': return input.destination ? `Finding a route to ${clip(input.destination)}` : 'Finding a route'
    case 'tour': return 'Planning a tour'
    case 'reachable_rooms': return 'Checking what you can reach'
    case 'solve': return `Measuring (${clip(String(input.kind ?? '').replace(/_/g, ' '))})`
    case 'set_profile': return 'Updating your routing profile'
    case 'propose_change': return 'Preparing a change'
    case 'apply_change': return 'Applying the change'
    case 'compare_routes': return 'Comparing routes before and after'
    case 'show_on_map': return 'Highlighting it on the map'
    case 'find_nearest': return `Finding the nearest ${clip(input.query)}`
    case 'set_my_location': return `Placing you at ${clip(input.place)}`
    case 'suggest_my_location': return 'Marking where you might be'
    case 'show_route_step': return `Going to step ${clip(input.step)}`
    case 'search_nearby_buildings': return 'Looking at the buildings nearby'
    case 'route_to_building': return 'Finding the way to the next building'
    case 'open_nearby_building': return `Opening ${clip(input.building)}`
    case 'open_edit_mode': return 'Opening the edit mode'
    case 'open_building_settings': return 'Opening the building settings'
    case 'set_preference': return 'Remembering how you like it'
    case 'send_object': return `Sending ${clip(input.object)}`
    // the Edit mode's Builder (agent/builder_tools.py)
    case 'overview': return 'Reading the building'
    case 'find': return `Looking for “${clip(input.query)}”`
    case 'space_info': return `Looking at ${clip(input.space)}`
    case 'floor_plan': return 'Reading the floor layout'
    case 'propose_edit': return 'Trying the change on a copy'
    default: return clip(step.name.replace(/_/g, ' '))
  }
}

/** Fold one streamed step into the checklist: a tool_done closes the latest running step of that tool; a
 * self-check closes everything before it (those rounds have finished). */
export function addStep(steps: Step[], step: ChatStep, key: number): Step[] {
  if (step.kind === 'tool_done') {
    const index = steps.findLastIndex((item) => item.state === 'running' && item.tool === step.name)
    return index < 0 ? steps : steps.map((item, i) => (i === index ? { ...item, state: step.ok ? 'done' : 'failed' } : item))
  }
  const before = step.kind === 'check' ? settle(steps) : steps
  return [...before, { key, label: stepLabel(step), tool: step.name, state: 'running' }]
}

/** Mark whatever is still running as done (the reply arrived). */
export const settle = (steps: Step[]): Step[] =>
  steps.map((item) => (item.state === 'running' ? { ...item, state: 'done' } : item))

// ---------- follow-ups ----------

type Context = { names: (spaceIds: string[]) => string[]; stepFree: boolean; pending: number }

/** Next questions a person would plausibly ask, from what this turn did. At most four, no duplicates. */
export function followUps(turn: ChatReply, context: Context): string[] {
  const tools = new Set(turn.tool_calls.map((call) => call.name))
  const events: UiEvent[] = turn.events
  const route = [...events].reverse().find((event) => event.type === 'route')
  const highlight = [...events].reverse().find((event) => event.type === 'highlight' && !event.style)
  const out: string[] = []

  if (route?.type === 'route') {
    if (!context.stepFree) out.push('I use a wheelchair — is it step-free?')
    if (route.legs?.some((leg) => leg.kind === 'connector' && leg.via_kind === 'lift')) out.push('The lift is out of order.')
    else if (route.legs?.some((leg) => leg.kind === 'connector')) out.push('Avoid the stairs, please.')
    out.push('Is there a shorter way?')
  } else if (highlight?.type === 'highlight') {
    const [first] = context.names(highlight.space_ids)
    if (first) out.push(`Take me to ${first}.`)
    out.push('Which one is closest to the main entrance?')
  }
  if (tools.has('propose_change') && context.pending) out.push('What changes for people in wheelchairs?')
  if (tools.has('apply_change')) out.push('Which rooms can no longer be reached?', 'Undo that change.')
  if (tools.has('set_profile') && !route) out.push('Take me from the main entrance to the nearest toilet.')
  if (tools.has('count_assets') || tools.has('locate')) out.push('Show them on the map.')
  if (!out.length) out.push('Where is the nearest printer?', 'Take me to a meeting room.')
  return [...new Set(out)].slice(0, 4)
}
