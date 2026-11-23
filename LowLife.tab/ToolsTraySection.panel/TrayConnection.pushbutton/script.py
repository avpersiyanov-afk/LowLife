# -*- coding: utf-8 -*-

__title__ = u"Соединить лотки\nпод углом"
__doc__ = (
    u"Выберите два кабельных лотка с концами на разных уровнях. Введите угол "
    u"наклонного участка к горизонту (от 2 до 88 градусов). Кнопка создаст "
    u"новый участок лотка и штатные соединительные детали, сохраняя выбранные "
    u"лотки на месте."
)

import traceback

from Autodesk.Revit.Exceptions import OperationCanceledException
from Autodesk.Revit.UI.Selection import ObjectType
from pyrevit import forms, revit, script

from lowlife import tray_connection, tray_connection_core, tray_tags
from lowlife.i18n import tr


TITLE = tr(u"Соединить лотки под углом", u"Connect trays at an angle")
doc = revit.doc
uidoc = revit.uidoc


def _selected_trays():
    selected = [doc.GetElement(item) for item in uidoc.Selection.GetElementIds()]
    trays = tray_tags.resolve_trays(doc, selected)
    if len(trays) == 2:
        return trays
    try:
        refs = uidoc.Selection.PickObjects(
            ObjectType.Element,
            tray_tags.TrayFilter(),
            tr(u"Выберите ровно два кабельных лотка и завершите выбор.",
               u"Select exactly two cable trays, then Finish.")
        )
    except OperationCanceledException:
        forms.alert(tr(u"Выбор отменён.", u"Selection cancelled."), title=TITLE,
                    exitscript=True)
    trays = tray_tags.resolve_trays(doc, [doc.GetElement(ref) for ref in refs])
    if len(trays) != 2:
        forms.alert(tr(u"Нужно выбрать ровно два разных кабельных лотка.",
                       u"Select exactly two different cable trays."),
                    title=TITLE, exitscript=True)
    return trays


def _angle():
    raw = forms.ask_for_string(
        default="45",
        prompt=tr(
            u"Угол наклонного участка к горизонту, градусы (2–88):",
            u"Angle of the sloped segment to horizontal, degrees (2–88):"
        ),
        title=TITLE,
    )
    try:
        return tray_connection_core.parse_angle(raw)
    except ValueError as exc:
        forms.alert(tr(u"Некорректный угол: {}", u"Invalid angle: {}").format(exc),
                    title=TITLE, exitscript=True)


try:
    first, second = _selected_trays()
    angle = _angle()
    with revit.Transaction(TITLE):
        segments = tray_connection.create_connection(doc, first, second, angle)
except Exception as exc:
    script.get_logger().exception("Fixed-angle tray connection failed")
    forms.alert(
        tr(u"Не удалось создать соединение:\n\n{}",
           u"Could not create the tray connection:\n\n{}").format(exc),
        title=TITLE,
        exitscript=True,
    )

forms.alert(
    tr(u"Соединение создано. Новых участков лотка: {}.",
       u"Connection created. New tray segments: {}.").format(len(segments)),
    title=TITLE,
)
