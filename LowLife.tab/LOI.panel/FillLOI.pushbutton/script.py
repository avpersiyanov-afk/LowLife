# -*- coding: utf-8 -*-

__title__ = u"Заполнение\nLOI"
__author__ = "Pipers"

import traceback

from pyrevit import revit, forms, script, EXEC_PARAMS

doc = revit.doc
uidoc = revit.uidoc


def main():
    from lowlife import loi_settings, loi_fill, loi_split, loi_conflict_dialog

    try:
        config_mode = bool(EXEC_PARAMS.config_mode)
    except Exception:
        config_mode = False

    if config_mode:
        edited = loi_settings.get_settings_interactive(doc)
        forms.alert(
            u"Отменено, настройки не изменены." if edited is None
            else u"Настройки сохранены."
        )
        return

    settings = loi_settings.get_settings_silent()
    loi_settings.require(settings, ["param_names_text"])
    loi_settings.require_selection_mode(settings)

    category_name = loi_fill.FORM_CATEGORY_NAME
    param_names = loi_settings.get_param_names(settings)
    search_locations = loi_settings.get_search_locations(settings)
    selection_mode = loi_settings.get_selection_mode(settings)
    selected_type_ids = loi_settings.get_selected_type_ids(settings)
    split_enabled = loi_settings.get_split_enabled(settings)

    view = doc.ActiveView
    if view is None:
        forms.alert(u"Нет активного вида.", exitscript=True)

    form_records = loi_fill.find_forms(doc, category_name, locations=search_locations)
    if not form_records:
        forms.alert(
            u"Не найдено элементов категории «{}» с геометрией (солидом) — "
            u"ни в одной из настроенных моделей.\n\n"
            u"В каких моделях искать — настраивается: Shift+клик по кнопке "
            u"«Заполнение LOI».".format(category_name),
            exitscript=True
        )

    candidates = loi_fill.collect_candidates(
        doc, view, category_name, mode=selection_mode, type_ids=selected_type_ids
    )
    matches = loi_fill.classify_elements(form_records, candidates)

    singles = [m for m in matches.values() if len(m.forms) == 1]
    multi = [m for m in matches.values() if len(m.forms) > 1]

    # Из «конфликтов» (элемент сразу в нескольких формах) сперва отделяем
    # то, что можно физически разрезать по границе форм (прямой линейный
    # элемент — лоток, короб, труба…) — см. loi_split.py. Что разрезать не
    # удалось (кривые участки, точечные элементы, наложенные формы),
    # остаётся конфликтом и идёт в диалог выбора формы-источника, как раньше.
    split_plans = []
    still_multi = []
    if split_enabled:
        for match in multi:
            plan = loi_split.plan_split(match)
            if plan:
                split_plans.append((match, plan))
            else:
                still_multi.append(match)
    else:
        still_multi = multi

    written_count = 0
    split_source_count = 0
    split_piece_count = 0
    failed_params = []

    def _apply_and_track(target_el, form_el):
        values = loi_fill.collect_form_values(form_el, param_names)
        applied = loi_fill.apply_values(target_el, values)
        for name, _val, ok in applied:
            if not ok:
                failed_params.append(u"{} (ID {}): {}".format(
                    loi_fill.element_display_name(doc, target_el),
                    target_el.Id.IntegerValue, name
                ))

    if singles or split_plans:
        with revit.Transaction(u"Заполнение LOI"):
            for match in singles:
                _apply_and_track(match.element, match.forms[0].element)
                written_count += 1

            for match, plan in split_plans:
                pieces = loi_split.execute_split(doc, match, plan)
                if not pieces:
                    # разрезать не удалось (Revit отклонил геометрию) —
                    # элемент остаётся как есть, отдаём его в конфликты
                    still_multi.append(match)
                    continue
                split_source_count += 1
                split_piece_count += len(pieces)
                for piece_el, form in pieces:
                    if form is None:
                        continue
                    _apply_and_track(piece_el, form.element)

    resolved_count = 0
    cancelled_conflicts = False

    if still_multi:
        mapping = loi_conflict_dialog.show_conflict_dialog(doc, uidoc, still_multi, param_names)
        if mapping is None:
            cancelled_conflicts = True
        elif mapping:
            with revit.Transaction(u"Заполнение LOI — конфликты"):
                for match in still_multi:
                    form = mapping.get(match.element.Id)
                    if form is None:
                        continue
                    _apply_and_track(match.element, form.element)
                    resolved_count += 1

    report_lines = [
        u"Форм найдено: {}".format(len(form_records)),
        u"Заполнено автоматически (1 форма): {}".format(written_count),
    ]

    if split_source_count:
        report_lines.append(
            u"Разделено по границе форм: {} элементов → {} кусков.".format(
                split_source_count, split_piece_count
            )
        )

    if still_multi:
        if cancelled_conflicts:
            report_lines.append(u"Конфликтов (несколько форм): {} — отменено пользователем.".format(len(still_multi)))
        else:
            report_lines.append(u"Конфликтов (несколько форм): {}, разрешено: {}.".format(len(still_multi), resolved_count))

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
