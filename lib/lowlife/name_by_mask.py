# -*- coding: utf-8 -*-
"""
Запись имени по маске из двух параметров элемента (CircuitsGeneric.panel):

- «Имя нагрузки» — для выбранных семейств находит их электрические цепи и
  пишет в параметр цепи из настроек (пусто — штатное «Имя нагрузки»)
  текст по маске из двух параметров семейства;
- «Имя панели» — выбранному электрооборудованию пишет в штатное «Имя
  панели» текст по маске из двух его параметров.

Сама маска — name_mask (чистая логика, есть тесты), настройки —
name_by_mask_settings. Функции write_* меняют модель — вызывать внутри
транзакции.
"""

try:
    unicode  # noqa: F821 — IronPython/Python 2
except NameError:  # Python 3
    unicode = str


from Autodesk.Revit.DB import BuiltInCategory, BuiltInParameter, StorageType

from lowlife.circuit_builtins import set_circuit_load_name, set_panel_name
from lowlife.name_mask import mask_tokens, missing_tokens, render_mask
from lowlife.params import get_param_any, param_to_text, set_param_text
from lowlife.scs_circuits import clean_text_value
from lowlife.selection import pick_model_elements


class Result(object):
    """Итог записи: сколько записано / уже было так, и что пропущено."""

    def __init__(self):
        self.written = 0
        self.unchanged = 0
        self.skipped = []   # строки для отчёта

    def skip(self, text):
        self.skipped.append(text)


def selected_or_picked(uidoc, doc, prompt, keep=None):
    """
    Выделенные до запуска элементы (подходящие под keep), а если таких
    нет — выбор рамкой/кликами (pick_model_elements; Esc — выход из
    скрипта). Возвращает (элементы, сколько отброшено keep).
    """
    els = []
    try:
        els = [doc.GetElement(i) for i in uidoc.Selection.GetElementIds()]
    except Exception:
        pass
    els = [el for el in els if el is not None]
    if keep is not None:
        els = [el for el in els if keep(el)]
    if not els:
        els = pick_model_elements(uidoc, doc, prompt)
    if keep is None:
        return els, 0
    kept = [el for el in els if keep(el)]
    return kept, len(els) - len(kept)


def element_label(el):
    """«Семейство: Тип [id]» для отчёта."""
    name = u""
    try:
        p = el.get_Parameter(BuiltInParameter.ELEM_FAMILY_AND_TYPE_PARAM)
        name = (p.AsValueString() or u"") if p is not None else u""
    except Exception:
        pass
    try:
        eid = unicode(el.Id.IntegerValue)
    except Exception:
        eid = u"?"
    return u"{} [{}]".format(name, eid) if name else u"[{}]".format(eid)


def source_value(doc, el, name):
    """Значение параметра name текстом: сначала экземпляр, затем тип; None — пусто."""
    value = clean_text_value(get_param_any(el, name))
    if value is None:
        try:
            type_el = doc.GetElement(el.GetTypeId())
        except Exception:
            type_el = None
        if type_el is not None:
            value = clean_text_value(get_param_any(type_el, name))
    return value


def check_mask_params(mask, first_param, second_param):
    """None — для каждого маркера маски задан параметр, иначе текст ошибки."""
    names = {1: first_param, 2: second_param}
    lacking = [i for i in mask_tokens(mask) if not (names.get(i) or u"").strip()]
    if lacking:
        return u"В маске есть {{{}}}, но параметр для него в настройках не указан.".format(lacking[0])
    return None


def name_for(doc, el, first_param, second_param, mask):
    """
    (текст по маске, None) или (None, причина пропуска) — если у элемента
    нет значения какого-то параметра из маски.
    """
    names = {1: first_param, 2: second_param}
    values = {}
    for i in mask_tokens(mask):
        values[i] = source_value(doc, el, names[i])
    lacking = missing_tokens(mask, values)
    if lacking:
        return None, u"не заполнен параметр «{}»".format(
            u"», «".join(names[i] for i in lacking))
    text = render_mask(mask, values)
    if not text:
        return None, u"по маске получилась пустая строка"
    return text, None


# --- «Имя нагрузки» -----------------------------------------------------------

def device_circuits(el):
    """Электрические цепи, в которые элемент входит как нагрузка (не как их панель)."""
    mep = getattr(el, "MEPModel", None)
    if mep is None:
        return []
    try:
        systems = list(mep.GetElectricalSystems() or [])
    except Exception:
        return []
    result = []
    for system in systems:
        try:
            base = system.BaseEquipment
            if base is not None and base.Id == el.Id:
                continue
        except Exception:
            pass
        result.append(system)
    return result


def _circuit_label(circuit):
    try:
        number = circuit.get_Parameter(BuiltInParameter.RBS_ELEC_CIRCUIT_NUMBER).AsString()
    except Exception:
        number = None
    try:
        eid = unicode(circuit.Id.IntegerValue)
    except Exception:
        eid = u"?"
    return u"цепь {} [{}]".format(number, eid) if number else u"цепь [{}]".format(eid)


def _target_parameter(circuit, target_param):
    if target_param:
        return circuit.LookupParameter(target_param)
    return circuit.get_Parameter(BuiltInParameter.RBS_ELEC_CIRCUIT_NAME)


def _write_circuit(circuit, target_param, text):
    """'written' / 'unchanged' / текст ошибки."""
    p = _target_parameter(circuit, target_param)
    if p is None:
        return u"у цепи нет параметра «{}»".format(target_param or u"Имя нагрузки")
    if param_to_text(p) == text:
        return "unchanged"
    if p.IsReadOnly:
        return u"параметр «{}» только для чтения".format(target_param or u"Имя нагрузки")
    if not target_param:
        ok = set_circuit_load_name(circuit, text)
    elif p.StorageType == StorageType.ElementId:
        ok = False
    else:
        ok = set_param_text(p, text)
    if not ok:
        return u"не удалось записать «{}» в параметр «{}»".format(
            text, target_param or u"Имя нагрузки")
    return "written"


def write_load_names(doc, elements, settings):
    """
    Имя по маске из параметров каждого элемента → в его электрические цепи.
    Если в одну цепь входят несколько выбранных элементов с разными
    значениями, цепь пропускается (в отчёте — какие значения столкнулись).
    """
    first = (settings.get("load_name_first_param") or u"").strip()
    second = (settings.get("load_name_second_param") or u"").strip()
    mask = settings.get("load_name_mask") or u""
    target = (settings.get("load_name_target_param") or u"").strip()

    result = Result()
    planned = {}   # id цепи -> (цепь, {текст: [метки элементов]})
    order = []

    for el in elements:
        circuits = device_circuits(el)
        if not circuits:
            result.skip(u"{} — нет электрической цепи".format(element_label(el)))
            continue
        text, reason = name_for(doc, el, first, second, mask)
        if text is None:
            result.skip(u"{} — {}".format(element_label(el), reason))
            continue
        for circuit in circuits:
            key = circuit.Id.IntegerValue
            if key not in planned:
                planned[key] = (circuit, {})
                order.append(key)
            planned[key][1].setdefault(text, []).append(element_label(el))

    for key in order:
        circuit, texts = planned[key]
        if len(texts) > 1:
            result.skip(u"{} — у элементов цепи разные значения: {}".format(
                _circuit_label(circuit),
                u"; ".join(u"«{}» ({})".format(t, u", ".join(labels))
                           for t, labels in sorted(texts.items()))))
            continue
        text = list(texts)[0]
        outcome = _write_circuit(circuit, target, text)
        if outcome == "written":
            result.written += 1
        elif outcome == "unchanged":
            result.unchanged += 1
        else:
            result.skip(u"{} — {}".format(_circuit_label(circuit), outcome))
    return result


# --- «Имя панели» -------------------------------------------------------------

def is_electrical_equipment(el):
    try:
        return el.Category is not None and \
            el.Category.Id.IntegerValue == int(BuiltInCategory.OST_ElectricalEquipment)
    except Exception:
        return False


def write_panel_names(doc, elements, settings):
    """Имя по маске из параметров электрооборудования → в его «Имя панели»."""
    first = (settings.get("panel_name_first_param") or u"").strip()
    second = (settings.get("panel_name_second_param") or u"").strip()
    mask = settings.get("panel_name_mask") or u""

    result = Result()
    for el in elements:
        text, reason = name_for(doc, el, first, second, mask)
        if text is None:
            result.skip(u"{} — {}".format(element_label(el), reason))
            continue
        p = el.get_Parameter(BuiltInParameter.RBS_ELEC_PANEL_NAME)
        if p is None:
            result.skip(u"{} — нет параметра «Имя панели»".format(element_label(el)))
            continue
        if param_to_text(p) == text:
            result.unchanged += 1
        elif set_panel_name(el, text):
            result.written += 1
        else:
            result.skip(u"{} — не удалось записать «{}» в «Имя панели»".format(
                element_label(el), text))
    return result
