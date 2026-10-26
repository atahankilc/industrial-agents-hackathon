// What the Guide's card shows in the Edit mode in place of the room card (building/Guide.tsx `card`): the Builder's
// proposal waiting for Apply / Cancel, else the Inspector for the selection or the active tool (the Access tool:
// src/access/AccessCard.tsx, who may enter the room picked). Nothing = the
// conversation with the Builder (captions, trail, Core) shows.

import { Check, X } from 'lucide-react'
import { AccessCard } from '../access/AccessCard'
import type { AccessRulesState } from '../access/useAccessRules'
import { Inspector } from './Inspector'
import type { Draft } from './useDraft'

/** The Builder writes a little markdown: keep its lines, drop the emphasis and the list dashes' asterisks. */
const plain = (text: string) =>
  text.replace(/\*\*(.+?)\*\*/g, '$1').replace(/^\s*[-*]\s+/gm, '• ').split(/\n+/).map((line) => line.trim()).filter(Boolean)

export function EditCard({ draft, access, onSettings }: { draft: Draft; access: AccessRulesState; onSettings: () => void }) {
  const { state, proposal, selected, tool, busy } = draft
  if (!state) return null
  if (proposal) {
    // what the Builder said with it (its explanation or caveats), unless it only repeats the summary
    const said = draft.messages.findLast((message) => message.role === 'guide' && !message.live)?.text.trim()
    const words = said && said !== proposal.summary.trim() ? plain(said) : null
    return (
      <article className="place-card edit-card proposal">
        <p className="who speaking">Builder · proposal</p>
        <h2>{proposal.summary}</h2>
        {words && <div className="edit-said">{words.map((line, index) => <p key={index}>{line}</p>)}</div>}
        {proposal.effect.changed_spaces.map((item) => (
          <p key={item.id} className="inspector-facts">{item.name}: {item.area_before} → {item.area_after} m²</p>
        ))}
        {proposal.new_problems.map((problem, index) => <p key={index} className="edit-problem">{problem}</p>)}
        <p className="inspector-note">Drawn dashed on the plan. Nothing changes until you apply it — or say “yes”.</p>
        <div className="row">
          <button type="button" className="edit-card-button" onClick={draft.cancel} disabled={busy}><X size={14} /> Cancel</button>
          <button type="button" className="edit-primary" onClick={() => void draft.apply()} disabled={busy}>
            <Check size={14} /> {proposal.new_problems.length ? 'Apply anyway' : 'Apply'}
          </button>
        </div>
      </article>
    )
  }
  if (!selected && tool === 'select') return null
  const close = (
    <button type="button" className="hud-icon edit-card-close" aria-label="Close"
      onClick={() => (tool === 'select' || (tool === 'access' && selected) ? draft.setSelected(null) : draft.setTool('select'))}>
      <X size={16} />
    </button>
  )
  if (tool === 'access') {
    const space = selected?.kind === 'space' ? state.building.spaces.find((item) => item.id === selected.id) : undefined
    return (
      <article className="place-card edit-card">
        {close}
        <AccessCard key={space?.id ?? ''} access={access} spaceId={space?.id ?? null} spaceName={space?.name ?? null} onSettings={onSettings} />
      </article>
    )
  }
  return (
    <article className="place-card edit-card">
      {close}
      <Inspector
        building={state.building}
        selected={selected}
        tool={tool}
        preset={draft.preset}
        onPreset={draft.setPreset}
        onOps={draft.onOps}
        onSelect={draft.setSelected}
        busy={busy}
        revision={draft.revision}
      />
    </article>
  )
}
