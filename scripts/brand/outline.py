"""Outline a word in a TTF as one SVG path (font units scaled to px), with GPOS pair kerning and extra tracking."""
import json, sys
from fontTools.ttLib import TTFont
from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.pens.transformPen import TransformPen

font_path, text, size, tracking_px = sys.argv[1], sys.argv[2], float(sys.argv[3]), float(sys.argv[4])
f = TTFont(font_path)
cmap, gs, hmtx = f.getBestCmap(), f.getGlyphSet(), f['hmtx']
upm = f['head'].unitsPerEm
names = [cmap[ord(c)] for c in text]

def class_of(cd, g): return cd.classDefs.get(g, 0) if cd else 0
def kern(a, b):
    total = 0
    for lookup in f['GPOS'].table.LookupList.Lookup:
        for st in lookup.SubTable:
            if lookup.LookupType == 9: st = st.ExtSubTable
            if getattr(st, 'LookupType', 2) != 2 or not hasattr(st, 'Format'): continue
            cov = st.Coverage.glyphs
            if a not in cov: continue
            if st.Format == 1:
                ps = st.PairSet[cov.index(a)]
                for r in ps.PairValueRecord:
                    if r.SecondGlyph == b and r.Value1 is not None: total += getattr(r.Value1, 'XAdvance', 0) or 0
            else:
                r = st.Class1Record[class_of(st.ClassDef1, a)].Class2Record[class_of(st.ClassDef2, b)]
                if r.Value1 is not None: total += getattr(r.Value1, 'XAdvance', 0) or 0
    return total

k = size / upm
pen = SVGPathPen(gs)
x = 0.0
kerns = []
for i, g in enumerate(names):
    gs[g].draw(TransformPen(pen, (k, 0, 0, -k, x, 0)))
    adv = hmtx[g][0] * k + tracking_px
    if i + 1 < len(names):
        kv = kern(g, names[i + 1]); kerns.append(kv); adv += kv * k
    x += adv
print(json.dumps({'d': pen.getCommands(), 'width': x - tracking_px, 'kerns': kerns,
                  'ascent': f['OS/2'].sCapHeight * k}))
