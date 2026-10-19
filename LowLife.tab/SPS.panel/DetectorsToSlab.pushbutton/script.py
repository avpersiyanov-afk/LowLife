# -*- coding: utf-8 -*-
__title__ = u"Извещатели\nна перекрытие"
__doc__ = (
    u"Переносит пожарные извещатели на низ перекрытия над ними (с учётом разных "
    u"отметок перекрытий, включая связи АР/КР) и подписывает на выбранных планах "
    u"высоту перекрытия от пола в каждом помещении, на сколько она отличается от "
    u"типовой, перепады плиты — толстыми красными линиями, а помещения с подвесным потолком обводит областью заливки с "
    u"подписью «ПП» и высотой потолка от пола.\n\n"
    u"Если перед запуском выделены извещатели — переносятся только они.\n\n"
    u"Shift+клик — настройки этой кнопки."
)
__author__ = "Pipers"

import time

from pyrevit import revit, forms, script, EXEC_PARAMS

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
action = forms.CommandSwitchWindow.show([BOTH, MOVE, MARK], message=TITLE)
if not action:
    script.exit()

selected_ids = list(uidoc.Selection.GetElementIds())
selected = slab_marks.collect_detectors(doc, settings, selected_ids) if selected_ids else []

views = []
if action != MOVE or not selected:
    views = forms.select_views(
        title=u"Планы, на уровнях которых работать" + (u" (и подписать)" if action != MOVE else u""),
        filterfunc=slab_marks.is_plan, multiple=True, use_selection=False)
    if not views:
        script.exit()

detectors = []
if action != MARK:
    if selected:
        detectors = selected
    else:
        level_ids = set(view.GenLevel.Id.IntegerValue for view in views)
        levels = slab_marks.plan_levels(doc)
        for detector in slab_marks.collect_detectors(doc, settings):
            level, _z = slab_marks.level_of(doc, detector, levels)
            if level is not None and level.Id.IntegerValue in level_ids:
                detectors.append(detector)
    if not detectors and action == MOVE:
        forms.alert(u"Не найдено ни одного извещателя (проверьте слова в настройках: Shift+клик).",
                    title=TITLE, exitscript=True)

move_result = None
view_results = []
timings = []  # (этап, секунды) — для отчёта: где уходит время
with forms.ProgressBar(title=TITLE + u": {value} из {max_value}", cancellable=False) as bar:
    def progress(index, total):
        if index % 10 == 0:
            bar.update_progress(index, total)

    with revit.Transaction(TITLE):
        probe = slab_marks.SlabProbe(doc)
        try:
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


output = script.get_output()
output.print_md(u"## " + TITLE)
lines = []
if move_result is not None:
    output.print_md(u"### Извещатели")
    lines.append(u"Извещателей перенесено: {}, уже на перекрытии: {}".format(
        move_result.moved, move_result.already))
    output.print_md(u"- перенесено на низ перекрытия: {}".format(move_result.moved))
    output.print_md(u"- уже были на перекрытии: {}".format(move_result.already))
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
    if result.typical_mm is not None:
        output.print_md(u"- типовая высота перекрытия от пола: {}".format(
            slab_marks.core.format_height(result.typical_mm)))
    output.print_md(u"- подписано помещений: {}, с подвесным потолком (ПП): {}, линий перепада плиты: {}".format(
        result.rooms, result.ceiling_rooms, result.steps))
    lines.append(u"«{}»: помещений {}, ПП {}, перепадов {}".format(
        result.view.Name, result.rooms, result.ceiling_rooms, result.steps))
    if result.changed:
        output.print_md(u"- перекрытие отличается от типового:")
        for name, height in sorted(result.changed, key=lambda item: item[1]):
            output.print_md(u"    - {}: {} (Δ {})".format(
                name or u"без имени", slab_marks.core.format_height(height),
                slab_marks.core.format_height(height - result.typical_mm)))
    if result.no_slab:
        output.print_md(u"- без перекрытия над ними: " + u", ".join(result.no_slab))
    for error in result.errors:
        output.print_md(u"- ошибка: " + error)

if timings:
    output.print_md(u"### Время")
    for stage, seconds in timings:
        output.print_md(u"- {}: {:.1f} с".format(stage, float(seconds)))

forms.alert(u"Готово.\n\n" + u"\n".join(lines) + u"\n\nПодробности — в окне вывода.", title=TITLE)
