# -*- coding: utf-8 -*-
"""
Универсальные хелперы создания электрических цепей Revit — без привязки к
дисциплине. Используются автоматическими сценариями (шлейфы СПС/СОУЭ,
цепи изолятор-устройства СПС) и кнопками ручного построения цепей на
панелях CircuitsSCS/CircuitsSKUD/CircuitsSPA («Цепи СКС/СКУД/СПА»).
"""

from Autodesk.Revit.DB import ElementId, Domain
from Autodesk.Revit.DB.Electrical import ElectricalSystem, ElectricalSystemType


def detect_electrical_system_type(el):
    """
    ElectricalSystemType первого коннектора элемента с Domain=DomainElectrical
    — тип системы, под который коннектор сконфигурирован в самом семействе
    (не тот, к которому он ФАКТИЧЕСКИ подключён сейчас — это отдельное,
    MEPSystem.SystemType, у ещё не закреплённого в цепь элемента всегда
    None). Именно этот тип Revit молча подставляет сам при ручном создании
    цепи через UI («Создать электрическую цепь») — а API
    ElectricalSystem.Create() требует его явно и отказывает с
    electComponents при малейшем несовпадении (например если у устройства
    коннектор сконфигурирован под Communication/Telephone, а вызывающий
    код запросил Data).

    Возвращает None, если у элемента нет электрических коннекторов или тип
    определить не удалось — тогда вызывающий код сам решает, что подставить
    по умолчанию.
    """
    mep_model = getattr(el, "MEPModel", None)
    connector_mgr = getattr(mep_model, "ConnectorManager", None) if mep_model else None

    if connector_mgr is None:
        return None

    try:
        connectors = list(connector_mgr.Connectors)
    except:
        return None

    for c in connectors:
        try:
            if c.Domain != Domain.DomainElectrical:
                continue
        except:
            continue

        try:
            system_type = c.ElectricalSystemType
        except:
            continue

        if isinstance(system_type, ElectricalSystemType):
            return system_type

    return None


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

    # dir(ElectricalSystemType) вперемешку с реальными значениями (Data,
    # FireAlarm, ...) выдаёт унаследованные от Enum методы (CompareTo,
    # Equals, Parse, ...) — отфильтровываем и то, и другое через isinstance,
    # иначе getattr мог бы случайно вернуть метод вместо None.
    if not isinstance(system_type, ElectricalSystemType):
        available = [
            a for a in dir(ElectricalSystemType)
            if not a.startswith("_") and isinstance(getattr(ElectricalSystemType, a, None), ElectricalSystemType)
        ]
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

    system_type_name — либо имя типа строкой (тогда резолвится через
    resolve_system_type, как раньше), либо уже готовый ElectricalSystemType
    (например от detect_electrical_system_type) — тогда используется как
    есть, без резолва по имени.

    Возвращает (цепь, текст ошибки).
    """
    from System.Collections.Generic import List

    if isinstance(system_type_name, ElectricalSystemType):
        system_type, error = system_type_name, None
    else:
        system_type, error = resolve_system_type(system_type_name)

    if system_type is None:
        return None, error

    # Порядок элементов сохраняется как передал вызывающий код — для
    # шлейфов СПС/СОУЭ это порядок по адресу устройства (build_loop_
    # circuits передаёт уже отсортированный список), чтобы подключение в
    # цепи шло по факту прохождения шлейфа, а не как попало.
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
        # Не помогло — как запасной вариант пробуем ещё раз, включив
        # панель в список первым элементом. По наблюдению панель сама по
        # себе обычно НЕ помогает (нужен реальный элемент категории
        # «Электрооборудование» среди устройств, например изолятор), но
        # это дешёвая попытка на случай других семейств/проектов, где
        # включение панели всё же нужно.
        with_panel_ids = List[ElementId]()
        with_panel_ids.Add(panel_el.Id)
        for el in device_els:
            with_panel_ids.Add(el.Id)

        system, create_error = _try_create(doc, with_panel_ids, system_type, system_type_name)
        panel_forced_into_elements = system is not None

    if system is None:
        return None, create_error

    if panel_forced_into_elements:
        # Панель числится элементом цепи (см. комментарий выше) — убираем
        # её оттуда ДО SelectPanel, а не после: пока панель одновременно и
        # элемент/нагрузка цепи, и её источник, Revit отказывает с
        # "Not allow circular connection..." прямо в SelectPanel, и до
        # Remove дело не доходит (а без Remove цепь остаётся без
        # назначенной панели). Если Remove недоступен для ElectricalSystem
        # в этой версии/случае — не критично: SelectPanel ниже всё равно
        # попробует назначить панель, просто она может остаться видна и
        # как элемент цепи в спецификации.
        try:
            remove_ids = List[ElementId]()
            remove_ids.Add(panel_el.Id)
            system.Remove(remove_ids)
        except:
            pass

    try:
        system.SelectPanel(panel_el)
    except Exception as ex:
        return system, u"цепь создана, но не подключена к панели: {}".format(ex)

    return system, None
