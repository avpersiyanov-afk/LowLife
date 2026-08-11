# -*- coding: utf-8 -*-
"""
Универсальные хелперы создания электрических цепей Revit — без привязки к
дисциплине. Используются автоматическими сценариями (шлейфы СПС/СОУЭ,
цепи изолятор-устройства СПС) и кнопками ручного построения цепей на
панелях CircuitsSCS/CircuitsSKUD/CircuitsSPA («Цепи СКС/СКУД/СПА»).
"""

from Autodesk.Revit.DB import ElementId
from Autodesk.Revit.DB.Electrical import ElectricalSystem, ElectricalSystemType


def resolve_system_type(name):
    """
    ElectricalSystemType по имени из настроек ("FireAlarm", "Data",
    "Communication", "Security", "NurseCall", "Power"...).

    Возвращает (тип, текст ошибки): набор значений отличается между
    версиями Revit, поэтому имя проверяется через getattr, а не
    фиксируется в коде.
    """
    value = (name or u"").strip()

    if not value:
        return None, u"тип цепи не задан в настройках"

    system_type = getattr(ElectricalSystemType, value, None)

    if system_type is None:
        available = [a for a in dir(ElectricalSystemType) if not a.startswith("_")]
        return None, u"неизвестный тип цепи «{}». Доступные: {}".format(
            value, u", ".join(sorted(available))
        )

    return system_type, None


def create_circuit(doc, panel_el, device_els, system_type_name):
    """
    Создаёт электрическую цепь из устройств и подключает её к панели.

    Возвращает (цепь, текст ошибки).
    """
    from System.Collections.Generic import List

    system_type, error = resolve_system_type(system_type_name)
    if system_type is None:
        return None, error

    # Revit требует, чтобы среди переданных элементов был хотя бы один,
    # способный "создать" цепь заданного типа — это панель, а не нагрузки:
    # без неё ElectricalSystem.Create падает с electComponents, даже если
    # панель потом отдельно назначается через SelectPanel.
    ids = List[ElementId]()
    ids.Add(panel_el.Id)
    for el in device_els:
        ids.Add(el.Id)

    try:
        system = ElectricalSystem.Create(doc, ids, system_type)
    except Exception as ex:
        return None, u"не удалось создать цепь типа «{}»: {}".format(system_type_name, ex)

    if system is None:
        return None, u"Revit не создал цепь"

    try:
        system.SelectPanel(panel_el)
    except Exception as ex:
        return system, u"цепь создана, но не подключена к панели: {}".format(ex)

    return system, None
