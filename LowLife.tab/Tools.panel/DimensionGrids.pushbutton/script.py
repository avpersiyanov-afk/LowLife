# -*- coding: utf-8 -*-

__title__ = u"Размеры осей"
__doc__ = u"Автоматически образмеривает оси плана по маске маркировки. Shift+клик — настройки."
__author__ = "Pipers"

from Autodesk.Revit.DB import Element, ViewPlan
from pyrevit import revit, forms, script, EXEC_PARAMS
from lowlife import grid_dimensions, grid_dimensions_settings, select_list
from lowlife.i18n import tr


class DimensionTypeOption(object):
    def __init__(self, dim_type):
        self.dim_type = dim_type
        self.name = Element.Name.GetValue(dim_type)

    def __str__(self):
        return self.name


if EXEC_PARAMS.config_mode:
    edited = grid_dimensions_settings.get_settings_interactive()
    forms.alert(tr(u"Отменено, настройки не изменены.") if edited is None
                else tr(u"Настройки сохранены."))
    script.exit()

doc = revit.doc
view = doc.ActiveView
if not isinstance(view, ViewPlan) or view.IsTemplate:
    forms.alert(tr(u"Откройте план для образмеривания осей."), exitscript=True)

settings = grid_dimensions_settings.get_settings_silent()
grid_dimensions_settings.require(settings, ["grid_name_mask"])
groups, skipped = grid_dimensions.collect_groups(doc, view, settings["grid_name_mask"])
if not groups:
    forms.alert(tr(u"На плане не найдено хотя бы двух параллельных прямых осей по маске «{}». "
                   u"Проверьте маску в настройках (Shift+клик) и видимость осей.").format(
                       settings["grid_name_mask"]), exitscript=True)

types = grid_dimensions.linear_dimension_types(doc)
if not types:
    forms.alert(tr(u"В проекте не найдены линейные стили размеров."), exitscript=True)
options = sorted([DimensionTypeOption(t) for t in types], key=lambda t: t.name)
selected = select_list.SelectFromList.show(
    options, title=tr(u"Выберите стиль размеров"),
    button_name=tr(u"Создать размеры"), multiselect=False)
if not selected:
    script.exit()

with revit.Transaction("Create Grid Dimensions"):
    chains, totals = grid_dimensions.create_dimensions(
        doc, view, groups, selected.dim_type, settings["offset_mm"], settings["total_gap_mm"])

forms.alert(tr(u"Готово. Размерных цепочек: {}. Общих размеров: {}. Пропущено дуговых осей: {}.").format(
    len(chains), len(totals), skipped))
