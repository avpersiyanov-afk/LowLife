# -*- coding: utf-8 -*-
"""
Кнопка «Внесение изменений» (Tools.panel/ChangeClouds). Revit-часть;
чистая логика — change_clouds_core.py, настройки — change_clouds_settings.py.

Что делает:
  1. list_changes — все типы семейства облака изменений с разобранными
     шифром/номером и значениями параметров типа (окно «все изменения»).
  2. suggest_next_number — следующий номер изменения по этому шифру.
  3. create_change — новый тип по маске имени (копия первого типа семейства),
     запись шифра/номера/даты в параметры типа, вставка экземпляра на
     активный вид, запись кода (1–5), содержания и порядкового номера
     (см. next_order_on_view — своя нумерация с 1 для каждого изменения
     на листе) в параметры экземпляра.
  4. place_instance — экземпляр уже существующего типа (двойной клик по
     строке окна): параметры типа уже в нём, пишутся только код, содержание
     и порядковый номер экземпляра.

Вызывать из script.py; create_change и place_instance открывают свою
транзакцию.
"""

from lowlife.i18n import tr

from Autodesk.Revit.DB import (
    FilteredElementCollector, Family, FamilyInstance, FamilySymbol, Transaction,
    ElementId,
)

from lowlife import change_clouds_core as core
from lowlife import params
from lowlife.scs import safe_element_name


class ChangeCloudsError(Exception):
    """Ошибка с текстом для forms.alert (u'…')."""


def _error(message):
    return ChangeCloudsError(message)


def find_family(doc, family_name):
    """Семейство по имени (None, если не загружено)."""
    name = (family_name or u"").strip()
    if not name:
        return None
    for family in FilteredElementCollector(doc).OfClass(Family):
        if safe_element_name(family) == name:
            return family
    return None


def family_symbols(doc, family):
    """Все типы семейства, включая невставленные (Family → GetFamilySymbolIds)."""
    result = []
    for symbol_id in family.GetFamilySymbolIds():
        symbol = doc.GetElement(symbol_id)
        if symbol is not None:
            result.append(symbol)
    return result


def instances_of_family(doc, family):
    """Все вставленные экземпляры всех типов семейства."""
    ids = set(s.Id.IntegerValue for s in family_symbols(doc, family))
    return [inst for inst in FilteredElementCollector(doc).OfClass(FamilyInstance)
            if inst.GetTypeId().IntegerValue in ids]


def next_order_on_view(doc, view, symbol, settings):
    """Следующий порядковый номер облака на виде: максимум записанных
    значений order_param у экземпляров этого типа на виде + 1; ни у одного
    номера нет — 1. Нумерация так своя для каждого изменения (типа) на листе
    и начинается с единицы; не сбивается облаком без номера (например,
    вставленным до настройки параметров — счёт «количество облаков + 1» его
    учитывал и давал 2 первому по-настоящему пронумерованному облаку).
    """
    name = (settings.get(u"order_param") or u"").strip()
    type_key = symbol.Id.IntegerValue
    view_key = view.Id.IntegerValue
    best = 0
    if name:
        for inst in FilteredElementCollector(doc).OfClass(FamilyInstance):
            if inst.GetTypeId().IntegerValue != type_key:
                continue
            if inst.OwnerViewId is None or inst.OwnerViewId.IntegerValue != view_key:
                continue
            try:
                number = int(params.get_param_any(inst, name) or u"")
            except (TypeError, ValueError):
                continue
            if number > best:
                best = number
    return best + 1


def type_row(doc, symbol, family_name, settings):
    """Строка окна «все изменения»: имя типа + разбор + параметры типа."""
    name = safe_element_name(symbol)
    parsed = core.parse_type_name(name, family_name) or {}
    return {
        u"name": name,
        u"cipher": params.get_param_any(symbol, settings.get(u"cipher_param")) or parsed.get(u"cipher") or u"",
        u"number": params.get_param_any(symbol, settings.get(u"number_param")) or parsed.get(u"number") or u"",
        u"date": params.get_param_any(symbol, settings.get(u"date_param")) or u"",
        u"placed": None,  # заполняется в list_changes
        u"symbol_id": symbol.Id,
    }


def list_changes(doc, settings):
    """(семейство, строки типов), отсортированные по шифру и номеру.

    Семейство None — в настройках пустое имя или семейство не загружено.
    """
    family_name = (settings.get(u"family_name") or u"").strip()
    family = find_family(doc, family_name) if family_name else None
    if family is None:
        return None, []
    counts = {}
    for inst in instances_of_family(doc, family):
        key = inst.GetTypeId().IntegerValue
        counts[key] = counts.get(key, 0) + 1
    rows = []
    for symbol in family_symbols(doc, family):
        row = type_row(doc, symbol, family_name, settings)
        row[u"placed"] = counts.get(symbol.Id.IntegerValue, 0)
        rows.append(row)
    rows.sort(key=lambda r: (unicode(r.get(u"cipher") or u""),
                             _as_sort_number(r.get(u"number")),
                             unicode(r.get(u"name") or u"")))
    return family, rows


def _as_sort_number(value):
    try:
        return int(value)
    except (ValueError, TypeError):
        return 0


def suggest_next_number(rows, cipher):
    """Следующий номер изменения по шифру из строк list_changes."""
    parsed = []
    for row in rows:
        try:
            number = int(row.get(u"number"))
        except (ValueError, TypeError):
            continue
        parsed.append({u"cipher": row.get(u"cipher") or u"", u"number": number})
    return core.suggest_number(parsed, cipher)


def create_change(doc, view, settings, cipher, number, date_text, code, content, point):
    """Новый тип + экземпляр на виде. Возвращает (symbol, instance).

    Открывает свою транзакцию; кидает ChangeCloudsError с понятным текстом.
    """
    family_name = (settings.get(u"family_name") or u"").strip()
    family = find_family(doc, family_name)
    if family is None:
        raise _error(tr(u"Семейство «{}» не загружено в проект.", u"The family “{}” is not loaded in the model.").format(family_name))
    symbols = family_symbols(doc, family)
    if not symbols:
        raise _error(tr(u"В семействе «{}» нет ни одного типа — нечего копировать.",
                        u"The family “{}” has no types to duplicate.").format(family_name))

    type_name = core.build_type_name(
        settings.get(u"name_template"), family_name, cipher, number)
    existing = {safe_element_name(s) for s in symbols}
    if type_name in existing:
        raise _error(tr(u"Тип «{}» уже существует.", u"The type “{}” already exists.").format(type_name))

    tx = Transaction(doc, tr(u"Внесение изменений", u"Enter change"))
    tx.Start()
    try:
        symbol = symbols[0].Duplicate(type_name)
        try:
            if not symbol.IsActive:
                symbol.Activate()
        except Exception:
            pass
        _write_type_params(symbol, settings, cipher, number, date_text)
        instance = doc.Create.NewFamilyInstance(point, symbol, view)
        order = next_order_on_view(doc, view, symbol, settings)
        _write_instance_params(instance, settings, code, content, order)
        tx.Commit()
    except Exception as ex:
        tx.RollBack()
        raise
    return symbol, instance


def place_instance(doc, view, settings, symbol_id, code, content, point):
    """Новый экземпляр уже существующего типа (двойной клик по строке окна):
    шифр/номер/дата берутся из типа, спрашиваются код и содержание.
    Возвращает (symbol, instance).

    Открывает свою транзакцию; кидает ChangeCloudsError с понятным текстом.
    """
    family_name = (settings.get(u"family_name") or u"").strip()
    family = find_family(doc, family_name)
    if family is None:
        raise _error(tr(u"Семейство «{}» не загружено в проект.",
                        u"The family “{}” is not loaded in the model.").format(family_name))
    symbol = doc.GetElement(symbol_id)
    if symbol is None:
        raise _error(tr(u"Тип не найден в проекте — возможно, его удалили. Откройте окно заново.",
                        u"The type is not found in the model — it may have been deleted. Reopen the window."))

    order = next_order_on_view(doc, view, symbol, settings)

    tx = Transaction(doc, tr(u"Внесение изменений: экземпляр", u"Enter change: instance"))
    tx.Start()
    try:
        try:
            if not symbol.IsActive:
                symbol.Activate()
        except Exception:
            pass
        instance = doc.Create.NewFamilyInstance(point, symbol, view)
        _write_instance_params(instance, settings, code, content, order)
        tx.Commit()
    except Exception:
        tx.RollBack()
        raise
    return symbol, instance


def _write_type_params(symbol, settings, cipher, number, date_text):
    problems = []
    for key, value in ((u"cipher_param", cipher),
                       (u"number_param", number),
                       (u"date_param", date_text)):
        name = settings.get(key) or u""
        if not name:
            continue
        if not params.set_param_any(symbol, name, value):
            problems.append(name)
    if problems:
        raise _error(tr(u"Не удалось записать параметры типа: {}",
                        u"Could not write type parameters: {}").format(u", ".join(problems)))


def _write_instance_params(instance, settings, code, content, order):
    problems = []
    for key, value in ((u"code_param", code),
                       (u"content_param", content),
                       (u"order_param", order)):
        name = settings.get(key) or u""
        if not name:
            continue
        if not params.set_param_any(instance, name, value):
            problems.append(name)
    if problems:
        raise _error(tr(u"Не удалось записать параметры экземпляра: {}",
                        u"Could not write instance parameters: {}").format(u", ".join(problems)))
