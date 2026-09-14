# -*- coding: utf-8 -*-

__title__ = u"Найти\nпомещение"
__doc__ = (
    u"Показывает список помещений активного вида (из текущей модели и всех "
    u"подключённых связей — по уровню/границам вида), отсортированный по "
    u"номеру и сгруппированный по параметру из настроек (например «Тип "
    u"помещения»). Начните печатать номер или название — список "
    u"отфильтруется. Пункт вверху списка переключает на все помещения "
    u"проекта, если нужного нет на этом виде. Выбор + «Подсветить» "
    u"приближает активный вид к этому помещению; если оно относится к "
    u"другому уровню, подскажет, на какой план переключиться.\n\n"
    u"После подсветки список открывается снова — не нужно нажимать кнопку "
    u"заново, чтобы найти следующее помещение. Список собирается один раз "
    u"за сеанс Revit и держится в памяти (пункт «Обновить список» наверху — "
    u"если помещения в связи изменились).\n\n"
    u"Shift+клик — настройки (параметр группировки)."
)
__author__ = "Pipers"

from pyrevit import revit, forms, script, EXEC_PARAMS

from lowlife import room_finder, room_finder_settings

doc = revit.doc
uidoc = revit.uidoc


class RefreshOption(object):
    def __str__(self):
        return u"↻ Обновить список помещений"


class ToggleScopeOption(object):
    def __init__(self, show_all, all_count, view_count):
        self.target_show_all = not show_all
        if show_all:
            self.label = u"▤ Только помещения активного вида ({})".format(view_count)
        else:
            self.label = u"▤ Показать все помещения проекта ({})".format(all_count)

    def __str__(self):
        return self.label


class RoomOption(object):
    def __init__(self, record, group):
        self.record = record
        if group:
            self.label = u"[{}]  {} — {}".format(
                group, record.number or u"?", record.name or u"без имени"
            )
        else:
            self.label = u"{} — {}".format(
                record.number or u"?", record.name or u"без имени"
            )

    def __str__(self):
        return self.label


def build_options(records, type_param_name):
    rows = []
    for record in records:
        group = room_finder.type_value(record, type_param_name)
        rows.append((
            group.lower(),
            room_finder.natural_key(record.number),
            RoomOption(record, group)
        ))
    rows.sort(key=lambda row: (row[0], row[1]))

    options = [RefreshOption()]
    options.extend(row[2] for row in rows)
    return options


try:
    config_mode = bool(EXEC_PARAMS.config_mode)
except Exception:
    config_mode = False

if config_mode:
    edited = room_finder_settings.get_settings_interactive()
    forms.alert(
        u"Отменено, настройки не изменены." if edited is None
        else u"Настройки сохранены."
    )
    script.exit()


settings = room_finder_settings.get_settings_silent()
type_param_name = settings.get("room_type_param_name", u"")

view = doc.ActiveView
if view is None:
    forms.alert(u"Нет активного вида.", exitscript=True)

records = room_finder.get_records(doc)
if not records:
    forms.alert(
        u"Помещений не найдено — ни в текущей модели, ни в подключённых "
        u"связях. Убедитесь, что связь с АР загружена и в ней расставлены "
        u"помещения.",
        exitscript=True
    )

view_records, narrowed = room_finder.filter_for_view(records, doc, view)
show_all = False

while True:
    current = records if (show_all or not narrowed) else view_records

    options = build_options(current, type_param_name)
    if narrowed:
        options.insert(0, ToggleScopeOption(show_all, len(records), len(view_records)))

    picked = forms.SelectFromList.show(
        options,
        title=u"Найти помещение — {} ({})".format(
            u"весь проект" if (show_all or not narrowed) else u"активный вид",
            len(current)
        ),
        button_name=u"Подсветить",
        multiselect=False
    )

    if not picked:
        break

    if isinstance(picked, RefreshOption):
        records = room_finder.get_records(doc, force_refresh=True)
        if not records:
            forms.alert(
                u"Помещений не найдено — ни в текущей модели, ни в "
                u"подключённых связях.",
                title=u"Найти помещение"
            )
            break
        view_records, narrowed = room_finder.filter_for_view(records, doc, view)
        continue

    if isinstance(picked, ToggleScopeOption):
        show_all = picked.target_show_all
        continue

    record = picked.record

    hint = room_finder.level_mismatch_hint(record, view)
    if hint:
        forms.alert(hint, title=u"Найти помещение")
        continue

    if not room_finder.zoom_to_bbox(uidoc, view, record.bbox):
        forms.alert(
            u"Не удалось приблизить вид к помещению {} — возможно, вид "
            u"открыт не в отдельном окне (например, на листе), либо у "
            u"помещения нет корректного габарита.".format(record.number or u"?"),
            title=u"Найти помещение"
        )
