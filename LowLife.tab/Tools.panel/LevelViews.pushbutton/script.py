# -*- coding: utf-8 -*-

__title__ = u"Виды по\nуровням"
__author__ = "Pipers"

import traceback

from pyrevit import revit, forms

doc = revit.doc

TITLE = u"Виды по уровням"
_ALERT_MAX_LINES = 30


def _report(results):
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

    if len(lines) <= _ALERT_MAX_LINES:
        forms.alert(u"\n".join(lines), title=TITLE)
        return
    # Длинный список ошибок — в окно вывода pyRevit, в сообщении только итог.
    from pyrevit import script
    output = script.get_output()
    output.set_title(TITLE)
    for line in lines:
        print(line)
    forms.alert(lines[0] + u"\n" + lines[1] + u"\n\nПодробности — в окне вывода.",
                title=TITLE)


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

    level_template = lvs.level_template()
    picked = level_views_dialog.show(doc, templates, levels, lvs.load(), level_template)
    if picked is None:
        return
    mask, items, values = picked
    checked = []
    for t, _v in items:
        name = level_views.safe_name(t)
        if name not in checked:
            checked.append(name)
    lvs.save(mask, values, checked)

    with revit.Transaction(TITLE):
        results = level_views.build_views(doc, levels, items, mask, level_template)
    _report(results)


try:
    main()
except SystemExit:
    pass
except Exception:
    forms.alert(
        u"Сбой в «{}»:\n\n{}".format(TITLE, traceback.format_exc()),
        title=TITLE
    )
