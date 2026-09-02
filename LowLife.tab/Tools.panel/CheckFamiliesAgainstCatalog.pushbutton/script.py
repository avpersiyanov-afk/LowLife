# -*- coding: utf-8 -*-

__title__ = u"Актуальность\nсемейств"
__doc__ = u"Окно с таблицей: имя семейства, статус (зелёный/красный), даты в модели и каталоге. Сортировка по столбцам, выбор галочками — отмеченные можно тут же обновить. Shift+клик — сменить папку каталога."
__author__ = "Pipers"

import traceback

import clr
clr.AddReference('RevitAPI')
clr.AddReference('RevitAPIUI')

from pyrevit import revit, forms, script, EXEC_PARAMS

from lowlife import family_catalog as fc

doc = revit.doc
output = script.get_output()


try:
    try:
        config_mode = bool(EXEC_PARAMS.config_mode)
    except Exception:
        config_mode = False

    root = fc.resolve_catalog_root(force_pick=config_mode)
    if not root:
        script.exit()

    entries = fc.scan_catalog(root)
    if not entries:
        forms.alert(
            u"В каталоге не найдено ни одного .rfa:\n{}".format(root),
            exitscript=True
        )

    categories = fc.list_family_categories(doc)
    if not categories:
        forms.alert(u"В проекте нет загружаемых семейств.", exitscript=True)

    chosen = forms.SelectFromList.show(
        categories,
        title=u"Категория семейств для проверки",
        button_name=u"Проверить",
        multiselect=False
    )
    if not chosen:
        script.exit()

    families = fc.list_families_in_category(doc, chosen.cat_id)
    if not families:
        forms.alert(u"В выбранной категории нет загружаемых семейств.", exitscript=True)

    rows = fc.build_matches(families, entries)

    picked = fc.show_status_form(rows, root)
    if not picked:
        # окно закрыто без действий — просто посмотрели
        script.exit()

    jobs, do_rename = picked
    result = fc.apply_updates(doc, jobs, do_rename)
    fc.render_result_md(output, result)

    summary = [u"Готово.", u""] + fc.result_summary_lines(result)
    summary += [
        u"",
        u"Подробности — в окне вывода. Каждая перезагрузка — отдельный шаг отмены (Ctrl+Z).",
    ]
    forms.alert(u"\n".join(summary), title=u"Актуальность семейств")

except Exception:
    forms.alert(
        u"Сбой при проверке актуальности:\n\n{}".format(traceback.format_exc()),
        title=u"Актуальность семейств"
    )
