# -*- coding: utf-8 -*-

__title__ = u"СС1-8Mile"
__doc__ = (
    u"Расстановка оборудования СС1. Кроссы: два в каждой шахте СС на каждом "
    u"отмеченном уровне, через который шахта проходит. Кабельные подводы: у "
    u"двери из прихожей в коридор/вестибюль по связи АР (у двухуровневой "
    u"квартиры — только в нижней прихожей). Перед расстановкой все "
    u"экземпляры выбранных типоразмеров кросса и подвода на отмеченных "
    u"уровнях удаляются.\n\n"
    u"Shift+клик — настройки (шахта СС, семейства и типы кросса и подвода, помещения, параметры, высоты)."
)
__author__ = "Pipers"

from pyrevit import revit, forms, script, EXEC_PARAMS

from lowlife import ss1_easy, ss1_easy_settings

doc = revit.doc
TITLE = u"СС1-8Mile"


try:
    config_mode = bool(EXEC_PARAMS.config_mode)
except Exception:
    config_mode = False

if config_mode:
    saved = ss1_easy_settings.show_settings_window(doc)
    forms.alert(u"Настройки сохранены." if saved else u"Отменено, семейства не изменены.")
    script.exit()


settings = ss1_easy_settings.load_all()
ss1_easy_settings.require_all(settings)

cross_symbol = ss1_easy.find_symbol(doc, settings["cross_family"], settings["cross_type"])
feed_symbol = ss1_easy.find_symbol(doc, settings["feed_family"], settings["feed_type"])
missing = []
if cross_symbol is None:
    missing.append(u"Кросс: {} : {}".format(settings["cross_family"], settings["cross_type"]))
if feed_symbol is None:
    missing.append(u"Кабельный подвод: {} : {}".format(settings["feed_family"], settings["feed_type"]))
if missing:
    forms.alert(
        u"В проекте не найдены типоразмеры:\n\n{}\n\n"
        u"Загрузите семейства или выберите другие: Shift+клик по кнопке.".format(u"\n".join(missing)),
        title=TITLE, exitscript=True
    )

levels, offset_mm = ss1_easy.ask_levels_and_offset(doc, settings["feed_height_mm"])
if not levels:
    script.exit()

with revit.Transaction(u"СС1-8Mile: кроссы и кабельные подводы"):
    result = ss1_easy.run(doc, levels, offset_mm, settings, cross_symbol, feed_symbol)


output = script.get_output()
output.print_md(u"## СС1-8Mile")
output.print_md(u"**Уровни:** " + u", ".join(level.Name for level in levels))
output.print_md(u"**Смещение подвода:** {:.0f} мм".format(float(offset_mm)))
output.print_md(u"### Кроссы")
output.print_md(u"- удалено старых: {}".format(result.deleted_crosses))
output.print_md(u"- шахт СС найдено: {}".format(result.shafts))
output.print_md(u"- установлено кроссов: {}".format(result.crosses))
output.print_md(u"### Кабельные подводы")
output.print_md(u"- удалено старых: {}".format(result.deleted_feeds))
output.print_md(u"- подходящих дверей: {}".format(result.doors))
output.print_md(u"- установлено подводов: {}".format(result.feeds))
if result.diagnostics:
    output.print_md(u"### Диагностика")
    for line in result.diagnostics:
        print(line)

warnings = [line for line in result.diagnostics if line.startswith(u"ВНИМАНИЕ")]
message = (
    u"Готово.\n\n"
    u"Шахт СС: {}\nКроссов установлено: {} (удалено старых: {})\n\n"
    u"Подходящих дверей: {}\nПодводов установлено: {} (удалено старых: {})"
).format(result.shafts, result.crosses, result.deleted_crosses,
         result.doors, result.feeds, result.deleted_feeds)
if warnings:
    message += u"\n\nПомещений без имени лота: {} — см. отчёт.".format(len(warnings))
if len(result.diagnostics) > len(warnings):
    message += u"\nДругих сообщений диагностики: {} — см. отчёт.".format(
        len(result.diagnostics) - len(warnings))
forms.alert(message, title=TITLE)
