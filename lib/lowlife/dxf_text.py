# -*- coding: utf-8 -*-
"""
Текст и габарит чертежа из DXF — для кнопки «DWG → чертёжный вид»
(Tools.panel/DwgToDrafting, lowlife.dwg_transfer).

Revit API отдаёт геометрию импортированного/связанного DWG (линии, дуги,
полилинии), но НЕ его текст — поэтому текст читается из DXF-версии того же
чертежа (сохранённой рядом или сконвертированной ODA File Converter).
Здесь только разбор файла — без Revit API, работает и под Python 3 (тесты
tests/test_dxf_text.py).

    drawing = read_dxf(path)
    drawing.texts        # [DxfText] — в мировых координатах DXF (единицы чертежа)
    drawing.extents      # (minx, miny, maxx, maxy) линий/дуг/полилиний или None
    drawing.units_to_feet  # футов в единице чертежа по $INSUNITS или None

Что разбирается:
  - TEXT, ATTRIB (видимые), MTEXT — в пространстве модели (код 67 = 1 —
    пространство листа — пропускается);
  - вхождения блоков INSERT (точка вставки, масштаб, поворот, массивы
    строк/столбцов) и блоки размеров DIMENSION — рекурсивно, с пересчётом
    точки, поворота, высоты и сжатия текста; объекты слоя «0» внутри блока
    получают слой вхождения;
  - слои выключенные/замороженные (таблица LAYER) — их текст пропускается;
  - кодировка: AutoCAD 2007+ (AC1021+) — UTF-8, старее — $DWGCODEPAGE
    (ANSI_1251 и т.п.); \\U+XXXX, %%c/%%d/%%p/%%nnn, форматирование MTEXT
    (\\P — новая строка, {\\f...;}, \\H, \\S дроби и т.д.) убирается.

fit_mapping() подбирает перевод координат DXF → координаты символа импорта
Revit по габаритам геометрии (масштаб + сдвиг), с проверкой по $INSUNITS.
"""

import math
import re

try:
    _text = unicode  # noqa: F821 — IronPython/Python 2
    _chr = unichr  # noqa: F821
except NameError:  # Python 3 (тесты)
    _text = str
    _chr = chr


HALIGN_LEFT = "left"
HALIGN_CENTER = "center"
HALIGN_RIGHT = "right"
VALIGN_BOTTOM = "bottom"
VALIGN_MIDDLE = "middle"
VALIGN_TOP = "top"

# $INSUNITS → футов в единице чертежа (0 — «без единиц», тогда None).
INSUNITS_TO_FEET = {
    1: 1.0 / 12.0,          # дюймы
    2: 1.0,                 # футы
    3: 5280.0,              # мили
    4: 1.0 / 304.8,         # мм
    5: 1.0 / 30.48,         # см
    6: 1.0 / 0.3048,        # м
    7: 1000.0 / 0.3048,     # км
    8: 1.0 / 12.0e6,        # микродюймы
    9: 1.0 / 12.0e3,        # милы
    10: 3.0,                # ярды
    14: 1.0 / 3.048,        # дм
}

_CODEPAGES = {
    "ANSI_874": "cp874", "ANSI_932": "cp932", "ANSI_936": "gbk",
    "ANSI_949": "cp949", "ANSI_950": "cp950", "ANSI_1250": "cp1250",
    "ANSI_1251": "cp1251", "ANSI_1252": "cp1252", "ANSI_1253": "cp1253",
    "ANSI_1254": "cp1254", "ANSI_1255": "cp1255", "ANSI_1256": "cp1256",
    "ANSI_1257": "cp1257", "ANSI_1258": "cp1258", "DOS866": "cp866",
    "DOS850": "cp850", "DOS437": "cp437",
}
DEFAULT_CODEPAGE = "cp1251"

_MAX_DEPTH = 16
_IDENTITY = (1.0, 0.0, 0.0, 1.0, 0.0, 0.0)


class DxfText(object):
    """Одна надпись в мировых координатах DXF (единицы чертежа)."""

    def __init__(self, text, x, y, height, angle, halign=HALIGN_LEFT,
                 valign=VALIGN_BOTTOM, width_factor=1.0, layer=u"0", kind="TEXT"):
        self.text = text            # строки разделены "\n"
        self.x = x
        self.y = y
        self.height = height        # высота букв, единицы чертежа
        self.angle = angle          # поворот, радианы против часовой
        self.halign = halign
        self.valign = valign
        self.width_factor = width_factor
        self.layer = layer
        self.kind = kind            # TEXT / MTEXT / ATTRIB

    def __repr__(self):
        return "DxfText(%r, %.3f, %.3f, h=%.3f)" % (self.text, self.x, self.y, self.height)


class DxfDrawing(object):
    def __init__(self):
        self.texts = []
        self.extents = None
        self.units_to_feet = None
        self.version = u""
        self.skipped_hidden = 0     # надписей на выключенных/замороженных слоях
        self.missing_blocks = set()


# --- чтение и кодировка ------------------------------------------------------

def read_dxf(path):
    with open(path, "rb") as f:
        data = f.read()
    return parse_dxf_bytes(data)


def _header_value(head, name):
    m = re.search(re.escape(name) + r"[ \t]*\r?\n[ \t]*\d+[ \t]*\r?\n([^\r\n]*)", head)
    return m.group(1).strip() if m else None


def decode_dxf(data):
    """Байты DXF → текст в правильной кодировке."""
    if data[:18] == b"AutoCAD Binary DXF":
        raise ValueError(u"Двоичный DXF не поддерживается — сохраните DXF в текстовом (ASCII) формате.")
    if data[:3] == b"\xef\xbb\xbf":
        return data[3:].decode("utf-8", "replace")
    head = data[:200000].decode("latin-1")
    version = _header_value(head, "$ACADVER") or ""
    if version >= "AC1021":
        encodings = ["utf-8"]
    else:
        page = (_header_value(head, "$DWGCODEPAGE") or "").upper()
        encodings = [_CODEPAGES.get(page, DEFAULT_CODEPAGE)]
    encodings.append("utf-8")
    for enc in encodings:
        try:
            return data.decode(enc)
        except (UnicodeDecodeError, LookupError):
            continue
    return data.decode(DEFAULT_CODEPAGE, "replace")


def _pairs(text):
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    while lines and not lines[-1].strip():
        lines.pop()
    result = []
    for i in range(0, len(lines) - 1, 2):
        raw = lines[i].strip()
        try:
            code = int(raw)
        except ValueError:
            raise ValueError(u"Файл не похож на текстовый DXF (строка {}: «{}»).".format(i + 1, raw[:40]))
        result.append((code, lines[i + 1]))
    return result


def _group(pairs):
    """Пары кодов → [(тип, [(код, значение)])], по коду 0."""
    ents = []
    cur = None
    for code, value in pairs:
        if code == 0:
            cur = (value.strip(), [])
            ents.append(cur)
        elif cur is not None:
            cur[1].append((code, value))
    return ents


def _get(tags, code, default=None):
    for c, v in tags:
        if c == code:
            return v
    return default


def _all(tags, code):
    return [v for c, v in tags if c == code]


def _float(tags, code, default=0.0):
    v = _get(tags, code)
    if v is None:
        return default
    try:
        return float(v.strip())
    except ValueError:
        return default


def _int(tags, code, default=0):
    v = _get(tags, code)
    if v is None:
        return default
    try:
        return int(float(v.strip()))
    except ValueError:
        return default


# --- текст: спецсимволы и форматирование ---------------------------------------

_UNICODE_RE = re.compile(r"\\U\+([0-9A-Fa-f]{4})")
_PERCENT_RE = re.compile(r"%%(\d{3}|[cCdDpPuUoOkK%])")
_PERCENT_MAP = {"c": u"\u00d8", "d": u"\u00b0", "p": u"\u00b1", "%": u"%",
                "u": u"", "o": u"", "k": u""}


def _percent(m):
    code = m.group(1)
    if code.isdigit():
        return _chr(int(code))
    return _PERCENT_MAP[code.lower()]


def decode_specials(s):
    """\\U+XXXX и %%-коды AutoCAD → символы."""
    s = _UNICODE_RE.sub(lambda m: _chr(int(m.group(1), 16)), s)
    return _PERCENT_RE.sub(_percent, s)


def text_plain(raw):
    """Значение TEXT/ATTRIB → обычная строка."""
    return decode_specials(raw)


def mtext_plain(raw):
    """Содержимое MTEXT без кодов форматирования; абзацы — "\\n"."""
    s = _UNICODE_RE.sub(lambda m: _chr(int(m.group(1), 16)), raw)
    out = []
    i = 0
    n = len(s)
    while i < n:
        ch = s[i]
        if ch == "\\" and i + 1 < n:
            nx = s[i + 1]
            if nx in "PN":
                out.append(u"\n")
                i += 2
            elif nx == "~":
                out.append(u" ")
                i += 2
            elif nx in "\\{}":
                out.append(nx)
                i += 2
            elif nx in "LlOoKk":
                i += 2
            elif nx == "S":
                end = s.find(";", i + 2)
                end = n if end < 0 else end
                part = s[i + 2:end]
                for sep in ("^", "#"):
                    part = part.replace(sep, "/")
                out.append(part.replace(" /", "/").strip())
                i = end + 1
            elif nx in "ACcFfHQTWpX":
                end = s.find(";", i + 2)
                i = n if end < 0 else end + 1
            else:
                out.append(nx)
                i += 2
        elif ch in "{}":
            i += 1
        else:
            out.append(ch)
            i += 1
    return _PERCENT_RE.sub(_percent, u"".join(out))


_HEIGHT_RE = re.compile(r"\\H(\d+(?:\.\d+)?)(x?);")


def mtext_height(raw, nominal):
    """Высота MTEXT: первый \\H в начале текста переопределяет номинальную."""
    m = _HEIGHT_RE.search(raw)
    if not m or m.start() > 40:
        return nominal
    value = float(m.group(1))
    if m.group(2):
        return nominal * value if nominal > 0 else nominal
    return value if value > 0 else nominal


# --- аффинные преобразования (a, b, c, d, e, f): x' = ax+by+e, y' = cx+dy+f ----

def _apply(m, x, y):
    a, b, c, d, e, f = m
    return a * x + b * y + e, c * x + d * y + f


def _lin(m, x, y):
    a, b, c, d, _e, _f = m
    return a * x + b * y, c * x + d * y


def _compose(m, n):
    """m ∘ n — сначала n, потом m."""
    a, b, c, d, e, f = m
    a2, b2, c2, d2, e2, f2 = n
    return (a * a2 + b * c2, a * b2 + b * d2,
            c * a2 + d * c2, c * b2 + d * d2,
            a * e2 + b * f2 + e, c * e2 + d * f2 + f)


def _ocs(tags):
    """Объекты с выдавливанием (0,0,-1) — зеркальная по X система координат."""
    if _float(tags, 230, 1.0) < 0:
        return (-1.0, 0.0, 0.0, 1.0, 0.0, 0.0)
    return _IDENTITY


def _insert_matrix(tags, base, col=0, row=0):
    sx = _float(tags, 41, 1.0) or 1.0
    sy = _float(tags, 42, 1.0) or 1.0
    rot = math.radians(_float(tags, 50))
    ix, iy = _float(tags, 10), _float(tags, 20)
    # смещение ячейки массива — в повёрнутой системе вхождения
    ox = col * _float(tags, 44)
    oy = row * _float(tags, 45)
    cr, sr = math.cos(rot), math.sin(rot)
    rotate = (cr, -sr, sr, cr, ix, iy)
    # (p - base) * s + сдвиг ячейки (сдвиг не масштабируется), затем поворот и перенос
    local = (sx, 0.0, 0.0, sy, ox - sx * base[0], oy - sy * base[1])
    return _compose(rotate, local)


# --- разбор ----------------------------------------------------------------

def parse_dxf_bytes(data):
    return parse_dxf_text(decode_dxf(data))


def parse_dxf_text(text):
    ents = _group(_pairs(text))
    drawing = DxfDrawing()

    section = None
    blocks = {}
    block_name = None
    block_ents = None
    model = []
    hidden_layers = set()

    for etype, tags in ents:
        if etype == "SECTION":
            section = (_get(tags, 2) or "").strip()
            if section == "HEADER":
                _read_header(tags, drawing)
            continue
        if etype == "ENDSEC":
            section = None
            continue
        if section == "TABLES" and etype == "LAYER":
            name = (_get(tags, 2) or u"").strip()
            if _int(tags, 62, 7) < 0 or _int(tags, 70) & 1:
                hidden_layers.add(name.upper())
        elif section == "BLOCKS":
            if etype == "BLOCK":
                block_name = (_get(tags, 2) or u"").strip()
                block_ents = []
                blocks[block_name.upper()] = ((_float(tags, 10), _float(tags, 20)), block_ents)
            elif etype == "ENDBLK":
                block_name = None
                block_ents = None
            elif block_ents is not None:
                block_ents.append((etype, tags))
        elif section == "ENTITIES":
            model.append((etype, tags))

    ext = [None]
    _walk(model, _IDENTITY, 0, None, drawing, ext, blocks, hidden_layers)
    drawing.extents = ext[0]
    return drawing


def _read_header(tags, drawing):
    name = None
    for code, value in tags:
        if code == 9:
            name = value.strip()
            continue
        if name == "$ACADVER" and code == 1:
            drawing.version = value.strip()
        elif name == "$INSUNITS" and code == 70:
            try:
                drawing.units_to_feet = INSUNITS_TO_FEET.get(int(value.strip()))
            except ValueError:
                pass


def _add_ext(ext, x, y):
    e = ext[0]
    if e is None:
        ext[0] = (x, y, x, y)
    else:
        ext[0] = (min(e[0], x), min(e[1], y), max(e[2], x), max(e[3], y))


def _add_points(ext, m, pts):
    for x, y in pts:
        tx, ty = _apply(m, x, y)
        _add_ext(ext, tx, ty)


def _arc_points(cx, cy, r, a0, a1, steps=16):
    sweep = (a1 - a0) % (2 * math.pi) or 2 * math.pi
    return [(cx + r * math.cos(a0 + sweep * k / steps), cy + r * math.sin(a0 + sweep * k / steps))
            for k in range(steps + 1)]


def _walk(ents, m, depth, parent_layer, drawing, ext, blocks, hidden_layers):
    for etype, tags in ents:
        if depth == 0 and (_get(tags, 67) or "").strip() == "1":
            continue
        layer = (_get(tags, 8) or u"0").strip()
        if layer == u"0" and parent_layer:
            layer = parent_layer

        if etype in ("TEXT", "ATTRIB"):
            _add_text(drawing, etype, tags, _compose(m, _ocs(tags)), layer, hidden_layers)
        elif etype == "MTEXT":
            _add_mtext(drawing, tags, m, layer, hidden_layers)
        elif etype == "INSERT":
            if depth >= _MAX_DEPTH:
                continue
            name = (_get(tags, 2) or u"").strip()
            block = blocks.get(name.upper())
            if block is None:
                drawing.missing_blocks.add(name)
                continue
            base, inner = block
            om = _compose(m, _ocs(tags))
            cols = max(1, _int(tags, 70, 1))
            rows = max(1, _int(tags, 71, 1))
            for col in range(cols):
                for row in range(rows):
                    im = _compose(om, _insert_matrix(tags, base, col, row))
                    _walk(inner, im, depth + 1, layer, drawing, ext, blocks, hidden_layers)
        elif etype == "DIMENSION":
            name = (_get(tags, 2) or u"").strip()
            block = blocks.get(name.upper())
            if block is not None and depth < _MAX_DEPTH:
                _walk(block[1], m, depth + 1, layer, drawing, ext, blocks, hidden_layers)
        elif etype == "LINE":
            _add_points(ext, m, [(_float(tags, 10), _float(tags, 20)),
                                 (_float(tags, 11), _float(tags, 21))])
        elif etype == "LWPOLYLINE":
            xs = [float(v) for v in _all(tags, 10)]
            ys = [float(v) for v in _all(tags, 20)]
            _add_points(ext, _compose(m, _ocs(tags)), list(zip(xs, ys)))
        elif etype == "VERTEX":
            _add_points(ext, m, [(_float(tags, 10), _float(tags, 20))])
        elif etype in ("CIRCLE", "ARC"):
            cx, cy, r = _float(tags, 10), _float(tags, 20), _float(tags, 40)
            if etype == "CIRCLE":
                a0, a1 = 0.0, 2 * math.pi
            else:
                a0, a1 = math.radians(_float(tags, 50)), math.radians(_float(tags, 51))
            _add_points(ext, _compose(m, _ocs(tags)), _arc_points(cx, cy, r, a0, a1))
        elif etype == "ELLIPSE":
            cx, cy = _float(tags, 10), _float(tags, 20)
            mx, my = _float(tags, 11), _float(tags, 21)
            ratio = _float(tags, 40, 1.0)
            t0, t1 = _float(tags, 41), _float(tags, 42, 2 * math.pi)
            sweep = (t1 - t0) % (2 * math.pi) or 2 * math.pi
            pts = []
            for k in range(17):
                t = t0 + sweep * k / 16.0
                pts.append((cx + mx * math.cos(t) - my * ratio * math.sin(t),
                            cy + my * math.cos(t) + mx * ratio * math.sin(t)))
            _add_points(ext, m, pts)
        elif etype == "SPLINE":
            xs, ys = _all(tags, 11), _all(tags, 21)
            if not xs:
                xs, ys = _all(tags, 10), _all(tags, 20)
            _add_points(ext, m, [(float(x), float(y)) for x, y in zip(xs, ys)])
        elif etype in ("SOLID", "TRACE", "3DFACE"):
            pts = [(_float(tags, 10 + k), _float(tags, 20 + k)) for k in range(4)
                   if _get(tags, 10 + k) is not None]
            _add_points(ext, _compose(m, _ocs(tags)) if etype != "3DFACE" else m, pts)


def _placed(m, x, y, angle, height, width_factor):
    """Точка, поворот, высота и сжатие надписи после преобразования m."""
    px, py = _apply(m, x, y)
    dx, dy = _lin(m, math.cos(angle), math.sin(angle))
    ux, uy = _lin(m, -math.sin(angle) * height, math.cos(angle) * height)
    length = math.hypot(dx, dy)
    if length < 1e-12:
        return None
    new_height = abs(dx * uy - dy * ux) / length
    if height > 0 and new_height > 0:
        width_factor = width_factor * length / (new_height / height)
    return px, py, math.atan2(dy, dx), new_height, width_factor


_TEXT_H = {0: HALIGN_LEFT, 1: HALIGN_CENTER, 2: HALIGN_RIGHT, 3: HALIGN_LEFT,
           4: HALIGN_CENTER, 5: HALIGN_LEFT}
_TEXT_V = {0: VALIGN_BOTTOM, 1: VALIGN_BOTTOM, 2: VALIGN_MIDDLE, 3: VALIGN_TOP}


def _add_text(drawing, etype, tags, m, layer, hidden_layers):
    if etype == "ATTRIB" and _int(tags, 70) & 1:
        return
    raw = _get(tags, 1)
    if raw is None:
        return
    text = text_plain(raw).strip()
    if not text:
        return
    if layer.upper() in hidden_layers:
        drawing.skipped_hidden += 1
        return
    h_code = _int(tags, 72)
    v_code = _int(tags, 74 if etype == "ATTRIB" else 73)
    x, y = _float(tags, 10), _float(tags, 20)
    if (h_code or v_code) and h_code not in (3, 5) and _get(tags, 11) is not None:
        x, y = _float(tags, 11), _float(tags, 21)
    halign = _TEXT_H.get(h_code, HALIGN_LEFT)
    valign = VALIGN_MIDDLE if h_code == 4 else _TEXT_V.get(v_code, VALIGN_BOTTOM)
    placed = _placed(m, x, y, math.radians(_float(tags, 50)), _float(tags, 40),
                     _float(tags, 41, 1.0) or 1.0)
    if placed is None:
        return
    px, py, angle, height, wf = placed
    drawing.texts.append(DxfText(text, px, py, height, angle, halign, valign, wf, layer, etype))


_MTEXT_ATTACH = {
    1: (HALIGN_LEFT, VALIGN_TOP), 2: (HALIGN_CENTER, VALIGN_TOP), 3: (HALIGN_RIGHT, VALIGN_TOP),
    4: (HALIGN_LEFT, VALIGN_MIDDLE), 5: (HALIGN_CENTER, VALIGN_MIDDLE), 6: (HALIGN_RIGHT, VALIGN_MIDDLE),
    7: (HALIGN_LEFT, VALIGN_BOTTOM), 8: (HALIGN_CENTER, VALIGN_BOTTOM), 9: (HALIGN_RIGHT, VALIGN_BOTTOM),
}


def _add_mtext(drawing, tags, m, layer, hidden_layers):
    raw = u"".join(_all(tags, 3)) + (_get(tags, 1) or u"")
    text = u"\n".join(line.rstrip() for line in mtext_plain(raw).split(u"\n")).strip(u"\n ")
    if not text.strip():
        return
    if layer.upper() in hidden_layers:
        drawing.skipped_hidden += 1
        return
    if _get(tags, 11) is not None:
        angle = math.atan2(_float(tags, 21), _float(tags, 11))
    else:
        angle = math.radians(_float(tags, 50))
    halign, valign = _MTEXT_ATTACH.get(_int(tags, 71, 1), (HALIGN_LEFT, VALIGN_TOP))
    height = mtext_height(raw, _float(tags, 40))
    placed = _placed(m, _float(tags, 10), _float(tags, 20), angle, height, 1.0)
    if placed is None:
        return
    px, py, angle, height, wf = placed
    drawing.texts.append(DxfText(text, px, py, height, angle, halign, valign, wf, layer, "MTEXT"))


# --- совмещение с геометрией Revit -----------------------------------------

def fit_mapping(dxf_extents, revit_extents, units_to_feet=None, tol=0.02):
    """
    Перевод координат DXF в координаты символа импорта Revit (футы):
    revit = dxf * scale + (ox, oy).

    Масштаб берётся из отношения габаритов геометрии (если по X и Y он
    совпадает в пределах tol); если он в пределах 5% от $INSUNITS — точное
    значение по $INSUNITS. Сдвиг — по центрам габаритов (близкий к нулю
    обнуляется: обычно Revit сохраняет начало координат DWG).
    Если габариты несопоставимы — масштаб по $INSUNITS без сдвига.

    → (scale, ox, oy, how) или None, если не на что опереться;
    how: "extents" | "units" | "units_only".
    """
    s_fit = None
    if dxf_extents and revit_extents:
        dw = dxf_extents[2] - dxf_extents[0]
        dh = dxf_extents[3] - dxf_extents[1]
        rw = revit_extents[2] - revit_extents[0]
        rh = revit_extents[3] - revit_extents[1]
        ratios = []
        big = max(dw, dh)
        if big > 1e-9:
            if dw > big * 1e-3 and rw > 1e-12:
                ratios.append(rw / dw)
            if dh > big * 1e-3 and rh > 1e-12:
                ratios.append(rh / dh)
        if ratios and (len(ratios) == 1 or
                       abs(ratios[0] - ratios[1]) <= tol * max(ratios)):
            s_fit = sum(ratios) / len(ratios)

    if s_fit is None:
        if units_to_feet:
            return units_to_feet, 0.0, 0.0, "units_only"
        return None

    how = "extents"
    scale = s_fit
    if units_to_feet and abs(s_fit / units_to_feet - 1.0) < 0.05:
        scale = units_to_feet
        how = "units"

    dcx = (dxf_extents[0] + dxf_extents[2]) / 2.0
    dcy = (dxf_extents[1] + dxf_extents[3]) / 2.0
    rcx = (revit_extents[0] + revit_extents[2]) / 2.0
    rcy = (revit_extents[1] + revit_extents[3]) / 2.0
    ox = rcx - dcx * scale
    oy = rcy - dcy * scale
    size = max(revit_extents[2] - revit_extents[0], revit_extents[3] - revit_extents[1])
    eps = size * 1e-4 + 1e-6
    if abs(ox) < eps and abs(oy) < eps:
        ox = oy = 0.0
    return scale, ox, oy, how
