// What the Guide found in the buildings next to this one (search_nearby_buildings): one line per building, nearest
// first, with its distance and the first match; ask for the way there, or open it. Sits above the Guide, as a route's step card does.

import { Building2, Navigation, X } from 'lucide-react'
import type { ElsewhereEvent } from '../api'

type Item = ElsewhereEvent['buildings'][number]

export function Elsewhere({ buildings, onDirections, onOpen, onClose }: {
  buildings: Item[]
  onDirections: (item: Item) => void
  onOpen: (item: Item) => void
  onClose: () => void
}) {
  return (
    <section className="next-move elsewhere" aria-label="Found in nearby buildings">
      <header>
        <span>Not in this building — found nearby</span>
        <span className="nav">
          <button type="button" className="hud-icon" onClick={onClose} aria-label="Close">
            <X size={16} />
          </button>
        </span>
      </header>
      <ul>
        {buildings.slice(0, 3).map((item) => (
          <li key={item.building}>
            <Building2 size={18} aria-hidden="true" />
            <span className="what">
              <b>{item.name}</b>
              <small>
                {item.distance_m} m away{item.first ? ` · ${item.first}` : ''}
                {item.total > 1 ? ` (+${item.total - 1})` : ''}
              </small>
            </span>
            <span className="acts">
              <button type="button" className="go" onClick={() => onDirections(item)}>
                <Navigation size={14} />
                Directions
              </button>
              <button type="button" onClick={() => onOpen(item)}>
                Open
              </button>
            </span>
          </li>
        ))}
      </ul>
    </section>
  )
}
