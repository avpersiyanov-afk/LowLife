# -*- coding: utf-8 -*-
"""Read circuit route descriptions and show two independent quantity reports."""
__title__ = u"Подсчёт прокладки"
__doc__ = u"Подсчёт длин труб и лотков по комплекту, с запасом и без. Shift+клик — имена параметров. Модель не меняет."

from pyrevit import revit, forms, script, EXEC_PARAMS
from Autodesk.Revit.DB import FilteredElementCollector
from Autodesk.Revit.DB.Electrical import ElectricalSystem
from lowlife import route_quantities, route_quantities_settings, select_list
from lowlife.route_quantities_report import print_report
from lowlife.i18n import tr


settings_ui = route_quantities_settings.SETTINGS
if EXEC_PARAMS.config_mode:
    settings_ui.get_settings_interactive()
    script.exit()

settings = settings_ui.get_settings_silent()
if settings_ui.missing(settings, route_quantities_settings.KEYS):
    settings = settings_ui.get_settings_interactive()
    if settings is None:
        script.exit()
settings_ui.require(settings, route_quantities_settings.KEYS)
systems = list(FilteredElementCollector(revit.doc).OfClass(ElectricalSystem)
               .WhereElementIsNotElementType())
packages = route_quantities.packages(systems, settings["package_param"])
if not packages:
    forms.alert(tr(u"Не найдены значения параметра {}.", u"No values found for parameter {}.")
                .format(settings["package_param"]), exitscript=True)
package = select_list.SelectFromList.show(
    packages, title=tr(u"Выберите комплект для подсчёта", u"Select a package to calculate"),
    button_name=tr(u"Выполнить подсчёт", u"Calculate"), multiselect=False)
if not package:
    script.exit()
processed, sections = route_quantities.summarize(systems, settings, package)
print_report(script.get_output(), package, len(systems), processed,
             [settings[key] for key in route_quantities_settings.KEYS[1:]], sections)
