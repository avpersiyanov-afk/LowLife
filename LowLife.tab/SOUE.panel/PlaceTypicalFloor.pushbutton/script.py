# -*- coding: utf-8 -*-

__title__ = u"СОУЭ - расстановка\nтиповой этаж"
__doc__ = (
    u"Расстановка оповещателей СОУЭ по всем помещениям связей АР на отмеченных "
    u"уровнях: в каждой квартире (лоте) — один на стене прихожей (или в первом "
    u"найденном помещении из списка в настройках); во всех остальных помещениях, "
    u"кроме исключённых, — по акустическому расчёту (уровень не ниже шума + 15 дБ "
    u"на высоте 1,5 м): настенные, а при подвесном потолке — потолочные. SPL и "
    u"мощность берутся из параметров оповещателя, уровень шума — из таблицы "
    u"помещений объекта. Перед расстановкой все экземпляры выбранных типов на "
    u"отмеченных уровнях удаляются.\n\n"
    u"Shift+клик — настройки (типы оповещателей, таблица помещений: шум и исключения, "
    u"параметры)."
)
__author__ = "Pipers"

from pyrevit import revit, forms, script, EXEC_PARAMS

from lowlife import soue_floor, soue_floor_rooms, soue_floor_settings

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

table = soue_floor_settings.load_room_table()
tasks, messages = soue_floor.gather(doc, levels, settings, table)
if not tasks:
    forms.alert(u"На отмеченных уровнях нет помещений для оснащения.", title=TITLE, exitscript=True)

if soue_floor_settings.SYMBOL_WALL in symbols:
    lacking = soue_floor.missing_noise_rows(tasks, table)
    if lacking:
        if soue_floor_rooms.ask_missing_noise(lacking) is None:
            script.exit()
        table = soue_floor_settings.load_room_table()
        # исключённые только что — убрать из расстановки
        tasks, messages = soue_floor.gather(doc, levels, settings, table)

with forms.ProgressBar(title=u"СОУЭ: помещения {value} из {max_value}", cancellable=False) as bar:
    def progress(index, total):
        if index % 5 == 0:
            bar.update_progress(index, total)

    with revit.Transaction(u"СОУЭ: оповещатели"):
        result = soue_floor.run(doc, levels, tasks, settings, symbols, table, progress)


output = script.get_output()
output.print_md(u"## СОУЭ - расстановка типовой этаж")
output.print_md(u"**Уровни:** " + u", ".join(level.Name for level in levels))
output.print_md(u"- удалено старых оповещателей: {}".format(result.deleted))
labels = [(soue_floor.core.ROLE_APARTMENT, u"Квартиры"), (soue_floor.core.ROLE_ROOM, u"Остальные помещения")]
lines = []
for role, label in labels:
    line = u"{}: помещений {}, оповещателей {}".format(label, result.rooms[role], result.placed[role])
    if result.failed[role]:
        line += u", не удалось {}".format(result.failed[role])
    lines.append(line)
    output.print_md(u"- " + line)
if result.skipped_no_noise:
    output.print_md(u"- пропущено без уровня шума: {}".format(result.skipped_no_noise))
if result.report:
    output.print_md(u"### Акустический расчёт")
    table_rows = []
    for row in result.report:
        table_rows.append([
            row.link, row.level, row.name, u"{}".format(row.room_id), row.category or u"—",
            u"{:.0f}".format(float(row.noise)), row.mount,
            u"{:.0f}".format(float(row.height_mm)), u"{:.1f}".format(float(row.reach_m)),
            u"{}".format(row.count),
            u"{} из {}".format(row.uncovered, row.samples) if row.uncovered else u"—",
        ])
    output.print_table(
        table_rows,
        columns=[u"Связь", u"Уровень", u"Помещение", u"Id", u"Категория", u"N, дБА",
                 u"Установка", u"h, мм", u"R (L), м", u"Оповещателей", u"Не озвучено"])
diagnostics = messages + result.diagnostics
if diagnostics:
    output.print_md(u"### Диагностика")
    for line in diagnostics:
        print(line)

message = u"Готово.\n\nУдалено старых: {}\n\n{}".format(result.deleted, u"\n".join(lines))
if diagnostics:
    message += u"\n\nСообщений диагностики: {} — см. отчёт.".format(len(diagnostics))
forms.alert(message, title=TITLE)
