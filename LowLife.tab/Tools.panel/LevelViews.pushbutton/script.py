# -*- coding: utf-8 -*-

__title__ = u"Виды по\nуровням"
__author__ = "Pipers"

import traceback

from pyrevit import revit, forms

doc = revit.doc

TITLE = u"Виды по уровням"
_ALERT_MAX_LINES = 30


def _report(results, align_range=False):
    from lowlife.geometry import level_name
    from lowlife.level_views import safe_name

    done = [r for r in results if r.error is None]
    failed = [r for r in results if r.error is not None]
    created = len([r for r in done if r.action == u"создан"])

    lines = [u"Создано видов: {}, уже были (назначен шаблон): {}.".format(
        created, len(done) - created)]
    if failed:
        lines.append(u"Не получилось: {}.".format(len(failed)))
        lines.append(u"")
        for r in failed:
            lines.append(u"  • {} ({} / {}): {}".format(
                r.name or u"—", safe_name(r.template), level_name(r.level), r.error))
    if align_range:
        with_view = [r for r in results if r.view is not None]
        skipped = [r for r in with_view if r.range_note]
        lines.append(u"")
        lines.append(u"Секущий диапазон выровнен: {} из {}.".format(
            len(with_view) - len(skipped), len(with_view)))
        for r in skipped:
            lines.append(u"  • {}: {}".format(r.name, r.range_note))

    if len(lines) <= _ALERT_MAX_LINES:
        forms.alert(u"\n".join(lines), title=TITLE)
        return
    # Длинный список ошибок — в окно вывода pyRevit, в сообщении только итог.
    from pyrevit import script
    output = script.get_output()
    output.set_title(TITLE)
    for line in lines:
        print(line)
    forms.alert(lines[0] + u"\n\nПодробности — в окне вывода.", title=TITLE)


def main():
    from lowlife import level_views, level_views_dialog, level_views_settings as lvs

    templates = level_views.list_plan_templates(doc)
    if not templates:
        forms.alert(u"В проекте нет шаблонов видов для планов.", title=TITLE)
        return
    levels = level_views.document_levels(doc)
    if not levels:
        forms.alert(u"В проекте нет уровней.", title=TITLE)
        return

    from lowlife import settings_transfer

    level_template = lvs.level_template()
    while True:
        state = level_views_dialog.show(doc, templates, levels, lvs.load(), level_template, lvs)
        if state != settings_transfer.RELOAD:
            break
    if state is None:
        return
    if state["action"] == "save":
        forms.alert(u"Настройки сохранены.", title=TITLE)
        return
    mask, items, align_range = state["mask"], state["items"], state["align"]
    lvs.save(mask, state["values"], state["checked"], align_range)

    if align_range and not lvs.view_range_configured():
        from lowlife import view_range_settings
        forms.alert(u"Секущий диапазон ещё не настроен — сейчас откроется настройка "
                    u"кнопки «Секущий диапазон» (шаблон имени уровня, по нему ищется "
                    u"следующий этаж).", title=TITLE)
        if view_range_settings.get_settings_interactive() is None:
            forms.alert(u"Отменено — виды не созданы.", title=TITLE)
            return
        level_template = lvs.level_template()

    with revit.Transaction(TITLE):
        results = level_views.build_views(doc, levels, items, mask, level_template)
        if align_range:
            level_views.align_ranges(doc, results, level_template)
    _report(results, align_range)


try:
    main()
except SystemExit:
    pass
except Exception:
    forms.alert(
        u"Сбой в «{}»:\n\n{}".format(TITLE, traceback.format_exc()),
        title=TITLE
    )
