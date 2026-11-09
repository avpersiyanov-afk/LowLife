# -*- coding: utf-8 -*-

__title__ = u"Оси и уровни\nКФП"
__doc__ = (
    u"Сравнивает уровни и оси модели с уровнями и осями связи КФП и "
    u"показывает список расхождений: другая отметка, смещённая или "
    u"повёрнутая ось, другое имя, нет в модели / нет в связи. Предлагает "
    u"скопировать недостающие элементы с выбором типа и рабочего набора.\n\n"
    u"Shift+клик — настройки (слово в имени связи, допуск)."
)
__author__ = "Pipers"
__persistentengine__ = True

import traceback
from lowlife.i18n import tr

from pyrevit import revit, forms, script, EXEC_PARAMS

from lowlife import link_datums, link_datums_core, link_datums_settings, select_list
from lowlife.link_datums_core import OK, format_angle, format_mm

doc = revit.doc
TITLE = tr(u"Оси и уровни КФП")


def pick_link(keyword):
    links = link_datums.loaded_links(doc)
    if not links:
        forms.alert(tr(u"В модели нет загруженных связей Revit."), title=TITLE, exitscript=True)
    found = link_datums.matching_links(links, keyword) if keyword else []
    if len(found) == 1:
        return found[0]

    candidates = found or links
    by_name = {}
    for link in candidates:
        by_name[u"{} [{}]".format(link_datums.link_label(link), link.Id)] = link
    chosen = select_list.SelectFromList.show(
        sorted(by_name.keys()),
        title=tr(u"С какой связью сравнить оси и уровни"),
        button_name=tr(u"Сравнить"),
        multiselect=False,
    )
    if not chosen:
        script.exit()
    return by_name[chosen]


def _cell(text):
    return (text or u"").replace(u"|", u"/")


def _model_cell(output, item):
    if item is None:
        return u"—"
    return u"{} {}".format(_cell(item["name"]), output.linkify(item["id"]))


def _link_cell(item):
    if item is None:
        return u"—"
    return u"{} [{}]".format(_cell(item["name"]), item["id_int"])


def _ok_names(rows):
    return u", ".join(_cell(r.name) for r in rows if r.status == OK)


def report_levels(output, rows):
    counts = link_datums_core.count_by_status(rows)
    output.print_md(tr(u"## Уровни — {}").format(link_datums_core.summary_text(counts)))
    bad = link_datums_core.problems_first([r for r in rows if r.status != OK])
    if bad:
        output.print_table(
            table_data=[[r.status_text, _model_cell(output, r.model), _link_cell(r.link),
                         format_mm(r.model and r.model["elevation"]),
                         format_mm(r.link and r.link["elevation"]),
                         format_mm(r.delta)] for r in bad],
            columns=[tr(u"Статус"), tr(u"В модели"), tr(u"В связи"), tr(u"Отметка в модели, мм"),
                     tr(u"Отметка в связи, мм"), tr(u"Разница, мм")])
    if counts.get(OK):
        output.print_md(tr(u"**Совпадают:** {}").format(_ok_names(rows)))


def report_grids(output, rows):
    counts = link_datums_core.count_by_status(rows)
    output.print_md(tr(u"## Оси — {}").format(link_datums_core.summary_text(counts)))
    bad = link_datums_core.problems_first([r for r in rows if r.status != OK])
    if bad:
        output.print_table(
            table_data=[[r.status_text, _model_cell(output, r.model), _link_cell(r.link),
                         format_mm(r.delta), format_angle(r.angle), r.note] for r in bad],
            columns=[tr(u"Статус"), tr(u"В модели"), tr(u"В связи"), tr(u"Расхождение, мм"),
                     tr(u"Поворот"), tr(u"Примечание")])
    if counts.get(OK):
        output.print_md(tr(u"**Совпадают:** {}").format(_ok_names(rows)))


def main():
    try:
        config_mode = bool(EXEC_PARAMS.config_mode)
    except Exception:
        config_mode = False
    if config_mode:
        edited = link_datums_settings.get_settings_interactive()
        forms.alert(tr(u"Отменено, настройки не изменены.") if edited is None
                    else tr(u"Настройки сохранены."), title=TITLE)
        return

    settings = link_datums_settings.get_settings_silent()
    keyword = (settings.get("link_name_filter") or u"").strip()
    tolerance = settings.get("tolerance_mm")
    if tolerance is None:
        tolerance = 1.0

    link = pick_link(keyword)
    levels, grids = link_datums.compare(doc, link, float(tolerance))

    output = script.get_output()
    output.print_md(tr(u"# Оси и уровни: модель ↔ связь"))
    output.print_md(
        tr(u"Связь: **{}** · допуск {} мм · отметки — от базовой точки проекта "
        u"модели. Ссылки в столбце «В модели» выделяют элемент; в «В связи» — "
        u"ID в связанном файле.").format(
            _cell(link_datums.link_label(link)), format_mm(tolerance, 1)))
    report_levels(output, levels)
    report_grids(output, grids)

    from lowlife import link_datums_copy, link_datums_copy_dialog
    if not link_datums_copy.missing_rows(levels, grids):
        return
    choices = link_datums_copy_dialog.show(doc, levels, grids)
    if not choices:
        return
    from lowlife import link_datums_native, link_datums_views
    batches = link_datums_views.prepare(doc, link, choices)
    for view, selected in batches:
        output.print_md(tr(u'Создан контрольный вид: **{}** (элементов: {}).',
                           u'Control view created: **{}** (elements: {}).').format(
                               _cell(view.Name), len(selected)))
    output.print_md(tr(u'Сначала копируются уровни на 3D-виде, затем оси на плане. '
                       u'После успешного завершения первого сеанса откроется следующий вид. '
                       u'Отмена или отсутствие новых копий останавливают переход.',
                       u'Levels are copied in 3D first, then grids in plan. '
                       u'After a successful first session the next view opens. '
                       u'Cancellation or no new copies stops the sequence.'))

    def native_report(source_link, configured, errors):
        output.print_md(tr(u'Штатный мониторинг проверен, настроено и закреплено: {}.',
                           u'Native monitoring verified, configured and pinned: {}.').format(len(configured)))
        for error in errors:
            output.print_md(_cell(error))
        if configured:
            output.print_md(output.linkify(configured))
        updated_levels, updated_grids = link_datums.compare(doc, source_link, float(tolerance))
        report_levels(output, updated_levels)
        report_grids(output, updated_grids)

    output.print_md(tr(
        u'В штатном инструменте выберите связь «{}». «Копировать» и «Несколько» включатся автоматически. '
        u'Выделите перечисленные элементы рамкой, при необходимости используйте фильтр. Нажмите «Готово» в строке параметров и на ленте. '
        u'Выбор из списка не заменяет выбор на виде Revit.',
        u'In the native tool select link “{}”. Copy and Multiple will be enabled automatically. Select the listed elements with a rectangle, use the filter if needed, '
        u'then click Finish on the options bar and ribbon. List selection does not replace Revit view picks.').format(
            _cell(link_datums.link_label(link))))
    for kind, row, element_type, workset_id in choices:
        output.print_md(u'- {} [{}]'.format(_cell(row.link['name']), row.link['id_int']))
    first_view, first_choices = batches[0]
    link_datums_views.activate(revit.uidoc, first_view, link, first_choices)
    link_datums_native.start(revit.uidoc.Application, link, first_choices, float(tolerance),
                            native_report, pending=batches[1:])


try:
    main()
except SystemExit:
    raise
except Exception:
    forms.alert(tr(u"Сбой при сравнении:\n\n{}").format(traceback.format_exc()), title=TITLE)
