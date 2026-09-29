# -*- coding: utf-8 -*-

__title__ = u"Модель\n→ JSON"
__doc__ = (
    u"Выгружает снимок модели в файл .json: элементы с их параметрами, "
    u"уровнем, при желании — цепями и координатами. Файл можно отдать на "
    u"анализ (например Claude), поправить значения в \"params\" и загрузить "
    u"обратно кнопкой «JSON → модель» — с предпросмотром перед записью.\n\n"
    u"Shift+клик — настройки: какие элементы (активный вид / выделение / "
    u"весь документ), каких категорий, какие параметры и что добавить."
)
__author__ = "Pipers"

import traceback

from pyrevit import revit, forms, script, EXEC_PARAMS

from lowlife import json_snapshot, json_snapshot_settings

doc = revit.doc
uidoc = revit.uidoc


try:
    config_mode = bool(EXEC_PARAMS.config_mode)
except Exception:
    config_mode = False

if config_mode:
    edited = json_snapshot_settings.get_settings_interactive(doc)
    forms.alert(
        u"Отменено, настройки не изменены." if edited is None
        else u"Настройки сохранены."
    )
    script.exit()


try:
    settings = json_snapshot_settings.get_settings_silent()
    options = json_snapshot_settings.to_options(settings)

    elements, error = json_snapshot.collect_elements(doc, uidoc, options)
    if error:
        forms.alert(error, exitscript=True)
    if options.get("include_circuits"):
        elements = json_snapshot.add_circuits(doc, elements)
    if not elements:
        forms.alert(
            u"Нечего выгружать: под настройки не попал ни один элемент.\n\n"
            u"Проверьте область и категории (Shift+клик по кнопке).",
            exitscript=True
        )

    path = forms.save_file(
        file_ext="json",
        default_name=u"{}_снимок".format(doc.Title),
    )
    if not path:
        script.exit()

    snapshot = json_snapshot.build_snapshot(doc, elements, options)
    json_snapshot.write_snapshot(path, snapshot)

    n_params = sum(len(r["params"]) for r in snapshot["elements"])
    forms.alert(
        u"Готово.\n\nЭлементов: {}\nЗначений для правки (\"params\"): {}\n\n{}\n\n"
        u"Правьте значения в \"params\" и загружайте кнопкой «JSON → модель». "
        u"Правила формата записаны в самом файле (\"readme\").".format(
            len(snapshot["elements"]), n_params, path
        )
    )
except Exception:
    forms.alert(
        u"Сбой при выгрузке:\n\n{}".format(traceback.format_exc()),
        title=u"Модель → JSON"
    )
