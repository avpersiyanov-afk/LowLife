# -*- coding: utf-8 -*-

try:
    unicode  # noqa: F821 — IronPython/Python 2
except NameError:  # Python 3
    unicode = str


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


def _report(output, results, missing_categories, view_3d, stage, hidden_3d=0, hidden_cats=0):
    output.print_md(u"# Проверка LOI")
    output.print_md(u"Этап: **{}**".format(stage.title) if stage is not None
                    else u"Проверка по своему списку параметров.")
    if view_3d is not None:
        output.print_md(
            u"3D-вид с незаполненными элементами: {} (оставлено {}; заполненные — {} — "
            u"спрятаны фильтром вида; выключено других категорий: {})".format(
                output.linkify(view_3d.Id, view_3d.Name),
                sum(len(r.incomplete_rows) for r in results), hidden_3d, hidden_cats))
    else:
        output.print_md(u"Незаполненных элементов нет — 3D-вид не обновлялся (если он есть, на нём результат прошлого запуска).")
    if missing_categories:
        output.print_md(u"**Категории не найдены в документе:** {}".format(
            u", ".join(missing_categories)))

    for res in results:
        s = res.summary
        output.print_md(u"## {} — элементов: {}, с незаполненными параметрами: {}".format(
            s.category_name, s.total, s.incomplete))
        if res.schedule is not None:
            output.print_md(u"Спецификация: {}".format(
                output.linkify(res.schedule.Id, res.schedule.Name)))
        if res.missing_fields:
            output.print_md(u"**Не выведены в спецификацию:**")
            output.print_table(
                table_data=[[_cell(label), reason] for label, reason in res.missing_fields],
                columns=[u"Параметр", u"Почему"])
        if res.no_code:
            output.print_md(
                u"Без кода классификатора: {} — проверены по параметрам, общим "
                u"для всех классов категории.".format(res.no_code))
        if res.unknown_codes:
            output.print_md(
                u"Не проверялись — кода нет в загруженных разделах приложения: {}".format(
                    u", ".join(u"{} ({})".format(_cell(code), n)
                               for code, n in sorted(res.unknown_codes.items()))))
        if not s.total:
            continue

        output.print_table(
            table_data=[[st.label, st.param_name, st.filled, st.empty, st.absent]
                        for st in s.stats],
            columns=[u"Строка списка", u"Параметр", u"Заполнено", u"Пусто", u"Нет параметра"])
        if stage is not None:
            output.print_md(u"Пустая ячейка в списке ниже — параметр у этого класса на этапе не требуется.")

        if res.incomplete_rows:
            shown = res.incomplete_rows[:MAX_ROWS]
            output.print_table(
                table_data=[[output.linkify(r.element.Id)]
                            + [_cell(x) for x in [r.type_name, r.family_name, r.floor] + r.cells]
                            for r in shown],
                columns=[u"ID", u"Тип", u"Семейство", u"Этаж"] + [label for label, _ in res.rows],
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
    stage = loi_check_settings.choose_stage(settings)
    floor_param = loi_check_settings.get_floor_param(settings)

    if stage is None:
        loi_check_settings.require(settings)
        rows = loi_check_settings.get_rows(settings)
        categories, missing_categories = loi_check.resolve_categories(
            doc, settings[loi_check_settings.CATEGORIES_KEY])
        targets = [(cat, rows, None) for cat in categories]
        code_param = None
    else:
        from lowlife import loi_check_core
        appendix = loi_check_settings.get_appendix(settings)
        plans = loi_check_core.plans_for_stage(appendix, stage)
        found, missing_categories = loi_check.resolve_plan_categories(doc, plans)
        targets = [(cat, [(name, name) for name in plan.columns], plan) for cat, plan in found]
        code_param = appendix.get("code_param")

    if not targets:
        forms.alert(
            u"Ни одна категория не найдена в документе:\n{}".format(
                u", ".join(missing_categories)),
            title=TITLE, exitscript=True)

    results = [loi_check.check_category(doc, cat, rows, floor_param, plan, code_param)
               for cat, rows, plan in targets]
    if stage is not None:
        # категории приложения без единого проверенного элемента — без спецификаций
        results = [r for r in results if r.summary.total or r.unknown_codes]

    incomplete = [row.element for res in results for row in res.incomplete_rows]

    with revit.Transaction(u"Проверка LOI — спецификации и 3D-вид"):
        for res in results:
            if stage is not None and not res.summary.total:
                continue
            res.schedule, res.missing_fields = loi_check.build_schedule(
                doc, res.category, res.rows, floor_param)
        view_3d, hidden_3d, hidden_cats = loi_check.build_3d_view(
            doc, incomplete, [res.category for res in results])

    _report(script.get_output(), results, missing_categories, view_3d, stage, hidden_3d, hidden_cats)

    if view_3d is not None:
        total = len(incomplete)
        if forms.alert(
                u"Элементов с незаполненными параметрами: {}.\n\n"
                u"Открыть 3D-вид «{}»?".format(total, view_3d.Name),
                title=TITLE, yes=True, no=True):
            _open(view_3d)
        return

    _open(next((r.schedule for r in results if r.schedule is not None), None))


def _open(view):
    if view is None:
        return
    try:
        uidoc.ActiveView = view
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
