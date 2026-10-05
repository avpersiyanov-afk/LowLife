# -*- coding: utf-8 -*-

__title__ = u"Обновить\nимя уровня"
__author__ = "Pipers"

import traceback

from pyrevit import revit, forms, EXEC_PARAMS

from Autodesk.Revit.DB import ElementType

doc = revit.doc
uidoc = revit.uidoc

TITLE = u"Обновить имя уровня"


def _selected_elements():
    """Выбранные элементы модели (без типоразмеров и элементов без категории)."""
    els = []
    for el_id in uidoc.Selection.GetElementIds():
        el = doc.GetElement(el_id)
        if el is None or isinstance(el, ElementType) or el.Category is None:
            continue
        els.append(el)
    return els


def main():
    from lowlife import level_name_settings, level_name_fill

    try:
        config_mode = bool(EXEC_PARAMS.config_mode)
    except Exception:
        config_mode = False

    if config_mode:
        edited = level_name_settings.get_settings_interactive()
        forms.alert(
            u"Отменено, настройки не изменены." if edited is None
            else u"Настройки сохранены."
        )
        return

    settings = level_name_settings.get_settings_silent()
    level_name_settings.require(settings, [level_name_settings.PARAM_KEY])
    target_param_name = settings[level_name_settings.PARAM_KEY].strip()

    elements = _selected_elements()
    if not elements:
        forms.alert(
            u"Сначала выберите элементы в Revit, потом запустите кнопку.",
            title=TITLE, exitscript=True
        )

    with revit.Transaction(TITLE):
        result = level_name_fill.fill_level_names(doc, elements, target_param_name)

    report_lines = [
        u"Выбрано элементов: {}".format(len(elements)),
        u"Записано: {}".format(result.written),
    ]

    if result.by_elevation:
        report_lines.append(
            u"  из них по высоте (у элемента нет уровня в свойствах): {}".format(
                result.by_elevation
            )
        )

    if result.no_level:
        report_lines.append(
            u"Не удалось определить уровень (пропущено): {}".format(result.no_level)
        )

    if result.failed:
        report_lines.append(u"")
        report_lines.append(
            u"Не удалось записать параметр «{}» у {} элементов "
            u"(нет такого параметра или он нередактируемый).".format(
                target_param_name, len(result.failed)
            )
        )

    forms.alert(u"\n".join(report_lines), title=TITLE)


try:
    main()
except SystemExit:
    pass
except Exception:
    forms.alert(
        u"Сбой в «{}»:\n\n{}".format(TITLE, traceback.format_exc()),
        title=TITLE
    )
