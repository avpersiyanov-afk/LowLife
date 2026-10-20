# -*- coding: utf-8 -*-
__title__ = u"Отметки\nпарковки"
__doc__ = (
    u"Отмечает на плане элементы категории «Парковка» из связей: у машиноместа — "
    u"отметку верха, у зоны (в «Комментариях» есть слово «зона») — верх и низ и "
    u"штриховку по контуру. Повторный запуск заменяет отметки прошлого запуска.\n\n"
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
zone_words = parking_marks.core.split_words(settings.get("zone_words"))

if parking_marks.is_plan(doc.ActiveView):
    views = [doc.ActiveView]
else:
    views = select_list.select_views(title=u"Планы, на которых отметить парковку",
                                     filterfunc=parking_marks.is_plan, multiple=True)
    if not views:
        script.exit()

collected = []
for view in views:
    collected.append((view, parking_marks.collect(doc, view, zone_words)))
if not any(found.links for _view, found in collected):
    forms.alert(u"В модели нет загруженных связей, видимых на плане.", title=TITLE, exitscript=True)

results = []
with revit.Transaction(TITLE):
    note_type = parking_marks.text_type(doc)
    spot = parking_marks.spot_type(doc)
    zone_fill, zone_fill_error = None, None
    if any(item.zone for _view, found in collected for item in found.items):
        zone_fill, zone_fill_error = parking_marks.fill_type(doc, settings.get("zone_fill_type_name"))
    for view, found in collected:
        results.append((found, parking_marks.annotate_view(
            doc, view, found.items, settings, note_type, spot, zone_fill, zone_fill_error)))


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
        output.print_md(u"- **категория «Парковка» скрыта на плане** — отметки поставлены, "
                        u"но самих элементов не видно")
    output.print_md(u"- машиномест: {}, зон: {} (заштриховано {})".format(
        result.parking, result.zones, result.fills))
    output.print_md(u"- высотных отметок: {}, текстов: {}".format(result.spots, result.texts))
    if found.out_of_range or found.out_of_crop:
        output.print_md(u"- пропущено: вне секущего диапазона {}, вне подрезки {}".format(
            found.out_of_range, found.out_of_crop))
    if found.no_geometry:
        output.print_md(u"- без геометрии и габарита: " + u", ".join(found.no_geometry))
    if result.no_prefix:
        output.print_md(u"- Revit не дал задать текст высотным отметкам (префикс/суффикс) — "
                        u"верх и низ зоны отличаются только положением")
    if result.spot_errors:
        output.print_md(u"- вместо высотной отметки — текст ({}):".format(len(result.spot_errors)))
        for label, reason in result.spot_errors[:30]:
            output.print_md(u"    - {} — {}".format(label, reason))
    for error in result.errors:
        output.print_md(u"- ошибка: " + error)
    lines.append(u"«{}»: машиномест {}, зон {}".format(result.view.Name, result.parking, result.zones))

forms.alert(u"Готово.\n\n" + u"\n".join(lines) + u"\n\nПодробности — в окне вывода.", title=TITLE)
