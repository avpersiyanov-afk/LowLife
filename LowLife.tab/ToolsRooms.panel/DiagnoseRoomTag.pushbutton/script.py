# -*- coding: utf-8 -*-

__title__ = u"Диагностика\nмарки"
__doc__ = (
    u"Временная диагностика: выделите одну марку помещения (RoomTag) и "
    u"нажмите — покажет, что видит по ней логика кнопки «Марки "
    u"помещений» (TaggedRoomId, площадь/точку помещения, положение "
    u"головы относительно границ помещения и т.д.). Не меняет модель."
)
__author__ = "Pipers"

from pyrevit import revit, forms

from lowlife import room_tags

doc = revit.doc
uidoc = revit.uidoc

selection = list(uidoc.Selection.GetElementIds())
if not selection:
    forms.alert(u"Выделите одну марку помещения и повторите.", exitscript=True)

tag = doc.GetElement(selection[0])
if tag is None or tag.Category is None or tag.Category.Id.IntegerValue != room_tags._OST_ROOM_TAGS:
    forms.alert(u"Выделенный элемент — не марка помещения.", exitscript=True)

report = room_tags.diagnose_tag(doc, tag)
forms.alert(report, title=u"Диагностика марки {}".format(tag.Id.IntegerValue))
