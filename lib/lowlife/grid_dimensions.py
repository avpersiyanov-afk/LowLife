# -*- coding: utf-8 -*-
"""Размеры видимых осей; маски и геометрия групп доступны без Revit."""

try:
    unicode
except NameError:
    unicode = str

import fnmatch
import math
import re


def matches_mask(name, mask):
    """Маски полного имени без учёта регистра, разделитель — точка с запятой."""
    name = unicode(name).strip().lower()
    patterns = [p.strip().lower() for p in (mask or u"*").split(u";") if p.strip()]
    return any(fnmatch.fnmatchcase(name, pattern) for pattern in patterns)


def marking_key(name):
    """Естественный порядок: 2 < 10, А/2 < А/10; одинаков для Python 2/3."""
    return tuple((1, int(part)) if part.isdigit() else (0, part)
                 for part in re.split(r"(\d+)", unicode(name).strip().lower()))


class GridLine(object):
    """Прямая ось в координатах вида, element нужен только для записи в Revit."""

    def __init__(self, element, name, start, end):
        self.element, self.name = element, name
        self.start, self.end = start, end


class GridGroup(object):
    def __init__(self, direction):
        self.direction = direction
        dx, dy = direction
        self.normal = (dy, -dx) if abs(dy) >= abs(dx) else (-dy, dx)
        self.lines = []

    def position(self, line):
        x = (line.start[0] + line.end[0]) / 2.0
        y = (line.start[1] + line.end[1]) / 2.0
        return x * self.normal[0] + y * self.normal[1]

    def chain(self):
        return sorted(self.lines, key=self.position)

    def extremes(self):
        lines = sorted(self.lines, key=lambda line: (marking_key(line.name), line.name))
        return [lines[0], lines[-1]]

    def dimension_points(self, lines, offset):
        dx, dy = self.direction
        along = min(p[0] * dx + p[1] * dy
                    for line in self.lines for p in (line.start, line.end)) - offset
        low = min(self.position(line) for line in lines)
        high = max(self.position(line) for line in lines)
        if high - low < 1e-6:
            return None
        nx, ny = self.normal
        return ((dx * along + nx * low, dy * along + ny * low),
                (dx * along + nx * high, dy * along + ny * high))


def group_lines(lines):
    """Разделить оси по параллельности, в том числе при повороте плана."""
    groups = []
    for line in lines:
        dx, dy = line.end[0] - line.start[0], line.end[1] - line.start[1]
        length = math.hypot(dx, dy)
        if length < 1e-6:
            continue
        dx, dy = dx / length, dy / length
        if (abs(dy) >= abs(dx) and dy < 0) or (abs(dx) > abs(dy) and dx < 0):
            dx, dy = -dx, -dy
        group = next((g for g in groups
                      if abs(dx * g.direction[1] - dy * g.direction[0]) < 1e-8), None)
        if group is None:
            group = GridGroup((dx, dy))
            groups.append(group)
        group.lines.append(line)
    return [g for g in groups if len(g.lines) >= 2]


def collect_groups(doc, view, mask):
    """Прямые оси текущей модели на активном плане; дуги пропускаются."""
    from Autodesk.Revit.DB import DatumExtentType, FilteredElementCollector, Grid, Line

    lines, skipped = [], 0
    right, up = view.RightDirection, view.UpDirection
    for grid in FilteredElementCollector(doc, view.Id).OfClass(Grid):
        if grid.IsHidden(view) or not matches_mask(grid.Name, mask):
            continue
        if not isinstance(grid.Curve, Line):
            skipped += 1
            continue
        curves = list(grid.GetCurvesInView(DatumExtentType.ViewSpecific, view))
        curve = curves[0] if curves else grid.Curve
        p0, p1 = curve.GetEndPoint(0), curve.GetEndPoint(1)
        lines.append(GridLine(grid, grid.Name,
                              (p0.DotProduct(right), p0.DotProduct(up)),
                              (p1.DotProduct(right), p1.DotProduct(up))))
    return group_lines(lines), skipped


def linear_dimension_types(doc):
    """Доступные типы, без служебных линейных стилей Revit."""
    from Autodesk.Revit.DB import ElementTypeGroup
    default = doc.GetElement(doc.GetDefaultElementTypeId(ElementTypeGroup.LinearDimensionType))
    if default is None:
        return []
    return [doc.GetElement(type_id) for type_id in default.GetSimilarTypes()]


def create_dimensions(doc, view, groups, dim_type, offset_mm, total_gap_mm):
    """Создать цепочки и общие размеры. Вызывать внутри транзакции."""
    from Autodesk.Revit.DB import Line, Reference, ReferenceArray

    right, up = view.RightDirection, view.UpDirection
    origin = view.Origin
    base = origin - right.Multiply(origin.DotProduct(right)) - up.Multiply(origin.DotProduct(up))
    chains, totals = [], []
    for group in groups:
        for lines, offset, output in (
                (group.chain(), offset_mm, chains),
                (group.extremes(), offset_mm + total_gap_mm, totals)):
            if output is totals and len(group.lines) < 3:
                continue
            points = group.dimension_points(lines, offset / 304.8)
            if points is None:
                continue
            points = [base + right.Multiply(x) + up.Multiply(y) for x, y in points]
            refs = ReferenceArray()
            for line in lines:
                refs.Append(Reference(line.element))
            dimension = doc.Create.NewDimension(view, Line.CreateBound(*points), refs, dim_type)
            output.append(dimension)
    return chains, totals
