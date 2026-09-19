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
рисует зону, а ПОДБИРАЕТ и записывает наклон камеры (параметр экземпляра)
так, чтобы дальний край конуса приходился на границу её помещения по
направлению взгляда. Единственное место в модуле, которое пишет
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

    return fallback


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
    try:
        if _SpecTypeId is not None and param.Definition.GetDataType() == _SpecTypeId.Angle:
            return v
    except Exception:
        pass
    try:
        if _ParameterType is not None and param.Definition.ParameterType == _ParameterType.Angle:
            return v
    except Exception:
        pass
    return math.radians(v)


def _opt_param_radians(doc, el, name, unit_mode):
    """
    Угловой параметр по имени в радианах или None, если имя пустое / нет
    значения ни на экземпляре, ни на типе (см. _find_param).
    """
    p = _find_param(doc, el, name)
    if p is None or not p.HasValue or p.StorageType != StorageType.Double:
        return None
    return _param_radians(p, unit_mode)


# --- угол обзора из оптики (фокусное расстояние + матрица) --------------

# Оптический формат матрицы -> (ширина, высота) активной области, мм.
# Значения номинальные (историческое «дюймовое» обозначение), при
# необходимости задайте размеры явно как «ШхВ» (например «5.37x4.04»).
_SENSOR_FORMATS = {
    u"1/4":   (3.60, 2.70),
    u"1/3.6": (4.00, 3.00),
    u"1/3.2": (4.54, 3.42),
    u"1/3":   (4.80, 3.60),
    u"1/2.9": (4.96, 3.72),
    u"1/2.8": (5.37, 4.04),
    u"1/2.7": (5.37, 4.04),
    u"1/2.5": (5.76, 4.29),
    u"1/2.3": (6.17, 4.55),
    u"1/2":   (6.40, 4.80),
    u"1/1.9": (6.74, 5.05),
    u"1/1.8": (7.18, 5.32),
    u"1/1.7": (7.60, 5.70),
    u"2/3":   (8.80, 6.60),
    u"1/1.2": (10.67, 8.00),
    u"1":     (12.80, 9.60),
}


def _parse_sensor(text):
    """
    «Формат матрицы» -> (ширина_мм, высота_мм). Принимает:
      «1/2.8», «1/3"», «2/3»  — по таблице оптических форматов;
      «5.37x4.04», «5,37*4,04» — явные размеры;
      «5.37» — только ширина (высота считается как 3/4 ширины).
    None, если распознать не удалось.
    """
    if not text:
        return None
    s = unicode(text).strip().strip(u'"').strip(u'”')
    s = s.replace(u",", u".").replace(u" ", u"").lower()
    if not s:
        return None
    if s in _SENSOR_FORMATS:
        return _SENSOR_FORMATS[s]
    for sep in (u"x", u"×", u"*"):
        if sep in s:
            a, _, b = s.partition(sep)
            try:
                return (float(a), float(b))
            except Exception:
                return None
    try:
        w = float(s)
        return (w, w * 3.0 / 4.0)
    except Exception:
        return None


def _length_param_mm(param):
    """Значение параметра длины в миллиметрах. Тип «Длина» -> из футов в мм;
    иначе значение берётся как есть (считаем, что уже в мм)."""
    v = param.AsDouble()
    try:
        if _SpecTypeId is not None and param.Definition.GetDataType() == _SpecTypeId.Length:
            return v * 304.8
    except Exception:
        pass
    try:
        if _ParameterType is not None and param.Definition.ParameterType == _ParameterType.Length:
            return v * 304.8
    except Exception:
        pass
    return v


def _is_length_param(param):
    try:
        if _SpecTypeId is not None and param.Definition.GetDataType() == _SpecTypeId.Length:
            return True
    except Exception:
        pass
    try:
        if _ParameterType is not None and param.Definition.ParameterType == _ParameterType.Length:
            return True
    except Exception:
        pass
    return False


def _is_angle_param(param):
    try:
        if _SpecTypeId is not None and param.Definition.GetDataType() == _SpecTypeId.Angle:
            return True
    except Exception:
        pass
    try:
        if _ParameterType is not None and param.Definition.ParameterType == _ParameterType.Angle:
            return True
    except Exception:
        pass
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
    ("distance_param_name", u"Дальность",
     (u"length",), True, False),
    ("height_param_name", u"Высота установки",
     (u"length",), False, False),
    ("tilt_param_name", u"Наклон оптической оси вниз",
     (u"angle", u"number"), False, True),
    ("rotation_param_name", u"Поворот камеры (внутри семейства)",
     (u"angle", u"number"), False, False),
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
    all_params = inst_params + type_params

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
                elif must_be_instance and level == u"тип":
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
    offset_deg = _as_float(settings.get(u"direction_offset_deg"), 0.0)
    unit_mode = settings.get(u"angle_unit") or u"авто"
    d, dir_note = _look_direction(el, offset_deg)
    if d is not None:
        base = math.atan2(d.Y, d.X)
        rot = _opt_param_radians(doc, el, settings.get(u"rotation_param_name"), unit_mode)
        if rot:
            base += rot
            dir_note = u"{} + поворот {:.1f}°".format(dir_note, math.degrees(rot))
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

    d, dir_note = _look_direction(cam, offset_deg)
    if d is None:
        return (cam, u"bad_geometry",
                u"не удалось определить направление камеры [{}]".format(dir_note))
    base = math.atan2(d.Y, d.X)

    # индивидуальный разворот камеры параметром внутри семейства
    rot = _opt_param_radians(doc, cam, s.get("rotation_param_name"), unit_mode)
    if rot:
        base += rot
        dir_note = u"{} + поворот {:.1f}°".format(dir_note, math.degrees(rot))

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

    if dori_style is not None and h_res > 0:
        _draw_dori(doc, view, center, base, half, h_res, hfov, max_r, z, dori_style)

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
#  АВТОНАВЕДЕНИЕ: НАКЛОН ПО РАЗМЕРУ ПОМЕЩЕНИЯ (кнопка «Навести на помещение»)
# ======================================================================
#
# Отдельная кнопка, не «Зоны обзора»: сама зона — только чтение и отрисовка,
# автонаведение — единственное место в СОТ, где кнопка ЗАПИСЫВАЕТ значения
# на камеру. Логика: вертикальный угол обзора — это свойство объектива
# (фиксированное, известное заранее), высота установки — факт монтажа;
# единственное, что имеет смысл ПОДБИРАТЬ под конкретное помещение — это
# наклон, чтобы дальний край конуса приходился на дальнюю стену по
# направлению взгляда камеры:
#
#   far = h / tg(наклон − верт.угол/2)  =>  наклон = arctg(h / far) + верт.угол/2
#
# где far — расстояние от камеры до границы помещения ВДОЛЬ направления
# взгляда (не по прямой до любой стены, а именно по лучу, куда камера
# смотрит). Высота и вертикальный угол при этом берутся как есть (параметр
# камеры или расчёт из оптики), либо, если их вовсе нет — записывается
# значение по умолчанию из настроек автонаведения (тоже параметром
# ЭКЗЕМПЛЯРА).

def _auto_aim_one(doc, cam, view, s, unit_mode, default_h_ft, default_vfov_rad):
    if not isinstance(cam.Location, LocationPoint):
        return (cam, u"no_location", u"")

    tilt_name = (s.get("tilt_param_name") or u"").strip()
    if not tilt_name:
        return (cam, u"no_tilt_param", u"в настройках не задано имя параметра наклона")

    # Наклон подбирается ПОД КОНКРЕТНУЮ камеру (её помещение, её
    # направление) — параметр должен быть параметром ЭКЗЕМПЛЯРА: если бы
    # он был параметром типа, запись одного значения переставила бы
    # наклон и у всех остальных камер того же типа.
    tilt_p = cam.LookupParameter(tilt_name)
    if tilt_p is None:
        return (cam, u"tilt_not_instance",
                u"«{}» не найден как параметр ЭКЗЕМПЛЯРА этой камеры (если он "
                u"параметр типа — сделайте его параметром экземпляра: наклон "
                u"должен подбираться отдельно для каждой камеры)".format(tilt_name))
    if tilt_p.IsReadOnly or tilt_p.StorageType != StorageType.Double:
        return (cam, u"tilt_readonly",
                u"параметр «{}» недоступен для записи".format(tilt_name))

    offset_deg = _as_float(s.get("direction_offset_deg"), 0.0)
    d, dir_note = _look_direction(cam, offset_deg)
    if d is None:
        return (cam, u"bad_geometry", u"нет направления камеры [{}]".format(dir_note))
    base = math.atan2(d.Y, d.X)
    rot = _opt_param_radians(doc, cam, s.get("rotation_param_name"), unit_mode)
    if rot:
        base += rot

    p = cam.Location.Point
    center = XYZ(p.X, p.Y, 0.0)

    dist_name = (s.get("distance_param_name") or u"").strip()
    dist_p = _find_param(doc, cam, dist_name) if dist_name else None
    search_r = dist_p.AsDouble() if (dist_p is not None and dist_p.HasValue) else 300.0

    boundary_mode = s.get("room_boundary") or u"отделка"
    rings, room_note = room_rings_for_point(doc, p, boundary_mode)
    if rings is None:
        return (cam, u"no_room", room_note)

    wall_ft = _clip_distance(center.X, center.Y, math.cos(base), math.sin(base), search_r, rings)
    if wall_ft >= search_r - 1e-6:
        return (cam, u"no_wall_hit",
                u"по направлению камеры (азимут {:.0f}°) граница помещения не "
                u"встретилась в пределах {:.1f} м — проверьте направление/поворот "
                u"камеры или дальность".format(math.degrees(base) % 360.0, search_r * _M_PER_FT))

    h_ft = _mounting_height_ft(doc, cam, view, s.get("height_param_name"))
    h_written = False
    if h_ft is None:
        h_ft = default_h_ft
        hname = (s.get("height_param_name") or u"").strip()
        if hname:
            hp = cam.LookupParameter(hname)
            if hp is not None and not hp.IsReadOnly and hp.StorageType == StorageType.Double:
                hp.Set(_mm_to_param_value(hp, default_h_ft * 304.8))
                h_written = True

    # вертикальный угол — расчётный (фокусное + матрица, см. _optical_fov);
    # если оптика не настроена/не нашлась на этой камере — значение по
    # умолчанию из настроек автонаведения (писать его некуда, это не
    # параметр камеры, а чистый расчётный вход)
    _, vfov, _optic_reason = _optical_fov(doc, cam, s)
    vfov_default_used = False
    if vfov is None:
        vfov = default_vfov_rad
        vfov_default_used = True

    if h_ft is None or h_ft <= 0.1 or vfov is None or vfov <= 1e-4:
        return (cam, u"missing_inputs",
                u"нет высоты и/или вертикального угла обзора, и не задано значение "
                u"по умолчанию в настройках автонаведения")

    tilt = math.atan2(h_ft, wall_ft) + vfov / 2.0
    tilt = max(0.0, min(tilt, math.radians(89.0)))
    tilt_p.Set(_radians_to_param_value(tilt_p, tilt, unit_mode))

    extra = u"".join([
        u"; высота по умолчанию (записана)" if h_written else u"",
        u"; верт.угол по умолчанию (не найдена оптика)" if vfov_default_used else u"",
    ])
    return (cam, u"ok",
            u"до стены {:.2f} м, h={:.2f} м, верт.угол={:.0f}° -> наклон "
            u"{:.1f}°{}".format(wall_ft * _M_PER_FT, h_ft * _M_PER_FT,
                                math.degrees(vfov), math.degrees(tilt), extra))


def auto_aim_cameras(doc, cameras, view, settings):
    """
    Подобрать и ЗАПИСАТЬ наклон (tilt_param_name, параметр экземпляра)
    каждой камеры так, чтобы дальний край конуса приходился на границу её
    помещения по направлению взгляда. Возвращает [(camera, status, detail)]
    со status: "ok"/"no_location"/"no_tilt_param"/"tilt_not_instance"/
    "tilt_readonly"/"bad_geometry"/"no_room"/"no_wall_hit"/"missing_inputs".
    Транзакция — на вызывающей стороне (пишет параметры).
    """
    s = settings
    unit_mode = s.get("angle_unit") or u"авто"
    default_h_ft = _as_float(s.get("auto_default_height_mm"), 3000.0) * _FT_PER_MM
    default_vfov_rad = math.radians(_as_float(s.get("auto_default_vfov_deg"), 30.0))

    results = []
    for cam in cameras:
        try:
            results.append(_auto_aim_one(doc, cam, view, s, unit_mode, default_h_ft, default_vfov_rad))
        except Exception as ex:
            results.append((cam, u"error", u"{}".format(ex)))
    return results


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
        u"таблице); либо явные размеры активной области «ШхВ» в мм — "
        u"«5.37x4.04»; либо одна ширина «5.37» (высота = 3/4). Обязательно, "
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
        u"«;»: «Вращение (поворот);УГО_Поворот».",
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
        "camera_h_res_px",
        u"",
        u"Горизонтальное разрешение матрицы, пикс",
        u"Нужно только для дуг DORI. Например 1920 (Full HD), 2560, 3840. "
        u"Расстояние: d = H / (2 · пикс/м · tg(гор.угол / 2)).",
        u"", False
    ),
    (
        "auto_default_height_mm",
        u"⑥ Автонаведение (кнопка «Навести на помещение»)",
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
