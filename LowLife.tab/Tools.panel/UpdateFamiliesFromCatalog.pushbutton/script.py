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

# Диагностика: каждый шаг пишем в файл (окно вывода pyRevit пустое).
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


step(u"0. скрипт стартовал")

try:
    step(u"1. импорт модуля family_catalog…")
    from lowlife import family_catalog as fc
    step(u"   ок")

    try:
        config_mode = bool(EXEC_PARAMS.config_mode)
    except Exception:
        config_mode = False
    step(u"   config_mode={}".format(config_mode))

    step(u"2. resolve_catalog_root…")
    root = fc.resolve_catalog_root(force_pick=config_mode)
    step(u"   root={}".format(root))
    if not root:
        forms.alert(u"Путь к каталогу не задан.\nЛог: {}".format(LOG_PATH), exitscript=True)

    step(u"3. scan_catalog (может быть долго на сетевом диске)…")
    entries = fc.scan_catalog(root)
    step(u"   .rfa найдено: {}".format(len(entries)))

    step(u"4. list_family_categories…")
    categories = fc.list_family_categories(doc)
    step(u"   категорий: {}".format(len(categories)))

    step(u"5. показываю forms.alert перед выбором категорий")
    forms.alert(
        u"Шаги 1–4 прошли.\n.rfa: {}\nкатегорий: {}\n\nЛог: {}".format(
            len(entries), len(categories), LOG_PATH
        ),
        title=u"Диагностика"
    )

    if not entries:
        script.exit()
    if not categories:
        script.exit()

    step(u"6. SelectFromList.show (категории)…")
    chosen = forms.SelectFromList.show(
        categories,
        title=u"Категории семейств (можно несколько)",
        button_name=u"Далее",
        multiselect=True
    )
    step(u"   выбрано: {}".format(len(chosen) if chosen else 0))
    if not chosen:
        script.exit()

    cat_ids = [c.cat_id for c in chosen]
    families = fc.list_families_in_categories(doc, cat_ids)
    step(u"7. семейств в категориях: {}".format(len(families)))
    if not families:
        forms.alert(u"В выбранных категориях нет загружаемых семейств.", exitscript=True)

    step(u"8. build_matches…")
    rows = fc.build_matches(families, entries)
    step(u"   строк: {}".format(len(rows)))

    step(u"9. show_status_form (окно-таблица)…")
    picked = fc.show_status_form(rows, root, entries)
    step(u"   окно вернуло: {}".format(u"выбор" if picked else u"None"))
    if not picked:
        script.exit()
    jobs, do_rename = picked

    step(u"10. apply_updates ({} семейств)…".format(len(jobs)))
    result = fc.apply_updates(doc, jobs, do_rename)
    step(u"    готово")

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
