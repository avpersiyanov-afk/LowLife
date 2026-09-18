# -*- coding: utf-8 -*-
u"""
Дуга обхода на пересечении линий детализации — не привязано к дисциплине,
любой чертёжный/иной вид с линиями детализации.

Сценарий (см. lib/README.md): диаметр дуги запрашивается ОДИН раз в начале
запуска. Дальше выбирается «базовая» линия (остаётся целой, без разрыва),
затем — одна ИЛИ несколько «вторых» линий за один PickObjects; каждая из
них в точке пересечения с базовой разрывается, и разрыв соединяется дугой
уже известного диаметра — повторного запроса диаметра нет. Сторона обхода
(в какую сторону от второй линии выгибается дуга) не выводится по какому-то
жёсткому правилу — пользователь указывает её сам кликом (PickPoint) для
каждой второй линии отдельно, т.к. заранее детерминированное правило может
"наехать" на соседние элементы чертежа.

Диаметр — это диаметр дуги в буквальном смысле: на второй линии вырезается
прямой участок длиной ровно diameter (по radius_ft в обе стороны от точки
пересечения), а дуга — ровно полуокружность этого диаметра. Достигается
тем, что обе точки разрыва (c1, c2) и выбранная "верхняя" точка обхода
равноудалены от точки пересечения на radius_ft — точка пересечения
оказывается центром окружности, а c1-c2 — её диаметром, поэтому
Arc.Create(c1, c2, bulge_point) всегда даёт ровно полуокружность.

Оригинальная вторая линия не переиспользуется (не меняется её
GeometryCurve на месте) — вместо этого удаляется и на её месте создаются
три новых DetailCurve (прямой-дуга-прямой), как и в других местах проекта
предпочитается delete+recreate вместо рискованной правки существующего
элемента "на месте" (см. sot_schematic.sync_rooms_in_level в lib/README.md
про марки узлов) — так меньше риск наткнуться на неожиданное поведение
GeometryCurve-сеттера, которое здесь негде проверить вживую (нет Revit
под рукой, см. CLAUDE.md).
"""

import math

from Autodesk.Revit.DB import Arc, DetailLine, Line, XYZ
from Autodesk.Revit.UI.Selection import ObjectType, ISelectionFilter
from Autodesk.Revit.Exceptions import OperationCanceledException

from pyrevit import revit, forms

MM_TO_FEET = 1.0 / 304.8

DEFAULT_DIAMETER_MM = 20.0


class _DetailLineSelectionFilter(ISelectionFilter):
    u"""Разрешает выбирать только прямые линии детализации текущего (не связанного) документа."""

    def AllowElement(self, elem):
        try:
            if elem.Document.IsLinked:
                return False
        except:
            pass

        try:
            if not isinstance(elem, DetailLine):
                return False
            return isinstance(elem.GeometryCurve, Line)
        except:
            return False

    def AllowReference(self, reference, position):
        return True


def ask_diameter_mm():
    u"""Запрашивает диаметр дуги обхода, мм. None, если отменено."""
    default_text = u"{:g}".format(DEFAULT_DIAMETER_MM)

    while True:
        raw = forms.ask_for_string(
            default=default_text,
            prompt=u"Диаметр дуги обхода, мм:",
            title=u"Обход линий"
        )
        if raw is None:
            return None

        raw = raw.strip().replace(u",", u".")
        if not raw:
            forms.alert(u"Введите значение диаметра.")
            continue

        try:
            value = float(raw)
        except ValueError:
            forms.alert(u"«{}» — не число. Введите положительное число.".format(raw))
            continue

        if value <= 0:
            forms.alert(u"Диаметр должен быть больше нуля.")
            continue

        return value


def segment_intersection_xy(p1, p2, p3, p4, tol=1e-9):
    u"""
    Точка пересечения отрезков (p1-p2) и (p3-p4) в плоскости XY (Z — от p1).
    None, если отрезки параллельны/коллинеарны или пересекаются только на
    продолжении (не в пределах собственной длины каждого отрезка).
    """
    denom = (p4.Y - p3.Y) * (p2.X - p1.X) - (p4.X - p3.X) * (p2.Y - p1.Y)
    if abs(denom) < tol:
        return None

    ua = ((p4.X - p3.X) * (p1.Y - p3.Y) - (p4.Y - p3.Y) * (p1.X - p3.X)) / denom
    ub = ((p2.X - p1.X) * (p1.Y - p3.Y) - (p2.Y - p1.Y) * (p1.X - p3.X)) / denom

    eps = 1e-6
    if ua < -eps or ua > 1 + eps or ub < -eps or ub > 1 + eps:
        return None

    x = p1.X + ua * (p2.X - p1.X)
    y = p1.Y + ua * (p2.Y - p1.Y)
    return XYZ(x, y, p1.Z)


def plan_bypass(uidoc, base_p1, base_p2, second_el, radius_ft):
    u"""
    Считает геометрию обхода для одной "второй" линии и спрашивает
    (PickPoint) сторону обхода. Возвращает (plan, error) — plan это dict
    для apply_bypass_plan, либо None с текстом причины пропуска (нет
    пересечения, диаметр не помещается на линии, отмена выбора стороны).
    """
    curve = second_el.GeometryCurve
    a1 = curve.GetEndPoint(0)
    a2 = curve.GetEndPoint(1)

    ip = segment_intersection_xy(a1, a2, base_p1, base_p2)
    if ip is None:
        return None, u"нет пересечения с базовой линией — пропущено"

    dx = a2.X - a1.X
    dy = a2.Y - a1.Y
    length = math.sqrt(dx * dx + dy * dy)
    if length < 1e-9:
        return None, u"вторая линия вырождена (нулевой длины) — пропущено"
    dir_x = dx / length
    dir_y = dy / length

    dist_to_a1 = ip.DistanceTo(a1)
    dist_to_a2 = ip.DistanceTo(a2)

    if radius_ft >= dist_to_a1 or radius_ft >= dist_to_a2:
        return None, u"диаметр обхода больше доступной длины линии у пересечения — пропущено"

    c1 = XYZ(ip.X - dir_x * radius_ft, ip.Y - dir_y * radius_ft, ip.Z)
    c2 = XYZ(ip.X + dir_x * radius_ft, ip.Y + dir_y * radius_ft, ip.Z)

    try:
        side_pt = uidoc.Selection.PickPoint(
            u"Укажите сторону обхода для линии ID {}".format(second_el.Id.IntegerValue)
        )
    except OperationCanceledException:
        return None, u"выбор стороны обхода отменён — пропущено"

    perp_x = -dir_y
    perp_y = dir_x
    dot = (side_pt.X - ip.X) * perp_x + (side_pt.Y - ip.Y) * perp_y
    side = 1.0 if dot >= 0 else -1.0
    bulge_point = XYZ(
        ip.X + perp_x * side * radius_ft,
        ip.Y + perp_y * side * radius_ft,
        ip.Z
    )

    return {
        "element": second_el,
        "a1": a1,
        "a2": a2,
        "c1": c1,
        "c2": c2,
        "bulge_point": bulge_point,
    }, None


def apply_bypass_plan(doc, view, plan):
    u"""
    Строит обход по уже посчитанному plan (см. plan_bypass): удаляет
    исходную вторую линию, создаёт на её месте три новых DetailCurve
    (прямая-дуга-прямая) со стилем линии оригинала.
    """
    el = plan["element"]

    line_style = None
    try:
        line_style = el.LineStyle
    except:
        pass

    head_line = Line.CreateBound(plan["a1"], plan["c1"])
    tail_line = Line.CreateBound(plan["c2"], plan["a2"])
    arc = Arc.Create(plan["c1"], plan["c2"], plan["bulge_point"])

    doc.Delete(el.Id)

    created = []
    for new_curve in (head_line, arc, tail_line):
        detail_curve = doc.Create.NewDetailCurve(view, new_curve)
        if line_style is not None:
            try:
                detail_curve.LineStyle = line_style
            except:
                pass
        created.append(detail_curve)

    return created


def run_line_bypass_tool(doc, uidoc, view):
    u"""Полный сценарий кнопки: диаметр -> базовая линия -> вторая(-ые) линия(-и) -> обходы."""
    diameter_mm = ask_diameter_mm()
    if diameter_mm is None:
        return

    radius_ft = (diameter_mm * MM_TO_FEET) / 2.0

    selection_filter = _DetailLineSelectionFilter()

    try:
        base_ref = uidoc.Selection.PickObject(
            ObjectType.Element, selection_filter,
            u"Выберите базовую линию (останется целой)"
        )
    except OperationCanceledException:
        return

    base_el = doc.GetElement(base_ref)
    base_curve = base_el.GeometryCurve
    base_p1 = base_curve.GetEndPoint(0)
    base_p2 = base_curve.GetEndPoint(1)

    try:
        second_refs = uidoc.Selection.PickObjects(
            ObjectType.Element, selection_filter,
            u"Выберите одну или несколько линий, которые обойдут базовую "
            u"(Enter/«Готово» — подтвердить)"
        )
    except OperationCanceledException:
        return

    second_els = [
        doc.GetElement(r) for r in second_refs
        if r.ElementId != base_el.Id
    ]

    if not second_els:
        forms.alert(u"Не выбрано ни одной второй линии.", exitscript=True)
        return

    plans = []
    skipped = []

    for second_el in second_els:
        plan, error = plan_bypass(uidoc, base_p1, base_p2, second_el, radius_ft)
        if plan is None:
            skipped.append(u"ID {}: {}".format(second_el.Id.IntegerValue, error))
        else:
            plans.append(plan)

    if not plans:
        forms.alert(
            u"Не удалось построить ни одного обхода.\n\n" + u"\n".join(skipped),
            exitscript=True
        )
        return

    with revit.Transaction(u"Обход линий"):
        for plan in plans:
            apply_bypass_plan(doc, view, plan)

    message = u"Готово. Построено обходов: {}".format(len(plans))
    if skipped:
        message += u"\n\nПропущено:\n" + u"\n".join(skipped)
    forms.alert(message)
