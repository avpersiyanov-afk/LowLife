# -*- coding: utf-8 -*-

__title__ = u"СОУЭ - расстановка\nтиповой этаж"
__doc__ = (
    u"Расстановка оповещателей СОУЭ на типовом этаже по помещениям связи АР: "
    u"в каждой квартире (лоте) — один на стене прихожей (или в первом найденном "
    u"помещении из списка в настройках), в коридорах МОП и лифтовых холлах — по "
    u"одному на помещение или с заданным шагом. Для квартир, коридоров и "
    u"лифтовых холлов — свой тип оповещателя, установка на стену или на потолок "
    u"и высота. Перед расстановкой все экземпляры выбранных типов на отмеченных "
    u"уровнях удаляются.\n\n"
    u"Shift+клик — настройки (семейства и типы, установка, высоты, помещения, параметры)."
)
__author__ = "Pipers"

from pyrevit import revit, forms, script, EXEC_PARAMS

from lowlife import soue_floor, soue_floor_settings

doc = revit.doc
TITLE = u"СОУЭ - расстановка типовой этаж"


try:
    config_mode = bool(EXEC_PARAMS.config_mode)
except Exception:
    config_mode = False

if config_mode:
    saved = soue_floor_settings.show_settings_window(doc)
    forms.alert(u"Настройки сохранены." if saved else u"Отменено, настройки не изменены.")
    script.exit()


settings = soue_floor_settings.load_all()
soue_floor_settings.require_all(settings)

symbols = {}
missing = []
for role, family_key, type_key, _, _, label, _, _ in soue_floor_settings.ROLE_KEYS:
    if not settings.get(family_key) or not settings.get(type_key):
        continue
    symbol = soue_floor.find_symbol(doc, settings[family_key], settings[type_key])
    if symbol is None:
        missing.append(u"{}: {} : {}".format(label, settings[family_key], settings[type_key]))
    else:
        symbols[role] = symbol
if missing:
    forms.alert(
        u"В проекте не найдены типоразмеры:\n\n{}\n\n"
        u"Загрузите семейства или выберите другие: Shift+клик по кнопке.".format(u"\n".join(missing)),
        title=TITLE, exitscript=True
    )

levels = soue_floor.ask_levels(doc, TITLE)
if not levels:
    script.exit()

with revit.Transaction(u"СОУЭ: оповещатели типового этажа"):
    result = soue_floor.run(doc, levels, settings, symbols)


output = script.get_output()
output.print_md(u"## СОУЭ - расстановка типовой этаж")
output.print_md(u"**Уровни:** " + u", ".join(level.Name for level in levels))
output.print_md(u"- удалено старых оповещателей: {}".format(result.deleted))
output.print_md(u"- связей просмотрено: {}".format(result.links))
lines = []
for role, _, _, mount_key, height_key, label, _, _ in soue_floor_settings.ROLE_KEYS:
    if role not in symbols:
        continue
    mount = dict(soue_floor_settings.MOUNT_LABELS).get(settings.get(mount_key), u"")
    line = u"{}: помещений {}, установлено {}".format(
        label, result.rooms[role], result.placed[role])
    if result.failed[role]:
        line += u", ошибок {}".format(result.failed[role])
    lines.append(line)
    output.print_md(u"### {}".format(label))
    output.print_md(u"- установка: {}, {:.0f} мм от уровня".format(
        mount.lower(), float(settings.get(height_key) or 0.0)))
    output.print_md(u"- помещений: {}".format(result.rooms[role]))
    output.print_md(u"- установлено оповещателей: {}".format(result.placed[role]))
    if result.failed[role]:
        output.print_md(u"- не удалось: {}".format(result.failed[role]))
if result.diagnostics:
    output.print_md(u"### Диагностика")
    for line in result.diagnostics:
        print(line)

message = u"Готово.\n\nУдалено старых: {}\n\n{}".format(result.deleted, u"\n".join(lines))
if result.diagnostics:
    message += u"\n\nСообщений диагностики: {} — см. отчёт.".format(len(result.diagnostics))
forms.alert(message, title=TITLE)
