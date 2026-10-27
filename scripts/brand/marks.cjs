// Steward's mark: the app's clay cutaway in isometric — floors stacked, the top one opened up, you (orange) standing
// in a doorway facing into the front room. Large sizes use three floors (A); 32 px and below a single bold floor (C).
// Writes every SVG from this one drawing:  node scripts/brand/marks.cjs [out-dir]  (default frontend/public/brand)
// The wordmark's "Steward" is Geist 500 outlined by outline.py into steward-outline.json, so it needs no font.
// PNG app icons are rendered from icon-dark.svg / icon-small-dark.svg at 1024 px (headless Chrome) and downscaled.
const fs = require('fs'), path = require('path');

const ORANGE = '#F2602A';
const BASE = {
  d: { top: '#ECE8E1', left: '#BDB6AA', right: '#9E978B', shadow: '#8F887D' },
  l: { top: '#FFFFFF', left: '#D9D4CB', right: '#C3BCB1', shadow: '#BDB6AB' },
};
const shade = (hex, k) => '#' + [1, 3, 5].map(i => Math.round(parseInt(hex.slice(i, i + 2), 16) * k).toString(16).padStart(2, '0')).join('');
const tone = (c, k) => ({ top: shade(c.top, k), left: shade(c.left, k), right: shade(c.right, k) });
const f = n => n.toFixed(2);
const pts = a => a.map(p => f(p[0]) + ',' + f(p[1])).join(' ');
const poly = (a, fill, extra = '') => `<polygon points="${pts(a)}" fill="${fill}" ${extra}/>`;
const box = (P, x, y, z, w, d, h, c) =>
  poly([P(x + w, y, z), P(x + w, y + d, z), P(x + w, y + d, z + h), P(x + w, y, z + h)], c.right) +
  poly([P(x, y + d, z), P(x + w, y + d, z), P(x + w, y + d, z + h), P(x, y + d, z + h)], c.left) +
  poly([P(x, y, z + h), P(x + w, y, z + h), P(x + w, y + d, z + h), P(x, y + d, z + h)], c.top);

// A unit-square floor plate in isometric, fitted to the 128 box from its z range.
function fit(zmin, zmax, pad = 12) {
  const span = 128 - 2 * pad, S = Math.min(span / 1.732, span / (1 + zmax - zmin));
  const oy = 64 - S * (1 - zmin - zmax) / 2;
  return { S, P: (x, y, z) => [64 + (x - y) * S * 0.8660254, oy + (x + y) * S * 0.5 - z * S] };
}

// floors: how many plates; gap: vertical distance between plates; H: wall height; small: bolder, simpler plan.
function cutaway(t, { floors = 3, gap = 0.46, H = 0.2, small = false } = {}) {
  const c = BASE[t], T = small ? 0.16 : 0.12, W = small ? 0.12 : 0.08;
  const zmin = -(floors - 1) * gap, zmax = T + H;
  const { S, P } = fit(zmin, zmax, small ? 8 : 12);
  let s = '';
  for (let i = floors - 1; i >= 1; i--) s += box(P, 0, 0, -i * gap, 1, 1, T, tone(c, 1 - 0.13 * i));
  s += box(P, 0, 0, 0, 1, 1, T, c);
  const z = T;
  s += box(P, 0, 0, z, 1, W, H, c);
  s += box(P, 0, W, z, W, 1 - W, H, c);
  if (small) {
    s += box(P, W, 0.5, z, 0.18, W, H, c);
    s += box(P, 0.62, 0.5, z, 0.38, W, H, c);
  } else {
    s += box(P, 0.52, W, z, W, 0.42, H, c);
    s += box(P, W, 0.5, z, 0.2, W, H, c);
    s += box(P, 0.52, 0.5, z, 0.48, W, H, c);
  }
  // You stand in the doorway, facing out into the front room.
  const px = small ? 0.46 : 0.4, py = small ? 0.56 : 0.54, r = small ? 0.12 : 0.08;
  if (!small) s += poly([P(px, py, z), P(px - 0.11, 0.94, z), P(px + 0.11, 0.94, z)], ORANGE, 'opacity="0.5"');
  const [sx, sy] = P(px, py, z);
  s += `<ellipse cx="${f(sx)}" cy="${f(sy)}" rx="${f(r * S * 1.22)}" ry="${f(r * S * 0.71)}" fill="${c.shadow}"/>`;
  const [bx, by] = P(px, py, z + r);
  s += `<circle cx="${f(bx)}" cy="${f(by)}" r="${f(r * S)}" fill="${ORANGE}"/>`;
  return s;
}

const out = process.argv[2] || path.join(__dirname, '../../frontend/public/brand');
fs.mkdirSync(out, { recursive: true });
const A = { floors: 3 }, C = { floors: 1, H: 0.24, small: true };
const BLACK = '#060606', PAPER = '#ECE9E3';
const inset = (body, k) => `<g transform="translate(64 64) scale(${k}) translate(-64 -64)">${body}</g>`;
const doc = (w, h, body, size) => `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${w} ${h}"${size ? ` width="${size[0]}" height="${size[1]}"` : ''}>${body}</svg>\n`;
const write = (name, s) => fs.writeFileSync(path.join(out, name), s);

// App icons: full-bleed squares (the OS rounds the corners).
write('icon-dark.svg', doc(128, 128, `<rect width="128" height="128" fill="${BLACK}"/>` + inset(cutaway('d', A), 0.92), [1024, 1024]));
write('icon-light.svg', doc(128, 128, `<rect width="128" height="128" fill="${PAPER}"/>` + inset(cutaway('l', A), 0.92), [1024, 1024]));
write('icon-small-dark.svg', doc(128, 128, `<rect width="128" height="128" fill="${BLACK}"/>` + cutaway('d', C), [128, 128]));
// Browser tab icon: the small mark on its own rounded tile.
write('favicon.svg', doc(128, 128, `<rect width="128" height="128" rx="28" fill="${BLACK}"/>` + cutaway('d', C), [32, 32]));
// Bare marks (transparent): 'd' clay tones sit on dark grounds, 'l' on light ones.
write('mark.svg', doc(128, 128, cutaway('d', A)));
write('mark-light.svg', doc(128, 128, cutaway('l', A)));
write('mark-small.svg', doc(128, 128, cutaway('d', C)));
write('mark-small-light.svg', doc(128, 128, cutaway('l', C)));
// Wordmark: mark + name, the name outlined from Geist 500 (kerned) so it needs no font.
const name = JSON.parse(fs.readFileSync(path.join(__dirname, 'steward-outline.json'), 'utf8'));
const W = Math.ceil(140 + name.width + 12);
const word = (t, ink) => doc(W, 128, cutaway(t, A) + `<path transform="translate(140 85)" d="${name.d}" fill="${ink}"/>`);
write('wordmark.svg', word('d', '#F3F4F6'));
write('wordmark-light.svg', word('l', '#111215'));
console.log(fs.readdirSync(out).join('\n'));
