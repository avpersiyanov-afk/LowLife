# -*- coding: utf-8 -*-
"""
Логика кнопки «Обновить имя уровня» (LOI.panel/UpdateLevelName.pushbutton):
назначает ОПОРНЫЙ УРОВЕНЬ выбранным экземплярам семейств, у которых его нет
вовсе (Element.LevelId пуст) и нет основы (Host) — типично экземпляр,
созданный NewFamilyInstance(point, symbol, StructuralType) без уровня
(запасная ветка companion_placement/skud_door_placement) или скопированный
откуда-то без привязки.

Два способа, по порядку:
  1. Параметр «Уровень» (FAMILY_LEVEL_PARAM / INSTANCE_REFERENCE_LEVEL_PARAM),
     если Revit разрешает его менять у этого экземпляра. Элемент после этого
     возвращается в исходную точку (Revit мог сдвинуть его к новому уровню).
  2. Иначе — пересоздание: новый экземпляр того же типоразмера с уровнем в
     той же точке/на той же линии, с тем же поворотом/отражением, копия всех
     редактируемых параметров экземпляра (в т.ч. рабочий набор, стадия),
     перенос в те же электрические цепи (как устройство — AddToCircuit, как
     панель — SelectPanel), потом удаление старого. У нового элемента ДРУГОЙ
     ElementId; марки (аннотации) старого элемента удаляются вместе с ним.
     Каждое пересоздание — в своей SubTransaction: если что-то не удалось
     (например, цепь не приняла новый элемент), этот элемент откатывается
     целиком и остаётся как был.

Уровень — либо выбранный пользователем, либо по высоте: ближайший уровень
документа не выше низа элемента (pick_level_by_elevation по
Level.ProjectElevation — та же система координат, что Z точек элементов).

Revit API импортируется лениво (внутри функций), поэтому чистая
pick_level_by_elevation тестируется вне Revit (tests/test_level_assign.py).
"""

import math

# Допуск по высоте, футы (~3 мм): элемент, стоящий ровно на отметке уровня,
# но из-за округления чуть ниже неё, относится к этому уровню, а не к нижнему.
ELEVATION_TOL_FT = 0.01

# Параметры «Уровень» экземпляра, через которые уровень можно назначить без
# пересоздания (если Revit разрешает их менять).
_LEVEL_PARAM_NAMES = ("FAMILY_LEVEL_PARAM", "INSTANCE_REFERENCE_LEVEL_PARAM")

# Не копируются при пересоздании: уровень/смещения задаются заново, тип и
# основа — свойства самого нового экземпляра.
_SKIP_COPY_PARAM_NAMES = (
    "FAMILY_LEVEL_PARAM",
    "INSTANCE_REFERENCE_LEVEL_PARAM",
    "INSTANCE_SCHEDULE_ONLY_LEVEL_PARAM",
    "SCHEDULE_LEVEL_PARAM",
    "INSTANCE_ELEVATION_PARAM",
    "INSTANCE_FREE_HOST_OFFSET_PARAM",
    "FAMILY_BASE_LEVEL_PARAM",
    "FAMILY_BASE_LEVEL_OFFSET_PARAM",
    "FAMILY_TOP_LEVEL_PARAM",
    "FAMILY_TOP_LEVEL_OFFSET_PARAM",
    "ELEM_FAMILY_AND_TYPE_PARAM",
    "ELEM_FAMILY_PARAM",
    "ELEM_TYPE_PARAM",
    "SYMBOL_ID_PARAM",
    "HOST_ID_PARAM",
)

# Способы назначения (AssignResult.how)
HOW_PARAM = "param"
HOW_RECREATED = "recreated"


def pick_level_by_elevation(z, levels_with_elevation, tol=ELEVATION_TOL_FT):
    """
    levels_with_elevation — [(отметка, уровень), ...] в той же системе
    координат, что z. Возвращает уровень с наибольшей отметкой <= z + tol;
    если элемент ниже всех уровней — самый нижний. None — уровней нет.
    """
    if not levels_with_elevation:
        return None

    ordered = sorted(levels_with_elevation, key=lambda pair: pair[0])
    best = ordered[0][1]

    for elevation, level in ordered:
        if elevation <= z + tol:
            best = level
        else:
            break

    return best


# --- разбор выбора ------------------------------------------------------------

SKIP_HAS_LEVEL = u"уже есть опорный уровень"
SKIP_NOT_FAMILY = u"не экземпляр семейства"
SKIP_HOSTED = u"размещён на основе"
SKIP_NESTED = u"вложенное семейство"
SKIP_IN_GROUP = u"в группе"
SKIP_NO_LOCATION = u"нет точки/линии размещения"


def classify(doc, el):
    """
    None — элементу можно и нужно назначать уровень; иначе — причина
    пропуска (одна из SKIP_*).
    """
    from Autodesk.Revit.DB import ElementId, FamilyInstance, LocationPoint, LocationCurve
    from lowlife import geometry

    if not isinstance(el, FamilyInstance):
        return SKIP_NOT_FAMILY

    if geometry.get_element_level(doc, el) is not None:
        return SKIP_HAS_LEVEL

    try:
        if el.SuperComponent is not None:
            return SKIP_NESTED
    except:
        pass

    try:
        if el.Host is not None:
            return SKIP_HOSTED
    except:
        pass

    try:
        if el.GroupId is not None and el.GroupId != ElementId.InvalidElementId:
            return SKIP_IN_GROUP
    except:
        pass

    if not isinstance(el.Location, (LocationPoint, LocationCurve)):
        return SKIP_NO_LOCATION

    return None


def _writable_level_param(el):
    from Autodesk.Revit.DB import BuiltInParameter

    for name in _LEVEL_PARAM_NAMES:
        bip = getattr(BuiltInParameter, name, None)
        if bip is None:
            continue
        try:
            p = el.get_Parameter(bip)
        except:
            p = None
        if p is not None and not p.IsReadOnly:
            return p
    return None


def can_assign_by_param(el):
    """True — уровень, скорее всего, назначится параметром, без пересоздания."""
    return _writable_level_param(el) is not None


# --- уровень по высоте ----------------------------------------------------------

def element_elevation(el):
    """Z элемента в координатах модели: точка вставки, иначе низ линии,
    иначе низ габарита. None — ничего из этого не нашлось."""
    from Autodesk.Revit.DB import LocationPoint, LocationCurve

    try:
        loc = el.Location
        if isinstance(loc, LocationPoint):
            return loc.Point.Z
        if isinstance(loc, LocationCurve):
            curve = loc.Curve
            return min(curve.GetEndPoint(0).Z, curve.GetEndPoint(1).Z)
    except:
        pass

    try:
        bbox = el.get_BoundingBox(None)
        if bbox is not None:
            return bbox.Min.Z
    except:
        pass

    return None


def levels_with_project_elevation(doc):
    """[(Level.ProjectElevation, Level)] — ProjectElevation отсчитывается от
    начала координат модели, как и Z точек элементов (Level.Elevation — от
    базовой точки/точки съёмки и с Z элемента напрямую не сравнима)."""
    from lowlife import geometry

    pairs = []
    for lv in geometry.get_document_levels(doc):
        try:
            pairs.append((lv.ProjectElevation, lv))
        except:
            pass
    return pairs


def level_for_element(el, levels):
    """Уровень по высоте элемента из levels_with_project_elevation()."""
    z = element_elevation(el)
    if z is None:
        return None
    return pick_level_by_elevation(z, levels)


# --- положение ------------------------------------------------------------------

def _anchor(el):
    """Точка, по которой сравнивается положение до/после: точка вставки или
    начало линии."""
    from Autodesk.Revit.DB import LocationPoint, LocationCurve

    loc = el.Location
    if isinstance(loc, LocationPoint):
        return loc.Point
    if isinstance(loc, LocationCurve):
        return loc.Curve.GetEndPoint(0)
    return None


def _move_anchor_to(doc, el, target):
    from Autodesk.Revit.DB import ElementTransformUtils

    current = _anchor(el)
    if current is None or target is None:
        return
    delta = target - current
    if delta.GetLength() > 1e-6:
        ElementTransformUtils.MoveElement(doc, el.Id, delta)


def _horizontal(v):
    from Autodesk.Revit.DB import XYZ

    if v is None:
        return None
    h = XYZ(v.X, v.Y, 0.0)
    if h.GetLength() < 1e-6:
        return None
    return h.Normalize()


def _rotate_to(doc, el, point, want, have):
    """Поворот el вокруг вертикали через point, чтобы горизонтальная
    проекция have совпала с want."""
    from Autodesk.Revit.DB import ElementTransformUtils, Line, XYZ

    want = _horizontal(want)
    have = _horizontal(have)
    if want is None or have is None:
        return
    angle = math.atan2(have.X * want.Y - have.Y * want.X, have.DotProduct(want))
    if abs(angle) < 1e-6:
        return
    axis = Line.CreateBound(point, point + XYZ.BasisZ)
    ElementTransformUtils.RotateElement(doc, el.Id, axis, angle)


def _match_orientation(doc, old, new):
    """Отражение/развороты/поворот нового точечного экземпляра как у старого."""
    from Autodesk.Revit.DB import ElementId, ElementTransformUtils, Plane
    from System.Collections.Generic import List

    point = new.Location.Point

    try:
        if old.Mirrored != new.Mirrored:
            plane = Plane.CreateByNormalAndOrigin(new.HandOrientation, point)
            ids = List[ElementId]()
            ids.Add(new.Id)
            ElementTransformUtils.MirrorElements(doc, ids, plane, False)
            doc.Regenerate()
    except:
        pass

    try:
        if old.FacingFlipped != new.FacingFlipped and new.CanFlipFacing:
            new.flipFacing()
        if old.HandFlipped != new.HandFlipped and new.CanFlipHand:
            new.flipHand()
        doc.Regenerate()
    except:
        pass

    try:
        _rotate_to(doc, new, point, old.FacingOrientation, new.FacingOrientation)
        doc.Regenerate()
    except:
        pass


def _orientation_matches(old, new):
    try:
        for a, b in ((old.FacingOrientation, new.FacingOrientation),
                     (old.HandOrientation, new.HandOrientation)):
            if a.DotProduct(b) < 0.999:
                return False
    except:
        pass
    return True


# --- параметры ------------------------------------------------------------------

def _skip_bips():
    from Autodesk.Revit.DB import BuiltInParameter

    result = set()
    for name in _SKIP_COPY_PARAM_NAMES:
        bip = getattr(BuiltInParameter, name, None)
        if bip is not None:
            result.add(int(bip))
    return result


def _target_param(new, p):
    from Autodesk.Revit.DB import BuiltInParameter, InternalDefinition

    try:
        if p.IsShared:
            return new.get_Parameter(p.GUID)
    except:
        pass

    d = p.Definition
    try:
        if isinstance(d, InternalDefinition) and d.BuiltInParameter != BuiltInParameter.INVALID:
            return new.get_Parameter(d.BuiltInParameter)
    except:
        pass

    try:
        return new.LookupParameter(d.Name)
    except:
        return None


def copy_instance_params(old, new):
    """Копирует все редактируемые параметры экземпляра old в new. Возвращает
    число параметров, которые не удалось записать."""
    from Autodesk.Revit.DB import InternalDefinition, StorageType

    skip = _skip_bips()
    failed = 0

    for p in old.Parameters:
        try:
            if p.IsReadOnly or not p.HasValue:
                continue
            d = p.Definition
            if isinstance(d, InternalDefinition) and int(d.BuiltInParameter) in skip:
                continue

            target = _target_param(new, p)
            if target is None or target.IsReadOnly or target.StorageType != p.StorageType:
                continue

            st = p.StorageType
            if st == StorageType.String:
                value, current = p.AsString(), target.AsString()
            elif st == StorageType.Integer:
                value, current = p.AsInteger(), target.AsInteger()
            elif st == StorageType.Double:
                value, current = p.AsDouble(), target.AsDouble()
            elif st == StorageType.ElementId:
                value, current = p.AsElementId(), target.AsElementId()
            else:
                continue

            if value == current:
                continue
            if value is None:
                value = u""
            if not target.Set(value):
                failed += 1
        except:
            failed += 1

    return failed


# --- электрические цепи -----------------------------------------------------------

def _systems(el):
    """(цепи, где el — устройство; цепи, где el — панель)."""
    mep = getattr(el, "MEPModel", None)
    if mep is None:
        return [], []

    as_device = []
    try:
        as_device = list(mep.GetElectricalSystems() or [])
    except:
        pass

    as_panel = []
    try:
        # Revit 2021+; в старых версиях метода нет.
        as_panel = list(mep.GetAssignedElectricalSystems() or [])
    except:
        pass

    panel_ids = set(s.Id.IntegerValue for s in as_panel)
    as_device = [s for s in as_device if s.Id.IntegerValue not in panel_ids]
    return as_device, as_panel


def _relink_circuits(new, as_device, as_panel):
    """Переносит new в цепи старого элемента. Текст ошибки или None."""
    from Autodesk.Revit.DB import ElementSet

    for system in as_device:
        try:
            members = ElementSet()
            members.Insert(new)
            if system.AddToCircuit(members) is False:
                return u"цепь {} не приняла новый элемент".format(_circuit_name(system))
        except Exception as ex:
            return u"цепь {}: {}".format(_circuit_name(system), ex)

    for system in as_panel:
        try:
            system.SelectPanel(new)
        except Exception as ex:
            return u"цепь {} (панель): {}".format(_circuit_name(system), ex)

    return None


def _circuit_name(system):
    try:
        return u"«{}»".format(system.Name)
    except:
        return u""


# --- создание сразу с уровнем -------------------------------------------------------

def create_on_level(doc, symbol, point, level):
    """
    Новый экземпляр symbol в point с опорным уровнем level — общий хелпер
    для кнопок расстановки, чтобы они не оставляли экземпляры без уровня:
      1. NewFamilyInstance(point, symbol, level, NonStructural) — семейства
         на основе уровня;
      2. если Revit отказал или уровень не прописался (типично — семейство
         на основе рабочей плоскости), — на плоскость уровня
         (Level.GetPlaneReference()), с подъёмом до point (смещение от
         рабочей плоскости).
    Возвращает экземпляр с уровнем или None (ничего не оставляет в модели).
    Вызывать внутри Transaction.
    """
    from Autodesk.Revit.DB import XYZ
    from Autodesk.Revit.DB.Structure import StructuralType
    from lowlife import geometry

    if level is None or symbol is None or point is None:
        return None

    if not symbol.IsActive:
        symbol.Activate()
        doc.Regenerate()

    def _attempts():
        yield lambda: doc.Create.NewFamilyInstance(point, symbol, level, StructuralType.NonStructural)
        yield lambda: doc.Create.NewFamilyInstance(level.GetPlaneReference(), point, XYZ.BasisX, symbol)

    for make in _attempts():
        try:
            inst = make()
        except:
            inst = None
        if inst is None:
            continue
        try:
            doc.Regenerate()
            if geometry.get_element_level(doc, inst) is not None:
                _move_anchor_to(doc, inst, point)
                return inst
            doc.Delete(inst.Id)
        except:
            pass

    return None


def ensure_level(doc, inst, level):
    """
    Если у только что созданного inst нет опорного уровня — пробует
    назначить level параметром «Уровень» (assign_by_param). True — уровень
    есть. Для запасных веток расстановки, где экземпляр пришлось создать
    без уровня (на основе без уровня или вовсе без привязки).
    """
    from lowlife import geometry

    if inst is None:
        return False
    if geometry.get_element_level(doc, inst) is not None:
        return True
    if level is None:
        return False
    return assign_by_param(doc, inst, level)


# --- назначение ------------------------------------------------------------------

def assign_by_param(doc, el, level):
    """
    Назначает уровень параметром «Уровень» и возвращает элемент на место.
    True — получилось. Вызывать внутри Transaction; сама откатывает свою
    SubTransaction при неудаче.
    """
    from Autodesk.Revit.DB import SubTransaction
    from lowlife import geometry

    p = _writable_level_param(el)
    if p is None:
        return False

    anchor = _anchor(el)
    st = SubTransaction(doc)
    st.Start()
    try:
        if not p.Set(level.Id):
            st.RollBack()
            return False
        doc.Regenerate()
        if geometry.get_element_level(doc, el) is None:
            st.RollBack()
            return False
        _move_anchor_to(doc, el, anchor)
        st.Commit()
        return True
    except:
        try:
            st.RollBack()
        except:
            pass
        return False


def recreate_with_level(doc, el, level):
    """
    Пересоздаёт экземпляр с опорным уровнем на том же месте (см. докстринг
    модуля). Возвращает (новый элемент, None, предупреждения) или
    (None, текст ошибки, []). Вызывать внутри Transaction.
    """
    from Autodesk.Revit.DB import LocationPoint, LocationCurve, SubTransaction
    from Autodesk.Revit.DB.Structure import StructuralType
    from lowlife import geometry

    symbol = el.Symbol
    loc = el.Location
    anchor = _anchor(el)
    as_device, as_panel = _systems(el)
    warnings = []

    st = SubTransaction(doc)
    st.Start()
    try:
        if isinstance(loc, LocationPoint):
            new = create_on_level(doc, symbol, loc.Point, level)
        else:
            if not symbol.IsActive:
                symbol.Activate()
                doc.Regenerate()
            new = doc.Create.NewFamilyInstance(loc.Curve, symbol, level, StructuralType.NonStructural)

        if new is None:
            st.RollBack()
            return None, u"Revit не создал экземпляр с уровнем", []
        doc.Regenerate()

        if geometry.get_element_level(doc, new) is None:
            st.RollBack()
            return None, u"семейство не принимает опорный уровень (иной способ размещения)", []

        if isinstance(new.Location, LocationPoint):
            _match_orientation(doc, el, new)
            _move_anchor_to(doc, new, anchor)
        elif isinstance(new.Location, LocationCurve):
            _move_curve_to(new, loc.Curve)
        doc.Regenerate()

        if isinstance(new.Location, LocationPoint) and not _orientation_matches(el, new):
            warnings.append(u"ориентация может отличаться от исходной")

        failed_params = copy_instance_params(el, new)
        if failed_params:
            warnings.append(u"не скопировано параметров: {}".format(failed_params))

        error = _relink_circuits(new, as_device, as_panel)
        if error:
            st.RollBack()
            return None, error, []

        doc.Delete(el.Id)
        st.Commit()
        return new, None, warnings
    except Exception as ex:
        try:
            st.RollBack()
        except:
            pass
        return None, unicode(ex), []


def _move_curve_to(el, curve):
    """Линейный экземпляр — на исходную линию (если Revit спроецировал её
    на уровень или задал смещение по-своему)."""
    try:
        el.Location.Curve = curve
    except:
        pass


class AssignResult(object):
    def __init__(self):
        self.by_param = []      # элементы, уровень назначен параметром
        self.recreated = []     # (старый id int, новый элемент)
        self.levels = {}        # имя уровня -> сколько назначено
        self.failed = []        # (element id int, причина)
        self.warnings = []      # (новый element id int, текст)

    def resulting_ids(self):
        ids = [el.Id for el in self.by_param]
        ids.extend(new.Id for _old, new in self.recreated)
        return ids


def assign_levels(doc, elements, fixed_level=None, allow_recreate=True):
    """
    elements — уже отобранные classify() == None. fixed_level — уровень для
    всех, иначе по высоте каждого элемента. allow_recreate=False — только
    параметром, без пересоздания. Вызывать внутри Transaction.
    """
    from lowlife import geometry

    result = AssignResult()
    levels = levels_with_project_elevation(doc)

    for el in elements:
        el_id = el.Id.IntegerValue
        level = fixed_level or level_for_element(el, levels)
        if level is None:
            result.failed.append((el_id, u"не удалось определить уровень по высоте"))
            continue

        name = geometry.level_name(level)

        if assign_by_param(doc, el, level):
            result.by_param.append(el)
            result.levels[name] = result.levels.get(name, 0) + 1
            continue

        if not allow_recreate:
            result.failed.append((el_id, u"уровень меняется только пересозданием (отключено)"))
            continue

        new, error, warnings = recreate_with_level(doc, el, level)
        if new is None:
            result.failed.append((el_id, error or u"не удалось пересоздать"))
            continue

        result.recreated.append((el_id, new))
        result.levels[name] = result.levels.get(name, 0) + 1
        for w in warnings:
            result.warnings.append((new.Id.IntegerValue, w))

    return result
