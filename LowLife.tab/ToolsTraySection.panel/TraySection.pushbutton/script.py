# -*- coding: utf-8 -*-
__title__ = u"Сечение\nлотка"
__author__ = "Pipers"

from collections import Counter

import clr
clr.AddReference('RevitAPI')
clr.AddReference('RevitAPIUI')

from Autodesk.Revit.DB import XYZ, ViewDrafting
from Autodesk.Revit.Exceptions import OperationCanceledException

from pyrevit import revit, forms, script as pyrevit_script

from lowlife.tray_section import (
    SECTION_GAP_MM, build_tray_section, format_number, list_sections, mm_to_feet,
    read_cables, renumber_cables, round_half_up
)

doc = revit.doc
uidoc = revit.uidoc
output = pyrevit_script.get_output()


view = doc.ActiveView
if not isinstance(view, ViewDrafting):
    forms.alert(u"Откройте чертёжный вид (Drafting View) и запустите кнопку ещё раз.", exitscript=True)

path = forms.pick_file(file_ext='xlsx')
if not path:
    pyrevit_script.exit()

cables, error = read_cables(path)
if error:
    forms.alert(error, exitscript=True)

all_sections = list_sections(cables)
if not all_sections:
    forms.alert(u"В файле не заполнен ни один участок (столбец «Участок»).", exitscript=True)

chosen = forms.SelectFromList.show(
    all_sections, title=u"Участки лотков (можно несколько — построятся в ряд слева направо)",
    button_name=u"Построить", multiselect=True
)
if not chosen:
    pyrevit_script.exit()

# порядок в ряду — как в файле (первое появление участка), а не как кликали
chosen_set = set(chosen)
sections = [s for s in all_sections if s in chosen_set]

show_marks = bool(forms.alert(u"Показывать марки кабелей на кружках?", yes=True, no=True))
show_table = bool(forms.alert(u"Показывать сводную таблицу рядом с каждым сечением?", yes=True, no=True))

# готовим данные по каждому участку заранее — чтобы не рисовать половину,
# а потом упереться в незаполненный размер лотка
jobs = []
for name in sections:
    section_cables = [c for c in cables if c.section == name]
    first_cable = section_cables[0]
    if first_cable.tray_width <= 0 or first_cable.tray_height <= 0:
        forms.alert(
            u"В файле не заданы размеры лотка для участка «{}» (ширина: {}, высота: {}).".format(
                name, first_cable.tray_width, first_cable.tray_height
            ),
            exitscript=True
        )
    renumber_cables(section_cables)
    jobs.append((name, section_cables, first_cable))

try:
    origin = uidoc.Selection.PickPoint(
        u"Укажите точку вставки (левый нижний угол первого сечения); дальше участки уйдут вправо"
    )
except OperationCanceledException:
    pyrevit_script.exit()

gap_ft = mm_to_feet(SECTION_GAP_MM)
results = []

with revit.Transaction(u"Сечения кабельных лотков"):
    x_cursor = origin.X
    for name, section_cables, first_cable in jobs:
        insertion_point = XYZ(x_cursor, origin.Y, origin.Z)
        placed, unplaced, fill_percent, footprint_ft = build_tray_section(
            doc, view, name, first_cable.tray_width, first_cable.tray_height,
            section_cables, insertion_point, show_marks, show_table
        )
        results.append({
            "name": name, "first": first_cable, "placed": placed, "unplaced": unplaced,
            "fill": fill_percent, "requested": sum(c.quantity for c in section_cables),
        })
        x_cursor += footprint_ft + gap_ft

output.print_md(u"### Сечения лотков — участков: {}".format(len(results)))
total_unplaced = 0
for r in results:
    output.print_md(u"**{}** — лоток {}×{} мм, кабелей {}/{}, заполнение {}%{}".format(
        r["name"], format_number(r["first"].tray_width), format_number(r["first"].tray_height),
        len(r["placed"]), r["requested"], round_half_up(r["fill"]),
        u"" if r["first"].fill_percent == 0 else u" (в Excel {}%)".format(format_number(r["first"].fill_percent))
    ))
    if r["unplaced"]:
        total_unplaced += len(r["unplaced"])
        counts = Counter(c.mark for c in r["unplaced"])
        for mark, n in sorted(counts.items()):
            output.print_md(u"- не уместилось: марка {} — {} шт.".format(mark, n))

forms.alert(
    u"Готово.\n\n"
    u"Построено сечений: {}\n"
    u"Всего уложено кабелей: {}\n"
    u"{}"
    u"Подробности — в окне вывода pyRevit.".format(
        len(results),
        sum(len(r["placed"]) for r in results),
        u"" if not total_unplaced else u"Не уместилось всего: {} шт.\n".format(total_unplaced),
    )
)
