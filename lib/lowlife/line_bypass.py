# -*- coding: utf-8 -*-
u"""
Дуга обхода на пересечении линий детализации — не привязано к дисциплине,
любой чертёжный/иной вид с линиями детализации.

Сценарий (см. lib/README.md): диаметр дуги и режим обхода запрашиваются
ОДИН раз в начале запуска (см. ask_diameter_mm/ask_bypass_mode). Базовые
линии выбираются ОДНИМ PickObjects — многократный выбор (рамкой и/или
кликами) сохранён именно здесь, подтверждается Enter/«Готово» один раз.

Дальше начинается цикл (см. run_line_bypass_tool): PickObject на ОДНУ
вторую линию -> сразу PickPoint на сторону обхода для именно этой линии
-> клик сразу строит и КОММИТИТ обход этой линии (без промежуточного
превью/подтверждения — щёлкнули сторону, обход готов) -> цикл
возвращается к выбору следующей второй линии. Esc на шаге выбора второй
линии заканчивает весь цикл (это единственная явная точка выхода); Esc на
шаге выбора стороны пропускает только текущую линию и возвращается к
выбору следующей, не завершая всю кнопку.

ВАЖНО про "превью, которое меняется по положению мыши": обычный
`uidoc.Selection.PickPoint` в Revit API — блокирующий вызов без обратных
вызовов на движение мыши, он не даёт скрипту возможности перерисовывать
собственную графику (дугу) вслед за курсором ДО клика — это ограничение
платформы для обычных внешних команд (`IExternalCommand`), а не
недоделанная часть этого файла. По-настоящему "живой" предпросмотр,
следующий за курсором, потребовал бы совсем другого класса решения
(например, свой `IDirectContext3DServer`/ловля позиции курсора через
`Idling` и ручной пересчёт экран->модель) — то есть модальный
модлесс-инструмент с непроверенной здесь механикой, а не скрипт-кнопка;
не делаем этого без живого Revit под рукой (см. CLAUDE.md). Вместо этого
клик по стороне СРАЗУ строит и коммитит итоговую дугу — без предпросмотра
и без отдельного подтверждения.

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

Оба режима считаются ОДНОЙ и той же геометрией (compute_line_plan +
build_curves_for_side): группировка пересечений в один "пролёт"
(множественный) или в отдельные "пролёты" по одному на пересечение
(одиночный) происходит только в group_crossing_positions, дальше код
общий. При ровно одном пересечении оба режима дают одинаковый результат.

Диаметр — это диаметр дуги в буквальном смысле для одиночного пролёта
(одно пересечение): вырезается прямой участок длиной ровно diameter, а
дуга — ровно полуокружность этого диаметра (обе точки разрыва и выбранная
"верхняя" точка обхода равноудалены от центра пролёта на radius_ft — этот
центр оказывается центром окружности, а c1-c2 — её диаметром, поэтому
Arc.Create(c1, c2, bulge_point) даёт РОВНО полуокружность — открытую дугу,
никогда не замкнутую окружность, т.к. c1 и c2 — две РАЗНЫЕ точки на этой
окружности). При нескольких пересечениях (множественный режим) центр —
уже середина между c1 и c2, не сама точка пересечения (их несколько) —
принцип и гарантия "дуга, не окружность" те же, хорда просто длиннее.

При «Одиночном» режиме с несколькими пересечениями на одной линии пролёты
(по одному на пересечение) не должны накладываться друг на друга — если
для заданного диаметра два соседних пересечения расположены слишком
близко, вся вторая линия пропускается с понятной ошибкой (предлагающей
уменьшить диаметр или переключиться на «Множественный»), а не тихо
сливается в одну дугу за спиной пользователя.

Оригинальная вторая линия не переиспользуется (не меняется её
GeometryCurve на месте) — вместо этого удаляется и на её месте создаются
новые DetailCurve (прямая-дуга-прямая-дуга-...-прямая, по числу пролётов),
как и в других местах проекта предпочитается delete+recreate вместо
рискованной правки существующего элемента "на месте" (см.
sot_schematic.sync_rooms_in_level в lib/README.md про марки узлов) — так
меньше риск наткнуться на неожиданное поведение GeometryCurve-сеттера,
которое здесь негде проверить вживую.
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


def highlight_elements(uidoc, elements):
    u"""Выделяет (подсвечивает) элементы в модели — чтобы было видно, о каких линиях идёт речь перед запросом стороны."""
    try:
        ids = List[ElementId]()
        for el in elements:
            ids.Add(el.Id)
        uidoc.Selection.SetElementIds(ids)
    except:
        pass


def ask_side_reference(uidoc, prompt):
    u"""Просит указать точку кликом — определяет сторону обхода (см. docstring модуля). None, если отменено (Esc)."""
    try:
        return uidoc.Selection.PickPoint(prompt)
    except OperationCanceledException:
        return None


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


def compute_line_plan(base_lines, second_el, radius_ft, bundle_mode):
    u"""
    Считает геометрию обхода для одной "второй" линии против списка
    base_lines ([(p1, p2), ...] — концы каждой базовой линии), в
    указанном режиме (см. ask_bypass_mode) — БЕЗ выбора стороны (сторона
    спрашивается отдельно, см. ask_side_reference/build_curves_for_side).
    Возвращает (line_plan, error): line_plan — dict с геометрией пролётов,
    достаточной, чтобы построить кривые под выбранную сторону без
    повторного пересчёта пересечений; либо None с текстом причины
    пропуска (нет пересечений, диаметр/запас не помещается на линии,
    пересечения слишком близки друг к другу в «Одиночном» режиме).
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

    line_style = None
    try:
        line_style = second_el.LineStyle
    except:
        pass

    return {
        "element": second_el,
        "a1": a1,
        "a2": a2,
        "dir_x": dir_x,
        "dir_y": dir_y,
        "length": length,
        "spans": spans,
        "line_style": line_style,
    }, None


def build_curves_for_side(line_plan, side_pt):
    u"""
    Строит последовательность Line/Arc (прямая-дуга-...-прямая) для
    line_plan (см. compute_line_plan) с заданной точкой стороны обхода
    side_pt — общей на все пролёты ЭТОЙ линии (если пролётов несколько,
    все выгибаются в одну сторону, но у разных линий сторона может быть
    своя — см. run_line_bypass_tool). Каждый пролёт выгибается в сторону
    side_pt (знак скалярного произведения перпендикуляра пролёта на
    вектор к этой точке от его центра).
    """
    a1 = line_plan["a1"]
    a2 = line_plan["a2"]
    dir_x = line_plan["dir_x"]
    dir_y = line_plan["dir_y"]
    length = line_plan["length"]

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

    for c1_pos, c2_pos in line_plan["spans"]:
        if c1_pos > prev_pos + EPS_FT:
            curves.append(Line.CreateBound(point_at(prev_pos), point_at(c1_pos)))

        c1 = point_at(c1_pos)
        c2 = point_at(c2_pos)
        center_pos = (c1_pos + c2_pos) / 2.0
        span_radius = (c2_pos - c1_pos) / 2.0
        center_point = point_at(center_pos)

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

    return curves


def build_and_commit_line(doc, view, line_plan, side_pt):
    u"""
    Строит curves (см. build_curves_for_side) и сразу коммитит: удаляет
    исходную вторую линию, создаёт новые DetailCurve со стилем линии
    оригинала — всё в одной транзакции.
    """
    curves = build_curves_for_side(line_plan, side_pt)

    with revit.Transaction(u"Обход линии"):
        doc.Delete(line_plan["element"].Id)
        for new_curve in curves:
            detail_curve = doc.Create.NewDetailCurve(view, new_curve)
            if line_plan["line_style"] is not None:
                try:
                    detail_curve.LineStyle = line_plan["line_style"]
                except:
                    pass


def run_line_bypass_tool(doc, uidoc, view):
    u"""
    Полный сценарий кнопки: диаметр -> режим -> базовые линии (одним
    PickObjects, многократный выбор) -> цикл «вторая линия -> сторона ->
    сразу построить» (см. docstring модуля), пока не нажмут Esc на шаге
    выбора второй линии.
    """
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

    built_count = 0
    notes = []

    while True:
        try:
            second_ref = uidoc.Selection.PickObject(
                ObjectType.Element, selection_filter,
                u"Выберите линию, которая обойдёт базовые (Esc — закончить)"
            )
        except OperationCanceledException:
            break

        second_el = doc.GetElement(second_ref)

        if second_el.Id in base_ids:
            forms.alert(u"Это базовая линия, она должна остаться целой — выберите другую.")
            continue

        line_plan, error = compute_line_plan(base_lines, second_el, radius_ft, bundle_mode)
        if line_plan is None:
            notes.append(u"ID {}: {}".format(second_el.Id.IntegerValue, error))
            continue

        highlight_elements(uidoc, [second_el])

        side_pt = ask_side_reference(
            uidoc,
            u"Укажите сторону обхода для этой линии (Esc — пропустить эту линию)"
        )
        if side_pt is None:
            notes.append(u"ID {}: выбор стороны отменён — пропущено".format(second_el.Id.IntegerValue))
            continue

        try:
            build_and_commit_line(doc, view, line_plan, side_pt)
            built_count += 1
        except Exception as ex:
            notes.append(u"ID {}: не удалось построить обход — {}".format(second_el.Id.IntegerValue, ex))

    if built_count == 0 and not notes:
        forms.alert(u"Обход не построен — вторые линии не выбирались.", exitscript=True)
        return

    message = u"Готово. Построено обходов: {}".format(built_count)
    if notes:
        message += u"\n\nПримечания:\n" + u"\n".join(notes)
    forms.alert(message)
