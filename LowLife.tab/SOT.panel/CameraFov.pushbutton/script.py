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

_SECURITY_CAT_ID = int(BuiltInCategory.OST_SecurityDevices)


class _SecurityDeviceFilter(ISelectionFilter):
    """Разрешает выбирать только элементы категории «Охранная сигнализация»
    (OST_SecurityDevices) — обычно к ней относятся семейства видеокамер."""

    def AllowElement(self, elem):
        try:
            cat = elem.Category
            return cat is not None and cat.Id.IntegerValue == _SECURITY_CAT_ID
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


def _report(results):
    ok = [r for r in results if r[1] in (u"ok", u"ok_no_room")]
    no_room = [r for r in results if r[1] == u"ok_no_room"]
    no_loc = [r for r in results if r[1] == u"no_location"]
    no_ang = [r for r in results if r[1] == u"no_angle_param"]
    no_dist = [r for r in results if r[1] == u"no_distance_param"]
    bad = [r for r in results if r[1] == u"bad_geometry"]
    failed = [r for r in results if r[1] in (u"create_failed", u"no_fill_type")]

    lines = [
        u"Готово.",
        u"",
        u"Построено зон: {}".format(len(ok)),
        u"  из них без обрезки (помещение не найдено): {}".format(len(no_room)),
        u"Нет точки вставки: {}".format(len(no_loc)),
        u"Нет параметра угла обзора: {}".format(len(no_ang)),
        u"Нет параметра дальности: {}".format(len(no_dist)),
        u"Вырожденная геометрия (угол/дальность/направление): {}".format(len(bad)),
        u"Ошибка создания: {}".format(len(failed)),
    ]

    if failed:
        detail = failed[0][2]
        if detail:
            lines += [u"", u"Первая ошибка: {}".format(detail)]

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
sot_fov.require(settings, ["angle_param_name", "distance_param_name", "zone_tag"])

view = doc.ActiveView
if not isinstance(view, (ViewPlan, ViewDrafting)):
    forms.alert(
        u"Активируйте план (этажа или потолка) либо чертёжный вид.\n"
        u"На 3D-виде, разрезе, фасаде и листе зона обзора не строится.",
        exitscript=True
    )

try:
    refs = uidoc.Selection.PickObjects(
        ObjectType.Element,
        _SecurityDeviceFilter(),
        u"Выберите видеокамеры (охранная сигнализация), затем Enter"
    )
except OperationCanceledException:
    forms.alert(u"Выбор отменён, ничего не построено.", exitscript=True)

cameras = [doc.GetElement(r) for r in refs]
cameras = [c for c in cameras if c is not None]

if not cameras:
    forms.alert(u"Не выбрано ни одной камеры.", exitscript=True)

with revit.Transaction(u"СОТ: зоны обзора камер"):
    results = sot_fov.build_fov_zones(doc, cameras, view, settings)

_report(results)
