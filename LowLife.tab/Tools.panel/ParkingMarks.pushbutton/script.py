# -*- coding: utf-8 -*-
__title__ = u"Отметки\nпарковки"
__doc__ = (
    u"Подписывает на плане отметки элементов категории «Парковка» из связей от "
    u"уровня плана и штрихует контуры: зоны светильников (низ и верх), проезда и "
    u"машиномест (верх). Повторный запуск заменяет подписи прошлого запуска.\n\n"
    u"Shift+клик — настройки этой кнопки."
)
__author__ = "Pipers"

from pyrevit import revit, forms, script, EXEC_PARAMS

from lowlife import parking_marks, parking_marks_settings, select_list

doc = revit.doc
TITLE = u"Отметки парковки"


try:
    config_mode = bool(EXEC_PARAMS.config_mode)
except Exception:
    config_mode = False

if config_mode:
    edited = parking_marks_settings.get_settings_interactive()
    forms.alert(u"Отменено, настройки не изменены." if edited is None else u"Настройки сохранены.")
    script.exit()


settings = parking_marks_settings.get_settings_silent()

if parking_marks.is_plan(doc.ActiveView):
    views = [doc.ActiveView]
else:
    views = select_list.select_views(title=u"Планы, на которых отметить парковку",
                                     filterfunc=parking_marks.is_plan, multiple=True)
    if not views:
        script.exit()

collected = [(view, parking_marks.collect(doc, view, settings)) for view in views]
if not any(found.links for _view, found in collected):
    forms.alert(u"В модели нет загруженных связей, видимых на плане.", title=TITLE, exitscript=True)

results = []
with revit.Transaction(TITLE):
    note_type = parking_marks.text_type(doc)
    for view, found in collected:
        results.append((found, parking_marks.annotate_view(doc, view, found.items, settings, note_type)))


output = script.get_output()
output.print_md(u"## " + TITLE)
lines = []
for found, result in results:
    output.print_md(u"### План «{}»".format(result.view.Name))
    output.print_md(u"- связи: " + (u", ".join(found.links) or u"—"))
    if found.unloaded:
        output.print_md(u"- **выгружены** (не проверены): " + u", ".join(found.unloaded))
    if found.hidden_links:
        output.print_md(u"- скрыты на плане (не проверены): " + u", ".join(found.hidden_links))
    if found.category_hidden:
        output.print_md(u"- **категория «Парковка» скрыта на плане** — подписи поставлены, "
                        u"но самих элементов не видно")
    counts = [u"{}: {}".format(group.name, result.counts[group.key])
              for group in parking_marks.core.GROUPS + [parking_marks.core.OTHER]
              if result.counts.get(group.key)]
    output.print_md(u"- найдено: " + (u", ".join(counts) or u"ничего"))
    output.print_md(u"- подписей: {}, заштриховано: {}".format(result.texts, result.fills))
    # пропущенные зоны (не машиноместа — их на других этажах сотни) — с отметками,
    # чтобы было видно, почему зона не попала на план
    names = dict((g.key, g.name) for g in parking_marks.core.GROUPS + [parking_marks.core.OTHER])
    skipped_zones = [s for s in found.skipped if s[0] != "parking"]
    if found.skipped:
        output.print_md(u"- пропущено элементов: {} (не на этом этаже или вне подрезки)".format(
            len(found.skipped)))
    if skipped_zones:
        rows = [[names.get(group, group), label,
                 parking_marks.core.format_height(bottom), parking_marks.core.format_height(top), reason]
                for group, label, bottom, top, reason in skipped_zones[:50]]
        output.print_table(rows, columns=[u"Группа", u"Элемент", u"Низ от уровня",
                                          u"Верх от уровня", u"Причина"])
    if found.no_geometry:
        output.print_md(u"- без геометрии и габарита: " + u", ".join(found.no_geometry))
    for error in result.errors:
        output.print_md(u"- ошибка: " + error)
    lines.append(u"«{}»: {}".format(result.view.Name, u", ".join(counts) or u"ничего не найдено"))

forms.alert(u"Готово.\n\n" + u"\n".join(lines) + u"\n\nПодробности — в окне вывода.", title=TITLE)
