# -*- coding: utf-8 -*-

__title__ = u"Экспликация\nфрагмента"
__doc__ = (
    u"Экспликация помещений по обрезанному плану (фрагменту). Берёт "
    u"помещения модели и видимых связей, чья точка размещения попадает в "
    u"рамку подрезки активного плана, и создаёт спецификацию-таблицу: "
    u"номер, наименование, площадь, категория. Таблица свободная — без "
    u"параметров в модели и без фильтров. Если у плана экспликация уже "
    u"есть — она обновляется (то же делает кнопка «Обновить экспликацию»).\n\n"
    u"Shift+клик — настройки: название, заголовки и ширины граф, высота "
    u"строк (по умолчанию — форма 2 ГОСТ 21.501: 15/80/20/10 мм, шапка 20, "
    u"строка 8), параметры номера/имени/площади/категории помещения, "
    u"знаки площади."
)
__author__ = "Pipers"

import traceback

from pyrevit import revit, forms, script, EXEC_PARAMS

from lowlife import room_explication as rexp
from lowlife import room_explication_settings

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

reason = rexp.unsupported_reason(view)
if reason:
    forms.alert(reason, title=TITLE, exitscript=True)

# Уборка за первой версией кнопки (ключевая спецификация + параметры).
legacy_schedules, legacy_params = rexp.find_legacy(doc)
if legacy_schedules or legacy_params:
    if forms.alert(
            u"В проекте осталось от прежней версии кнопки: ключевых "
            u"спецификаций — {}, параметров LL_Экспликация_* — {}. Теперь "
            u"экспликация делается без параметров.\n\nУдалить их?".format(
                len(legacy_schedules), len(legacy_params)),
            title=TITLE, yes=True, no=True):
        with revit.Transaction(u"Удалить старую экспликацию"):
            rexp.delete_legacy(doc, legacy_schedules, legacy_params)

existing = rexp.explications_of_view(doc, view)
if existing:
    schedule, _view, sources = existing[0]
else:
    schedule = None
    by_source, skipped, stats = rexp.collect_fragment_rooms(
        doc, view, room_explication_settings.room_params(settings))
    if not by_source:
        details = u"\n".join(st.text() for st in stats)
        if skipped:
            details += u"\nНеразмещённых/незамкнутых (площадь 0): {}".format(skipped)
        forms.alert(u"Во фрагменте не найдено ни одного помещения.\n\n" + details +
                    u"\n\nЕсли помещения в рамке есть, пришлите этот текст "
                    u"разработчику.", title=TITLE, exitscript=True)
    sources = []
    labels = sorted(by_source.keys())
    if len(labels) > 1:
        options = [u"{} ({} пом.)".format(s, len(by_source[s])) for s in labels]
        all_option = u"Все источники"
        choice = forms.CommandSwitchWindow.show(
            options + [all_option],
            message=u"Помещения фрагмента найдены в нескольких моделях. Откуда брать?")
        if not choice:
            script.exit()
        if choice != all_option:
            sources = [labels[options.index(choice)]]

try:
    with revit.Transaction(TITLE):
        schedule, count, skipped = rexp.rebuild(doc, view, sources, settings, schedule)
except Exception:
    forms.alert(u"Не удалось построить экспликацию.\n\n" + traceback.format_exc(),
                title=TITLE, exitscript=True)

lines = [u"{} «{}»: {} пом.".format(
    u"Обновлена экспликация" if existing else u"Создана экспликация",
    rexp.element_name(schedule), count)]
if skipped:
    lines.append(u"Пропущено неразмещённых/незамкнутых помещений (площадь 0): {}.".format(skipped))
if not (settings.get("category_param") or u"").strip():
    lines.append(u"Графа «Категория» пустая: параметр категории не задан "
                 u"(Shift+клик по кнопке).")
lines.append(u"\nОткрыть спецификацию?")
if forms.alert(u"\n".join(lines), title=TITLE, yes=True, no=True):
    uidoc.ActiveView = schedule
