# -*- coding: utf-8 -*-
"""
Тело кнопки «Цепи СКС» (CircuitsSCS.panel): ручное построение цепей
панель -> устройства.

Тип электрической цепи Revit определяется по коннектору самого устройства
(detect_electrical_system_type) — тем же способом, каким его молча
подставляет сам Revit при ручном создании цепи через UI. У СКС встречаются
устройства разных категорий (розетки RJ-45 категории «Устройства связи»,
оптические кроссы и т.п.), и их коннекторы в проекте могут быть
сконфигурированы под разные типы (Data, Communication, Telephone...) —
раньше здесь был жёстко зашит один тип Data для всех, из-за чего
ElectricalSystem.Create падал с electComponents для устройств с другим
типом коннектора, хотя вручную через Revit UI цепь с той же панелью
создаётся нормально. CIRCUIT_SYSTEM_TYPE остаётся запасным значением — на
случай, если у устройства не нашлось электрического коннектора для
автоопределения.

Проводник (кабель) для параметра цепи «Проводник» — это встроенный
параметр электрической цепи Revit (выпадающий список — ссылка на строку
ключевой спецификации), а не project-specific SMNX_-параметр, поэтому его
имя зашито в код (CONDUCTOR_PARAM_NAME), а не берётся из настроек СКС (там
ему не место). Но САМО значение — какую строку справочника кабелей
проставлять — выбирается один раз в окне настроек («Параметры СКС», раздел
«Проводник для цепей СКС», см. scs_settings.py) и оттуда читается при
каждом запуске кнопки, а не запрашивается заново, аналогично тому, как это
сделано для типа проводника по категории устройства в СПС
(fire_alarm_settings.get_category_wire_type_elem_ids).

После создания каждой цепи заполняется и параметр «Имя нагрузки» (его имя
берётся из настроек, load_name_param) — из параметра типа устройства
«Обозначение» (type_code_param) и параметра экземпляра «Адрес устройства»
(device_address_param), см. scs_circuits.make_load_name. Те же настройки
уже используются кнопкой «Расчёт длины цепи» (SyncCircuitsAndLengths).

Устройство с несколькими электрическими коннекторами (например розетка с
двумя гнёздами RJ-45 в одном экземпляре семейства) получает по отдельной
цепи на каждый коннектор, см. count_electrical_connectors и
build_scs_manual_circuits — имя нагрузки у таких цепей дополняется
суффиксом "-1"/"-2" по номеру коннектора.
"""

from Autodesk.Revit.DB import ElementId

from pyrevit import revit, forms

from lowlife.electrical_circuits import create_circuit, detect_electrical_system_type, count_electrical_connectors
from lowlife.params import set_element_id_param, get_type_string_param, get_string_param, set_param_any
from lowlife.scs_circuits import clean_text_value, make_load_name

# Запасной тип цепи — только если у устройства не нашлось электрического
# коннектора для detect_electrical_system_type (обычный случай — Data).
CIRCUIT_SYSTEM_TYPE = "Data"
CONDUCTOR_PARAM_NAME = u"Проводник"


def get_conductor_id(doc, settings):
    """
    ElementId проводника (строки справочника кабелей) для цепей СКС — берётся
    из настроек СКС (кнопка «Параметры СКС»), а не выбирается заново при
    каждом запуске. Останавливает скрипт, если в настройках ничего не
    выбрано или выбранный элемент больше не существует в проекте.
    """
    id_str = settings.get("conductor_type_id")

    if not id_str:
        forms.alert(
            u"В настройках СКС не выбран проводник для цепей.\n\n"
            u"Запустите кнопку «Параметры СКС» и выберите его в разделе "
            u"«Проводник для цепей СКС».",
            exitscript=True
        )

    element_id = None
    try:
        element_id = ElementId(int(id_str))
    except:
        element_id = None

    if element_id is None or doc.GetElement(element_id) is None:
        forms.alert(
            u"Проводник, выбранный в настройках СКС, не найден в проекте "
            u"(возможно, был удалён). Запустите кнопку «Параметры СКС» и "
            u"выберите его заново.",
            exitscript=True
        )

    return element_id


def build_scs_manual_circuits(doc, panel_el, device_els, conductor_id, settings):
    """
    Создаёт по одной цепи на каждый электрический коннектор устройства
    (тип — по коннектору самого устройства, см. detect_electrical_system_type),
    подключая его напрямую к панели, и проставляет каждой цепи параметры
    «Проводник» и «Имя нагрузки» (последний — из «Обозначение» типа
    устройства + «Адрес устройства», если оба заполнены и заданы в
    настройках).

    Устройства с двумя и более электрическими коннекторами (например
    розетка с двумя гнёздами RJ-45 в одном экземпляре семейства) получают
    по отдельной цепи на каждый коннектор — Revit сам подбирает свободный
    коннектор при каждом вызове ElectricalSystem.Create с тем же элементом
    (см. count_electrical_connectors), поэтому вызываем create_circuit
    подряд нужное число раз. Такие цепи получают имя нагрузки с суффиксом
    "-1", "-2"... (порядок вызовов), чтобы отличать их друг от друга —
    у обычных однопортовых устройств суффикс не добавляется, имя нагрузки
    остаётся прежним.

    Возвращает (created_count, errors).
    """
    type_code_param = settings.get("type_code_param")
    device_address_param = settings.get("device_address_param")
    load_name_param = settings.get("load_name_param")

    created = 0
    errors = []

    with revit.Transaction(u"Построение цепей СКС"):
        for dev in device_els:
            system_type = detect_electrical_system_type(dev) or CIRCUIT_SYSTEM_TYPE
            connector_count = max(1, count_electrical_connectors(dev))

            base_load_name = None
            if type_code_param and device_address_param and load_name_param:
                type_code = clean_text_value(get_type_string_param(doc, dev, type_code_param))
                device_address = clean_text_value(get_string_param(dev, device_address_param))
                base_load_name = make_load_name(type_code, device_address)

            for i in range(connector_count):
                circuit, error = create_circuit(doc, panel_el, [dev], system_type)

                if circuit is None:
                    if connector_count > 1:
                        errors.append(u"Устройство ID {} (коннектор {}/{}): {}".format(
                            dev.Id.IntegerValue, i + 1, connector_count, error
                        ))
                    else:
                        errors.append(u"Устройство ID {}: {}".format(dev.Id.IntegerValue, error))
                    continue

                created += 1

                if error:
                    errors.append(u"Устройство ID {}: {}".format(dev.Id.IntegerValue, error))

                set_element_id_param(circuit, CONDUCTOR_PARAM_NAME, conductor_id)

                if base_load_name:
                    load_name = base_load_name if connector_count <= 1 else u"{}-{}".format(base_load_name, i + 1)
                    set_param_any(circuit, load_name_param, load_name)

    return created, errors
