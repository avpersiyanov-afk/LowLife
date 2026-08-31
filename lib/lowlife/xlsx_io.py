# -*- coding: utf-8 -*-
"""
Мини чтение/запись .xlsx без сторонних пакетов (openpyxl не нужен).

Работает на IronPython 2 через System.IO.Compression: .xlsx — это zip с
XML внутри. Пишем строки как inlineStr, читаем и inlineStr, и обычные
sharedStrings (так Excel пересохраняет файл после правки).

Ограничения намеренные: один лист, без стилей/форматов/формул. Значения
ячеек на чтении возвращаются как unicode или None. Этого хватает для
сценария «выгрузил параметры — поправил в Excel — загрузил обратно».
"""

import re

import clr
clr.AddReference("System.IO.Compression")
try:
    clr.AddReference("System.IO.Compression.FileSystem")
except Exception:
    pass

from System.IO import FileStream, FileMode, FileAccess, StreamReader
from System.IO.Compression import ZipArchive, ZipArchiveMode
from System.Text import Encoding


_CT = (
    u'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    u'<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
    u'<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
    u'<Default Extension="xml" ContentType="application/xml"/>'
    u'<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
    u'<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
    u'</Types>'
)

_RELS = (
    u'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    u'<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
    u'<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>'
    u'</Relationships>'
)

_WB = (
    u'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    u'<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
    u'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
    u'<sheets><sheet name="{name}" sheetId="1" r:id="rId1"/></sheets></workbook>'
)

_WB_RELS = (
    u'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    u'<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
    u'<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>'
    u'</Relationships>'
)


def _col_letter(idx):
    u"""0 -> A, 25 -> Z, 26 -> AA."""
    s = u""
    n = idx + 1
    while n:
        n, r = divmod(n - 1, 26)
        s = unichr(65 + r) + s
    return s


def _col_index(letters):
    u"""A -> 0, AA -> 26."""
    n = 0
    for ch in letters:
        n = n * 26 + (ord(ch) - 64)
    return n - 1


def _esc(s):
    return (s.replace(u"&", u"&amp;").replace(u"<", u"&lt;")
            .replace(u">", u"&gt;").replace(u'"', u"&quot;"))


def _unesc(s):
    return (s.replace(u"&lt;", u"<").replace(u"&gt;", u">")
            .replace(u"&quot;", u'"').replace(u"&apos;", u"'")
            .replace(u"&#10;", u"\n").replace(u"&#13;", u"\r")
            .replace(u"&#9;", u"\t").replace(u"&amp;", u"&"))


def _sheet_xml(rows):
    out = [
        u'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
        u'<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">',
        u'<sheetData>',
    ]
    for ri, row in enumerate(rows):
        out.append(u'<row r="%d">' % (ri + 1))
        for ci, val in enumerate(row):
            if val is None or val == u"":
                continue
            ref = u"%s%d" % (_col_letter(ci), ri + 1)
            if isinstance(val, bool):
                val = u"1" if val else u"0"
            if isinstance(val, (int, long, float)):
                out.append(u'<c r="%s"><v>%s</v></c>' % (ref, unicode(val)))
            else:
                out.append(
                    u'<c r="%s" t="inlineStr"><is><t xml:space="preserve">%s</t></is></c>'
                    % (ref, _esc(unicode(val)))
                )
        out.append(u'</row>')
    out.append(u'</sheetData></worksheet>')
    return u"".join(out)


def write_xlsx(path, rows, sheet_name=u"Лист1"):
    u"""rows — список списков (str/число/None). Первая строка обычно заголовок."""
    parts = [
        (u"[Content_Types].xml", _CT),
        (u"_rels/.rels", _RELS),
        (u"xl/workbook.xml", _WB.format(name=_esc(sheet_name[:31]))),
        (u"xl/_rels/workbook.xml.rels", _WB_RELS),
        (u"xl/worksheets/sheet1.xml", _sheet_xml(rows)),
    ]
    fs = FileStream(path, FileMode.Create)
    try:
        zf = ZipArchive(fs, ZipArchiveMode.Create)
        try:
            for name, text in parts:
                entry = zf.CreateEntry(name)
                st = entry.Open()
                try:
                    data = Encoding.UTF8.GetBytes(text)
                    st.Write(data, 0, data.Length)
                finally:
                    st.Close()
        finally:
            zf.Dispose()
    finally:
        fs.Close()


def _read_entry(zf, name):
    e = zf.GetEntry(name)
    if e is None:
        return None
    st = e.Open()
    try:
        sr = StreamReader(st, Encoding.UTF8)
        try:
            return sr.ReadToEnd()
        finally:
            sr.Close()
    finally:
        st.Close()


def _shared_strings(zf):
    txt = _read_entry(zf, u"xl/sharedStrings.xml")
    if not txt:
        return []
    items = []
    for m in re.finditer(r"<si>(.*?)</si>", txt, re.S):
        chunks = re.findall(r"<t[^>]*>(.*?)</t>", m.group(1), re.S)
        items.append(_unesc(u"".join(chunks)))
    return items


def _sheet_entry_name(zf):
    if zf.GetEntry(u"xl/worksheets/sheet1.xml") is not None:
        return u"xl/worksheets/sheet1.xml"
    for e in zf.Entries:
        fn = e.FullName
        if fn.startswith(u"xl/worksheets/") and fn.endswith(u".xml"):
            return fn
    return None


def read_xlsx(path):
    u"""Вернуть список строк (список ячеек: unicode или None)."""
    fs = FileStream(path, FileMode.Open, FileAccess.Read)
    try:
        zf = ZipArchive(fs, ZipArchiveMode.Read)
        try:
            shared = _shared_strings(zf)
            sheet_name = _sheet_entry_name(zf)
            xml = _read_entry(zf, sheet_name) if sheet_name else None
        finally:
            zf.Dispose()
    finally:
        fs.Close()

    if not xml:
        return []

    rows = []
    for rm in re.finditer(r"<row\b[^>]*>(.*?)</row>", xml, re.S):
        body = rm.group(1)
        cells = {}
        maxc = -1
        for cm in re.finditer(r"<c\b([^>]*?)(?:/>|>(.*?)</c>)", body, re.S):
            attrs = cm.group(1) or u""
            inner = cm.group(2) or u""

            rmatch = re.search(r'r="([A-Z]+)\d+"', attrs)
            col = _col_index(rmatch.group(1)) if rmatch else (maxc + 1)

            tmatch = re.search(r't="([^"]+)"', attrs)
            typ = tmatch.group(1) if tmatch else None

            val = None
            if typ == u"inlineStr":
                chunks = re.findall(r"<t[^>]*>(.*?)</t>", inner, re.S)
                val = _unesc(u"".join(chunks))
            elif typ == u"s":
                vmatch = re.search(r"<v>(.*?)</v>", inner, re.S)
                if vmatch:
                    i = int(vmatch.group(1))
                    val = shared[i] if 0 <= i < len(shared) else None
            else:
                vmatch = re.search(r"<v>(.*?)</v>", inner, re.S)
                if vmatch:
                    val = _unesc(vmatch.group(1))

            cells[col] = val
            if col > maxc:
                maxc = col

        rows.append([cells.get(i) for i in range(maxc + 1)])

    return rows
