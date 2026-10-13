# -*- coding: utf-8 -*-

__title__ = u"Виды по\nуровням"
__author__ = "Pipers"

import traceback

from pyrevit import revit, forms, EXEC_PARAMS

doc = revit.doc

TITLE = u"Виды по уровням"
_ALERT_MAX_LINES = 30


class _Option(object):
    def __init__(self, item, label):
        self.item = item
        self.label = label


def _pick(options, checked_labels, title, button):
    """Отмеченные варианты (SelectFromList, несколько) или None — отмена."""
    items = [forms.TemplateListItem(o, checked=(o.label in checked_labels), name_attr="label")
             for o in options]
    chosen = forms.SelectFromList.show(
        items, title=title, button_name=button, multiselect=True, width=520, height=600)
    if not chosen:
        return None
    return chosen


def _report(results):
    from lowlife.geometry import level_name

    done = [r for r in results if r.error is None]
    failed = [r for r in results if r.error is not None]
    created = len([r for r in done if r.action == u"создан"])
    updated = len(done) - created

    lines = [u"Создано видов: {}, обновлено: {}.".format(created, updated)]
    if failed:
        lines.append(u"Не получилось: {}.".format(len(failed)))
    for r in done:
        line = u"  • {} — {}".format(r.name, r.action)
        if r.links:
            line += u"; связи: " + u", ".join(
                u"{} → «{}»".format(link, view) for link, view in r.links)
        lines.append(line)
        lines.extend(u"      ! {}".format(n) for n in r.notes)
    if failed:
        lines.append(u"")
        lines.append(u"Ошибки:")
        for r in failed:
            lines.append(u"  • {} / {}: {}".format(
                level_name(r.level), r.group[u"name"], r.error))
    if len(lines) <= _ALERT_MAX_LINES:
        forms.alert(u"\n".join(lines), title=TITLE)
        return
    # Длинный отчёт — в окно вывода pyRevit, в сообщении только итог.
    from pyrevit import script
    output = script.get_output()
    output.set_title(TITLE)
    for line in lines:
        print(line)
    forms.alert(lines[0] + (u"\n" + lines[1] if failed else u"") +
                u"\n\nПодробности — в окне вывода.", title=TITLE)


def main():
    from lowlife import level_views, level_views_settings as lvs
    from lowlife import level_name_template
    from lowlife import level_views_core as core
    from lowlife.geometry import level_name

    try:
        config_mode = bool(EXEC_PARAMS.config_mode)
    except Exception:
        config_mode = False

    if config_mode:
        edited = lvs.get_settings_interactive(doc)
        forms.alert(
            u"Отменено, настройки не изменены." if edited is None
            else u"Настройки сохранены.",
            title=TITLE
        )
        return

    settings = lvs.get_settings_silent()
    if not settings[lvs.GROUPS_KEY]:
        forms.alert(u"Групп видов пока нет — сейчас откроются настройки "
                    u"(потом их можно открыть Shift+кликом по кнопке).", title=TITLE)
        settings = lvs.get_settings_interactive(doc)
        if settings is None or not settings[lvs.GROUPS_KEY]:
            return

    levels = level_views.document_levels(doc)
    if not levels:
        forms.alert(u"В проекте нет уровней.", title=TITLE)
        return

    level_options = [_Option(l, level_name(l)) for l in levels]
    chosen_levels = _pick(level_options, set(settings[lvs.LAST_LEVELS_KEY]),
                          u"Уровни, для которых создать виды", u"Далее")
    if chosen_levels is None:
        return

    groups = settings[lvs.GROUPS_KEY]
    if len(groups) == 1:
        chosen_groups = [_Option(groups[0], groups[0][core.G_NAME])]
    else:
        last = set(settings[lvs.LAST_GROUPS_KEY]) or set(g[core.G_NAME] for g in groups)
        chosen_groups = _pick([_Option(g, g[core.G_NAME]) for g in groups], last,
                              u"Группы видов", u"Создать виды")
        if chosen_groups is None:
            return

    lvs.remember_choice([o.label for o in chosen_levels], [o.label for o in chosen_groups])

    level_template = level_name_template.LevelNameTemplate(settings[lvs.LEVEL_TEMPLATE_KEY])
    with revit.Transaction(TITLE):
        results = level_views.build_views(
            doc, [o.item for o in chosen_levels], [o.item for o in chosen_groups],
            level_template)
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
