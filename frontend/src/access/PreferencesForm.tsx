// Preferences UI (access mode), one sheet: "Everywhere" (the general preferences) and, over a building, a second tab
// with that building's own (overrides and favourites). Same fields in both; an override field is either "General"
// (use the general setting) or its own value. A field the Guide set from what the user said wears a "From the Guide"
// tag until it is changed by hand. Only fields the data can honour (design "Preferences").

import {
  Accessibility, AudioLines, Ban, Bookmark, DoorClosed, Languages, MessageSquareText, Ruler, Spline, Volume2, VolumeX,
  Warehouse, X,
} from 'lucide-react'
import { useState, type ComponentType, type ReactNode } from 'react'
import type { Preferences } from '../api'
import { openPanel } from './auth'
import { forgetAll, preferencesTab, setBuilding, setGlobal, update, useHere, usePreferences, type Here, type PreferencesTab } from './preferences'
import { GroupChips, Sheet } from './Sheet'

type Icon = ComponentType<{ size?: number; strokeWidth?: number }>

/** A lift (lucide has none): a car with its up and down arrows, drawn like a lucide icon; `off` strikes it through. */
const lift = (off: boolean): Icon =>
  function Lift({ size = 24, strokeWidth = 2 }) {
    return (
      <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={strokeWidth} strokeLinecap="round" strokeLinejoin="round">
        <rect x="4" y="3" width="16" height="18" rx="2" />
        <path d="m9 10 3-3 3 3M9 14l3 3 3-3" />
        {off && <path d="m2 2 20 20" />}
      </svg>
    )
  }
const Lift = lift(false)
const LiftOff = lift(true)

type Bool = 'step_free' | 'avoid_lifts' | 'prefer_lifts' | 'fewer_doors' | 'quiet' | 'avoid_halls' | 'simple_routes' | 'voice'
const ROUTE_TOGGLES: [Bool, string, string, Icon][] = [
  ['step_free', 'Step-free routes', 'No steps or stairs on the way.', Accessibility],
  ['avoid_lifts', 'Avoid lifts', '', LiftOff],
  ['prefer_lifts', 'Lifts over stairs', 'Stairs count as a longer way.', Lift],
  ['fewer_doors', 'Fewer doors', '', DoorClosed],
  ['quiet', 'Quiet route', 'Keeps away from noisy rooms.', VolumeX],
  ['avoid_halls', 'Avoid large halls', '', Warehouse],
  ['simple_routes', 'Simple routes', 'Fewer changes of room, even if a little longer.', Spline],
]
const humanise = (type: string) => type.replace(/_/g, ' ').replace(/^\w/, (c) => c.toUpperCase())
const roomType = (name: string) => name.trim().toLowerCase().replace(/\s+/g, '_')

/** A row's label: the topic's icon in the group's colour, the name (tagged when the Guide set it) and a hint. */
function Label({ icon: Glyph, children, hint, learned = false }: { icon: Icon; children: ReactNode; hint?: string; learned?: boolean }) {
  return (
    <span className="pref-label">
      <i className="pref-icon" aria-hidden="true">
        <Glyph size={20} strokeWidth={1.9} />
      </i>
      <span>
        {children}
        {learned && (
          <em className="pref-learned" title="The Guide heard this from you">
            <AudioLines size={11} strokeWidth={2.4} aria-hidden="true" />
            From the Guide
          </em>
        )}
        {hint && <small>{hint}</small>}
      </span>
    </span>
  )
}

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
function PreferenceFields({ values, onChange, inherited, roomTypes, learned = [] }: {
  values: Preferences
  onChange: (values: Preferences) => void
  /** the fields the Guide set */
  learned?: string[]
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

  const toggle = (key: Bool, label: string, hint: string, icon: Icon) =>
    override ? (
      <div className={`pref-row${values[key] ?? inherited[key] ? ' on' : ''}`} key={key}>
        <Label icon={icon} hint={hint} learned={learned.includes(key)}>{label}</Label>
        <Segmented
          label={label}
          options={[['general', `General · ${onOff(inherited[key])}`], ['on', 'On'], ['off', 'Off']]}
          value={values[key] === undefined ? 'general' : values[key] ? 'on' : 'off'}
          onChange={(choice) => set(key, choice === 'general' ? undefined : choice === 'on')}
        />
      </div>
    ) : (
      <label className={`toggle-row${values[key] ? ' on' : ''}`} key={key}>
        <Label icon={icon} hint={hint} learned={learned.includes(key)}>{label}</Label>
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
  // short own values sit at the row's end; with a "General" choice they go under the label like every override
  const short = `pref-row${override ? '' : ' inline'}`
  return (
    <>
      <h4>Routes</h4>
      <div className="pref-group tone-route">{ROUTE_TOGGLES.map(([key, label, hint, icon]) => toggle(key, label, hint, icon))}</div>

      <h4>Leave out</h4>
      <div className="pref-group tone-leave">
        <div className={`${short}${values.min_door_width_m ?? inherited?.min_door_width_m ? ' on' : ''}`}>
          <Label icon={Ruler} hint="Narrower doors are left out." learned={learned.includes('min_door_width_m')}>Narrowest door</Label>
          {ownOrGeneral('min_door_width_m', 'Narrowest door', inherited?.min_door_width_m ? `${inherited.min_door_width_m} m` : 'any', () => null)}
          {showOwn('min_door_width_m') && (
            <label className="field compact unit">
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
        <div className={`pref-row${(values.avoid_room_types ?? inherited?.avoid_room_types)?.length ? ' on' : ''}`}>
          <Label icon={Ban} learned={learned.includes('avoid_room_types')} hint={roomTypes?.length ? `Room types here: ${roomTypes.map(humanise).join(', ')}.` : 'Room types, e.g. production zone.'}>
            Rooms to avoid
          </Label>
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
      </div>

      <h4>The Guide</h4>
      <div className="pref-group tone-guide">
        <div className={`${short}${values.language ?? inherited?.language ? ' on' : ''}`}>
          <Label icon={Languages} learned={learned.includes('language')}>Language</Label>
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
        <div className={`pref-row${values.reply_style ?? inherited?.reply_style ? ' on' : ''}`}>
          <Label icon={MessageSquareText} learned={learned.includes('reply_style')}>Replies</Label>
          <Segmented
            label="Replies"
            options={override ? [['general', `General · ${inherited.reply_style ?? 'not set'}`], ['brief', 'Brief'], ['detailed', 'Detailed']] : [['general', 'Not set'], ['brief', 'Brief'], ['detailed', 'Detailed']]}
            value={values.reply_style ?? 'general'}
            onChange={(choice) => set('reply_style', choice === 'general' ? undefined : choice)}
          />
        </div>
        {toggle('voice', 'Spoken replies', '', Volume2)}
      </div>
    </>
  )
}

/** Settings corner → Preferences: the two switches, then the general preferences ("Everywhere") or, over a
 * building, that building's own. */
export function PreferencesSheet() {
  const store = usePreferences()
  const here = useHere()
  const [tab, setTab] = useState<PreferencesTab>(preferencesTab)
  const [forgetting, setForgetting] = useState(false)
  const showing = here ? tab : 'everywhere'
  return (
    <Sheet title="Preferences" onClose={() => openPanel(null)} wide>
      <section className="sheet-section prefs">
        <h4>Memory</h4>
        <div className="pref-group tone-memory">
          <label className={`toggle-row${store.remember ? ' on' : ''}`}>
            <Label icon={Bookmark} hint={store.remember ? 'Kept for your next visit, in every building.' : 'Nothing is kept; each visit starts fresh.'}>
              Remember my preferences
            </Label>
            <input type="checkbox" role="switch" checked={store.remember} onChange={(event) => update((data) => ({ ...data, remember: event.target.checked }))} />
          </label>
          <label className={`toggle-row${store.auto_capture && store.remember ? ' on' : ''}`}>
            <Label icon={AudioLines} hint="“I use a wheelchair” becomes a preference; you see what it keeps.">
              Let the Guide remember what I say
            </Label>
            <input
              type="checkbox"
              role="switch"
              checked={store.auto_capture && store.remember}
              disabled={!store.remember}
              onChange={(event) => update((data) => ({ ...data, auto_capture: event.target.checked }))}
            />
          </label>
        </div>
        {store.remember && here && (
          <div className="pref-scope" role="tablist" aria-label="Where these apply">
            <button type="button" role="tab" aria-selected={showing === 'everywhere'} onClick={() => setTab('everywhere')}>
              Everywhere
            </button>
            <button type="button" role="tab" aria-selected={showing === 'here'} onClick={() => setTab('here')}>
              <span>Only in {here.name}</span>
            </button>
          </div>
        )}
        {store.remember && showing === 'everywhere' && (
          <>
            <p className="sheet-hint pref-scope-hint">
              {here ? 'Used in every building, unless a building has its own.' : 'Used in every building. Each building can have its own too: open it and choose “Only in …” here.'}
            </p>
            <PreferenceFields values={store.global} onChange={setGlobal} learned={store.learned?.global} />
          </>
        )}
        {store.remember && showing === 'here' && here && <BuildingPreferences here={here} />}
      </section>
      {store.remember && (
        <footer className="pref-footer">
          {forgetting ? (
            <div className="confirm-row">
              <span>Forget all preferences and favourites?</span>
              <button type="button" className="sheet-quiet bordered danger" onClick={() => { forgetAll(); setForgetting(false) }}>Forget</button>
              <button type="button" className="sheet-quiet bordered" onClick={() => setForgetting(false)}>Keep</button>
            </div>
          ) : (
            <button type="button" className="sheet-quiet bordered danger" onClick={() => setForgetting(true)}>
              Forget everything
            </button>
          )}
        </footer>
      )}
    </Sheet>
  )
}

/** The building on screen: its favourites and its own preferences over the general ones. */
function BuildingPreferences({ here }: { here: Here }) {
  const store = usePreferences()
  const own = store.buildings[here.id] ?? {}
  const favourites = own.favourites ?? []
  const removeFavourite = (id: string) =>
    update((data) => ({ ...data, buildings: { ...data.buildings, [here.id]: { ...own, favourites: favourites.filter((item) => item !== id) } } }))

  return (
    <>
      <p className="sheet-hint pref-scope-hint">Only in {here.name}. “General” follows your Everywhere setting.</p>
      <h4>Favourites</h4>
      {favourites.length === 0 && <p className="sheet-hint pref-scope-hint">None yet. Ask the Guide to remember a place.</p>}
      {favourites.length > 0 && (
        <ul className="rule-list pref-group">
          {favourites.map((id) => (
            <li key={id} className="row">
              <span className="rule-name">{here.spaceName(id) ?? 'A place you can’t see now'}</span>
              <button type="button" className="hud-icon" aria-label={`Remove ${here.spaceName(id) ?? 'favourite'}`} onClick={() => removeFavourite(id)}>
                <X size={14} strokeWidth={2.2} />
              </button>
            </li>
          ))}
        </ul>
      )}
      <PreferenceFields
        values={own}
        inherited={store.global}
        roomTypes={here.roomTypes}
        learned={store.learned?.buildings[here.id]}
        onChange={(values) => setBuilding(here.id, values)}
      />
    </>
  )
}
