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


def _try_create(doc, ids, system_type, system_type_name):
    try:
        system = ElectricalSystem.Create(doc, ids, system_type)
    except Exception as ex:
        return None, u"не удалось создать цепь типа «{}»: {}".format(system_type_name, ex)

    if system is None:
        return None, u"Revit не создал цепь"

    return system, None


def create_circuit(doc, panel_el, device_els, system_type_name):
    """
    Создаёт электрическую цепь из устройств и подключает её к панели.

    Возвращает (цепь, текст ошибки).
    """
    from System.Collections.Generic import List

    system_type, error = resolve_system_type(system_type_name)
    if system_type is None:
        return None, error

    device_ids = List[ElementId]()
    for el in device_els:
        device_ids.Add(el.Id)

    # Панель НЕ передаём в список элементов цепи — только устройства,
    # панель назначается отдельно через SelectPanel ниже. Иначе панель
    # становится ещё и "элементом" (нагрузкой) собственной цепи, а не
    # только источником — из-за этого цепь на плане/в спецификации
    # выглядит замкнутой ("кольцевой": панель одновременно и источник, и
    # потребитель).
    system, create_error = _try_create(doc, device_ids, system_type, system_type_name)
    panel_forced_into_elements = False

    if system is None:
        # Некоторые семейства панелей (например СПС) не могут "создать"
        # цепь заданного типа сами по себе — Revit падает с electComponents,
        # если среди переданных элементов нет ни одного способного её
        # создать (обычно значит, что у устройств этой категории нет
        # коннектора нужного домена/классификации — см. кнопку
        # «Диагностика коннекторов»/InspectConnectors). Как запасной
        # вариант пробуем ещё раз, включив панель в список.
        with_panel_ids = List[ElementId]()
        with_panel_ids.Add(panel_el.Id)
        for el in device_els:
            with_panel_ids.Add(el.Id)

        system, create_error = _try_create(doc, with_panel_ids, system_type, system_type_name)
        panel_forced_into_elements = system is not None

    if system is None:
        return None, create_error

    try:
        system.SelectPanel(panel_el)
    except Exception as ex:
        return system, u"цепь создана, но не подключена к панели: {}".format(ex)

    if panel_forced_into_elements:
        # Панель по-прежнему числится элементом цепи (см. комментарий выше)
        # — теперь, когда она назначена источником через SelectPanel,
        # пробуем убрать её из состава элементов, чтобы цепь не выглядела
        # замкнутой. Если Revit это не позволяет (метод недоступен для
        # ElectricalSystem в этой версии/случае) — не критично: цепь всё
        # равно создана и подключена к панели правильно, просто панель
        # останется видна как элемент цепи в спецификации.
        try:
            remove_ids = List[ElementId]()
            remove_ids.Add(panel_el.Id)
            system.Remove(remove_ids)
        except:
            pass

    return system, None
