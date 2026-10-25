// Barge-in: while the Guide speaks, the mic also hears the Guide itself (speakers → mic), and speech recognition
// writes that down too. Words it hears that the Guide is not saying are the user's. Numbers are left out: the voice
// reads "3.07" as words the recogniser may write either way, and they say nothing about who is talking.

const STOP_WORDS = new Set([
  'stop', 'wait', 'enough', 'quiet', 'pause', 'halt', // en
  'stopp', 'warte', 'moment', 'genug', 'ruhe', // de
  'dur', 'bekle', 'yeter', 'sus', // tr
])
const NUMBER_WORDS = new Set([
  'oh', 'zero', 'one', 'two', 'three', 'four', 'five', 'six', 'seven', 'eight', 'nine', 'ten', 'point',
])

const words = (text: string) => text.toLowerCase().match(/[\p{L}\p{N}]+/gu) ?? []

/** The words in `heard` that are not an echo of `said` (a word counts as echo when the Guide says it, or for words of
 * four letters or more, one starting with the same three: "meters" for "metres"). Single letters ("m" for metres)
 * don't count either way. */
export function userWords(heard: string, said: string): string[] {
  const guide = new Set(words(said))
  const stems = new Set([...guide].filter((word) => word.length >= 4).map((word) => word.slice(0, 3)))
  return words(heard).filter(
    (word) =>
      word.length > 1 && !/^\p{N}+$/u.test(word) && !NUMBER_WORDS.has(word) && !guide.has(word) &&
      !(word.length >= 4 && stems.has(word.slice(0, 3))),
  )
}

/** The user's part of what was heard while the Guide spoke, given the recogniser's results in order: from the first
 * result that is mostly the user's own words (the results before it were the Guide's echo). */
export function userPart(results: string[], said: string): string {
  const first = results.findIndex((text) => {
    const own = userWords(text, said).length
    return own > 0 && own * 2 >= words(text).filter((word) => !/^\p{N}+$/u.test(word)).length
  })
  return first < 0 ? '' : results.slice(first).join(' ').trim()
}

/** What the user did while the Guide spoke: "stop" (a stop word in a short phrase: "stop", "wait please"), "talk"
 * (three or more own words that are most of what was heard: the Guide goes quiet and listens on), or nothing yet
 * (silence, echo, a misheard word of the Guide's or a stray word from the room). */
export function interruption(heard: string, said: string): 'stop' | 'talk' | null {
  const all = words(heard).filter((word) => !/^\p{N}+$/u.test(word))
  const own = userWords(heard, said)
  if (all.length <= 3 && own.some((word) => STOP_WORDS.has(word))) return 'stop'
  return own.length >= 3 && own.length * 2 >= all.length ? 'talk' : null
}
