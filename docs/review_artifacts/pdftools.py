"""Decode/encode LibreOffice-produced PDF text runs (subset TrueType, hex glyph codes)."""
import re
from pypdf import PdfReader


def code_width(cmap):
    m = re.search(r'begincodespacerange(.*?)endcodespacerange', cmap, re.S)
    if m:
        h = re.search(r'<([0-9A-Fa-f]+)>', m.group(1))
        if h:
            return max(1, len(h.group(1)) // 2)
    return 1


def unicode_maps(page):
    """Return {fontname: (code->char, char->code, nbytes)} from each font's /ToUnicode CMap."""
    out = {}
    fonts = page['/Resources'].get('/Font', {})
    for name, ref in fonts.items():
        f = ref.get_object()
        tu = f.get('/ToUnicode')
        if tu is None:
            out[name] = ({}, {}, 1)
            continue
        cmap = tu.get_object().get_data().decode('latin-1')
        nb = code_width(cmap)
        w = nb * 2
        fwd = {}
        for block in re.findall(r'beginbfchar(.*?)endbfchar', cmap, re.S):
            for src, dst in re.findall(r'<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>', block):
                fwd[src.upper().zfill(w)] = ''.join(
                    chr(int(dst[i:i + 4], 16)) for i in range(0, len(dst), 4))
        for block in re.findall(r'beginbfrange(.*?)endbfrange', cmap, re.S):
            for lo, hi, dst in re.findall(
                    r'<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>', block):
                base = int(dst, 16)
                for i in range(int(lo, 16), int(hi, 16) + 1):
                    fwd['%0*X' % (w, i)] = chr(base + i - int(lo, 16))
        rev = {}
        for code, ch in fwd.items():
            if len(ch) == 1 and ch not in rev:
                rev[ch] = code
        out[name] = (fwd, rev, nb)
    return out


def decode_hex(hexstr, fwd, nb=1):
    hexstr = hexstr.upper()
    w = nb * 2
    return ''.join(fwd.get(hexstr[i:i + w], '�') for i in range(0, len(hexstr), w))


def encode_text(text, rev, nb=1):
    """Encode text to hex glyph codes. Returns (hex, missing_chars)."""
    out, missing = [], []
    for ch in text:
        c = rev.get(ch)
        if c is None:
            missing.append(ch)
        else:
            out.append(c)
    return ''.join(out), missing


RUN_RE = re.compile(
    r'BT\s*\n([\d.\-]+)\s+([\d.\-]+)\s+Td\s*/(\w+)\s+([\d.]+)\s+Tf'
    r'(\[[^\]]*\]TJ|<[0-9A-Fa-f]*>Tj)',
    re.S)


def runs(stream, maps):
    """Yield (match, x, y, font, size, text)."""
    for m in RUN_RE.finditer(stream):
        x, y, font, size, payload = m.group(1), m.group(2), m.group(3), m.group(4), m.group(5)
        fwd, _rev, nb = maps.get('/' + font, ({}, {}, 1))
        text = ''.join(decode_hex(h, fwd, nb)
                       for h in re.findall(r'<([0-9A-Fa-f]*)>', payload))
        yield m, float(x), float(y), font, float(size), text


def glyph_widths(page):
    """Return {fontname: (firstchar, [widths], missing_width)} for advance-width maths."""
    out = {}
    for name, ref in page['/Resources'].get('/Font', {}).items():
        f = ref.get_object()
        w = f.get('/Widths')
        out[name] = (
            int(f.get('/FirstChar', 0)),
            [float(x) for x in w] if w else [],
            float(f.get('/FontDescriptor', {}).get_object().get('/MissingWidth', 0))
            if f.get('/FontDescriptor') else 0.0,
        )
    return out


def text_width(hexcodes, font, size, widths, nb=1):
    """Advance width in points of a hex-encoded string."""
    first, ws, mw = widths[font]
    w = nb * 2
    total = 0.0
    for i in range(0, len(hexcodes), w):
        code = int(hexcodes[i:i + w], 16)
        idx = code - first
        total += ws[idx] if 0 <= idx < len(ws) else mw
    return total * size / 1000.0


def load(path, pno):
    r = PdfReader(path)
    page = r.pages[pno]
    return r, page, page.get_contents().get_data().decode('latin-1'), unicode_maps(page)
