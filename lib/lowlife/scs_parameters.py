# -*- coding: utf-8 -*-
"""
Проверка и добавление привязок параметров СКС из подключённого к проекту
файла общих параметров (ФОП).

Ничего не выдумывает: если у параметра нет определения ни в проекте, ни
в файле ФОП — только сообщает об этом (см. ensure_binding). Новые
определения в сам файл ФОП не добавляются.
"""

from Autodesk.Revit.DB import BuiltInCategory, BuiltInParameterGroup

CAT_MARKERS = [BuiltInCategory.OST_GenericModel]

CAT_DEVICES_ONLY = [
    BuiltInCategory.OST_CommunicationDevices,
    BuiltInCategory.OST_ElectricalFixtures,
    BuiltInCategory.OST_DataDevices,
]

CAT_DEVICES_AND_PANELS = CAT_DEVICES_ONLY + [BuiltInCategory.OST_ElectricalEquipment]

CAT_CIRCUITS = [BuiltInCategory.OST_ElectricalCircuit]

INSTANCE = "instance"
TYPE = "type"

TEXT = "Text"
NUMBER = "Number"

FOP = "fop"
NATIVE = "native"

# (ключ настроек, подпись, список ли значений через запятую, категории,
#  instance/type, тип данных для справки, источник)
PARAM_SPECS = [
    ("cable_param_name", u"Тип прокладки кабеля (узлы)",
        False, CAT_MARKERS, INSTANCE, TEXT, FOP),
    ("route_param_name", u"Тип трассы (узлы)",
        False, CAT_MARKERS, INSTANCE, TEXT, FOP),
    ("addr_param_name", u"Адрес узла",
        False, CAT_MARKERS, INSTANCE, TEXT, FOP),
    ("addr_prev_param_name", u"Предыдущий адрес",
        False, CAT_MARKERS, INSTANCE, TEXT, FOP),
    ("segment_loads_param", u"Список цепей (узел маршрута)",
        False, CAT_MARKERS, INSTANCE, TEXT, FOP),
    ("offset_param_names", u"Отметка (узлы/устройства/панели/стояки)",
        True, CAT_MARKERS + CAT_DEVICES_AND_PANELS, INSTANCE, NUMBER, FOP),
    ("nearest_segment_param", u"Ближайший узел маршрута (панель/устройство)",
        False, CAT_DEVICES_AND_PANELS, INSTANCE, TEXT, FOP),
    ("device_address_param", u"Адрес устройства",
        False, CAT_DEVICES_ONLY, INSTANCE, TEXT, FOP),
    ("type_code_param", u"Обозначение (тип устройства)",
        False, CAT_DEVICES_ONLY, TYPE, TEXT, FOP),
    ("circuit_panel_param", u"Панель (параметр цепи)",
        False, CAT_CIRCUITS, INSTANCE, TEXT, FOP),
    ("circuit_name_type_param", u"Наименование (цепь)",
        False, CAT_CIRCUITS, INSTANCE, TEXT, FOP),
    ("circuit_number_param", u"Номер цепи",
        False, CAT_CIRCUITS, INSTANCE, TEXT, FOP),
    ("circuit_route_param", u"Маршрут цепи",
        False, CAT_CIRCUITS, INSTANCE, TEXT, FOP),
    ("wire_length_param", u"Длина проводника",
        False, CAT_CIRCUITS, INSTANCE, NUMBER, FOP),
    ("tray_length_param", u"Длина проводника в лотке",
        False, CAT_CIRCUITS, INSTANCE, NUMBER, FOP),
    ("pipe_length_param", u"Длина проводника в трубе",
        False, CAT_CIRCUITS, INSTANCE, NUMBER, FOP),
    ("route_method_param", u"Способ прокладки",
        False, CAT_CIRCUITS, INSTANCE, TEXT, FOP),
    ("load_name_param", u"Имя нагрузки",
        False, CAT_CIRCUITS, INSTANCE, TEXT, NATIVE),
]


def get_category(doc, built_in_category):
    try:
        return doc.Settings.Categories.get_Item(built_in_category)
    except:
        return None


def find_existing_binding(doc, name):
    """(definition, binding), если параметр name уже привязан хоть к чему-то в проекте."""
    it = doc.ParameterBindings.ForwardIterator()
    it.Reset()

    while it.MoveNext():
        definition = it.Key
        if definition.Name == name:
            return definition, it.Current

    return None, None


def binding_has_category(binding, category):
    try:
        return binding.Categories.Contains(category)
    except:
        return False


def find_shared_definition(sp_file, name):
    if sp_file is None:
        return None

    for group in sp_file.Groups:
        for definition in group.Definitions:
            if definition.Name == name:
                return definition

    return None


def ensure_binding(doc, app, sp_file, name, categories, binding_kind,
                    param_group=BuiltInParameterGroup.PG_DATA):
    """
    Убеждается, что параметр name привязан ко всем categories в проекте.

    Возвращает dict:
        added_categories — имена категорий, для которых добавлена привязка
        already_ok — True, если добавлять ничего не пришлось
        missing_definition — True, если определения нет ни в проекте, ни в ФОП
        error — текст ошибки Revit API, если попытка привязки не удалась
    """
    existing_def, existing_binding = find_existing_binding(doc, name)

    missing_categories = []
    for cat_enum in categories:
        category = get_category(doc, cat_enum)
        if category is None:
            continue
        if existing_binding is not None and binding_has_category(existing_binding, category):
            continue
        missing_categories.append(category)

    if not missing_categories:
        return {"added_categories": [], "already_ok": True, "missing_definition": False, "error": None}

    definition = existing_def
    if definition is None:
        definition = find_shared_definition(sp_file, name)

    if definition is None:
        return {"added_categories": [], "already_ok": False, "missing_definition": True, "error": None}

    cat_set = app.Create.NewCategorySet()

    if existing_binding is not None:
        for c in existing_binding.Categories:
            cat_set.Insert(c)

    for c in missing_categories:
        cat_set.Insert(c)

    if binding_kind == TYPE:
        new_binding = app.Create.NewTypeBinding(cat_set)
    else:
        new_binding = app.Create.NewInstanceBinding(cat_set)

    try:
        if existing_binding is not None:
            ok = doc.ParameterBindings.ReInsert(definition, new_binding, param_group)
        else:
            ok = doc.ParameterBindings.Insert(definition, new_binding, param_group)
    except Exception as ex:
        return {"added_categories": [], "already_ok": False, "missing_definition": False, "error": str(ex)}

    if not ok:
        return {
            "added_categories": [], "already_ok": False, "missing_definition": False,
            "error": u"ParameterBindings.Insert/ReInsert вернул False"
        }

    return {
        "added_categories": [c.Name for c in missing_categories],
        "already_ok": False,
        "missing_definition": False,
        "error": None
    }
