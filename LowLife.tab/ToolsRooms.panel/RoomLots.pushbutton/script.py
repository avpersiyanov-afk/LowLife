# -*- coding: utf-8 -*-

__title__ = u"Двухуровневые\nлоты"
__doc__ = (
    u"Анализирует помещения связанной модели (АР), группирует их по имени "
    u"лота и показывает только двухуровневые лоты — те, у которых "
    u"помещения с одинаковым именем лота стоят на двух и более уровнях: "
    u"имя лота, секция, уровни. Список отсортирован по имени лота и "
    u"номеру секции, выводится в окно pyRevit, по желанию — выгрузка в "
    u"Excel. Модель не меняет.\n\n"
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
lots = room_lots.group_by_lot(rooms)
multi = [lot for lot in lots if lot.is_multilevel()]


def _lot_row(lot):
    row = [
        lot.lot,
        u", ".join(lot.sections()) or u"—",
        u" + ".join(name for name, _e in lot.levels()),
    ]
    if multi_link:
        row.append(lot.link_name)
    return row


columns = [u"Имя лота", u"Секция", u"Уровни"]
if multi_link:
    columns.append(u"Связь")

output = script.get_output()
output.print_md(u"## Двухуровневые лоты ({})".format(len(multi)))
output.print_md(
    u"Параметр лота: **{}**, секции: **{}**. Связи: {}. Лотов всего: {}, "
    u"из них на нескольких уровнях: **{}**.".format(
        lot_param, section_param or u"—",
        u", ".join(s.name for s in sources), len(lots), len(multi)
    )
)
if multi:
    output.print_table(table_data=[_lot_row(lot) for lot in multi], columns=columns)
else:
    output.print_md(u"Лотов с помещениями на нескольких уровнях не найдено.")


summary = u"Лотов всего: {}\nДвухуровневых лотов: {}{}\n\nСписок — в окне вывода pyRevit.".format(
    len(lots), len(multi),
    u"\nПропущено неразмещённых помещений: {}".format(skipped) if skipped else u""
)

if not multi:
    forms.alert(summary)
elif forms.alert(summary + u"\n\nСохранить список в Excel?", yes=True, no=True):
    path = forms.save_file(file_ext='xlsx', default_name=u"Двухуровневые лоты")
    if path:
        rows = [columns] + [_lot_row(lot) for lot in multi]
        write_xlsx(path, rows, sheet_name=u"Лоты", col_widths=[24, 14, 40, 30])
        forms.alert(u"Сохранено:\n{}".format(path))
