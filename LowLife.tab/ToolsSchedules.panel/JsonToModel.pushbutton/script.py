# -*- coding: utf-8 -*-

__title__ = u"JSON\n→ модель"
__doc__ = (
    u"Загружает правки из снимка .json (кнопка «Модель → JSON») обратно в "
    u"модель: значения параметров (\"params\") и положение элементов "
    u"(\"location\" — перемещение, поворот, голова марки). Показывает список "
    u"«было → станет»; записываются только отмеченные правки, одной "
    u"транзакцией (Ctrl+Z отменяет всё сразу). То, что в файле не правили, "
    u"не пишется. Правка поверх изменения в модели после выгрузки помечена "
    u"⚠ и по умолчанию не отмечена."
)
__author__ = "Pipers"

import traceback

from pyrevit import revit, forms, script

from lowlife import json_snapshot

doc = revit.doc

MAX_LISTED = 20


def _tail(title, items, fmt):
    if not items:
        return []
    out = [u"", u"{} ({}):".format(title, len(items))]
    out.extend(fmt(x) for x in items[:MAX_LISTED])
    if len(items) > MAX_LISTED:
        out.append(u"… и ещё {}".format(len(items) - MAX_LISTED))
    return out


def _problems_text(plan):
    lines = []
    lines += _tail(u"Элемент не найден в модели", plan["no_element"],
                   lambda x: u"  {}".format(x))
    lines += _tail(u"Нет такого параметра у элемента", plan["no_param"],
                   lambda x: u"  ID {} / «{}»".format(*x))
    lines += _tail(u"Параметр только для чтения — пропущен", plan["read_only"],
                   lambda x: u"  ID {} / «{}»".format(*x))
    lines += _tail(u"Значение не записать", plan["bad_value"],
                   lambda x: u"  ID {} / «{}»: {}".format(*x))
    return lines


try:
    path = forms.pick_file(file_ext="json")
    if not path:
        script.exit()

    data, error = json_snapshot.read_snapshot(path)
    if error:
        forms.alert(error, exitscript=True)

    src_title = (data.get("document") or {}).get("title")
    if src_title and src_title != doc.Title:
        if not forms.alert(
            u"Снимок выгружен из другого документа:\n«{}»\n\nТекущий: «{}»\n\n"
            u"Элементы ищутся по UniqueId/Id — в другом файле они, скорее "
            u"всего, не найдутся или окажутся не теми. Продолжить?".format(
                src_title, doc.Title),
            yes=True, no=True
        ):
            script.exit()

    plan = json_snapshot.plan_changes(doc, data)
    changes = plan["changes"]

    if not changes:
        forms.alert(u"\n".join(
            [u"Нечего загружать: все значения совпадают с моделью "
             u"(совпало {}).".format(plan["unchanged"])]
            + _problems_text(plan)
        ))
        script.exit()

    n_conflicts = sum(1 for ch in changes if ch.conflict)
    items = [forms.TemplateListItem(ch, checked=not ch.conflict) for ch in changes]
    title = u"Правки для записи: {}".format(len(changes))
    if n_conflicts:
        title += u" (⚠ конфликтов: {} — не отмечены)".format(n_conflicts)
    chosen = forms.SelectFromList.show(
        items,
        title=title,
        button_name=u"Записать отмеченные",
        multiselect=True,
        width=1000,
        height=700,
    )
    if not chosen:
        script.exit()

    with revit.Transaction(u"Загрузка правок из JSON"):
        done, errors = json_snapshot.apply_changes(chosen)

    parts = [
        u"Готово.",
        u"",
        u"Записано значений: {}".format(done),
        u"Не выбрано в списке: {}".format(len(changes) - len(chosen)),
        u"Без изменений: {}".format(plan["unchanged"]),
    ]
    if plan["not_edited"]:
        parts.append(u"Не правили в файле, но изменили в модели — оставлено "
                     u"как в модели: {}".format(plan["not_edited"]))
    parts += _tail(u"Ошибки записи", errors, lambda x: u"  " + x)
    parts += _problems_text(plan)
    forms.alert(u"\n".join(parts))
except Exception:
    forms.alert(
        u"Сбой при загрузке:\n\n{}".format(traceback.format_exc()),
        title=u"JSON → модель"
    )
