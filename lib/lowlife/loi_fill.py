# -*- coding: utf-8 -*-
"""
Логика кнопки «Заполнение LOI» (LOI.panel): клонирование значений
параметров из элементов категории «Форма» (FORM_CATEGORY_NAME — она всегда
одна и та же, не настраивается) во все элементы активного вида, физически
находящиеся внутри солида конкретной «Формы».

Проверка «элемент внутри формы» — точно по солиду формы (не по bounding
box): для точечных элементов (LocationPoint) — попадание точки в солид
через ray-casting (point_in_solid), для линейных (LocationCurve, лотки/
короба/трубы) — пересечение кривой с солидом (curve_intersects_solid,
через Solid.IntersectWithCurve — та же проверка, что и для точки, просто
на всей длине кривой, а не в одной точке). Bounding box формы/элемента —
только дешёвый предварительный отсев пар, которые точно не пересекаются,
перед дорогой точной проверкой.

Линейный элемент может попасть сразу в несколько «Форм» (например лоток,
проходящий через границу двух форм) — для такого элемента однозначно
клонировать нечего. Если элемент прямой (LocationCurve.Curve — Line),
loi_split.py сначала пробует физически разрезать его по границам форм и
записать каждому куску значения его формы; то, что разрезать не удалось
(кривые участки, точечные элементы, наложенные формы), по-прежнему идёт в
список конфликтов, где источник выбирает пользователь (see
loi_conflict_dialog.py). Элемент, попавший ровно в одну форму, клонируется
автоматически.

Какие именно элементы вообще проверяются на попадание в форму — определяет
SELECTION_MODE_* (см. collect_candidates): весь документ, только активный
вид, либо только выбранные в настройках типы семейств.

«Формы» обычно лежат в отдельной связанной архитектурной модели — какие
именно модели просматривать (текущий файл-хост и/или конкретные загруженные
связи по имени), выбирает пользователь в настройках (loi_settings.py,
SEARCH_LOCATIONS_KEY) вместо того, чтобы искать их во всех связях подряд;
см. find_forms/list_search_locations. Ищутся по ВСЕМУ документу каждой
модели, а не по активному виду — у «Форм» часто намеренно выключена
видимость (категория скрыта в настройках графики), поэтому поиск не должен
зависеть от того, что видно на текущем виде хоста. Геометрия и bbox
элементов связи трансформируются в координаты текущего файла через
RevitLinkInstance.GetTotalTransform(), тем же способом, что и у обычного
элемента текущего файла, только с дополнительным Transform. Кандидаты
(элементы, которые заполняются) ищутся только в текущем файле — писать
параметры в элементы связи API не позволяет (это отдельный открытый
Document, а не часть текущей транзакции).
"""

from Autodesk.Revit.DB import (
    Element, ElementId, FilteredElementCollector, Options, Solid, GeometryInstance,
    LocationPoint, LocationCurve, Line, XYZ, SolidCurveIntersectionOptions,
    CategoryType, ViewDetailLevel, RevitLinkInstance, SolidUtils, BoundingBoxXYZ
)

from lowlife import params as params_mod

MIN_SOLID_VOLUME = 1e-9
RAY_LENGTH_FT = 10000.0
POINT_TOL_FT = 0.01
BBOX_TOL_FT = 0.01

# Категория элементов «Формы» — зона, по которой всегда строится LOI, одна
# и та же во всех проектах (в отличие от имён клонируемых параметров, это
# не соглашение конкретного ФОП), поэтому она фиксирована, а не читается
# из настроек.
FORM_CATEGORY_NAME = u"Формы"

# Ключ HOST_LOCATION_KEY в списке «где искать формы» (settings.search_locations)
# означает «искать в текущем файле-хосте» — остальные элементы списка это
# имена загруженных связей (RevitLinkInstance), см. list_search_locations.
HOST_LOCATION_KEY = u"HOST"

# Режимы отбора кандидатов (loi_settings.MODE_KEY) — какие элементы вообще
# проверяются на попадание в «Формы»:
#   view  — модельные элементы активного вида (исходное поведение);
#   all   — все модельные элементы документа, без привязки к виду;
#   types — только экземпляры заранее отмеченных типов семейств
#           (selected_type_ids), по всему документу.
SELECTION_MODE_VIEW = u"view"
SELECTION_MODE_ALL = u"all"
SELECTION_MODE_TYPES = u"types"


# --- геометрия -----------------------------------------------------------

def _iter_solids(geometry_element):
    solids = []
    for gobj in geometry_element:
        if isinstance(gobj, Solid):
            if gobj.Volume > MIN_SOLID_VOLUME:
                solids.append(gobj)
        elif isinstance(gobj, GeometryInstance):
            try:
                inst_geom = gobj.GetInstanceGeometry()
            except:
                inst_geom = None
            if inst_geom is not None:
                solids.extend(_iter_solids(inst_geom))
    return solids


def get_element_solids(el, extra_transform=None):
    """
    Все твёрдые тела элемента (Volume > 0), в координатах его собственного
    документа. extra_transform (например RevitLinkInstance.GetTotalTransform())
    — для элемента из связи, чтобы получить солид в координатах текущего файла.
    """
    opts = Options()
    opts.ComputeReferences = False
    opts.IncludeNonVisibleObjects = False
    opts.DetailLevel = ViewDetailLevel.Fine

    try:
        geom = el.get_Geometry(opts)
    except:
        geom = None

    if geom is None:
        return []

    solids = _iter_solids(geom)

    if extra_transform is None or extra_transform.IsIdentity:
        return solids

    transformed = []
    for solid in solids:
        try:
            transformed.append(SolidUtils.CreateTransformed(solid, extra_transform))
        except:
            transformed.append(solid)
    return transformed


def _transform_bbox(bbox, transform):
    """Bbox элемента связи (в координатах связи) -> bbox в координатах текущего файла."""
    if bbox is None:
        return None
    if transform is None or transform.IsIdentity:
        return bbox

    xs, ys, zs = [], [], []
    for x in (bbox.Min.X, bbox.Max.X):
        for y in (bbox.Min.Y, bbox.Max.Y):
            for z in (bbox.Min.Z, bbox.Max.Z):
                p = transform.OfPoint(XYZ(x, y, z))
                xs.append(p.X)
                ys.append(p.Y)
                zs.append(p.Z)

    new_bbox = BoundingBoxXYZ()
    new_bbox.Min = XYZ(min(xs), min(ys), min(zs))
    new_bbox.Max = XYZ(max(xs), max(ys), max(zs))
    return new_bbox


def point_in_solid(solid, pt, tol=POINT_TOL_FT):
    """
    True, если точка pt лежит внутри solid — ray-casting: пускаем луч
    вверх ИЗ точки и смотрим, начинается ли первый "внутренний" отрезок
    пересечения ровно в pt (если pt внутри тела — луч сразу входит в
    "внутри", если снаружи — первый внутренний отрезок начнётся дальше,
    в точке входа в тело, либо пересечений не будет вовсе).
    """
    ray = Line.CreateBound(pt, XYZ(pt.X, pt.Y, pt.Z + RAY_LENGTH_FT))

    try:
        result = solid.IntersectWithCurve(ray, SolidCurveIntersectionOptions())
    except:
        return False

    if result is None or result.SegmentCount == 0:
        return False

    seg0 = result.GetCurveSegment(0)
    start = seg0.GetEndPoint(0)
    return start.DistanceTo(pt) <= tol


def curve_intersects_solid(solid, curve):
    """True, если хотя бы часть curve лежит внутри solid."""
    try:
        result = solid.IntersectWithCurve(curve, SolidCurveIntersectionOptions())
    except:
        return False

    return result is not None and result.SegmentCount > 0


def get_test_geometry(el):
    """
    ("point", XYZ) для точечных элементов, ("curve", Curve) для линейных,
    ("point", XYZ-центр bbox) как запасной вариант для всего остального
    (нет LocationPoint/LocationCurve — например элемент, заданный только
    солидом без явной точки/кривой вставки). None, если геометрию найти
    не удалось вовсе.
    """
    try:
        loc = el.Location
    except:
        loc = None

    if isinstance(loc, LocationPoint):
        return ("point", loc.Point)

    if isinstance(loc, LocationCurve):
        return ("curve", loc.Curve)

    try:
        bbox = el.get_BoundingBox(None)
    except:
        bbox = None

    if bbox is None:
        return None

    center = XYZ(
        (bbox.Min.X + bbox.Max.X) / 2.0,
        (bbox.Min.Y + bbox.Max.Y) / 2.0,
        (bbox.Min.Z + bbox.Max.Z) / 2.0,
    )
    return ("point", center)


def bbox_overlap(a, b, tol=BBOX_TOL_FT):
    """Дешёвый предварительный отсев: пересекаются ли габариты a и b (с запасом tol)."""
    if a is None or b is None:
        return True

    return not (
        a.Max.X + tol < b.Min.X or b.Max.X + tol < a.Min.X or
        a.Max.Y + tol < b.Min.Y or b.Max.Y + tol < a.Min.Y or
        a.Max.Z + tol < b.Min.Z or b.Max.Z + tol < a.Min.Z
    )


# --- сбор форм/кандидатов -------------------------------------------------

class FormRecord(object):
    def __init__(self, element, solids, bbox, label):
        self.element = element
        self.solids = solids
        self.bbox = bbox
        self.label = label


def _collect_form_records(collector, category_name, type_doc, transform, source_label):
    records = []

    for el in collector:
        cat = el.Category
        if cat is None or cat.Name != category_name:
            continue

        solids = get_element_solids(el, transform)
        if not solids:
            continue

        try:
            bbox = el.get_BoundingBox(None)
        except:
            bbox = None
        bbox = _transform_bbox(bbox, transform)

        label = u"{} (ID {})".format(element_display_name(type_doc, el), el.Id.IntegerValue)
        if source_label:
            label = u"{} [{}]".format(label, source_label)

        records.append(FormRecord(el, solids, bbox, label))

    return records


def find_forms(doc, category_name, locations=None):
    """
    Элементы категории category_name — по всему текущему файлу и по всем
    загруженным связям (весь документ, БЕЗ привязки к виду в обоих
    случаях — геометрия/bbox элементов связи трансформируются в координаты
    текущего файла через RevitLinkInstance.GetTotalTransform()).

    Специально не FilteredElementCollector(doc, view.Id) для хоста: «Формы»
    — это зоны для переноса параметров, а не то, что обязано быть видимым
    на текущем виде; у них часто намеренно выключена видимость (категория
    скрыта в настройках графики вида) — collector, ограниченный видом,
    такие элементы молча не находит, хотя физически они в документе есть.

    locations — какие модели просматривать (значения settings.search_locations,
    см. loi_settings.py): список строк, HOST_LOCATION_KEY — текущий файл,
    остальное — точные имена RevitLinkInstance (как их возвращает
    list_search_locations/_safe_name). None (настройка ещё не тронута) —
    прежнее поведение: искать везде (хост + все загруженные связи).
    """
    records = []

    search_host = locations is None or HOST_LOCATION_KEY in locations
    if search_host:
        host_collector = FilteredElementCollector(doc).WhereElementIsNotElementType()
        records.extend(_collect_form_records(host_collector, category_name, doc, None, u""))

    link_collector = FilteredElementCollector(doc).OfClass(RevitLinkInstance)
    for link_inst in link_collector:
        link_name = _safe_name(link_inst)
        if locations is not None and link_name not in locations:
            continue

        try:
            link_doc = link_inst.GetLinkDocument()
        except:
            link_doc = None
        if link_doc is None:
            continue

        try:
            transform = link_inst.GetTotalTransform()
        except:
            transform = None

        link_elems = FilteredElementCollector(link_doc).WhereElementIsNotElementType()
        records.extend(_collect_form_records(link_elems, category_name, link_doc, transform, link_name))

    return records


def _bigrams(s):
    if len(s) < 2:
        return set([s]) if s else set()
    return set(s[i:i + 2] for i in range(len(s) - 1))


def _name_similarity(a, b):
    """
    Похожесть двух имён 0..1 — коэффициент Сёренсена—Дайса по буквенным
    биграммам, регистронезависимо (тот же метод, что
    family_catalog.similarity, здесь — самостоятельная копия, чтобы не
    тянуть в LOI чужой модуль ради одной функции). Нужна вместо простой
    проверки «одно имя — подстрока другого»: «форма» не является подстрокой
    «формы» (расходятся в последней букве), а спутать их легко.
    """
    na, nb = (a or u"").lower(), (b or u"").lower()
    if not na or not nb:
        return 0.0
    if na == nb:
        return 1.0
    ba, bb = _bigrams(na), _bigrams(nb)
    denom = len(ba) + len(bb)
    return (2.0 * len(ba & bb) / denom) if denom else 0.0


SIMILAR_CATEGORY_THRESHOLD = 0.4


def diagnose_form_search(doc, category_name, locations):
    """
    Диагностика для сообщения «форм не найдено» — вместо гадания, что не
    так, показывает по КАЖДОЙ модели документа (текущий файл + все
    загруженные связи, НЕЗАВИСИМО от того, что отмечено в locations —
    иначе, если «Формы» физически лежат в модели, которую забыли отметить
    в «Выбрать модели…», об этом никогда не узнать) — сколько элементов
    категории category_name там вообще есть (без требования солида) и
    сколько из них реально с солидом (столько же, сколько найдёт
    find_forms); отмечает, входила ли эта модель в фактический поиск.
    Похожие по написанию категории (вдруг реальное имя отличается —
    «Формы» вместо «Форма», опечатка) ищутся по буквенным биграммам
    (_name_similarity), а не подстрокой. Плюс — связи из настроек, которые
    сейчас не найдены среди загруженных (переименовали/выгрузили после
    того, как их отметили). Возвращает список строк для показа пользователю.
    """
    lines = []
    search_host = locations is None or HOST_LOCATION_KEY in locations

    def _scan(scan_doc, label, included):
        total = 0
        with_solid = 0
        seen_names = set()
        similar = []  # (similarity, name)

        for el in FilteredElementCollector(scan_doc).WhereElementIsNotElementType():
            cat = el.Category
            if cat is None:
                continue
            if cat.Name == category_name:
                total += 1
                if get_element_solids(el):
                    with_solid += 1
            elif cat.Name not in seen_names:
                seen_names.add(cat.Name)
                sim = _name_similarity(category_name, cat.Name)
                if sim >= SIMILAR_CATEGORY_THRESHOLD:
                    similar.append((sim, cat.Name))

        mark = u"" if included else u" [не входит в текущий поиск]"
        line = u"«{}»{}: элементов категории «{}» — {} (с солидом — {})".format(
            label, mark, category_name, total, with_solid
        )
        if similar:
            similar.sort(key=lambda x: -x[0])
            line += u"; похожие по названию категории есть в этой модели: {}".format(
                u", ".join(u"«{}»".format(name) for _sim, name in similar[:5])
            )
        lines.append(line)

    _scan(doc, u"Текущий файл", search_host)

    loaded_link_names = set()
    for link_inst in FilteredElementCollector(doc).OfClass(RevitLinkInstance):
        link_name = _safe_name(link_inst)
        loaded_link_names.add(link_name)
        included = locations is None or link_name in locations

        try:
            link_doc = link_inst.GetLinkDocument()
        except:
            link_doc = None
        if link_doc is None:
            lines.append(
                u"«{}»{}: связь сейчас не загружена (Unload/не найден путь) — "
                u"просканировать нельзя.".format(
                    link_name, u"" if included else u" [не входит в текущий поиск]"
                )
            )
            continue

        _scan(link_doc, link_name, included)

    if locations:
        missing = [
            loc for loc in locations
            if loc != HOST_LOCATION_KEY and loc not in loaded_link_names
        ]
        for m in missing:
            lines.append(
                u"«{}»: такая связь сейчас не найдена среди загруженных в "
                u"документе — переименована, удалена или не загружена; "
                u"откройте настройки и выберите модели заново.".format(m)
            )

    return lines


class LocationOption(object):
    """Модель — кандидат для поиска «Форм»: текущий файл (HOST_LOCATION_KEY)
    или загруженная связь по имени — для чек-листа в настройках."""

    def __init__(self, key, label):
        self.key = key
        self.name = label

    def __str__(self):
        return self.name


def list_search_locations(doc):
    """
    Текущий файл + все загруженные связи документа (по имени, даже
    выгруженные — RevitLinkInstance остаётся в документе) — источник
    списка для настройки «В каких моделях искать формы».
    """
    options = [LocationOption(HOST_LOCATION_KEY, u"Текущий файл (хост)")]

    for link_inst in FilteredElementCollector(doc).OfClass(RevitLinkInstance):
        name = _safe_name(link_inst)
        if name:
            options.append(LocationOption(name, u"Связь: {}".format(name)))

    return options


def collect_candidates(doc, view, exclude_category_name,
                        mode=SELECTION_MODE_VIEW, type_ids=None):
    """
    Элементы модели — кандидаты на попадание в «Формы», кроме самих
    «Форм» и не-модельных категорий. mode (см. SELECTION_MODE_*):
      view  — только элементы активного вида (исходное поведение, view.Id);
      all   — все элементы документа, вид не учитывается;
      types — все элементы документа, чей GetTypeId() входит в type_ids
              (набор int — ElementId.IntegerValue типов, см.
              list_candidate_types); пустой/None type_ids -> пустой
              результат (нечего искать).
    """
    if mode == SELECTION_MODE_TYPES:
        wanted_type_ids = set(type_ids or [])
        if not wanted_type_ids:
            return []
        collector = FilteredElementCollector(doc).WhereElementIsNotElementType()
    elif mode == SELECTION_MODE_ALL:
        wanted_type_ids = None
        collector = FilteredElementCollector(doc).WhereElementIsNotElementType()
    else:
        wanted_type_ids = None
        collector = FilteredElementCollector(doc, view.Id).WhereElementIsNotElementType()

    result = []
    for el in collector:
        cat = el.Category
        if cat is None:
            continue
        if cat.Name == exclude_category_name:
            continue
        try:
            if cat.CategoryType != CategoryType.Model:
                continue
        except:
            continue

        if wanted_type_ids is not None:
            try:
                tid = el.GetTypeId()
            except:
                tid = None
            if tid is None or tid.IntegerValue not in wanted_type_ids:
                continue

        result.append(el)

    return result


class MatchRecord(object):
    def __init__(self, element, forms_matched):
        self.element = element
        self.forms = forms_matched  # list of FormRecord


def classify_elements(form_records, candidates):
    """
    {ElementId: MatchRecord} только для кандидатов, попавших хотя бы в
    одну форму (0 совпадений — элемент просто не участвует).
    """
    matches = {}

    for el in candidates:
        test = get_test_geometry(el)
        if test is None:
            continue

        try:
            el_bbox = el.get_BoundingBox(None)
        except:
            el_bbox = None

        matched_forms = []
        for form in form_records:
            if not bbox_overlap(el_bbox, form.bbox):
                continue

            hit = False
            for solid in form.solids:
                if test[0] == "point":
                    if point_in_solid(solid, test[1]):
                        hit = True
                        break
                else:
                    if curve_intersects_solid(solid, test[1]):
                        hit = True
                        break

            if hit:
                matched_forms.append(form)

        if matched_forms:
            matches[el.Id] = MatchRecord(el, matched_forms)

    return matches


# --- параметры -------------------------------------------------------------

def _safe_name(el):
    # Element.Name.GetValue(el) avoids the ambiguous-binding error some
    # element types throw on plain el.Name under IronPython (see
    # scs_settings._safe_element_name / cable_tray._safe_type_name).
    try:
        return Element.Name.GetValue(el)
    except:
        try:
            return el.Name
        except:
            return u""


def element_type_name(doc, el):
    """Имя типа (FamilySymbol/ElementType) элемента el, иначе — имя самого el."""
    type_el = None
    try:
        type_id = el.GetTypeId()
        if type_id is not None:
            type_el = doc.GetElement(type_id)
    except:
        type_el = None

    if type_el is not None:
        name = _safe_name(type_el)
        if name:
            return name

    return _safe_name(el)


def element_display_name(doc, el):
    try:
        cat_name = el.Category.Name
    except:
        cat_name = u"?"
    return u"{}: {}".format(cat_name, element_type_name(doc, el))


class TypeOption(object):
    """Тип элемента (FamilySymbol/системный ElementType) — для чек-листа
    «Выбранные типы семейств» в настройках (forms.SelectFromList)."""

    def __init__(self, type_id, label):
        self.type_id = type_id
        self.name = label

    def __str__(self):
        return self.name


def list_candidate_types(doc, exclude_category_name):
    """
    Типы, у которых в документе есть хотя бы один экземпляр модельной
    категории (кроме категории «Форма») — источник списка для режима
    отбора «Выбранные типы семейств» (SELECTION_MODE_TYPES). Подпись —
    «Категория — Имя типа (N экз.)», отсортировано по ней же.
    """
    counts = {}
    labels = {}

    for el in FilteredElementCollector(doc).WhereElementIsNotElementType():
        cat = el.Category
        if cat is None or cat.Name == exclude_category_name:
            continue
        try:
            if cat.CategoryType != CategoryType.Model:
                continue
        except:
            continue

        try:
            tid = el.GetTypeId()
        except:
            tid = None
        if tid is None or tid == ElementId.InvalidElementId:
            continue

        key = tid.IntegerValue
        counts[key] = counts.get(key, 0) + 1
        if key not in labels:
            labels[key] = u"{} — {}".format(cat.Name, element_type_name(doc, el))

    options = [
        TypeOption(ElementId(key), u"{} ({} экз.)".format(labels[key], counts[key]))
        for key in counts
    ]
    options.sort(key=lambda o: o.name.lower())
    return options


def collect_form_values(form_el, param_names):
    """{имя_параметра: строковое_значение} только для параметров, у которых есть значение."""
    values = {}
    for name in param_names:
        val = params_mod.get_param_any(form_el, name)
        if val is not None:
            values[name] = val
    return values


def format_values(values, param_names):
    parts = []
    for name in param_names:
        if name in values:
            parts.append(u"{}={}".format(name, values[name]))
    return u"; ".join(parts) if parts else u"—"


def apply_values(target_el, values):
    """
    Записывает values в target_el. Возвращает список (имя, значение, успех)
    — вызывающий код сам решает, что делать с неуспешными записями.
    Вызывать внутри revit.Transaction.
    """
    applied = []
    for name, val in values.items():
        ok = params_mod.set_param_any(target_el, name, val)
        applied.append((name, val, ok))
    return applied
