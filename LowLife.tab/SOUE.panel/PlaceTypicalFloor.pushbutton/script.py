# -*- coding: utf-8 -*-

__title__ = u"СОУЭ - расстановка\nтиповой этаж"
__doc__ = (
    u"Расстановка оповещателей СОУЭ на типовом этаже по помещениям связи АР: "
    u"в каждой квартире (лоте) — один на стене прихожей (или в первом найденном "
    u"помещении из списка в настройках), в коридорах МОП и лифтовых холлах — по "
    u"акустическому расчёту (количество и места — чтобы уровень звука везде был "
    u"не ниже шума + 15 дБ). Для квартир, коридоров и лифтовых холлов — свой тип "
    u"оповещателя, установка на стену или на потолок и высота; потолок "
    u"определяется сам — подвесной (оповещатель в его плоскость) или перекрытие "
    u"(свой тип под плитой). Перед расстановкой все экземпляры выбранных типов "
    u"на отмеченных уровнях удаляются.\n\n"
    u"Shift+клик — настройки (семейства и типы, установка, высоты, расчёт, помещения, параметры)."
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

symbols, missing = soue_floor.find_symbols(doc, settings)
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
    if settings.get(mount_key) == soue_floor_settings.core.MOUNT_WALL:
        output.print_md(u"- установка: на стену, {:.0f} мм от уровня".format(
            float(settings.get(height_key) or 0.0)))
    else:
        output.print_md(u"- установка: {} (высота — по потолку/перекрытию)".format(mount.lower()))
    output.print_md(u"- помещений: {}".format(result.rooms[role]))
    output.print_md(u"- установлено оповещателей: {}".format(result.placed[role]))
    if result.failed[role]:
        output.print_md(u"- не удалось: {}".format(result.failed[role]))
if result.mop_rows:
    output.print_md(u"### Акустический расчёт МОП")
    table = []
    for row in result.mop_rows:
        table.append([
            row.link, row.name, u"{}".format(row.room_id), row.ceiling,
            u"{:.0f}".format(float(row.height_mm)), u"{:.1f}".format(float(row.reach_m)),
            u"{}".format(row.count),
            u"{} из {}".format(row.uncovered, row.samples) if row.uncovered else u"—",
        ])
    output.print_table(
        table,
        columns=[u"Связь", u"Помещение", u"Id", u"Установка", u"h, мм",
                 u"R (L), м", u"Оповещателей", u"Не озвучено"])
if result.diagnostics:
    output.print_md(u"### Диагностика")
    for line in result.diagnostics:
        print(line)

message = u"Готово.\n\nУдалено старых: {}\n\n{}".format(result.deleted, u"\n".join(lines))
if result.diagnostics:
    message += u"\n\nСообщений диагностики: {} — см. отчёт.".format(len(result.diagnostics))
forms.alert(message, title=TITLE)
