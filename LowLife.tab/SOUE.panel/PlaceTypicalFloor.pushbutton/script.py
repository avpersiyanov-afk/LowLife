# -*- coding: utf-8 -*-

__title__ = u"СОУЭ - расстановка\nтиповой этаж"
__doc__ = (
    u"Расстановка оповещателей СОУЭ по всем помещениям связей АР на отмеченных "
    u"уровнях: в каждой квартире (лоте) — один на стене прихожей (или в первом "
    u"найденном помещении из списка в настройках); во всех остальных помещениях, "
    u"кроме исключённых, — по акустическому расчёту (уровень не ниже шума + 15 дБ "
    u"на высоте 1,5 м): настенные (на стены и колонны), а при подвесном потолке — "
    u"потолочные. Оповещатель и отвод подбираются из всех типов проекта с "
    u"параметрами SPL/мощность/исполнение, уровень шума — из таблицы помещений "
    u"объекта. Если на отмеченных уровнях уже есть оповещатели, кнопка спросит: "
    u"удалить их и расставить заново или оснастить только помещения без них.\n\n"
    u"Shift+клик — настройки (оповещатель квартир, найденные оповещатели, таблица "
    u"помещений: шум и исключения, параметры)."
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

apartment_symbol, missing = soue_floor.find_apartment_symbol(doc, settings)
if missing:
    forms.alert(
        u"В проекте не найден типоразмер:\n\n{}\n\n"
        u"Загрузите семейство или выберите другое: Shift+клик по кнопке.".format(missing),
        title=TITLE, exitscript=True
    )
speakers, speaker_messages = soue_floor.collect_speakers(doc, settings)
if apartment_symbol is None and not speakers:
    forms.alert(
        u"Нечего ставить: не выбран оповещатель для квартир и в проекте нет типов с "
        u"параметром «{}» для автоподбора.\n\nShift+клик по кнопке — настройки.".format(
            settings.get("spl_param_name") or u""),
        title=TITLE, exitscript=True
    )

levels = soue_floor.ask_levels(doc, TITLE)
if not levels:
    script.exit()

REPLACE = u"Удалить и расставить заново"
KEEP = u"Не удалять: оснастить только помещения без оповещателей"
existing = soue_floor.existing_points(doc, soue_floor.speaker_symbols(apartment_symbol, speakers), levels)
existing_count = sum(len(points) for points in existing.values())
replace = True
if existing_count:
    answer = forms.alert(
        u"На отмеченных уровнях уже стоит оповещателей: {}.\n\n"
        u"«{}» — все они (экземпляры типа квартир и всех типов с параметром SPL) удаляются, "
        u"включая поставленные вручную.\n"
        u"«{}» — ничего не удаляется; помещения, где оповещатель уже есть, пропускаются.".format(
            existing_count, REPLACE, KEEP),
        title=TITLE, options=[REPLACE, KEEP])
    if not answer:
        script.exit()
    replace = answer == REPLACE

table = soue_floor_settings.load_room_table()
tasks, messages = soue_floor.gather(doc, levels, settings, table)
if not tasks:
    forms.alert(u"На отмеченных уровнях нет помещений для оснащения.", title=TITLE, exitscript=True)

if speakers:
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
        result = soue_floor.run(doc, levels, tasks, settings, apartment_symbol, speakers, table,
                                progress, replace)


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
if result.skipped_existing:
    output.print_md(u"- пропущено помещений, где оповещатель уже стоит: {}".format(result.skipped_existing))
if result.skipped_no_noise:
    output.print_md(u"- пропущено без уровня шума: {}".format(result.skipped_no_noise))
if result.report:
    output.print_md(u"### Акустический расчёт")
    table_rows = []
    for row in result.report:
        table_rows.append([
            row.link, row.level, row.name, u"{}".format(row.room_id), row.category or u"—",
            u"{:.0f}".format(float(row.noise)), row.mount,
            u"{} ({:g} Вт)".format(row.speaker, float(row.tap)) if row.speaker else u"—",
            u"{:.0f}".format(float(row.height_mm)), u"{:.1f}".format(float(row.reach_m)),
            u"{}".format(row.count),
            u"{} из {}".format(row.uncovered, row.samples) if row.uncovered else u"—",
        ])
    output.print_table(
        table_rows,
        columns=[u"Связь", u"Уровень", u"Помещение", u"Id", u"Категория", u"N, дБА",
                 u"Установка", u"Оповещатель (отвод)", u"h, мм", u"R (L), м", u"Оповещателей", u"Не озвучено"])
diagnostics = speaker_messages + messages + result.diagnostics
if diagnostics:
    output.print_md(u"### Диагностика")
    for line in diagnostics:
        print(line)

message = u"Готово.\n\nУдалено старых: {}\n\n{}".format(result.deleted, u"\n".join(lines))
if result.skipped_existing:
    message += u"\n\nПропущено помещений с оповещателями: {}".format(result.skipped_existing)
if diagnostics:
    message += u"\n\nСообщений диагностики: {} — см. отчёт.".format(len(diagnostics))
forms.alert(message, title=TITLE)
