# -*- coding: utf-8 -*-
"""Обрезка вида по двум точкам (`Tools.panel/CropView`).

Пользователь указывает мышью два противоположных угла прямоугольника, затем
выбирает, что обрезать: сам вид или его копию (простую, с детализацией или
зависимую), с суффиксом в конце имени копии. По углам задаётся область подрезки
(CropBox) и включается подрезка аннотаций с минимальным отступом от неё —
аннотации за пределами рамки тоже скрываются.

Чистая часть (`crop_rect`, `copy_name`, `MODES`) работает на кортежах/строках
и покрыта `tests/test_view_crop.py`; остальное — Revit API.
"""

MM_IN_FOOT = 304.8

# Меньше этого (по любой стороне, в футах) рамку не строим: скорее всего,
# пользователь дважды кликнул в одну точку.
MIN_SIZE_FT = 10.0 / MM_IN_FOOT

# Минимальный отступ подрезки аннотаций от рамки вида (в футах бумаги).
# Revit не принимает отступ меньше ~1 мм на листе; если не примет и этот —
# отступ останется прежним, а сама подрезка аннотаций всё равно включится.
ANNOTATION_OFFSET_FT = 1.0 / MM_IN_FOOT


# Что обрезать: (ключ, подпись в окне, имя ViewDuplicateOption или None).
MODE_SELF = "self"
MODES = (
    (MODE_SELF, u"Обрезать этот вид", None),
    ("copy", u"Копировать вид", "Duplicate"),
    ("detailing", u"Копировать с детализацией", "WithDetailing"),
    ("dependent", u"Копировать как зависимый", "AsDependent"),
)
DEFAULT_MODE = "copy"
DEFAULT_SUFFIX = u" - Фрагмент"

# Символы, недопустимые в именах видов Revit.
_FORBIDDEN = u"\\:{}[]|;<>?`~"


def copy_name(suffix, source_name, existing):
    """Имя копии: имя исходного вида + суффикс; если занято — « (2)», « (3)», …"""
    text = u"".join(ch for ch in (source_name or u"") + (suffix or u"") if ch not in _FORBIDDEN)
    name = u" ".join(text.split()) or u"Фрагмент"
    if name not in existing:
        return name
    i = 2
    while u"{} ({})".format(name, i) in existing:
        i += 1
    return u"{} ({})".format(name, i)


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


def available_modes(view):
    """MODES, которые Revit разрешает для этого вида (CanViewBeDuplicated)."""
    from Autodesk.Revit.DB import ViewDuplicateOption
    result = []
    for key, label, option in MODES:
        if option is None:
            result.append((key, label, option))
            continue
        try:
            if view.CanViewBeDuplicated(getattr(ViewDuplicateOption, option)):
                result.append((key, label, option))
        except Exception:
            pass
    return result


def duplicate_view(doc, view, mode, suffix):
    """Копия вида в режиме mode (ключ из MODES) с именем «имя вида + суффикс».
    Вызывать в транзакции. Для MODE_SELF возвращает сам view."""
    from Autodesk.Revit.DB import Element, FilteredElementCollector, View, ViewDuplicateOption
    option = dict((k, o) for k, _l, o in MODES).get(mode)
    if option is None:
        return view
    new_view = doc.GetElement(view.Duplicate(getattr(ViewDuplicateOption, option)))
    existing = set()
    for v in FilteredElementCollector(doc).OfClass(View):
        try:
            if v.Id != new_view.Id:
                existing.add(Element.Name.GetValue(v))
        except Exception:
            pass
    new_view.Name = copy_name(suffix, Element.Name.GetValue(view), existing)
    return new_view


def check_points(view, pt1, pt2):
    """ValueError, если по двум точкам модели рамка вида выйдет вырожденной."""
    inv = view.CropBox.Transform.Inverse
    a = inv.OfPoint(pt1)
    b = inv.OfPoint(pt2)
    crop_rect((a.X, a.Y), (b.X, b.Y))


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
