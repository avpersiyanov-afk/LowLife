# -*- coding: utf-8 -*-
"""
Тело кнопки «Цепь (общее)» (CircuitsGeneric.panel): ручное построение
произвольных электрических цепей «панель → устройства».

В отличие от кнопок «Цепи СКС/СКУД/СПА» здесь ничего не зашито в код —
всё берётся из окна «Параметры цепей (общее)» (generic_circuits_settings.py):

  * тип цепи — из настроек (circuit_system_type); если там пусто,
    определяется по коннектору устройства (detect_electrical_system_type),
    запасной вариант — FALLBACK_SYSTEM_TYPE ("Data");
  * кабель (строка справочника) — из настроек (conductor_type_id), пишется
    в штатный «Проводник» цепи (circuit_builtins); кабель
    необязателен — если не выбран, «Проводник» просто не проставляется;
  * «Имя нагрузки» цепи собирается из параметров подключаемого устройства
    по списку имён (load_name_source_params) через разделитель
    (load_name_separator): для каждого имени сначала берётся параметр
    экземпляра, затем — типа; пустые значения и «пустышки» ("0", "-",
    "None"…) пропускаются. Один параметр в списке = одиночный источник;
  * режим circuit_mode:
      "per_device" — отдельная цепь на каждое устройство (у каждой своё
                     имя нагрузки);
      "single"     — все устройства подключаются в одну общую цепь; имя
                     нагрузки при этом НЕ заполняется (нет одного
                     устройства-источника).

Выбор панели и устройств — общий с кнопками «Цепи СКС/СКУД/СПА»
(manual_circuits.pick_panel_and_devices), само создание цепи —
electrical_circuits.create_circuit.
"""

from Autodesk.Revit.DB import ElementId

from pyrevit import revit

from lowlife.electrical_circuits import create_circuit, detect_electrical_system_type
from lowlife.params import (
    get_param_any, get_type_string_param
)
from lowlife.circuit_builtins import set_circuit_load_name, set_circuit_wire_type
from lowlife.scs_circuits import clean_text_value

# Запасной тип цепи — только если circuit_system_type не задан в настройках
# И у устройства не нашлось электрического коннектора для автоопределения.
FALLBACK_SYSTEM_TYPE = u"Data"


def get_conductor_id(doc, settings):
    """
    ElementId кабеля (строки справочника) из настроек (conductor_type_id)
    или None, если кабель не выбран либо выбранный элемент больше не
    существует в проекте. В отличие от СКС кабель здесь необязателен,
    поэтому скрипт не останавливается — просто цепям не проставляется
    «Проводник».
    """
    id_str = settings.get("conductor_type_id")

    if not id_str:
        return None

    try:
        element_id = ElementId(int(id_str))
    except:
        return None

    if doc.GetElement(element_id) is None:
        return None

    return element_id


def build_load_name(doc, dev, source_param_names, separator):
    """
    Значение параметра цепи «Имя нагрузки» для устройства dev: значения
    параметров из source_param_names (по порядку) через separator. Для
    каждого имени сначала пробуется параметр экземпляра, затем — типа.
    Пустые и «пустышечные» значения пропускаются. Возвращает None, если
    ни один параметр не дал значения.
    """
    parts = []

    for name in source_param_names:
        value = clean_text_value(get_param_any(dev, name))
        if value is None:
            value = clean_text_value(get_type_string_param(doc, dev, name))
        if value:
            parts.append(value)

    if not parts:
        return None

    return (separator if separator is not None else u"").join(parts)


def _resolve_system_type(dev, configured_type):
    """Настроенный тип цепи, иначе — по коннектору устройства, иначе — запасной."""
    if configured_type:
        return configured_type
    return detect_electrical_system_type(dev) or FALLBACK_SYSTEM_TYPE


def _apply_conductor(doc, circuit, conductor_id):
    if conductor_id is not None:
        set_circuit_wire_type(doc, circuit, conductor_id)


def build_generic_circuits(doc, panel_el, device_els, conductor_id, settings):
    """
    Создаёт цепи «панель → устройства» по настройкам «Параметры цепей (общее)».

    Возвращает (created_count, errors) — errors это список текстов ошибок
    по устройствам/цепям, которые не удалось создать или подключить.
    """
    configured_type = (settings.get("circuit_system_type") or u"").strip()
    source_params = settings.get("load_name_source_params") or []
    separator = settings.get("load_name_separator", u"")
    mode = settings.get("circuit_mode") or "per_device"

    created = 0
    errors = []

    with revit.Transaction(u"Построение цепей (общее)"):

        if mode == "single":
            if device_els:
                system_type = _resolve_system_type(device_els[0], configured_type)
            else:
                system_type = configured_type or FALLBACK_SYSTEM_TYPE

            circuit, error = create_circuit(doc, panel_el, device_els, system_type)

            if circuit is None:
                errors.append(u"Общая цепь: {}".format(error))
            else:
                created += 1
                if error:
                    errors.append(u"Общая цепь: {}".format(error))
                _apply_conductor(doc, circuit, conductor_id)

        else:
            for dev in device_els:
                system_type = _resolve_system_type(dev, configured_type)

                circuit, error = create_circuit(doc, panel_el, [dev], system_type)

                if circuit is None:
                    errors.append(u"Устройство ID {}: {}".format(dev.Id.IntegerValue, error))
                    continue

                created += 1

                if error:
                    errors.append(u"Устройство ID {}: {}".format(dev.Id.IntegerValue, error))

                _apply_conductor(doc, circuit, conductor_id)

                if source_params:
                    load_name = build_load_name(doc, dev, source_params, separator)
                    if load_name:
                        set_circuit_load_name(circuit, load_name)

    return created, errors
