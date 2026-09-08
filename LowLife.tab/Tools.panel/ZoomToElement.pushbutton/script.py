# -*- coding: utf-8 -*-

__title__ = "Зум к\nэлементу"
__doc__ = (
    "Приближает вид к элементу. Если элемент уже выбран в модели — просто "
    "зумирует к нему (к нескольким выбранным — к их общему габариту). Если "
    "ничего не выбрано — спрашивает ID элемента и зумирует к нему. Если "
    "элемента не видно на активном виде, подсказывает, на какой уровень "
    "(план/разрез/3D) переключиться, чтобы он был заметен."
)
__author__ = "Pipers"

import clr

clr.AddReference('RevitAPI')
clr.AddReference('RevitAPIUI')

from Autodesk.Revit.DB import (
    BuiltInParameter,
    ElementId,
    FilteredElementCollector,
    Level,
    LocationCurve,
    LocationPoint,
    XYZ,
)
from System.Collections.Generic import List

from pyrevit import revit, forms

doc = revit.doc
uidoc = revit.uidoc
view = doc.ActiveView

MM_IN_FOOT = 304.8

# Минимальный «радиус» кадра вокруг элемента (мм в плане) — чтобы кнопка не
# приближала вплотную к мелкому символу устройства, а оставляла контекст.
MIN_HALF_MM = 1500.0

# Запас вокруг габарита элемента (доля от радиуса), чтобы элемент не упирался
# в края экрана.
PADDING_RATIO = 0.35

# Параметры, в которых у разных категорий лежит ссылка на уровень элемента —
# перебираем по очереди, если у элемента нет прямого свойства LevelId.
LEVEL_BIPS = (
    BuiltInParameter.FAMILY_LEVEL_PARAM,
    BuiltInParameter.SCHEDULE_LEVEL_PARAM,
    BuiltInParameter.INSTANCE_SCHEDULE_ONLY_LEVEL_PARAM,
    BuiltInParameter.INSTANCE_REFERENCE_LEVEL_PARAM,
    BuiltInParameter.FAMILY_BASE_LEVEL_PARAM,
    BuiltInParameter.RBS_START_LEVEL_PARAM,
    BuiltInParameter.LEVEL_PARAM,
)


def get_selected_elements():
    ids = list(uidoc.Selection.GetElementIds())
    return [doc.GetElement(eid) for eid in ids if doc.GetElement(eid) is not None]


def ask_element_by_id():
    raw = forms.ask_for_string(
        default="",
        prompt=u"Введите ID элемента, к которому нужно приблизить вид:",
        title=u"Зум к элементу"
    )

    if raw is None:
        # Пользователь закрыл окно — тихо выходим.
        forms.alert(u"Операция отменена.", exitscript=True)

    raw = raw.strip()
    if not raw:
        forms.alert(u"ID не введён.", exitscript=True)

    try:
        int_id = int(raw)
    except ValueError:
        forms.alert(u"«{}» — это не число. ID элемента должен быть целым числом.".format(raw), exitscript=True)

    el = doc.GetElement(ElementId(int_id))
    if el is None:
        forms.alert(
            u"Элемент с ID {} не найден в текущем документе. Возможно, он "
            u"удалён или находится в связанной модели.".format(int_id),
            exitscript=True
        )

    return el


def get_level_name(el):
    """Имя уровня элемента: свойство LevelId -> типовые параметры -> ближайший уровень по Z."""
    try:
        lid = el.LevelId
        if lid is not None and lid != ElementId.InvalidElementId:
            lvl = doc.GetElement(lid)
            if lvl is not None:
                return lvl.Name
    except:
        pass

    for bip in LEVEL_BIPS:
        try:
            p = el.get_Parameter(bip)
            if p and p.HasValue:
                lvl = doc.GetElement(p.AsElementId())
                if lvl is not None:
                    return lvl.Name
        except:
            pass

    # Ближайший уровень по средней отметке габаритного контейнера элемента.
    try:
        bb = el.get_BoundingBox(None)
        if bb is not None:
            z = (bb.Min.Z + bb.Max.Z) / 2.0
            levels = list(FilteredElementCollector(doc).OfClass(Level))
            if levels:
                nearest = min(levels, key=lambda L: abs(L.Elevation - z))
                return nearest.Name
    except:
        pass

    return None


def get_elevation_m(el):
    try:
        bb = el.get_BoundingBox(None)
        if bb is not None:
            return (bb.Min.Z + bb.Max.Z) / 2.0 * MM_IN_FOOT / 1000.0
    except:
        pass
    return None


def view_bbox_world(el):
    """Габарит элемента на активном виде (в мировых координатах) или None, если элемента на виде не видно."""
    try:
        bb = el.get_BoundingBox(view)
    except:
        bb = None
    if bb is None:
        return None, None
    try:
        t = bb.Transform
        pts = [
            t.OfPoint(XYZ(bb.Min.X, bb.Min.Y, bb.Min.Z)),
            t.OfPoint(XYZ(bb.Max.X, bb.Max.Y, bb.Max.Z)),
        ]
        xs = [p.X for p in pts]
        ys = [p.Y for p in pts]
        zs = [p.Z for p in pts]
        return XYZ(min(xs), min(ys), min(zs)), XYZ(max(xs), max(ys), max(zs))
    except:
        return bb.Min, bb.Max


def element_center(el):
    """
    «Визуальный» центр элемента для зума. Точка/кривая расположения даёт
    центр гораздо точнее, чем середина bounding box: у семейств bbox часто
    несимметричен (учитывает выносные элементы, вложенные семейства, хост),
    и центрирование по нему уводит элемент от середины экрана.
    """
    try:
        loc = el.Location
    except:
        loc = None

    if isinstance(loc, LocationPoint):
        return loc.Point
    if isinstance(loc, LocationCurve):
        try:
            return loc.Curve.Evaluate(0.5, True)
        except:
            pass
    return None


def zoom_center_radius(center, radius):
    """
    Приближает активный вид так, чтобы center оказался в середине экрана.
    Прямоугольник строится СИММЕТРИЧНО вокруг center — тогда его середина
    (а именно её ставит по центру ZoomAndCenterRectangle) точно совпадает
    с центром элемента.
    """
    r = max(radius, MIN_HALF_MM / MM_IN_FOOT)
    r = r * (1.0 + PADDING_RATIO)

    p1 = XYZ(center.X - r, center.Y - r, center.Z)
    p2 = XYZ(center.X + r, center.Y + r, center.Z)

    for uv in uidoc.GetOpenUIViews():
        if uv.ViewId == view.Id:
            uv.ZoomAndCenterRectangle(p1, p2)
            try:
                uidoc.RefreshActiveView()
            except:
                pass
            return True
    return False


def hint_where_to_look(elements):
    el = elements[0]
    level_name = get_level_name(el)
    elev_m = get_elevation_m(el)

    active_level = getattr(view, "GenLevel", None)
    active_level_name = active_level.Name if active_level is not None else None

    elev_line = u"\nОтметка элемента ≈ {:.2f} м.".format(elev_m) if elev_m is not None else u""

    if level_name and active_level_name and level_name == active_level_name:
        forms.alert(
            u"Элемент относится к уровню активного вида («{}»), но на виде "
            u"не показан. Проверьте: видимость его категории (VG), фильтры "
            u"вида, стадию (Phase) и диапазон вида (View Range) — элемент "
            u"может быть выше/ниже секущей плоскости.{}".format(level_name, elev_line),
            title=u"Зум к элементу"
        )
    elif level_name:
        forms.alert(
            u"Элемента не видно на активном виде. Похоже, он расположен на "
            u"уровне «{}». Переключитесь на план этого уровня (или на "
            u"подходящий разрез / 3D-вид) и запустите кнопку снова.{}".format(level_name, elev_line),
            title=u"Зум к элементу"
        )
    else:
        forms.alert(
            u"Элемента не видно на активном виде, и определить его уровень "
            u"не удалось. Откройте 3D-вид или разрез, где элемент виден, и "
            u"запустите кнопку снова.{}".format(elev_line),
            title=u"Зум к элементу"
        )


# ------------------------------------------------------------
# ОСНОВНОЙ СЦЕНАРИЙ
# ------------------------------------------------------------

elements = get_selected_elements()

if not elements:
    el = ask_element_by_id()
    elements = [el]
    # Выделяем найденный по ID элемент, чтобы его было видно после зума.
    sel_ids = List[ElementId]()
    sel_ids.Add(el.Id)
    try:
        uidoc.Selection.SetElementIds(sel_ids)
    except:
        pass

# Габариты на активном виде — только по элементам, которые на нём видны.
boxes = []
for el in elements:
    pmin, pmax = view_bbox_world(el)
    if pmin is not None:
        boxes.append((pmin, pmax))

if not boxes:
    # Ни один из элементов не виден на активном виде — подсказываем куда смотреть.
    hint_where_to_look(elements)
else:
    # Центр кадра: точка расположения единственного элемента (самый точный
    # центр), иначе — середина общего габарита видимых элементов.
    center = element_center(elements[0]) if len(elements) == 1 else None
    if center is None:
        cx = sum((b[0].X + b[1].X) for b in boxes) / (2.0 * len(boxes))
        cy = sum((b[0].Y + b[1].Y) for b in boxes) / (2.0 * len(boxes))
        cz = sum((b[0].Z + b[1].Z) for b in boxes) / (2.0 * len(boxes))
        center = XYZ(cx, cy, cz)

    # Радиус кадра — самый дальний угол габарита(ов) от выбранного центра
    # (в плане), чтобы элемент целиком попал в кадр и остался по центру.
    radius = 0.0
    for pmin, pmax in boxes:
        for x in (pmin.X, pmax.X):
            for y in (pmin.Y, pmax.Y):
                d = ((x - center.X) ** 2 + (y - center.Y) ** 2) ** 0.5
                if d > radius:
                    radius = d

    if not zoom_center_radius(center, radius):
        forms.alert(
            u"Не удалось приблизить вид: активный вид не открыт в отдельном "
            u"окне (например, вы находитесь на листе). Откройте сам вид и "
            u"запустите кнопку снова."
        )
