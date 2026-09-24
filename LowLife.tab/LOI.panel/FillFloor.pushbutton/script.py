# -*- coding: utf-8 -*-

__title__ = u"Заполнение\nэтажа"
__author__ = "Pipers"

import traceback

from pyrevit import revit, forms, EXEC_PARAMS

doc = revit.doc
uidoc = revit.uidoc


def main():
    from lowlife import floor_settings, floor_fill

    try:
        config_mode = bool(EXEC_PARAMS.config_mode)
    except Exception:
        config_mode = False

    if config_mode:
        edited = floor_settings.get_settings_interactive(doc)
        forms.alert(
            u"Отменено, настройки не изменены." if edited is None
            else u"Настройки сохранены."
        )
        return

    settings = floor_settings.get_settings_silent()
    floor_settings.require(settings)

    target_param_name = settings[floor_settings.PARAM_KEY].strip()
    level_values = floor_settings.get_level_values(settings)

    with revit.Transaction(u"Заполнение этажа"):
        result = floor_fill.fill_floors(doc, target_param_name, level_values)

    report_lines = [
        u"Записано: {}".format(result.written),
    ]

    if result.no_level:
        report_lines.append(u"Без уровня (пропущено): {}".format(result.no_level))

    if result.unmapped_levels:
        report_lines.append(
            u"Уровни без значения в настройках (пропущено): {}".format(
                u", ".join(sorted(result.unmapped_levels))
            )
        )

    if result.failed:
        report_lines.append(u"")
        report_lines.append(
            u"Не удалось записать параметр «{}» у {} элементов "
            u"(нет такого параметра или он нередактируемый).".format(
                target_param_name, len(result.failed)
            )
        )

    forms.alert(u"\n".join(report_lines), title=u"Заполнение этажа")


try:
    main()
except SystemExit:
    pass
except Exception:
    forms.alert(
        u"Сбой в «Заполнение этажа»:\n\n{}".format(traceback.format_exc()),
        title=u"Заполнение этажа"
    )
