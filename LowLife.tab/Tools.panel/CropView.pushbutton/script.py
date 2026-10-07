# -*- coding: utf-8 -*-

__title__ = u"Обрезать\nвид"
__doc__ = (
    u"Обрезает вид и аннотации по прямоугольнику: укажите мышью два "
    u"противоположных угла, затем выберите, что обрезать — этот вид или его "
    u"копию (простую, с детализацией или зависимую; к имени копии "
    u"добавляется префикс). Включаются подрезка вида и подрезка аннотаций "
    u"(с минимальным отступом от рамки), копия открывается. Работает на "
    u"планах, разрезах, фасадах и узлах. Esc — отмена."
)
__author__ = "Pipers"

import traceback

from Autodesk.Revit.DB import Element, Transaction, TransactionGroup
from Autodesk.Revit.Exceptions import OperationCanceledException
from pyrevit import revit, forms, script

from lowlife import view_crop, view_crop_dialog

doc = revit.doc
uidoc = revit.uidoc
view = doc.ActiveView

TITLE = u"Обрезать вид"


class _Cancelled(Exception):
    """Окно выбора закрыто — откатить всё, как по Esc."""


def _abort(group, t):
    if t is not None and t.HasStarted() and not t.HasEnded():
        t.RollBack()
    group.RollBack()


reason = view_crop.unsupported_reason(view)
if reason:
    forms.alert(reason, title=TITLE, exitscript=True)

result = None
t = None
group = TransactionGroup(doc, TITLE)
group.Start()
try:
    # PickPoint требует рабочую плоскость; на разрезах/фасадах её часто нет.
    t = Transaction(doc, u"Рабочая плоскость вида")
    t.Start()
    temp_plane = view_crop.ensure_work_plane(doc, view)
    t.Commit()

    pt1 = uidoc.Selection.PickPoint(u"Обрезать вид: первый угол рамки")
    pt2 = uidoc.Selection.PickPoint(u"Обрезать вид: противоположный угол рамки")
    view_crop.check_points(view, pt1, pt2)

    choice = view_crop_dialog.ask(view_crop.available_modes(view),
                                  Element.Name.GetValue(view))
    if choice is None:
        raise _Cancelled()
    mode, prefix = choice

    t = Transaction(doc, TITLE)
    t.Start()
    view_crop.remove_work_plane(doc, temp_plane)
    target = view_crop.duplicate_view(doc, view, mode, prefix)
    warnings = view_crop.apply_crop(target, pt1, pt2)
    t.Commit()
    group.Assimilate()
    result = (target, warnings)
except (OperationCanceledException, _Cancelled):
    _abort(group, t)
except ValueError as err:
    _abort(group, t)
    forms.alert(unicode(err), title=TITLE)
except Exception:
    _abort(group, t)
    forms.alert(u"Не удалось обрезать вид (возможно, подрезка задана "
                u"шаблоном вида).\n\n" + traceback.format_exc(), title=TITLE)

if result is None:
    script.exit()

target, warnings = result
if target.Id != view.Id:
    uidoc.ActiveView = target
if warnings:
    forms.alert(u"\n".join(warnings), title=TITLE)
