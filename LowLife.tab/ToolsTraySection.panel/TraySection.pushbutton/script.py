# -*- coding: utf-8 -*-
__title__ = u"Сечение\nлотка"
__author__ = "Pipers"

from collections import Counter

import clr
clr.AddReference('RevitAPI')
clr.AddReference('RevitAPIUI')

from Autodesk.Revit.DB import ViewDrafting
from Autodesk.Revit.Exceptions import OperationCanceledException

from pyrevit import revit, forms, script as pyrevit_script

from lowlife.tray_section import (
    build_tray_section, format_number, list_sections, read_cables, renumber_cables, round_half_up
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

sections = list_sections(cables)
if not sections:
    forms.alert(u"В файле не заполнен ни один участок (столбец «Участок»).", exitscript=True)

section_name = forms.SelectFromList.show(
    sections, title=u"Участок лотка", button_name=u"Выбрать", multiselect=False
)
if not section_name:
    pyrevit_script.exit()

section_cables = [c for c in cables if c.section == section_name]
if not section_cables:
    forms.alert(u"Нет кабелей на участке «{}».".format(section_name), exitscript=True)

first_cable = section_cables[0]
if first_cable.tray_width <= 0 or first_cable.tray_height <= 0:
    forms.alert(
        u"В файле не заданы размеры лотка для участка «{}» (ширина: {}, высота: {}).".format(
            section_name, first_cable.tray_width, first_cable.tray_height
        ),
        exitscript=True
    )

show_marks = bool(forms.alert(u"Показывать марки кабелей на кружках?", yes=True, no=True))
show_table = bool(forms.alert(u"Показывать сводную таблицу рядом с сечением?", yes=True, no=True))

try:
    point = uidoc.Selection.PickPoint(u"Укажите точку вставки сечения лотка (левый нижний угол)")
except OperationCanceledException:
    pyrevit_script.exit()

renumber_cables(section_cables)

with revit.Transaction(u"Сечение кабельного лотка"):
    placed, unplaced, fill_percent = build_tray_section(
        doc, view, section_name, first_cable.tray_width, first_cable.tray_height,
        section_cables, point, show_marks, show_table
    )

requested = sum(c.quantity for c in section_cables)

output.print_md(u"### Сечение лотка: участок «{}»".format(section_name))
output.print_md(u"Размер лотка: {}×{} мм".format(
    format_number(first_cable.tray_width), format_number(first_cable.tray_height)
))
output.print_md(u"Кабелей запрошено: **{}**, уложено: **{}**".format(requested, len(placed)))
output.print_md(u"Реальное заполнение (по уложенным кабелям): **{}%**".format(round_half_up(fill_percent)))
if first_cable.fill_percent:
    output.print_md(u"Заполнение по данным Excel (справочно): {}%".format(format_number(first_cable.fill_percent)))

if unplaced:
    output.print_md(u"### Не уместилось в лоток: {} шт.".format(len(unplaced)))
    counts = Counter(c.mark for c in unplaced)
    for mark, n in sorted(counts.items()):
        output.print_md(u"- Марка {}: {} шт.".format(mark, n))

forms.alert(
    u"Готово.\n\n"
    u"Участок: {}\n"
    u"Размер лотка: {}×{} мм\n"
    u"Уложено кабелей: {} из {}\n"
    u"Заполнение: {}%\n\n"
    u"{}".format(
        section_name, format_number(first_cable.tray_width), format_number(first_cable.tray_height),
        len(placed), requested, round_half_up(fill_percent),
        (u"Не уместилось: {} шт. — см. окно вывода pyRevit.".format(len(unplaced))
         if unplaced else u"Подробности — в окне вывода pyRevit.")
    )
)
