# -*- coding: utf-8 -*-
u"""
Дуга обхода на пересечении линий детализации — не привязано к дисциплине,
любой чертёжный/иной вид с линиями детализации.

Сценарий (см. lib/README.md): диаметр дуги и режим обхода запрашиваются
ОДИН раз в начале запуска. Дальше выбирается одна ИЛИ несколько «базовых»
линий (остаются целыми, без разрыва), затем — одна ИЛИ несколько «вторых»
линий за один PickObjects. Каждая вторая линия разрывается там, где она
пересекает базовые линии, и разрыв соединяется дугой; повторного запроса
диаметра/режима нет.

Режим обхода (ask_bypass_mode) — явный выбор пользователя, а не
автоматическое определение по числу пересечений:
  - «Одиночный» (bundle_mode=False) — если вторая линия пересекает
    несколько базовых, на КАЖДОМ пересечении отдельно строится своя
    маленькая дуга ровно введённого диаметра (несколько дуг подряд на
    одной линии, если пересечений несколько).
  - «Множественный» (bundle_mode=True) — все пересечения этой второй
    линии с базовыми объединяются в ОДНУ большую дугу, накрывающую сразу
    весь пучок: вырезаемый прямой участок растягивается от первого до
    последнего пересечения (по расстоянию вдоль второй линии) с запасом
    radius_ft по каждому краю — тем же diameter, что был бы диаметром
    дуги при одиночном пересечении.

Оба режима считаются ОДНОЙ и той же функцией (_plan_span): группировка
пересечений в один "пролёт" (множественный) или в отдельные "пролёты" по
одному на пересечение (одиночный) происходит только в group_crossing_positions,
дальше код общий. При ровно одном пересечении оба режима дают одинаковый
результат (единственная точка — сама себе и минимум, и максимум).

Диаметр — это диаметр дуги в буквальном смысле для одиночного пролёта
(одно пересечение): вырезается прямой участок длиной ровно diameter, а
дуга — ровно полуокружность этого диаметра (обе точки разрыва и выбранная
"верхняя" точка обхода равноудалены от центра пролёта на radius_ft — этот
центр оказывается центром окружности, а c1-c2 — её диаметром, поэтому
Arc.Create(c1, c2, bulge_point) даёт РОВНО полуокружность — открытую дугу,
никогда не замкнутую окружность, т.к. c1 и c2 — две РАЗНЫЕ точки на этой
окружности, а не одна и та же). При нескольких пересечениях (множественный
режим) центр — уже середина между c1 и c2, не сама точка пересечения (их
несколько) — принцип и гарантия "дуга, не окружность" те же, хорда просто
длиннее.

При «Одиночном» режиме с несколькими пересечениями на одной линии пролёты
(по одному на пересечение) не должны накладываться друг на друга — если
для заданного диаметра два соседних пересечения расположены слишком
близко, вся вторая линия пропускается с понятной ошибкой (предлагающей
уменьшить диаметр или переключиться на «Множественный»), а не тихо
сливается в одну дугу за спиной пользователя.

Сторона обхода (в какую сторону от второй линии выгибается дуга) не
выводится по какому-то жёсткому правилу — пользователь указывает её сам
кликом (PickPoint) для каждого пролёта отдельно, т.к. заранее
детерминированное правило может "наехать" на соседние элементы чертежа.
Перед каждым таким кликом соответствующая вторая линия подсвечивается
(выделяется) в модели — иначе при обходе нескольких линий/пролётов подряд
легко потерять, к какой из них относится текущий запрос стороны.

Оригинальная вторая линия не переиспользуется (не меняется её
GeometryCurve на месте) — вместо этого удаляется и на её месте создаются
новые DetailCurve (прямая-дуга-прямая-дуга-...-прямая, по числу пролётов),
как и в других местах проекта предпочитается delete+recreate вместо
рискованной правки существующего элемента "на месте" (см.
sot_schematic.sync_rooms_in_level в lib/README.md про марки узлов) — так
меньше риск наткнуться на неожиданное поведение GeometryCurve-сеттера,
которое здесь негде проверить вживую (нет Revit под рукой, см. CLAUDE.md).
"""

import math

from Autodesk.Revit.DB import Arc, DetailLine, ElementId, Line, XYZ
from Autodesk.Revit.UI.Selection import ObjectType, ISelectionFilter
from Autodesk.Revit.Exceptions import OperationCanceledException
from System.Collections.Generic import List

from pyrevit import revit, forms

MM_TO_FEET = 1.0 / 304.8

DEFAULT_DIAMETER_MM = 20.0

EPS_FT = 1e-6


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
    диаметр дуги целиком, а при «Множественном» обходе — запас по каждому
    краю общей дуги (см. docstring модуля). None, если отменено.
    """
    default_text = u"{:g}".format(DEFAULT_DIAMETER_MM)

    while True:
        raw = forms.ask_for_string(
            default=default_text,
            prompt=u"Диаметр дуги обхода, мм (при «Множественном» обходе — "
                   u"это запас по краям общей дуги):",
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


def ask_bypass_mode():
    u"""
    Спрашивает режим обхода (см. docstring модуля). Возвращает True —
    «Множественный» (одна большая дуга на весь пучок пересечений второй
    линии с базовыми), False — «Одиночный» (своя маленькая дуга ровно
    заданного диаметра на каждое пересечение отдельно, даже если их
    несколько на одной линии). При закрытии окна без ответа — False
    (безопаснее не сливать пересечения в одну дугу без явного согласия).
    """
    return bool(forms.alert(
        u"Как обходить пересечения второй линии с базовыми?\n\n"
        u"Да — «Множественный обход»: если вторая линия пересекает сразу "
        u"несколько базовых линий (пучок), строится ОДНА большая дуга через "
        u"весь пучок.\n\n"
        u"Нет — «Одиночный обход»: на каждом отдельном пересечении со своей "
        u"базовой линией строится своя маленькая дуга ровно введённого "
        u"диаметра — даже если пересечений на одной линии несколько.",
        title=u"Обход линий",
        yes=True, no=True
    ))


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


def collect_crossing_positions(a1, a2, dir_x, dir_y, base_lines):
    u"""Расстояния (от a1, вдоль (dir_x, dir_y)) всех точек пересечения (a1-a2) с любой из base_lines."""
    positions = []
    for base_p1, base_p2 in base_lines:
        ip = segment_intersection_xy(a1, a2, base_p1, base_p2)
        if ip is not None:
            positions.append((ip.X - a1.X) * dir_x + (ip.Y - a1.Y) * dir_y)
    return positions


def group_crossing_positions(positions, bundle_mode):
    u"""
    Группирует позиции пересечений в список "пролётов" под дуги, по
    возрастанию: bundle_mode=True — один пролёт на все позиции сразу
    («Множественный» — одна большая дуга); bundle_mode=False — свой
    пролёт на каждую позицию отдельно («Одиночный» — по маленькой дуге на
    каждое пересечение).
    """
    if not positions:
        return []
    if bundle_mode:
        return [sorted(positions)]
    return [[p] for p in sorted(positions)]


def plan_bypass_for_line(uidoc, base_lines, second_el, radius_ft, bundle_mode):
    u"""
    Считает геометрию обхода для одной "второй" линии против списка
    base_lines ([(p1, p2), ...] — концы каждой базовой линии), в
    указанном режиме (см. ask_bypass_mode), и спрашивает (PickPoint)
    сторону обхода отдельно для каждого пролёта. Возвращает (plan, error):
    plan — dict {"element": second_el, "curves": [Line/Arc, ...]}
    (готовая последовательность прямая-дуга-...-прямая) для
    apply_bypass_plan, либо None с текстом причины пропуска (нет
    пересечений, диаметр/запас не помещается на линии, пересечения
    слишком близки друг к другу в «Одиночном» режиме, отмена выбора
    стороны).
    """
    curve = second_el.GeometryCurve
    a1 = curve.GetEndPoint(0)
    a2 = curve.GetEndPoint(1)

    dx = a2.X - a1.X
    dy = a2.Y - a1.Y
    length = math.sqrt(dx * dx + dy * dy)
    if length < EPS_FT:
        return None, u"вторая линия вырождена (нулевой длины) — пропущено"
    dir_x = dx / length
    dir_y = dy / length

    positions = collect_crossing_positions(a1, a2, dir_x, dir_y, base_lines)
    if not positions:
        return None, u"нет пересечений с базовыми линиями — пропущено"

    groups = group_crossing_positions(positions, bundle_mode)

    spans = []
    prev_c2_pos = None
    for group in groups:
        c1_pos = min(group) - radius_ft
        c2_pos = max(group) + radius_ft

        if c1_pos <= EPS_FT or c2_pos >= length - EPS_FT:
            return None, u"диаметр/запас обхода больше доступной длины линии у пересечения — пропущено"

        if prev_c2_pos is not None and c1_pos <= prev_c2_pos + EPS_FT:
            return None, (
                u"два пересечения слишком близко друг к другу для отдельных "
                u"дуг такого диаметра — уменьшите диаметр или выберите "
                u"«Множественный обход»"
            )

        spans.append((c1_pos, c2_pos))
        prev_c2_pos = c2_pos

    def point_at(pos):
        if pos <= EPS_FT:
            return a1
        if pos >= length - EPS_FT:
            return a2
        return XYZ(a1.X + dir_x * pos, a1.Y + dir_y * pos, a1.Z)

    perp_x = -dir_y
    perp_y = dir_x

    curves = []
    prev_pos = 0.0

    for c1_pos, c2_pos in spans:
        if c1_pos > prev_pos + EPS_FT:
            curves.append(Line.CreateBound(point_at(prev_pos), point_at(c1_pos)))

        c1 = point_at(c1_pos)
        c2 = point_at(c2_pos)
        center_pos = (c1_pos + c2_pos) / 2.0
        span_radius = (c2_pos - c1_pos) / 2.0
        center_point = point_at(center_pos)

        highlight_element(uidoc, second_el)

        try:
            side_pt = uidoc.Selection.PickPoint(
                u"Укажите сторону обхода для линии ID {}".format(second_el.Id.IntegerValue)
            )
        except OperationCanceledException:
            return None, u"выбор стороны обхода отменён — пропущено"

        dot = (side_pt.X - center_point.X) * perp_x + (side_pt.Y - center_point.Y) * perp_y
        side = 1.0 if dot >= 0 else -1.0
        bulge_point = XYZ(
            center_point.X + perp_x * side * span_radius,
            center_point.Y + perp_y * side * span_radius,
            center_point.Z
        )

        # Arc.Create(p1, p2, p3) с тремя РАЗНЫМИ точками всегда даёт открытую
        # дугу между p1 и p2 через p3, никогда замкнутую окружность.
        curves.append(Arc.Create(c1, c2, bulge_point))
        prev_pos = c2_pos

    if prev_pos < length - EPS_FT:
        curves.append(Line.CreateBound(point_at(prev_pos), a2))

    return {"element": second_el, "curves": curves}, None


def apply_bypass_plan(doc, view, plan):
    u"""
    Строит обход по уже посчитанному plan (см. plan_bypass_for_line):
    удаляет исходную вторую линию, создаёт на её месте новые DetailCurve
    (по plan["curves"]) со стилем линии оригинала.
    """
    el = plan["element"]

    line_style = None
    try:
        line_style = el.LineStyle
    except:
        pass

    doc.Delete(el.Id)

    created = []
    for new_curve in plan["curves"]:
        detail_curve = doc.Create.NewDetailCurve(view, new_curve)
        if line_style is not None:
            try:
                detail_curve.LineStyle = line_style
            except:
                pass
        created.append(detail_curve)

    return created


def run_line_bypass_tool(doc, uidoc, view):
    u"""Полный сценарий кнопки: диаметр -> режим -> базовая(-ые) линия(-и) -> вторая(-ые) линия(-и) -> обходы."""
    diameter_mm = ask_diameter_mm()
    if diameter_mm is None:
        return

    bundle_mode = ask_bypass_mode()

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
        plan, error = plan_bypass_for_line(uidoc, base_lines, second_el, radius_ft, bundle_mode)
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
