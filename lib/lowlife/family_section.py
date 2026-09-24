# -*- coding: utf-8 -*-
"""
Разрез по экземпляру семейства — тело кнопки «Разрез по семейству»
(Tools.panel/FamilySection).

Разрез смотрит на «лицо» семейства (FamilyInstance.FacingOrientation —
для настенных устройств это сторона, обращённая в помещение). Линейные
элементы и системные семейства (кабельные лотки, короба, трубы,
воздуховоды, стены — не FamilyInstance) тоже поддерживаются: для них
разрез идёт вдоль оси элемента и смотрит на его бок (см.
facing_direction). Разрез сразу обрезан:
  - по высоте — от базового уровня семейства до следующего уровня выше;
  - по ширине — габарит геометрии семейства + side_mm слева и справа;
  - по глубине — плоскость сечения на front_mm перед передней гранью
    геометрии, дальняя граница — на back_mm за задней гранью.

Габарит геометрии считается по реальным точкам тела семейства
(рёбра солидов, кривые, вершины сеток — GetInstanceGeometry, т.е. уже в
координатах модели), спроецированным на оси разреза — поэтому повёрнутое
на плане семейство не «раздувается», как было бы с осевым BoundingBox.

Про ориентацию BoundingBoxXYZ для ViewSection.CreateSection: вид смотрит
в сторону -BasisZ, BasisY — вверх, BasisX = BasisY × BasisZ (правая
тройка обязательна). Max.Z — плоскость сечения (ближняя граница),
Min.Z — дальняя граница подрезки.
"""

import re

from Autodesk.Revit.DB import (
    BoundingBoxXYZ, BuiltInCategory, BuiltInParameter, CategoryType,
    ElementId, FamilyInstance, LocationCurve,
    FilteredElementCollector, GeometryInstance, Level, Mesh, Options, Point,
    Solid, Curve, Transform, View, Wall, ViewDetailLevel, ViewFamily,
    ViewFamilyType, ViewSection, ViewType, XYZ, Element, ElementTypeGroup
)

from lowlife import geometry

MM_IN_FOOT = 304.8

# Уровень «выше» должен быть выше базового хотя бы на эту величину — чтобы
# два уровня на одной отметке не дали разрез нулевой высоты.
_LEVEL_TOL_FT = 1.0 / MM_IN_FOOT

# Если над базовым уровнем больше нет уровней — верх подрезки берётся как
# max(базовый уровень + FALLBACK_HEIGHT_MM, верх геометрии + FALLBACK_TOP_GAP_MM).
FALLBACK_HEIGHT_MM = 3000.0
FALLBACK_TOP_GAP_MM = 500.0

# Символы, недопустимые в имени вида Revit.
_BAD_NAME_CHARS = re.compile(u"[\\\\:{}\\[\\]|;<>?`~]")

NAME_PLACEHOLDERS = [
    (u"{Семейство}", u"имя семейства"),
    (u"{Тип}", u"имя типоразмера"),
    (u"{Марка}", u"параметр «Марка» экземпляра"),
    (u"{Уровень}", u"базовый уровень"),
    (u"{Id}", u"ElementId экземпляра"),
]


def mm_to_ft(mm):
    return float(mm) / MM_IN_FOOT


def safe_name(el):
    """Element.Name.GetValue(el) — см. CLAUDE.md про неоднозначное связывание el.Name."""
    try:
        return Element.Name.GetValue(el) or u""
    except Exception:
        try:
            return el.Name or u""
        except Exception:
            return u""


# --- что можно выбрать --------------------------------------------------------

def _bic_ids(*names):
    ids = set()
    for name in names:
        try:
            ids.add(int(getattr(BuiltInCategory, name)))
        except Exception:
            pass
    return ids


# Модельные категории, по которым разрез «по элементу» смысла не имеет.
# Обобщённые модели здесь НЕ исключаются (в отличие от
# selection.is_pickable_model_element) — по ним разрез как раз нужен.
_NOT_SECTIONABLE_CATEGORY_IDS = _bic_ids(
    "OST_Grids", "OST_Levels", "OST_CLines", "OST_SketchLines",
    "OST_RvtLinks", "OST_Rooms", "OST_MEPSpaces", "OST_Areas",
    "OST_SectionBox", "OST_Cameras", "OST_Viewers", "OST_ScopeBoxes",
    "OST_Lines",
)


def is_sectionable(el):
    """
    True для модельного элемента текущего документа с геометрией: любые
    семейства (FamilyInstance) и системные элементы — кабельные лотки,
    короба, трубы, воздуховоды, стены и т.п.
    """
    if el is None:
        return False
    try:
        if el.Document.IsLinked:
            return False
    except Exception:
        pass
    try:
        cat = el.Category
    except Exception:
        cat = None
    if cat is None:
        return False
    try:
        if cat.CategoryType != CategoryType.Model:
            return False
        if cat.Id.IntegerValue in _NOT_SECTIONABLE_CATEGORY_IDS:
            return False
    except Exception:
        return False
    try:
        if el.ViewSpecific:
            return False
    except Exception:
        pass
    try:
        return el.get_BoundingBox(None) is not None
    except Exception:
        return False


# --- справочники для окна настроек ------------------------------------------

def list_section_templates(doc):
    """Шаблоны видов для разрезов (IsTemplate, ViewType.Section), по имени."""
    result = []
    for view in FilteredElementCollector(doc).OfClass(View):
        try:
            if view.IsTemplate and view.ViewType == ViewType.Section:
                result.append(view)
        except Exception:
            continue
    return sorted(result, key=safe_name)


def list_section_types(doc):
    """Типоразмеры разрезов (ViewFamilyType с ViewFamily.Section), по имени."""
    result = []
    for vft in FilteredElementCollector(doc).OfClass(ViewFamilyType):
        try:
            if vft.ViewFamily == ViewFamily.Section:
                result.append(vft)
        except Exception:
            continue
    return sorted(result, key=safe_name)


def find_by_name(elements, name):
    name = unicode(name or u"").strip()
    if not name:
        return None
    for el in elements:
        if safe_name(el) == name:
            return el
    return None


def default_section_type(doc):
    """Типоразмер разреза по умолчанию в проекте, иначе — первый найденный."""
    try:
        type_id = doc.GetDefaultElementTypeId(ElementTypeGroup.ViewTypeSection)
        if type_id and type_id != ElementId.InvalidElementId:
            vft = doc.GetElement(type_id)
            if vft is not None:
                return vft
    except Exception:
        pass
    types = list_section_types(doc)
    return types[0] if types else None


# --- геометрия ---------------------------------------------------------------

def _collect_points(geom, points):
    if geom is None:
        return
    for g in geom:
        try:
            if isinstance(g, GeometryInstance):
                _collect_points(g.GetInstanceGeometry(), points)
            elif isinstance(g, Solid):
                if g.Faces.Size == 0:
                    continue
                for edge in g.Edges:
                    points.extend(edge.Tessellate())
            elif isinstance(g, Curve):
                points.extend(g.Tessellate())
            elif isinstance(g, Mesh):
                points.extend(g.Vertices)
            elif isinstance(g, Point):
                points.append(g.Coord)
        except Exception:
            continue


def element_points(el):
    """
    Точки тела элемента в координатах модели. Если геометрию получить не
    удалось — 8 углов BoundingBox (грубее для повёрнутых элементов, но
    лучше, чем ничего).
    """
    points = []
    try:
        opts = Options()
        opts.ComputeReferences = False
        opts.IncludeNonVisibleObjects = False
        opts.DetailLevel = ViewDetailLevel.Fine
        _collect_points(el.get_Geometry(opts), points)
    except Exception:
        points = []

    if points:
        return points

    bb = el.get_BoundingBox(None)
    if bb is None:
        return []
    mn, mx = bb.Min, bb.Max
    return [XYZ(x, y, z) for x in (mn.X, mx.X) for y in (mn.Y, mx.Y) for z in (mn.Z, mx.Z)]


def _horizontal(v):
    if v is None:
        return None
    h = XYZ(v.X, v.Y, 0.0)
    if h.GetLength() < 1e-6:
        return None
    return h.Normalize()


def _curve_direction(el):
    """Горизонтальное направление оси линейного элемента (хорда начало→конец)."""
    try:
        loc = el.Location
    except Exception:
        return None
    if not isinstance(loc, LocationCurve):
        return None
    try:
        curve = loc.Curve
        return _horizontal(curve.GetEndPoint(1) - curve.GetEndPoint(0))
    except Exception:
        return None


def _side_facing(direction):
    """
    Горизонтальная нормаль к оси, с какой стороны стоит наблюдатель. Из двух
    нормалей берётся та, что смотрит на -Y модели (наблюдатель «с юга»,
    смотрит «на север»); для осей вдоль Y — та, что смотрит на -X. Так
    разрезы по параллельным лоткам получаются одинаково ориентированными,
    а не зависят от того, в какую сторону лоток был начерчен.
    """
    n = XYZ.BasisZ.CrossProduct(direction).Normalize()
    if abs(n.Y) > 1e-6:
        return n if n.Y < 0 else n.Negate()
    return n if n.X < 0 else n.Negate()


def _instance_point(el):
    try:
        loc = el.Location
        if loc is not None and hasattr(loc, "Point"):
            return loc.Point
    except Exception:
        pass
    try:
        return el.GetTransform().Origin
    except Exception:
        return None


def _orient_away_from_wall_host(el, f):
    """
    Для экземпляра на стене (Host — Wall текущей модели) разворачивает f,
    если оно смотрит в стену: устройство стоит на поверхности стены, т.е.
    смещено от её оси в сторону помещения, и f должно смотреть туда же.
    Для основы-связи (RevitLinkInstance) и точки на самой оси — f как есть.
    """
    try:
        host = el.Host
    except Exception:
        host = None
    if host is None or not isinstance(host, Wall):
        return f
    pt = _instance_point(el)
    if pt is None:
        return f
    try:
        curve = host.Location.Curve
        proj = curve.Project(pt)
        if proj is None:
            return f
        off = XYZ(pt.X - proj.XYZPoint.X, pt.Y - proj.XYZPoint.Y, 0.0)
    except Exception:
        return f
    if off.GetLength() < _LEVEL_TOL_FT:
        return f
    return f if off.DotProduct(f) >= 0 else f.Negate()


def _family_facing(el):
    """
    Наружная сторона семейства:
      - семейство на вертикальной грани (face-based / по рабочей плоскости
        стены): ось Z экземпляра (GetTransform().BasisZ) — нормаль грани
        основы наружу. FacingOrientation у таких семейств лежит в
        плоскости стены (смотрит вверх) и для разреза не годится;
      - иначе — FacingOrientation;
      - если и оно вертикальное — ось Z экземпляра / HandOrientation.
    """
    try:
        bz = _horizontal(el.GetTransform().BasisZ)
    except Exception:
        bz = None
    if bz is not None:
        return bz

    try:
        f = _horizontal(el.FacingOrientation)
        if f is not None:
            return f
    except Exception:
        pass

    try:
        hand = _horizontal(el.HandOrientation)
        if hand is not None:
            # в семействе Facing (ось Y) = Z × Hand (ось X)
            return XYZ.BasisZ.CrossProduct(hand).Normalize()
    except Exception:
        pass
    return None


def facing_direction(el, flip=False):
    """
    Горизонтальное направление к наблюдателю разреза (разрез смотрит на
    элемент с этой стороны):
      - линейный элемент (LocationCurve: лоток, короб, труба, стена,
        балка) — перпендикуляр к оси (см. _side_facing), разрез идёт
        вдоль элемента;
      - FamilyInstance — лицевая сторона (_family_facing), для экземпляров
        на стене дополнительно проверенная по положению относительно оси
        стены (_orient_away_from_wall_host);
      - иначе / для вертикального стояка — -Y модели («на север»).
    flip=True — смотреть с противоположной стороны (настройка кнопки, на
    случай семейств с «перевёрнутой» лицевой стороной).
    """
    f = None
    direction = _curve_direction(el)
    if direction is not None:
        f = _side_facing(direction)
    elif isinstance(el, FamilyInstance):
        f = _family_facing(el)
        if f is not None:
            f = _orient_away_from_wall_host(el, f)
    if f is None:
        f = XYZ(0.0, -1.0, 0.0)
    return f.Negate() if flip else f


# --- уровни ------------------------------------------------------------------

_LEVEL_PARAMS = [
    "RBS_START_LEVEL_PARAM",
    "WALL_BASE_CONSTRAINT",
    "FAMILY_LEVEL_PARAM",
    "INSTANCE_SCHEDULE_ONLY_LEVEL_PARAM",
    "SCHEDULE_LEVEL_PARAM",
    "INSTANCE_REFERENCE_LEVEL_PARAM",
]


def _level_from_param(doc, el):
    for bip_name in _LEVEL_PARAMS:
        try:
            p = el.get_Parameter(getattr(BuiltInParameter, bip_name))
        except Exception:
            continue
        if p is None:
            continue
        try:
            lv = doc.GetElement(p.AsElementId())
        except Exception:
            continue
        if isinstance(lv, Level):
            return lv
    return None


def base_level(doc, el, fallback_z=None):
    """
    Базовый уровень элемента: Element.LevelId, MEPCurve.ReferenceLevel,
    затем уровневые параметры экземпляра, затем уровень основы (для семейств на основе), и в самом
    крайнем случае — ближайший уровень снизу от низа геометрии.
    """
    lv = geometry.get_element_level(doc, el)
    if isinstance(lv, Level):
        return lv

    try:
        lv = el.ReferenceLevel  # MEPCurve: лотки, короба, трубы, воздуховоды
    except Exception:
        lv = None
    if isinstance(lv, Level):
        return lv

    lv = _level_from_param(doc, el)
    if lv is not None:
        return lv

    try:
        host = el.Host
    except Exception:
        host = None
    if host is not None:
        lv = geometry.get_element_level(doc, host)
        if isinstance(lv, Level):
            return lv

    if fallback_z is not None:
        levels = sorted(FilteredElementCollector(doc).OfClass(Level), key=lambda l: l.ProjectElevation)
        below = [l for l in levels if l.ProjectElevation <= fallback_z + _LEVEL_TOL_FT]
        if below:
            return below[-1]
        if levels:
            return levels[0]
    return None


def level_above(doc, level):
    """Ближайший уровень строго выше level (по ProjectElevation), иначе None."""
    base_z = level.ProjectElevation
    above = [l for l in FilteredElementCollector(doc).OfClass(Level)
             if l.ProjectElevation > base_z + _LEVEL_TOL_FT]
    if not above:
        return None
    return min(above, key=lambda l: l.ProjectElevation)


# --- имя вида ----------------------------------------------------------------

def _instance_mark(el):
    try:
        p = el.get_Parameter(BuiltInParameter.ALL_MODEL_MARK)
        if p is not None:
            return p.AsString() or u""
    except Exception:
        pass
    return u""


def build_view_name(doc, el, level, mask):
    family_name = u""
    type_name = u""
    try:
        symbol = doc.GetElement(el.GetTypeId())
        if symbol is not None:
            type_name = safe_name(symbol)
            try:
                family_name = symbol.FamilyName or u""
            except Exception:
                family_name = u""
    except Exception:
        pass

    values = {
        u"{Семейство}": family_name,
        u"{Тип}": type_name,
        u"{Марка}": _instance_mark(el),
        u"{Уровень}": geometry.level_name(level) if level is not None else u"",
        u"{Id}": unicode(el.Id.IntegerValue),
    }

    name = unicode(mask or u"")
    for key, val in values.items():
        name = name.replace(key, unicode(val))

    name = _BAD_NAME_CHARS.sub(u"_", name)
    name = u" ".join(name.split())
    return name or u"Разрез {}".format(el.Id.IntegerValue)


def existing_view_names(doc):
    names = set()
    for v in FilteredElementCollector(doc).OfClass(View):
        n = safe_name(v)
        if n:
            names.add(n)
    return names


def unique_name(name, taken):
    """name, а если занято — «name (2)», «name (3)», ... Добавляет результат в taken."""
    candidate = name
    i = 2
    while candidate in taken:
        candidate = u"{} ({})".format(name, i)
        i += 1
    taken.add(candidate)
    return candidate


# --- построение ---------------------------------------------------------------

class SectionResult(object):
    def __init__(self, element):
        self.element = element
        self.view = None
        self.name = u""
        self.warnings = []
        self.error = None


def compute_section_box(doc, el, side_mm, front_mm, back_mm, flip=False):
    """
    (BoundingBoxXYZ, base_level, top_level_or_None, warnings) для разреза по
    элементу, либо поднимает ValueError, если у элемента нет геометрии/уровня.
    """
    warnings = []

    points = element_points(el)
    if not points:
        raise ValueError(u"не удалось получить геометрию элемента")

    min_geom_z = min(p.Z for p in points)
    max_geom_z = max(p.Z for p in points)

    level = base_level(doc, el, fallback_z=min_geom_z)
    if level is None:
        raise ValueError(u"в проекте нет уровней")

    bottom_z = level.ProjectElevation
    top = level_above(doc, level)
    if top is not None:
        top_z = top.ProjectElevation
    else:
        top_z = max(bottom_z + mm_to_ft(FALLBACK_HEIGHT_MM),
                    max_geom_z + mm_to_ft(FALLBACK_TOP_GAP_MM))
        warnings.append(
            u"над уровнем «{}» нет уровней — верх подрезки взят на {:.0f} мм "
            u"выше базового уровня".format(
                geometry.level_name(level), (top_z - bottom_z) * MM_IN_FOOT))

    toward_viewer = facing_direction(el, flip)    # BasisZ: к наблюдателю
    up = XYZ.BasisZ                               # BasisY
    right = up.CrossProduct(toward_viewer)        # BasisX = Y × Z

    cx = sum(p.X for p in points) / len(points)
    cy = sum(p.Y for p in points) / len(points)
    origin = XYZ(cx, cy, bottom_z)

    xs = []
    zs = []
    for p in points:
        v = p - origin
        xs.append(v.DotProduct(right))
        zs.append(v.DotProduct(toward_viewer))

    t = Transform.Identity
    t.Origin = origin
    t.BasisX = right
    t.BasisY = up
    t.BasisZ = toward_viewer

    box = BoundingBoxXYZ()
    box.Enabled = True
    box.Transform = t
    box.Min = XYZ(min(xs) - mm_to_ft(side_mm), 0.0, min(zs) - mm_to_ft(back_mm))
    box.Max = XYZ(max(xs) + mm_to_ft(side_mm), top_z - bottom_z, max(zs) + mm_to_ft(front_mm))

    return box, level, top, warnings


def create_family_section(doc, el, section_type, template, name_mask,
                          side_mm, front_mm, back_mm, taken_names, flip=False):
    """
    Создаёт разрез по элементу (внутри уже открытой транзакции). Возвращает
    SectionResult; ошибки по конкретному элементу не пробрасываются, а
    пишутся в result.error — чтобы при нескольких выбранных семействах
    одно неудачное не отменяло остальные.
    """
    result = SectionResult(el)
    try:
        box, level, _top, warnings = compute_section_box(doc, el, side_mm, front_mm, back_mm, flip)
        result.warnings.extend(warnings)

        view = ViewSection.CreateSection(doc, section_type.Id, box)

        if template is not None:
            try:
                view.ViewTemplateId = template.Id
            except Exception as ex:
                result.warnings.append(u"не удалось назначить шаблон: {}".format(ex))

        try:
            view.CropBoxActive = True
        except Exception:
            pass

        name = unique_name(build_view_name(doc, el, level, name_mask), taken_names)
        try:
            view.Name = name
        except Exception as ex:
            result.warnings.append(u"не удалось задать имя «{}»: {}".format(name, ex))
            name = safe_name(view)

        result.view = view
        result.name = name
    except Exception as ex:
        result.error = unicode(ex)
    return result
