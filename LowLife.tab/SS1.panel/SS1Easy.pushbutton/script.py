# -*- coding: utf-8 -*-

__title__ = u"СС1-8Mile"
__doc__ = (
    u"Расстановка оборудования СС1. Кроссы: два в каждой шахте СС на каждом "
    u"отмеченном уровне, через который шахта проходит. Кабельные подводы: у "
    u"двери из прихожей в коридор/вестибюль по связи АР (у двухуровневой "
    u"квартиры — только в нижней прихожей), со стороны квартиры. Цепи: от "
    u"кросса №1 шахты своей секции к каждому подводу. Потом — заполнение LOI "
    u"(по настройкам «Заполнение LOI») и адрес устройства подводов по маске. "
    u"Перед расстановкой все "
    u"экземпляры выбранных типоразмеров кросса и подвода на отмеченных "
    u"уровнях удаляются.\n\n"
    u"Shift+клик — настройки (шахта СС, семейства и типы кросса и подвода, помещения, параметры, высоты, адрес)."
)
__author__ = "Pipers"

from pyrevit import revit, forms, script, EXEC_PARAMS
from lowlife.i18n import tr

from lowlife import ss1_easy, ss1_easy_settings

doc = revit.doc
TITLE = tr(u"СС1-8Mile")


try:
    config_mode = bool(EXEC_PARAMS.config_mode)
except Exception:
    config_mode = False

if config_mode:
    saved = ss1_easy_settings.show_settings_window(doc)
    forms.alert(tr(u"Настройки сохранены.") if saved else tr(u"Отменено, семейства не изменены."))
    script.exit()


settings = ss1_easy_settings.load_all()
ss1_easy_settings.require_all(settings)

cross_symbol = ss1_easy.find_symbol(doc, settings["cross_family"], settings["cross_type"])
feed_symbol = ss1_easy.find_symbol(doc, settings["feed_family"], settings["feed_type"])
missing = []
if cross_symbol is None:
    missing.append(tr(u"Кросс: {} : {}").format(settings["cross_family"], settings["cross_type"]))
if feed_symbol is None:
    missing.append(tr(u"Кабельный подвод: {} : {}").format(settings["feed_family"], settings["feed_type"]))
if missing:
    forms.alert(
        tr(u"В проекте не найдены типоразмеры:\n\n{}\n\n"
        u"Загрузите семейства или выберите другие: Shift+клик по кнопке.").format(u"\n".join(missing)),
        title=TITLE, exitscript=True
    )

levels, offset_mm = ss1_easy.ask_levels_and_offset(doc, settings["feed_height_mm"])
if not levels:
    script.exit()

with revit.Transaction(u"СС1-8Mile: кроссы, подводы, цепи, LOI, адреса"):
    result = ss1_easy.run(doc, levels, offset_mm, settings, cross_symbol, feed_symbol)


output = script.get_output()
output.print_md(tr(u"## СС1-8Mile"))
output.print_md(tr(u"**Уровни:** ") + u", ".join(level.Name for level in levels))
output.print_md(tr(u"**Смещение подвода:** {:.0f} мм").format(float(offset_mm)))
output.print_md(tr(u"### Кроссы"))
output.print_md(tr(u"- удалено старых: {}").format(result.deleted_crosses))
output.print_md(tr(u"- шахт СС найдено: {}").format(result.shafts))
output.print_md(tr(u"- установлено кроссов: {}").format(result.crosses))
output.print_md(tr(u"### Кабельные подводы"))
output.print_md(tr(u"- удалено старых: {}").format(result.deleted_feeds))
output.print_md(tr(u"- подходящих дверей: {}").format(result.doors))
output.print_md(tr(u"- установлено подводов: {}").format(result.feeds))
if result.feeds_unoriented:
    output.print_md(tr(u"- без определённой стороны квартиры: {}").format(result.feeds_unoriented))
output.print_md(tr(u"### Цепи кросс №1 → подвод"))
output.print_md(tr(u"- тип цепи: {}").format(settings.get("circuit_system_type")))
output.print_md(tr(u"- создано: {}").format(result.circuits))
output.print_md(tr(u"- не создано: {}").format(result.circuits_failed))
output.print_md(tr(u"### LOI и адрес"))
if result.loi_skipped:
    output.print_md(tr(u"- LOI не заполнено: {}").format(result.loi_skipped))
else:
    output.print_md(tr(u"- LOI заполнено у элементов: {}").format(result.loi_filled))
output.print_md(tr(u"- адресов подводов записано: {}").format(result.addresses))
if result.diagnostics:
    output.print_md(tr(u"### Диагностика"))
    for line in result.diagnostics:
        print(line)

warnings = [line for line in result.diagnostics if line.startswith(tr(u"ВНИМАНИЕ"))]
message = (
    tr(u"Готово.\n\n"
    u"Шахт СС: {}\nКроссов установлено: {} (удалено старых: {})\n\n"
    u"Подходящих дверей: {}\nПодводов установлено: {} (удалено старых: {})\n\n"
    u"Цепей создано: {} (не создано: {})\n"
    u"LOI заполнено: {}\nАдресов записано: {}")
).format(result.shafts, result.crosses, result.deleted_crosses,
         result.doors, result.feeds, result.deleted_feeds,
         result.circuits, result.circuits_failed,
         result.loi_filled if not result.loi_skipped else tr(u"нет — ") + result.loi_skipped,
         result.addresses)
if warnings:
    message += tr(u"\n\nПомещений без имени лота: {} — см. отчёт.").format(len(warnings))
if len(result.diagnostics) > len(warnings):
    message += tr(u"\nДругих сообщений диагностики: {} — см. отчёт.").format(
        len(result.diagnostics) - len(warnings))
forms.alert(message, title=TITLE)
