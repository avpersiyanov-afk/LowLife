# -*- coding: utf-8 -*-
__title__ = u"Параметры\nв ФОП"
__doc__ = (
    u"Показывает список общих параметров, нужных кнопкам LowLife (СКС, СКУД, "
    u"СПС, СОУЭ, СПА, СОТ), с примером имени, типом данных и категориями. "
    u"Имена можно поменять под соглашение проекта; отмеченные параметры "
    u"создаются в файле общих параметров (ФОП) — если их там ещё нет — и "
    u"сразу привязываются к нужным категориям проекта. Введённые имена "
    u"вписываются в настройки кнопок."
)
__author__ = "Pipers"

from pyrevit import revit, forms, script

from lowlife import fop_catalog, fop_setup, fop_parameters_ui

doc = revit.doc
app = doc.Application
TITLE = fop_parameters_ui.TITLE

if doc.IsFamilyDocument:
    forms.alert(u"Кнопка работает в проекте, а не в редакторе семейств.",
                title=TITLE, exitscript=True)

choice = fop_parameters_ui.show_dialog(app)
if not choice:
    script.exit()

# --- файл ФОП ---
path = choice["sp_path"]
if choice["create_file"] and not fop_setup.create_file(path):
    forms.alert(u"Не удалось создать файл ФОП:\n{}".format(path), title=TITLE, exitscript=True)

if path == fop_setup.connected_path(app):
    _path, sp_file = fop_setup.connected_file(app)
else:
    sp_file = fop_setup.open_file(app, path)
if sp_file is None:
    forms.alert(u"Не удалось открыть файл ФОП:\n{}".format(path), title=TITLE, exitscript=True)

# --- определения и привязки ---
rows = [r for r in choice["rows"] if r.Checked]
report = fop_setup.add_and_bind(doc, app, sp_file, choice["group"], rows)

written = []
if choice["write_settings"]:
    updates = fop_catalog.settings_updates(rows, fop_parameters_ui.read_system_settings())
    written = fop_parameters_ui.write_system_settings(updates)

# --- отчёт ---
output = script.get_output()
output.print_md(u"## {}".format(TITLE))
output.print_md(u"Файл ФОП: `{}`".format(path))


def section(title, lines):
    if lines:
        output.print_md(u"### {} ({})".format(title, len(lines)))
        for line in lines:
            output.print_md(u"- {}".format(line))


section(u"Созданы в ФОП", report.created)
section(u"Уже были в ФОП или проекте", report.reused)
section(u"Добавлены привязки", report.bound)
section(u"Уже привязаны ко всем категориям", report.already)
section(u"Предупреждения", report.warnings)
section(u"Ошибки", report.errors)
if written:
    output.print_md(u"Имена вписаны в настройки: {}".format(u", ".join(written)))

forms.alert(
    u"Готово.\n\n"
    u"Создано в ФОП: {}\n"
    u"Добавлено привязок: {}\n"
    u"Уже привязаны: {}\n"
    u"Предупреждения: {}\n"
    u"Ошибки: {}\n\n"
    u"Подробности — в окне вывода pyRevit.".format(
        len(report.created), len(report.bound), len(report.already),
        len(report.warnings), len(report.errors)),
    title=TITLE,
)
