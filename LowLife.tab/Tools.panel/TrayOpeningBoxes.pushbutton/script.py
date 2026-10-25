# -*- coding: utf-8 -*-
__title__ = u"Боксы\nна лотки"
__doc__ = (
    u"Ставит бокс (семейство с «бокс» в имени, тип с «временный») на каждое "
    u"пересечение выбранных кабельных лотков со стенами и перекрытиями "
    u"(модели и связей). Размер — сечение лотка плюс 50 мм, глубина — по "
    u"толщине стены/перекрытия. Где бокс уже есть — новый не "
    u"создаётся, кнопка предупреждает.\n\n"
    u"Shift+клик — настройки."
)
__author__ = "Pipers"

import traceback
from lowlife.i18n import tr

from Autodesk.Revit.UI.Selection import ObjectType
from Autodesk.Revit.Exceptions import OperationCanceledException
from pyrevit import revit, forms, script, EXEC_PARAMS

from lowlife import select_list, tray_boxes, tray_boxes_settings, tray_tags

doc = revit.doc
uidoc = revit.uidoc
TITLE = tr(u"Боксы на лотки")


try:
    config_mode = bool(EXEC_PARAMS.config_mode)
except Exception:
    config_mode = False

if config_mode:
    edited = tray_boxes_settings.get_settings_interactive(doc)
    forms.alert(tr(u"Отменено, настройки не изменены.") if edited is None
                else tr(u"Настройки сохранены."), exitscript=True)

settings = tray_boxes_settings.get_settings_silent()


def pick_trays():
    picked = [doc.GetElement(i) for i in uidoc.Selection.GetElementIds()]
    trays = tray_tags.resolve_trays(doc, [e for e in picked if e is not None])
    if trays:
        return trays
    try:
        refs = uidoc.Selection.PickObjects(
            ObjectType.Element, tray_tags.TrayFilter(),
            tr(u"Выберите лотки (рамкой и/или кликами), Enter — готово"))
    except OperationCanceledException:
        forms.alert(tr(u"Выбор отменён."), exitscript=True)
    return tray_tags.resolve_trays(doc, [doc.GetElement(r) for r in refs])


def choose_symbol():
    options = tray_boxes.find_box_types(doc, settings)
    if not options:
        forms.alert(
            tr(u"В проекте нет загруженного типа бокса: семейство со словами «{}» "
            u"в имени и тип со словами «{}». Загрузите семейство или поправьте "
            u"слова в настройках (Shift+клик).").format(
                settings.get("box_family_words"), settings.get("box_type_words")),
            title=TITLE, exitscript=True)
    if len(options) == 1:
        return options[0][1]
    label = select_list.SelectFromList.show(
        [name for name, _symbol in options],
        title=tr(u"Боксы на лотки — какой тип ставить"),
        button_name=tr(u"Ставить"),
        multiselect=False,
    )
    if not label:
        forms.alert(tr(u"Отменено."), exitscript=True)
    return dict(options)[label]


trays = pick_trays()
if not trays:
    forms.alert(tr(u"Не выбрано ни одного лотка."), title=TITLE, exitscript=True)

if not tray_boxes.sources(doc, settings):
    forms.alert(tr(u"Связь «{}», выбранная в настройках как модель для поиска пересечений, "
                u"не загружена. Загрузите её или выберите другую модель (Shift+клик).").format(
                    settings.get("box_source_model")), title=TITLE, exitscript=True)

symbol = choose_symbol()
if not tray_boxes.placement_supported(symbol):
    forms.alert(tr(u"Семейство бокса должно быть без основы или на рабочей плоскости "
                u"(на основе грани/стены не поддерживается)."), title=TITLE, exitscript=True)


def choose_workset():
    u"""Рабочий набор для новых боксов (None — активный)."""
    if not doc.IsWorkshared or not settings.get("box_workset_words"):
        return None
    worksets = tray_boxes.find_box_worksets(doc, settings)
    if not worksets:
        forms.alert(tr(u"В модели нет рабочего набора со словами «{}» в имени. Создайте его "
                    u"или поправьте слова в настройках (Shift+клик).").format(
                        settings.get("box_workset_words")), title=TITLE, exitscript=True)
    if len(worksets) == 1:
        return worksets[0]
    name = select_list.SelectFromList.show(
        [w.Name for w in worksets],
        title=tr(u"Боксы на лотки — в какой рабочий набор"),
        button_name=tr(u"Выбрать"),
        multiselect=False,
    )
    if not name:
        forms.alert(tr(u"Отменено."), exitscript=True)
    return [w for w in worksets if w.Name == name][0]


workset = choose_workset()

try:
    with forms.ProgressBar(title=TITLE + tr(u": {value} из {max_value}"), cancellable=False) as bar:
        with revit.Transaction(TITLE):
            result = tray_boxes.run(doc, trays, symbol, settings,
                                    lambda i, n: bar.update_progress(i + 1, n), workset)
except Exception:
    forms.alert(tr(u"Сбой (транзакция отменена, изменения не сохранены):\n\n{}").format(
        traceback.format_exc()), title=TITLE, exitscript=True)


output = script.get_output()
output.print_md(u"## " + TITLE)
output.print_md(tr(u"- лотков: {}").format(len(trays)))
output.print_md(tr(u"- поставлено боксов: {}").format(len(result.created)))
if workset is not None:
    output.print_md(tr(u"- рабочий набор новых боксов: «{}»").format(workset.Name))
if result.existing:
    output.print_md(tr(u"- **бокс уже есть — новый не ставился**: {}").format(len(result.existing)))
if result.new_types:
    output.print_md(tr(u"- созданы типоразмеры: ") + u", ".join(result.new_types))
if result.missing_params:
    output.print_md(tr(u"- **нет параметров размера в семействе** (размер не задан): ") +
                    u", ".join(sorted(result.missing_params)))

rows = []
for state, entries in ((tr(u"новый"), result.created), (tr(u"уже был — не ставился"), result.existing)):
    for tray, crossing, inst in entries:
        rows.append([output.linkify(tray.Id), crossing.host_label(), output.linkify(inst.Id), state])
if rows:
    output.print_table(rows, columns=[tr(u"Лоток"), tr(u"Пересекает"), tr(u"Бокс"), u""])
if result.skipped:
    output.print_md(tr(u"### Пропущено"))
    for tray, crossing, reason in result.skipped:
        output.print_md(u"- {} × {}: {}".format(output.linkify(tray.Id), crossing.host_label(), reason))
if result.failed:
    output.print_md(tr(u"### Ошибки"))
    for tray, crossing, error in result.failed:
        where = crossing.host_label() if crossing is not None else u""
        output.print_md(u"- {} {}: {}".format(output.linkify(tray.Id), where, error))

lines = [tr(u"Поставлено боксов: {}").format(len(result.created))]
if result.existing:
    lines.append(tr(u"\nВНИМАНИЕ: на {} пересечениях бокс уже есть — новые там не "
                 u"создавались, стоящие боксы не изменены.\n").format(len(result.existing)))
if result.skipped:
    lines.append(tr(u"Пропущено пересечений: {}").format(len(result.skipped)))
if result.failed:
    lines.append(tr(u"Ошибок: {}").format(len(result.failed)))
if result.missing_params:
    lines.append(tr(u"Нет параметров: ") + u", ".join(sorted(result.missing_params)))
if not (result.created or result.existing or result.skipped or result.failed):
    lines.append(tr(u"Выбранные лотки не пересекают ни стен, ни перекрытий выбранной модели."))
forms.alert(u"\n".join(lines) + tr(u"\n\nПодробности — в окне вывода."), title=TITLE,
            warn_icon=bool(result.existing))
