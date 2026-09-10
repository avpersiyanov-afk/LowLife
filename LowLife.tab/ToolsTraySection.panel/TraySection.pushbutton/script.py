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
    SECTION_GAP_MM, TITLE_BAND_MM, build_tray_section, list_sections, mm_to_feet,
    read_cables, renumber_cables
)

doc = revit.doc
uidoc = revit.uidoc


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
    all_sections, title=u"Участки лотков (можно несколько — построятся стопкой сверху вниз)",
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
    jobs.append((name, section_cables))

try:
    origin = uidoc.Selection.PickPoint(
        u"Укажите точку вставки (левый нижний угол первого сечения); дальше участки уйдут вниз"
    )
except OperationCanceledException:
    pyrevit_script.exit()

gap_ft = mm_to_feet(SECTION_GAP_MM)
title_band_ft = mm_to_feet(TITLE_BAND_MM)
unplaced_by_section = []

with revit.Transaction(u"Сечения кабельных лотков"):
    prev_lowest_y = None  # самая нижняя точка предыдущего участка
    for name, section_cables in jobs:
        first_cable = section_cables[0]
        tray_h_ft = mm_to_feet(first_cable.tray_height)
        if prev_lowest_y is None:
            insertion_y = origin.Y
        else:
            # подпись нового участка должна начаться на gap ниже низа предыдущего
            insertion_y = prev_lowest_y - gap_ft - title_band_ft - tray_h_ft
        insertion_point = XYZ(origin.X, insertion_y, origin.Z)
        placed, unplaced, fill_percent, extent_down_ft = build_tray_section(
            doc, view, name, first_cable.tray_width, first_cable.tray_height,
            section_cables, insertion_point, show_marks, show_table
        )
        if unplaced:
            unplaced_by_section.append((name, Counter(c.mark for c in unplaced)))
        prev_lowest_y = insertion_y - extent_down_ft

# Отчёт не показываем. Единственное, о чём предупреждаем, — кабели, которые
# физически не влезли в лоток по высоте (иначе они молча пропали бы с чертежа).
if unplaced_by_section:
    lines = [u"Не поместились в лоток (не нарисованы):", u""]
    for name, counts in unplaced_by_section:
        parts = u", ".join(u"марка {} — {} шт.".format(m, n) for m, n in sorted(counts.items()))
        lines.append(u"{}: {}".format(name, parts))
    forms.alert(u"\n".join(lines))
