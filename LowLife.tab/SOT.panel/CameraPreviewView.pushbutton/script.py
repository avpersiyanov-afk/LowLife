# -*- coding: utf-8 -*-

__title__ = u"Вид как\nс камеры"
__doc__ = (
    u"Создаёт (или обновляет, если уже создан) 3D-перспективный вид Revit "
    u"в точке выбранной камеры, смотрящий туда же, что и она — тот же "
    u"азимут и наклон, что использует «Зоны обзора»/«Навести на "
    u"помещение» — с полем зрения, подогнанным под расчётный "
    u"горизонтальный/вертикальный угол этой камеры (фокусное расстояние + "
    u"формат матрицы).\n\n"
    u"Порядок: сначала кнопка, потом выбор камер (тот же фильтр "
    u"категорий, что у «Зон обзора») — по одному 3D-виду на камеру. "
    u"Повторный запуск на той же камере не плодит вид заново, а "
    u"переставляет уже созданный.\n\n"
    u"Shift+клик — настройки (общие с «Зонами обзора»)."
)
__author__ = "Pipers"

from pyrevit import revit, forms, script, EXEC_PARAMS

from Autodesk.Revit.DB import BuiltInCategory, BuiltInParameter, Element
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
    u"ok": u"вид создан",
    u"ok_no_optics": u"вид создан (без подгонки поля зрения)",
    u"no_location": u"нет точки вставки (LocationPoint)",
    u"bad_geometry": u"не удалось определить направление камеры",
    u"no_view_family_type": u"в проекте нет типа 3D-вида",
    u"create_failed": u"ошибка создания вида",
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
    output.print_md(u"# Вид как с камеры — отчёт ({} камер)".format(len(results)))

    ok_n = 0
    for cam, view3d, status, detail in results:
        is_ok = status in (u"ok", u"ok_no_optics")
        ok_n += 1 if is_ok else 0
        try:
            link = output.linkify(cam.Id) if cam is not None else u"—"
        except Exception:
            link = u"[{}]".format(cam.Id.IntegerValue if cam is not None else u"—")
        marker = u"OK  " if status == u"ok" else (u"~   " if is_ok else u"FAIL")
        view_note = u""
        if view3d is not None:
            try:
                view_note = u" -> {}".format(output.linkify(view3d.Id))
            except Exception:
                pass
        print(u"{}  {}  {}  —  {}: {}{}".format(
            marker, link, _cam_label(cam),
            _STATUS_RU.get(status, status), detail or u"", view_note
        ))

    output.print_md(u"---")
    output.print_md(u"**Создано/обновлено: {} из {}**".format(ok_n, len(results)))


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

view = doc.ActiveView

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
    forms.alert(u"Выбор отменён, ничего не создано.", exitscript=True)

cameras = [doc.GetElement(r) for r in refs]
cameras = [c for c in cameras if c is not None]

if not cameras:
    forms.alert(
        u"Не выбрано ни одной камеры.\n\n"
        u"Если камеры не выделялись вовсе — они не в тех категориях, что "
        u"заданы в настройках («Категории камер для фильтра выбора»).",
        exitscript=True
    )

with revit.Transaction(u"СОТ: вид как с камеры"):
    results = []
    for cam in cameras:
        view3d, status, detail = sot_fov.build_camera_preview_view(doc, cam, view, settings)
        results.append((cam, view3d, status, detail))

_report(results)
