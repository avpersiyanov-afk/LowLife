# -*- coding: utf-8 -*-

__title__ = u"Навести на\nпомещение"
__doc__ = (
    u"Подбирает и записывает наклон выбранных камер так, чтобы дальний "
    u"край зоны обзора приходился на границу помещения по направлению "
    u"взгляда камеры. Сама зону не строит — после запуска перестройте её "
    u"кнопкой «Зоны обзора».\n\n"
    u"Порядок: сначала кнопка, потом выбор камер (тот же фильтр "
    u"категорий, что у «Зон обзора»). Параметр наклона должен быть "
    u"параметром ЭКЗЕМПЛЯРА — если он окажется параметром типа, камера "
    u"пропускается (иначе наклон переставился бы у всех камер этого "
    u"типа).\n\n"
    u"Shift+клик — настройки (те же, что у «Зон обзора», плюс значения "
    u"высоты/вертикального угла по умолчанию)."
)
__author__ = "Pipers"

from pyrevit import revit, forms, script, EXEC_PARAMS

from Autodesk.Revit.DB import ViewPlan, ViewDrafting, BuiltInCategory, BuiltInParameter, Element
from Autodesk.Revit.UI.Selection import ObjectType
from Autodesk.Revit.Exceptions import OperationCanceledException

from lowlife import sot_fov

doc = revit.doc
uidoc = revit.uidoc


def _open_settings():
    edited = sot_fov.get_settings_interactive()
    forms.alert(
        u"Отменено, настройки не изменены." if edited is None
        else u"Настройки сохранены."
    )


_STATUS_RU = {
    u"ok": u"наклон записан",
    u"no_location": u"нет точки вставки (LocationPoint)",
    u"no_tilt_param": u"в настройках не задано имя параметра наклона",
    u"tilt_not_instance": u"параметр наклона не найден как параметр экземпляра",
    u"tilt_readonly": u"параметр наклона недоступен для записи",
    u"bad_geometry": u"не удалось определить направление камеры",
    u"no_room": u"помещение не найдено",
    u"no_wall_hit": u"граница помещения не встретилась по направлению взгляда",
    u"missing_inputs": u"нет высоты/вертикального угла и значений по умолчанию",
    u"error": u"ошибка",
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
    output.print_md(u"# Навести на помещение — отчёт ({} камер)".format(len(results)))

    ok_n = 0
    for cam, status, detail in results:
        is_ok = status == u"ok"
        ok_n += 1 if is_ok else 0
        try:
            link = output.linkify(cam.Id) if cam is not None else u"—"
        except Exception:
            link = u"[{}]".format(cam.Id.IntegerValue if cam is not None else u"—")
        marker = u"OK  " if is_ok else u"FAIL"
        print(u"{}  {}  {}  —  {}: {}".format(
            marker, link, _cam_label(cam),
            _STATUS_RU.get(status, status), detail or u""
        ))

    output.print_md(u"---")
    output.print_md(u"**Наклон записан: {} из {}**".format(ok_n, len(results)))
    if ok_n:
        output.print_md(u"_Перестройте зону кнопкой «Зоны обзора», чтобы увидеть результат._")


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
sot_fov.require(settings, ["tilt_param_name"])

view = doc.ActiveView
if not isinstance(view, (ViewPlan, ViewDrafting)):
    forms.alert(
        u"Активируйте план (этажа или потолка) либо чертёжный вид — "
        u"по нему определяется уровень камеры.",
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
        sot_fov.CategorySelectionFilter(cat_ids),
        u"Выберите видеокамеры, затем Enter (фильтр — категории из настроек)"
    )
except OperationCanceledException:
    forms.alert(u"Выбор отменён, ничего не изменено.", exitscript=True)

cameras = [doc.GetElement(r) for r in refs]
cameras = [c for c in cameras if c is not None]

if not cameras:
    forms.alert(u"Не выбрано ни одной камеры.", exitscript=True)

with revit.Transaction(u"СОТ: наклон камер по помещению"):
    results = sot_fov.auto_aim_cameras(doc, cameras, view, settings)

_report(results)
