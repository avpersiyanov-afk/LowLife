# -*- coding: utf-8 -*-

__title__ = "Настройки\nплагина"
__doc__ = "Настройка параметров проекта, используемых при формировании журнала цепей."
__author__ = "Pipers"

import traceback

print(u"=== OpenSettings: старт ===")

try:
    import clr
    clr.AddReference('RevitAPI')
    print(u"OK: clr.AddReference RevitAPI")

    from Autodesk.Revit.DB import FilteredElementCollector, BuiltInCategory
    print(u"OK: import Autodesk.Revit.DB")

    from pyrevit import revit, forms
    print(u"OK: import pyrevit.revit/forms")

    from lowlife.cable_schedule import load_settings, save_settings
    print(u"OK: import lowlife.cable_schedule")

    doc = revit.doc

    def collect_circuit_param_names():
        names = set()
        circuits = FilteredElementCollector(doc) \
            .OfCategory(BuiltInCategory.OST_ElectricalCircuit) \
            .WhereElementIsNotElementType() \
            .ToElements()

        for circuit in list(circuits)[:50]:
            for p in circuit.Parameters:
                name = p.Definition.Name if p.Definition else None
                if name and name.strip():
                    names.add(name)

        return sorted(names)

    settings = load_settings()
    print(u"OK: load_settings -> {}".format(settings))

    param_names = collect_circuit_param_names()
    print(u"OK: collect_circuit_param_names -> {} шт.".format(len(param_names)))

    current = settings["cable_mark_parameter"]
    options = param_names if current in param_names else [current] + param_names
    print(u"OK: options готовы, вызываю forms.SelectFromList.show...")

    selected = forms.SelectFromList.show(
        options,
        title=u"Марка кабеля, провода",
        button_name=u"Выбрать",
        multiselect=False
    )
    print(u"OK: SelectFromList.show вернул: {}".format(selected))

    if selected is None:
        if forms.alert(
            u"Нужного параметра нет в списке?\n\n"
            u"Можно ввести имя параметра вручную.",
            yes=True, no=True
        ):
            typed = forms.ask_for_string(
                default=current,
                prompt=u"Имя параметра цепи, хранящего марку кабеля/провода:",
                title=u"Настройки плагина — Кабельный журнал"
            )
            if typed:
                settings["cable_mark_parameter"] = typed
                save_settings(settings)
    else:
        settings["cable_mark_parameter"] = selected
        save_settings(settings)

    print(u"=== OpenSettings: успешно завершён ===")

except Exception as ex:
    print(u"!!! ОШИБКА: {}".format(ex))
    print(traceback.format_exc())
