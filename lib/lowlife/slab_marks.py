# -*- coding: utf-8 -*-
"""
Кнопка «Извещатели на перекрытие» (SPS.panel/DetectorsToSlab). Revit-часть;
чистая логика — slab_marks_core.py, настройки — slab_marks_settings.py.

Что делает:
  1. move_detectors — каждый пожарный извещатель (категория «Пожарная
     сигнализация», отбор по словам в имени семейства/типа) поднимается или
     опускается так, чтобы точка вставки встала на низ перекрытия над ним.
     Перекрытие ищется лучом вверх (ReferenceIntersector по временному
     3D-виду, с элементами связей АР/КР) из точки над уровнем извещателя —
     поэтому разные отметки перекрытий в здании учитываются сами.
  2. annotate_view — на плане для каждого помещения (связей и модели) на
     уровне вида — подпись высоты низа перекрытия от пола (пол — ближайшее
     перекрытие под точкой), «Δ» — на сколько перекрытие выше/ниже типового
     для этого вида, а в помещениях с подвесным потолком — область заливки
     по контуру помещения и подпись «ПП» с высотой потолка от пола.
     Перепады плиты — толстые красные линии детализации (draw_steps) там,
     где сходятся края нижних граней перекрытий с разной отметкой.
     Повторный запуск заменяет подписи, области и линии прошлого запуска на виде.

Вызывать внутри одной открытой транзакции (временный 3D-вид создаётся и
удаляется в ней же — SlabProbe.close()).
"""

from Autodesk.Revit.DB import (
    XYZ, Line, CurveLoop, ElementId, FilteredElementCollector, BuiltInCategory,
    BuiltInParameter, FamilyInstance, LocationPoint, Level, ViewPlan, TextNote, TextNoteType,
    FilledRegion, FilledRegionType, ElementTypeGroup, ElementTransformUtils,
    SpatialElementBoundaryOptions, CurveElement, GraphicsStyleType, Color, Options,
    ViewDetailLevel, Solid, GeometryInstance, PlanarFace, RevitLinkInstance, Transform
)

from lowlife import slab_marks_core as core
from lowlife.scs import safe_element_name
from lowlife.soue_floor import room_sources, room_name

FT_TO_MM = 304.8

# Тип текста подписей (создаётся копией типа текста по умолчанию). По нему
# повторный запуск находит и удаляет подписи прошлого запуска на виде.
TEXT_TYPE_NAME = u"LowLife — отметки перекрытий"

# Метка в «Комментариях» областей заливки подвесного потолка.
REGION_TAG = u"LowLife ПП"

# Стиль линий перепада плиты (подкатегория «Линии», красная, толстая). По нему
# повторный запуск находит и удаляет линии прошлого запуска на виде.
STEP_LINE_STYLE = u"LowLife — перепад плиты"
STEP_LINE_COLOR = (255, 0, 0)

# Перепад плиты: отметки, различающиеся меньше, — одна плита; края короче — не линия.
STEP_MIN_DZ_MM = 20.0
STEP_MIN_LEN_MM = 100.0

# Расхождение после перемещения, при котором извещатель считается не сдвинутым.
MOVE_TOLERANCE_MM = 5.0

# Перекрытие тоньше — отделка пола, а не плита (SlabProbe._is_thin).
THIN_FLOOR_MM = 150.0

# Отрезки контура помещения короче этого не строятся (меньше допуска Revit).
_MIN_SEG_FT = 0.01


def mm(value_ft):
    return value_ft * FT_TO_MM


def ft(value_mm):
    return float(value_mm) / FT_TO_MM


# ------------------------------------------------------------
# Луч вверх/вниз
# ------------------------------------------------------------

class SlabProbe(object):
    """
    Лучи вверх и вниз из точки (ReferenceIntersector по временному 3D-виду,
    с элементами связей): перекрытия («Перекрытия», «Крыши») и подвесные
    потолки («Потолки»). Вид создаётся при первом запросе; close() удаляет
    его в той же транзакции.

    Скорость: на виде скрыты все категории модели, кроме перекрытий, крыш,
    потолков и связей, — луч иначе собирает попадания во всё подряд
    (мебель, трубы, воздуховоды, оборудование во всех связях), и на сотнях
    точек это основное время. Результаты кэшируются по точке (повторные
    запросы той же точки — подпись помещения, проверка перепада).

    Колонны для луча скрыты: луч вниз из точки над колонной упирался в низ
    колонны (ниже чистого пола), и высота получалась завышенной. Если
    ближайшим сверху оказался тонкий слой (отделка пола над полостью, а
    не плита), точка проверяется как отверстие (_check_opening).
    """

    _VISIBLE = (
        BuiltInCategory.OST_Floors, BuiltInCategory.OST_Roofs,
        BuiltInCategory.OST_Ceilings, BuiltInCategory.OST_RvtLinks,
    )

    _KINDS = {
        int(BuiltInCategory.OST_Floors): core.SLAB,
        int(BuiltInCategory.OST_Roofs): core.SLAB,
        int(BuiltInCategory.OST_Ceilings): core.CEILING,
    }

    def __init__(self, doc, opening_size_mm=0.0):
        self.doc = doc
        # Отверстия в перекрытии (шахты, проёмы): луч проходит насквозь до
        # плиты следующих этажей. Если найденная плита выше следующего уровня,
        # проверяются 4 точки на этом расстоянии вокруг (см. _check_opening).
        # 0 — не проверять.
        self.opening_ft = ft(opening_size_mm or 0.0)
        self._levels = None
        self.view = None
        self.intersector = None
        self.error = None
        self._cache = {}
        # Перекрытия, в которые лучи упёрлись как в ближайшие сверху, по
        # уровню, от которого шёл луч: {отметка уровня, мм: {(Id связи или -1
        # для модели, Id элемента)}} — по ним ищутся перепады (slabs_above).
        self.slab_elements = {}
        self.openings = 0  # точек над отверстиями в перекрытии (для отчёта)
        self._sources = None
        self._thin = {}    # {ключ элемента: тонкий ли (отделка пола)}
        self._solids_cache = {}  # {ключ элемента: [Solid]} — для _refine_nearest_slab

    def _hide_other_categories(self):
        from Autodesk.Revit.DB import CategoryType
        keep = set(int(c) for c in self._VISIBLE)
        for category in self.doc.Settings.Categories:
            try:
                if category.CategoryType != CategoryType.Model:
                    continue
                if category.Id.IntegerValue in keep:
                    continue
                if self.view.CanCategoryBeHidden(category.Id):
                    self.view.SetCategoryHidden(category.Id, True)
            except Exception:
                pass

    def _open(self):
        from Autodesk.Revit.DB import (
            View3D, ViewFamilyType, ViewFamily, ReferenceIntersector, FindReferenceTarget
        )
        vft = None
        for candidate in FilteredElementCollector(self.doc).OfClass(ViewFamilyType):
            if candidate.ViewFamily == ViewFamily.ThreeDimensional:
                vft = candidate
                break
        if vft is None:
            raise Exception(u"в проекте нет типа 3D-вида")
        self.view = View3D.CreateIsometric(self.doc, vft.Id)
        try:
            self.view.ViewTemplateId = ElementId.InvalidElementId
        except Exception:
            pass
        self._hide_other_categories()
        self.doc.Regenerate()
        self.intersector = ReferenceIntersector(self.view)
        self.intersector.TargetType = FindReferenceTarget.Face
        self.intersector.FindReferencesInRevitLinks = True

    def _kind(self, reference):
        """(вид попадания или None, ключ элемента (Id связи или -1, Id элемента))."""
        element = self.doc.GetElement(reference.ElementId)
        key = (-1, reference.ElementId.IntegerValue)
        if reference.LinkedElementId != ElementId.InvalidElementId:
            key = (reference.ElementId.IntegerValue, reference.LinkedElementId.IntegerValue)
            try:
                element = element.GetLinkDocument().GetElement(reference.LinkedElementId)
            except Exception:
                return None, key
        try:
            return self._KINDS.get(element.Category.Id.IntegerValue), key
        except Exception:
            return None, key

    def _hits(self, origin, direction):
        """[(расстояние мм, вид, ключ элемента)]."""
        hits = []
        for context in self.intersector.Find(origin, direction):
            kind, key = self._kind(context.GetReference())
            if kind is not None:
                hits.append((mm(context.Proximity), kind, key))
        return hits

    def describe(self, x, y, origin_z, level_z, limit=8):
        """
        Диагностика для отчёта: во что упираются лучи из точки — строки
        «вверх/вниз: расстояние, отметка от уровня, категория, тип, связь» (до
        limit на направление) и итог probe(). Только для выбранных извещателей.
        """
        lines = []
        if self.intersector is None:
            self._open()
        origin = XYZ(x, y, origin_z)
        for label, direction, sign in ((u"вверх", XYZ.BasisZ, 1), (u"вниз", XYZ.BasisZ.Negate(), -1)):
            contexts = sorted(self.intersector.Find(origin, direction), key=lambda c: c.Proximity)
            for context in contexts[:limit]:
                reference = context.GetReference()
                element = self.doc.GetElement(reference.ElementId)
                link = u"модель"
                if reference.LinkedElementId != ElementId.InvalidElementId:
                    link = safe_element_name(element) or u"связь"
                    try:
                        element = element.GetLinkDocument().GetElement(reference.LinkedElementId)
                    except Exception:
                        element = None
                try:
                    category = element.Category.Name
                    type_name = safe_element_name(element.Document.GetElement(element.GetTypeId())) or u""
                    element_id = element.Id.IntegerValue
                except Exception:
                    category, type_name, element_id = u"?", u"", 0
                distance = mm(context.Proximity)
                lines.append(u"{} {:.0f} мм (от уровня {:+.0f}): {} «{}» Id {} — {}".format(
                    label, float(distance), float(mm(origin_z - level_z) + sign * distance),
                    category, type_name, element_id, link))
        found = self.probe(x, y, origin_z, level_z)
        if found is None:
            lines.append(u"итог: перекрытие не найдено")
        else:
            lines.append(u"итог: низ перекрытия {} от пола, пол {:+.0f} мм от уровня{}{}".format(
                core.format_height(found.slab_mm), float(found.floor_z_mm - mm(level_z)),
                u", ПП {}".format(core.format_height(found.ceiling_mm)) if found.ceiling_mm is not None else u"",
                u", над отверстием — по плите вокруг" if found.through_opening else u""))
        return lines

    def _remember_slab(self, up_hits, level_z):
        key = self._nearest_slab_key(up_hits)
        if key is not None:
            self.slab_elements.setdefault(int(round(mm(level_z))), set()).add(key)

    def slabs_above(self, level_z, tolerance):
        """Перекрытия, найденные лучами от уровней не дальше tolerance (футы) от level_z."""
        result = set()
        for level_mm, keys in self.slab_elements.items():
            if abs(ft(level_mm) - level_z) <= tolerance + ft(1.0):
                result.update(keys)
        return result

    def _is_thin(self, key):
        """Перекрытие тоньше THIN_FLOOR_MM — отделка пола, а не плита (кэш по элементу)."""
        if key in self._thin:
            return self._thin[key]
        thin = False
        try:
            if self._sources is None:
                self._sources = model_sources(self.doc)
            source_doc, _transform = self._sources[key[0]]
            element = source_doc.GetElement(ElementId(key[1]))
            if element.Category.Id.IntegerValue == int(BuiltInCategory.OST_Floors):
                param = element.get_Parameter(BuiltInParameter.FLOOR_ATTR_THICKNESS_PARAM)
                if param is not None and param.HasValue:
                    thickness = param.AsDouble()
                else:
                    bbox = element.get_BoundingBox(None)
                    thickness = bbox.Max.Z - bbox.Min.Z
                thin = 0 < mm(thickness) < THIN_FLOOR_MM
        except Exception:
            thin = False
        self._thin[key] = thin
        return thin

    @staticmethod
    def _nearest_slab_key(up_hits):
        best = None
        for distance, kind, key in up_hits:
            if kind == core.SLAB and distance > 0 and (best is None or distance < best[0]):
                best = (distance, key)
        return None if best is None else best[1]

    def _raw(self, x, y, origin_z, level_z):
        """(core.Probe или None, лучи вверх) без проверки отверстия; кэшируется."""
        key = (round(x, 3), round(y, 3), round(origin_z, 3), round(level_z, 3))
        if key in self._cache:
            return self._cache[key]
        if self.intersector is None:
            self._open()
        origin = XYZ(x, y, origin_z)
        up = self._refine_nearest_slab(self._hits(origin, XYZ.BasisZ), x, y, origin_z)
        down = self._hits(origin, XYZ.BasisZ.Negate())
        found = core.probe(mm(origin_z), [h[:2] for h in up], [h[:2] for h in down], mm(level_z))
        self._cache[key] = (found, up)
        return found, up

    def _element_solids(self, key):
        """Тела элемента в координатах модели (кэш по элементу); [] — не удалось."""
        if key in self._solids_cache:
            return self._solids_cache[key]
        from Autodesk.Revit.DB import SolidUtils
        solids = []
        try:
            if self._sources is None:
                self._sources = model_sources(self.doc)
            source_doc, transform = self._sources[key[0]]
            element = source_doc.GetElement(ElementId(key[1]))
            options = Options()
            options.DetailLevel = ViewDetailLevel.Fine
            for solid, solid_transform in _solids(element.get_Geometry(options), transform):
                if solid_transform.IsIdentity:
                    solids.append(solid)
                else:
                    solids.append(SolidUtils.CreateTransformed(solid, solid_transform))
        except Exception:
            solids = []
        self._solids_cache[key] = solids
        return solids

    def _refine_nearest_slab(self, up, x, y, origin_z):
        """
        Низ ближайшего перекрытия — по геометрии самого элемента, а не по
        грани, которую вернул луч. У капителей (перекрытие, присоединённое к
        плите) ReferenceIntersector бывает отдаёт только верхнюю грань —
        отметка получалась по верху капители. Вертикаль от точки до
        попадания пересекается с телом элемента: где она входит в тело
        снизу — там низ. Не получилось — попадание как есть.
        """
        best = None
        for index, (distance, kind, key) in enumerate(up):
            if kind == core.SLAB and distance > 0 and (best is None or distance < up[best][0]):
                best = index
        if best is None:
            return up
        distance, kind, key = up[best]
        try:
            from Autodesk.Revit.DB import SolidCurveIntersectionOptions
            top = origin_z + ft(distance + 10.0)
            line = Line.CreateBound(XYZ(x, y, origin_z), XYZ(x, y, top))
            lowest = None
            for solid in self._element_solids(key):
                result = solid.IntersectWithCurve(line, SolidCurveIntersectionOptions())
                for i in range(result.SegmentCount):
                    segment = result.GetCurveSegment(i)
                    z = min(segment.GetEndPoint(0).Z, segment.GetEndPoint(1).Z)
                    if lowest is None or z < lowest:
                        lowest = z
        except Exception:
            return up
        if lowest is None:
            return up
        refined = mm(lowest - origin_z)
        # точка внутри тела (колонна) или уточнять нечего — попадание как есть
        if refined <= 50.0 or refined >= distance - 1.0:
            return up
        up = list(up)
        up[best] = (refined, kind, key)
        return up

    def _next_level_z(self, level_z):
        if self._levels is None:
            self._levels = [z for _level, z in plan_levels(self.doc)]
        for z in self._levels:
            if z > level_z + ft(1000.0):
                return z
        return None

    def _check_opening(self, found, up, x, y, origin_z, level_z):
        """
        Над точкой отверстие (шахта, проём, полость в плите)? Проверяется,
        только если найденная плита выше следующего уровня (луч мог пройти
        сквозь перекрытие этого этажа) или это тонкий слой — отделка пола
        над полостью. Тогда 4 точки вокруг на opening_ft: если везде плита
        ниже — отверстие, возвращается Probe с плитой вокруг него; иначе
        None (высокая зона).
        """
        if self.opening_ft <= 0 or found is None:
            return None
        next_z = self._next_level_z(level_z)
        above_next = next_z is not None and found.slab_z_mm > mm(next_z)
        if not above_next:
            key = self._nearest_slab_key(up)
            if key is None or not self._is_thin(key):
                return None
        d = self.opening_ft
        around = []
        for dx, dy in ((d, 0), (-d, 0), (0, d), (0, -d)):
            neighbor, _up = self._raw(x + dx, y + dy, origin_z, level_z)
            around.append(None if neighbor is None else neighbor.slab_z_mm)
        slab_z = core.opening_slab_z(found.slab_z_mm, around)
        return None if slab_z is None else core.replace_slab(found, slab_z)

    def probe(self, x, y, origin_z, level_z):
        """
        core.Probe для точки (x, y) с началом лучей на высоте origin_z (футы)
        или None. Над отверстием — перекрытие вокруг отверстия
        (through_opening=True), плита сверху в поиск перепадов не идёт.
        """
        if self.error is not None:
            return None
        try:
            found, up = self._raw(x, y, origin_z, level_z)
            opening = self._check_opening(found, up, x, y, origin_z, level_z)
        except Exception as ex:
            self.error = ex
            return None
        if opening is not None:
            self.openings += 1
            return opening
        self._remember_slab(up, level_z)
        return found

    def close(self):
        if self.view is not None:
            try:
                self.doc.Delete(self.view.Id)
            except Exception:
                pass
            self.view = None


# ------------------------------------------------------------
# Извещатели
# ------------------------------------------------------------

def _names(instance):
    names = []
    try:
        symbol = instance.Symbol
        names.append(safe_element_name(symbol.Family) or u"")
        names.append(safe_element_name(symbol) or u"")
    except Exception:
        pass
    return names


def _point(instance):
    try:
        location = instance.Location
        if isinstance(location, LocationPoint):
            return location.Point
    except Exception:
        pass
    return None


def plan_levels(doc):
    """Уровни модели по высоте: [(уровень, ProjectElevation в футах)]."""
    levels = [(level, level.ProjectElevation)
              for level in FilteredElementCollector(doc).OfClass(Level)]
    return sorted(levels, key=lambda item: item[1])


def level_of(doc, instance, levels):
    """(уровень, отметка) извещателя: его LevelId, иначе ближайший уровень снизу."""
    try:
        level = doc.GetElement(instance.LevelId)
    except Exception:
        level = None
    if isinstance(level, Level):
        return level, level.ProjectElevation
    point = _point(instance)
    if point is None or not levels:
        return None, None
    best = levels[0]
    for item in levels:
        if item[1] <= point.Z + 1e-6:
            best = item
    return best


def collect_detectors(doc, settings, element_ids=None, view=None):
    """
    Извещатели, подходящие по словам из настроек: из element_ids (выделение),
    иначе видимые на виде view, иначе все в модели.
    """
    include = core.split_words(settings.get("detector_include_words"))
    exclude = core.split_words(settings.get("detector_exclude_words"))
    if element_ids:
        candidates = [doc.GetElement(element_id) for element_id in element_ids]
    elif view is not None:
        candidates = (FilteredElementCollector(doc, view.Id)
                      .OfCategory(BuiltInCategory.OST_FireAlarmDevices)
                      .WhereElementIsNotElementType())
    else:
        candidates = (FilteredElementCollector(doc)
                      .OfCategory(BuiltInCategory.OST_FireAlarmDevices)
                      .WhereElementIsNotElementType())
    result = []
    for element in candidates:
        if not isinstance(element, FamilyInstance) or _point(element) is None:
            continue
        try:
            if element.Category.Id.IntegerValue != int(BuiltInCategory.OST_FireAlarmDevices):
                continue
        except Exception:
            continue
        if core.is_detector(_names(element), include, exclude):
            result.append(element)
    return result


def pick_detectors(uidoc, doc, settings):
    """
    Выбрать извещатели на модели (рамкой или по одному, «Готово» на панели
    параметров): к выбору допускаются только подходящие по словам из
    настроек. Esc — None; выбранное становится выделением Revit.
    """
    from Autodesk.Revit.UI.Selection import ISelectionFilter, ObjectType
    from Autodesk.Revit.Exceptions import OperationCanceledException
    from System.Collections.Generic import List

    allowed = set(d.Id.IntegerValue for d in collect_detectors(doc, settings))

    class _DetectorFilter(ISelectionFilter):
        def AllowElement(self, element):
            try:
                return element.Id.IntegerValue in allowed
            except Exception:
                return False

        def AllowReference(self, reference, position):
            return False

    try:
        references = uidoc.Selection.PickObjects(
            ObjectType.Element, _DetectorFilter(),
            u"Выберите извещатели (рамкой или по одному), затем «Готово»")
    except OperationCanceledException:
        return None
    ids = [reference.ElementId for reference in references]
    try:
        uidoc.Selection.SetElementIds(List[ElementId](ids))
    except Exception:
        pass
    return collect_detectors(doc, settings, ids) if ids else []


def detectors_on_levels(doc, settings, views):
    """Извещатели, чей уровень (level_of) — уровень одного из планов views."""
    level_ids = set(view.GenLevel.Id.IntegerValue for view in views if is_plan(view))
    levels = plan_levels(doc)
    result = []
    for detector in collect_detectors(doc, settings):
        level, _z = level_of(doc, detector, levels)
        if level is not None and level.Id.IntegerValue in level_ids:
            result.append(detector)
    return result


def can_collect_on(view):
    """На виде можно собрать видимые элементы: не шаблон, не спецификация/лист."""
    from Autodesk.Revit.DB import ViewSchedule, ViewSheet
    try:
        return view is not None and not view.IsTemplate and \
            not isinstance(view, (ViewSchedule, ViewSheet))
    except Exception:
        return False


class MoveResult(object):
    def __init__(self):
        self.moved = 0
        self.already = 0
        self.no_slab = []      # извещатели без перекрытия над ними
        self.failed = []       # (извещатель, причина)
        self.under_ceiling = 0  # извещателей над подвесным потолком (для отчёта)
        self.to_ceiling = 0     # встраиваемых, поставленных на подвесной потолок


def _writable(param):
    return param is not None and not param.IsReadOnly


def _shift(doc, instance, delta_ft):
    """Сдвиг точки вставки по Z: параметром смещения, иначе переносом. Ошибка — текст."""
    host = None
    try:
        host = instance.Host
    except Exception:
        pass
    face_hosted = False
    try:
        face_hosted = instance.HostFace is not None
    except Exception:
        pass
    if not face_hosted:
        for bip in (BuiltInParameter.INSTANCE_ELEVATION_PARAM,
                    BuiltInParameter.INSTANCE_FREE_HOST_OFFSET_PARAM):
            param = instance.get_Parameter(bip)
            if _writable(param):
                try:
                    param.Set(param.AsDouble() + delta_ft)
                    return None
                except Exception:
                    pass
    try:
        ElementTransformUtils.MoveElement(doc, instance.Id, XYZ(0, 0, delta_ft))
        return None
    except Exception as ex:
        if face_hosted or host is not None:
            return u"размещён на грани/основе — сдвинуть по высоте нельзя ({})".format(ex)
        return u"{}".format(ex)


def move_detectors(doc, detectors, settings, probe, progress=None):
    """
    Поднять/опустить извещатели на низ перекрытия над ними; встраиваемые
    (слово из ceiling_mount_words в имени семейства/типа) — на низ
    подвесного потолка. Возвращает MoveResult.
    """
    result = MoveResult()
    levels = plan_levels(doc)
    probe_ft = ft(settings.get("probe_height_mm") or 1500.0)
    offset_mm = settings.get("mount_offset_mm") or 0.0
    ceiling_words = core.split_words(settings.get("ceiling_mount_words"))
    shifts = []    # (извещатель, сдвиг мм, отметка до сдвига мм)
    targets = []
    for index, detector in enumerate(detectors):
        if progress is not None:
            progress(index, len(detectors))
        point = _point(detector)
        _level, level_z = level_of(doc, detector, levels)
        if level_z is None:
            result.failed.append((detector, u"не определён уровень"))
            continue
        found = probe.probe(point.X, point.Y, level_z + probe_ft, level_z)
        if found is None:
            result.no_slab.append(detector)
            continue
        ceiling_mount = bool(ceiling_words) and core.is_detector(_names(detector), ceiling_words, [])
        surface_mm, skip = core.mount_surface(found, ceiling_mount)
        if skip:
            result.failed.append((detector, skip))
            continue
        if ceiling_mount:
            result.to_ceiling += 1
        elif found.ceiling_mm is not None:
            result.under_ceiling += 1
        # встраиваемый — точка вставки ровно в плоскости потолка, без отступа
        delta_mm = core.move_delta(mm(point.Z), surface_mm, 0.0 if ceiling_mount else offset_mm)
        if abs(delta_mm) < MOVE_TOLERANCE_MM:
            result.already += 1
            continue
        shifts.append((detector, delta_mm, mm(point.Z)))
    if probe.error is not None:
        result.failed.append((None, u"луч к перекрытию: {}".format(probe.error)))
    # Сдвиги — только после всех лучей: любое изменение модели заставляет
    # Revit пересобрать временный 3D-вид (со всеми связями) перед следующим
    # лучом, и чередование «луч — сдвиг» на сотнях извещателей — это минуты.
    for detector, delta_mm, z_mm in shifts:
        error = _shift(doc, detector, ft(delta_mm))
        if error:
            result.failed.append((detector, error))
        else:
            targets.append((detector, z_mm + delta_mm))
    if targets:
        doc.Regenerate()
    for detector, target_mm in targets:
        point = _point(detector)
        if point is not None and abs(mm(point.Z) - target_mm) < MOVE_TOLERANCE_MM:
            result.moved += 1
        else:
            result.failed.append((detector, u"Revit не сдвинул элемент по высоте (размещён на грани?)"))
    return result


# ------------------------------------------------------------
# Подписи на плане
# ------------------------------------------------------------

def is_plan(view):
    try:
        return (isinstance(view, ViewPlan) and not view.IsTemplate
                and view.GenLevel is not None)
    except Exception:
        return False


def text_type(doc, name=TEXT_TYPE_NAME):
    """Тип текста подписей (по умолчанию TEXT_TYPE_NAME), создаётся копией типа по умолчанию."""
    for candidate in FilteredElementCollector(doc).OfClass(TextNoteType):
        if safe_element_name(candidate) == name:
            return candidate
    base = doc.GetElement(doc.GetDefaultElementTypeId(ElementTypeGroup.TextNoteType))
    if base is None:
        base = FilteredElementCollector(doc).OfClass(TextNoteType).FirstElement()
    return base.Duplicate(name)


def region_type(doc, name):
    """Тип области заливки по имени, иначе первый немаскирующий; None — нет ни одного."""
    types = list(FilteredElementCollector(doc).OfClass(FilledRegionType))
    name = (name or u"").strip()
    if name:
        for candidate in types:
            if safe_element_name(candidate) == name:
                return candidate
    for candidate in types:
        try:
            if not candidate.IsMasking:
                return candidate
        except Exception:
            return candidate
    return types[0] if types else None


def _comment(element):
    try:
        param = element.get_Parameter(BuiltInParameter.ALL_MODEL_INSTANCE_COMMENTS)
        return param.AsString() if param is not None else None
    except Exception:
        return None


def step_line_style(doc, weight):
    """GraphicsStyle линий перепада (STEP_LINE_STYLE) — см. line_style."""
    return line_style(doc, STEP_LINE_STYLE, STEP_LINE_COLOR, weight)


def line_style(doc, name, color, weight):
    """GraphicsStyle стиля линий name (подкатегория «Линии»): создаётся при
    отсутствии, цвет (r, g, b) и толщина выставляются на каждом запуске.
    None — не удалось."""
    try:
        categories = doc.Settings.Categories
        lines = categories.get_Item(BuiltInCategory.OST_Lines)
        sub = None
        for candidate in lines.SubCategories:
            if candidate.Name == name:
                sub = candidate
                break
        if sub is None:
            sub = categories.NewSubcategory(lines, name)
        try:
            sub.LineColor = Color(*color)
            sub.SetLineWeight(int(weight), GraphicsStyleType.Projection)
        except Exception:
            pass
        return sub.GetGraphicsStyle(GraphicsStyleType.Projection)
    except Exception:
        return None


def _line_style_name(curve_element):
    try:
        style = curve_element.LineStyle
        return safe_element_name(style) if style is not None else None
    except Exception:
        return None


def clear_view(doc, view, note_type):
    """Удалить с вида подписи, области заливки и линии перепада прошлого запуска."""
    from System.Collections.Generic import List
    ids = List[ElementId]()
    for note in FilteredElementCollector(doc, view.Id).OfClass(TextNote):
        if note.GetTypeId() == note_type.Id:
            ids.Add(note.Id)
    for curve in FilteredElementCollector(doc, view.Id).OfClass(CurveElement):
        if _line_style_name(curve) == STEP_LINE_STYLE:
            ids.Add(curve.Id)
    for region in FilteredElementCollector(doc, view.Id).OfClass(FilledRegion):
        comment = _comment(region) or u""
        if comment.startswith(REGION_TAG) or comment.startswith(SLAB_REGION_TAG):
            ids.Add(region.Id)
    if ids.Count:
        doc.Delete(ids)
    return ids.Count


class RoomMark(object):
    """Помещение на виде: точки проверки и их Probe, контур, место подписи."""

    def __init__(self, source, room, name):
        self.source = source
        self.room = room
        self.name = name
        self.probes = []
        self.anchor = None

    def slab_values(self):
        return [p.slab_mm for p in self.probes]

    def ceiling_values(self):
        return [p.ceiling_mm for p in self.probes]


def _room_level_z(source, room):
    """Отметка уровня помещения в координатах модели (футы) или None."""
    try:
        level = source.doc.GetElement(room.LevelId)
        z = level.ProjectElevation
    except Exception:
        return None
    return source.transform.OfPoint(XYZ(0, 0, z)).Z


def _room_points(room, level_z_link, probe_ft, max_grid=3, max_points=None):
    """
    Точки внутри помещения (координаты его документа): точка помещения +
    сетка до max_grid×max_grid; не больше max_points (точка помещения — первой).
    """
    test_z = level_z_link + min(probe_ft, ft(1000.0))
    points = []
    try:
        location = room.Location.Point
        if room.IsPointInRoom(XYZ(location.X, location.Y, test_z)):
            points.append(XYZ(location.X, location.Y, test_z))
    except Exception:
        pass
    bbox = room.get_BoundingBox(None)
    if bbox is None:
        return points
    nx = core.grid_steps(mm(bbox.Max.X - bbox.Min.X), max_grid)
    ny = core.grid_steps(mm(bbox.Max.Y - bbox.Min.Y), max_grid)
    for i in range(nx):
        for j in range(ny):
            x = bbox.Min.X + (bbox.Max.X - bbox.Min.X) * (i + 0.5) / nx
            y = bbox.Min.Y + (bbox.Max.Y - bbox.Min.Y) * (j + 0.5) / ny
            point = XYZ(x, y, test_z)
            try:
                if room.IsPointInRoom(point):
                    points.append(point)
            except Exception:
                pass
    return points if max_points is None else points[:max_points]


def _boundary_loops(room, transform, z):
    """CurveLoop'ы контура помещения в координатах модели на высоте z."""
    loops = []
    try:
        segments_loops = room.GetBoundarySegments(SpatialElementBoundaryOptions())
    except Exception:
        segments_loops = None
    for segments in segments_loops or []:
        points = []
        for segment in segments:
            try:
                tessellated = list(segment.GetCurve().Tessellate())
            except Exception:
                continue
            for p in tessellated:
                p = transform.OfPoint(p)
                p = XYZ(p.X, p.Y, z)
                if not points or points[-1].DistanceTo(p) > _MIN_SEG_FT:
                    points.append(p)
        if len(points) >= 2 and points[0].DistanceTo(points[-1]) <= _MIN_SEG_FT:
            points.pop()
        if len(points) < 3:
            continue
        loop = CurveLoop()
        try:
            for i in range(len(points)):
                loop.Append(Line.CreateBound(points[i], points[(i + 1) % len(points)]))
        except Exception:
            continue
        loops.append(loop)
    return loops


def _filled_region(doc, view, region_type_id, room, transform, z):
    from System.Collections.Generic import List
    last_error = None
    for plane_z in (z, 0.0):
        loops = _boundary_loops(room, transform, plane_z)
        if not loops:
            return None, u"нет контура помещения"
        try:
            return FilledRegion.Create(doc, region_type_id, view.Id, List[CurveLoop](loops)), None
        except Exception as ex:
            last_error = ex
    return None, u"{}".format(last_error)


# ------------------------------------------------------------
# Перепады плиты
# ------------------------------------------------------------

def model_sources(doc):
    """{Id связи или -1: (документ, преобразование в координаты модели)}."""
    sources = {-1: (doc, Transform.Identity)}
    for link in FilteredElementCollector(doc).OfClass(RevitLinkInstance):
        try:
            link_doc = link.GetLinkDocument()
        except Exception:
            link_doc = None
        if link_doc is not None:
            sources[link.Id.IntegerValue] = (link_doc, link.GetTotalTransform())
    return sources


def _solids(geometry, transform):
    """(Solid, преобразование в координаты модели) из геометрии элемента."""
    for item in geometry or []:
        if isinstance(item, Solid):
            if item.Faces.Size:
                yield item, transform
        elif isinstance(item, GeometryInstance):
            for nested in _solids(item.GetSymbolGeometry(),
                                  transform.Multiply(item.Transform)):
                yield nested


def _is_column(element):
    try:
        return element.Category.Id.IntegerValue == int(BuiltInCategory.OST_StructuralColumns)
    except Exception:
        return False


def slab_bottom_edges(doc, element_keys, bottom_z):
    """
    Края нижних горизонтальных граней перекрытий из element_keys
    ({(Id связи или -1, Id элемента)} — SlabProbe.slabs_above: только те
    плиты, в которые лучи с этого уровня упёрлись как в ближайшее перекрытие
    сверху), выше bottom_z (футы, координаты модели): [(x1, y1, x2, y2, z)]
    в мм. Все перекрытия связей не перебираются — иначе в кандидаты попадают
    отделка полов, плиты следующего этажа, пандусы, и поиск перепадов на
    большой модели длится часами. Верхней границы нет: плиты уже отобраны
    лучами, а высокие зоны (двусветные, техпространства) бывают выше
    следующего уровня.
    """
    options = Options()
    options.DetailLevel = ViewDetailLevel.Fine
    sources = model_sources(doc)
    edges = []
    for source_key, element_id in sorted(element_keys):
        if source_key not in sources:
            continue
        source_doc, transform = sources[source_key]
        element = source_doc.GetElement(ElementId(element_id))
        if element is None or _is_column(element):   # контур капители — не перепад плиты
            continue
        try:
            bbox = element.get_BoundingBox(None)
            z0 = transform.OfPoint(bbox.Min).Z
            z1 = transform.OfPoint(bbox.Max).Z
        except Exception:
            continue
        if max(z0, z1) < bottom_z:
            continue
        try:
            geometry = element.get_Geometry(options)
        except Exception:
            continue
        for solid, solid_transform in _solids(geometry, transform):
            for face in solid.Faces:
                if not isinstance(face, PlanarFace):
                    continue
                normal = solid_transform.OfVector(face.FaceNormal)
                if normal.Z > -0.99:
                    continue
                z = solid_transform.OfPoint(face.Origin).Z
                if z < bottom_z:
                    continue
                for loop in face.EdgeLoops:
                    for edge in loop:
                        points = [solid_transform.OfPoint(p)
                                  for p in edge.AsCurve().Tessellate()]
                        for a, b in zip(points, points[1:]):
                            edges.append((mm(a.X), mm(a.Y), mm(b.X), mm(b.Y), mm(z)))
    return edges


def _slab_mm_at(probe, x, y, level_z, probe_ft):
    found = probe.probe(x, y, level_z + probe_ft, level_z)
    return None if found is None else found.slab_z_mm


# Наибольшее число проверок лучами на план (каждая — 2 точки по сторонам
# линии, ~0,1 с): дальше — только самые длинные линии, остальные в отчёт.
STEP_CHECK_BUDGET = 1500


def _confirmed(probe, piece, side, level_z, probe_ft):
    x1, y1, x2, y2, _dz = piece
    length = ((x2 - x1) ** 2 + (y2 - y1) ** 2) ** 0.5
    nx, ny = -(y2 - y1) / length * side, (x2 - x1) / length * side
    mx, my = (x1 + x2) / 2.0, (y1 + y2) / 2.0
    left = _slab_mm_at(probe, ft(mx + nx), ft(my + ny), level_z, probe_ft)
    right = _slab_mm_at(probe, ft(mx - nx), ft(my - ny), level_z, probe_ft)
    return left is not None and right is not None and abs(left - right) >= STEP_MIN_DZ_MM


def find_steps(view, settings, probe, edges, progress=None):
    """
    Линии перепада плиты на плане (без изменений модели — только лучи):
    по краям нижних граней перекрытий edges (slab_marks_core.step_segments);
    каждый кандидат проверяется лучами по обе стороны линии — там должны
    быть перекрытия с разной отметкой. Куски одной линии сначала
    склеиваются (merge_collinear), длинная линия проверяется частями по
    ~3 м (split_segment) — остаются только подтверждённые части. Проверок
    не больше STEP_CHECK_BUDGET. Возвращает (отрезки в мм, StepStats);
    рисует draw_step_lines.
    """
    stats = StepStats()
    level_z = view.GenLevel.ProjectElevation
    probe_ft = ft(settings.get("probe_height_mm") or 1500.0)
    tol_mm = settings.get("step_search_mm") or 600.0
    stats.edges = len(edges)
    candidates = core.step_segments(edges, tol_mm, STEP_MIN_DZ_MM, STEP_MIN_LEN_MM)
    stats.candidates = len(candidates)
    lines = core.merge_collinear(candidates, tol_mm=100.0)
    lines.sort(key=lambda s: -((s[2] - s[0]) ** 2 + (s[3] - s[1]) ** 2))
    stats.lines = len(lines)
    if len(lines) > STEP_CHECK_BUDGET:
        stats.skipped = len(lines) - STEP_CHECK_BUDGET
        lines = lines[:STEP_CHECK_BUDGET]
    pieces = [core.split_segment(line) for line in lines]
    if sum(len(p) for p in pieces) > STEP_CHECK_BUDGET:
        pieces = [[line] for line in lines]   # не укладываемся — по одной проверке на линию
    side = tol_mm + 150.0
    confirmed = []
    for index, line_pieces in enumerate(pieces):
        if progress is not None:
            progress(index, len(pieces))
        for piece in line_pieces:
            if _confirmed(probe, piece, side, level_z, probe_ft):
                confirmed.append(piece)
            else:
                stats.rejected += 1
    segments = [s for s in core.merge_collinear(confirmed, tol_mm=100.0)
                if ((s[2] - s[0]) ** 2 + (s[3] - s[1]) ** 2) ** 0.5 >= STEP_MIN_LEN_MM]
    return segments, stats


def draw_step_lines(doc, view, segments, style, stats):
    level_z = view.GenLevel.ProjectElevation
    for x1, y1, x2, y2, _dz in segments:
        try:
            line = Line.CreateBound(XYZ(ft(x1), ft(y1), level_z), XYZ(ft(x2), ft(y2), level_z))
            curve = doc.Create.NewDetailCurve(view, line)
            if style is not None:
                curve.LineStyle = style
            stats.drawn += 1
        except Exception as ex:
            stats.errors.append(u"линия перепада плиты — {}".format(ex))


def draw_steps(doc, view, settings, probe, style, progress=None):
    """find_steps + draw_step_lines по всем плитам, найденным лучами с уровня вида."""
    level_z = view.GenLevel.ProjectElevation
    probe_ft = ft(settings.get("probe_height_mm") or 1500.0)
    slabs = probe.slabs_above(level_z, ft(settings.get("level_tolerance_mm") or 0.0))
    edges = slab_bottom_edges(doc, slabs, level_z + probe_ft)
    segments, stats = find_steps(view, settings, probe, edges, progress)
    stats.slabs = len(slabs)
    draw_step_lines(doc, view, segments, style, stats)
    return stats


class StepStats(object):
    """Счётчики поиска перепадов — для отчёта (где отсеялись кандидаты)."""

    def __init__(self):
        self.slabs = 0        # плит, в которые упёрлись лучи с уровня
        self.edges = 0        # краёв их нижних граней
        self.candidates = 0   # пар краёв с разной отметкой рядом в плане
        self.lines = 0        # линий после склейки кусков
        self.skipped = 0      # линий сверх STEP_CHECK_BUDGET (не проверены)
        self.rejected = 0     # частей линий, не подтверждённых лучами по сторонам
        self.drawn = 0
        self.errors = []


# ------------------------------------------------------------
# Заливки плит
# ------------------------------------------------------------

# Метка в «Комментариях» заливок плит; типы заливки — «LowLife пер. +4,400».
SLAB_REGION_TAG = u"LowLife пер."
SLAB_TYPE_PREFIX = u"LowLife пер. "

# Грани меньше этой площади (опоры, капители, мелкие ниши) не заливаются.
MIN_FILL_AREA_MM2 = 0.5e6

# Отметка грани и перекрытия под лучом в точке подписи расходятся больше —
# грань закрыта более низкой плитой, не заливается.
FACE_MATCH_MM = 30.0

# Точек проверки на помещение, когда в помещениях подписываются только ПП.
ROOM_POINTS_CEILING_ONLY = 3

# Пол в точке подписи дальше этого от типового пола плана — луч провалился
# (отверстие у колонны, приямок): пробуется другая точка грани.
FLOOR_TOLERANCE_MM = 300.0

# Цвета штриховки по отметкам (красный — у линий перепада).
FILL_COLORS = [
    (0, 114, 189), (60, 160, 60), (240, 140, 40), (126, 47, 142), (0, 170, 200),
    (150, 150, 0), (200, 0, 160), (140, 90, 40), (40, 40, 160), (0, 128, 128),
]


class SlabFace(object):
    """Нижняя грань перекрытия: отметка, контур и отверстия (мм, координаты модели)."""

    def __init__(self, z_mm, outer, holes):
        self.z_mm = z_mm
        self.outer = outer
        self.holes = holes
        self.area = core.region_area(outer, holes)
        self.point = None       # точка подписи (мм)
        self.height_mm = None   # высота от пола по лучу в точке подписи
        self.column = False     # грань колонны — заливается, но не перепад плиты
        self.key = None         # (Id связи или -1, Id элемента)
        self.source = u""       # имя связи или «модель»
        self.type_name = u""
        self.status = u""       # для отчёта: залита / почему нет
        self.points = []        # точки подписи: основная и запасные (мм)

    def loops(self):
        return [self.outer] + list(self.holes)


def _loop_points(face, loop, transform):
    points = []
    for edge in loop:
        try:
            curve = edge.AsCurveFollowingFace(face)
        except Exception:
            curve = edge.AsCurve()
        for p in curve.Tessellate():
            p = transform.OfPoint(p)
            xy = (mm(p.X), mm(p.Y))
            if not points or abs(points[-1][0] - xy[0]) + abs(points[-1][1] - xy[1]) > 3.0:
                points.append(xy)
    if len(points) >= 2 and abs(points[0][0] - points[-1][0]) + abs(points[0][1] - points[-1][1]) <= 3.0:
        points.pop()
    return points


def _source_labels(doc):
    labels = {-1: u"модель"}
    for link in FilteredElementCollector(doc).OfClass(RevitLinkInstance):
        labels[link.Id.IntegerValue] = safe_element_name(link) or u"связь"
    return labels


def structural_floor_keys(doc, bottom_z, top_z):
    """
    Несущие перекрытия (толще THIN_FLOOR_MM — не отделка пола) модели и
    связей, чей габарит по высоте задевает [bottom_z, top_z] (футы):
    {(Id связи или -1, Id элемента)}. Добавляются к плитам, найденным
    лучами, — чтобы не пропустить капители и другие плиты, в которые не
    попал ни один луч; закрытые более низкими гранями отсекаются геометрией
    (slab_marks_core.lowest_face_at).
    """
    keys = set()
    for source_key, (source_doc, transform) in model_sources(doc).items():
        collector = (FilteredElementCollector(source_doc).OfCategory(BuiltInCategory.OST_Floors)
                     .WhereElementIsNotElementType())
        for element in collector:
            try:
                bbox = element.get_BoundingBox(None)
                z0 = transform.OfPoint(bbox.Min).Z
                z1 = transform.OfPoint(bbox.Max).Z
                if max(z0, z1) < bottom_z or min(z0, z1) > top_z:
                    continue
                param = element.get_Parameter(BuiltInParameter.FLOOR_ATTR_THICKNESS_PARAM)
                thickness = param.AsDouble() if param is not None and param.HasValue else abs(z1 - z0)
                if mm(thickness) < THIN_FLOOR_MM:
                    continue
            except Exception:
                continue
            keys.add((source_key, element.Id.IntegerValue))
    return keys


def slab_bottom_faces(doc, element_keys, bottom_z):
    """
    Нижние горизонтальные грани перекрытий из element_keys (как
    slab_bottom_edges) выше bottom_z: [SlabFace].
    """
    options = Options()
    options.DetailLevel = ViewDetailLevel.Fine
    sources = model_sources(doc)
    labels = _source_labels(doc)
    faces = []
    for source_key, element_id in sorted(element_keys):
        if source_key not in sources:
            continue
        source_doc, transform = sources[source_key]
        element = source_doc.GetElement(ElementId(element_id))
        if element is None:
            continue
        try:
            bbox = element.get_BoundingBox(None)
            if max(transform.OfPoint(bbox.Min).Z, transform.OfPoint(bbox.Max).Z) < bottom_z:
                continue
            geometry = element.get_Geometry(options)
        except Exception:
            continue
        try:
            type_name = safe_element_name(source_doc.GetElement(element.GetTypeId())) or u""
        except Exception:
            type_name = u""
        for solid, solid_transform in _solids(geometry, transform):
            for face in solid.Faces:
                if not isinstance(face, PlanarFace):
                    continue
                if solid_transform.OfVector(face.FaceNormal).Z > -0.99:
                    continue
                z = solid_transform.OfPoint(face.Origin).Z
                if z < bottom_z:
                    continue
                loops = [_loop_points(face, loop, solid_transform) for loop in face.EdgeLoops]
                outer, holes = core.split_outer(loops)
                if outer is not None:
                    face_item = SlabFace(mm(z), outer, holes)
                    face_item.column = _is_column(element)
                    face_item.key = (source_key, element_id)
                    face_item.source = labels.get(source_key, u"")
                    face_item.type_name = type_name
                    faces.append(face_item)
    return faces


def hatch_pattern(doc):
    """Штриховка для заливок плит: «диагональная», иначе первая не сплошная чертёжная."""
    from Autodesk.Revit.DB import FillPatternElement, FillPatternTarget
    fallback = None
    for pattern_element in FilteredElementCollector(doc).OfClass(FillPatternElement):
        try:
            pattern = pattern_element.GetFillPattern()
            if pattern.Target != FillPatternTarget.Drafting or pattern.IsSolidFill:
                continue
        except Exception:
            continue
        name = (safe_element_name(pattern_element) or u"").lower()
        if u"диагон" in name or u"diagonal" in name:
            return pattern_element
        if fallback is None:
            fallback = pattern_element
    return fallback


def slab_fill_type(doc, height_mm, color, base_type, pattern):
    """Тип заливки «LowLife пер. +4,400»: создаётся копией base_type, штриховка и цвет — на каждом запуске."""
    name = SLAB_TYPE_PREFIX + core.format_height(height_mm)
    found = None
    for candidate in FilteredElementCollector(doc).OfClass(FilledRegionType):
        if safe_element_name(candidate) == name:
            found = candidate
            break
    if found is None:
        found = base_type.Duplicate(name)
    try:
        if pattern is not None:
            found.ForegroundPatternId = pattern.Id
        found.ForegroundPatternColor = Color(*color)
        found.BackgroundPatternId = ElementId.InvalidElementId
    except Exception:
        pass
    return found


def _curve_loops(polygons, z):
    loops = []
    for polygon in polygons:
        points = [XYZ(ft(x), ft(y), z) for x, y in polygon]
        loop = CurveLoop()
        try:
            for i in range(len(points)):
                a, b = points[i], points[(i + 1) % len(points)]
                if a.DistanceTo(b) > _MIN_SEG_FT:
                    loop.Append(Line.CreateBound(a, b))
        except Exception:
            continue
        loops.append(loop)
    return loops


def _tag(element, text):
    param = element.get_Parameter(BuiltInParameter.ALL_MODEL_INSTANCE_COMMENTS)
    if _writable(param):
        param.Set(text)


# ------------------------------------------------------------
# План целиком
# ------------------------------------------------------------

class ViewResult(object):
    def __init__(self, view):
        self.view = view
        self.rooms = 0
        self.excluded_rooms = 0
        self.ceiling_rooms = 0
        self.steps = 0
        self.step_stats = None
        self.typical_mm = None
        self.slab_heights = []  # (высота мм, площадь м²) — заливки плит
        self.fills = 0
        self.faces = []        # SlabFace плит над этажом — для диагностики в отчёте
        self.typical_floor_mm = None  # пол плана относительно уровня (медиана по лучам вниз)
        self.changed = []      # (помещение, основная высота мм)
        self.no_slab = []      # имена помещений без перекрытия над ними
        self.errors = []


def annotate_view(doc, view, settings, probe, note_type, fill_type, step_style=None,
                  progress=None):
    """
    Всё по плану: заливки плит над уровнем вида по отметкам с подписями,
    подвесные потолки (ПП) и подписи в помещениях, линии перепада.
    Сначала все лучи (помещения, точки подписей плит, проверка перепадов),
    потом все изменения модели — иначе Revit пересобирает временный 3D-вид
    перед каждым лучом (см. move_detectors). ViewResult.
    """
    result = ViewResult(view)
    clear_view(doc, view, note_type)

    level_z = view.GenLevel.ProjectElevation
    tolerance = ft(settings.get("level_tolerance_mm") or 0.0)
    probe_ft = ft(settings.get("probe_height_mm") or 1500.0)
    step = settings.get("round_mm") or 10.0
    mode = settings.get("room_labels") or "ceiling"
    excluded = core.split_words(settings.get("excluded_room_words"))
    slab_format = settings.get("slab_text_format") or u"{h}"
    delta_format = settings.get("delta_text_format") or u"Δ {d}"
    ceiling_format = settings.get("ceiling_text_format") or u"ПП {h}"

    # --- 1. лучи: помещения ---
    rooms = []
    if mode != "none":
        for source in room_sources(doc):
            for room in source.rooms():
                room_z = _room_level_z(source, room)
                if room_z is None or abs(room_z - level_z) > tolerance + 1e-6:
                    continue
                if excluded and core.has_word(room_name(room), excluded):
                    result.excluded_rooms += 1
                    continue
                rooms.append((source, room, room_z))
    # Для одних ПП хватает 1–3 точек (точка помещения + сетка 2×2 в больших),
    # для подписей перекрытия во всех помещениях — до 10 (сетка 3×3).
    grid, limit = (3, None) if mode == "all" else (2, ROOM_POINTS_CEILING_ONLY)
    marks = []
    for index, (source, room, room_z) in enumerate(rooms):
        if progress is not None:
            progress(index, len(rooms))
        link_level_z = source.doc.GetElement(room.LevelId).ProjectElevation
        mark = RoomMark(source, room, room_name(room))
        for point in _room_points(room, link_level_z, probe_ft, grid, limit):
            host = source.transform.OfPoint(point)
            found = probe.probe(host.X, host.Y, room_z + probe_ft, room_z)
            if mark.anchor is None:
                mark.anchor = XYZ(host.X, host.Y, level_z)
            if found is not None:
                mark.probes.append(found)
        if mark.anchor is not None:
            marks.append(mark)

    # --- 2. плиты над уровнем: грани и лучи в точках подписей ---
    slabs = probe.slabs_above(level_z, tolerance)
    faces = slab_bottom_faces(doc, slabs, level_z + probe_ft) if slabs else []
    if faces:
        # плиты, в которые не попал ни один луч (капители и т. п.): все
        # несущие перекрытия до самой высокой найденной лучами грани
        top = ft(max(f.z_mm for f in faces) + FACE_MATCH_MM)
        extra = structural_floor_keys(doc, level_z + probe_ft, top) - set(slabs)
        faces += [f for f in slab_bottom_faces(doc, extra, level_z + probe_ft)
                  if f.z_mm <= mm(top)]
    result.faces = faces

    # Что видно снизу и на какой отметке — по геометрии граней, а не по лучу
    # вверх (у капителей луч бывает отдаёт верхнюю грань). Дубли (одна плита
    # в АР и в КР) и закрытые более низкими гранями — отбрасываются.
    regions = [(f.z_mm, f.outer, f.holes, core.polygon_bbox(f.outer)) for f in faces]
    duplicates = core.duplicate_faces([(f.z_mm, r[3], f.area) for f, r in zip(faces, regions)])
    visible = []
    for index, face in enumerate(faces):
        if face.area < MIN_FILL_AREA_MM2:
            face.status = u"меньше {:.1f} м²".format(MIN_FILL_AREA_MM2 / 1e6)
            continue
        if index in duplicates:
            face.status = u"дубль (та же плита в другой связи)"
            continue
        face.points = core.interior_points(face.outer, face.holes)
        if not face.points:
            face.status = u"нет точки внутри контура"
            continue
        point = face.points[0]
        lowest = core.lowest_face_at(point[0], point[1], regions)
        if lowest is not None and faces[lowest] is not face and \
                faces[lowest].z_mm < face.z_mm - FACE_MATCH_MM:
            face.status = u"закрыта более низкой плитой ({})".format(
                core.format_height(faces[lowest].z_mm - mm(level_z), signed=True))
            continue
        visible.append(face)

    fills = []
    if (settings.get("draw_slab_fills") or "yes") != "no":
        # Высота от пола: луч вниз в точке подписи. Если пол там далеко от
        # типового пола плана (над колонной в плите пола отверстие — луч
        # проваливается ниже), пробуются запасные точки грани; не нашлось —
        # типовой пол.
        level_mm = mm(level_z)
        offsets = [p.floor_z_mm - level_mm for m in marks for p in m.probes]
        if not offsets:
            for face in visible:
                found = probe.probe(ft(face.points[0][0]), ft(face.points[0][1]),
                                    level_z + probe_ft, level_z)
                if found is not None:
                    offsets.append(found.floor_z_mm - level_mm)
        typical_floor = core.median(offsets)
        result.typical_floor_mm = typical_floor
        for index, face in enumerate(visible):
            if progress is not None:
                progress(index, len(visible))
            chosen = None
            for point in face.points:
                found = probe.probe(ft(point[0]), ft(point[1]), level_z + probe_ft, level_z)
                if found is None:
                    continue
                offset = found.floor_z_mm - level_mm
                if typical_floor is None or abs(offset - typical_floor) <= FLOOR_TOLERANCE_MM:
                    chosen = (point, found.floor_z_mm)
                    break
            if chosen is None:
                chosen = (face.points[0], level_mm + (typical_floor or 0.0))
                face.status = u"залита (пол — типовой плана)"
            else:
                face.status = u"залита"
            face.point = chosen[0]
            face.height_mm = face.z_mm - chosen[1]
            fills.append(face)
    else:
        for face in visible:
            face.status = u"заливки выключены"

    # --- 3. лучи: проверка перепадов ---
    step_segments = []
    if (settings.get("draw_steps") or "yes") != "no":
        # Края только видимых снизу граней: закрытые (отделка, стяжки) и
        # дубли давали тысячи ложных кандидатов.
        edges = []
        for face in visible:
            if not face.column:   # контур колонны — не перепад плиты
                edges.extend(core.loop_edges(face.loops(), face.z_mm))
        step_segments, result.step_stats = find_steps(view, settings, probe, edges, progress)
        result.step_stats.slabs = len(slabs)

    # --- типовая высота: по площади заливок, иначе по помещениям ---
    if fills:
        result.typical_mm = core.typical_by_area(
            [(f.height_mm, f.area / 1e6) for f in fills], step)
        totals = {}
        for f in fills:
            key = core.round_to(f.height_mm, step)
            totals[key] = totals.get(key, 0.0) + f.area / 1e6
        result.slab_heights = sorted(totals.items())
    else:
        result.typical_mm = core.typical_height(
            [core.main_height(m.slab_values(), step) for m in marks], step)

    # --- 4. изменения модели ---
    if fills:
        base = fill_type or region_type(doc, None)
        pattern = hatch_pattern(doc)
        heights = [h for h, _area in result.slab_heights]
        types = {}
        for face in fills:
            key = core.round_to(face.height_mm, step)
            try:
                if key not in types:
                    color = FILL_COLORS[heights.index(key) % len(FILL_COLORS)]
                    types[key] = slab_fill_type(doc, key, color, base, pattern)
                from System.Collections.Generic import List
                region = FilledRegion.Create(doc, types[key].Id, view.Id,
                                             List[CurveLoop](_curve_loops(face.loops(), level_z)))
                _tag(region, u"{} {}".format(SLAB_REGION_TAG, core.format_height(key)))
                text = core.slab_label(face.height_mm, result.typical_mm, step,
                                       slab_format, delta_format)
                TextNote.Create(doc, view.Id, XYZ(ft(face.point[0]), ft(face.point[1]), level_z),
                                text.replace(u"\n", u"\r"), note_type.Id)
                result.fills += 1
            except Exception as ex:
                result.errors.append(u"заливка плиты {} — {}".format(core.format_height(key), ex))

    for index, mark in enumerate(marks):
        if not mark.probes:
            result.no_slab.append(mark.name)
            continue
        ceiling = core.has_ceiling(mark.ceiling_values())
        if mode == "all":
            text = core.room_label(mark.slab_values(), mark.ceiling_values(), result.typical_mm,
                                   step, slab_format, ceiling_format, delta_format)
            main = core.main_height(mark.slab_values(), step)
            if result.typical_mm is not None and main is not None and main != result.typical_mm:
                result.changed.append((mark.name, main))
        else:
            text = core.ceiling_label(mark.ceiling_values(), step, ceiling_format) if ceiling else u""
        if text:
            try:
                # абзацы текста Revit разделяет «\r»
                TextNote.Create(doc, view.Id, mark.anchor, text.replace(u"\n", u"\r"), note_type.Id)
                result.rooms += 1
            except Exception as ex:
                result.errors.append(u"{}: подпись — {}".format(mark.name, ex))
        if ceiling:
            if fill_type is None:
                result.errors.append(u"{}: в проекте нет типа области заливки".format(mark.name))
                continue
            region, error = _filled_region(doc, view, fill_type.Id, mark.room,
                                           mark.source.transform, level_z)
            if region is None:
                result.errors.append(u"{}: область заливки — {}".format(mark.name, error))
                continue
            _tag(region, u"{} {}".format(REGION_TAG, mark.name))
            result.ceiling_rooms += 1

    if result.step_stats is not None:
        draw_step_lines(doc, view, step_segments, step_style, result.step_stats)
        result.steps = result.step_stats.drawn
        result.errors.extend(result.step_stats.errors)
    if probe.error is not None:
        result.errors.append(u"луч к перекрытию: {}".format(probe.error))
    return result
