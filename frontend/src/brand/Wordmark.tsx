// Steward's wordmark: the name drawn as a floor plan's walls (square ends, on a grid: x-height 10, ascender 14),
// raised as the cutaway's low clay walls (a light top over a darker face). The d's top wall stops short of its stem: a
// doorway, where you stand (the mark's orange ball) facing into its room. The letters live in ./wordmark.json, shared
// with scripts/brand/marks.cjs, which writes the same drawing into frontend/public/brand/wordmark*.svg.

import WORDMARK from './wordmark.json'

const { wall, depth, gap, door: doorAt, xTop, letters, colours } = WORDMARK

const placed = letters.reduce<{ x: number; d: string }[]>(
  (all, letter, i) => [...all, { x: i ? all[i - 1].x + letters[i - 1].width + gap : 0, d: letter.d }],
  [],
)
const width = placed[placed.length - 1].x + letters[letters.length - 1].width
const door = placed[placed.length - 1].x + doorAt

export function Wordmark({ dark, className }: { dark: boolean; className?: string }) {
  const tone = colours[dark ? 'dark' : 'light']
  const walls = (colour: string, dy: number) => (
    <g fill="none" stroke={colour} strokeWidth={wall} strokeLinecap="square" strokeLinejoin="miter">
      {placed.map((letter, i) => <path key={i} transform={`translate(${letter.x} ${dy})`} d={letter.d} />)}
    </g>
  )
  return (
    <svg className={className} viewBox={`-1.2 -1.2 ${width + 2.4} ${16.4 + depth}`} role="img" aria-label="Steward">
      {walls(tone.face, depth)}
      {walls(tone.top, 0)}
      {/* you: the heading cone into the d's room, a shadow at your feet, the orange ball */}
      <path d={`M${door} ${xTop + 2.4}L${door - 2.2} ${xTop + 7.4}Q${door} ${xTop + 8.2} ${door + 2.2} ${xTop + 7.4}Z`} fill={colours.you} opacity={0.3} />
      <ellipse cx={door} cy={xTop + depth + 0.2} rx={1.5} ry={0.7} fill="#000" opacity={0.35} />
      <circle cx={door} cy={xTop - 0.1} r={1.55} fill={colours.you} />
    </svg>
  )
}
