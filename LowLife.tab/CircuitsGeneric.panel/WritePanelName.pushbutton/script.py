# -*- coding: utf-8 -*-
__title__ = u"Имя\nпанели"
__doc__ = (
    u"Записывает электрооборудованию в штатный параметр «Имя панели» текст, "
    u"собранный по маске из двух его параметров: {1} — значение первого "
    u"параметра, {2} — второго (сначала параметр экземпляра, затем типа). "
    u"Выделите электрооборудование до запуска или выберите его рамкой/"
    u"кликами — элементы других категорий отбрасываются.\n\n"
    u"Элементы без значений параметров пропускаются и перечисляются в окне "
    u"вывода pyRevit.\n\n"
    u"Shift+клик — настройки (параметры и маска)."
)
__author__ = "Pipers"

from pyrevit import revit, forms, script, EXEC_PARAMS
from lowlife.i18n import tr

from lowlife import name_by_mask
from lowlife.name_by_mask_settings import PANEL_NAME

doc = revit.doc
uidoc = revit.uidoc


try:
    config_mode = bool(EXEC_PARAMS.config_mode)
except Exception:
    config_mode = False

if config_mode:
    edited = PANEL_NAME.get_settings_interactive()
    forms.alert(
        tr(u"Отменено, настройки не изменены.") if edited is None
        else tr(u"Настройки сохранены.")
    )
    script.exit()


settings = PANEL_NAME.get_settings_silent()
PANEL_NAME.require(settings, ["panel_name_first_param", "panel_name_mask"])
error = name_by_mask.check_mask_params(
    settings["panel_name_mask"],
    settings.get("panel_name_first_param"),
    settings.get("panel_name_second_param"),
)
if error:
    forms.alert(error + tr(u"\n\nShift+клик по кнопке — настройки."), exitscript=True)

panels, dropped = name_by_mask.selected_or_picked(
    uidoc, doc,
    tr(u"Выберите электрооборудование (рамкой и/или кликами), подтвердите Enter"),
    keep=name_by_mask.is_electrical_equipment,
)
if not panels:
    forms.alert(tr(u"Среди выбранного нет электрооборудования."), exitscript=True)

with revit.Transaction(tr(u"LowLife: имя панели по маске")):
    result = name_by_mask.write_panel_names(doc, panels, settings)

if result.skipped:
    output = script.get_output()
    output.print_md(tr(u"### Пропущено ({})").format(len(result.skipped)))
    for line in result.skipped[:300]:
        output.print_md(u"- {}".format(line))

forms.alert(
    tr(u"Готово.\n\nЭлектрооборудования выбрано: {}{}\nЗаписано: {}\n"
    u"Уже совпадало: {}\nПропущено: {}{}").format(
        len(panels),
        tr(u" (не электрооборудование, отброшено: {})").format(dropped) if dropped else u"",
        result.written, result.unchanged, len(result.skipped),
        tr(u"\n\nПодробности — в окне вывода pyRevit.") if result.skipped else u""
    )
)
