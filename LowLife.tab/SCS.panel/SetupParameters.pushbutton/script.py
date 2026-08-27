# -*- coding: utf-8 -*-
__title__ = "Параметры\nСКС"
__doc__ = (
    "Проверяет, что все параметры СКС привязаны в проекте к нужным "
    "категориям, и добавляет недостающие привязки из подключённого файла "
    "общих параметров (ФОП). Если определения параметра нет ни в проекте, "
    "ни в файле ФОП — ничего не выдумывает, только сообщает об этом."
)
__author__ = "Pipers"

import clr

clr.AddReference('RevitAPI')
clr.AddReference('RevitAPIUI')

from Autodesk.Revit.DB import *
from pyrevit import revit, forms

from lowlife import scs_settings
from lowlife.scs_settings import get_settings_interactive
from lowlife.scs_parameters import (
    PARAM_SPECS, ensure_binding, find_existing_binding, get_category,
    binding_has_category, FOP, NATIVE
)

doc = revit.doc
app = doc.Application


# ------------------------------------------------------------
# НАСТРОЙКИ
# ------------------------------------------------------------

settings = get_settings_interactive(doc)

if settings is None:
    forms.alert(u"Операция отменена.", exitscript=True)

scs_settings.require(settings, [key for key, _, _, _, _, _, source, required in PARAM_SPECS if required])


# ------------------------------------------------------------
# ФАЙЛ ФОП
# ------------------------------------------------------------

sp_path = None
try:
    sp_path = app.SharedParametersFilename
except:
    pass

if not sp_path:
    forms.alert(
        u"К Revit не подключён файл общих параметров (ФОП).\n\n"
        u"Управление → Общие параметры → укажите файл, затем запустите кнопку заново.",
        exitscript=True
    )

sp_file = None
try:
    sp_file = app.OpenSharedParameterFile()
except:
    pass

if sp_file is None:
    forms.alert(u"Не удалось открыть файл ФОП:\n{}".format(sp_path), exitscript=True)


# ------------------------------------------------------------
# ПРОВЕРКА/ПРИВЯЗКА
# ------------------------------------------------------------

def split_names(value, is_list):
    if is_list:
        return [v for v in value if v]
    return [value] if value else []


already_ok = []
added = []
missing_definition = []
native_skipped = []
errors = []

with revit.Transaction("Setup SCS Parameters"):

    for key, label, is_list, categories, binding_kind, data_type, source, required in PARAM_SPECS:
        raw_value = settings.get(key)
        names = split_names(raw_value, is_list)

        if not names:
            continue

        if source == NATIVE:
            native_skipped.append(u"{} ({})".format(label, u", ".join(names)))
            continue

        if not is_list:
            name = names[0]
            result = ensure_binding(doc, app, sp_file, name, categories, binding_kind)

            if result["missing_definition"]:
                missing_definition.append(u"{} — «{}»".format(label, name))
            elif result["error"]:
                errors.append(u"{} — «{}»: {}".format(label, name, result["error"]))
            elif result["already_ok"]:
                already_ok.append(label)
            else:
                added.append(u"{} — «{}» -> {}".format(label, name, u", ".join(result["added_categories"])))

        else:
            # Список альтернативных имён (любое одно достаточно) —
            # необязательный параметр, поэтому отсутствие определения
            # в ФОП для ВСЕХ вариантов не блокирует, а просто отмечается.
            any_ok = False
            any_added = None
            any_error = None

            for name in names:
                _, existing_binding = find_existing_binding(doc, name)

                fully_bound = existing_binding is not None and all(
                    binding_has_category(existing_binding, get_category(doc, c))
                    for c in categories
                )

                if fully_bound:
                    any_ok = True
                    break

            if not any_ok:
                for name in names:
                    result = ensure_binding(doc, app, sp_file, name, categories, binding_kind)

                    if result["missing_definition"]:
                        continue

                    if result["error"]:
                        any_error = u"{} — «{}»: {}".format(label, name, result["error"])
                        break

                    if result["already_ok"]:
                        any_ok = True
                        break

                    any_added = u"{} — «{}» -> {}".format(label, name, u", ".join(result["added_categories"]))
                    any_ok = True
                    break

            if any_error:
                errors.append(any_error)
            elif any_added:
                added.append(any_added)
            elif any_ok:
                already_ok.append(label)
            else:
                native_skipped.append(
                    u"{} (необязательный, ни один из вариантов «{}» не найден в ФОП)".format(
                        label, u", ".join(names)
                    )
                )


# ------------------------------------------------------------
# ОТЧЁТ
# ------------------------------------------------------------

from pyrevit import script as pyrevit_script
output = pyrevit_script.get_output()

output.print_md(u"## Параметры СКС")

if already_ok:
    output.print_md(u"### Уже привязаны ({})".format(len(already_ok)))
    for line in already_ok:
        output.print_md(u"- {}".format(line))

if added:
    output.print_md(u"### Добавлены привязки ({})".format(len(added)))
    for line in added:
        output.print_md(u"- {}".format(line))

if native_skipped:
    output.print_md(u"### Пропущены (нативные/необязательные) ({})".format(len(native_skipped)))
    for line in native_skipped:
        output.print_md(u"- {}".format(line))

if errors:
    output.print_md(u"### Ошибки привязки ({})".format(len(errors)))
    for line in errors:
        output.print_md(u"- {}".format(line))

if missing_definition:
    output.print_md(u"### Нет определения ни в проекте, ни в ФОП ({})".format(len(missing_definition)))
    for line in missing_definition:
        output.print_md(u"- {}".format(line))

forms.alert(
    u"Готово.\n\n"
    u"Уже привязано: {}\n"
    u"Добавлено привязок: {}\n"
    u"Пропущено (нативные/необязательные): {}\n"
    u"Ошибки: {}\n"
    u"Нет определения ни в проекте, ни в ФОП: {}\n\n"
    u"{}".format(
        len(already_ok),
        len(added),
        len(native_skipped),
        len(errors),
        len(missing_definition),
        u"Подробности — в окне вывода pyRevit." if (added or errors or missing_definition or native_skipped) else u""
    )
)

if missing_definition:
    forms.alert(
        u"Добавьте эти параметры в файл ФОП (или создайте с такими же именами "
        u"в другом ФОП), затем запустите кнопку ещё раз:\n\n{}".format(
            u"\n".join(missing_definition)
        )
    )
