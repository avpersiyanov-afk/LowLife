# -*- coding: utf-8 -*-
__title__ = u"Доступ к\nизвещателям"
__doc__ = (
    u"Проверяет доступ к пожарным извещателям с пола: под ними есть пол, они не над "
    u"подвесным потолком, не ближе 500 мм к стене и в зоне доступа от пола до извещателя нет инженерных сетей "
    u"(модели и связей). На планах обводит зону доступа (зелёный — доступен, красный — "
    u"нет), а для недоступных показывает ближайшее свободное место и перенос.\n\n"
    u"Если перед запуском выделены извещатели — проверяются только они.\n\n"
    u"Shift+клик — настройки этой кнопки."
)
__author__ = "Pipers"

from pyrevit import revit, forms, script, EXEC_PARAMS

from lowlife import detector_access, detector_access_settings, slab_marks
from lowlife import detector_access_core as core

doc = revit.doc
uidoc = revit.uidoc
TITLE = u"Доступ к извещателям"


try:
    config_mode = bool(EXEC_PARAMS.config_mode)
except Exception:
    config_mode = False

if config_mode:
    edited = detector_access_settings.get_settings_interactive()
    forms.alert(u"Отменено, настройки не изменены." if edited is None else u"Настройки сохранены.")
    script.exit()


settings = detector_access_settings.get_settings_silent()

selected_ids = list(uidoc.Selection.GetElementIds())
selected = slab_marks.collect_detectors(doc, settings, selected_ids) if selected_ids else []

views = forms.select_views(
    title=u"Планы, на которых показать зоны доступа",
    filterfunc=slab_marks.is_plan, multiple=True, use_selection=False)
if not views:
    script.exit()

if selected:
    detectors = selected
else:
    level_ids = set(view.GenLevel.Id.IntegerValue for view in views)
    levels = slab_marks.plan_levels(doc)
    detectors = []
    for detector in slab_marks.collect_detectors(doc, settings):
        level, _z = slab_marks.level_of(doc, detector, levels)
        if level is not None and level.Id.IntegerValue in level_ids:
            detectors.append(detector)
if not detectors:
    forms.alert(u"Не найдено ни одного извещателя (проверьте слова в настройках: Shift+клик).",
                title=TITLE, exitscript=True)

draw_results = []
with forms.ProgressBar(title=TITLE + u": {value} из {max_value}", cancellable=False) as bar:
    def progress(index, total):
        if index % 10 == 0:
            bar.update_progress(index, total)

    with revit.Transaction(TITLE):
        probe = slab_marks.SlabProbe(doc)
        try:
            checks, failed, unknown = detector_access.assess(doc, detectors, settings, probe, progress)
            note_type = detector_access.text_type(doc)
            line_styles = detector_access.styles(doc)
            for view in views:
                draw_results.append(detector_access.draw(
                    doc, view, checks, settings, note_type, line_styles))
        finally:
            probe.close()


output = script.get_output()
output.print_md(u"## " + TITLE)
if unknown:
    output.print_md(u"- **не найдены категории препятствий из настроек:** " + u", ".join(unknown))

problems = [check for check in checks if not check.ok]
ok_count = len(checks) - len(problems)
moves = [check for check in problems if check.spot is not None]
output.print_md(u"- проверено извещателей: {}, доступны: {}, **нет доступа: {}**, "
                u"найдено новое место: {}".format(len(checks), ok_count, len(problems), len(moves)))

for status in (core.BLOCKED, core.NEAR_WALL, core.NO_FLOOR, core.ABOVE_CEILING, core.TOO_HIGH,
               core.NOT_MOUNTED, core.NO_SLAB):
    group = [check for check in problems if check.status == status]
    if not group:
        continue
    output.print_md(u"### {} ({})".format(core.STATUS_TEXT[status].capitalize(), len(group)))
    for check in group:
        parts = [output.linkify(check.detector.Id)]
        if check.room:
            parts.append(u"«{}»".format(check.room))
        if check.height_mm is not None:
            parts.append(u"на {} м от пола".format(
                slab_marks.core.format_height(check.height_mm, signed=False)))
        if status in (core.BLOCKED, core.NEAR_WALL):
            parts.append(check.reason)
        if check.spot is not None:
            parts.append(u"→ " + core.move_label(
                settings.get("move_text_format"),
                slab_marks.mm(check.spot[0] - check.point.X), slab_marks.mm(check.spot[1] - check.point.Y)))
        elif check.search_note:
            parts.append(check.search_note)
        output.print_md(u"- " + u" — ".join(parts))
        if status == core.BLOCKED:
            for obstacle in check.zone_blockers[:5]:
                output.print_md(u"    - {}".format(obstacle.label or obstacle.name))

for result in draw_results:
    output.print_md(u"### План «{}»".format(result.view.Name))
    output.print_md(u"- зон доступа: {}, недоступных: {}, показано переносов: {}".format(
        result.ok, result.problems, result.moves))
    for error in result.errors:
        output.print_md(u"- ошибка: " + error)

if failed:
    output.print_md(u"### Не проверены")
    for detector, reason in failed:
        link = output.linkify(detector.Id) if detector is not None else u""
        output.print_md(u"- {} {}".format(link, reason))

if problems:
    from System.Collections.Generic import List
    from Autodesk.Revit.DB import ElementId
    ids = List[ElementId]()
    for check in problems:
        ids.Add(check.detector.Id)
    uidoc.Selection.SetElementIds(ids)

forms.alert(
    u"Готово.\n\nПроверено: {}, доступны: {}, нет доступа: {} (новое место найдено: {}).\n{}"
    u"Подробности — в окне вывода.".format(
        len(checks), ok_count, len(problems), len(moves),
        u"Недоступные извещатели выделены.\n" if problems else u""),
    title=TITLE)
