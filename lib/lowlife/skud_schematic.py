# -*- coding: utf-8 -*-
"""
Логика кнопки BuildSkudSchematic ("Структурная схема СКУД"): раскладка
схемных семейств контроллеров и их устройств по цепям, без группы-эталона
— каждый контроллер и каждое его устройство вставляются как отдельный
экземпляр типа, назначенного в настройках СКУД для соответствующей
категории, в точке, вычисленной от точки контроллера.
"""


def layout_points(base_point, count, gap_ft, per_row):
    """
    Точки вставки для count контроллеров, рядами по per_row штук,
    начиная от base_point, с шагом gap_ft по X (внутри ряда) и по Y
    (между рядами, вниз).
    """
    from Autodesk.Revit.DB import XYZ

    points = []
    for i in range(count):
        row = i // per_row
        col = i % per_row
        points.append(XYZ(
            base_point.X + col * gap_ft,
            base_point.Y - row * gap_ft,
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
