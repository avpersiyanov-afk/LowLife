# -*- coding: utf-8 -*-
"""
Тело кнопки «Цепи СКС» (CircuitsSCS.panel): ручное построение цепей
панель -> устройства, всегда типа Data (СКС — структурированная кабельная
система, других типов цепи здесь не бывает, в отличие от СКУД/СПА).

В начале работы, перед выбором панели/устройств, кнопка просит выбрать
тип проводника (кабеля) из справочника — он проставляется в параметр
цепи «Проводник» на каждую созданную цепь.
"""

from pyrevit import revit, forms

from lowlife.electrical_circuits import create_circuit
from lowlife.params import set_element_id_param
from lowlife.scs_settings import list_wire_catalog_items, WireTypeOption

CIRCUIT_SYSTEM_TYPE = "Data"


def pick_wire_type(doc, marker_param_name):
    """
    Показывает список типов проводника (строк справочника кабелей,
    см. list_wire_catalog_items) и возвращает выбранный элемент.
    Останавливает скрипт, если справочник пуст или выбор отменён.
    """
    wire_items = list_wire_catalog_items(doc, marker_param_name)

    if not wire_items:
        forms.alert(
            u"Не найдено строк справочника кабелей (ни один элемент документа "
            u"не содержит одновременно «Ключевое имя» и параметр «{}»).".format(marker_param_name),
            exitscript=True
        )

    options = sorted([WireTypeOption(w) for w in wire_items], key=lambda o: o.name)

    selected = forms.SelectFromList.show(
        options,
        title=u"Тип проводника (кабеля) для цепей СКС",
        button_name=u"Выбрать",
        multiselect=False
    )

    if not selected:
        forms.alert(u"Операция отменена.", exitscript=True)

    return selected.wire_type


def build_scs_manual_circuits(doc, panel_el, device_els, wire_type_el, cable_type_param):
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

            set_element_id_param(circuit, cable_type_param, wire_type_el.Id)

    return created, errors
