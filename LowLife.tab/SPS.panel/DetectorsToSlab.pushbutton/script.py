# -*- coding: utf-8 -*-
__title__ = u"Извещатели\nна перекрытие"
__doc__ = (
    u"Переносит пожарные извещатели на низ перекрытия над ними (с учётом разных "
    u"отметок перекрытий, включая связи АР/КР), на выбранных планах заливает плиты "
    u"над этажом штриховкой по отметкам с подписью высоты от пола и разницы с "
    u"типовой, перепады плиты — толстыми красными линиями, а помещения с подвесным потолком обводит областью заливки с "
    u"подписью «ПП» и высотой потолка от пола.\n\n"
    u"Какие извещатели переносить — выбирается при запуске: выделенные (если "
    u"ничего не выделено — выбрать на модели), все на активном виде или все на "
    u"уровнях выбранных планов.\n\n"
    u"Shift+клик — настройки этой кнопки."
)
__author__ = "Pipers"

import time

from pyrevit import revit, forms, script, EXEC_PARAMS
from lowlife import select_list

from lowlife import slab_marks, slab_marks_settings

doc = revit.doc
uidoc = revit.uidoc
TITLE = u"Извещатели на перекрытие"


try:
    config_mode = bool(EXEC_PARAMS.config_mode)
except Exception:
    config_mode = False

if config_mode:
    edited = slab_marks_settings.get_settings_interactive()
    forms.alert(u"Отменено, настройки не изменены." if edited is None else u"Настройки сохранены.")
    script.exit()


settings = slab_marks_settings.get_settings_silent()

BOTH = u"Перенести извещатели и подписать отметки"
MOVE = u"Только перенести извещатели"
MARK = u"Только подписать отметки на планах"
action = select_list.CommandSwitchWindow.show([BOTH, MOVE, MARK], message=TITLE)
if not action:
    script.exit()

selected_ids = list(uidoc.Selection.GetElementIds())
selected = slab_marks.collect_detectors(doc, settings, selected_ids) if selected_ids else []
active_view = doc.ActiveView

# Какие извещатели переносить: выделенные (если перед запуском ничего не
# выделено — выбрать на модели после этого окна), все на активном виде или
# все на уровнях выбранных планов.
SCOPE_SELECTED = (u"Выделенные извещатели ({})".format(len(selected)) if selected
                  else u"Выделенные извещатели — выбрать на модели")
SCOPE_VIEW = u"Все извещатели на активном виде «{}»".format(
    active_view.Name if active_view is not None else u"")
SCOPE_LEVELS = u"Все извещатели на уровнях выбранных планов"
scope = None
if action != MARK:
    scopes = [SCOPE_SELECTED]
    if slab_marks.can_collect_on(active_view):
        scopes.append(SCOPE_VIEW)
    scopes.append(SCOPE_LEVELS)
    scope = select_list.CommandSwitchWindow.show(scopes, message=u"Какие извещатели переносить?")
    if not scope:
        script.exit()
    if scope == SCOPE_SELECTED and not selected:
        selected = slab_marks.pick_detectors(uidoc, doc, settings)
        if selected is None:
            script.exit()
        if not selected:
            forms.alert(u"Не выбрано ни одного извещателя (подходящие — по словам в настройках: "
                        u"Shift+клик).", title=TITLE, exitscript=True)

# Планы для подписей (и для «на уровнях выбранных планов»): при переносе с
# активного плана подписывается он же — без лишнего окна выбора.
views = []
if action != MOVE and scope == SCOPE_VIEW and slab_marks.is_plan(active_view):
    views = [active_view]
elif action != MOVE or scope == SCOPE_LEVELS:
    views = select_list.select_views(
        title=u"Планы, на уровнях которых работать" + (u" (и подписать)" if action != MOVE else u""),
        filterfunc=slab_marks.is_plan, multiple=True)
    if not views:
        script.exit()

detectors = []
if scope == SCOPE_SELECTED:
    detectors = selected
elif scope == SCOPE_VIEW:
    detectors = slab_marks.collect_detectors(doc, settings, view=active_view)
elif scope == SCOPE_LEVELS:
    detectors = slab_marks.detectors_on_levels(doc, settings, views)
if action == MOVE and not detectors:
    forms.alert(u"Не найдено ни одного извещателя (проверьте слова в настройках: Shift+клик).",
                title=TITLE, exitscript=True)

move_result = None
view_results = []
timings = []  # (этап, секунды) — для отчёта: где уходит время
diagnostics = []  # (извещатель, [строки]) — лучи над выделенными извещателями
DIAGNOSE_LIMIT = 30
FACE_ROWS_LIMIT = 400  # строк диагностики плит на план
run_started = time.time()
body_done = None
with forms.ProgressBar(title=TITLE + u": {value} из {max_value}", cancellable=False) as bar:
    def progress(index, total):
        if index % 10 == 0:
            bar.update_progress(index, total)

    with revit.Transaction(TITLE):
        probe = slab_marks.SlabProbe(doc, settings.get("opening_size_mm"))
        try:
            # выделены извещатели (немного) — в отчёт: во что упираются лучи над ними
            if selected and len(selected) <= DIAGNOSE_LIMIT:
                started = time.time()
                levels = slab_marks.plan_levels(doc)
                probe_ft = slab_marks.ft(settings.get("probe_height_mm") or 1500.0)
                for detector in selected:
                    point = slab_marks._point(detector)
                    _level, level_z = slab_marks.level_of(doc, detector, levels)
                    if point is None or level_z is None:
                        continue
                    try:
                        diagnostics.append((detector, probe.describe(
                            point.X, point.Y, level_z + probe_ft, level_z)))
                    except Exception as ex:
                        diagnostics.append((detector, [u"ошибка: {}".format(ex)]))
                timings.append((u"диагностика лучей ({})".format(len(selected)), time.time() - started))
            if detectors:
                started = time.time()
                move_result = slab_marks.move_detectors(doc, detectors, settings, probe, progress)
                timings.append((u"перенос извещателей ({})".format(len(detectors)),
                                time.time() - started))
            if action != MOVE:
                note_type = slab_marks.text_type(doc)
                fill_type = slab_marks.region_type(doc, settings.get("filled_region_type_name"))
                step_style = slab_marks.step_line_style(doc, settings.get("step_line_weight") or 10)
                for view in views:
                    started = time.time()
                    view_results.append(slab_marks.annotate_view(
                        doc, view, settings, probe, note_type, fill_type, step_style, progress))
                    timings.append((u"план «{}»".format(view.Name), time.time() - started))
        finally:
            probe.close()
            body_done = time.time()
run_done = time.time()


output = script.get_output()
output.print_md(u"## " + TITLE)
lines = []
if move_result is not None:
    output.print_md(u"### Извещатели")
    lines.append(u"Извещателей перенесено: {}, уже на перекрытии: {}".format(
        move_result.moved, move_result.already))
    output.print_md(u"- перенесено на низ перекрытия: {}".format(move_result.moved))
    output.print_md(u"- уже были на перекрытии: {}".format(move_result.already))
    if move_result.to_ceiling:
        output.print_md(u"- встраиваемых — на подвесной потолок: {}".format(move_result.to_ceiling))
    if move_result.under_ceiling:
        output.print_md(u"- из них над подвесным потолком: {}".format(move_result.under_ceiling))
    if move_result.no_slab:
        lines.append(u"Без перекрытия над ними: {}".format(len(move_result.no_slab)))
        output.print_md(u"- **над ними не найдено перекрытие** ({}): {}".format(
            len(move_result.no_slab), u", ".join(output.linkify(d.Id) for d in move_result.no_slab)))
    if move_result.failed:
        lines.append(u"Не удалось перенести: {}".format(len(move_result.failed)))
        output.print_md(u"- **не удалось перенести:**")
        for detector, reason in move_result.failed:
            link = output.linkify(detector.Id) if detector is not None else u""
            output.print_md(u"    - {} {}".format(link, reason))
for result in view_results:
    output.print_md(u"### План «{}»".format(result.view.Name))
    if result.slab_heights:
        output.print_md(u"- плиты над этажом (заливок {}):".format(result.fills))
        for height, area in result.slab_heights:
            note = u" — типовая" if height == result.typical_mm else u" (Δ {})".format(
                slab_marks.core.format_height(height - result.typical_mm))
            output.print_md(u"    - {}: {:.0f} м²{}".format(
                slab_marks.core.format_height(height), float(area), note))
    if result.typical_floor_mm is not None:
        output.print_md(u"- пол плана (медиана по лучам вниз): {} мм от уровня".format(
            u"{:+.0f}".format(float(result.typical_floor_mm))))
    big_faces = [f for f in result.faces if f.area >= slab_marks.MIN_FILL_AREA_MM2]
    if big_faces:
        output.print_md(u"- диагностика плит над этажом (граней от {:.1f} м²: {}, мельче — {}):".format(
            slab_marks.MIN_FILL_AREA_MM2 / 1e6, len(big_faces), len(result.faces) - len(big_faces)))
        level_mm = slab_marks.mm(result.view.GenLevel.ProjectElevation)
        rows = []
        for face in sorted(big_faces, key=lambda f: f.z_mm)[:FACE_ROWS_LIMIT]:
            rows.append([
                face.source, u"{}".format(face.key[1] if face.key else u""), face.type_name,
                slab_marks.core.format_height(face.z_mm - level_mm),
                slab_marks.core.format_height(face.height_mm) if face.height_mm is not None else u"—",
                u"{:.1f}".format(float(face.area) / 1e6), face.status or u"—",
            ])
        output.print_table(rows, columns=[u"Связь", u"Id", u"Тип", u"Низ от уровня", u"От пола",
                                          u"Площадь, м²", u"Заливка"])
        if len(big_faces) > FACE_ROWS_LIMIT:
            output.print_md(u"- (показаны первые {} по отметке)".format(FACE_ROWS_LIMIT))
    if result.excluded_rooms:
        output.print_md(u"- исключено помещений по имени: {}".format(result.excluded_rooms))
    if result.typical_mm is not None:
        output.print_md(u"- типовая высота перекрытия от пола: {}".format(
            slab_marks.core.format_height(result.typical_mm)))
    output.print_md(u"- подписано помещений: {}, с подвесным потолком (ПП): {}, линий перепада плиты: {}".format(
        result.rooms, result.ceiling_rooms, result.steps))
    lines.append(u"«{}»: помещений {}, ПП {}, перепадов {}".format(
        result.view.Name, result.rooms, result.ceiling_rooms, result.steps))
    stats = result.step_stats
    if stats is not None:
        output.print_md(
            u"- поиск перепадов: плит под лучами {}, краёв нижних граней {}, кандидатов {}, "
            u"линий после склейки {}, не подтверждено лучами частей {}, нарисовано {}".format(
                stats.slabs, stats.edges, stats.candidates, stats.lines, stats.rejected, stats.drawn))
        if stats.skipped:
            output.print_md(
                u"- **не проверено линий перепада: {}** (слишком много — проверены самые длинные; "
                u"уменьшите «Наибольший зазор между краями соседних плит»)".format(stats.skipped))
    if result.changed:
        output.print_md(u"- перекрытие отличается от типового (помещений: {}):".format(len(result.changed)))
        for height, names in slab_marks.core.group_by_height(result.changed):
            output.print_md(u"    - {} (Δ {}): {}".format(
                slab_marks.core.format_height(height),
                slab_marks.core.format_height(height - result.typical_mm),
                u", ".join(u"{} ×{}".format(name or u"без имени", count) if count > 1
                           else (name or u"без имени") for name, count in names)))
    if result.no_slab:
        output.print_md(u"- без перекрытия над ними: " + u", ".join(result.no_slab))
    for error in result.errors:
        output.print_md(u"- ошибка: " + error)

if diagnostics:
    output.print_md(u"### Лучи над выделенными извещателями (до переноса)")
    for detector, diag_lines in diagnostics:
        output.print_md(u"- {}".format(output.linkify(detector.Id)))
        for line in diag_lines:
            output.print_md(u"    - " + line)

if probe.openings:
    output.print_md(u"### Отверстия в перекрытиях")
    output.print_md(
        u"- точек над отверстиями: {} — высота взята по перекрытию вокруг отверстия".format(probe.openings))

if timings or body_done is not None:
    output.print_md(u"### Время")
    output.print_md(u"- всего: {:.1f} с".format(float(run_done - run_started)))
    if probe.open_seconds is not None:
        output.print_md(u"- подготовка 3D-вида для лучей: {:.1f} с".format(float(probe.open_seconds)))
        for step_name, seconds in probe.open_steps:
            output.print_md(u"    - {}: {:.1f} с".format(step_name, float(seconds)))
    if probe.first_ray_seconds is not None:
        output.print_md(u"- первый луч (Revit строит геометрию связей в виде): {:.1f} с".format(
            float(probe.first_ray_seconds)))
    if body_done is not None:
        output.print_md(u"- завершение транзакции (регенерация): {:.1f} с".format(
            float(run_done - body_done)))
    for stage, seconds in timings:
        output.print_md(u"- {}: {:.1f} с".format(stage, float(seconds)))
    for result in view_results:
        for stage, seconds in result.stage_times:
            output.print_md(u"    - «{}» — {}: {:.1f} с".format(result.view.Name, stage, float(seconds)))

forms.alert(u"Готово.\n\n" + u"\n".join(lines) + u"\n\nПодробности — в окне вывода.", title=TITLE)
