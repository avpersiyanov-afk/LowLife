# -*- coding: utf-8 -*-

__title__ = u"Заполнение\nLOI"
__author__ = "Pipers"

import traceback

from pyrevit import revit, forms, script, EXEC_PARAMS

doc = revit.doc
uidoc = revit.uidoc


def main():
    from lowlife import loi_settings, loi_fill, loi_conflict_dialog

    try:
        config_mode = bool(EXEC_PARAMS.config_mode)
    except Exception:
        config_mode = False

    if config_mode:
        edited = loi_settings.get_settings_interactive()
        forms.alert(
            u"Отменено, настройки не изменены." if edited is None
            else u"Настройки сохранены."
        )
        return

    settings = loi_settings.get_settings_silent()
    loi_settings.require(settings, ["form_category_name", "param_names_text"])

    category_name = settings["form_category_name"].strip()
    param_names = loi_settings.get_param_names(settings)

    view = doc.ActiveView
    if view is None:
        forms.alert(u"Нет активного вида.", exitscript=True)

    form_records = loi_fill.find_forms(doc, view, category_name)
    if not form_records:
        forms.alert(
            u"Не найдено элементов категории «{}» с геометрией (солидом) — "
            u"ни в текущем файле, ни в загруженных связях.\n\n"
            u"Имя категории задаётся в настройках: Shift+клик по кнопке.".format(category_name),
            exitscript=True
        )

    candidates = loi_fill.collect_candidates(doc, view, category_name)
    matches = loi_fill.classify_elements(form_records, candidates)

    singles = [m for m in matches.values() if len(m.forms) == 1]
    multi = [m for m in matches.values() if len(m.forms) > 1]

    written_count = 0
    failed_params = []

    if singles:
        with revit.Transaction(u"Заполнение LOI"):
            for match in singles:
                values = loi_fill.collect_form_values(match.forms[0].element, param_names)
                applied = loi_fill.apply_values(match.element, values)
                written_count += 1
                for name, _val, ok in applied:
                    if not ok:
                        failed_params.append(u"{} (ID {}): {}".format(
                            loi_fill.element_display_name(doc, match.element),
                            match.element.Id.IntegerValue, name
                        ))

    resolved_count = 0
    cancelled_conflicts = False

    if multi:
        mapping = loi_conflict_dialog.show_conflict_dialog(doc, uidoc, multi, param_names)
        if mapping is None:
            cancelled_conflicts = True
        elif mapping:
            with revit.Transaction(u"Заполнение LOI — конфликты"):
                for match in multi:
                    form = mapping.get(match.element.Id)
                    if form is None:
                        continue
                    values = loi_fill.collect_form_values(form.element, param_names)
                    applied = loi_fill.apply_values(match.element, values)
                    resolved_count += 1
                    for name, _val, ok in applied:
                        if not ok:
                            failed_params.append(u"{} (ID {}): {}".format(
                                loi_fill.element_display_name(doc, match.element),
                                match.element.Id.IntegerValue, name
                            ))

    report_lines = [
        u"Форм найдено: {}".format(len(form_records)),
        u"Заполнено автоматически (1 форма): {}".format(written_count),
    ]

    if multi:
        if cancelled_conflicts:
            report_lines.append(u"Конфликтов (несколько форм): {} — отменено пользователем.".format(len(multi)))
        else:
            report_lines.append(u"Конфликтов (несколько форм): {}, разрешено: {}.".format(len(multi), resolved_count))

    if failed_params:
        report_lines.append(u"")
        report_lines.append(u"Не удалось записать параметр у:")
        report_lines.extend(failed_params[:20])
        if len(failed_params) > 20:
            report_lines.append(u"… и ещё {}.".format(len(failed_params) - 20))

    forms.alert(u"\n".join(report_lines), title=u"Заполнение LOI")


try:
    main()
except SystemExit:
    pass
except Exception:
    forms.alert(
        u"Сбой в «Заполнение LOI»:\n\n{}".format(traceback.format_exc()),
        title=u"Заполнение LOI"
    )
