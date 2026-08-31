# -*- coding: utf-8 -*-
"""
Выгрузка спецификации в таблицу и обратная загрузка правок в модель.

Ключ связи строки Excel с элементом — «Revit ID» (первый столбец).
Столбцы — параметры по именам полей спецификации; на загрузке ищем
параметр по имени столбца через LookupParameter. Только параметры
экземпляра, только записываемые (не read-only, не ссылки на элементы).
"""

from Autodesk.Revit.DB import (
    Element,
    ElementId,
    FilteredElementCollector,
    StorageType,
    ViewSchedule,
)

ID_HEADER = u"Revit ID"
_ID_ALIASES = (u"revit id", u"id", u"ид", u"элемент id", u"elementid")


def schedule_name(el):
    try:
        return Element.Name.GetValue(el)
    except Exception:
        try:
            return el.Name
        except Exception:
            return u"ID {}".format(el.Id.IntegerValue)


def list_schedules(doc):
    u"""Обычные спецификации проекта (без шаблонов, ключевых и штамповых)."""
    out = []
    for v in FilteredElementCollector(doc).OfClass(ViewSchedule):
        try:
            if v.IsTemplate:
                continue
            d = v.Definition
            if d is None or d.IsKeySchedule:
                continue
            if getattr(v, "IsTitleblockRevisionSchedule", False):
                continue
        except Exception:
            continue
        out.append(v)
    out.sort(key=schedule_name)
    return out


def _visible_fields(sched):
    d = sched.Definition
    fields = []
    for i in range(d.GetFieldCount()):
        f = d.GetField(i)
        try:
            if f.IsHidden:
                continue
        except Exception:
            pass
        fields.append(f)
    return fields


def _param_to_text(p):
    if p is None or not p.HasValue:
        return u""
    st = p.StorageType
    try:
        if st == StorageType.String:
            return p.AsString() or u""
        if st == StorageType.Integer:
            vs = p.AsValueString()
            return vs if vs is not None else unicode(p.AsInteger())
        if st == StorageType.Double:
            vs = p.AsValueString()
            return vs if vs is not None else unicode(p.AsDouble())
        if st == StorageType.ElementId:
            vs = p.AsValueString()
            if vs:
                return vs
            eid = p.AsElementId()
            return unicode(eid.IntegerValue) if eid is not None else u""
    except Exception:
        return u""
    return u""


def _set_param_text(p, text):
    st = p.StorageType
    try:
        if st == StorageType.String:
            return bool(p.Set(text))
        if st == StorageType.Double:
            if p.SetValueString(text):
                return True
            alt = text.replace(u".", u",") if u"." in text else text.replace(u",", u".")
            if alt != text and p.SetValueString(alt):
                return True
            return bool(p.Set(float(text.replace(u",", u"."))))
        if st == StorageType.Integer:
            t = text.strip().lower()
            if t in (u"да", u"yes", u"true", u"истина", u"1", u"x", u"✓"):
                return bool(p.Set(1))
            if t in (u"нет", u"no", u"false", u"ложь", u"0", u"-", u""):
                return bool(p.Set(0))
            return bool(p.Set(int(round(float(text.replace(u",", u"."))))))
    except Exception:
        return False
    return False


def schedule_to_rows(doc, sched):
    u"""(rows, число_элементов, число_столбцов-параметров). rows[0] — заголовок."""
    fields = _visible_fields(sched)
    names = [f.GetName() for f in fields]

    els = (FilteredElementCollector(doc, sched.Id)
           .WhereElementIsNotElementType()
           .ToElements())

    rows = [[ID_HEADER] + names]
    for el in els:
        row = [el.Id.IntegerValue]
        for nm in names:
            row.append(_param_to_text(el.LookupParameter(nm)))
        rows.append(row)

    return rows, len(els), len(names)


def rows_to_model(doc, rows):
    u"""
    Применить правки из rows к модели. Вызывать внутри транзакции.
    Возвращает dict со счётчиками и списком ошибок.
    """
    res = {
        "changed": 0, "unchanged": 0, "no_element": 0,
        "no_param": 0, "read_only": 0, "errors": [],
    }
    if not rows:
        return res

    # первая непустая строка — заголовок
    hidx = None
    for i, r in enumerate(rows):
        if r and any(c is not None and unicode(c).strip() for c in r):
            hidx = i
            break
    if hidx is None:
        return res

    header = [unicode(c).strip() if c is not None else u"" for c in rows[hidx]]
    id_col = None
    for i, h in enumerate(header):
        if h.lower() in _ID_ALIASES:
            id_col = i
            break
    if id_col is None:
        res["errors"].append(u"Не найден столбец «{}».".format(ID_HEADER))
        return res

    for r in rows[hidx + 1:]:
        if not r or id_col >= len(r) or r[id_col] is None:
            continue
        raw_id = unicode(r[id_col]).strip().replace(u",", u".")
        if not raw_id:
            continue
        try:
            eid = int(float(raw_id))
        except ValueError:
            continue

        el = doc.GetElement(ElementId(eid))
        if el is None:
            res["no_element"] += 1
            continue

        for ci, h in enumerate(header):
            if ci == id_col or not h or ci >= len(r):
                continue
            cell = r[ci]
            if cell is None or not unicode(cell).strip():
                continue
            new_text = unicode(cell)

            p = el.LookupParameter(h)
            if p is None:
                res["no_param"] += 1
                continue
            if p.IsReadOnly or p.StorageType == StorageType.ElementId:
                res["read_only"] += 1
                continue

            if _param_to_text(p).strip() == new_text.strip():
                res["unchanged"] += 1
                continue

            if _set_param_text(p, new_text):
                res["changed"] += 1
            else:
                res["errors"].append(
                    u"ID {} / «{}»: не удалось записать «{}»".format(eid, h, new_text)
                )

    return res
