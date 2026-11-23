"""Fill the author-contact and repository placeholders in the manuscript PDF.

The PDF comes from LibreOffice: text is drawn as hex-encoded subset glyph codes,
so replacement text is re-encoded against each font's /ToUnicode map.

The Caladea-Regular subset carries no underscore glyph, because the manuscript
never used one, and the repository name needs two. Rather than draw them as
rectangles - which looks right but breaks copy, search and indexing of the URL -
a real 'underscore' glyph is appended to the embedded subset and wired into the
font's cmap, /Widths and /ToUnicode. The URL then behaves like ordinary text.
"""
import io
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import pymupdf
from fontTools.ttLib import TTFont
from fontTools.pens.ttGlyphPen import TTGlyphPen
from pdftools import load, runs, glyph_widths, encode_text, text_width

SRC = 'Olaiya_2026_Smartphone_Catfish_Fingerling_Counting_Manuscript.pdf'
DST = sys.argv[1] if len(sys.argv) > 1 else 'manuscript_edited.pdf'

EMAIL = 'flourisholaiya@gmail.com'
URL = 'https://github.com/lourish789/fy_fingerling_project'
PAGE_CENTRE = 595.275 / 2

# Underscore geometry in font units (the subset is 1000 upem). Caladea's
# punctuation advances match Cambria's exactly in this document - '.', '@',
# '/', ':' and 'i' all agree to under one unit - so Cambria's underscore
# metrics are used for the added glyph.
UND_ADV = 371
UND_X0, UND_X1 = 0, 371
UND_Y0, UND_Y1 = -118, -61


# --------------------------------------------------------------------------
# font surgery
# --------------------------------------------------------------------------
def font_xrefs(doc, pno, name):
    """Return (font_xref, descriptor_xref, fontfile_xref, tounicode_xref)."""
    for xref, _ext, _typ, _base, refname, _enc in doc[pno].get_fonts(full=False):
        if refname == name:
            break
    else:
        raise SystemExit(f'font {name} not found on page {pno + 1}')

    def ref(x, key):
        kind, val = doc.xref_get_key(x, key)
        if kind != 'xref':
            raise SystemExit(f'{key} on xref {x} is {kind}, expected an indirect reference')
        return int(val.split()[0])

    fd = ref(xref, 'FontDescriptor')
    return xref, fd, ref(fd, 'FontFile2'), ref(xref, 'ToUnicode')


def add_underscore(doc, font_xref, ff_xref, tu_xref, code):
    """Append an underscore glyph to the embedded subset and wire it to `code`."""
    tt = TTFont(io.BytesIO(doc.xref_stream(ff_xref)), lazy=False)
    order = tt.getGlyphOrder()
    if 'underscore' in order:
        return

    pen = TTGlyphPen(None)
    pen.moveTo((UND_X0, UND_Y0))
    pen.lineTo((UND_X1, UND_Y0))
    pen.lineTo((UND_X1, UND_Y1))
    pen.lineTo((UND_X0, UND_Y1))
    pen.closePath()

    new_order = list(order) + ['underscore']
    tt.setGlyphOrder(new_order)
    tt['glyf'].glyphOrder = new_order
    tt['glyf'].glyphs['underscore'] = pen.glyph()
    tt['hmtx'].metrics['underscore'] = (UND_ADV, UND_X0)
    tt['maxp'].numGlyphs = len(new_order)
    for sub in tt['cmap'].tables:
        sub.cmap[code] = 'underscore'

    buf = io.BytesIO()
    tt.save(buf)
    data = buf.getvalue()
    doc.update_stream(ff_xref, data, compress=True)
    doc.xref_set_key(ff_xref, 'Length1', str(len(data)))

    # /Widths must cover the new code
    kind, widths = doc.xref_get_key(font_xref, 'Widths')
    if kind == 'xref':
        widths = doc.xref_object(int(widths.split()[0]))
    vals = [float(v) for v in re.findall(r'-?[\d.]+', widths)]
    first = int(doc.xref_get_key(font_xref, 'FirstChar')[1])
    while first + len(vals) <= code:
        vals.append(0.0)
    vals[code - first] = float(UND_ADV)
    doc.xref_set_key(font_xref, 'Widths',
                     '[' + ' '.join(f'{v:g}' for v in vals) + ']')
    doc.xref_set_key(font_xref, 'LastChar', str(max(code, first + len(vals) - 1)))

    # /ToUnicode so the glyph extracts and searches as U+005F
    cmap = doc.xref_stream(tu_xref).decode('latin-1')
    entry = f'<{code:02X}> <005F>\n'
    m = re.search(r'(\d+) beginbfchar\n', cmap)
    if not m:
        raise SystemExit('no bfchar block in /ToUnicode')
    cmap = (cmap[:m.start()] + f'{int(m.group(1)) + 1} beginbfchar\n'
            + entry + cmap[m.end():])
    doc.update_stream(tu_xref, cmap.encode('latin-1'), compress=True)


# --------------------------------------------------------------------------
# text replacement
# --------------------------------------------------------------------------
def find_run(stream, maps, y, needle):
    for m, x, ry, font, size, text in runs(stream, maps):
        if abs(ry - y) < 0.05 and needle in text:
            return m, x, ry, font, size, text
    raise SystemExit(f'run not found at y={y} containing {needle!r}')


def replace_run(doc, pno, stream, old_frag, new_frag, label):
    assert old_frag in stream, f'{label}: original fragment not found'
    new_stream = stream.replace(old_frag, new_frag, 1)
    xrefs = doc[pno].get_contents()
    assert len(xrefs) == 1, f'{label}: page has {len(xrefs)} content streams'
    doc.update_stream(xrefs[0], new_stream.encode('latin-1'))


def main():
    doc = pymupdf.open(SRC)
    report = []

    # --- add the underscore glyph before encoding anything with it ---------
    UND_CODE = 102
    fx, _fd, ffx, tux = font_xrefs(doc, 13, 'F4')
    add_underscore(doc, fx, ffx, tux, UND_CODE)

    # --- page 1: correspondence line (centred, 9 pt, grey) ----------------
    _r, page, stream, maps = load(SRC, 0)
    fwd, rev, nb = maps['/F4']
    widths = glyph_widths(page)
    m, x, y, font, size, old = find_run(stream, maps, 678.639, 'Correspondence')

    new_text = f'Correspondence: {EMAIL}'
    new_hex, missing = encode_text(new_text, rev, nb)
    assert not missing, f'page 1 missing glyphs {sorted(set(missing))!r}'
    new_w = text_width(new_hex, '/F4', size, widths, nb)
    new_x = round(PAGE_CENTRE - new_w / 2, 2)

    replace_run(doc, 0, stream, m.group(0),
                f'BT\n{new_x} {y} Td /{font} {size:g} Tf<{new_hex}>Tj', 'page 1')
    report.append(('p1', old, new_text, f'x {x} -> {new_x}, width {new_w:.1f} pt, centred'))

    # --- page 14: repository URL (left aligned, 10.5 pt, black) -----------
    _r, page14, stream14, maps14 = load(SRC, 13)
    fwd, rev, nb = maps14['/F4']
    rev = dict(rev)
    rev['_'] = f'{UND_CODE:02X}'
    w14 = glyph_widths(page14)
    w14['/F4'] = (w14['/F4'][0], w14['/F4'][1] + [0.0] * 64, w14['/F4'][2])
    w14['/F4'][1][UND_CODE - w14['/F4'][0]] = float(UND_ADV)

    m, x, y, font, size, old = find_run(stream14, maps14, 468.739, 'repository URL')
    new_text = f'available at {URL}.'
    new_hex, missing = encode_text(new_text, rev, nb)
    assert not missing, f'page 14 missing glyphs {sorted(set(missing))!r}'
    new_w = text_width(new_hex, '/F4', size, w14, nb)
    column = 538.95 - x
    assert new_w < column, f'URL line is {new_w:.1f} pt, wider than the {column:.1f} pt column'

    replace_run(doc, 13, stream14, m.group(0),
                f'BT\n{x} {y} Td /{font} {size:g} Tf<{new_hex}>Tj', 'page 14')
    report.append(('p14', old, new_text, f'width {new_w:.1f} pt of {column:.1f} pt column'))

    doc.save(DST, garbage=3, deflate=True)
    doc.close()

    for pg, before, after, note in report:
        print(f'[{pg}] {before!r}\n  ->  {after!r}\n      {note}\n')
    print('written', DST)


if __name__ == '__main__':
    main()
