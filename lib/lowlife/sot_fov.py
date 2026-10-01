# -*- coding: utf-8 -*-
"""
СОТ: построение зоны обзора видеокамеры на активном виде (плоская 2D-зона
из области заливки), с обрезкой по границе помещения из связанной модели.

Отдельная дисциплина СОТ — но это не структурная схема, поэтому логика и
настройки живут не в sot_settings.py/sot_schematic.py, а здесь, со своим
файлом настроек %APPDATA%\\pyRevit\\LowLifeCameraFov_settings.json (тот же
приём «своя дисциплина — свой файл», что у scs_settings/skud_settings/
room_info_settings).

Что строит кнопка «Зоны обзора» (SOT.panel):
  1. по каждой выбранной камере горизонтальный И вертикальный угол
     обзора — ВСЕГДА расчётные (не параметр, вписанный вручную), из
     фокусного расстояния объектива и формата матрицы:
       hfov = 2*atan(w/2f),  vfov = 2*atan(h/2f)
     (см. _optical_fov); дальность — отдельный параметр камеры (это не
     оптика, а заявленная дальность распознавания/наблюдения). Все входы
     — экземпляра или типа, ищутся автоматически там и там (_find_param);
  2. направление «взгляда» — FamilyInstance.FacingOrientation (уже
     учитывает поворот и отражения экземпляра; параметр поворота НЕ
     складывается отдельно — иначе двойной учёт), плюс необязательный
     фиксированный доворот из настроек;
  3. если заданы параметры высоты установки и наклона оптической оси
     вниз — зона считается как проекция конуса (с уже посчитанным в
     п.1 вертикальным углом) на плоскость расчёта: ближняя мёртвая зона
     + дальняя граница
       near = h / tan(tilt + vfov/2),  far = h / tan(tilt - vfov/2)
     (far бесконечен при tilt <= vfov/2 -> обрезается дальностью);
  4. если задан RevitLinkInstance с помещениями — зона обрезается по
     контуру помещения, в котором стоит камера: каждый луч сектора
     укорачивается до первого пересечения с границей Room (работает и с
     вогнутыми помещениями, и с «дырами» — колоннами/шахтами);
  5. рисуется одна FilledRegion на камеру; в «Комментарии» пишется метка
     «<tag>|<id камеры>» — при повторном запуске прежние зоны выбранных
     камер на этом виде удаляются и создаются заново (идемпотентность);
  6. необязательно — концентрические дуги зон DORI (EN 62676-4:
     идентификация/распознавание/наблюдение/обнаружение) по горизонтальному
     разрешению матрицы.

Вторая кнопка панели — «Навести на помещение» (auto_aim_cameras): не
рисует зону, а НАВОДИТ камеру на её помещение: поворачивает по
биссектрисе помещения, подбирает фокусное (у вариофокальных) и наклон и
записывает их на камеру. Единственное место в модуле, которое пишет
параметры на камеру.

Транзакцию открывает скрипт кнопки, не этот модуль.
"""

import re
import math

from Autodesk.Revit.DB import (
    XYZ, Line, Arc, CurveLoop, Element, ElementId,
    FilteredElementCollector, RevitLinkInstance, BuiltInCategory,
    BuiltInParameter, StorageType, LocationPoint,
    FilledRegion, FilledRegionType, CurveElement,
    SpatialElementBoundaryOptions, SpatialElementBoundaryLocation,
    Color, GraphicsStyleType, Options, Solid, PlanarFace,
    View3D, ViewFamilyType, ViewFamily, ViewOrientation3D,
    ElementTransformUtils,
)
from Autodesk.Revit.UI.Selection import ISelectionFilter

try:
    from Autodesk.Revit.DB import ViewDetailLevel as _ViewDetailLevel
except Exception:
    _ViewDetailLevel = None

# Определение «это угловой параметр?» — модульный SpecTypeId (Revit 2021+),
# с откатом на устаревший enum ParameterType, если он ещё доступен. Оба —
# опциональны: при неудаче число трактуется по полю «Единицы углов».
try:
    from Autodesk.Revit.DB import SpecTypeId as _SpecTypeId
except Exception:
    _SpecTypeId = None

try:
    from Autodesk.Revit.DB import ParameterType as _ParameterType
except Exception:
    _ParameterType = None

# Для inspect_family_definition (диагностика CameraParamsCheck) — опять
# опциональные импорты: не должны ронять весь модуль, если класса нет в
# установленной версии Revit API, диагностика просто пропустит тот раздел.
try:
    from Autodesk.Revit.DB import Family, GenericForm, ReferencePlane, FamilyInstance
except Exception:
    Family = GenericForm = ReferencePlane = FamilyInstance = None

try:
    from Autodesk.Revit.DB import ConnectorElement
except Exception:
    ConnectorElement = None

from System.Collections.Generic import List

from lowlife.geometry import get_element_level

_FT_PER_MM = 1.0 / 304.8
_M_PER_FT = 0.3048


# ======================================================================
#  РАЗБОР ЗНАЧЕНИЙ НАСТРОЕК
# ======================================================================

def _as_bool(value, default=False):
    if value is None:
        return default
    s = unicode(value).strip().lower()
    if not s:
        return default
    return s in (u"да", u"1", u"true", u"yes", u"y", u"вкл", u"on", u"истина", u"+")


def _as_float(value, default=0.0):
    try:
        return float(unicode(value).strip().replace(u",", u"."))
    except Exception:
        return default


def _as_int(value, default=0):
    try:
        return int(round(_as_float(value, default)))
    except Exception:
        return default


def _split_alias_names(configured):
    """
    Настройка вида «Вращение (поворот)» либо «Вращение (поворот);УГО_Поворот»
    — список имён-кандидатов на одну роль через «;». Нужно потому, что
    разные семейства камер в одном проекте называют один и тот же по смыслу
    параметр по-разному (например, цилиндрическая — «Вращение (поворот)»,
    купольная — «УГО_Поворот»); настройка на весь проект одна, поэтому ей
    нужно уметь перечислить все варианты, а не только один.
    """
    if not configured:
        return []
    return [n.strip() for n in configured.split(u";") if n.strip()]


def _subcomponents(doc, el, depth=3):
    """Вложенные общие (shared) семейства экземпляра — рекурсивно, до depth
    уровней. У составной камеры «основание + поворотная камера» параметры
    поворота/наклона/оптики нередко принадлежат вложенной камере, а не
    основанию. Необщие вложенные семейства в проекте отдельными элементами
    не существуют — их параметры видны только через параметры основания."""
    out = []
    if depth <= 0 or el is None:
        return out
    try:
        ids = list(el.GetSubComponentIds())
    except Exception:
        return out
    for i in ids:
        sub = doc.GetElement(i)
        if sub is None:
            continue
        out.append(sub)
        out.extend(_subcomponents(doc, sub, depth - 1))
    return out


def _find_param(doc, el, name):
    """
    Параметр el по имени (или по «;»-списку имён-кандидатов, см.
    _split_alias_names — перебираются по порядку, первое совпадение
    побеждает): сначала параметр ЭКЗЕМПЛЯРА; если его нет или он пуст — тот
    же параметр у ТИПА (family symbol) этого экземпляра.

    Нужно потому, что у камер одни и те же характеристики на практике
    бывают то экземплярными, то параметрами типа: высота установки, угол
    наклона — обычно экземплярные (у каждой камеры своя точка и
    ориентация); угол обзора/дальность/матрица — часто параметр ТИПА
    (общая характеристика модели камеры), а фокусное расстояние — может
    быть и тем, и другим (у вариофокального объектива это, как правило,
    экземплярный параметр — его можно подстроить на месте для конкретной
    камеры того же типа). `Element.LookupParameter` смотрит только среди
    параметров экземпляра, поэтому параметр типа сам по себе не найдёт.

    Возвращает Parameter либо None. Если параметр экземпляра существует,
    но не заполнен, а на типе такого параметра нет вовсе — возвращает
    именно параметр экземпляра (без значения), чтобы вызывающий код мог
    отличить «нет такого параметра» от «параметр есть, но пуст».
    Если параметра нет ни на экземпляре, ни на типе — ищется во вложенных
    общих семействах (_subcomponents: составная камера «основание +
    поворотная камера»).
    """
    names = _split_alias_names(name)
    if not names:
        return None

    try:
        type_id = el.GetTypeId()
    except Exception:
        type_id = None
    type_el = None
    if type_id is not None and type_id != ElementId.InvalidElementId:
        try:
            type_el = doc.GetElement(type_id)
        except Exception:
            type_el = None

    fallback = None
    for candidate in names:
        inst_p = None
        try:
            inst_p = el.LookupParameter(candidate)
        except Exception:
            inst_p = None
        if inst_p is not None and inst_p.HasValue:
            return inst_p

        if type_el is not None:
            try:
                type_p = type_el.LookupParameter(candidate)
            except Exception:
                type_p = None
            if type_p is not None and type_p.HasValue:
                return type_p

        if fallback is None and inst_p is not None:
            fallback = inst_p

    if fallback is None:
        # у самой камеры (основания) нет — ищем во вложенных семействах
        for sub in _subcomponents(doc, el):
            p = _find_param_flat(doc, sub, names)
            if p is not None:
                return p

    return fallback


def _find_param_flat(doc, el, names):
    """Как _find_param, но без спуска во вложенные: экземпляр, потом тип;
    только параметр со значением."""
    try:
        type_el = doc.GetElement(el.GetTypeId())
    except Exception:
        type_el = None
    for candidate in names:
        for holder in (el, type_el):
            if holder is None:
                continue
            try:
                p = holder.LookupParameter(candidate)
            except Exception:
                p = None
            if p is not None and p.HasValue:
                return p
    return None


def _param_radians(param, unit_mode):
    """
    Значение углового параметра в радианах. unit_mode: «авто» — по типу
    параметра (ParameterType.Angle -> уже радианы, иначе трактуем число
    как градусы); «градусы» / «радианы» — принудительно.
    """
    v = param.AsDouble()
    mode = (unit_mode or u"авто").strip().lower()

    if mode.startswith(u"град"):
        return math.radians(v)
    if mode.startswith(u"рад"):
        return v

    # авто: значение уже в радианах, если параметр углового типа
    if _is_angle_param(param):
        return v
    return math.radians(v)


def _opt_param_radians(doc, el, name, unit_mode):
    """
    Угловой параметр по имени в радианах или None, если имя пустое / нет
    значения ни на экземпляре, ни на типе (см. _find_param).
    """
    p = _find_param(doc, el, name)
    if p is None or not p.HasValue:
        return None
    if p.StorageType == StorageType.Integer:
        # «Целое» — число градусов (или радиан, если так задано в настройках)
        v = float(p.AsInteger())
        mode = (unit_mode or u"авто").strip().lower()
        return v if mode.startswith(u"рад") else math.radians(v)
    if p.StorageType != StorageType.Double:
        return None
    return _param_radians(p, unit_mode)


# --- угол обзора из оптики (фокусное расстояние + матрица) --------------

# Оптический формат матрицы -> диагональ активной области, мм.
# «Дюймовое» обозначение задаёт именно диагональ (исторически неточно, но
# так его указывают производители матриц); ширина и высота получаются из
# диагонали и соотношения сторон кадра. У IP-камер видеонаблюдения кадр
# почти всегда 16:9 (1920×1080, 2560×1440, 3840×2160) — поэтому по
# умолчанию берётся 16:9, а не классическое 4:3: при той же диагонали
# кадр 16:9 шире на ~9 %, и угол обзора, посчитанный по 4:3, выходит
# заметно меньше паспортного (1/3", f=2.8: 81° вместо 86°). Для камер с
# кадром 4:3 (например 2048×1536) допишите соотношение: «1/3 4:3». При сомнениях задавайте размеры явно — «ШхВ».
_SENSOR_DIAGONALS = {
    u"1/4":   4.50,
    u"1/3.6": 5.00,
    u"1/3.2": 5.68,
    u"1/3":   6.00,
    u"1/2.9": 6.23,
    u"1/2.8": 6.46,
    u"1/2.7": 6.72,
    u"1/2.5": 7.18,
    u"1/2.3": 7.66,
    u"1/2":   8.00,
    u"1/1.9": 8.46,
    u"1/1.8": 8.93,
    u"1/1.7": 9.50,
    u"2/3":   11.00,
    u"1/1.2": 13.30,
    u"1":     16.00,
}

_DEFAULT_ASPECT = (16.0, 9.0)

_ASPECT_RE = re.compile(u"(\\d+(?:\\.\\d+)?)\\s*:\\s*(\\d+(?:\\.\\d+)?)")


def _sensor_from_diagonal(diag_mm, aspect):
    """(ширина, высота) активной области по диагонали и соотношению сторон."""
    aw, ah = aspect
    k = diag_mm / math.sqrt(aw * aw + ah * ah)
    return (aw * k, ah * k)


def _parse_sensor(text):
    """
    «Формат матрицы» -> (ширина_мм, высота_мм). Принимает:
      «1/2.8», «1/3"», «2/3»  — по таблице оптических форматов (диагональ),
                               кадр 16:9 (типично для IP-камер);
      «1/3 4:3», «1/2.8 16:9» — то же с явным соотношением сторон кадра;
      «5.37x4.04», «5,37*4,04» — явные размеры;
      «5.37» — только ширина (высота — по соотношению сторон, по
               умолчанию 16:9).
    None, если распознать не удалось.
    """
    if not text:
        return None
    s = unicode(text).strip()
    aspect = _DEFAULT_ASPECT
    m = _ASPECT_RE.search(s)
    if m:
        try:
            aw, ah = float(m.group(1)), float(m.group(2))
            if aw > 0 and ah > 0:
                aspect = (aw, ah)
        except Exception:
            pass
        s = s[:m.start()] + s[m.end():]
    s = s.replace(u",", u".").replace(u" ", u"").lower()
    s = s.strip(u'"').strip(u'\u201d')
    if not s:
        return None
    if s in _SENSOR_DIAGONALS:
        return _sensor_from_diagonal(_SENSOR_DIAGONALS[s], aspect)
    for sep in (u"x", u"\u00d7", u"*"):
        if sep in s:
            a, _, b = s.partition(sep)
            try:
                return (float(a), float(b))
            except Exception:
                return None
    try:
        w = float(s)
        return (w, w * aspect[1] / aspect[0])
    except Exception:
        return None


def _length_param_mm(param):
    """Значение параметра длины в миллиметрах. Тип «Длина» -> из футов в мм;
    иначе значение берётся как есть (считаем, что уже в мм)."""
    v = param.AsDouble()
    return v * 304.8 if _is_length_param(param) else v


def _spec_is(param, spec_attr, spec_key):
    """
    Тип данных параметра — spec_attr (SpecTypeId.Angle/Length)? Сравнение
    ForgeTypeId через «==» в IronPython ненадёжно (может сравнить ссылки,
    а не значения) — поэтому основной способ — по строке TypeId
    («autodesk.spec.aec:angle-2.0.0»), затем Equals, затем устаревший
    ParameterType (Revit до 2022).
    """
    try:
        dt = param.Definition.GetDataType()
        tid = (dt.TypeId or u"").lower()
        if tid.startswith(u"autodesk.spec.aec:" + spec_key + u"-") \
                or tid == u"autodesk.spec.aec:" + spec_key:
            return True
        if _SpecTypeId is not None and dt.Equals(getattr(_SpecTypeId, spec_attr)):
            return True
    except Exception:
        pass
    try:
        if _ParameterType is not None and \
                param.Definition.ParameterType == getattr(_ParameterType, spec_attr):
            return True
    except Exception:
        pass
    return False


def _is_length_param(param):
    return _spec_is(param, "Length", u"length")


def _is_angle_param(param):
    if _spec_is(param, "Angle", u"angle"):
        return True
    # последний шанс: Revit сам показывает значение в градусах
    try:
        vs = param.AsValueString() or u""
        return u"\u00b0" in vs
    except Exception:
        return False


def _mm_to_param_value(param, mm_value):
    """Обратное к _length_param_mm: мм -> значение, которое примет именно
    этот параметр (футы для типа «Длина», иначе как есть)."""
    return mm_value / 304.8 if _is_length_param(param) else mm_value


def _radians_to_param_value(param, radians_value, unit_mode):
    """Обратное к _param_radians: радианы -> значение, которое примет
    именно этот параметр (радианы для типа «Угол»; для «Число» — градусы
    или радианы по unit_mode, тем же правилом, что и при чтении)."""
    mode = (unit_mode or u"авто").strip().lower()
    if mode.startswith(u"град"):
        return math.degrees(radians_value)
    if mode.startswith(u"рад"):
        return radians_value
    return radians_value if _is_angle_param(param) else math.degrees(radians_value)


def _optical_fov(doc, fi, settings):
    """
    (hfov_rad, vfov_rad, reason). Горизонтальный и вертикальный угол
    обзора — ВСЕГДА расчётные величины, из фокусного расстояния объектива
    и размера матрицы (реальных физических характеристик камеры), а не
    вписанные вручную градусы, которые легко разойдутся с реальным
    объективом (особенно у вариофокального — угол обзора меняется вместе
    с фокусным расстоянием):

        hfov = 2·arctg(ширина_матрицы / (2·f))
        vfov = 2·arctg(высота_матрицы / (2·f))

    Если расчёт получился — reason is None, оба угла заполнены. Если
    нет — hfov/vfov оба None, reason — короткая причина для сообщения об
    ошибке (какого из двух входов не хватает).

    Фокусное расстояние ищется и на экземпляре, и на типе (_find_param) —
    у вариофокального объектива это обычно параметр экземпляра (разный у
    одинаковых по типу камер, сфокусировано по месту), у фикс-фокальных
    моделей нередко параметр типа. Формат матрицы — тем же способом из
    параметра `sensor_format_param_name` (текстовый параметр камеры),
    либо, если он не задан/не распознан на этой камере, общий текст
    `sensor_format` из настроек (одна матрица на все камеры).
    """
    fname = (settings.get("focal_length_param_name") or u"").strip()
    if not fname:
        return None, None, u"не задано имя параметра фокусного расстояния (настройки)"
    p = _find_param(doc, fi, fname)
    if p is None or not p.HasValue:
        return None, None, u"параметр «{}» (фокусное расстояние) не найден на камере".format(fname)
    if p.StorageType != StorageType.Double:
        return None, None, u"параметр «{}» не числовой".format(fname)
    f_mm = _length_param_mm(p)
    if not f_mm or f_mm <= 0.01:
        return None, None, u"фокусное расстояние = 0 (параметр «{}»)".format(fname)

    sensor = None
    sensor_pname = (settings.get("sensor_format_param_name") or u"").strip()
    if sensor_pname:
        sp = _find_param(doc, fi, sensor_pname)
        if sp is not None and sp.HasValue:
            text = sp.AsString() if sp.StorageType == StorageType.String else sp.AsValueString()
            sensor = _parse_sensor(text)
    if sensor is None:
        sensor = _parse_sensor(settings.get("sensor_format"))
    if sensor is None:
        return None, None, u"формат матрицы не задан или не распознан (ни на камере, ни в настройках)"
    w_mm, h_mm = sensor

    hfov = 2.0 * math.atan(w_mm / (2.0 * f_mm))
    vfov = 2.0 * math.atan(h_mm / (2.0 * f_mm)) if (h_mm and h_mm > 0) else None
    return hfov, vfov, None


# ======================================================================
#  ДИАГНОСТИКА: КАКИЕ ПАРАМЕТРЫ ЕСТЬ И КАКИЕ ПОДХОДЯТ ПОД РОЛИ СОТ
# ======================================================================
#
# Роль -> (ключ в settings, подпись, подходящие «типы данных» параметра,
# обязательна ли роль, обязан ли параметр быть параметром ЭКЗЕМПЛЯРА).
# Порядок и роли соответствуют полям ①-настроек (TEXT_FIELDS) и таблице
# параметров в docs/camera-fov.md — держите их синхронно при изменении.
_ROLE_SPECS = [
    ("focal_length_param_name", u"Фокусное расстояние",
     (u"length", u"number"), True, False),
    ("sensor_format_param_name", u"Формат матрицы (текст)",
     (u"text",), False, False),
    ("camera_h_res_param_name", u"Горизонтальное разрешение, пикс",
     (u"integer", u"number", u"text"), False, False),
    ("distance_param_name", u"Дальность",
     (u"length",), True, False),
    ("height_param_name", u"Высота установки",
     (u"length",), False, False),
    ("tilt_param_name", u"Наклон оптической оси вниз",
     (u"angle", u"number"), False, True),
    ("rotation_param_name", u"Поворот камеры (внутри семейства)",
     (u"angle", u"number", u"integer"), False, False),
]

# Публичная — используется CameraParamsCheck.pushbutton для отображения
# «kind» из _ROLE_SPECS/diagnose_camera_params человеку.
PARAM_KIND_RU = {
    u"length": u"Длина", u"angle": u"Угол", u"text": u"Текст",
    u"number": u"Число", u"integer": u"Целое число", u"yesno": u"Да/Нет",
    u"elementid": u"ссылка на элемент", u"other": u"другое",
}


def _param_kind(param):
    """Грубая классификация типа данных параметра для сопоставления с
    ролями СОТ (см. _ROLE_SPECS): length / angle / text / number /
    integer / yesno / elementid / other."""
    if _is_length_param(param):
        return u"length"
    if _is_angle_param(param):
        return u"angle"
    st = param.StorageType
    if st == StorageType.String:
        return u"text"
    if st == StorageType.ElementId:
        return u"elementid"
    if st == StorageType.Integer:
        try:
            if _ParameterType is not None and param.Definition.ParameterType == _ParameterType.YesNo:
                return u"yesno"
        except Exception:
            pass
        return u"integer"
    if st == StorageType.Double:
        return u"number"
    return u"other"


def _param_value_text(param):
    """Значение параметра как отображаемая строка (с единицами, где Revit
    их даёт) — для диагностического отчёта, не для расчётов."""
    try:
        vs = param.AsValueString()
        if vs:
            return vs
    except Exception:
        pass
    try:
        st = param.StorageType
        if st == StorageType.String:
            return param.AsString() or u""
        if st == StorageType.Double:
            return unicode(param.AsDouble())
        if st == StorageType.Integer:
            return unicode(param.AsInteger())
        if st == StorageType.ElementId:
            eid = param.AsElementId()
            return unicode(eid.IntegerValue) if eid else u""
    except Exception:
        pass
    return u""


# getattr, не StorageType.None — "None" не резервированное слово в этом
# Python 2, но так надёжнее и не смущает беглым чтением.
_STORAGE_TYPE_NONE = getattr(StorageType, "None")


def _list_params(el, level_label):
    """[(имя, kind, level_label, value_text, has_value), ...] по всем
    параметрам el. Параметры StorageType.None пропускаются — это
    служебные пустышки (например, заголовки групп в UI), не настоящие
    значения."""
    out = []
    if el is None:
        return out
    try:
        params = list(el.Parameters)
    except Exception:
        params = []
    for p in params:
        try:
            if p.StorageType == _STORAGE_TYPE_NONE:
                continue
            name = p.Definition.Name
        except Exception:
            continue
        has_value = bool(p.HasValue)
        out.append((
            name, _param_kind(p), level_label,
            _param_value_text(p) if has_value else u"",
            has_value,
        ))
    return out


def diagnose_camera_params(doc, el, settings):
    """
    Собирает все параметры элемента el (экземпляра и его типа) и для
    каждой роли СОТ (_ROLE_SPECS) проверяет: настроено ли имя параметра в
    settings, есть ли такой параметр на элементе (экземпляр/тип), подходит
    ли его тип данных под роль, и что ещё на элементе того же типа данных
    можно было бы использовать вместо него. Только читает — ничего не
    меняет ни в settings, ни в модели.

    Возвращает dict:
      family_name, type_name, category_name, category_ok (bool — входит ли
      категория элемента в settings["camera_categories"]),
      instance_params, type_params — списки как в _list_params,
      roles — список dict-ов на каждую роль:
        key, label, expected_kinds, required, must_be_instance,
        configured_name, status, found (кортеж как в _list_params или
        None), candidates (список кортежей-кандидатов того же типа данных).

      status: "not_configured" (имя не задано в настройках),
        "not_found" (имя задано, такого параметра нет ни на экземпляре, ни
        на типе), "wrong_kind" (параметр найден, но не тот тип данных),
        "tilt_not_instance" (роль требует параметр экземпляра, а найден —
        параметр типа), "empty" (тип данных верный, но значение не
        заполнено), "ok" (всё в порядке).
    """
    type_el = None
    try:
        type_id = el.GetTypeId()
        if type_id is not None and type_id != ElementId.InvalidElementId:
            type_el = doc.GetElement(type_id)
    except Exception:
        type_el = None

    inst_params = _list_params(el, u"экземпляр")
    type_params = _list_params(type_el, u"тип")

    # вложенные общие семейства (составная камера «основание + камера»)
    nested = []   # [(sub, sub_type, family_label)]
    nested_params = []
    for sub in _subcomponents(doc, el):
        try:
            sub_type = doc.GetElement(sub.GetTypeId())
        except Exception:
            sub_type = None
        try:
            fam = sub_type.FamilyName if sub_type is not None else _safe_name(sub)
        except Exception:
            fam = u"?"
        nested.append((sub, sub_type, fam))
        nested_params.extend(_list_params(sub, u"вложенное «{}»".format(fam)))
        nested_params.extend(_list_params(sub_type, u"тип вложенного «{}»".format(fam)))
    all_params = inst_params + type_params + nested_params

    try:
        family_name = type_el.FamilyName if type_el is not None else u""
    except Exception:
        family_name = u""
    try:
        type_name = Element.Name.GetValue(type_el) if type_el is not None else u""
    except Exception:
        type_name = u""
    try:
        category_name = el.Category.Name if el.Category is not None else u""
    except Exception:
        category_name = u""

    cat_ids = resolve_category_ids(
        doc, settings.get("camera_categories") or u"OST_SecurityDevices"
    )
    try:
        category_ok = el.Category is not None and el.Category.Id.IntegerValue in cat_ids
    except Exception:
        category_ok = True

    roles = []
    for key, label, expected_kinds, required, must_be_instance in _ROLE_SPECS:
        configured_name = (settings.get(key) or u"").strip() or None
        candidate_names = _split_alias_names(configured_name)
        found_entry = None
        matched_name = None

        if not candidate_names:
            status = u"not_configured"
        else:
            chosen, level = None, None
            for cname in candidate_names:
                inst_p = None
                try:
                    inst_p = el.LookupParameter(cname)
                except Exception:
                    inst_p = None
                type_p = None
                if type_el is not None:
                    try:
                        type_p = type_el.LookupParameter(cname)
                    except Exception:
                        type_p = None

                if inst_p is not None:
                    chosen, level, matched_name = inst_p, u"экземпляр", cname
                    break
                elif type_p is not None:
                    chosen, level, matched_name = type_p, u"тип", cname
                    break

            if chosen is None:
                for sub, sub_type, fam in nested:
                    for cname in candidate_names:
                        for holder, lvl in ((sub, u"вложенное «{}»".format(fam)),
                                            (sub_type, u"тип вложенного «{}»".format(fam))):
                            if holder is None:
                                continue
                            try:
                                p = holder.LookupParameter(cname)
                            except Exception:
                                p = None
                            if p is not None:
                                chosen, level, matched_name = p, lvl, cname
                                break
                        if chosen is not None:
                            break
                    if chosen is not None:
                        break

            if chosen is None:
                status = u"not_found"
            else:
                kind = _param_kind(chosen)
                has_value = bool(chosen.HasValue)
                found_entry = (
                    matched_name, kind, level,
                    _param_value_text(chosen) if has_value else u"",
                    has_value,
                )
                if kind not in expected_kinds:
                    status = u"wrong_kind"
                elif must_be_instance and level.startswith(u"тип"):
                    status = u"tilt_not_instance"
                elif not has_value:
                    status = u"empty"
                else:
                    status = u"ok"

        seen = set()
        candidates = []
        for name, kind, level, value_text, has_value in all_params:
            if kind not in expected_kinds:
                continue
            if matched_name and name == matched_name and level == (
                found_entry[2] if found_entry else None
            ):
                continue
            dedup_key = (name, level)
            if dedup_key in seen:
                continue
            seen.add(dedup_key)
            candidates.append((name, kind, level, value_text, has_value))

        roles.append({
            u"key": key, u"label": label, u"expected_kinds": expected_kinds,
            u"required": required, u"must_be_instance": must_be_instance,
            u"configured_name": configured_name, u"status": status,
            u"found": found_entry, u"candidates": candidates,
        })

    return {
        u"family_name": family_name, u"type_name": type_name,
        u"category_name": category_name, u"category_ok": category_ok,
        u"instance_params": inst_params, u"type_params": type_params,
        u"nested_params": nested_params,
        u"roles": roles,
        u"geometry": describe_camera_geometry(doc, el, settings),
        u"family_def": inspect_family_definition(doc, el),
    }


# ======================================================================
#  ГЕОМЕТРИЯ КАМЕРЫ
# ======================================================================

def _horiz(v):
    """Горизонтальная проекция вектора как XYZ, либо None, если она почти нулевая."""
    if v is None:
        return None
    try:
        h = XYZ(v.X, v.Y, 0.0)
    except Exception:
        return None
    return h if h.GetLength() > 1e-6 else None


def _look_direction(fi, offset_deg):
    """
    (горизонтальный единичный вектор «куда смотрит» камера, пояснение).
    Источники по очереди: FacingOrientation, BasisY / BasisX её Transform,
    HandOrientation. offset_deg — фиксированный доворот против часовой
    стрелки. Первый элемент None, если направление определить не удалось
    (тогда во втором — что перебрали, для диагностики).
    """
    tried = []

    src = None
    try:
        f = fi.FacingOrientation
        tried.append(u"Facing=({:.2f},{:.2f},{:.2f})".format(f.X, f.Y, f.Z))
        src = _horiz(f)
        if src is not None:
            note = u"FacingOrientation"
    except Exception as ex:
        tried.append(u"Facing!{}".format(ex))

    if src is None:
        try:
            t = fi.GetTransform()
            tried.append(u"BasisY=({:.2f},{:.2f},{:.2f})".format(
                t.BasisY.X, t.BasisY.Y, t.BasisY.Z))
            src = _horiz(t.BasisY)
            if src is not None:
                note = u"Transform.BasisY"
            if src is None:
                tried.append(u"BasisX=({:.2f},{:.2f},{:.2f})".format(
                    t.BasisX.X, t.BasisX.Y, t.BasisX.Z))
                src = _horiz(t.BasisX)
                if src is not None:
                    note = u"Transform.BasisX"
        except Exception as ex:
            tried.append(u"Transform!{}".format(ex))

    if src is None:
        try:
            hnd = fi.HandOrientation
            tried.append(u"Hand=({:.2f},{:.2f},{:.2f})".format(hnd.X, hnd.Y, hnd.Z))
            # «взгляд» перпендикулярен руке в плане: повернём на -90°
            hh = _horiz(hnd)
            if hh is not None:
                hh = hh.Normalize()
                src = XYZ(hh.Y, -hh.X, 0.0)
                note = u"HandOrientation⟂"
        except Exception as ex:
            tried.append(u"Hand!{}".format(ex))

    if src is None:
        return None, u" / ".join(tried)

    d = src.Normalize()
    if offset_deg:
        a = math.radians(offset_deg)
        ca, sa = math.cos(a), math.sin(a)
        d = XYZ(d.X * ca - d.Y * sa, d.X * sa + d.Y * ca, 0.0)

    return d, note


_RANGE_RE = re.compile(
    u"^\\s*(-?\\d+(?:[.,]\\d+)?)\\s*(?:\\.\\.|\u2026|-|\u2013|\u2014|;|/|\\s)\\s*(-?\\d+(?:[.,]\\d+)?)\\s*\u00b0?\\s*$")


def _parse_range_deg(text):
    """«0-180», «0..180», «-90;90» -> (мин_рад, макс_рад); пусто/не
    распознано -> None (поворот без ограничений)."""
    if not text:
        return None
    # дефис между числами — разделитель, а не минус второго числа
    m = _RANGE_RE.match(unicode(text))
    if not m:
        return None
    try:
        lo = float(m.group(1).replace(u",", u"."))
        hi = float(m.group(2).replace(u",", u"."))
    except Exception:
        return None
    if hi < lo:
        lo, hi = hi, lo
    if hi - lo >= 360.0 - 1e-6:
        return None
    return math.radians(lo), math.radians(hi)


def _rotation_spec(s):
    """
    Шкала параметра поворота камеры (rotation_param_name):
    (ноль_рад, знак, диапазон_или_None). Направление взгляда
        азимут = «вперёд» семейства + ноль + знак · значение_параметра
    где «вперёд» — FacingOrientation (+ direction_offset_deg), ноль —
    rotation_zero_deg (куда смотрит камера при значении 0, против часовой
    от «вперёд»), знак = −1, если параметр растёт по часовой
    (rotation_clockwise). Пример — поворотная камера на настенном
    основании (на плане, стена снизу): 0 — смотрит вправо вдоль стены,
    90 — от стены, 180 — влево: ноль = −90°, против часовой, диапазон
    0–180 (зеркальная шкала «0 — влево, 180 — вправо»: ноль = 90°, по
    часовой).
    """
    zero = math.radians(_as_float(s.get("rotation_zero_deg"), 0.0))
    sign = -1.0 if _as_bool(s.get("rotation_clockwise"), False) else 1.0
    return zero, sign, _parse_range_deg(s.get("rotation_range_deg"))


def _camera_azimuth(doc, cam, s, unit_mode):
    """
    (азимут_рад, пояснение, «вперёд»_рад) — куда смотрит камера в плане:
    направление семейства (_look_direction + direction_offset_deg) плюс
    поворот параметром rotation_param_name по шкале _rotation_spec.
    Азимут None, если направление определить не удалось (в пояснении —
    что перебрали). Общая для «Зон обзора», автонаведения, вида с камеры
    и диагностики — чтобы все они смотрели в одну сторону.
    """
    offset_deg = _as_float(s.get("direction_offset_deg"), 0.0)
    d, note = _look_direction(cam, offset_deg)
    if d is None:
        return None, note, None
    forward = math.atan2(d.Y, d.X)
    rot_name = (s.get("rotation_param_name") or u"").strip()
    rot = _opt_param_radians(doc, cam, rot_name, unit_mode)
    if rot is None:
        if rot_name:
            note = u"{}; параметр поворота «{}» не найден ни на камере, ни на её " \
                   u"типе, ни во вложенных семействах — поворот не учтён".format(
                       note, rot_name)
        return forward, note, forward
    zero, sign, _rng = _rotation_spec(s)
    az = forward + zero + sign * rot
    return az, u"{} + поворот {:.1f}°".format(note, math.degrees(rot)), forward


def _rotation_value_for_azimuth(az, forward, s):
    """Обратное к _camera_azimuth: значение параметра поворота (рад),
    при котором камера смотрит в азимут az, приведённое в диапазон
    rotation_range_deg (если задан; иначе в (−180°, 180°]). Второй
    элемент — False, если az в этот диапазон не попадает."""
    zero, sign, rng = _rotation_spec(s)
    rot = sign * (az - forward - zero)
    if rng is None:
        return _norm_angle(rot), True
    lo, hi = rng
    rot = lo + math.fmod(math.fmod(rot - lo, 2.0 * math.pi) + 2.0 * math.pi, 2.0 * math.pi)
    return rot, rot <= hi + 1e-9


def _norm_angle(a):
    """Угол в диапазон (−π, π]."""
    a = math.fmod(a, 2.0 * math.pi)
    if a <= -math.pi:
        a += 2.0 * math.pi
    elif a > math.pi:
        a -= 2.0 * math.pi
    return a


def _mounting_height_ft(doc, fi, view, height_param_name):
    """
    Высота установки камеры над её уровнем, футы. Сначала — из параметра
    height_param_name (если задан и положителен); иначе — отметка точки
    вставки минус отметка связанного уровня (или GenLevel вида). None,
    если высоту не определить или она неположительна.
    """
    name = (height_param_name or u"").strip()
    if name:
        p = _find_param(doc, fi, name)
        if p is not None and p.HasValue and p.StorageType == StorageType.Double:
            h = p.AsDouble()
            if h > 0:
                return h

    try:
        pt = fi.Location.Point
    except Exception:
        return None

    base_z = None
    lvl = get_element_level(doc, fi)
    if lvl is not None:
        try:
            base_z = lvl.Elevation
        except Exception:
            base_z = None
    if base_z is None:
        gen = getattr(view, "GenLevel", None)
        if gen is not None:
            try:
                base_z = gen.Elevation
            except Exception:
                base_z = None
    if base_z is None:
        return None

    h = pt.Z - base_z
    return h if h > 0 else None


def _vec_text(v):
    if v is None:
        return u"—"
    return u"({:.3f}, {:.3f}, {:.3f})".format(v.X, v.Y, v.Z)


def _safe_name(el):
    """Element.Name.GetValue вместо el.Name — на Family/FamilySymbol и
    некоторых элементах семейства el.Name кидает ошибку неоднозначного
    связывания в IronPython (тот же приём, что _safe_element_name в
    scs_settings.py)."""
    if el is None:
        return u"—"
    try:
        return Element.Name.GetValue(el)
    except Exception:
        try:
            return unicode(el.Name)
        except Exception:
            return u"—"


def describe_camera_geometry(doc, el, settings):
    """
    Геометрия и ориентация КОНКРЕТНОГО экземпляра камеры в проекте — то,
    что реально использует расчёт «Зон обзора»/«Навести на помещение»
    (_look_direction + rotation_param_name + direction_offset_deg,
    _mounting_height_ft), плюс справочная информация для диагностики
    (уровень/хост, отражение, тип размещения семейства). Про внутреннюю
    структуру самого файла семейства (типы/формулы/геометрию форм) — см.
    inspect_family_definition, это другое: там семейство как файл, здесь —
    как этот экземпляр стоит и развёрнут в ТЕКУЩЕМ проекте.

    Только читает, ничего не пишет. Возвращает dict — все поля лучше
    выводить через str()/готовые *_text значения, часть может быть None
    (нет такого свойства у этого элемента / упало исключение).
    """
    info = {}

    loc = None
    try:
        loc = el.Location
    except Exception:
        loc = None
    if isinstance(loc, LocationPoint):
        p = loc.Point
        info[u"location_mm"] = (p.X * 304.8, p.Y * 304.8, p.Z * 304.8)
    else:
        info[u"location_mm"] = None

    level = get_element_level(doc, el)
    info[u"level_name"] = _safe_name(level) if level is not None else u"—"

    host = None
    try:
        host = el.Host
    except Exception:
        host = None
    if host is not None:
        try:
            host_cat = host.Category.Name if host.Category is not None else u""
        except Exception:
            host_cat = u""
        info[u"host_label"] = u"{} (id {})".format(host_cat or u"?", host.Id.IntegerValue)
    else:
        info[u"host_label"] = u"нет (не хостовый экземпляр)"

    try:
        info[u"placement_type"] = unicode(el.Symbol.Family.FamilyPlacementType)
    except Exception:
        info[u"placement_type"] = u"—"

    for attr, key in ((u"Mirrored", u"mirrored"), (u"FacingFlipped", u"facing_flipped"),
                       (u"HandFlipped", u"hand_flipped")):
        try:
            info[key] = bool(getattr(el, attr))
        except Exception:
            info[key] = None

    try:
        f = el.FacingOrientation
        info[u"facing_orientation_text"] = _vec_text(f)
        info[u"facing_azimuth_deg"] = math.degrees(math.atan2(f.Y, f.X)) % 360.0
    except Exception:
        info[u"facing_orientation_text"] = u"—"
        info[u"facing_azimuth_deg"] = None

    try:
        info[u"hand_orientation_text"] = _vec_text(el.HandOrientation)
    except Exception:
        info[u"hand_orientation_text"] = u"—"

    try:
        t = el.GetTransform()
        info[u"basis_y_text"] = _vec_text(t.BasisY)
        info[u"basis_x_text"] = _vec_text(t.BasisX)
    except Exception:
        info[u"basis_y_text"] = info[u"basis_x_text"] = u"—"

    # то же направление и та же итоговая формула, что реально использует
    # построение зоны (_one_camera) — чтобы диагностика не разошлась с
    # тем, что на самом деле рисуется
    unit_mode = settings.get(u"angle_unit") or u"авто"
    base, dir_note, _fwd = _camera_azimuth(doc, el, settings, unit_mode)
    if base is not None:
        info[u"used_direction_source"] = dir_note
        info[u"used_azimuth_deg"] = math.degrees(base) % 360.0
    else:
        info[u"used_direction_source"] = dir_note
        info[u"used_azimuth_deg"] = None

    return info


# ======================================================================
#  РАЗБОР СЕМЕЙСТВА (структура .rfa, не экземпляра в проекте)
# ======================================================================

def inspect_family_definition(doc, el):
    """
    Открывает семейство выбранного экземпляра на редактирование
    (Document.EditFamily) и читает его внутреннюю структуру: все
    типоразмеры со значениями каждого параметра, формулы параметров,
    вложенные семейства (имя, категория, сколько экземпляров), формы
    (выдавливание/тело вращения/сдвиг и т.п. — тело или вырез), опорные
    плоскости, разъёмы (для устройств с электрическим/сетевым
    подключением). Семейство закрывается БЕЗ сохранения сразу после
    чтения — fam_doc не меняется ничем, кроме чтения.

    Это про структуру самого файла семейства — что чем в нём задано; про
    то, как уже размещённый экземпляр стоит и развёрнут в проекте, см.
    describe_camera_geometry.

    ВНИМАНИЕ: это открывает реальный документ семейства в Revit (как
    двойной клик «Редактировать семейство»), просто без показа окна
    пользователю, и сразу закрывает его. Не вызывайте это внутри
    транзакции документа проекта. Если семейство уже открыто на
    редактирование в другом окне — Revit это не даст сделать, см. поле
    editable/error в результате.

    Возвращает dict: editable (bool), error (строка причины неудачи, или
    None), family_name, category_name, placement_type, types (список
    dict: name, params — список кортежей (имя_параметра, формула_или_None,
    текст_значения)), nested_families (список dict: name, category,
    count), forms (список dict: name, kind — "тело"/"вырез"/"?"),
    reference_planes (список имён), connectors (список dict: domain, id).
    """
    result = {
        u"editable": False, u"error": None, u"family_name": u"",
        u"category_name": u"", u"placement_type": u"",
        u"types": [], u"nested_families": [], u"forms": [],
        u"reference_planes": [], u"connectors": [],
    }

    if Family is None:
        result[u"error"] = u"класс Family недоступен в этой версии Revit API"
        return result

    try:
        family = el.Symbol.Family
    except Exception as ex:
        result[u"error"] = u"у элемента нет типа/семейства: {}".format(ex)
        return result

    result[u"family_name"] = _safe_name(family)
    try:
        result[u"category_name"] = family.FamilyCategory.Name if family.FamilyCategory else u""
    except Exception:
        pass
    try:
        result[u"placement_type"] = unicode(family.FamilyPlacementType)
    except Exception:
        pass

    try:
        editable = bool(family.IsEditable)
    except Exception:
        editable = False
    result[u"editable"] = editable
    if not editable:
        result[u"error"] = (
            u"Revit не даёт открыть это семейство на редактирование в "
            u"текущей сессии (IsEditable=False) — часто потому, что оно "
            u"уже открыто на редактирование в другом окне, либо это "
            u"системное семейство"
        )
        return result

    try:
        fam_doc = doc.EditFamily(family)
    except Exception as ex:
        result[u"error"] = u"doc.EditFamily упал: {}".format(ex)
        return result

    try:
        fm = fam_doc.FamilyManager
        fam_params = list(fm.Parameters)
        for ftype in fm.Types:
            try:
                type_name = ftype.Name
            except Exception:
                type_name = u"?"
            row = {u"name": type_name, u"params": []}
            for fp in fam_params:
                try:
                    pname = fp.Definition.Name
                except Exception:
                    pname = u"?"
                try:
                    formula = fp.Formula
                except Exception:
                    formula = None
                value_text = u""
                try:
                    vs = ftype.AsValueString(fp)
                    if vs:
                        value_text = vs
                except Exception:
                    pass
                if not value_text:
                    try:
                        st = fp.StorageType
                        if st == StorageType.String:
                            value_text = ftype.AsString(fp) or u""
                        elif st == StorageType.Double:
                            value_text = unicode(ftype.AsDouble(fp))
                        elif st == StorageType.Integer:
                            value_text = unicode(ftype.AsInteger(fp))
                    except Exception:
                        pass
                row[u"params"].append((pname, formula, value_text))
            result[u"types"].append(row)

        if GenericForm is not None:
            for f in FilteredElementCollector(fam_doc).OfClass(GenericForm).ToElements():
                try:
                    is_solid = bool(f.IsSolid)
                    kind = u"тело" if is_solid else u"вырез"
                except Exception:
                    kind = u"?"
                result[u"forms"].append({u"name": _safe_name(f), u"kind": kind})

        if ReferencePlane is not None:
            for rp in FilteredElementCollector(fam_doc).OfClass(ReferencePlane).ToElements():
                result[u"reference_planes"].append(_safe_name(rp))

        if FamilyInstance is not None:
            nested_counts = {}
            for ni in FilteredElementCollector(fam_doc).OfClass(FamilyInstance).ToElements():
                try:
                    nfam_name = _safe_name(ni.Symbol.Family)
                    ncat = ni.Category.Name if ni.Category is not None else u""
                except Exception:
                    nfam_name, ncat = u"?", u""
                key = (nfam_name, ncat)
                nested_counts[key] = nested_counts.get(key, 0) + 1
            for (nfam_name, ncat), count in nested_counts.items():
                result[u"nested_families"].append({
                    u"name": nfam_name, u"category": ncat, u"count": count
                })

        if ConnectorElement is not None:
            try:
                for ce in FilteredElementCollector(fam_doc).OfClass(ConnectorElement).ToElements():
                    try:
                        domain = unicode(ce.Domain)
                    except Exception:
                        domain = u"?"
                    result[u"connectors"].append({u"domain": domain, u"id": ce.Id.IntegerValue})
            except Exception:
                pass

    except Exception as ex:
        result[u"error"] = u"ошибка при чтении семейства: {}".format(ex)
    finally:
        try:
            fam_doc.Close(False)
        except Exception:
            pass

    return result


def _near_far_radius(h_ft, tilt_rad, vfov_rad, max_r):
    """
    (near_r, far_r) — радиусы ближней и дальней границы зоны на плоскости
    расчёта, футы. Если высоты/наклона/верт.угла нет — плоский сектор
    (0, max_r), как в исходном скрипте.
    """
    if (h_ft is None or h_ft <= 0.1
            or tilt_rad is None or vfov_rad is None or vfov_rad <= 1e-4):
        return 0.0, max_r

    half_v = vfov_rad / 2.0
    bottom = tilt_rad + half_v      # нижний луч кадра -> ближняя кромка
    top = tilt_rad - half_v         # верхний луч кадра -> дальняя кромка

    near = 0.0
    if bottom > 1e-3:
        near = h_ft / math.tan(bottom)

    far = max_r
    if top > 1e-3:
        far = min(max_r, h_ft / math.tan(top))

    near = max(0.0, min(near, max_r))
    if far <= near:
        far = max_r
    return near, far


# ======================================================================
#  ОБЩАЯ 3D-ГЕОМЕТРИЯ: ГОРИЗОНТАЛЬНОЕ СЕЧЕНИЕ ТЕЛА ЭЛЕМЕНТА
# ======================================================================
#
# Резерв для помещений, чей контур GetBoundarySegments не отдаёт
# (повреждённая/разомкнутая граница) — берём уже готовое тело, которое
# Revit сам считает для площади/объёма, и вырезаем его нижнюю
# горизонтальную грань. Работает для любой формы (вогнутой, с несколькими
# контурами, с дугами) без ручной геометрии.
#
# Тени от колонн отдельно не считаются: колонна с отделкой, отмеченной
# «граница помещения» (обычная практика в АР), уже вырезает свой контур
# внутри границы самого Room — GetBoundarySegments отдаёт его как
# дополнительный внутренний контур («дыру»), см. room_rings_for_point.

def _geom_options():
    o = Options()
    try:
        o.ComputeReferences = False
    except Exception:
        pass
    try:
        o.IncludeNonVisibleObjects = False
    except Exception:
        pass
    if _ViewDetailLevel is not None:
        try:
            o.DetailLevel = _ViewDetailLevel.Fine
        except Exception:
            pass
    return o


def _element_solids(el, opts):
    """Список Solid элемента (в его собственных координатах), включая
    вложенную геометрию семейства (GeometryInstance). Тела с нулевым
    объёмом (грани/кромки-заглушки) отбрасываются."""
    try:
        geo = el.get_Geometry(opts)
    except Exception:
        geo = None
    if geo is None:
        return []

    out = []
    for g in geo:
        try:
            if isinstance(g, Solid):
                if g.Volume > 1e-6:
                    out.append(g)
                continue
        except Exception:
            pass
        inst_geo = None
        try:
            inst_geo = g.GetInstanceGeometry()   # GeometryInstance (семейство)
        except Exception:
            inst_geo = None
        if inst_geo is None:
            continue
        for g2 in inst_geo:
            try:
                if isinstance(g2, Solid) and g2.Volume > 1e-6:
                    out.append(g2)
            except Exception:
                continue
    return out


def _horizontal_face_rings(solid, tf):
    """
    [[XYZ,...], ...] — контуры нижней горизонтальной плоской грани тела
    (в координатах ХОСТА, Z=0), т.е. его горизонтальное сечение/подошва.
    Для призматических объёмов (помещение, колонна постоянного сечения)
    это и есть их контур в плане. None, если такой грани нет.
    """
    best_face = None
    best_z = None
    try:
        faces = solid.Faces
    except Exception:
        return None

    for face in faces:
        try:
            if not isinstance(face, PlanarFace):
                continue
            n = face.FaceNormal
            if abs(n.Z) < 0.98:
                continue
            z = face.Origin.Z
        except Exception:
            continue
        if best_z is None or z < best_z:
            best_z = z
            best_face = face

    if best_face is None:
        return None

    rings = []
    try:
        loops = best_face.GetEdgesAsCurveLoops()
    except Exception:
        return None
    for loop in loops:
        pts = []
        for curve in loop:
            try:
                tess = curve.CreateTransformed(tf).Tessellate()
            except Exception:
                continue
            for i in range(tess.Count - 1):
                q = tess[i]
                pts.append(XYZ(q.X, q.Y, 0.0))
        if len(pts) >= 3:
            rings.append(pts)
    return rings or None


# ======================================================================
#  ПОМЕЩЕНИЕ ИЗ СВЯЗИ  ->  КОНТУР В КООРДИНАТАХ ХОСТА
# ======================================================================

_ROOM_TOLERANCE_FT = 90.0 * _FT_PER_MM   # как в room_info.py: точка часто «в стене»
_ROOM_Z_PAD_FT = 1.0                     # запас по высоте при выборе этажа


def _boundary_options(mode):
    opt = SpatialElementBoundaryOptions()
    if mode and unicode(mode).strip().lower().startswith(u"центр"):
        opt.SpatialElementBoundaryLocation = SpatialElementBoundaryLocation.Center
    else:
        opt.SpatialElementBoundaryLocation = SpatialElementBoundaryLocation.Finish
    return opt


def _room_solid_rings(room, tf):
    """Резерв для _room_boundary_rings: сечение тела помещения, которое
    Revit сам строит для площади/объёма. None, если у помещения нет
    вычисленной геометрии (совсем не ограничено)."""
    for solid in _element_solids(room, _geom_options()):
        rings = _horizontal_face_rings(solid, tf)
        if rings:
            return rings
    return None


def _room_boundary_rings(room, opt, tf):
    """[[XYZ,...], ...] — контуры Room в координатах ХОСТА, Z=0. Первый —
    внешний, остальные — «дыры». Основной путь — GetBoundarySegments;
    если он не дал ни одного пригодного контура (разомкнутая/повреждённая
    граница) — резерв _room_solid_rings. None, если не получилось ни так,
    ни так (помещение действительно не ограничено)."""
    try:
        loops = room.GetBoundarySegments(opt)
    except Exception:
        loops = None
    if not loops:
        return _room_solid_rings(room, tf)

    rings = []
    for loop in loops:
        pts = []
        for seg in loop:
            crv = None
            try:
                crv = seg.GetCurve()
            except Exception:
                try:
                    crv = seg.Curve            # старое имя (Revit < 2016)
                except Exception:
                    crv = None
            if crv is None:
                continue
            try:
                tess = crv.CreateTransformed(tf).Tessellate()
            except Exception:
                continue
            for i in range(tess.Count - 1):
                q = tess[i]
                pts.append(XYZ(q.X, q.Y, 0.0))
        if len(pts) >= 3:
            rings.append(pts)
    return rings or _room_solid_rings(room, tf)


def _point_in_ring(px, py, ring):
    inside = False
    n = len(ring)
    j = n - 1
    for i in range(n):
        xi, yi = ring[i].X, ring[i].Y
        xj, yj = ring[j].X, ring[j].Y
        if ((yi > py) != (yj > py)) and \
           (px < (xj - xi) * (py - yi) / (yj - yi) + xi):
            inside = not inside
        j = i
    return inside


def _dist_point_to_rings(px, py, rings):
    best = None
    for ring in rings:
        n = len(ring)
        for i in range(n):
            a = ring[i]
            b = ring[(i + 1) % n]
            ex, ey = b.X - a.X, b.Y - a.Y
            seg2 = ex * ex + ey * ey
            if seg2 < 1e-12:
                continue
            t = ((px - a.X) * ex + (py - a.Y) * ey) / seg2
            t = max(0.0, min(1.0, t))
            dx = px - (a.X + t * ex)
            dy = py - (a.Y + t * ey)
            d = math.sqrt(dx * dx + dy * dy)
            if best is None or d < best:
                best = d
    return best


def room_rings_for_point(doc, host_point, boundary_mode):
    """
    (контуры помещения в координатах ХОСТА [Z=0], пояснение).

    host_point — точка камеры С РЕАЛЬНОЙ ОТМЕТКОЙ (не сплющенная в Z=0).
    Помещение ищется во всех загруженных RevitLinkInstance двумерным
    тестом «точка внутри контура по XY» (это надёжнее Room.IsPointInRoom,
    который чувствителен к Z и отсекает камеру под потолком). Если по XY
    подошло несколько помещений (этажи друг над другом) — выбирается то,
    чей вертикальный габарит содержит Z камеры, иначе ближайшее по высоте.
    Если точка вне всех контуров — ближайшее в пределах 90 мм («камера
    сидит в стене»). Первый элемент None + пояснение, если не нашлось.
    """
    opt = _boundary_options(boundary_mode)
    opt_center = SpatialElementBoundaryOptions()
    opt_center.SpatialElementBoundaryLocation = SpatialElementBoundaryLocation.Center

    links = list(FilteredElementCollector(doc).OfClass(RevitLinkInstance))
    if not links:
        return None, u"в проекте нет связей (RevitLinkInstance)"

    loaded = 0
    total_rooms = 0
    xy_hits = []   # (area, rings, zmin, zmax, pz)
    near = []      # (dist_ft, rings)

    for li in links:
        ldoc = li.GetLinkDocument()
        if ldoc is None:
            continue
        loaded += 1
        try:
            tf = li.GetTotalTransform()
            p_link = tf.Inverse.OfPoint(host_point)
        except Exception:
            continue

        rooms = (FilteredElementCollector(ldoc)
                 .OfCategory(BuiltInCategory.OST_Rooms)
                 .WhereElementIsNotElementType()
                 .ToElements())

        for room in rooms:
            try:
                if room.Area <= 0:
                    continue
            except Exception:
                continue
            total_rooms += 1

            rings = _room_boundary_rings(room, opt, tf)
            if not rings:
                rings = _room_boundary_rings(room, opt_center, tf)
            if not rings:
                continue

            inside = (_point_in_ring(host_point.X, host_point.Y, rings[0])
                      and not any(_point_in_ring(host_point.X, host_point.Y, h)
                                  for h in rings[1:]))

            if inside:
                zmin = zmax = None
                try:
                    bb = room.get_BoundingBox(None)
                    if bb is not None:
                        zmin, zmax = bb.Min.Z, bb.Max.Z
                except Exception:
                    pass
                try:
                    area = room.Area
                except Exception:
                    area = 0.0
                xy_hits.append((area, rings, zmin, zmax, p_link.Z))
            else:
                d = _dist_point_to_rings(host_point.X, host_point.Y, rings)
                if d is not None and d <= _ROOM_TOLERANCE_FT:
                    near.append((d, rings))

    if loaded == 0:
        return None, u"связи есть, но не загружены (GetLinkDocument = None)"
    if total_rooms == 0:
        return None, u"в связях ({} шт.) нет размещённых помещений".format(loaded)

    if xy_hits:
        if len(xy_hits) == 1:
            return xy_hits[0][1], u"помещение (1 по XY)"

        def _contains_z(h):
            _, _, zmin, zmax, pz = h
            return zmin is not None and (zmin - _ROOM_Z_PAD_FT <= pz <= zmax + _ROOM_Z_PAD_FT)

        in_z = [h for h in xy_hits if _contains_z(h)]
        if in_z:
            in_z.sort(key=lambda h: h[0])   # меньшая площадь = более точное
            return in_z[0][1], u"помещение (из {} по XY — по высоте)".format(len(xy_hits))

        def _zdist(h):
            _, _, zmin, zmax, pz = h
            if zmin is None:
                return 1e9
            return abs(0.5 * (zmin + zmax) - pz)

        xy_hits.sort(key=_zdist)
        return xy_hits[0][1], u"помещение (из {} по XY — ближайшее по высоте)".format(len(xy_hits))

    if near:
        near.sort(key=lambda c: c[0])
        return near[0][1], u"вне контура, взято ближайшее ({:.0f} мм)".format(near[0][0] * 304.8)

    return None, u"проверено помещений: {}, точка вне всех контуров по XY".format(total_rooms)


# ======================================================================
#  ПОСТРОЕНИЕ КОНТУРА ЗОНЫ
# ======================================================================

def _clip_distance(ox, oy, ux, uy, max_d, rings):
    """Расстояние вдоль луча (ox,oy)+t*(ux,uy) до первого пересечения с
    любым отрезком контуров rings, но не больше max_d."""
    best = max_d
    for ring in rings:
        n = len(ring)
        for i in range(n):
            a = ring[i]
            b = ring[(i + 1) % n]
            ex, ey = b.X - a.X, b.Y - a.Y
            den = ux * ey - uy * ex
            if abs(den) < 1e-12:
                continue
            ax, ay = a.X - ox, a.Y - oy
            t = (ax * ey - ay * ex) / den
            u = (ax * uy - ay * ux) / den
            if 1e-6 < t < best and -1e-9 <= u <= 1.0 + 1e-9:
                best = t
    return best


# Минимальная длина отрезка контура зоны, футы (~3 мм) — с запасом выше
# минимальной длины кривой, которую примет Revit (около 0.79 мм,
# Application.ShortCurveTolerance). Раньше здесь стояло 1e-4 фт
# (~0.03 мм) — куда меньше этого порога: соседние точки проходили дедуп
# как «разные», но Line.CreateBound на них падал с исключением, а один
# такой отрезок обрывал построение ВСЕГО контура (см. ниже) — типичная
# причина «обрезка дала пустой контур» на помещениях с частой сеткой
# вершин (много сегментов границы / много препятствий).
_MIN_SEG_FT = 0.01

# Угловой зазор между «до» и «после» вершины препятствия/помещения при
# добавлении лучей точности — вместе с радиусом даёт длину дуги; должен
# быть настолько большим, чтобы эта длина не схлопнулась дедупом выше
# (_MIN_SEG_FT) на обычных для камеры расстояниях.
_VERTEX_RAY_EPS = 0.01


def _zone_curveloop(center, base, half, near_r, far_r, rings, ray_count, z):
    """
    CurveLoop контура зоны обзора (звёздный многоугольник от центра либо
    кольцевой сектор при near_r > 0). Каждый радиальный луч обрезается по
    rings. None, если контур вырожден.
    """
    steps = max(8, int(ray_count))
    offs = [(-half + 2.0 * half * (float(i) / steps)) for i in range(steps + 1)]

    # добавочные лучи точно в вершины помещения — чёткие изломы на границе
    for ring in (rings or []):
        for p in ring:
            a = math.atan2(p.Y - center.Y, p.X - center.X)
            da = math.atan2(math.sin(a - base), math.cos(a - base))
            if -half - _VERTEX_RAY_EPS <= da <= half + _VERTEX_RAY_EPS:
                offs.append(max(-half, da - _VERTEX_RAY_EPS))
                offs.append(min(half, da + _VERTEX_RAY_EPS))

    offs = sorted(set(round(o, 9) for o in offs))

    far_ray = []
    for o in offs:
        a = base + o
        ux, uy = math.cos(a), math.sin(a)
        r = far_r
        if rings:
            r = _clip_distance(center.X, center.Y, ux, uy, far_r, rings)
        far_ray.append((a, r))

    pts = []
    if near_r <= 0.05:
        pts.append(XYZ(center.X, center.Y, z))
        for a, r in far_ray:
            pts.append(XYZ(center.X + math.cos(a) * r, center.Y + math.sin(a) * r, z))
    else:
        for a, r in far_ray:
            rr = max(r, near_r + 0.02)
            pts.append(XYZ(center.X + math.cos(a) * rr, center.Y + math.sin(a) * rr, z))
        for a, r in reversed(far_ray):
            pts.append(XYZ(center.X + math.cos(a) * near_r, center.Y + math.sin(a) * near_r, z))

    clean = []
    for p in pts:
        if not clean or clean[-1].DistanceTo(p) > _MIN_SEG_FT:
            clean.append(p)
    if len(clean) >= 2 and clean[0].DistanceTo(clean[-1]) <= _MIN_SEG_FT:
        clean.pop()
    if len(clean) < 3:
        return None

    cl = CurveLoop()
    made = 0
    n = len(clean)
    for i in range(n):
        a = clean[i]
        b = clean[(i + 1) % n]
        if a.DistanceTo(b) < _MIN_SEG_FT:
            continue
        try:
            cl.Append(Line.CreateBound(a, b))
            made += 1
        except Exception:
            # единичный «плохой» отрезок не должен ронять весь контур —
            # пропускаем вершину-виновника и продолжаем достраивать
            # оставшиеся; итог проверяется по made >= 3 ниже
            continue
    return cl if made >= 3 else None


# ======================================================================
#  ТИПЫ / СТИЛИ / ОЧИСТКА
# ======================================================================

def _pick_filled_region_type(doc, name):
    types = list(FilteredElementCollector(doc).OfClass(FilledRegionType))
    if not types:
        return None
    if name and name.strip():
        want = name.strip()
        for t in types:
            try:
                if Element.Name.GetValue(t) == want:
                    return t
            except Exception:
                continue
    return types[0]


def _get_or_create_line_style(doc, name):
    """Подкатегория категории «Линии» с этим именем (создаётся при
    отсутствии, цвет — фирменный синий). GraphicsStyle или None."""
    if not name or not name.strip():
        return None
    name = name.strip()
    try:
        cats = doc.Settings.Categories
        lines_cat = cats.get_Item(BuiltInCategory.OST_Lines)

        sub = None
        for s in lines_cat.SubCategories:
            if s.Name == name:
                sub = s
                break
        if sub is None:
            sub = cats.NewSubcategory(lines_cat, name)
        try:
            sub.LineColor = Color(27, 97, 180)
        except Exception:
            pass
        return sub.GetGraphicsStyle(GraphicsStyleType.Projection)
    except Exception:
        return None


def _apply_boundary_style(filled_region, gstyle):
    if gstyle is None:
        return
    try:
        filled_region.SetLineStyleId(gstyle.Id)
    except Exception:
        pass


def _delete_previous(doc, view, tag, cam_ids, dori_style_name):
    """Удалить с вида зоны выбранных камер, созданные прошлым запуском:
    FilledRegion по метке в «Комментариях», дуги DORI по имени стиля линии."""
    to_del = List[ElementId]()
    prefix = tag + u"|"

    for fr in FilteredElementCollector(doc, view.Id).OfClass(FilledRegion):
        p = fr.get_Parameter(BuiltInParameter.ALL_MODEL_INSTANCE_COMMENTS)
        s = p.AsString() if (p is not None and p.HasValue) else None
        if not s or not s.startswith(prefix):
            continue
        try:
            cid = int(s.split(u"|")[1])
        except Exception:
            cid = None
        if cid is None or cid in cam_ids:
            to_del.Add(fr.Id)

    if dori_style_name:
        for dc in FilteredElementCollector(doc, view.Id).OfClass(CurveElement):
            try:
                gs = dc.LineStyle
                nm = Element.Name.GetValue(gs) if gs is not None else None
            except Exception:
                nm = None
            if nm and nm == dori_style_name:
                to_del.Add(dc.Id)

    if to_del.Count:
        try:
            doc.Delete(to_del)
        except Exception:
            pass


# ======================================================================
#  ЗОНЫ DORI  (EN 62676-4)
# ======================================================================

_DORI_LEVELS = (
    (u"Идентификация", 250.0),
    (u"Распознавание", 125.0),
    (u"Наблюдение", 63.0),
    (u"Обнаружение", 25.0),
)


def _camera_h_res(doc, cam, s, default_px):
    """
    Горизонтальное разрешение матрицы этой камеры, пикс: из параметра
    camera_h_res_param_name (обычно параметр ТИПА — характеристика модели;
    ищется на экземпляре, потом на типе; «Целое», «Число» или текст
    вида «1920» / «1920x1080»), а если параметр не задан, не найден или
    пуст — общее значение default_px (camera_h_res_px из настроек).
    """
    name = (s.get("camera_h_res_param_name") or u"").strip()
    if name:
        p = _find_param(doc, cam, name)
        if p is not None and p.HasValue:
            v = None
            try:
                if p.StorageType == StorageType.Integer:
                    v = float(p.AsInteger())
                elif p.StorageType == StorageType.Double:
                    v = p.AsDouble()
                elif p.StorageType == StorageType.String:
                    m = re.search(u"\\d+", p.AsString() or u"")
                    v = float(m.group(0)) if m else None
            except Exception:
                v = None
            # меньше 100 — явно не пиксели (мегапиксели, пусто и т.п.)
            if v is not None and v >= 100:
                return v
    # float: значение уходит в «{:.0f}» отчёта, а IronPython не форматирует
    # целое с точностью («Precision not allowed in integer format specifier»)
    return float(default_px or 0)


def _draw_dori(doc, view, center, base, half, h_res_px, hfov_rad, max_r, z, gstyle):
    if h_res_px <= 0 or hfov_rad <= 1e-4:
        return
    tan_half = math.tan(hfov_rad / 2.0)
    if tan_half <= 1e-6:
        return

    sweep = 2.0 * half
    if sweep <= 1e-3 or sweep >= 2.0 * math.pi - 1e-3:
        return

    for _name, ppm in _DORI_LEVELS:
        d_ft = (h_res_px / (2.0 * ppm * tan_half)) / _M_PER_FT
        if not (0.1 < d_ft <= max_r):
            continue
        c = XYZ(center.X, center.Y, z)
        try:
            arc = Arc.Create(c, d_ft, base - half, base + half, XYZ.BasisX, XYZ.BasisY)
            dc = doc.Create.NewDetailCurve(view, arc)
            if gstyle is not None:
                try:
                    dc.LineStyle = gstyle
                except Exception:
                    pass
        except Exception:
            continue


# ======================================================================
#  ГЛАВНЫЙ ВХОД
# ======================================================================

def _one_camera(doc, cam, view, s, frt, line_style, dori_style,
                clip, ray_count, boundary_mode, target_off_ft, offset_deg,
                dead_zone_on, unit_mode, h_res, tag, z):
    if not isinstance(cam.Location, LocationPoint):
        return (cam, u"no_location", u"")

    dist_name = (s.get("distance_param_name") or u"").strip()
    dist_p = _find_param(doc, cam, dist_name)
    if dist_p is None or not dist_p.HasValue:
        return (cam, u"no_distance_param", dist_name or u"(имя не задано)")

    # горизонтальный и вертикальный угол обзора — ВСЕГДА расчётные, из
    # фокусного расстояния и формата матрицы (см. _optical_fov)
    hfov, vfov, optic_reason = _optical_fov(doc, cam, s)
    if hfov is None:
        return (cam, u"no_optics", optic_reason)

    max_r = dist_p.AsDouble()
    if hfov <= 1e-4:
        return (cam, u"bad_geometry",
                u"расчётный угол обзора = {:.4f} рад ({:.1f}°) — проверьте "
                u"фокусное расстояние/формат матрицы".format(hfov, math.degrees(hfov)))
    if max_r <= 0.02:
        return (cam, u"bad_geometry",
                u"дальность = {:.3f} фт ({:.0f} мм) — параметр «{}» пуст или "
                u"не типа «Длина»".format(max_r, max_r * 304.8, dist_name))
    hfov = min(hfov, 2.0 * math.pi - 1e-3)
    half = hfov / 2.0

    # направление семейства + индивидуальный разворот параметром внутри
    # семейства (по шкале rotation_zero_deg/rotation_clockwise)
    base, dir_note, _fwd = _camera_azimuth(doc, cam, s, unit_mode)
    if base is None:
        return (cam, u"bad_geometry",
                u"не удалось определить направление камеры [{}]".format(dir_note))

    p = cam.Location.Point
    center = XYZ(p.X, p.Y, 0.0)

    tilt = _opt_param_radians(doc, cam, s.get("tilt_param_name"), unit_mode)
    # vfov уже посчитан выше (_optical_fov) — из фокусного расстояния и
    # высоты матрицы; отдельного параметра вертикального угла больше нет
    h_ft = _mounting_height_ft(doc, cam, view, s.get("height_param_name"))
    if h_ft is not None:
        h_ft = h_ft - target_off_ft

    if h_ft is not None and tilt is not None and vfov is not None:
        cone_note = u"h={:.2f} м, наклон={:.0f}°, верт.угол={:.0f}°".format(
            h_ft * _M_PER_FT, math.degrees(tilt), math.degrees(vfov))
    else:
        missing = []
        if h_ft is None:
            missing.append(u"высота")
        if tilt is None:
            missing.append(u"наклон")
        if vfov is None:
            missing.append(u"верт.угол")
        cone_note = u"мёртвая зона не считается (не найдено: {})".format(u", ".join(missing))

    near_r, far_r = _near_far_radius(h_ft, tilt, vfov, max_r)
    if not dead_zone_on:
        near_r = 0.0
        cone_note = u"мёртвая зона отключена (draw_dead_zone)"

    status = u"ok"
    room_rings = None
    room_note = u""
    if clip:
        room_rings, room_note = room_rings_for_point(doc, p, boundary_mode)
        if room_rings is None:
            status = u"ok_no_room"

    used_room = room_rings is not None

    cl = _zone_curveloop(center, base, half, near_r, far_r, room_rings, ray_count, z)
    if cl is None and room_rings is not None:
        # обрезка по границе помещения «съела» весь контур — строим без
        # обрезки, но помечаем (см. статус ok_clip_failed)
        cl = _zone_curveloop(center, base, half, near_r, far_r, None, ray_count, z)
        if cl is not None:
            used_room = False
            status = u"ok_clip_failed"
    if cl is None:
        return (cam, u"bad_geometry",
                u"контур вырожден (near={:.2f} far={:.2f} фт, обрезка={})".format(
                    near_r, far_r, u"да" if room_rings is not None else u"нет"))

    try:
        fr = FilledRegion.Create(doc, frt.Id, view.Id, List[CurveLoop]([cl]))
    except Exception as ex:
        return (cam, u"create_failed", u"{}".format(ex))

    cp = fr.get_Parameter(BuiltInParameter.ALL_MODEL_INSTANCE_COMMENTS)
    if cp is not None and not cp.IsReadOnly:
        try:
            cp.Set(u"{}|{}".format(tag, cam.Id.IntegerValue))
        except Exception:
            pass

    _apply_boundary_style(fr, line_style)

    if dori_style is not None:
        cam_res = _camera_h_res(doc, cam, s, h_res)
        if cam_res > 0:
            _draw_dori(doc, view, center, base, half, cam_res, hfov, max_r, z, dori_style)

    if not clip:
        clip_note = u"без обрезки по помещению (выключена)"
    elif status == u"ok_no_room":
        clip_note = u"без обрезки по помещению — {}".format(room_note or u"не найдено")
    elif used_room:
        clip_note = u"обрезка по помещению: {} ({} сегм.)".format(
            room_note or u"", sum(len(r) for r in room_rings))
    else:
        clip_note = u"обрезка по помещению не удалась — без неё"

    az = math.degrees(base) % 360.0
    summary = (u"азимут {:.0f}°, угол {:.0f}°, R {:.1f}–{:.1f} м; {}; напр.: {}; {}"
               .format(az, math.degrees(hfov),
                       near_r * _M_PER_FT, far_r * _M_PER_FT,
                       cone_note, dir_note, clip_note))
    return (cam, status, summary)


def resolve_category_ids(doc, text):
    """
    Множество int-id категорий для фильтра выбора камер. Каждый токен
    (через запятую / точку с запятой / перевод строки) трактуется как имя
    BuiltInCategory (OST_SecurityDevices) либо как русское имя категории
    («Оборудование систем безопасности»). Нераспознанные молча
    пропускаются.
    """
    ids = set()
    for tok in re.split(u"[,;\n\r\t]+", text or u""):
        name = tok.strip()
        if not name:
            continue
        bic = getattr(BuiltInCategory, name, None)
        if bic is not None:
            try:
                ids.add(int(bic))
                continue
            except Exception:
                pass
        try:
            for c in doc.Settings.Categories:
                if c.Name and c.Name.strip().lower() == name.lower():
                    ids.add(c.Id.IntegerValue)
                    break
        except Exception:
            pass
    return ids


class CategorySelectionFilter(ISelectionFilter):
    """
    ISelectionFilter, пропускающий только элементы категорий из
    allowed_ids (см. resolve_category_ids) — общий для обеих кнопок
    панели («Зоны обзора» и «Навести на помещение»), чтобы фильтр выбора
    камер не дублировался в их script.py.
    """

    def __init__(self, allowed_ids):
        self._ids = set(allowed_ids)

    def AllowElement(self, elem):
        try:
            cat = elem.Category
            return cat is not None and cat.Id.IntegerValue in self._ids
        except Exception:
            return False

    def AllowReference(self, reference, position):
        return True


def build_fov_zones(doc, cameras, view, settings):
    """
    Построить/перестроить зоны обзора по списку камер на виде view.
    Возвращает список (camera, status, detail); status:
      "ok" / "ok_no_room" / "ok_clip_failed" / "no_location" /
      "no_optics" / "no_distance_param" / "bad_geometry" /
      "create_failed". detail — текст с числами/векторами для диагностики.
    Транзакция — на вызывающей стороне.
    """
    s = settings

    frt = _pick_filled_region_type(doc, s.get("fill_type_name"))
    if frt is None:
        return [(None, u"no_fill_type",
                 u"В проекте нет ни одного типа области заливки (FilledRegionType).")]

    line_style = _get_or_create_line_style(doc, s.get("line_subcategory") or u"СОТ_Зона обзора")

    dori_on = _as_bool(s.get("draw_dori"))
    base_sub = (s.get("line_subcategory") or u"СОТ_Зона обзора").strip()
    dori_style_name = base_sub + u" · DORI"
    dori_style = _get_or_create_line_style(doc, dori_style_name) if dori_on else None
    h_res = _as_float(s.get("camera_h_res_px"), 0.0) if dori_on else 0.0

    tag = (s.get("zone_tag") or u"CCTV_FOV").strip() or u"CCTV_FOV"
    clip = _as_bool(s.get("clip_to_rooms"), default=True)
    ray_count = _as_int(s.get("ray_count"), 96)
    boundary_mode = s.get("room_boundary") or u"отделка"
    target_off_ft = _as_float(s.get("target_level_offset_mm"), 0.0) * _FT_PER_MM
    offset_deg = _as_float(s.get("direction_offset_deg"), 0.0)
    dead_zone_on = _as_bool(s.get("draw_dead_zone"), default=True)
    unit_mode = s.get("angle_unit") or u"авто"

    cam_ids = set(c.Id.IntegerValue for c in cameras)
    _delete_previous(doc, view, tag, cam_ids, dori_style_name if dori_on else None)

    z = 0.0
    gen = getattr(view, "GenLevel", None)
    if gen is not None:
        try:
            z = gen.Elevation
        except Exception:
            z = 0.0

    results = []
    for cam in cameras:
        try:
            results.append(_one_camera(
                doc, cam, view, s, frt, line_style, dori_style,
                clip, ray_count, boundary_mode, target_off_ft, offset_deg,
                dead_zone_on, unit_mode, h_res, tag, z))
        except Exception as ex:
            results.append((cam, u"create_failed", u"{}".format(ex)))
    return results


# ======================================================================
#  АВТОНАВЕДЕНИЕ: ПОВОРОТ, ФОКУСНОЕ И НАКЛОН ПО ПОМЕЩЕНИЮ
#  (кнопка «Навести на помещение»)
# ======================================================================
#
# Отдельная кнопка, не «Зоны обзора»: сама зона — только чтение и отрисовка,
# автонаведение — единственное место в СОТ, где кнопка ЗАПИСЫВАЕТ значения
# на камеру. По каждой камере:
#
#   1. Из камеры по кругу пускается веер лучей до границы её помещения;
#      каждый луч обрезается дальностью камеры R (distance_param_name —
#      обычно параметр типа, паспортная дальность). Вес луча — площадь
#      узкого сектора помещения в пределах дальности (≈ r²); если включён
#      учёт других камер (auto_consider_others), уже покрытая ими площадь
#      идёт с весом _AIM_COVERED_WEIGHT.
#   2. Поворот — только если включён (auto_rotate; по умолчанию камеру
#      ориентирует пользователь): азимут, при котором сектор самого
#      широкого угла объектива накрывает наибольший вес; при «плато» —
#      середина (биссектриса). Пишется в параметр поворота экземпляра по
#      его шкале (_rotation_spec), иначе поворачивается экземпляр.
#   3. Рабочее расстояние L = min(до стены по оси взгляда, R).
#   4. Фокусное (если это параметр экземпляра) по auto_focal_mode:
#        «площадь» — самый узкий угол вокруг оси, накрывающий
#                    auto_coverage_pct % веса;
#        «DORI»    — кадр шириной разрешение / пикс_на_м на расстоянии L
#                    (auto_dori_level, camera_h_res_px);
#        «авто»    — DORI, если стена дальше дальности (большое помещение:
#                    паркинг, склад), иначе «площадь».
#   5. Наклон по auto_tilt_mode, h_эфф = высота установки − высота
#      плоскости расчёта (target_level_offset_mm, как у «Зон обзора»):
#        «ось»  — ось кадра в точку цели на расстоянии L:  arctg(h_эфф / L)
#        «верх» — верхний край кадра в цель на L:  arctg(h_эфф / L) + верт/2
#        «низ»  — нижний край кадра даёт мёртвую зону auto_max_near_zone_mm:
#                 arctg(h_эфф / мёртвая_зона) − верт/2

_AIM_RAY_COUNT = 360            # лучей на полный круг (шаг 1°)
_AIM_SEARCH_FT = 1000.0         # предел поиска границы помещения, фт (~300 м)
_AIM_PLATEAU = 0.99             # доля от максимума площади — «плато» азимутов
_AIM_MIN_ROTATE_RAD = math.radians(0.1)


def _window_sums(weights, half_steps):
    """Кольцевые суммы weights в окне [c−half_steps, c+half_steps] для
    каждого c. half_steps >= n/2 — окно на весь круг."""
    n = len(weights)
    total = sum(weights)
    if 2 * half_steps + 1 >= n:
        return [total] * n
    ext = weights + weights + weights
    prefix = [0.0]
    for w in ext:
        prefix.append(prefix[-1] + w)
    out = []
    for c in range(n):
        lo = c + n - half_steps
        hi = c + n + half_steps + 1
        out.append(prefix[hi] - prefix[lo])
    return out


def _best_azimuth(weights, half_steps, current_idx, allowed=None):
    """
    Индекс азимута, при котором окно ±half_steps накрывает наибольший вес,
    либо None (вес всюду одинаков — поворачивать не к чему). При плато
    (несколько азимутов в пределах _AIM_PLATEAU от максимума подряд) —
    середина того плато, которое содержит максимум (ближайший к текущему
    направлению, если максимумов несколько). allowed — список bool по
    индексам: только эти азимуты достижимы (диапазон поворота камеры);
    None — все.
    """
    n = len(weights)
    sums = _window_sums(weights, half_steps)
    if allowed is not None:
        if not any(allowed):
            return None
        sums = [sm if ok else -1.0 for sm, ok in zip(sums, allowed)]
    best = max(sums)
    if best <= 0.0:
        return None
    thr = best * _AIM_PLATEAU
    good = [s >= thr for s in sums]
    if all(good):
        return None

    # непрерывные (по кругу) участки good; стартуем с первого «плохого»
    start = good.index(False)
    runs = []
    run = []
    for i in range(1, n + 1):
        k = (start + i) % n
        if good[k]:
            run.append(k)
        elif run:
            runs.append(run)
            run = []
    if run:
        runs.append(run)

    def _run_center(r):
        return r[len(r) // 2]

    def _circ_dist(a, b):
        d = abs(a - b) % n
        return min(d, n - d)

    best_run = None
    best_key = None
    for r in runs:
        peak = max(sums[k] for k in r)
        key = (-peak, _circ_dist(_run_center(r), current_idx))
        if best_key is None or key < best_key:
            best_key = key
            best_run = r
    return _run_center(best_run)


def _coverage_half_steps(weights, center_idx, fraction):
    """Наименьшее число шагов a, при котором окно ±a вокруг center_idx
    набирает fraction всего веса (по кругу)."""
    n = len(weights)
    total = sum(weights)
    if total <= 0.0:
        return 0
    need = total * fraction
    acc = weights[center_idx]
    a = 0
    while acc < need - 1e-9 and a < n // 2:
        a += 1
        acc += weights[(center_idx + a) % n]
        if (center_idx - a) % n != (center_idx + a) % n:
            acc += weights[(center_idx - a) % n]
    return a


def _instance_param(cam, configured):
    """Первый из перечисленных через «;» параметров, найденный на ЭКЗЕМПЛЯРЕ
    (LookupParameter), либо None. Если у самой камеры нет — на экземплярах
    вложенных общих семейств (составная камера «основание + поворотная
    камера»)."""
    names = _split_alias_names((configured or u"").strip())
    for name in names:
        p = cam.LookupParameter(name)
        if p is not None:
            return p
    for sub in _subcomponents(cam.Document, cam):
        for name in names:
            try:
                p = sub.LookupParameter(name)
            except Exception:
                p = None
            if p is not None:
                return p
    return None


def _writable_double(p):
    return p is not None and not p.IsReadOnly and p.StorageType == StorageType.Double


def _writable_angle(p):
    """Угловой параметр, в который можно писать: «Угол»/«Число» (Double)
    или «Целое» (градусы)."""
    return p is not None and not p.IsReadOnly and \
        p.StorageType in (StorageType.Double, StorageType.Integer)


def _camera_sensor(doc, cam, s):
    sensor = None
    sensor_pname = (s.get("sensor_format_param_name") or u"").strip()
    if sensor_pname:
        sp = _find_param(doc, cam, sensor_pname)
        if sp is not None and sp.HasValue:
            text = sp.AsString() if sp.StorageType == StorageType.String else sp.AsValueString()
            sensor = _parse_sensor(text)
    if sensor is None:
        sensor = _parse_sensor(s.get("sensor_format"))
    return sensor


def _rotate_camera(doc, cam, s, unit_mode, target, forward, delta):
    """Развернуть камеру в азимут target (рад). Сначала — через параметр
    поворота экземпляра (rotation_param_name, по его шкале —
    _rotation_value_for_azimuth; forward — «вперёд» семейства), иначе —
    поворотом самого экземпляра на delta вокруг вертикали через точку
    вставки. Возвращает (успех, пояснение)."""
    rot_p = _instance_param(cam, s.get("rotation_param_name"))
    if _writable_angle(rot_p):
        new, in_range = _rotation_value_for_azimuth(target, forward, s)
        if not in_range:
            return False, u"азимут вне диапазона поворота «{}»".format(
                s.get("rotation_range_deg"))
        if rot_p.StorageType == StorageType.Integer:
            mode = (unit_mode or u"авто").strip().lower()
            rot_p.Set(int(round(new if mode.startswith(u"рад") else math.degrees(new))))
        else:
            rot_p.Set(_radians_to_param_value(rot_p, new, unit_mode))
        return True, u"параметр «{}» = {:.1f}°".format(
            rot_p.Definition.Name, math.degrees(new))
    p = cam.Location.Point
    axis = Line.CreateBound(p, XYZ(p.X, p.Y, p.Z + 1.0))
    try:
        ElementTransformUtils.RotateElement(doc, cam.Id, axis, delta)
    except Exception as ex:
        return False, u"не удалось повернуть экземпляр ({})".format(ex)
    return True, u"повёрнут экземпляр"


# --- учёт других камер ------------------------------------------------
#
# Площадь, которую уже видят другие камеры, при выборе поворота и
# фокусного новой камеры учитывается с весом _AIM_COVERED_WEIGHT (не
# нулём — чтобы направление всё равно оставалось осмысленным, если всё
# вокруг уже покрыто). «Покрытие» камеры — сектор её зоны обзора
# (азимут ± гор.угол/2, от мёртвой зоны до дальней границы), обрезанный
# её помещением по лучам — та же модель, что у «Зон обзора».

_AIM_COVERED_WEIGHT = 0.1
_AIM_RADIAL_SAMPLES = 32        # точек вдоль луча при учёте чужого покрытия


def _ray_table(center, rings, max_r):
    """Расстояния от center до границы помещения по _AIM_RAY_COUNT лучам,
    обрезанные max_r."""
    n = _AIM_RAY_COUNT
    step = 2.0 * math.pi / n
    out = []
    for k in range(n):
        a = k * step
        r = _clip_distance(center.X, center.Y, math.cos(a), math.sin(a), _AIM_SEARCH_FT, rings)
        out.append(min(r, max_r))
    return out


def _coverage_record(doc, cam, view, s, unit_mode, target_off_ft):
    """Сектор, который камера видит сейчас (по параметрам на ней), для
    учёта при наведении других камер; None, если не посчитать."""
    if not isinstance(cam.Location, LocationPoint):
        return None
    base, _note, _fwd = _camera_azimuth(doc, cam, s, unit_mode)
    if base is None:
        return None
    hfov, vfov, _r = _optical_fov(doc, cam, s)
    if not hfov:
        return None
    dist_p = _find_param(doc, cam, (s.get("distance_param_name") or u"").strip())
    if dist_p is None or not dist_p.HasValue or dist_p.StorageType != StorageType.Double:
        return None
    max_r = dist_p.AsDouble()
    if max_r <= 0.02:
        return None
    p = cam.Location.Point
    rings, _rn = room_rings_for_point(doc, p, s.get("room_boundary") or u"отделка")
    if rings is None:
        return None
    tilt = _opt_param_radians(doc, cam, s.get("tilt_param_name"), unit_mode)
    h_ft = _mounting_height_ft(doc, cam, view, s.get("height_param_name"))
    if h_ft is not None:
        h_ft -= target_off_ft
    near_r, far_r = _near_far_radius(h_ft, tilt, vfov, max_r)
    center = XYZ(p.X, p.Y, 0.0)
    return {
        "id": cam.Id.IntegerValue,
        "x": center.X, "y": center.Y,
        "az": base, "half": min(hfov, 2.0 * math.pi) / 2.0,
        "near": near_r, "far": far_r,
        "rays": _ray_table(center, rings, far_r),
    }


def _is_covered(x, y, records):
    n = _AIM_RAY_COUNT
    step = 2.0 * math.pi / n
    for rec in records:
        dx = x - rec["x"]
        dy = y - rec["y"]
        d = math.sqrt(dx * dx + dy * dy)
        if d < rec["near"] or d > rec["far"]:
            continue
        a = math.atan2(dy, dx)
        if abs(_norm_angle(a - rec["az"])) > rec["half"]:
            continue
        if d <= rec["rays"][int(round(a / step)) % n] + 1e-6:
            return True
    return False


def _ray_weights(center, rays, range_ft, records):
    """Вес каждого луча веера — площадь сектора помещения в пределах
    дальности (≈ r²), где уже покрытое другими камерами (records) идёт с
    весом _AIM_COVERED_WEIGHT."""
    if not records:
        return [r * r for r in rays]
    near_recs = [rec for rec in records
                 if math.hypot(rec["x"] - center.X, rec["y"] - center.Y)
                 <= range_ft + rec["far"] + 1e-6]
    if not near_recs:
        return [r * r for r in rays]
    n = len(rays)
    step = 2.0 * math.pi / n
    dr = max(range_ft / _AIM_RADIAL_SAMPLES, 0.1)
    out = []
    for k, r_max in enumerate(rays):
        a = k * step
        ca, sa = math.cos(a), math.sin(a)
        w = 0.0
        r0 = 0.0
        while r0 < r_max - 1e-9:
            r1 = min(r0 + dr, r_max)
            elem = r1 * r1 - r0 * r0            # кольцевой отрезок сектора
            rm = (r0 + r1) / 2.0
            if _is_covered(center.X + ca * rm, center.Y + sa * rm, near_recs):
                elem *= _AIM_COVERED_WEIGHT
            w += elem
            r0 = r1
        out.append(w)
    return out


def _dori_ppm(text):
    """Уровень DORI для подбора фокусного: название (обнаружение/
    наблюдение/распознавание/идентификация) или число пикс/м."""
    t = (text or u"").strip().lower()
    if not t:
        return 125.0
    for name, ppm in _DORI_LEVELS:
        if name.lower().startswith(t[:5]):
            return ppm
    try:
        v = float(t.replace(u",", u"."))
        return v if v > 0 else 125.0
    except Exception:
        return 125.0


def _auto_aim_one(doc, cam, view, s, o, covered):
    """Навести одну камеру (см. заголовок раздела); o — разобранные
    настройки из auto_aim_cameras, covered — покрытие других камер
    (список _coverage_record) или None, если учёт выключен."""
    unit_mode = o["unit_mode"]
    if not isinstance(cam.Location, LocationPoint):
        return (cam, u"no_location", u"")

    tilt_name = (s.get("tilt_param_name") or u"").strip()
    if not tilt_name:
        return (cam, u"no_tilt_param", u"в настройках не задано имя параметра наклона")

    # Наклон подбирается ПОД КОНКРЕТНУЮ камеру (её помещение, её
    # направление) — параметр должен быть параметром ЭКЗЕМПЛЯРА: если бы
    # он был параметром типа, запись одного значения переставила бы
    # наклон и у всех остальных камер того же типа.
    tilt_p = _instance_param(cam, tilt_name)
    if tilt_p is None:
        return (cam, u"tilt_not_instance",
                u"«{}» не найден как параметр ЭКЗЕМПЛЯРА этой камеры (если он "
                u"параметр типа — сделайте его параметром экземпляра: наклон "
                u"должен подбираться отдельно для каждой камеры)".format(tilt_name))
    if not _writable_double(tilt_p):
        return (cam, u"tilt_readonly",
                u"параметр «{}» недоступен для записи".format(tilt_name))

    # дальность — паспортная характеристика камеры (обычно параметр типа)
    dist_name = (s.get("distance_param_name") or u"").strip()
    dist_p = _find_param(doc, cam, dist_name) if dist_name else None
    if dist_p is None or not dist_p.HasValue or dist_p.StorageType != StorageType.Double:
        return (cam, u"no_distance_param",
                u"параметр дальности «{}» не найден на камере (ни на экземпляре, "
                u"ни на типе)".format(dist_name or u"(имя не задано)"))
    range_ft = dist_p.AsDouble()
    if range_ft <= 0.02:
        return (cam, u"no_distance_param",
                u"дальность = 0 (параметр «{}»)".format(dist_name))

    base, dir_note, forward = _camera_azimuth(doc, cam, s, unit_mode)
    if base is None:
        return (cam, u"bad_geometry", u"нет направления камеры [{}]".format(dir_note))

    p = cam.Location.Point
    center = XYZ(p.X, p.Y, 0.0)

    rings, room_note = room_rings_for_point(doc, p, s.get("room_boundary") or u"отделка")
    if rings is None:
        return (cam, u"no_room", room_note)

    n = _AIM_RAY_COUNT
    step = 2.0 * math.pi / n
    others = [rec for rec in (covered or []) if rec["id"] != cam.Id.IntegerValue]
    weights = None
    if o["rotate_on"] or o["focal_mode"] != u"dori":
        weights = _ray_weights(center, _ray_table(center, rings, range_ft), range_ft, others)

    # --- оптика: вариофокал (фокусное — параметр экземпляра) или нет
    sensor = _camera_sensor(doc, cam, s)
    focal_p = _instance_param(cam, s.get("focal_length_param_name"))
    varifocal = _writable_double(focal_p) and sensor is not None
    focal_min_mm, focal_max_mm = o["focal_min_mm"], o["focal_max_mm"]

    if varifocal:
        hfov_wide = 2.0 * math.atan(sensor[0] / (2.0 * focal_min_mm))
    else:
        hfov_now, _v, _r = _optical_fov(doc, cam, s)
        hfov_wide = hfov_now if hfov_now else math.radians(90.0)

    notes = []
    warn_reasons = []

    # --- поворот (по выбору: auto_rotate)
    if o["rotate_on"]:
        # поворот параметром внутри семейства с ограниченным диапазоном
        # (поворотная камера на настенном основании: 0–180°) — искать
        # только среди достижимых азимутов
        allowed = None
        if (_writable_angle(_instance_param(cam, s.get("rotation_param_name")))
                and _rotation_spec(s)[2] is not None):
            allowed = [_rotation_value_for_azimuth(k * step, forward, s)[1]
                       for k in range(n)]
        cur_idx = int(round(_norm_angle(base) / step)) % n
        half_steps = max(0, int(round(hfov_wide / 2.0 / step)))
        best_idx = _best_azimuth(weights, half_steps, cur_idx, allowed)
        if best_idx is not None:
            target = best_idx * step
            delta = _norm_angle(target - base)
            if abs(delta) > _AIM_MIN_ROTATE_RAD:
                ok, how = _rotate_camera(doc, cam, s, unit_mode, target, forward, delta)
                if ok:
                    base = target
                    notes.append(u"повёрнута на {:+.0f}° ({})".format(math.degrees(delta), how))
                else:
                    warn_reasons.append(how)
            else:
                notes.append(u"поворот не нужен")
        else:
            notes.append(u"поворот: помещение симметрично вокруг камеры, направление не менялось")

    # --- рабочее расстояние по оси взгляда
    wall_ft = _clip_distance(center.X, center.Y, math.cos(base), math.sin(base),
                             _AIM_SEARCH_FT, rings)
    if wall_ft >= _AIM_SEARCH_FT - 1e-6:
        return (cam, u"no_wall_hit",
                u"по направлению камеры (азимут {:.0f}°) граница помещения не "
                u"встретилась — контур помещения незамкнут?".format(
                    math.degrees(base) % 360.0))
    work_ft = min(wall_ft, range_ft)
    large_room = wall_ft > range_ft + 1e-6

    # --- фокусное: по площади помещения или по детализации DORI на L
    mode = o["focal_mode"]
    h_res = _camera_h_res(doc, cam, s, o["h_res_px"])
    if mode == u"auto":
        mode = u"dori" if large_room else u"area"
    if mode == u"dori" and h_res <= 0:
        notes.append(u"DORI: не задано разрешение матрицы (ни параметром камеры, ни в "
                     u"разделе ⑤) — фокусное по площади")
        mode = u"area"
        if weights is None:
            weights = _ray_weights(center, _ray_table(center, rings, range_ft), range_ft, others)

    needed_hfov = None
    if mode == u"dori":
        # кадр шириной res/ppm метров на расстоянии L
        frame_w_ft = (h_res / o["dori_ppm"]) / _M_PER_FT
        needed_hfov = 2.0 * math.atan2(frame_w_ft / 2.0, work_ft)
        focal_how = u"DORI {:.0f} пикс/м на {:.1f} м, {:.0f} пикс".format(
            o["dori_ppm"], work_ft * _M_PER_FT, h_res)
    else:
        center_idx = int(round(_norm_angle(base) / step)) % n
        cov_half = _coverage_half_steps(weights, center_idx, o["coverage"]) * step
        needed_hfov = min(2.0 * cov_half, math.radians(178.0))
        focal_how = u"{:.0f}% площади".format(o["coverage"] * 100.0)
    if varifocal:
        tan_half = math.tan(needed_hfov / 2.0)
        needed_f = (sensor[0] / (2.0 * tan_half)) if tan_half > 1e-6 else focal_max_mm
        chosen_f = max(focal_min_mm, min(needed_f, focal_max_mm))
        focal_p.Set(_mm_to_param_value(focal_p, chosen_f))
        notes.append(u"фокусное {:.2f} мм ({}){}".format(
            chosen_f, focal_how,
            u", ограничено диапазоном" if abs(chosen_f - needed_f) > 0.005 else u""))

    hfov, vfov, _optic_reason = _optical_fov(doc, cam, s)
    vfov_default_used = False
    if vfov is None:
        vfov = o["default_vfov_rad"]
        vfov_default_used = True
    if mode == u"area":
        if hfov is not None and needed_hfov > hfov + math.radians(1.0):
            warn_reasons.append(
                u"для {:.0f}% площади помещения нужен угол {:.0f}°, объектив даёт "
                u"{:.0f}° — часть помещения вне кадра".format(
                    o["coverage"] * 100.0, math.degrees(needed_hfov), math.degrees(hfov)))
        if large_room:
            warn_reasons.append(
                u"до стены {:.1f} м, а дальность камеры {:.1f} м — дальняя часть "
                u"помещения не просматривается".format(
                    wall_ft * _M_PER_FT, range_ft * _M_PER_FT))
    elif hfov is not None and needed_hfov < hfov - math.radians(1.0):
        warn_reasons.append(
            u"детализация {:.0f} пикс/м на {:.1f} м недостижима — объектив даёт "
            u"угол не уже {:.0f}° (нужно {:.0f}°)".format(
                o["dori_ppm"], work_ft * _M_PER_FT, math.degrees(hfov),
                math.degrees(needed_hfov)))

    # --- высота
    h_ft = _mounting_height_ft(doc, cam, view, s.get("height_param_name"))
    h_written = False
    if h_ft is None:
        h_ft = o["default_h_ft"]
        hp = _instance_param(cam, s.get("height_param_name"))
        if _writable_double(hp):
            hp.Set(_mm_to_param_value(hp, o["default_h_ft"] * 304.8))
            h_written = True
    if h_ft is None or h_ft <= 0.1:
        return (cam, u"missing_inputs",
                u"нет высоты установки и не задано значение по умолчанию")
    h_eff = h_ft - o["target_off_ft"]
    if h_eff <= 0.1:
        return (cam, u"missing_inputs",
                u"камера ({:.2f} м) не выше плоскости расчёта ({:.2f} м)".format(
                    h_ft * _M_PER_FT, o["target_off_ft"] * _M_PER_FT))
    if vfov is None or vfov <= 1e-4:
        return (cam, u"missing_inputs",
                u"нет вертикального угла обзора и значения по умолчанию")

    # --- наклон
    max_near_ft = o["max_near_ft"]
    tmode = o["tilt_mode"]
    if tmode.startswith(u"верх"):
        tilt = math.atan2(h_eff, work_ft) + vfov / 2.0
        mode_note = u"верх кадра в цель"
    elif tmode.startswith(u"низ"):
        tilt = math.atan2(h_eff, max(max_near_ft, 0.01)) - vfov / 2.0
        mode_note = u"низ кадра по мёртвой зоне"
    else:
        tilt = math.atan2(h_eff, work_ft)
        mode_note = u"ось в цель"
    tilt = max(0.0, min(tilt, math.radians(89.0)))
    tilt_p.Set(_radians_to_param_value(tilt_p, tilt, unit_mode))

    # предупреждение «поднимите камеру» — та же формула, что _near_far_radius
    bottom = tilt + vfov / 2.0
    near_ft = 0.0
    if 1e-3 < bottom < (math.pi / 2.0 - 1e-3):
        near_ft = max(0.0, h_eff / math.tan(bottom))
    if near_ft > max_near_ft + 1e-6:
        warn_reasons.append(u"мёртвая зона {:.2f} м больше допустимой {:.2f} м".format(
            near_ft * _M_PER_FT, max_near_ft * _M_PER_FT))
    if tilt > o["max_tilt_rad"]:
        warn_reasons.append(u"наклон {:.0f}° больше допустимого {:.0f}°".format(
            math.degrees(tilt), math.degrees(o["max_tilt_rad"])))

    if others:
        notes.append(u"учтено камер рядом: {}".format(len(others)))
    if h_written:
        notes.append(u"высота по умолчанию (записана)")
    if vfov_default_used:
        notes.append(u"верт.угол по умолчанию (не найдена оптика)")

    detail = (u"азимут {:.0f}°, до стены {:.2f} м, L={:.2f} м, h={:.2f} м "
              u"(над плоскостью {:.2f} м), гор./верт. угол {}/{:.0f}° -> наклон "
              u"{:.1f}° ({}), мёртвая зона {:.2f} м".format(
                  math.degrees(base) % 360.0, wall_ft * _M_PER_FT,
                  work_ft * _M_PER_FT, h_ft * _M_PER_FT, h_eff * _M_PER_FT,
                  u"{:.0f}".format(math.degrees(hfov)) if hfov else u"?",
                  math.degrees(vfov), math.degrees(tilt), mode_note,
                  near_ft * _M_PER_FT))
    if notes:
        detail += u"; " + u"; ".join(notes)
    if warn_reasons:
        detail += u"; ВНИМАНИЕ: " + u", ".join(warn_reasons)
        return (cam, u"ok_warn", detail)
    return (cam, u"ok", detail)


def _focal_mode(text):
    t = (text or u"").strip().lower()
    if t.startswith(u"пл"):
        return u"area"
    if t.startswith(u"dori") or t.startswith(u"дори") or t.startswith(u"дет"):
        return u"dori"
    return u"auto"


def _other_cameras_in_view(doc, view, s, exclude_ids):
    """Камеры тех же категорий (camera_categories) на виде view, кроме
    exclude_ids — их наведение не меняется, но их покрытие учитывается."""
    cat_ids = resolve_category_ids(doc, s.get("camera_categories") or u"OST_SecurityDevices")
    out = []
    try:
        els = FilteredElementCollector(doc, view.Id).WhereElementIsNotElementType()
    except Exception:
        return out
    for el in els:
        try:
            cat = el.Category
            if cat is None or cat.Id.IntegerValue not in cat_ids:
                continue
            if el.Id.IntegerValue in exclude_ids:
                continue
            if isinstance(el.Location, LocationPoint):
                out.append(el)
        except Exception:
            continue
    return out


def auto_aim_cameras(doc, cameras, view, settings):
    """
    Навести каждую камеру на её помещение (см. заголовок раздела выше):
    по выбору (auto_rotate) ПОВЕРНУТЬ, подобрать и ЗАПИСАТЬ фокусное
    (если это параметр экземпляра) и наклон (tilt_param_name, параметр
    экземпляра). При auto_consider_others камеры наводятся по очереди, и
    площадь, уже покрытая другими камерами на виде (невыбранными — как
    есть, выбранными — после их наведения), при выборе поворота и
    фокусного почти не учитывается. Возвращает [(camera, status, detail)]
    со status: "ok"/"ok_warn" (записано, но есть предупреждения)/
    "no_location"/"no_tilt_param"/"tilt_not_instance"/"tilt_readonly"/
    "no_distance_param"/"bad_geometry"/"no_room"/"no_wall_hit"/
    "missing_inputs"/"error".
    Транзакция — на вызывающей стороне (пишет параметры и поворачивает).
    """
    s = settings
    o = {
        "unit_mode": s.get("angle_unit") or u"авто",
        "default_h_ft": _as_float(s.get("auto_default_height_mm"), 3000.0) * _FT_PER_MM,
        "default_vfov_rad": math.radians(_as_float(s.get("auto_default_vfov_deg"), 30.0)),
        "focal_min_mm": _as_float(s.get("auto_focal_min_mm"), 2.8),
        "focal_max_mm": _as_float(s.get("auto_focal_max_mm"), 12.0),
        "max_tilt_rad": math.radians(_as_float(s.get("auto_max_tilt_deg"), 60.0)),
        "max_near_ft": _as_float(s.get("auto_max_near_zone_mm"), 1500.0) * _FT_PER_MM,
        "rotate_on": _as_bool(s.get("auto_rotate"), False),
        "coverage": max(0.1, min(_as_float(s.get("auto_coverage_pct"), 90.0), 100.0)) / 100.0,
        "tilt_mode": (s.get("auto_tilt_mode") or u"ось").strip().lower(),
        "target_off_ft": _as_float(s.get("target_level_offset_mm"), 0.0) * _FT_PER_MM,
        "focal_mode": _focal_mode(s.get("auto_focal_mode")),
        "dori_ppm": _dori_ppm(s.get("auto_dori_level")),
        "h_res_px": float(_as_int(s.get("camera_h_res_px"), 0)),
    }

    covered = None
    if _as_bool(s.get("auto_consider_others"), False):
        covered = []
        sel_ids = set(c.Id.IntegerValue for c in cameras)
        for other in _other_cameras_in_view(doc, view, s, sel_ids):
            try:
                rec = _coverage_record(doc, other, view, s, o["unit_mode"], o["target_off_ft"])
            except Exception:
                rec = None
            if rec is not None:
                covered.append(rec)

    results = []
    for cam in cameras:
        try:
            res = _auto_aim_one(doc, cam, view, s, o, covered)
        except Exception as ex:
            res = (cam, u"error", u"{}".format(ex))
        results.append(res)
        if covered is not None and res[1] in (u"ok", u"ok_warn"):
            try:
                doc.Regenerate()
                rec = _coverage_record(doc, cam, view, s, o["unit_mode"], o["target_off_ft"])
            except Exception:
                rec = None
            if rec is not None:
                covered.append(rec)
    return results


# ======================================================================
#  ВИД «КАК С КАМЕРЫ»  (3D-перспектива, кнопка CameraPreviewView)
# ======================================================================
#
# Создаёт/обновляет 3D-перспективный вид Revit в точке камеры, смотрящий
# туда же (тот же азимут+наклон, что «Зоны обзора»/«Навести на
# помещение»), с полем зрения, подогнанным под расчётный hfov/vfov этой
# камеры (фокусное + матрица, _optical_fov) через crop box перспективы —
# прямого API «угол обзора камеры» у Revit нет, но т.к. crop box
# перспективы — это сечение пирамиды с вершиной в точке глаза, отношение
# половины ширины/высоты crop box к глубине сечения одинаково на любой
# глубине; поэтому подгонка не трогает Z (ближнюю/дальнюю плоскость,
# выставленную Revit по умолчанию), только X/Y на уже имеющейся глубине —
# это устраняет саму необходимость знать знак/точку отсчёта Z. Идемпотентно
# по имени вида: повторный запуск на той же камере обновляет уже созданный
# вид на месте, а не плодит дубли.

def _camera_view_name(cam):
    label = u""
    try:
        label = _safe_name(cam.Symbol) if cam.Symbol is not None else u""
    except Exception:
        label = u""
    mark = None
    try:
        mp = cam.get_Parameter(BuiltInParameter.ALL_MODEL_MARK)
        mark = mp.AsString() if mp is not None else None
    except Exception:
        mark = None
    parts = [p for p in (label, mark) if p and p.strip()]
    tail = u" ".join(parts) if parts else u"камера"
    return u"СОТ · {} · id{}".format(tail, cam.Id.IntegerValue)


def _find_existing_preview_view(doc, name):
    for v in FilteredElementCollector(doc).OfClass(View3D):
        try:
            if v.IsTemplate or not v.IsPerspective:
                continue
            if Element.Name.GetValue(v) == name:
                return v
        except Exception:
            continue
    return None


def _pick_3d_view_family_type(doc, name):
    types = [t for t in FilteredElementCollector(doc).OfClass(ViewFamilyType)
             if t.ViewFamily == ViewFamily.ThreeDimensional]
    if not types:
        return None
    if name and name.strip():
        want = name.strip()
        for t in types:
            try:
                if Element.Name.GetValue(t) == want:
                    return t
            except Exception:
                continue
    return types[0]


def _camera_level_elevation(doc, cam, view):
    lvl = get_element_level(doc, cam)
    if lvl is not None:
        try:
            return lvl.Elevation
        except Exception:
            pass
    gen = getattr(view, "GenLevel", None)
    if gen is not None:
        try:
            return gen.Elevation
        except Exception:
            pass
    return None


# Глубина плоскости, на которой задаются X/Y рамки перспективного вида
# (CropBox.Max.Z = −это значение), футы (~3 см). Сама по себе на угол
# обзора не влияет — важно только отношение X/Y к ней.
_PREVIEW_CROP_DEPTH_FT = 0.1


def build_camera_preview_view(doc, cam, view, settings):
    """
    Создать либо обновить 3D-перспективный вид, поставленный в точку камеры
    cam и смотрящий туда же, что и она — тот же источник направления/
    наклона, что «Зоны обзора»/«Навести на помещение» (_look_direction +
    rotation_param_name + direction_offset_deg, tilt_param_name), с полем
    зрения, подогнанным под расчётный hfov/vfov (_optical_fov). view —
    активный вид, нужен только чтобы определить уровень камеры, если у неё
    самой уровня нет (как в _mounting_height_ft).

    Возвращает (view3d_или_None, status, detail):
      "ok" — вид создан/обновлён, поле зрения подогнано под оптику камеры;
      "ok_no_optics" — вид создан/обновлён, но без подгонки FOV (нет
        фокусного расстояния/формата матрицы на этой камере — остаётся
        штатное поле зрения Revit для нового вида, либо прежнее для
        обновляемого);
      "no_location" / "bad_geometry" / "no_view_family_type" /
      "create_failed".
    Транзакция — на вызывающей стороне (создаёт/меняет элемент вида).
    """
    s = settings
    if not isinstance(cam.Location, LocationPoint):
        return (None, u"no_location", u"")

    unit_mode = s.get("angle_unit") or u"авто"
    base, dir_note, _fwd = _camera_azimuth(doc, cam, s, unit_mode)
    if base is None:
        return (None, u"bad_geometry",
                u"не удалось определить направление камеры [{}]".format(dir_note))

    notes = []
    tilt = _opt_param_radians(doc, cam, s.get("tilt_param_name"), unit_mode)
    if tilt is None:
        tilt = 0.0
        notes.append(u"наклон не найден на камере — вид горизонтальный")

    p = cam.Location.Point
    h_ft = _mounting_height_ft(doc, cam, view, s.get("height_param_name"))
    if h_ft is None:
        h_ft = _as_float(s.get("auto_default_height_mm"), 3000.0) * _FT_PER_MM
    level_elev = _camera_level_elevation(doc, cam, view)
    eye_z = (level_elev + h_ft) if level_elev is not None else p.Z
    eye = XYZ(p.X, p.Y, eye_z)

    forward = XYZ(math.cos(base) * math.cos(tilt),
                  math.sin(base) * math.cos(tilt),
                  -math.sin(tilt))
    right = XYZ(-math.sin(base), math.cos(base), 0.0)
    up = forward.CrossProduct(right)
    if up.GetLength() < 1e-6:
        return (None, u"bad_geometry", u"вырожденный базис вида (up почти нулевой)")
    up = up.Normalize()
    forward = forward.Normalize()

    vft = _pick_3d_view_family_type(doc, s.get("view3d_type_name"))
    if vft is None:
        return (None, u"no_view_family_type",
                u"в проекте нет типа 3D-вида (ViewFamilyType, ViewFamily.ThreeDimensional)")

    name = _camera_view_name(cam)
    v3d = _find_existing_preview_view(doc, name)
    created = v3d is None
    if v3d is None:
        try:
            v3d = View3D.CreatePerspective(doc, vft.Id)
        except Exception as ex:
            return (None, u"create_failed", u"{}".format(ex))
        try:
            v3d.Name = name
        except Exception as ex:
            # имя занято (например, обычным видом) — без имени повторный
            # запуск не найдёт этот вид и создаст ещё один
            notes.append(u"не удалось назвать вид «{}» ({}) — повторный запуск "
                         u"создаст новый вид".format(name, ex))

    try:
        v3d.SetOrientation(ViewOrientation3D(eye, up, forward))
    except Exception as ex:
        return (v3d, u"create_failed", u"SetOrientation: {}".format(ex))

    # глаз стоит в точке вставки камеры — внутри её корпуса: скрыть саму
    # камеру и её вложенные семейства (основание/корпус), иначе они
    # загораживают кадр
    hide_ids = [cam.Id]
    try:
        hide_ids.extend(list(cam.GetSubComponentIds()))
    except Exception:
        pass
    try:
        can = [i for i in hide_ids if doc.GetElement(i) is not None
               and doc.GetElement(i).CanBeHidden(v3d)]
        if can:
            v3d.HideElements(List[ElementId](can))
    except Exception as ex:
        notes.append(u"не удалось скрыть саму камеру в виде ({})".format(ex))

    hfov, vfov, optic_reason = _optical_fov(doc, cam, s)
    status = u"ok"
    detail = u"азимут {:.0f}°, наклон {:.0f}°".format(
        math.degrees(base) % 360.0, math.degrees(tilt))

    if hfov is not None and vfov is not None:
        try:
            v3d.CropBoxActive = True
            box = v3d.CropBox
            # X/Y рамки перспективы Revit откладывает на плоскости Max.Z
            # (ближняя, отрицательная — вид смотрит в −Z): Xmax = −Zmax·tg(h/2).
            # Глубину задаём сами, а не берём штатную: раньше при штатном
            # |Max.Z| < 0.1 фт подставлялось 10 фт, а Max.Z оставался
            # прежним — рамка выходила в десятки раз шире, и вид показывал
            # чуть ли не пол-здания вместо кадра камеры.
            z_max = -_PREVIEW_CROP_DEPTH_FT
            z_min = box.Min.Z if box.Min.Z < z_max - 1.0 else z_max - 1000.0
            half_w = _PREVIEW_CROP_DEPTH_FT * math.tan(min(hfov, math.radians(178.0)) / 2.0)
            half_h = _PREVIEW_CROP_DEPTH_FT * math.tan(min(vfov, math.radians(178.0)) / 2.0)
            box.Min = XYZ(-half_w, -half_h, z_min)
            box.Max = XYZ(half_w, half_h, z_max)
            v3d.CropBox = box
            detail += u", угол {:.0f}°×{:.0f}°".format(
                math.degrees(hfov), math.degrees(vfov))
            # диагностика: что Revit в итоге хранит в crop box (если Revit
            # что-то пересчитал — углы в скобках разойдутся с расчётными)
            try:
                rb = v3d.CropBox
                rd = abs(rb.Max.Z)
                if rd > 1e-6:
                    detail += (u" [crop: X {:.2f}…{:.2f}, Y {:.2f}…{:.2f}, "
                               u"Z {:.2f}…{:.2f} фт -> по глубине |Max.Z| "
                               u"{:.0f}°×{:.0f}°]".format(
                                   rb.Min.X, rb.Max.X, rb.Min.Y, rb.Max.Y,
                                   rb.Min.Z, rb.Max.Z,
                                   math.degrees(2.0 * math.atan((rb.Max.X - rb.Min.X) / 2.0 / rd)),
                                   math.degrees(2.0 * math.atan((rb.Max.Y - rb.Min.Y) / 2.0 / rd))))
            except Exception:
                pass
        except Exception as ex:
            status = u"ok_no_optics"
            detail += u"; не удалось подогнать crop box: {}".format(ex)
    else:
        status = u"ok_no_optics"
        detail += u"; поле зрения не подогнано под объектив ({})".format(optic_reason)

    detail += u", глаз h={:.2f} м".format(h_ft * _M_PER_FT)
    if notes:
        detail += u"; " + u"; ".join(notes)
    detail += u"; {}".format(u"создан" if created else u"обновлён")
    return (v3d, status, detail)


# ======================================================================
#  НАСТРОЙКИ  (окно + хранение, по образцу room_info_settings.py)
# ======================================================================

import os
import io
import json

import clr
clr.AddReference('PresentationFramework')
clr.AddReference('PresentationCore')

from pyrevit import forms
from lowlife import settings_transfer

from System.Windows import (
    Window, WindowStartupLocation, Thickness,
    FontWeights, HorizontalAlignment, TextWrapping
)
from System.Windows.Controls import (
    StackPanel, TextBlock, TextBox, Button, Orientation, DockPanel, Dock,
    ScrollViewer, ScrollBarVisibility
)
from System.Windows.Media import Brushes

SETTINGS_FILE_NAME = "LowLifeCameraFov_settings.json"

# (ключ, заголовок раздела, подпись поля, пояснение, значение по умолчанию, обязательное)
TEXT_FIELDS = [
    (
        "camera_categories",
        u"⓪ Что выбирать",
        u"Категории камер для фильтра выбора",
        u"Через запятую. Имя BuiltInCategory (OST_SecurityDevices, "
        u"OST_CommunicationDevices, OST_DataDevices, OST_ElectricalEquipment, "
        u"OST_GenericModel) и/или русское имя категории как в дереве "
        u"«Категории» («Оборудование систем безопасности»). Кнопка даст "
        u"выбрать только элементы этих категорий. Если после нажатия ничего "
        u"не выделяется — камера не в этой категории; посмотрите её "
        u"категорию в свойствах и впишите сюда.",
        u"OST_SecurityDevices", True
    ),
    (
        "focal_length_param_name",
        u"① Параметры камеры (в этой модели)",
        u"Параметр «фокусное расстояние», мм",
        u"Имя параметра объектива — экземпляра ИЛИ типа (сначала ищется "
        u"на экземпляре, если там пусто/нет — на его типе). Горизонтальный "
        u"и вертикальный угол обзора — ВСЕГДА расчётные (не вписываются "
        u"вручную): θ = 2·arctg(размер матрицы / (2·f)) — так они не "
        u"разойдутся с реальным объективом, особенно у вариофокального, "
        u"где угол меняется вместе с фокусным расстоянием. Тип «Длина» → "
        u"пересчёт из футов; «Число» → как есть, в мм. Для вариофокального "
        u"объектива обычно это параметр ЭКЗЕМПЛЯРА (сфокусировано по месту, "
        u"отличается у одинаковых по типу камер) — берётся текущее значение. "
        u"Если разные семейства камер в проекте называют этот параметр "
        u"по-разному — перечислите все имена через «;» (проверяются по "
        u"порядку, первое найденное на камере побеждает).",
        u"", True
    ),
    (
        "sensor_format_param_name",
        u"",
        u"Параметр «формат матрицы» (необязательно)",
        u"Имя ТЕКСТОВОГО параметра камеры (экземпляра или типа) со "
        u"значением формата матрицы — тем же, что принимает поле «Формат "
        u"матрицы» ниже («1/2.8», «5.37x4.04» и т.п.). Нужен, только если "
        u"разные типы/модели камер в проекте отличаются матрицей и она уже "
        u"внесена в семейство. Пусто — берётся общее значение из поля "
        u"«Формат матрицы» для всех камер сразу. Несколько имён (у разных "
        u"семейств камер) — через «;».",
        u"", False
    ),
    (
        "sensor_format",
        u"",
        u"Формат матрицы (общий, если нет параметра выше)",
        u"Нужен вместе с фокусным расстоянием, чтобы посчитать угол обзора. "
        u"Оптический формат — «1/2.8», «1/3», «1/1.8», «2/3», «1» (по "
        u"таблице диагоналей, кадр 16:9 — как у IP-камер; для кадра 4:3 "
        u"допишите «1/3 4:3»); либо явные размеры активной области «ШхВ» в "
        u"мм — «5.37x4.04»; либо одна ширина «5.37» (высота — по 16:9). "
        u"Обязательно, "
        u"если не заполнен параметр формата матрицы выше хотя бы у части "
        u"камер.",
        u"", True
    ),
    (
        "distance_param_name",
        u"",
        u"Параметр «дальность» (макс. радиус зоны)",
        u"Имя параметра камеры с максимальной дальностью обзора —  "
        u"экземпляра ИЛИ типа. Должен быть параметром типа «Длина» (иначе "
        u"значение уедет по единицам). Задаёт дальнюю границу зоны, если "
        u"она не ограничена расчётом по наклону/вертикальному углу. "
        u"«Навести на помещение» берёт её как предел рабочего расстояния: "
        u"площадь помещения дальше неё при повороте и подборе фокусного не "
        u"учитывается, а ось кадра наводится не дальше неё. Обычно это "
        u"параметр ТИПА — паспортная дальность модели камеры. "
        u"Несколько имён (у разных семейств камер) — через «;».",
        u"УГО_ПВ_Дистанция до объекта", True
    ),
    (
        "angle_unit",
        u"",
        u"Единицы параметров наклона и поворота",
        u"«авто» — по типу параметра (тип «Угол» → радианы, иначе число "
        u"трактуется как градусы). «градусы» / «радианы» — принудительно. "
        u"Горизонтальный и вертикальный угол обзора это поле не "
        u"затрагивает — они расчётные, единиц не имеют (сразу радианы).",
        u"авто", False
    ),
    (
        "height_param_name",
        u"",
        u"Параметр «высота установки» над уровнем",
        u"Имя параметра высоты монтажа камеры (тип «Длина») — экземпляра "
        u"ИЛИ типа; обычно экземпляра (у каждой камеры своя высота). Если "
        u"пусто — высота берётся как отметка точки вставки минус отметка "
        u"уровня камеры. Нужна для расчёта ближней мёртвой зоны и дальней "
        u"границы — без неё (и без наклона ниже) зона всегда плоский "
        u"сектор от самой точки камеры, без мёртвой зоны. Несколько имён "
        u"(у разных семейств камер) — через «;».",
        u"", False
    ),
    (
        "tilt_param_name",
        u"",
        u"Параметр «наклон оптической оси вниз»",
        u"Имя углового параметра наклона оси камеры вниз от горизонта — "
        u"экземпляра ИЛИ типа (0 — камера смотрит горизонтально). Пусто — "
        u"наклон не учитывается, зона строится как плоский сектор без "
        u"мёртвой зоны, даже если высота задана. Подобрать автоматически "
        u"под помещение можно кнопкой «Навести на помещение». Несколько "
        u"имён (у разных семейств камер, если наклон называется по-разному) "
        u"— через «;».",
        u"", False
    ),
    (
        "rotation_param_name",
        u"",
        u"Параметр «поворот камеры» (угол внутри семейства)",
        u"Имя углового параметра камеры (экземпляра ИЛИ типа), которым "
        u"камера разворачивается НЕ поворотом самого экземпляра, а внутри "
        u"семейства (тогда FacingOrientation не меняется, и без этого поля "
        u"все зоны смотрят в одну сторону). Его значение прибавляется к "
        u"направлению (против часовой стрелки). В исходном Dynamo-скрипте "
        u"это был «Вращение (поворот)». Пусто — если камера разворачивается "
        u"поворотом экземпляра в модели. Если у разных семейств камер этот "
        u"параметр называется по-разному (например, «Вращение (поворот)» у "
        u"одних, «УГО_Поворот» у других) — перечислите все варианты через "
        u"«;»: «Вращение (поворот);УГО_Поворот». Как значение переводится "
        u"в направление — три поля ниже.",
        u"", False
    ),
    (
        "rotation_zero_deg",
        u"",
        u"Поворот 0 — куда смотрит камера, ° от «вперёд»",
        u"Куда смотрит камера, когда параметр поворота = 0: угол от "
        u"направления «вперёд» семейства (от основания, от стены), против "
        u"часовой стрелки. Обычно 0 (при 0 камера смотрит вперёд). Для "
        u"поворотной камеры на настенном основании, у которой (на плане, "
        u"стена снизу) 0 — вправо вдоль стены, 90 — вверх от стены, 180 — "
        u"влево, впишите -90 (и «по часовой» — «нет»); если наоборот "
        u"(0 — влево, 180 — вправо) — 90 и «по часовой» — «да».",
        u"0", False
    ),
    (
        "rotation_clockwise",
        u"",
        u"Поворот растёт по часовой стрелке (да/нет)",
        u"«нет» — большее значение параметра поворачивает камеру против "
        u"часовой стрелки (в плане), «да» — по часовой. Для камеры «0 — "
        u"вправо, 90 — от стены, 180 — влево» (стена снизу) — «нет», для "
        u"«0 — влево, 180 — вправо» — «да». Если после «Зон обзора» зоны "
        u"смотрят зеркально — поменяйте и это поле, и знак поля выше "
        u"(90 <-> -90).",
        u"нет", False
    ),
    (
        "rotation_range_deg",
        u"",
        u"Диапазон поворота, ° (мин-макс, необязательно)",
        u"Пределы, в которых поворачивается камера внутри семейства, "
        u"например «0-180» — тогда «Навести на помещение» выбирает "
        u"направление только из них (камера не отвернётся в стену) и "
        u"записывает значение в этом диапазоне. Пусто — без ограничений.",
        u"", False
    ),
    (
        "direction_offset_deg",
        u"",
        u"Доворот направления «взгляда», градусы",
        u"Фиксированная поправка направления (одинаковая для всех камер, "
        u"против часовой стрелки), если геометрия камеры в семействе "
        u"смотрит не «вперёд» относительно FacingOrientation. Обычно 0. "
        u"Индивидуальный разворот каждой камеры — это поле выше "
        u"«Параметр поворот камеры», а не это.",
        u"0", False
    ),
    (
        "target_level_offset_mm",
        u"② Плоскость расчёта и форма зоны",
        u"Высота плоскости расчёта над уровнем, мм",
        u"На какой высоте считать зону: 0 — пол; 1500 — плоскость лиц; "
        u"800 — рабочие поверхности. Влияет на ближнюю/дальнюю границу при "
        u"учёте высоты установки.",
        u"0", False
    ),
    (
        "draw_dead_zone",
        u"",
        u"Показывать ближнюю мёртвую зону (да/нет)",
        u"«да» — при заданных высоте/наклоне/вертикальном угле зона рисуется "
        u"кольцевым сектором (с вырезом под камерой). «нет» — всегда сплошной "
        u"сектор от точки камеры.",
        u"да", False
    ),
    (
        "ray_count",
        u"",
        u"Детализация дуги (число лучей на сектор)",
        u"Больше — глаже дуга и точнее обрезка по помещению, но тяжелее "
        u"область заливки. 64–128 обычно достаточно.",
        u"96", False
    ),
    (
        "clip_to_rooms",
        u"③ Обрезка по помещению",
        u"Резать зону по границе помещения (да/нет)",
        u"«да» — зона обрезается по контуру Room из связанной модели, в "
        u"котором стоит камера. Учитываются вогнутые помещения и «дыры» — "
        u"внутренние контуры, которые сам Revit вырезает в границе "
        u"помещения вокруг колонн с отделкой, если она отмечена «граница "
        u"помещения» (обычный случай для АР) — отдельно колонны в кнопке "
        u"ничем не обрабатываются, тень от них берётся прямо из контура "
        u"помещения. «нет» — зона строится без обрезки.",
        u"да", False
    ),
    (
        "room_boundary",
        u"",
        u"Граница помещения",
        u"«отделка» — по чистовой поверхности стен (Finish); «центр» — по "
        u"осям стен (Center). Если для конкретного помещения контур так и "
        u"не построился (открытый/повреждённый контур) — используется "
        u"резервный способ: сечение уже готового тела помещения, которое "
        u"сам Revit строит для площади/объёма — работает для помещений "
        u"любой формы (вогнутых, с несколькими контурами, с дугами).",
        u"отделка", False
    ),
    (
        "fill_type_name",
        u"④ Оформление",
        u"Тип области заливки (FilledRegion)",
        u"Имя типа штриховки для зоны. Пусто — берётся первый доступный тип "
        u"в проекте. Прозрачность/цвет настраиваются в самом типе.",
        u"", False
    ),
    (
        "line_subcategory",
        u"",
        u"Подкатегория линий контура",
        u"Имя подкатегории категории «Линии» для границы зоны (создаётся "
        u"автоматически). По ней же именуется стиль дуг DORI "
        u"(«… · DORI»).",
        u"СОТ_Зона обзора", False
    ),
    (
        "zone_tag",
        u"",
        u"Метка зоны в параметре «Комментарии»",
        u"Служебная строка, по которой кнопка находит и удаляет прежние зоны "
        u"этих камер при повторном запуске. Формат записи — «метка|Id камеры».",
        u"CCTV_FOV", True
    ),
    (
        "draw_dori",
        u"⑤ Зоны DORI (EN 62676-4, необязательно)",
        u"Рисовать дуги DORI (да/нет)",
        u"«да» — добавляет концентрические дуги на расстояниях "
        u"идентификации / распознавания / наблюдения / обнаружения "
        u"(250 / 125 / 63 / 25 пикс/м).",
        u"нет", False
    ),
    (
        "camera_h_res_param_name",
        u"",
        u"Параметр «горизонтальное разрешение» (необязательно)",
        u"Имя параметра камеры с горизонтальным разрешением матрицы в "
        u"пикселях — обычно параметр ТИПА (характеристика модели; ищется и "
        u"на экземпляре, и на типе). «Целое», «Число» или текст вида «1920» "
        u"/ «1920x1080». Если параметр не задан, не найден или пуст — "
        u"берётся общее значение из поля ниже. Несколько имён (у разных "
        u"семейств камер) — через «;».",
        u"", False
    ),
    (
        "camera_h_res_px",
        u"",
        u"Горизонтальное разрешение матрицы, пикс (общее)",
        u"Нужно для дуг DORI и для подбора фокусного по DORI (раздел ⑥), "
        u"если у камеры нет параметра разрешения (поле выше). "
        u"Например 1920 (Full HD), 2560, 3840. "
        u"Расстояние: d = H / (2 · пикс/м · tg(гор.угол / 2)).",
        u"", False
    ),
    (
        "auto_rotate",
        u"⑥ Автонаведение (кнопка «Навести на помещение»)",
        u"Поворачивать камеру автоматически (да/нет)",
        u"«нет» (обычный режим) — камеру ориентируете вы, кнопка подбирает "
        u"только фокусное и наклон. «да» — кнопка сама разворачивает камеру "
        u"туда, где кадр самого "
        u"широкого угла (минимальное фокусное) накрывает наибольшую площадь "
        u"помещения в пределах дальности: у камеры в углу — по диагонали, "
        u"у камеры на стене — перпендикулярно стене. Поворот пишется в "
        u"параметр поворота камеры (если он задан и это параметр "
        u"экземпляра), иначе поворачивается сам экземпляр семейства.",
        u"нет", False
    ),
    (
        "auto_consider_others",
        u"",
        u"Учитывать другие камеры (да/нет)",
        u"«да» — камеры наводятся по очереди, и площадь, которую уже видят "
        u"другие камеры на этом виде (невыбранные — как они стоят сейчас, "
        u"выбранные — после наведения), при выборе поворота и фокусного "
        u"почти не учитывается: соседние камеры расходятся по разным "
        u"направлениям, а не смотрят в одну точку. Работает медленнее.",
        u"нет", False
    ),
    (
        "auto_focal_mode",
        u"",
        u"Фокусное: авто / площадь / DORI",
        u"«площадь» — самый узкий угол, при котором в кадре заданная ниже "
        u"доля площади помещения. «DORI» — чтобы на рабочем расстоянии "
        u"(до стены, но не дальше дальности камеры) была заданная ниже "
        u"детализация; нужно разрешение матрицы (раздел ⑤). «авто» — DORI, "
        u"если стена дальше дальности камеры (паркинг, склад), иначе "
        u"площадь.",
        u"авто", False
    ),
    (
        "auto_dori_level",
        u"",
        u"Детализация для фокусного по DORI",
        u"обнаружение (25 пикс/м) / наблюдение (63) / распознавание (125) "
        u"/ идентификация (250) или число пикс/м. Фокусное подбирается "
        u"так, чтобы кадр на рабочем расстоянии был шириной "
        u"разрешение / пикс_на_м.",
        u"распознавание", False
    ),
    (
        "auto_coverage_pct",
        u"",
        u"Какую долю площади помещения держать в кадре, %",
        u"Фокусное подбирается как самый узкий угол вокруг направления "
        u"камеры, при котором в кадре эта доля площади помещения (в пределах "
        u"дальности). 100 — всё помещение (у камеры на стене почти всегда "
        u"упрётся в минимальное фокусное), 80–90 — можно отдать углы у "
        u"самой камеры ради большей детализации вдали.",
        u"90", False
    ),
    (
        "auto_tilt_mode",
        u"",
        u"Как считать наклон: ось / верх / низ",
        u"«ось» — ось кадра смотрит в точку на плоскости расчёта у дальней "
        u"стены (или на дальности, если стена дальше): наклон = "
        u"arctg(h / L). «верх» — туда же приходится верхний край кадра "
        u"(камера смотрит круче, видно больше пола под собой). «низ» — "
        u"нижний край кадра даёт мёртвую зону из поля «Предупреждать, если "
        u"мёртвая зона больше». h — высота камеры над плоскостью расчёта "
        u"(раздел ②).",
        u"ось", False
    ),
    (
        "auto_default_height_mm",
        u"",
        u"Высота установки по умолчанию, мм",
        u"Используется кнопкой «Навести на помещение», только если у "
        u"конкретной камеры высоту не удалось определить (нет параметра "
        u"высоты и нет уровня для расчёта по отметке) — тогда это значение "
        u"записывается в параметр высоты (если он есть на экземпляре).",
        u"3000", False
    ),
    (
        "auto_default_vfov_deg",
        u"",
        u"Вертикальный угол обзора по умолчанию, °",
        u"Используется той же кнопкой, только если у камеры не нашёлся "
        u"вертикальный угол (ни параметром, ни из фокусного+матрицы) — "
        u"записывается в параметр вертикального угла (если он есть на "
        u"экземпляре). Возьмите из паспорта объектива/камеры.",
        u"30", False
    ),
    (
        "auto_focal_min_mm",
        u"",
        u"Автоподбор фокусного — минимум, мм",
        u"«Навести на помещение» подбирает фокусное (если оно параметр "
        u"ЭКЗЕМПЛЯРА этой камеры) так, чтобы в кадре была заданная выше доля "
        u"площади помещения, и записывает его — результат клампится в этот "
        u"диапазон (непрерывный вариофокал). По минимуму считается и самый "
        u"широкий угол для поворота камеры. Если фокусное — параметр типа, "
        u"оно не трогается, используется то, что уже на камере.",
        u"2.8", False
    ),
    (
        "auto_focal_max_mm",
        u"",
        u"Автоподбор фокусного — максимум, мм",
        u"Верхняя граница того же диапазона.",
        u"12", False
    ),
    (
        "auto_max_tilt_deg",
        u"",
        u"Предупреждать, если наклон больше, °",
        u"После подбора наклона под помещение — если получившийся наклон "
        u"больше этого значения, статус камеры в отчёте станет "
        u"«с предупреждением»: слишком крутой наклон обычно значит, что "
        u"камеру стоит установить выше.",
        u"60", False
    ),
    (
        "auto_max_near_zone_mm",
        u"",
        u"Предупреждать, если мёртвая зона больше, мм",
        u"Так же — если получившаяся ближняя мёртвая зона (не видно под "
        u"камерой) больше этого значения, отчёт предупредит: поднимите "
        u"камеру выше — это уменьшает мёртвую зону при том же дальнем "
        u"крае обзора. В режиме наклона «низ» — это же значение задаёт "
        u"желаемую мёртвую зону.",
        u"1500", False
    ),
    (
        "view3d_type_name",
        u"⑦ Вид как с камеры",
        u"Тип 3D-вида (необязательно)",
        u"Имя ViewFamilyType для создаваемого перспективного вида. Пусто — "
        u"берётся первый доступный 3D-тип в проекте.",
        u"", False
    ),
]

PLAIN_LABELS = {key: label for key, _s, label, _h, _d, _r in TEXT_FIELDS}


def _settings_file_path():
    appdata = os.environ.get("APPDATA") or os.path.expanduser("~")
    folder = os.path.join(appdata, "pyRevit")
    if not os.path.isdir(folder):
        try:
            os.makedirs(folder)
        except Exception:
            pass
    return os.path.join(folder, SETTINGS_FILE_NAME)


def _read_all():
    path = _settings_file_path()
    if not os.path.isfile(path):
        return {}
    try:
        with io.open(path, "r", encoding="utf-8") as f:
            text = f.read()
        if not text.strip():
            return {}
        return json.loads(text)
    except Exception:
        return {}


def _write_all(data):
    path = _settings_file_path()
    try:
        with io.open(path, "w", encoding="utf-8") as f:
            f.write(unicode(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True)))
    except Exception:
        forms.alert(u"Не удалось сохранить настройки зон обзора в файл:\n{}".format(path))


def load_saved_values():
    saved = _read_all()
    return {key: saved.get(key, default)
            for key, _s, _label, _hint, default, _req in TEXT_FIELDS}


def save_values(values):
    data = _read_all()
    data.update(values)
    _write_all(data)


def require(settings, keys):
    """Останавливает скрипт через forms.alert(exitscript=True), если какие-то
    из перечисленных ключей не заполнены."""
    missing = [PLAIN_LABELS.get(k, k) for k in keys
               if not (settings.get(k) and unicode(settings.get(k)).strip())]
    if missing:
        forms.alert(
            u"Не заполнены обязательные настройки зон обзора:\n\n{}\n\n"
            u"Откройте настройки: Shift+клик по кнопке «Зоны обзора».".format(
                u"\n".join(missing)
            ),
            exitscript=True
        )


def show_settings_form(values):
    result = {"values": None}

    win = Window()
    win.Title = u"Настройки: Зоны обзора видеокамер (СОТ)"
    win.Width = 820
    win.Height = 720
    win.WindowStartupLocation = WindowStartupLocation.CenterScreen

    outer = DockPanel()
    outer.LastChildFill = True

    root = StackPanel()
    root.Margin = Thickness(16)

    title = TextBlock()
    title.Text = u"Параметры расчёта зоны обзора"
    title.FontSize = 16
    title.FontWeight = FontWeights.Bold
    title.Margin = Thickness(0, 0, 0, 4)
    root.Children.Add(title)

    hint = TextBlock()
    hint.Text = (u"Сначала кнопка, потом выбор камер (фильтр — только «Охранная "
                 u"сигнализация»). Значения сохраняются между запусками.")
    hint.FontSize = 11
    hint.Foreground = Brushes.Gray
    hint.TextWrapping = TextWrapping.Wrap
    hint.Margin = Thickness(0, 0, 0, 10)
    root.Children.Add(hint)

    boxes = {}

    for key, section_title, label_text, hint_text, _default, required in TEXT_FIELDS:
        if section_title:
            section = TextBlock()
            section.Text = section_title
            section.FontWeight = FontWeights.Bold
            section.Margin = Thickness(0, 16, 0, 2)
            root.Children.Add(section)

        label = TextBlock()
        label.Text = label_text + (u" *" if required else u"")
        label.Margin = Thickness(0, 8, 0, 2)
        label.TextWrapping = TextWrapping.Wrap
        root.Children.Add(label)

        box = TextBox()
        box.Text = values.get(key, "")
        box.Padding = Thickness(4)
        root.Children.Add(box)
        boxes[key] = box

        h = TextBlock()
        h.Text = hint_text
        h.FontSize = 11
        h.Foreground = Brushes.Gray
        h.TextWrapping = TextWrapping.Wrap
        h.Margin = Thickness(0, 2, 0, 0)
        root.Children.Add(h)

    required_hint = TextBlock()
    required_hint.Text = u"* обязательные поля"
    required_hint.FontSize = 11
    required_hint.Foreground = Brushes.Gray
    required_hint.Margin = Thickness(0, 12, 0, 0)
    root.Children.Add(required_hint)

    buttons = StackPanel()
    buttons.Orientation = Orientation.Horizontal
    buttons.HorizontalAlignment = HorizontalAlignment.Right
    buttons.Margin = Thickness(16, 8, 16, 12)
    DockPanel.SetDock(buttons, Dock.Bottom)

    reset_btn = Button()
    reset_btn.Content = u"Сбросить"
    reset_btn.Padding = Thickness(10, 4, 10, 4)
    reset_btn.Margin = Thickness(0, 0, 8, 0)

    cancel_btn = Button()
    cancel_btn.Content = u"Отмена"
    cancel_btn.Padding = Thickness(10, 4, 10, 4)
    cancel_btn.Margin = Thickness(0, 0, 8, 0)

    ok_btn = Button()
    ok_btn.Content = u"Сохранить"
    ok_btn.Padding = Thickness(10, 4, 10, 4)
    ok_btn.FontWeight = FontWeights.Bold

    def on_reset(sender, args):
        for key, _s, _label, _hint, default, _req in TEXT_FIELDS:
            boxes[key].Text = default

    def on_ok(sender, args):
        result["values"] = {key: box.Text for key, box in boxes.items()}
        win.Close()

    def on_cancel(sender, args):
        win.Close()

    reset_btn.Click += on_reset
    ok_btn.Click += on_ok
    cancel_btn.Click += on_cancel

    buttons.Children.Add(reset_btn)
    buttons.Children.Add(cancel_btn)
    buttons.Children.Add(ok_btn)

    def _on_settings_imported():
        result["values"] = settings_transfer.RELOAD
        win.Close()

    settings_transfer.add_transfer_buttons(
        buttons, _read_all, _write_all, u"зон обзора", _on_settings_imported
    )

    scroll = ScrollViewer()
    scroll.VerticalScrollBarVisibility = ScrollBarVisibility.Auto
    scroll.Content = root

    outer.Children.Add(buttons)
    outer.Children.Add(scroll)

    win.Content = outer
    win.ShowDialog()

    return result["values"]


def get_settings_interactive():
    """Окно настроек: сохраняет и возвращает значения; None при отмене.
    Открывается по Shift+клику на кнопке «Зоны обзора»."""
    while True:
        saved = load_saved_values()
        edited = show_settings_form(saved)

        if edited == settings_transfer.RELOAD:
            continue
        if edited is None:
            return None

        save_values(edited)
        return edited


def get_settings_silent():
    """Сохранённые значения без показа окна (или значения по умолчанию)."""
    return load_saved_values()
