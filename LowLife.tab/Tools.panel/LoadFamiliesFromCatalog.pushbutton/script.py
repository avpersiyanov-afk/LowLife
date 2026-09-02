# -*- coding: utf-8 -*-

__title__ = u"Загрузить\nсемейства"
__doc__ = u"Загружает семейства из папки-каталога .rfa в модель. Shift+клик — сменить папку каталога."
__author__ = "Pipers"

import os
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


class FolderOption(object):
    def __init__(self, rel):
        self.rel = rel
        self.name = rel if rel != u"." else u"(корень каталога)"

    def __str__(self):
        return self.name


try:
    log(u"### Загрузить семейства — запуск")

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

    folders = sorted(set(os.path.dirname(e.rel) or u"." for e in entries))
    if len(folders) > 1:
        log(u"4. окно выбора разделов ({} папок)…".format(len(folders)))
        chosen = forms.SelectFromList.show(
            [FolderOption(f) for f in folders],
            title=u"Разделы каталога — можно несколько (Отмена = все)",
            button_name=u"Далее",
            multiselect=True
        )
        if chosen:
            keep = set(o.rel for o in chosen)
            entries = [e for e in entries if (os.path.dirname(e.rel) or u".") in keep]

    if not entries:
        forms.alert(u"В выбранных разделах нет .rfa.", exitscript=True)

    log(u"5. имена семейств проекта…")
    present = fc.project_family_names(doc)
    log(u"   семейств в проекте: {}".format(len(present)))

    log(u"6. окно таблицы файлов (show_load_form)…")
    picked = fc.show_load_form(entries, present, root)
    if not picked:
        log(u"   окно закрыто")
        script.exit()
    load_entries, overwrite_params, choose_types = picked

    if choose_types:
        log(u"7. чтение типоразмеров у {} файлов…".format(len(load_entries)))
        app = doc.Application
        type_map = []
        passthru = []
        for e in load_entries:
            names = fc.read_family_type_names(app, e.path)
            if names:
                type_map.append((e, names))
            else:
                passthru.append(e)
        log(u"   с типами: {}, без: {}".format(len(type_map), len(passthru)))
        sel = fc.show_type_picker(type_map)
        if sel is None:
            log(u"   окно типов закрыто")
            script.exit()
        jobs = [(e, None) for e in passthru]
        for e, names in type_map:
            ch = sel.get(e)
            if not ch:
                continue
            jobs.append((e, None if set(ch) == set(names) else sorted(ch)))
    else:
        jobs = [(e, None) for e in load_entries]

    if not jobs:
        forms.alert(u"Нечего загружать.", exitscript=True)

    log(u"8. загрузка {} семейств…".format(len(jobs)))
    result = fc.apply_loads(doc, jobs, present, overwrite_params)
    fc.render_load_result_md(output, result)

    summary = [u"Готово.", u""] + fc.load_summary_lines(result)
    summary += [
        u"",
        u"Подробности — в окне вывода. Каждая загрузка — отдельный шаг отмены (Ctrl+Z).",
    ]
    forms.alert(u"\n".join(summary), title=u"Загрузить семейства")

except Exception:
    tb = traceback.format_exc()
    log(u"**ОШИБКА**\n```\n{}\n```".format(tb))
    try:
        forms.alert(u"Сбой при загрузке семейств:\n\n{}".format(tb),
                    title=u"Загрузить семейства")
    except:
        pass
