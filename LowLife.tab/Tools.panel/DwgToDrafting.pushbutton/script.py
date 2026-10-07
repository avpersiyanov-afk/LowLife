# -*- coding: utf-8 -*-

__title__ = u"DWG →\nчертёжный"
__doc__ = (
    u"Обводит DWG-подложку аннотациями: линии, дуги и полилинии DWG "
    u"становятся линиями детализации, текст DWG — текстовыми примечаниями "
    u"(та же точка, поворот, выравнивание и высота на бумаге).\n\n"
    u"Куда — на выбор: в новый чертёжный вид (вид откроется) или на этот "
    u"же вид поверх подложки. DWG берётся выделенный, иначе видимый на "
    u"виде (если их несколько — из списка). Слои, скрытые на виде, не "
    u"переносятся.\n\n"
    u"Текст Revit у DWG не видит, поэтому он читается из DXF того же "
    u"чертежа: DXF с тем же именем рядом с DWG, иначе DWG конвертируется "
    u"бесплатным ODA File Converter (если установлен), иначе DXF можно "
    u"указать вручную или перенести только линии.\n\n"
    u"Shift+клик — настройки (стиль линий или стили по слоям, типоразмер "
    u"текста, путь к ODA File Converter)."
)
__author__ = "Pipers"

import os
import shutil
import traceback

from Autodesk.Revit.DB import ViewType
from pyrevit import revit, forms, script, EXEC_PARAMS

from lowlife import dwg_transfer as dt
from lowlife import dwg_transfer_settings, dxf_text

doc = revit.doc
uidoc = revit.uidoc
view = doc.ActiveView

TITLE = u"DWG → чертёжный вид"

try:
    config_mode = bool(EXEC_PARAMS.config_mode)
except Exception:
    config_mode = False

if config_mode:
    edited = dwg_transfer_settings.get_settings_interactive()
    forms.alert(u"Отменено, настройки не изменены." if edited is None
                else u"Настройки сохранены.", title=TITLE)
    script.exit()

settings = dwg_transfer_settings.get_settings_silent()

SUPPORTED_VIEWS = (ViewType.FloorPlan, ViewType.CeilingPlan, ViewType.EngineeringPlan,
                   ViewType.AreaPlan, ViewType.Section, ViewType.Elevation,
                   ViewType.Detail, ViewType.DraftingView)
if view.ViewType not in SUPPORTED_VIEWS:
    forms.alert(u"Откройте план, разрез, фасад, узел или чертёжный вид, на "
                u"котором лежит DWG.", title=TITLE, exitscript=True)

# --- какой DWG -----------------------------------------------------------------

imports = dt.find_imports(doc, view, uidoc.Selection.GetElementIds())
if not imports:
    forms.alert(u"На виде нет импортированного или связанного DWG.", title=TITLE,
                exitscript=True)
imp = imports[0]
if len(imports) > 1:
    labels = [u"{} (id {})".format(dt.import_label(doc, i), i.Id.IntegerValue) for i in imports]
    picked = forms.SelectFromList.show(labels, title=TITLE, button_name=u"Перенести",
                                       multiselect=False)
    if not picked:
        script.exit()
    imp = imports[labels.index(picked)]
label = dt.import_label(doc, imp)

# --- стили из настроек -------------------------------------------------------------

fixed_style = None
style_name = (settings.get("line_style") or u"").strip()
if style_name:
    fixed_style = dt.find_line_style(doc, style_name)
    if fixed_style is None:
        forms.alert(u"Стиль линий «{}» не найден в проекте.\n\nShift+клик по "
                    u"кнопке — настройки (пусто — стили по слоям DWG).".format(style_name),
                    title=TITLE, exitscript=True)

base_name = (settings.get("base_text_type") or u"").strip()
base_text_type = dt.find_text_type(doc, base_name) if base_name else dt.default_text_type(doc)
if base_text_type is None:
    forms.alert(u"Типоразмер текста «{}» не найден в проекте.\n\nShift+клик по "
                u"кнопке — настройки.".format(base_name), title=TITLE, exitscript=True)

# --- куда -------------------------------------------------------------------------

TO_NEW = u"В новый чертёжный вид"
TO_SAME = u"На этот вид, поверх DWG"
target_choice = forms.CommandSwitchWindow.show(
    [TO_NEW, TO_SAME], message=u"«{}»: куда перенести линии и текст?".format(label))
if not target_choice:
    script.exit()

# --- откуда текст ---------------------------------------------------------------

file_path = dt.import_file_path(doc, imp)
dxf_path, searched = dt.find_dxf(doc, imp, file_path)
temp_dir = None
convert_error = None
if dxf_path is None and file_path and file_path.lower().endswith(".dwg") and os.path.isfile(file_path):
    exe = dt.find_oda_converter((settings.get("oda_converter") or u"").strip() or None)
    if exe:
        try:
            dxf_path, temp_dir = dt.convert_with_oda(exe, file_path)
        except Exception as err:
            convert_error = u"{}".format(err)

if dxf_path is None:
    where = u""
    if searched:
        where = u"\n\nDXF искался здесь:\n" + u"\n".join(searched[:6])
    if not file_path:
        why = u"DWG вставлен в проект, а не связан — путь к нему неизвестен."
    elif not os.path.isfile(file_path):
        why = u"Файл DWG не найден:\n{}".format(file_path)
    elif convert_error:
        why = u"Не удалось сконвертировать DWG в DXF: {}".format(convert_error)
    else:
        why = (u"Рядом с DWG нет DXF с тем же именем, а ODA File Converter не "
               u"найден (бесплатно: opendesign.com → ODA File Converter, или "
               u"сохраните DWG как DXF в AutoCAD).")
    PICK = u"Указать DXF-файл…"
    SKIP = u"Без текста — только линии"
    text_choice = forms.CommandSwitchWindow.show(
        [PICK, SKIP],
        message=u"Текст DWG читается из DXF того же чертежа. " + why + where)
    if not text_choice:
        script.exit()
    if text_choice == PICK:
        start_dir = os.path.dirname(file_path) if file_path else None
        if start_dir and os.path.isdir(start_dir):
            dxf_path = forms.pick_file(file_ext="dxf", init_dir=start_dir)
        else:
            dxf_path = forms.pick_file(file_ext="dxf")
        if not dxf_path:
            script.exit()

drawing = None
read_error = None
if dxf_path:
    try:
        drawing = dxf_text.read_dxf(dxf_path)
    except Exception as err:
        read_error = u"{}".format(err)
if temp_dir:
    shutil.rmtree(temp_dir, ignore_errors=True)

# --- геометрия и совмещение ------------------------------------------------------

geo = dt.collect_geometry(doc, imp, view)
mapping = None
mapping_how = None
if drawing is not None and drawing.texts:
    fit = dxf_text.fit_mapping(drawing.extents, geo.symbol_extents, drawing.units_to_feet)
    if fit is not None:
        mapping = fit[:3]
        mapping_how = fit[3]

if not geo.items and mapping is None:
    forms.alert(u"В DWG «{}» нечего переносить: видимых линий нет{}.".format(
        label, u", текст не прочитан" if drawing is None else u""), title=TITLE, exitscript=True)

# --- перенос --------------------------------------------------------------------

result = dt.TransferResult()
target = view
styles = None
text_types = None
try:
    with revit.Transaction(TITLE, swallow_errors=True):
        if target_choice == TO_NEW:
            target = dt.create_drafting_view(doc, u"DWG - " + label, view.Scale)
            placement = dt.placement_drafting(view, target)
        else:
            placement = dt.placement_same_view(view)

        if fixed_style is not None:
            style_for = lambda layer_cat: fixed_style
        else:
            styles = dt.LayerStyles(doc, settings.get("layer_style_prefix") or u"")
            style_for = styles.style_for
        dt.transfer_lines(doc, geo, placement, style_for, result)

        if mapping is not None:
            text_types = dt.TextTypes(doc, base_text_type, settings.get("text_type_prefix") or u"")
            dt.transfer_texts(doc, imp, view, geo, drawing, mapping, placement, text_types, result)
except Exception:
    forms.alert(u"Не удалось перенести DWG.\n\n" + traceback.format_exc(),
                title=TITLE, exitscript=True)

if target.Id != view.Id:
    uidoc.ActiveView = target

# --- отчёт ----------------------------------------------------------------------

lines = [u"«{}» → {}".format(label, u"чертёжный вид «{}»".format(dt.element_name(target))
                              if target.Id != view.Id else u"этот вид")]
if dxf_path:
    lines.append(u"Текст из: " + (u"DWG, сконвертированного ODA File Converter"
                                  if temp_dir else dxf_path))
line_text = u"Линий детализации: {}".format(result.lines)
if result.lines_failed:
    line_text += u" (не удалось: {})".format(result.lines_failed)
if geo.hidden_skipped:
    line_text += u"; на скрытых слоях пропущено: {}".format(geo.hidden_skipped)
lines.append(line_text)

if drawing is None:
    lines.append(u"Текст не перенесён: " + (read_error or u"DXF не указан."))
elif not drawing.texts:
    lines.append(u"В DXF нет текста в пространстве модели.")
elif mapping is None:
    lines.append(u"Текст не перенесён: не удалось совместить DXF с геометрией DWG "
                 u"(в DXF нет линий и не заданы единицы $INSUNITS).")
else:
    text_line = u"Текстов: {}".format(result.texts)
    if result.texts_failed:
        text_line += u" (не удалось: {})".format(result.texts_failed)
    hidden = result.texts_hidden + drawing.skipped_hidden
    if hidden:
        text_line += u"; на скрытых/выключенных слоях пропущено: {}".format(hidden)
    lines.append(text_line)
    if mapping_how == "units_only":
        lines.append(u"Внимание: габариты DXF и DWG не совпали (это тот же чертёж?) — "
                     u"текст поставлен только по единицам DXF, проверьте его положение.")
    kinds = drawing.counts()
    if kinds:
        names = [(u"TEXT", u"однострочный"), (u"MTEXT", u"многострочный"),
                 (u"ATTRIB", u"атрибуты блоков"), (u"ATTDEF", u"постоянные атрибуты"),
                 (u"MULTILEADER", u"мультивыноски")]
        lines.append(u"Найдено в DXF: " + u", ".join(
            u"{} {}".format(label, kinds[k]) for k, label in names if kinds.get(k)) + u".")
    if drawing.missing_blocks:
        lines.append(u"В DXF нет описаний блоков: {}.".format(
            u", ".join(sorted(drawing.missing_blocks)[:5])))

if drawing is not None and drawing.unsupported:
    top = sorted(drawing.unsupported.items(), key=lambda kv: -kv[1])[:6]
    lines.append(u"Не разобраны объекты DXF (их текст не перенесён): " + u", ".join(
        u"{} ×{}".format(k, v) for k, v in top) + u".")

if styles is not None and styles.created:
    lines.append(u"Создано стилей линий по слоям: {}.".format(len(styles.created)))
if text_types is not None and text_types.created:
    lines.append(u"Создано типов текста: {} ({}).".format(
        len(text_types.created), u", ".join(text_types.created[:6])))
if result.errors:
    lines.append(u"")
    lines.append(u"Ошибки:")
    lines.extend(result.errors)
lines.append(u"")
lines.append(u"Штриховки и заливки DWG не переносятся. Подложку можно скрыть или удалить.")

forms.alert(u"\n".join(lines), title=TITLE)
