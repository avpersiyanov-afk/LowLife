# -*- coding: utf-8 -*-

__title__ = u"Обновить\nсемейства"
__doc__ = u"Обновляет семейства выбранной категории из папки-каталога .rfa: подбор по похожему имени + перезагрузка с заменой параметров. Shift+клик — сменить папку каталога."
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

    # Shift+клик (config_mode) или отсутствующий/битый путь — выбрать папку.
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
        title=u"Категория семейств для обновления",
        button_name=u"Далее",
        multiselect=False
    )
    if not chosen:
        script.exit()

    families = fc.list_families_in_category(doc, chosen.cat_id)
    if not families:
        forms.alert(u"В выбранной категории нет загружаемых семейств.", exitscript=True)

    rows = fc.build_matches(families, entries)

    picked = fc.show_preview_form(rows, entries, root)
    if not picked:
        script.exit()
    confirmed, do_rename = picked
    if not confirmed:
        script.exit()

    result = fc.apply_updates(doc, list(confirmed), do_rename)
    fc.render_result_md(output, result)

    summary = [u"Готово.", u""] + fc.result_summary_lines(result)
    summary += [
        u"",
        u"Подробности — в окне вывода. Каждая перезагрузка — отдельный шаг отмены (Ctrl+Z).",
    ]
    forms.alert(u"\n".join(summary), title=u"Обновить семейства")

except Exception:
    forms.alert(
        u"Сбой при обновлении семейств:\n\n{}".format(traceback.format_exc()),
        title=u"Обновить семейства"
    )
