# -*- coding: utf-8 -*-

__title__ = u"Рыба\nструктурной схемы"
__author__ = "Pipers"

from pyrevit import revit, forms

from lowlife import room_finder, room_schematic_picker, room_schematic

doc = revit.doc

records = room_finder.get_records(doc)
if not records:
    forms.alert(
        u"В модели (и подключённых связях) не найдено ни одного "
        u"размещённого помещения.",
        title=u"Рыба структурной схемы",
        exitscript=True,
    )

sections = room_schematic_picker.show(doc, records)
if not sections:
    import sys
    sys.exit()

# Проверка/подбор вида на КАЖДУЮ секцию — до открытия транзакции (только
# чтение модели), чтобы ошибка конфликта имени вида остановила скрипт
# раньше, чем что-либо начнёт строиться (см. room_schematic.check_view).
view_plans = []
for section_label, boxes in sections.items():
    view_name = room_schematic.schematic_view_name(section_label)
    existing_view, drafting_type_id, error = room_schematic.check_view(doc, view_name)
    if error:
        forms.alert(error, title=u"Рыба структурной схемы", exitscript=True)
    view_plans.append((view_name, existing_view, drafting_type_id, boxes))

summary_lines = []
last_view = None

with revit.Transaction(u"Build Room Schematic"):
    for view_name, existing_view, drafting_type_id, boxes in view_plans:
        view = existing_view if existing_view is not None else room_schematic.create_view(
            doc, drafting_type_id, view_name
        )
        num_levels, num_boxes = room_schematic.rebuild(doc, view, boxes)
        summary_lines.append(u"«{}»: уровней — {}, боксов — {}".format(view_name, num_levels, num_boxes))
        last_view = view

revit.uidoc.ActiveView = last_view

forms.alert(u"Готово.\n\n" + u"\n".join(summary_lines), title=u"Рыба структурной схемы")
