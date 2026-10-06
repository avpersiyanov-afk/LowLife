# -*- coding: utf-8 -*-

__title__ = u"Экспликация\nфрагмента"
__doc__ = (
    u"Экспликация помещений по обрезанному плану (фрагменту). Берёт "
    u"помещения модели и видимых связей, чья точка размещения попадает в "
    u"рамку подрезки активного плана, и создаёт ключевую спецификацию: "
    u"номер, наименование, площадь, категория — без настройки фильтров. "
    u"Повторный запуск на том же виде обновляет эту же спецификацию.\n\n"
    u"Shift+клик — настройки: заголовки и ширины столбцов (по умолчанию — "
    u"форма 2 ГОСТ 21.501), параметр категории, знаки площади."
)
__author__ = "Pipers"

import traceback

from pyrevit import revit, forms, script, EXEC_PARAMS

from lowlife import room_explication, room_explication_settings
from lowlife import room_explication_core as core

doc = revit.doc
uidoc = revit.uidoc
view = doc.ActiveView
TITLE = u"Экспликация фрагмента"

try:
    config_mode = bool(EXEC_PARAMS.config_mode)
except Exception:
    config_mode = False

if config_mode:
    edited = room_explication_settings.get_settings_interactive()
    forms.alert(u"Отменено, настройки не изменены." if edited is None
                else u"Настройки сохранены.", title=TITLE)
    script.exit()

settings = room_explication_settings.get_settings_silent()
category_param = (settings.get("category_param") or u"").strip()

reason = room_explication.unsupported_reason(view)
if reason:
    forms.alert(reason, title=TITLE, exitscript=True)

by_source, skipped = room_explication.collect_fragment_rooms(doc, view, category_param)
if not by_source:
    forms.alert(u"В рамке подрезки вида нет размещённых помещений "
                u"(ни в модели, ни в видимых связях).", title=TITLE, exitscript=True)

# Помещения есть и в модели, и в связи (или в нескольких связях) — спросить.
sources = sorted(by_source.keys())
if len(sources) > 1:
    options = [u"{} ({} пом.)".format(s, len(by_source[s])) for s in sources]
    all_option = u"Все источники"
    choice = forms.CommandSwitchWindow.show(
        options + [all_option],
        message=u"Помещения фрагмента найдены в нескольких моделях. Откуда брать?")
    if not choice:
        script.exit()
    if choice != all_option:
        sources = [sources[options.index(choice)]]

rooms = []
for s in sources:
    rooms.extend(by_source[s])
rows = core.build_rows(rooms, settings.get("area_decimals", 2))
columns = room_explication_settings.columns(settings)

try:
    with revit.Transaction(TITLE):
        schedule, created = room_explication.build_schedule(
            doc, __revit__.Application, view.Name, rows, columns)
except Exception:
    forms.alert(u"Не удалось построить экспликацию.\n\n" + traceback.format_exc(),
                title=TITLE, exitscript=True)

lines = [u"{} «{}»: {} пом.".format(
    u"Создана спецификация" if created else u"Обновлена спецификация",
    core.schedule_name(view.Name), len(rows))]
if skipped:
    lines.append(u"Пропущено неразмещённых/незамкнутых помещений (площадь 0): {}.".format(skipped))
if not category_param:
    lines.append(u"Графа «Категория» пустая: параметр категории не задан "
                 u"(Shift+клик по кнопке).")
lines.append(u"\nОткрыть спецификацию?")
if forms.alert(u"\n".join(lines), title=TITLE, yes=True, no=True):
    uidoc.ActiveView = schedule
