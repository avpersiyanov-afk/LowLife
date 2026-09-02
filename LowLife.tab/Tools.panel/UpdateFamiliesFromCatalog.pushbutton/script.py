# -*- coding: utf-8 -*-

__title__ = u"Семейства\nиз каталога"
__doc__ = u"Актуальность семейств выбранных категорий относительно папки-каталога .rfa и обновление отмеченных. Shift+клик — сменить папку каталога."
__author__ = "Pipers"

import io
import os
import tempfile
import traceback

import clr
clr.AddReference('RevitAPI')
clr.AddReference('RevitAPIUI')

from pyrevit import revit, forms, script, EXEC_PARAMS

doc = revit.doc

# --- Диагностика: пишем каждый шаг в файл, т.к. окно вывода pyRevit пустое ---
LOG_PATH = os.path.join(tempfile.gettempdir(), "lowlife_famcat_debug.txt")

try:
    with io.open(LOG_PATH, "w", encoding="utf-8") as _f:
        _f.write(u"=== Семейства из каталога ===\n")
except:
    pass


def step(msg):
    try:
        with io.open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(unicode(msg) + u"\n")
    except:
        pass
    try:
        script.get_output().print_md(unicode(msg))
    except:
        pass


try:
    step(u"1. импорт модуля family_catalog…")
    from lowlife import family_catalog as fc
    step(u"   ок")

    try:
        config_mode = bool(EXEC_PARAMS.config_mode)
    except Exception:
        config_mode = False
    step(u"   config_mode={}".format(config_mode))

    step(u"2. путь к каталогу…")
    root = fc.resolve_catalog_root(force_pick=config_mode)
    step(u"   root={}".format(root))
    if not root:
        step(u"   путь не задан — выход")
        forms.alert(u"Путь к каталогу не задан. Лог: {}".format(LOG_PATH))
        script.exit()

    step(u"3. сканирую каталог (может быть долго на сетевом диске)…")
    entries = fc.scan_catalog(root)
    step(u"   найдено .rfa: {}".format(len(entries)))
    if not entries:
        forms.alert(u"В каталоге нет .rfa:\n{}\nЛог: {}".format(root, LOG_PATH), exitscript=True)

    step(u"4. категории семейств проекта…")
    categories = fc.list_family_categories(doc)
    step(u"   категорий: {}".format(len(categories)))
    if not categories:
        forms.alert(u"В проекте нет загружаемых семейств.\nЛог: {}".format(LOG_PATH), exitscript=True)

    step(u"5. сейчас откроется окно выбора категорий")
    forms.alert(
        u"Дошли до выбора категорий (шаги 1–4 ок).\n"
        u".rfa в каталоге: {}\nкатегорий: {}\n\nЛог: {}".format(
            len(entries), len(categories), LOG_PATH
        ),
        title=u"Диагностика"
    )

    chosen = forms.SelectFromList.show(
        categories,
        title=u"Категории семейств (можно несколько)",
        button_name=u"Далее",
        multiselect=True
    )
    if not chosen:
        step(u"   выбор отменён")
        script.exit()

    cat_ids = [c.cat_id for c in chosen]
    families = fc.list_families_in_categories(doc, cat_ids)
    step(u"6. семейств в выбранных категориях: {}".format(len(families)))
    if not families:
        forms.alert(u"В выбранных категориях нет загружаемых семейств.", exitscript=True)

    step(u"7. сопоставление имён с каталогом…")
    rows = fc.build_matches(families, entries)
    step(u"   строк: {}".format(len(rows)))

    step(u"8. окно таблицы (show_status_form)…")
    picked = fc.show_status_form(rows, root, entries)
    step(u"   результат окна: {}".format(u"есть выбор" if picked else u"закрыто"))
    if not picked:
        script.exit()
    jobs, do_rename, overwrite_params = picked

    step(u"9. обновление {} семейств…".format(len(jobs)))
    result = fc.apply_updates(doc, jobs, do_rename, overwrite_params)
    step(u"   apply_updates завершён")
    fc.render_result_md(output=script.get_output(), result=result)

    summary = [u"Готово.", u""] + fc.result_summary_lines(result)
    summary += [u"", u"Лог: {}".format(LOG_PATH)]
    forms.alert(u"\n".join(summary), title=u"Семейства из каталога")

except Exception:
    tb = traceback.format_exc()
    step(u"ОШИБКА:\n" + tb)
    try:
        forms.alert(u"Сбой:\n\n{}\n\nЛог: {}".format(tb, LOG_PATH),
                    title=u"Семейства из каталога")
    except:
        pass
