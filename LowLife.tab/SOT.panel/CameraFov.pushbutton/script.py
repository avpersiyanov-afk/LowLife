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

from Autodesk.Revit.DB import ViewPlan, ViewDrafting, BuiltInCategory
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


def _report(results):
    ok = [r for r in results if r[1] in _OK_STATUSES]
    no_room = [r for r in results if r[1] == u"ok_no_room"]
    clip_failed = [r for r in results if r[1] == u"ok_clip_failed"]
    problems = [r for r in results if r[1] not in _OK_STATUSES]

    lines = [
        u"Готово.",
        u"",
        u"Построено зон: {}".format(len(ok)),
        u"  из них без обрезки (помещение не найдено): {}".format(len(no_room)),
        u"  из них без обрезки (обрезка дала пустой контур): {}".format(len(clip_failed)),
        u"Не построено: {}".format(len(problems)),
    ]

    if problems:
        lines.append(u"")
        lines.append(u"Подробности по непостроенным:")
        for cam, status, detail in problems:
            try:
                cid = cam.Id.IntegerValue if cam is not None else u"—"
            except Exception:
                cid = u"—"
            lines.append(u"  • [{}] {}: {}".format(cid, status, detail or u""))

    forms.alert(u"\n".join(lines))


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
