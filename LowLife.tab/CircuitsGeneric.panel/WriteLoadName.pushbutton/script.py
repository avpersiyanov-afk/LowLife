# -*- coding: utf-8 -*-
__title__ = u"Имя\nнагрузки"
__doc__ = (
    u"Записывает электрическим цепям имя, собранное по маске из двух "
    u"параметров семейства. Выделите семейства до запуска или выберите их "
    u"рамкой/кликами — для каждого находятся его электрические цепи, и в "
    u"параметр цепи из настроек (пусто — штатное «Имя нагрузки») пишется "
    u"текст по маске: {1} — значение первого параметра, {2} — второго "
    u"(сначала параметр экземпляра, затем типа).\n\n"
    u"Семейства без цепи или без значений параметров пропускаются; если в "
    u"одну цепь входят несколько выбранных семейств с разными значениями, "
    u"цепь не меняется — всё это перечисляется в окне вывода pyRevit.\n\n"
    u"Shift+клик — настройки (параметры, маска, параметр цепи)."
)
__author__ = "Pipers"

from pyrevit import revit, forms, script, EXEC_PARAMS

from lowlife import name_by_mask
from lowlife.name_by_mask_settings import LOAD_NAME

doc = revit.doc
uidoc = revit.uidoc


try:
    config_mode = bool(EXEC_PARAMS.config_mode)
except Exception:
    config_mode = False

if config_mode:
    edited = LOAD_NAME.get_settings_interactive()
    forms.alert(
        u"Отменено, настройки не изменены." if edited is None
        else u"Настройки сохранены."
    )
    script.exit()


settings = LOAD_NAME.get_settings_silent()
LOAD_NAME.require(settings, ["load_name_first_param", "load_name_mask"])
error = name_by_mask.check_mask_params(
    settings["load_name_mask"],
    settings.get("load_name_first_param"),
    settings.get("load_name_second_param"),
)
if error:
    forms.alert(error + u"\n\nShift+клик по кнопке — настройки.", exitscript=True)

elements, _dropped = name_by_mask.selected_or_picked(
    uidoc, doc,
    u"Выберите семейства, чьим цепям записать имя нагрузки (рамкой и/или "
    u"кликами), подтвердите Enter",
)

with revit.Transaction(u"LowLife: имя нагрузки по маске"):
    result = name_by_mask.write_load_names(doc, elements, settings)

if result.skipped:
    output = script.get_output()
    output.print_md(u"### Пропущено ({})".format(len(result.skipped)))
    for line in result.skipped[:300]:
        output.print_md(u"- {}".format(line))

forms.alert(
    u"Готово.\n\nВыбрано семейств: {}\nЦепей записано: {}\nУже совпадало: {}\n"
    u"Пропущено: {}{}".format(
        len(elements), result.written, result.unchanged, len(result.skipped),
        u"\n\nПодробности — в окне вывода pyRevit." if result.skipped else u""
    )
)
