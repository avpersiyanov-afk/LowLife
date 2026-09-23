# -*- coding: utf-8 -*-

__title__ = u"Двухуровневые\nлоты"
__doc__ = (
    u"Анализирует помещения связанной модели (АР): раскладывает их по "
    u"уровням, сортирует по имени лота и номеру секции и находит "
    u"двухуровневые лоты — те, у которых помещения с одинаковым именем "
    u"лота стоят на двух и более уровнях. Отчёт — в окне вывода pyRevit "
    u"(сначала список двухуровневых лотов, затем помещения по уровням), "
    u"по желанию — выгрузка в Excel. Модель не меняет.\n\n"
    u"Shift+клик — настройки (параметры имени лота и номера секции)."
)
__author__ = "Pipers"

from pyrevit import revit, forms, script, EXEC_PARAMS

from lowlife import room_lots, room_lots_settings
from lowlife.xlsx_io import write_xlsx

doc = revit.doc


try:
    config_mode = bool(EXEC_PARAMS.config_mode)
except Exception:
    config_mode = False

if config_mode:
    edited = room_lots_settings.get_settings_interactive()
    forms.alert(
        u"Отменено, настройки не изменены." if edited is None
        else u"Настройки сохранены."
    )
    script.exit()


settings = room_lots_settings.get_settings_silent()
room_lots_settings.require(settings, ["lot_param_name"])
lot_param = settings["lot_param_name"].strip()
section_param = (settings.get("section_param_name") or u"").strip()

sources = room_lots.get_link_sources(doc)
if not sources:
    forms.alert(
        u"Не найдено ни одной загруженной связи с помещениями. Убедитесь, "
        u"что связь с АР загружена и в ней расставлены помещения.",
        exitscript=True
    )

if len(sources) > 1:
    sources = forms.SelectFromList.show(
        sources,
        title=u"Связи для анализа лотов (можно несколько)",
        button_name=u"Анализировать",
        multiselect=True
    )
    if not sources:
        script.exit()

rooms, skipped = room_lots.collect_rooms(sources, lot_param, section_param)
if not rooms:
    forms.alert(u"В выбранных связях нет размещённых помещений.", exitscript=True)

with_lot = [r for r in rooms if r.lot]
if not with_lot:
    forms.alert(
        u"Ни у одного помещения не заполнен параметр «{}». Проверьте имя "
        u"параметра в настройках (Shift+клик по кнопке).".format(lot_param),
        exitscript=True
    )

multi_link = len(sources) > 1
levels = room_lots.group_by_level(rooms)
lots = room_lots.group_by_lot(rooms)
multi = [lot for lot in lots if lot.is_multilevel()]
multi_keys = set((lot.link_name, lot.lot) for lot in multi)


def _is_multi(r):
    return (r.link_name, r.lot) in multi_keys


def _rooms_by_level(lot):
    parts = []
    for level_name, _elev in lot.levels():
        numbers = [r.number or u"?" for r in lot.rooms if r.level_name == level_name]
        parts.append(u"{}: {}".format(level_name, u", ".join(numbers)))
    return u"; ".join(parts)


output = script.get_output()
output.print_md(u"## Лоты помещений связи")
output.print_md(
    u"Параметр лота: **{}**, секции: **{}**. Связи: {}. Помещений: {} "
    u"(без имени лота: {}), лотов: {}, из них на нескольких уровнях: **{}**.".format(
        lot_param, section_param or u"—",
        u", ".join(s.name for s in sources),
        len(rooms), len(rooms) - len(with_lot), len(lots), len(multi)
    )
)

output.print_md(u"### Двухуровневые лоты ({})".format(len(multi)))
if multi:
    columns = [u"Имя лота", u"Секция", u"Уровни", u"Помещ.", u"Номера помещений по уровням"]
    if multi_link:
        columns.append(u"Связь")
    table = []
    for lot in multi:
        row = [
            lot.lot,
            u", ".join(lot.sections()) or u"—",
            u" + ".join(name for name, _e in lot.levels()),
            len(lot.rooms),
            _rooms_by_level(lot),
        ]
        if multi_link:
            row.append(lot.link_name)
        table.append(row)
    output.print_table(table_data=table, columns=columns)
else:
    output.print_md(u"Лотов с помещениями на нескольких уровнях не найдено.")

level_columns = [u"Имя лота", u"Секция", u"Номер", u"Имя помещения", u"2 ур.", u"ID"]
if multi_link:
    level_columns.append(u"Связь")

for level_name, _elev, level_rooms in levels:
    output.print_md(u"### {} ({})".format(level_name, len(level_rooms)))
    table = []
    for r in level_rooms:
        row = [
            r.lot or u"—", r.section or u"—", r.number or u"?", r.name or u"",
            u"✔" if _is_multi(r) else u"", r.room_id,
        ]
        if multi_link:
            row.append(r.link_name)
        table.append(row)
    output.print_table(table_data=table, columns=level_columns)


summary = (
    u"Помещений: {}\nЛотов: {}\nДвухуровневых лотов: {}\n"
    u"Уровней: {}{}\n\nПодробности — в окне вывода pyRevit.".format(
        len(rooms), len(lots), len(multi), len(levels),
        u"\nПропущено неразмещённых помещений: {}".format(skipped) if skipped else u""
    )
)

if forms.alert(summary + u"\n\nСохранить отчёт в Excel?", yes=True, no=True):
    path = forms.save_file(file_ext='xlsx', default_name=u"Лоты")
    if path:
        rows = [[u"Уровень", u"Имя лота", u"Секция", u"Номер", u"Имя помещения",
                 u"Двухуровневый", u"ID", u"Связь"]]
        for level_name, _elev, level_rooms in levels:
            for r in level_rooms:
                rows.append([
                    level_name, r.lot, r.section, r.number, r.name,
                    u"да" if _is_multi(r) else u"", r.room_id, r.link_name,
                ])
        write_xlsx(path, rows, sheet_name=u"Лоты",
                   col_widths=[16, 20, 10, 10, 30, 14, 10, 30])
        forms.alert(u"Сохранено:\n{}".format(path))
