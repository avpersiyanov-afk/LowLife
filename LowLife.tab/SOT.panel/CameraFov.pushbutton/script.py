# -*- coding: utf-8 -*-

__title__ = u"Зоны\nобзора"
__doc__ = (
    u"Строит зону обзора выбранных видеокамер на активном виде "
    u"(область заливки), обрезая её по границе помещения из связанной "
    u"модели.\n\n"
    u"Порядок: сначала кнопка, потом выбор камер — фильтр выбора "
    u"пропускает только «Охранную сигнализацию». Угол обзора, дальность, "
    u"высота установки, наклон и вертикальный угол берутся из параметров "
    u"экземпляра (имена — в настройках). Повторный запуск перерисовывает "
    u"зоны тех же камер, не плодя дубли.\n\n"
    u"Shift+клик — настройки (имена параметров, учёт высоты установки, "
    u"обрезка по помещению, зоны DORI)."
)
__author__ = "Pipers"

from pyrevit import revit, forms, script, EXEC_PARAMS

from Autodesk.Revit.DB import (
    ViewPlan, ViewDrafting, BuiltInCategory, BuiltInParameter, Element
)
from Autodesk.Revit.UI.Selection import ObjectType, ISelectionFilter
from Autodesk.Revit.Exceptions import OperationCanceledException

from lowlife import sot_fov

doc = revit.doc
uidoc = revit.uidoc


class _CategoryFilter(ISelectionFilter):
    """Разрешает выбирать только элементы категорий из настроек
    (по умолчанию — «Оборудование систем безопасности», OST_SecurityDevices)."""

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


def _open_settings():
    edited = sot_fov.get_settings_interactive()
    forms.alert(
        u"Отменено, настройки не изменены." if edited is None
        else u"Настройки зон обзора сохранены."
    )


_OK_STATUSES = (u"ok", u"ok_no_room", u"ok_clip_failed")

_STATUS_RU = {
    u"ok": u"построена",
    u"ok_no_room": u"построена (без обрезки — помещение не найдено)",
    u"ok_clip_failed": u"построена (без обрезки — обрезка дала пустой контур)",
    u"no_location": u"нет точки вставки (LocationPoint)",
    u"no_angle_param": u"нет параметра угла обзора",
    u"no_distance_param": u"нет параметра дальности",
    u"bad_geometry": u"вырожденная геометрия",
    u"create_failed": u"ошибка создания области заливки",
    u"no_fill_type": u"в проекте нет типа области заливки",
}


def _cam_label(cam):
    if cam is None:
        return u""
    parts = []
    try:
        parts.append(Element.Name.GetValue(cam))
    except Exception:
        pass
    try:
        mp = cam.get_Parameter(BuiltInParameter.ALL_MODEL_MARK)
        mv = mp.AsString() if mp is not None else None
        if mv and mv.strip():
            parts.append(u"марка {}".format(mv.strip()))
    except Exception:
        pass
    return u" · ".join(p for p in parts if p)


def _report(results):
    output = script.get_output()
    output.print_md(u"# Зоны обзора — отчёт ({} камер)".format(len(results)))

    ok_n = 0
    bad_n = 0
    for cam, status, detail in results:
        is_ok = status in _OK_STATUSES
        ok_n += 1 if is_ok else 0
        bad_n += 0 if is_ok else 1

        try:
            link = output.linkify(cam.Id) if cam is not None else u"—"
        except Exception:
            link = u"[{}]".format(cam.Id.IntegerValue if cam is not None else u"—")

        marker = u"OK  " if status == u"ok" else (u"~   " if is_ok else u"FAIL")
        print(u"{}  {}  {}  —  {}: {}".format(
            marker, link, _cam_label(cam),
            _STATUS_RU.get(status, status), detail or u""
        ))

    output.print_md(u"---")
    output.print_md(u"**Построено: {}  ·  Не построено: {}**".format(ok_n, bad_n))
    if bad_n:
        output.print_md(u"_Клик по ссылке в строке — выделить камеру в модели._")


# --- Shift+клик -> настройки ------------------------------------------
try:
    config_mode = bool(EXEC_PARAMS.config_mode)
except Exception:
    config_mode = False

if config_mode:
    _open_settings()
    script.exit()


# --- обычный запуск --------------------------------------------------
settings = sot_fov.get_settings_silent()
sot_fov.require(settings, ["distance_param_name", "zone_tag"])

_has_angle = bool((settings.get("angle_param_name") or u"").strip())
_has_optics = bool((settings.get("focal_length_param_name") or u"").strip()
                   and (settings.get("sensor_format") or u"").strip())
if not _has_angle and not _has_optics:
    forms.alert(
        u"В настройках не задан способ получить угол обзора:\n"
        u"— либо «Параметр горизонтального угла обзора»,\n"
        u"— либо пара «Фокусное расстояние» + «Формат матрицы».\n\n"
        u"Откройте настройки: Shift+клик по кнопке «Зоны обзора».",
        exitscript=True
    )

view = doc.ActiveView
if not isinstance(view, (ViewPlan, ViewDrafting)):
    forms.alert(
        u"Активируйте план (этажа или потолка) либо чертёжный вид.\n"
        u"На 3D-виде, разрезе, фасаде и листе зона обзора не строится.",
        exitscript=True
    )

cat_ids = sot_fov.resolve_category_ids(
    doc, settings.get("camera_categories") or u"OST_SecurityDevices"
)
if not cat_ids:
    cat_ids = {int(BuiltInCategory.OST_SecurityDevices)}

try:
    refs = uidoc.Selection.PickObjects(
        ObjectType.Element,
        _CategoryFilter(cat_ids),
        u"Выберите видеокамеры, затем Enter (фильтр — категории из настроек)"
    )
except OperationCanceledException:
    forms.alert(u"Выбор отменён, ничего не построено.", exitscript=True)

cameras = [doc.GetElement(r) for r in refs]
cameras = [c for c in cameras if c is not None]

if not cameras:
    forms.alert(
        u"Не выбрано ни одной камеры.\n\n"
        u"Если камеры не выделялись вовсе — они не в тех категориях, что "
        u"заданы в настройках («Категории камер для фильтра выбора»). "
        u"Посмотрите категорию семейства камеры в свойствах и впишите её "
        u"в настройки (Shift+клик).",
        exitscript=True
    )

with revit.Transaction(u"СОТ: зоны обзора камер"):
    results = sot_fov.build_fov_zones(doc, cameras, view, settings)

_report(results)
