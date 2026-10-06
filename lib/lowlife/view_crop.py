# -*- coding: utf-8 -*-
"""Обрезка вида по двум точкам (`Tools.panel/CropView`).

Пользователь указывает мышью два противоположных угла прямоугольника; по ним
задаётся область подрезки вида (CropBox) и включается подрезка аннотаций с
минимальным отступом от неё — аннотации за пределами рамки тоже скрываются.

Чистая часть (`crop_rect`) работает на кортежах и покрыта
`tests/test_view_crop.py`; остальное — Revit API.
"""

MM_IN_FOOT = 304.8

# Меньше этого (по любой стороне, в футах) рамку не строим: скорее всего,
# пользователь дважды кликнул в одну точку.
MIN_SIZE_FT = 10.0 / MM_IN_FOOT

# Минимальный отступ подрезки аннотаций от рамки вида (в футах бумаги).
# Revit не принимает отступ меньше ~1 мм на листе; если не примет и этот —
# отступ останется прежним, а сама подрезка аннотаций всё равно включится.
ANNOTATION_OFFSET_FT = 1.0 / MM_IN_FOOT


def crop_rect(p1, p2, min_size=MIN_SIZE_FT):
    """(x1, y1), (x2, y2) в координатах вида -> (xmin, ymin, xmax, ymax).

    Углы можно указывать в любом порядке. ValueError, если рамка вырождена
    (по одной из сторон меньше `min_size`).
    """
    x1, y1 = float(p1[0]), float(p1[1])
    x2, y2 = float(p2[0]), float(p2[1])
    xmin, xmax = min(x1, x2), max(x1, x2)
    ymin, ymax = min(y1, y2), max(y1, y2)
    if xmax - xmin < min_size or ymax - ymin < min_size:
        raise ValueError(u"Рамка слишком мала: укажите два противоположных угла.")
    return xmin, ymin, xmax, ymax


# ---------------------------------------------------------------------------
# Revit API
# ---------------------------------------------------------------------------

def _view_types():
    from Autodesk.Revit.DB import ViewType
    names = ("FloorPlan", "CeilingPlan", "EngineeringPlan", "AreaPlan",
             "Section", "Elevation", "Detail")
    return set(getattr(ViewType, n) for n in names if hasattr(ViewType, n))


def unsupported_reason(view):
    """None, если вид можно обрезать этой кнопкой, иначе текст причины."""
    if view is None:
        return u"Нет активного вида."
    if view.IsTemplate:
        return u"Активный вид — шаблон вида."
    if view.ViewType not in _view_types():
        return (u"Обрезка по двум точкам работает на планах, разрезах, "
                u"фасадах и узлах. Активный вид: {}.".format(view.ViewType))
    return None


def ensure_work_plane(doc, view):
    """Рабочая плоскость вида для PickPoint (на разрезах/фасадах её часто нет).

    Создаёт плоскость через начало вида по его направлению; вызывать внутри
    транзакции. Возвращает True, если плоскость пришлось создать.
    """
    from Autodesk.Revit.DB import Plane, SketchPlane
    if view.SketchPlane is not None:
        return False
    plane = Plane.CreateByNormalAndOrigin(view.ViewDirection, view.Origin)
    view.SketchPlane = SketchPlane.Create(doc, plane)
    return True


def apply_crop(view, pt1, pt2):
    """Задаёт рамку подрезки вида по двум точкам модели (XYZ) и включает
    подрезку вида и аннотаций. Вызывать внутри транзакции.

    Возвращает список предупреждений (то, что не удалось, но не критично).
    """
    from Autodesk.Revit.DB import BuiltInParameter, XYZ

    warnings = []

    # Непрямоугольную (отредактированную) рамку сначала сбрасываем —
    # иначе новый CropBox не применится к её форме.
    manager = view.GetCropRegionShapeManager()
    try:
        if manager.ShapeSet:
            manager.RemoveCropRegionShape()
    except Exception:
        pass

    box = view.CropBox
    inv = box.Transform.Inverse
    a = inv.OfPoint(pt1)
    b = inv.OfPoint(pt2)
    xmin, ymin, xmax, ymax = crop_rect((a.X, a.Y), (b.X, b.Y))

    view.CropBoxActive = True
    box.Min = XYZ(xmin, ymin, box.Min.Z)
    box.Max = XYZ(xmax, ymax, box.Max.Z)
    view.CropBox = box

    ann = view.get_Parameter(BuiltInParameter.VIEWER_ANNOTATION_CROP_ACTIVE)
    if ann is None or ann.IsReadOnly:
        warnings.append(u"Подрезку аннотаций включить нельзя (параметр "
                        u"недоступен или задан шаблоном вида).")
    else:
        ann.Set(1)
        manager = view.GetCropRegionShapeManager()
        for prop in ("LeftAnnotationCropOffset", "RightAnnotationCropOffset",
                     "TopAnnotationCropOffset", "BottomAnnotationCropOffset"):
            try:
                setattr(manager, prop, ANNOTATION_OFFSET_FT)
            except Exception:
                pass
    return warnings
