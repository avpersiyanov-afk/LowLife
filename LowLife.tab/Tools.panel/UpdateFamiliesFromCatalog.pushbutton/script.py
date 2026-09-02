# -*- coding: utf-8 -*-

__title__ = u"Семейства\nиз каталога"
__doc__ = u"Актуальность семейств выбранных категорий относительно папки-каталога .rfa и обновление отмеченных. Shift+клик — сменить папку каталога."
__author__ = "Pipers"

import traceback

import clr
clr.AddReference('RevitAPI')
clr.AddReference('RevitAPIUI')

from pyrevit import revit, forms, script, EXEC_PARAMS

doc = revit.doc
output = script.get_output()


def log(msg):
    try:
        output.print_md(msg)
    except:
        pass


try:
    log(u"### Семейства из каталога — запуск")

    log(u"1. импорт модуля family_catalog…")
    from lowlife import family_catalog as fc
    log(u"   ок")

    try:
        config_mode = bool(EXEC_PARAMS.config_mode)
    except Exception:
        config_mode = False

    log(u"2. путь к каталогу…")
    root = fc.resolve_catalog_root(force_pick=config_mode)
    if not root:
        log(u"   путь не задан — выход")
        script.exit()
    log(u"   каталог: `{}`".format(root))

    log(u"3. сканирую каталог (на сетевом диске может быть долго)…")
    entries = fc.scan_catalog(root)
    log(u"   найдено .rfa: {}".format(len(entries)))
    if not entries:
        forms.alert(u"В каталоге не найдено ни одного .rfa:\n{}".format(root), exitscript=True)

    log(u"4. категории семейств проекта…")
    categories = fc.list_family_categories(doc)
    log(u"   категорий: {}".format(len(categories)))
    if not categories:
        forms.alert(u"В проекте нет загружаемых семейств.", exitscript=True)

    log(u"5. окно выбора категорий…")
    chosen = forms.SelectFromList.show(
        categories,
        title=u"Категории семейств (можно несколько)",
        button_name=u"Далее",
        multiselect=True
    )
    if not chosen:
        log(u"   отменено")
        script.exit()

    cat_ids = [c.cat_id for c in chosen]
    families = fc.list_families_in_categories(doc, cat_ids)
    log(u"6. семейств в выбранных категориях: {}".format(len(families)))
    if not families:
        forms.alert(u"В выбранных категориях нет загружаемых семейств.", exitscript=True)

    log(u"7. сопоставление имён с каталогом…")
    rows = fc.build_matches(families, entries)

    log(u"8. окно таблицы (show_status_form)…")
    picked = fc.show_status_form(rows, root, entries)
    if not picked:
        log(u"   окно закрыто")
        script.exit()
    jobs, do_rename, overwrite_params = picked

    log(u"9. обновление {} семейств…".format(len(jobs)))
    result = fc.apply_updates(doc, jobs, do_rename, overwrite_params)
    fc.render_result_md(output, result)

    summary = [u"Готово.", u""] + fc.result_summary_lines(result)
    summary += [
        u"",
        u"Подробности — в окне вывода. Каждая перезагрузка — отдельный шаг отмены (Ctrl+Z).",
    ]
    forms.alert(u"\n".join(summary), title=u"Семейства из каталога")

except Exception:
    tb = traceback.format_exc()
    log(u"**ОШИБКА**\n```\n{}\n```".format(tb))
    try:
        forms.alert(u"Сбой при обновлении семейств:\n\n{}".format(tb),
                    title=u"Семейства из каталога")
    except:
        pass
