# -*- coding: utf-8 -*-
"""
Логика кнопки BuildSkudSchematic ("Структурная схема СКУД"): раскладка
схемных семейств контроллеров и их устройств по цепям, без группы-эталона
— каждый контроллер и каждое его устройство вставляются как отдельный
экземпляр типа, назначенного в настройках СКУД для соответствующей
категории, в точке, вычисленной от точки контроллера.
"""


def layout_points_by_level(base_point, level_elevations, gap_ft):
    """
    Точки вставки для контроллеров, сгруппированных по этажам:
    level_elevations — список elevation (float, в футах), один элемент на
    контроллер, в том же порядке, что и сам список контроллеров.

    Этажи сортируются по elevation по возрастанию; первый (нижний) этаж
    располагается в base_point, следующие — со сдвигом вверх по Y на
    gap_ft за каждый этаж. Внутри одного этажа все точки идут единым
    горизонтальным рядом по X с шагом gap_ft, без ограничения длины ряда
    — контроллеров на одном этаже может быть сколько угодно.
    """
    from Autodesk.Revit.DB import XYZ

    distinct_elevations = sorted(set(level_elevations))
    row_index_by_elevation = {elev: row for row, elev in enumerate(distinct_elevations)}

    points = []
    col_by_row = {}
    for elev in level_elevations:
        row = row_index_by_elevation[elev]
        col = col_by_row.get(row, 0)
        col_by_row[row] = col + 1
        points.append(XYZ(
            base_point.X + col * gap_ft,
            base_point.Y + row * gap_ft,
            base_point.Z
        ))
    return points


def device_layout_point(insert_pt, category_layout, category, index_in_category, step_ft):
    """
    Точка вставки схемного устройства: insert_pt (точка контроллера) +
    смещение (dx, dy) категории из category_layout (в футах) + шаг
    вправо по X на каждый следующий экземпляр той же категории у этого
    же контроллера (index_in_category — 0 для первого).

    category_layout — {имя_категории: (dx_ft, dy_ft)}. Категория без
    записи в layout получает нулевое смещение (в точке контроллера).
    """
    from Autodesk.Revit.DB import XYZ

    dx, dy = category_layout.get(category, (0.0, 0.0))
    return XYZ(
        insert_pt.X + dx + index_in_category * step_ft,
        insert_pt.Y + dy,
        insert_pt.Z
    )
