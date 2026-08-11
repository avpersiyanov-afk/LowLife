# -*- coding: utf-8 -*-
"""
Тело кнопки «Цепи СКС» (CircuitsSCS.panel): ручное построение цепей
панель -> устройства, всегда типа Data (СКС — структурированная кабельная
система, других типов цепи здесь не бывает, в отличие от СКУД/СПА).

Перед выбором панели/устройств кнопка просит выбрать проводник (кабель)
для параметра цепи «Проводник» — это встроенный параметр электрической
цепи Revit (выпадающий список — ссылка на строку ключевой спецификации),
а не project-specific SMNX_-параметр, поэтому его имя зашито в код, а не
берётся из настроек СКС (там ему не место).

Revit не даёт получить список строк справочника кабелей напрямую (в
отличие, например, от списка типов категории), поэтому список для выбора
собирается из значений, уже проставленных хотя бы у одной электрической
цепи документа — тот же приём, что и в исходном Dynamo-скрипте
пользователя (там имя проводника вводилось вручную текстом в IN[0], здесь
— выбирается из списка уже использованных).
"""

from Autodesk.Revit.DB import FilteredElementCollector
from Autodesk.Revit.DB.Electrical import ElectricalSystem

from pyrevit import revit, forms

from lowlife.electrical_circuits import create_circuit
from lowlife.params import set_element_id_param
from lowlife.scs import safe_element_name

CIRCUIT_SYSTEM_TYPE = "Data"
CONDUCTOR_PARAM_NAME = u"Проводник"


def list_used_conductors(doc):
    """
    {имя элемента-проводника: ElementId} — по значениям параметра
    «Проводник», уже проставленным хотя бы у одной электрической цепи
    документа (ElectricalSystem).
    """
    conductors = {}

    systems = FilteredElementCollector(doc).OfClass(ElectricalSystem).ToElements()

    for s in systems:
        p = s.LookupParameter(CONDUCTOR_PARAM_NAME)
        if not p:
            continue

        try:
            elem_id = p.AsElementId()
        except:
            continue

        if elem_id is None or elem_id.IntegerValue == -1:
            continue

        elem = doc.GetElement(elem_id)
        if elem is None:
            continue

        name = safe_element_name(elem) or unicode(elem_id.IntegerValue)
        conductors[name] = elem_id

    return conductors


def pick_conductor(doc):
    """
    Даёт выбрать проводник из уже использованных в проекте. Останавливает
    скрипт, если ни у одной цепи документа проводник ещё не выбран, или
    если пользователь отменил выбор.
    """
    conductors = list_used_conductors(doc)

    if not conductors:
        forms.alert(
            u"В проекте пока ни у одной электрической цепи не выбран "
            u"проводник — Revit не даёт получить список строк справочника "
            u"кабелей напрямую, поэтому кнопка берёт варианты из уже "
            u"использованных значений. Выберите проводник вручную в "
            u"свойствах любой электрической цепи хотя бы один раз, затем "
            u"запустите кнопку снова.",
            exitscript=True
        )

    names = sorted(conductors.keys())

    selected_name = forms.SelectFromList.show(
        names,
        title=u"Проводник для цепей СКС",
        button_name=u"Выбрать",
        multiselect=False
    )

    if not selected_name:
        forms.alert(u"Операция отменена.", exitscript=True)

    return conductors[selected_name]


def build_scs_manual_circuits(doc, panel_el, device_els, conductor_id):
    """
    Создаёт по одной цепи типа Data на каждое устройство, подключая его
    напрямую к панели, и проставляет каждой цепи параметр «Проводник».

    Возвращает (created_count, errors).
    """
    created = 0
    errors = []

    with revit.Transaction(u"Построение цепей СКС"):
        for dev in device_els:
            circuit, error = create_circuit(doc, panel_el, [dev], CIRCUIT_SYSTEM_TYPE)

            if circuit is None:
                errors.append(u"Устройство ID {}: {}".format(dev.Id.IntegerValue, error))
                continue

            created += 1

            if error:
                errors.append(u"Устройство ID {}: {}".format(dev.Id.IntegerValue, error))

            set_element_id_param(circuit, CONDUCTOR_PARAM_NAME, conductor_id)

    return created, errors
