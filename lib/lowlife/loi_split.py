# -*- coding: utf-8 -*-
u"""
Разделение прямого линейного элемента (лоток, короб, труба…) по границе
нескольких «Форм» — для кнопки «Заполнение LOI» (LOI.panel), см.
loi_fill.py/script.py.

Элемент, чья LocationCurve проходит сразу через несколько «Форм»
(match.forms из loi_fill.classify_elements), не может однозначно получить
одно общее значение параметра. Раньше такой элемент целиком уходил в
диалог конфликтов (loi_conflict_dialog.py), где пользователь для ВСЕГО
элемента выбирал одну форму-источник. Этот модуль вместо этого умеет
разрезать физический элемент ровно по границам форм: получившиеся отрезки
— отдельные элементы того же типа (копии исходного через
ElementTransformUtils.CopyElement, с подрезанной LocationCurve), каждый из
которых получает значения именно своей формы.

Работает только для ПРЯМЫХ участков (LocationCurve.Curve — Line):
у дуг понятие «отрезок между точкой A и точкой B» через скалярное
расстояние от начала не годится (нужна параметризация по самой кривой,
которую solid.IntersectWithCurve не даёт напрямую), поэтому такие
элементы plan_split() не трогает — они, как и раньше, остаются в диалоге
конфликтов. Туда же попадают элементы, чьи формы физически перекрываются
на этом отрезке (наложение больше SPLIT_TOL_FT) — разрезать по
неоднозначной границе нечем.

Куски всегда получаются СТЫКУЮЩИМИСЯ (общая точка разреза — конец одного
и начало следующего), но электрические/MEP-коннекторы между ними после
разреза не переподключаются — эта кнопка предназначена для простановки
атрибутов по зоне (LOI), а не для перестроения трассировки; физическая
непрерывность (полки совпадают) сохраняется, просто как отдельные
элементы, а не один связанный маршрут.
"""

from Autodesk.Revit.DB import (
    Line, ElementTransformUtils, SolidCurveIntersectionOptions, XYZ, LocationCurve
)

SPLIT_TOL_FT = 0.01  # ~3 мм — слияние близких точек разреза / допуск на наложение форм


class Piece(object):
    """Один отрезок разбиения вдоль исходной прямой: [t0, t1] (расстояние
    от начала кривой) + форма-источник значений (None — вне всех форм)."""

    def __init__(self, t0, t1, form):
        self.t0 = t0
        self.t1 = t1
        self.form = form


def _solid_segments_as_t(solid, line, p0):
    """Отрезки пересечения solid с line как (t0, t1) — расстояние от p0 (t0 <= t1)."""
    try:
        result = solid.IntersectWithCurve(line, SolidCurveIntersectionOptions())
    except:
        return []
    if result is None:
        return []

    out = []
    for i in range(result.SegmentCount):
        seg = result.GetCurveSegment(i)
        a = p0.DistanceTo(seg.GetEndPoint(0))
        b = p0.DistanceTo(seg.GetEndPoint(1))
        out.append((min(a, b), max(a, b)))
    return out


def plan_split(match):
    """
    Пытается построить план разбиения match.element по границам
    match.forms (match — loi_fill.MatchRecord с len(forms) >= 2).

    Возвращает список Piece, отсортированный по t и покрывающий [0, length]
    без пропусков (каждый Piece — свой кусок кривой; form=None у кусков вне
    всех форм), либо None, если разбиение невозможно:
      - элемент не прямой (нет LocationCurve, либо Curve не Line);
      - на этой прямой формы физически перекрываются сильнее SPLIT_TOL_FT;
      - ни одна форма не даёт на прямой отрезка длиннее допуска.
    None означает «оставить элемент как есть — конфликт решает
    loi_conflict_dialog.py», как раньше.
    """
    el = match.element

    try:
        loc = el.Location
    except:
        loc = None
    if not isinstance(loc, LocationCurve):
        return None

    curve = loc.Curve
    if not isinstance(curve, Line):
        return None

    p0 = curve.GetEndPoint(0)
    p1 = curve.GetEndPoint(1)
    length = p0.DistanceTo(p1)
    if length <= SPLIT_TOL_FT:
        return None

    intervals = []  # (t0, t1, form)
    for form in match.forms:
        for solid in form.solids:
            for t0, t1 in _solid_segments_as_t(solid, curve, p0):
                t0 = max(0.0, min(t0, length))
                t1 = max(0.0, min(t1, length))
                if t1 - t0 > SPLIT_TOL_FT:
                    intervals.append((t0, t1, form))

    if not intervals:
        return None

    intervals.sort(key=lambda x: x[0])

    # Наложение сильнее допуска — формы физически перекрываются на этом
    # отрезке, однозначной границы разреза нет.
    for i in range(1, len(intervals)):
        if intervals[i][0] < intervals[i - 1][1] - SPLIT_TOL_FT:
            return None

    breakpoints = set([0.0, length])
    for t0, t1, _form in intervals:
        breakpoints.add(t0)
        breakpoints.add(t1)
    breakpoints = sorted(breakpoints)

    pieces = []
    for i in range(len(breakpoints) - 1):
        t0, t1 = breakpoints[i], breakpoints[i + 1]
        if t1 - t0 <= SPLIT_TOL_FT:
            continue
        mid = (t0 + t1) / 2.0
        owner = None
        for it0, it1, form in intervals:
            if it0 - SPLIT_TOL_FT <= mid <= it1 + SPLIT_TOL_FT:
                owner = form
                break
        pieces.append(Piece(t0, t1, owner))

    # Меньше двух кусков — разбивать физически нечего (вся форма покрывает
    # элемент целиком), это не должно было попасть в match.forms > 1, но
    # на всякий случай отступаем к диалогу конфликтов, а не молчим.
    if len(pieces) < 2:
        return None

    return pieces


def _point_at(p0, p1, length, t):
    """Точка на отрезке [p0, p1] на расстоянии t от p0 (без операторов XYZ)."""
    if length <= SPLIT_TOL_FT:
        return p0
    frac = t / length
    return XYZ(
        p0.X + (p1.X - p0.X) * frac,
        p0.Y + (p1.Y - p0.Y) * frac,
        p0.Z + (p1.Z - p0.Z) * frac,
    )


def execute_split(doc, match, pieces):
    """
    Выполняет разбиение match.element на pieces (результат plan_split).
    **Вызывать внутри открытой транзакции.**

    Первый кусок переиспользует Id исходного элемента (просто подрезается
    его LocationCurve); остальные — копии через
    ElementTransformUtils.CopyElement (сохраняют тип/уровень/параметры
    экземпляра), каждой подрезается LocationCurve под свой [t0, t1].

    Возвращает список (element, form_or_None) — по одному на каждый
    получившийся кусок. Кусок, для которого подрезать кривую или создать
    копию не удалось (Revit отклонил геометрию), просто пропускается —
    список может быть короче pieces.
    """
    el = match.element
    loc = el.Location
    curve = loc.Curve
    p0 = curve.GetEndPoint(0)
    p1 = curve.GetEndPoint(1)
    length = p0.DistanceTo(p1)

    results = []

    first = pieces[0]
    try:
        loc.Curve = Line.CreateBound(
            _point_at(p0, p1, length, first.t0),
            _point_at(p0, p1, length, first.t1)
        )
        results.append((el, first.form))
    except:
        # не удалось подрезать даже исходный элемент — разбиение не
        # состоялось, вызывающий код должен трактовать это как отказ
        return []

    for piece in pieces[1:]:
        try:
            # Ненулевой сдвиг — иначе копия на мгновение (до сброса Curve
            # ниже) оказывается в точности там же, где исходный элемент, и
            # Revit может показать предупреждение о дублирующихся
            # экземплярах в одном месте.
            new_ids = ElementTransformUtils.CopyElement(doc, el.Id, XYZ(0, 0, 1.0))
        except:
            new_ids = None
        if new_ids is None or new_ids.Count == 0:
            continue

        new_el = doc.GetElement(list(new_ids)[0])
        try:
            new_loc = new_el.Location
            new_loc.Curve = Line.CreateBound(
                _point_at(p0, p1, length, piece.t0),
                _point_at(p0, p1, length, piece.t1)
            )
        except:
            continue

        results.append((new_el, piece.form))

    return results
