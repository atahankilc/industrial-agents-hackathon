// Preferences UI (access mode): the general sheet (menu → Preferences) and the per-building overrides (Building
// settings → My preferences). Same fields in both; an override field is either "General" (use the general setting)
// or its own value. Only fields the data can honour (design "Preferences").

import { X } from 'lucide-react'
import { useState } from 'react'
import type { Plan, Preferences } from '../api'
import { openPanel } from './auth'
import { forgetAll, update, usePreferences } from './preferences'
import { GroupChips, Sheet } from './Sheet'

type Bool = 'step_free' | 'avoid_lifts' | 'prefer_lifts' | 'fewer_doors' | 'quiet' | 'avoid_halls' | 'simple_routes' | 'voice'
const ROUTE_TOGGLES: [Bool, string, string][] = [
  ['step_free', 'Step-free routes', 'No steps or stairs on the way.'],
  ['avoid_lifts', 'Avoid lifts', ''],
  ['prefer_lifts', 'Lifts over stairs', 'Stairs count as a longer way.'],
  ['fewer_doors', 'Fewer doors', ''],
  ['quiet', 'Quiet route', 'Keeps away from noisy rooms.'],
  ['avoid_halls', 'Avoid large halls', ''],
  ['simple_routes', 'Simple routes', 'Fewer changes of room, even if a little longer.'],
]
const humanise = (type: string) => type.replace(/_/g, ' ').replace(/^\w/, (c) => c.toUpperCase())
const roomType = (name: string) => name.trim().toLowerCase().replace(/\s+/g, '_')

/** Choose one of a few options; `value` null = none chosen. */
function Segmented<T extends string>({ options, value, onChange, label }: { options: [T, string][]; value: T; onChange: (value: T) => void; label: string }) {
  return (
    <div className="segmented" role="radiogroup" aria-label={label}>
      {options.map(([key, text]) => (
        <button key={key} type="button" role="radio" aria-checked={value === key} onClick={() => onChange(key)}>
          {text}
        </button>
      ))}
    </div>
  )
}

/** The fields. Without `inherited` they edit the general preferences; with it, a building's overrides. */
function PreferenceFields({ values, onChange, inherited, roomTypes }: {
  values: Preferences
  onChange: (values: Preferences) => void
  inherited?: Preferences
  roomTypes?: string[]
}) {
  const override = inherited !== undefined
  const set = <K extends keyof Preferences>(key: K, value: Preferences[K] | undefined) => {
    const next = { ...values }
    if (value === undefined) delete next[key]
    else next[key] = value
    onChange(next)
  }
  const onOff = (on: boolean | undefined) => (on ? 'on' : 'off')

  const toggle = (key: Bool, label: string, hint: string) =>
    override ? (
      <div className="pref-row" key={key}>
        <span>
          {label}
          {hint && <small>{hint}</small>}
        </span>
        <Segmented
          label={label}
          options={[['general', `General · ${onOff(inherited[key])}`], ['on', 'On'], ['off', 'Off']]}
          value={values[key] === undefined ? 'general' : values[key] ? 'on' : 'off'}
          onChange={(choice) => set(key, choice === 'general' ? undefined : choice === 'on')}
        />
      </div>
    ) : (
      <label className="toggle-row" key={key}>
        <span>
          {label}
          {hint && <small>{hint}</small>}
        </span>
        <input type="checkbox" role="switch" checked={Boolean(values[key])} onChange={(event) => set(key, event.target.checked)} />
      </label>
    )

  /** "General" or own value, for the fields that are not on/off */
  const ownOrGeneral = (key: keyof Preferences, label: string, general: string, fresh: () => Preferences[typeof key]) =>
    override ? (
      <Segmented
        label={label}
        options={[['general', `General · ${general}`], ['own', 'Here']]}
        value={values[key] === undefined ? 'general' : 'own'}
        onChange={(choice) => set(key, choice === 'general' ? undefined : (values[key] ?? fresh()))}
      />
    ) : null
  const showOwn = (key: keyof Preferences) => !override || values[key] !== undefined

  const width = values.min_door_width_m
  return (
    <>
      <h4>Routes</h4>
      {ROUTE_TOGGLES.map(([key, label, hint]) => toggle(key, label, hint))}
      <div className="pref-row">
        <span>
          Narrowest door
          <small>Doors narrower than this are left out. Empty = any.</small>
        </span>
        {ownOrGeneral('min_door_width_m', 'Narrowest door', inherited?.min_door_width_m ? `${inherited.min_door_width_m} m` : 'any', () => null)}
        {showOwn('min_door_width_m') && (
          <label className="field compact">
            <input
              type="number"
              inputMode="decimal"
              min={0}
              max={5}
              step={0.05}
              placeholder="Any"
              value={width ?? ''}
              onChange={(event) => set('min_door_width_m', event.target.value === '' ? null : Math.max(0, Number(event.target.value)) || null)}
              aria-label="Narrowest door in metres"
            />
            <em>m</em>
          </label>
        )}
      </div>
      <div className="pref-row">
        <span>
          Rooms to avoid
          <small>{roomTypes?.length ? `Room types here: ${roomTypes.map(humanise).join(', ')}.` : 'Room types, e.g. production zone.'}</small>
        </span>
        {ownOrGeneral('avoid_room_types', 'Rooms to avoid', inherited?.avoid_room_types?.length ? inherited.avoid_room_types.map(humanise).join(', ') : 'none', () => [])}
        {showOwn('avoid_room_types') && (
          <GroupChips
            label="Room types to avoid"
            placeholder="Add a room type"
            groups={values.avoid_room_types ?? []}
            onChange={(rooms) => set('avoid_room_types', [...new Set(rooms.map(roomType))])}
          />
        )}
      </div>

      <h4>The Guide</h4>
      <div className="pref-row">
        <span>Language</span>
        {ownOrGeneral('language', 'Language', inherited?.language ?? 'as you speak', () => '')}
        {showOwn('language') && (
          <label className="field compact">
            <input
              type="text"
              value={values.language ?? ''}
              placeholder="As you speak"
              onChange={(event) => set('language', event.target.value || (override ? '' : undefined))}
              aria-label="Language"
            />
          </label>
        )}
      </div>
      <div className="pref-row">
        <span>Replies</span>
        <Segmented
          label="Replies"
          options={override ? [['general', `General · ${inherited.reply_style ?? 'not set'}`], ['brief', 'Brief'], ['detailed', 'Detailed']] : [['general', 'Not set'], ['brief', 'Brief'], ['detailed', 'Detailed']]}
          value={values.reply_style ?? 'general'}
          onChange={(choice) => set('reply_style', choice === 'general' ? undefined : choice)}
        />
      </div>
      {toggle('voice', 'Spoken replies', '')}
    </>
  )
}

/** Menu → Preferences: the general preferences and the two switches. */
export function PreferencesSheet() {
  const store = usePreferences()
  const [forgetting, setForgetting] = useState(false)
  return (
    <Sheet title="Preferences" onClose={() => openPanel(null)} wide>
      <section className="sheet-section">
        <label className="toggle-row">
          <span>
            Remember my preferences
            <small>{store.remember ? 'Kept for your next visit, in every building.' : 'Nothing is kept; each visit starts fresh.'}</small>
          </span>
          <input type="checkbox" role="switch" checked={store.remember} onChange={(event) => update((data) => ({ ...data, remember: event.target.checked }))} />
        </label>
        <label className="toggle-row">
          <span>
            Let the Guide remember what I say
            <small>“I use a wheelchair” becomes a preference.</small>
          </span>
          <input
            type="checkbox"
            role="switch"
            checked={store.auto_capture && store.remember}
            disabled={!store.remember}
            onChange={(event) => update((data) => ({ ...data, auto_capture: event.target.checked }))}
          />
        </label>
      </section>
      {store.remember && (
        <section className="sheet-section">
          <PreferenceFields values={store.global} onChange={(global) => update((data) => ({ ...data, global }))} />
          <p className="sheet-hint pref-note">A building can override these in its Building settings.</p>
          {forgetting ? (
            <div className="confirm-row">
              <span>Forget all preferences and favourites?</span>
              <button type="button" className="sheet-quiet danger" onClick={() => { forgetAll(); setForgetting(false) }}>Forget</button>
              <button type="button" className="sheet-quiet" onClick={() => setForgetting(false)}>Keep</button>
            </div>
          ) : (
            <button type="button" className="sheet-quiet" onClick={() => setForgetting(true)}>
              Forget everything
            </button>
          )}
        </section>
      )}
    </Sheet>
  )
}

/** Building settings → My preferences: this building's overrides and its favourites (for every viewer). */
export function BuildingPreferencesSection({ buildingId, plan }: { buildingId: string; plan: Plan | null }) {
  const store = usePreferences()
  const own = store.buildings[buildingId] ?? {}
  const roomTypes = plan ? [...new Set(plan.spaces.map((space) => space.room_type).filter(Boolean))].sort() : []
  const name = (id: string) => plan?.spaces.find((space) => space.id === id)?.name
  const setOwn = (values: Preferences) =>
    update((data) => ({ ...data, buildings: { ...data.buildings, [buildingId]: { ...values, favourites: own.favourites } } }))
  const favourites = own.favourites ?? []

  return (
    <section className="sheet-section">
      <h3>My preferences</h3>
      {!store.remember ? (
        <p className="sheet-hint">
          Remembering is off.{' '}
          <button type="button" className="inline-link" onClick={() => openPanel('preferences')}>Open Preferences</button>
        </p>
      ) : (
        <>
          <p className="sheet-hint">For this building only. “General” uses your general preferences.</p>
          <h4>Favourites</h4>
          {favourites.length === 0 && <p className="sheet-hint">None yet. Ask the Guide to remember a place.</p>}
          {favourites.length > 0 && (
            <ul className="rule-list">
              {favourites.map((id) => (
                <li key={id} className="row">
                  <span className="rule-name">{name(id) ?? 'A place you can’t see now'}</span>
                  <button
                    type="button"
                    className="hud-icon"
                    aria-label={`Remove ${name(id) ?? 'favourite'}`}
                    onClick={() => update((data) => ({ ...data, buildings: { ...data.buildings, [buildingId]: { ...own, favourites: favourites.filter((item) => item !== id) } } }))}
                  >
                    <X size={14} strokeWidth={2.2} />
                  </button>
                </li>
              ))}
            </ul>
          )}
          <PreferenceFields values={own} inherited={store.global} roomTypes={roomTypes} onChange={setOwn} />
        </>
      )}
    </section>
  )
}
