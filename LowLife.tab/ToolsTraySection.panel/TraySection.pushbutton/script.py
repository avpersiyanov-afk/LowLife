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
    SECTION_GAP_MM, TITLE_BAND_MM, draw_section, draw_table, list_sections, mm_to_feet,
    paper_to_model, plan_section, read_cables, renumber_cables
)
from lowlife.xlsx_io import list_sheet_names

doc = revit.doc
uidoc = revit.uidoc

MODE_BOTH = u"Сечение и таблица"
MODE_SECTION = u"Только сечение"
MODE_TABLE = u"Только таблица"
_TABLE_GAP_MM = 16.0  # отступ таблицы от правой стенки лотка (режим «сечение и таблица»)


view = doc.ActiveView
if not isinstance(view, ViewDrafting):
    forms.alert(u"Откройте чертёжный вид (Drafting View) и запустите кнопку ещё раз.", exitscript=True)

# .xlsm — тот же формат (ZIP + тот же XML), что .xlsx, отличие только в
# макросах, парсеру не нужных: читается тем же xlsx_io. Дело за фильтром.
path = forms.pick_file(files_filter=u"Excel (*.xlsx;*.xlsm)|*.xlsx;*.xlsm|Все файлы (*.*)|*.*")
if not path:
    pyrevit_script.exit()

# Лист не угадываем по имени: один лист — берём его, несколько — спрашиваем.
sheet_names = list_sheet_names(path)
if not sheet_names:
    forms.alert(u"Не удалось прочитать книгу Excel (не видно ни одного листа).", exitscript=True)
elif len(sheet_names) == 1:
    sheet_name = sheet_names[0]
else:
    sheet_name = forms.SelectFromList.show(
        sheet_names, title=u"Лист со сводными данными для плагина",
        button_name=u"Выбрать", multiselect=False
    )
    if not sheet_name:
        pyrevit_script.exit()

cables, error = read_cables(path, sheet_name)
if error:
    forms.alert(error, exitscript=True)

all_sections = list_sections(cables)
if not all_sections:
    forms.alert(u"В файле не заполнен ни один участок (столбец «Участок»).", exitscript=True)

chosen = forms.SelectFromList.show(
    all_sections, title=u"Участки — отметьте, какие вывести (построятся стопкой сверху вниз)",
    button_name=u"Построить", multiselect=True
)
if not chosen:
    pyrevit_script.exit()

# порядок в стопке — как в файле (первое появление участка), а не как отмечали
chosen_set = set(chosen)
sections = [s for s in all_sections if s in chosen_set]

mode = forms.SelectFromList.show(
    [MODE_BOTH, MODE_SECTION, MODE_TABLE],
    title=u"Что построить на этом виде? "
          u"(сечение и таблицу на разных видах — запустите кнопку дважды)",
    button_name=u"Выбрать", multiselect=False
)
if not mode:
    pyrevit_script.exit()

want_section = mode in (MODE_BOTH, MODE_SECTION)
want_table = mode in (MODE_BOTH, MODE_TABLE)

show_marks = False
if want_section:
    show_marks = bool(forms.alert(u"Показывать марки кабелей на кружках?", yes=True, no=True))

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
    origin = uidoc.Selection.PickPoint(u"Укажите точку вставки первого блока; дальше участки уйдут вниз")
except OperationCanceledException:
    pyrevit_script.exit()

scale = float(view.Scale) if view.Scale else 1.0
gap_ft = paper_to_model(SECTION_GAP_MM, scale)
title_band_ft = paper_to_model(TITLE_BAND_MM, scale)
table_gap_ft = paper_to_model(_TABLE_GAP_MM, scale)
unplaced_by_section = []

with revit.Transaction(u"Сечения кабельных лотков"):
    prev_bottom_y = None  # самая нижняя нарисованная точка предыдущего блока
    for name, section_cables, first_cable in jobs:
        placed, unplaced, fill_percent = plan_section(
            section_cables, first_cable.tray_width, first_cable.tray_height
        )
        tray_w_ft = mm_to_feet(first_cable.tray_width)
        tray_h_ft = mm_to_feet(first_cable.tray_height)

        # над лотком есть ещё подпись участка, у одиночной таблицы — нет
        top_offset_ft = (title_band_ft + tray_h_ft) if want_section else 0.0
        if prev_bottom_y is None:
            tray_bottom_y = origin.Y  # первый блок — от указанной точки
        else:
            tray_bottom_y = (prev_bottom_y - gap_ft) - top_offset_ft
        lowest_y = tray_bottom_y

        if want_section:
            draw_section(
                doc, view, name, first_cable.tray_width, first_cable.tray_height,
                placed, XYZ(origin.X, tray_bottom_y, origin.Z), show_marks, scale
            )

        if want_table and placed:
            if want_section:
                table_tl = XYZ(origin.X + tray_w_ft + table_gap_ft, tray_bottom_y + tray_h_ft, origin.Z)
            else:
                table_tl = XYZ(origin.X, tray_bottom_y, origin.Z)
            table_low = draw_table(
                doc, view, name, first_cable.tray_width, first_cable.tray_height,
                placed, fill_percent, table_tl, scale
            )
            lowest_y = min(lowest_y, table_low)

        prev_bottom_y = lowest_y
        if unplaced:
            unplaced_by_section.append((name, Counter(c.mark for c in unplaced)))

# Отчёт не показываем. Предупреждаем только про кабели, которые физически
# не влезли в лоток по высоте (иначе бы молча пропали с чертежа).
if unplaced_by_section:
    lines = [u"Не поместились в лоток (не нарисованы):", u""]
    for name, counts in unplaced_by_section:
        parts = u", ".join(u"марка {} — {} шт.".format(m, n) for m, n in sorted(counts.items()))
        lines.append(u"{}: {}".format(name, parts))
    forms.alert(u"\n".join(lines))
