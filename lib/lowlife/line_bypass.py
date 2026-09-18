# -*- coding: utf-8 -*-
u"""
Дуга обхода на пересечении линий детализации — не привязано к дисциплине,
любой чертёжный/иной вид с линиями детализации.

Сценарий (см. lib/README.md): диаметр дуги запрашивается ОДИН раз в начале
запуска. Дальше выбирается одна ИЛИ несколько «базовых» линий (остаются
целыми, без разрыва), затем — одна ИЛИ несколько «вторых» линий за один
PickObjects. Каждая вторая линия разрывается ОДИН раз — в месте, где она
пересекает базовые линии, — и разрыв соединяется дугой; повторного запроса
диаметра нет.

Если вторая линия пересекает несколько базовых линий сразу (типовой случай
— одна линия обходит целый пучок соседних линий), вместо N мелких дуг по
одной на каждое пересечение строится ОДНА большая дуга, накрывающая сразу
все пересечения этой второй линии: вырезаемый прямой участок растягивается
от первого до последнего пересечения (по расстоянию вдоль второй линии) с
запасом radius_ft по каждому краю — тем же diameter, что был бы диаметром
дуги при одиночном пересечении. При ровно одном пересечении формула
вырождается в старый случай (единственная точка — сама себе и минимум, и
максимум), поэтому это одна и та же функция без раздельных веток "малая
дуга" / "большая дуга".

Диаметр — это диаметр дуги в буквальном смысле для случая одного
пересечения: вырезается прямой участок длиной ровно diameter, а дуга —
ровно полуокружность этого диаметра (обе точки разрыва и выбранная
"верхняя" точка обхода равноудалены от точки пересечения на radius_ft —
точка пересечения оказывается центром окружности, а c1-c2 — её диаметром,
поэтому Arc.Create(c1, c2, bulge_point) всегда даёт полуокружность). При
нескольких пересечениях центр окружности — уже не сама точка пересечения
(пересечений несколько), а середина между c1 и c2 — принцип тот же, просто
хорда длиннее.

Сторона обхода (в какую сторону от второй линии выгибается дуга) не
выводится по какому-то жёсткому правилу — пользователь указывает её сам
кликом (PickPoint) для каждой второй линии отдельно, т.к. заранее
детерминированное правило может "наехать" на соседние элементы чертежа.
Перед каждым таким кликом соответствующая вторая линия подсвечивается
(выделяется) в модели — иначе при обходе нескольких линий подряд легко
потерять, к какой из них относится текущий запрос стороны.

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

from Autodesk.Revit.DB import Arc, DetailLine, ElementId, Line, XYZ
from Autodesk.Revit.UI.Selection import ObjectType, ISelectionFilter
from Autodesk.Revit.Exceptions import OperationCanceledException
from System.Collections.Generic import List

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
    u"""
    Запрашивает диаметр дуги обхода, мм — для одиночного пересечения это
    диаметр дуги целиком, а при обходе нескольких линий сразу — запас по
    каждому краю групповой дуги (см. docstring модуля). None, если
    отменено.
    """
    default_text = u"{:g}".format(DEFAULT_DIAMETER_MM)

    while True:
        raw = forms.ask_for_string(
            default=default_text,
            prompt=u"Диаметр дуги обхода, мм (при обходе сразу нескольких "
                   u"линий — это запас по краям общей дуги):",
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


def highlight_element(uidoc, el):
    u"""Выделяет (подсвечивает) один элемент в модели — чтобы перед PickPoint было видно, о какой линии идёт речь."""
    try:
        ids = List[ElementId]()
        ids.Add(el.Id)
        uidoc.Selection.SetElementIds(ids)
    except:
        pass


def plan_bypass(uidoc, base_lines, second_el, radius_ft):
    u"""
    Считает геометрию обхода для одной "второй" линии против списка
    base_lines ([(p1, p2), ...] — концы каждой базовой линии) и спрашивает
    (PickPoint) сторону обхода. Возвращает (plan, error) — plan это dict
    для apply_bypass_plan, либо None с текстом причины пропуска (нет
    пересечений, диаметр/запас не помещается на линии, отмена выбора
    стороны).

    Если second_el пересекает несколько base_lines, вырезаемый участок
    растягивается от первого до последнего пересечения (плюс radius_ft
    запаса с каждого края) — одна общая дуга на все эти пересечения, а не
    по дуге на каждое.
    """
    curve = second_el.GeometryCurve
    a1 = curve.GetEndPoint(0)
    a2 = curve.GetEndPoint(1)

    dx = a2.X - a1.X
    dy = a2.Y - a1.Y
    length = math.sqrt(dx * dx + dy * dy)
    if length < 1e-9:
        return None, u"вторая линия вырождена (нулевой длины) — пропущено"
    dir_x = dx / length
    dir_y = dy / length

    positions = []
    for base_p1, base_p2 in base_lines:
        ip = segment_intersection_xy(a1, a2, base_p1, base_p2)
        if ip is not None:
            pos = (ip.X - a1.X) * dir_x + (ip.Y - a1.Y) * dir_y
            positions.append(pos)

    if not positions:
        return None, u"нет пересечений с базовыми линиями — пропущено"

    min_pos = min(positions)
    max_pos = max(positions)

    c1_pos = min_pos - radius_ft
    c2_pos = max_pos + radius_ft

    eps = 1e-6
    if c1_pos <= eps or c2_pos >= length - eps:
        return None, u"диаметр/запас обхода больше доступной длины линии у пересечения — пропущено"

    c1 = XYZ(a1.X + dir_x * c1_pos, a1.Y + dir_y * c1_pos, a1.Z)
    c2 = XYZ(a1.X + dir_x * c2_pos, a1.Y + dir_y * c2_pos, a1.Z)

    center_pos = (c1_pos + c2_pos) / 2.0
    big_radius = (c2_pos - c1_pos) / 2.0
    center_point = XYZ(a1.X + dir_x * center_pos, a1.Y + dir_y * center_pos, a1.Z)

    highlight_element(uidoc, second_el)

    try:
        side_pt = uidoc.Selection.PickPoint(
            u"Укажите сторону обхода для линии ID {}".format(second_el.Id.IntegerValue)
        )
    except OperationCanceledException:
        return None, u"выбор стороны обхода отменён — пропущено"

    perp_x = -dir_y
    perp_y = dir_x
    dot = (side_pt.X - center_point.X) * perp_x + (side_pt.Y - center_point.Y) * perp_y
    side = 1.0 if dot >= 0 else -1.0
    bulge_point = XYZ(
        center_point.X + perp_x * side * big_radius,
        center_point.Y + perp_y * side * big_radius,
        center_point.Z
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
    u"""Полный сценарий кнопки: диаметр -> базовая(-ые) линия(-и) -> вторая(-ые) линия(-и) -> обходы."""
    diameter_mm = ask_diameter_mm()
    if diameter_mm is None:
        return

    radius_ft = (diameter_mm * MM_TO_FEET) / 2.0

    selection_filter = _DetailLineSelectionFilter()

    try:
        base_refs = uidoc.Selection.PickObjects(
            ObjectType.Element, selection_filter,
            u"Выберите одну или несколько базовых линий — останутся целыми "
            u"(Enter/«Готово» — подтвердить)"
        )
    except OperationCanceledException:
        return

    base_els = [doc.GetElement(r) for r in base_refs]
    if not base_els:
        forms.alert(u"Не выбрано ни одной базовой линии.", exitscript=True)
        return

    base_ids = set(el.Id for el in base_els)
    base_lines = []
    for base_el in base_els:
        base_curve = base_el.GeometryCurve
        base_lines.append((base_curve.GetEndPoint(0), base_curve.GetEndPoint(1)))

    try:
        second_refs = uidoc.Selection.PickObjects(
            ObjectType.Element, selection_filter,
            u"Выберите одну или несколько линий, которые обойдут базовые "
            u"(Enter/«Готово» — подтвердить)"
        )
    except OperationCanceledException:
        return

    second_els = [
        doc.GetElement(r) for r in second_refs
        if r.ElementId not in base_ids
    ]

    if not second_els:
        forms.alert(u"Не выбрано ни одной второй линии.", exitscript=True)
        return

    plans = []
    skipped = []

    for second_el in second_els:
        plan, error = plan_bypass(uidoc, base_lines, second_el, radius_ft)
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
