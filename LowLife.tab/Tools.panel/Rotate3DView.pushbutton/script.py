# -*- coding: utf-8 -*-

__title__ = u"Повернуть\n3D вид"
__doc__ = (
    u"Поворачивает открытый 3D вид под ось: кликните на виде ось сетки (или "
    u"прямую линию, стену, лоток — в модели или в связанном файле), и вид "
    u"развернётся вокруг вертикали вдоль или поперёк этой оси. Включённая "
    u"рамка 3D вида поворачивается так же — её стороны встают параллельно "
    u"оси. Можно кликать следующие оси подряд; Esc — выход."
)
__author__ = "Pipers"

import traceback

from Autodesk.Revit.DB import Transaction
from Autodesk.Revit.Exceptions import OperationCanceledException
from Autodesk.Revit.UI.Selection import ObjectType
from pyrevit import revit, forms, script

from lowlife import view_rotate

doc = revit.doc
uidoc = revit.uidoc
view = doc.ActiveView

TITLE = u"Повернуть 3D вид"

reason = view_rotate.unsupported_reason(view)
if reason:
    forms.alert(reason, title=TITLE, exitscript=True)

pick_filter = view_rotate.make_pick_filter(doc)

while True:
    try:
        ref = uidoc.Selection.PickObject(
            ObjectType.LinkedElement, pick_filter,
            u"Повернуть 3D вид: выберите ось (Esc — выход)")
    except OperationCanceledException:
        script.exit()

    try:
        direction, _name = view_rotate.picked_direction(doc, ref)
    except ValueError as err:
        forms.alert(unicode(err), title=TITLE)
        continue

    t = Transaction(doc, TITLE)
    t.Start()
    try:
        view_rotate.align_view(view, direction)
        t.Commit()
    except Exception:
        t.RollBack()
        forms.alert(u"Не удалось повернуть вид.\n\n" + traceback.format_exc(),
                    title=TITLE, exitscript=True)
    uidoc.RefreshActiveView()
