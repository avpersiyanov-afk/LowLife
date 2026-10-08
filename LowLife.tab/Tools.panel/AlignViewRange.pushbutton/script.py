# -*- coding: utf-8 -*-

__title__ = u"Секущий\nдиапазон"
__author__ = "Pipers"

import traceback

from pyrevit import revit, forms

doc = revit.doc
uidoc = revit.uidoc

TITLE = u"Секущий диапазон"


def _target_views():
    from lowlife import view_range

    selected = [doc.GetElement(i) for i in uidoc.Selection.GetElementIds()]
    views = [v for v in selected if view_range.is_plan(v)]
    if views:
        return views

    active = doc.ActiveView
    if view_range.is_plan(active):
        return [active]
    forms.alert(u"Откройте план этажа (или выделите планы в Диспетчере проекта) — "
                u"секущий диапазон выравнивается только у планов.", title=TITLE)
    return []


def main():
    from lowlife import view_range, family_section_settings as fss, level_name_template
    from lowlife.geometry import level_name

    views = _target_views()
    if not views:
        return

    level_template = level_name_template.LevelNameTemplate(
        fss.get_settings_silent()[fss.LEVEL_TEMPLATE_KEY])

    with revit.Transaction(TITLE):
        results = [view_range.align_view_range(doc, v, level_template) for v in views]

    done = [r for r in results if r.error is None]
    failed = [r for r in results if r.error is not None]
    notes = sorted(set(r.note for r in done if r.note))

    lines = [u"Выровнено видов: {}".format(len(done))]
    for r in done:
        top = level_name(r.top_level) if r.top_level is not None else u"неограниченно"
        lines.append(u"  • {} — верх: {}".format(r.view_name(), top))
    if failed:
        lines.append(u"")
        lines.append(u"Пропущено:")
        lines.extend(u"  • {}: {}".format(r.view_name(), r.error) for r in failed)
    if notes:
        lines.append(u"")
        lines.append(u"Примечания:")
        lines.extend(u"  • {}".format(n) for n in notes)
    forms.alert(u"\n".join(lines), title=TITLE)


try:
    main()
except SystemExit:
    pass
except Exception:
    forms.alert(
        u"Сбой в «{}»:\n\n{}".format(TITLE, traceback.format_exc()),
        title=TITLE
    )
