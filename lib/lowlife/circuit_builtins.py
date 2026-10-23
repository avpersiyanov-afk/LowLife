# -*- coding: utf-8 -*-
"""
Штатные параметры электрической цепи Revit, которые кнопки раньше брали из
настроек по имени («Панель», «Имя нагрузки», «Проводник»). Имена
штатных параметров зависят от языка Revit и одинаковы во всех проектах,
поэтому их больше не спрашивают в настройках: здесь они читаются и
пишутся через BuiltInParameter (и ключевую спецификацию для «Проводника»).

- circuit_panel_name(circuit) — имя панели цепи («Панель»,
  RBS_ELEC_CIRCUIT_PANEL_PARAM; запасной вариант — BaseEquipment).
  Панель цепи задаётся подключением (ElectricalSystem.SelectPanel) —
  писать её отдельно не нужно.
- set_circuit_load_name(circuit, value) — «Имя нагрузки»
  (RBS_ELEC_CIRCUIT_NAME).
- set_circuit_wire_type(doc, circuit, row_id) — «Проводник»: ссылка на
  строку справочника кабелей (ключевой спецификации цепей). Параметр,
  который заполняет строка, — ключевой параметр её спецификации
  (KeyScheduleParameterName), обычно «Проводник».
- set_panel_name(panel, value) — «Имя панели» электрооборудования
  (RBS_ELEC_PANEL_NAME).
"""

try:
    unicode  # noqa: F821 — IronPython/Python 2
except NameError:  # Python 3
    unicode = str


from Autodesk.Revit.DB import BuiltInParameter, ElementId, Element

from lowlife.params import set_element_id_param
from lowlife.wire_catalog import DEFAULT_KEY_PARAM_NAME


def _builtin(el, bip):
    try:
        return el.get_Parameter(bip)
    except Exception:
        return None


def circuit_panel_name(circuit):
    """Имя панели, к которой подключена цепь, или u""."""
    p = _builtin(circuit, BuiltInParameter.RBS_ELEC_CIRCUIT_PANEL_PARAM)
    try:
        if p is not None and p.HasValue:
            value = p.AsString() or p.AsValueString()
            if value:
                return value
    except Exception:
        pass
    try:
        panel = circuit.BaseEquipment
        if panel is not None:
            return Element.Name.GetValue(panel) or u""
    except Exception:
        pass
    return u""


def set_circuit_load_name(circuit, value):
    """Пишет «Имя нагрузки» цепи. True — записано."""
    text = u"" if value is None else unicode(value)
    p = _builtin(circuit, BuiltInParameter.RBS_ELEC_CIRCUIT_NAME)
    try:
        if p is not None and not p.IsReadOnly:
            return bool(p.Set(text))
    except Exception:
        pass
    try:
        circuit.LoadName = text
        return True
    except Exception:
        return False


def wire_type_param_name(doc, row_id):
    """Ключевой параметр спецификации, которой принадлежит строка row_id."""
    try:
        row = doc.GetElement(row_id)
        schedule = doc.GetElement(row.OwnerViewId) if row is not None else None
        name = schedule.Definition.KeyScheduleParameterName if schedule is not None else None
        if name:
            return name
    except Exception:
        pass
    return DEFAULT_KEY_PARAM_NAME


def set_circuit_wire_type(doc, circuit, row_id):
    """«Проводник» цепи = строка справочника кабелей row_id. True — записано."""
    if row_id is None or row_id == ElementId.InvalidElementId:
        return False
    return set_element_id_param(circuit, wire_type_param_name(doc, row_id), row_id)


def set_panel_name(panel, value):
    """Пишет «Имя панели» электрооборудования (RBS_ELEC_PANEL_NAME). True — записано."""
    text = u"" if value is None else unicode(value)
    p = _builtin(panel, BuiltInParameter.RBS_ELEC_PANEL_NAME)
    try:
        if p is not None and not p.IsReadOnly:
            return bool(p.Set(text))
    except Exception:
        pass
    return False
