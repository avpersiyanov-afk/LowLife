# -*- coding: utf-8 -*-

__title__ = u"Проверка\nLOI"
__author__ = "Pipers"

import traceback

from pyrevit import revit, forms, script, EXEC_PARAMS

doc = revit.doc
uidoc = revit.uidoc

TITLE = u"Проверка LOI"
MAX_ROWS = 300  # строк в таблице отчёта на категорию


def _cell(text):
    # «|» ломает markdown-таблицу отчёта
    return unicode(text or u"").replace(u"|", u"/")


def _report(output, results, rows, missing_categories, view_3d):
    output.print_md(u"# Проверка LOI")
    if view_3d is not None:
        output.print_md(u"3D-вид с незаполненными элементами: {}".format(
            output.linkify(view_3d.Id, view_3d.Name)))
    else:
        output.print_md(u"Незаполненных элементов нет — 3D-вид не обновлялся (если он есть, на нём результат прошлого запуска).")
    if missing_categories:
        output.print_md(u"**Категории из настроек не найдены в документе:** {}".format(
            u", ".join(missing_categories)))

    for res in results:
        s = res.summary
        output.print_md(u"## {} — элементов: {}, с незаполненными параметрами: {}".format(
            s.category_name, s.total, s.incomplete))
        if res.schedule is not None:
            output.print_md(u"Спецификация: {}".format(
                output.linkify(res.schedule.Id, res.schedule.Name)))
        if res.missing_fields:
            output.print_md(
                u"**Не выведены в спецификацию** (нет такого параметра среди полей "
                u"категории): {}".format(u", ".join(res.missing_fields)))
        if not s.total:
            continue

        output.print_table(
            table_data=[[st.label, st.param_name, st.filled, st.empty, st.absent]
                        for st in s.stats],
            columns=[u"Строка списка", u"Параметр", u"Заполнено", u"Пусто", u"Нет параметра"])

        if res.incomplete_rows:
            shown = res.incomplete_rows[:MAX_ROWS]
            output.print_table(
                table_data=[[output.linkify(r.element.Id)]
                            + [_cell(x) for x in [r.type_name, r.family_name, r.floor] + r.cells]
                            for r in shown],
                columns=[u"ID", u"Тип", u"Семейство", u"Этаж"] + [label for label, _ in rows],
                title=u"Незаполненные элементы")
            if len(res.incomplete_rows) > MAX_ROWS:
                output.print_md(u"…и ещё {} — полный список в спецификации.".format(
                    len(res.incomplete_rows) - MAX_ROWS))


def main():
    from lowlife import loi_check_settings, loi_check

    try:
        config_mode = bool(EXEC_PARAMS.config_mode)
    except Exception:
        config_mode = False

    if config_mode:
        edited = loi_check_settings.get_settings_interactive(doc)
        forms.alert(
            u"Отменено, настройки не изменены." if edited is None
            else u"Настройки сохранены."
        )
        return

    settings = loi_check_settings.get_settings_silent()
    loi_check_settings.require(settings)

    rows = loi_check_settings.get_rows(settings)
    floor_param = loi_check_settings.get_floor_param(settings)
    categories, missing_categories = loi_check.resolve_categories(
        doc, settings[loi_check_settings.CATEGORIES_KEY])
    if not categories:
        forms.alert(
            u"Ни одна категория из настроек не найдена в документе:\n{}".format(
                u", ".join(missing_categories)),
            title=TITLE, exitscript=True)

    results = [loi_check.check_category(doc, cat, rows, floor_param) for cat in categories]

    incomplete = [row.element for res in results for row in res.incomplete_rows]

    with revit.Transaction(u"Проверка LOI — спецификации и 3D-вид"):
        for res in results:
            res.schedule, res.missing_fields = loi_check.build_schedule(
                doc, res.category, rows, floor_param)
        view_3d = loi_check.build_3d_view(doc, incomplete)

    _report(script.get_output(), results, rows, missing_categories, view_3d)

    first = view_3d or next((r.schedule for r in results if r.schedule is not None), None)
    if first is not None:
        try:
            uidoc.ActiveView = first
        except Exception:
            pass


try:
    main()
except SystemExit:
    pass
except Exception:
    forms.alert(
        u"Сбой в «Проверка LOI»:\n\n{}".format(traceback.format_exc()),
        title=TITLE
    )
