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

boxes = room_schematic_picker.show(doc, records)
if not boxes:
    import sys
    sys.exit()

existing_view, drafting_type_id, error = room_schematic.check_view(doc)
if error:
    forms.alert(error, title=u"Рыба структурной схемы", exitscript=True)

with revit.Transaction(u"Build Room Schematic"):
    view = existing_view if existing_view is not None else room_schematic.create_view(doc, drafting_type_id)
    num_levels, num_boxes = room_schematic.rebuild(doc, view, boxes)

revit.uidoc.ActiveView = view

forms.alert(
    u"Готово: вид «{}», уровней — {}, боксов — {}.".format(
        room_schematic.SCHEMATIC_VIEW_NAME, num_levels, num_boxes
    ),
    title=u"Рыба структурной схемы",
)
