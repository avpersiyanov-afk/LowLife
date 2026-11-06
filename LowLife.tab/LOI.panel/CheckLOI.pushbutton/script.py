# -*- coding: utf-8 -*-

try:
    unicode  # noqa: F821 — IronPython/Python 2
except NameError:  # Python 3
    unicode = str


__title__ = u"Проверка\nLOI"
__author__ = "Pipers"

import traceback
from lowlife.i18n import tr

from pyrevit import revit, forms, script, EXEC_PARAMS

doc = revit.doc
uidoc = revit.uidoc

TITLE = tr(u"Проверка LOI")
MAX_ROWS = 300  # строк в таблице отчёта на категорию


def _cell(text):
    # «|» ломает markdown-таблицу отчёта
    return unicode(text or u"").replace(u"|", u"/")


def _report(output, results, missing_categories, views_3d, stage):
    output.print_md(tr(u"# Проверка LOI"))
    output.print_md(tr(u"Этап: **{}**").format(stage.title) if stage is not None
                    else tr(u"Проверка по своему списку параметров."))
    if views_3d:
        for param, view, count, hidden, hidden_cats in views_3d:
            output.print_md(
                tr(u"Параметр «{}»: 3D-вид {} (элементов: {}; скрыто фильтром: {}; "
                   u"выключено категорий: {})").format(
                    _cell(param), output.linkify(view.Id, view.Name), count, hidden, hidden_cats))
    else:
        output.print_md(tr(u"3D-виды не созданы. Виды прошлых запусков сохраняют прежний результат."))
    if missing_categories:
        output.print_md(tr(u"**Категории не найдены в документе:** {}").format(
            u", ".join(missing_categories)))

    for res in results:
        s = res.summary
        output.print_md(tr(u"## {} — элементов: {}, с незаполненными параметрами: {}").format(
            s.category_name, s.total, s.incomplete))
        if res.schedule is not None:
            output.print_md(tr(u"Спецификация: {}").format(
                output.linkify(res.schedule.Id, res.schedule.Name)))
        if res.missing_fields:
            output.print_md(tr(u"**Не выведены в спецификацию:**"))
            output.print_table(
                table_data=[[_cell(label), tr(reason)] for label, reason in res.missing_fields],
                columns=[tr(u"Параметр"), tr(u"Почему")])
        if res.no_code:
            output.print_md(
                tr(u"Без кода классификатора: {} — проверены по параметрам, общим "
                u"для всех классов категории.").format(res.no_code))
        if res.unknown_codes:
            output.print_md(
                tr(u"Не проверялись — кода нет в загруженных разделах приложения: {}").format(
                    u", ".join(u"{} ({})".format(_cell(code), n)
                               for code, n in sorted(res.unknown_codes.items()))))
        if not s.total:
            continue

        output.print_table(
            table_data=[[st.label, st.param_name, st.filled, st.empty, st.absent]
                        for st in s.stats],
            columns=[tr(u"Строка списка"), tr(u"Параметр"), tr(u"Заполнено"), tr(u"Пусто"), tr(u"Нет параметра")])
        if stage is not None:
            output.print_md(tr(u"Пустая ячейка в списке ниже — параметр у этого класса на этапе не требуется."))

        if res.incomplete_rows:
            shown = res.incomplete_rows[:MAX_ROWS]
            output.print_table(
                table_data=[[output.linkify(r.element.Id)]
                            + [_cell(x) for x in [r.type_name, r.family_name, r.floor] + r.cells]
                            for r in shown],
                columns=[u"ID", tr(u"Тип"), tr(u"Семейство"), tr(u"Этаж")] + [label for label, _ in res.rows],
                title=tr(u"Незаполненные элементы"))
            if len(res.incomplete_rows) > MAX_ROWS:
                output.print_md(tr(u"…и ещё {} — полный список в спецификации.").format(
                    len(res.incomplete_rows) - MAX_ROWS))


def main():
    from lowlife import loi_check_settings, loi_check, select_list

    try:
        config_mode = bool(EXEC_PARAMS.config_mode)
    except Exception:
        config_mode = False

    if config_mode:
        edited = loi_check_settings.get_settings_interactive(doc)
        forms.alert(
            tr(u"Отменено, настройки не изменены.") if edited is None
            else tr(u"Настройки сохранены.")
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
            tr(u"Ни одна категория не найдена в документе:\n{}").format(
                u", ".join(missing_categories)),
            title=TITLE, exitscript=True)

    results = [loi_check.check_category(doc, cat, rows, floor_param, plan, code_param)
               for cat, rows, plan in targets]
    if stage is not None:
        # категории приложения без единого проверенного элемента — без спецификаций
        results = [r for r in results if r.summary.total or r.unknown_codes]

    with revit.Transaction(u"Проверка LOI — спецификации и 3D-виды"):
        for res in results:
            if stage is not None and not res.summary.total:
                continue
            res.schedule, res.missing_fields = loi_check.build_schedule(
                doc, res.category, res.rows, floor_param)
        views_3d = loi_check.build_3d_views(doc, results)

    _report(script.get_output(), results, missing_categories, views_3d, stage)

    if views_3d:
        chosen = select_list.SelectFromList.show(
            [view for _param, view, _count, _hidden, _cats in views_3d],
            name_attr="Name", title=tr(u"Открыть 3D-вид по параметру"),
            button_name=tr(u"Открыть"), multiselect=False)
        if chosen is not None:
            _open(chosen)
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
        tr(u"Сбой в «Проверка LOI»:\n\n{}").format(traceback.format_exc()),
        title=TITLE
    )
