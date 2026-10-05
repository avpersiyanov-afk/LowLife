# -*- coding: utf-8 -*-

__title__ = u"Обновить\nимя уровня"
__author__ = "Pipers"

import traceback

from pyrevit import revit, forms

from System.Collections.Generic import List
from Autodesk.Revit.DB import ElementId

doc = revit.doc
uidoc = revit.uidoc

TITLE = u"Обновить имя уровня"
AUTO_OPTION = u"По высоте — ближайший уровень не выше элемента"


def _pick_level():
    """None — по высоте; Level — для всех; выход из скрипта — отмена."""
    from lowlife import geometry

    levels = geometry.get_document_levels(doc)
    if not levels:
        forms.alert(u"В документе нет ни одного уровня.", title=TITLE, exitscript=True)

    by_name = {}
    options = [AUTO_OPTION]
    for lv in reversed(levels):
        name = geometry.level_name(lv)
        if name not in by_name:
            by_name[name] = lv
            options.append(name)

    choice = forms.SelectFromList.show(
        options, title=u"Какой опорный уровень назначить", button_name=u"Назначить"
    )
    if not choice:
        forms.alert(u"Отменено.", title=TITLE, exitscript=True)

    return None if choice == AUTO_OPTION else by_name[choice]


def _report(selected_count, skipped, result):
    lines = [u"Выбрано элементов: {}".format(selected_count)]

    assigned = len(result.by_param) + len(result.recreated)
    lines.append(u"Назначен опорный уровень: {}".format(assigned))
    if result.recreated:
        lines.append(
            u"  из них пересозданы (новый ID, цепи и параметры перенесены): {}".format(
                len(result.recreated)
            )
        )
    for name in sorted(result.levels):
        lines.append(u"  «{}»: {}".format(name, result.levels[name]))

    if skipped:
        lines.append(u"")
        lines.append(u"Пропущено:")
        for reason in sorted(skipped):
            lines.append(u"  {} — {}".format(reason, skipped[reason]))

    if result.failed:
        lines.append(u"")
        lines.append(u"Не удалось ({}):".format(len(result.failed)))
        for el_id, reason in result.failed[:15]:
            lines.append(u"  ID {} — {}".format(el_id, reason))
        if len(result.failed) > 15:
            lines.append(u"  … и ещё {}".format(len(result.failed) - 15))

    if result.warnings:
        lines.append(u"")
        lines.append(u"Проверьте:")
        for el_id, text in result.warnings[:15]:
            lines.append(u"  ID {} — {}".format(el_id, text))
        if len(result.warnings) > 15:
            lines.append(u"  … и ещё {}".format(len(result.warnings) - 15))

    forms.alert(u"\n".join(lines), title=TITLE)


def main():
    from lowlife import level_assign

    selected = [doc.GetElement(i) for i in uidoc.Selection.GetElementIds()]
    selected = [el for el in selected if el is not None]
    if not selected:
        forms.alert(
            u"Сначала выберите элементы в Revit, потом запустите кнопку.",
            title=TITLE, exitscript=True
        )

    targets = []
    skipped = {}
    for el in selected:
        reason = level_assign.classify(doc, el)
        if reason is None:
            targets.append(el)
        else:
            skipped[reason] = skipped.get(reason, 0) + 1

    if not targets:
        _report(len(selected), skipped, level_assign.AssignResult())
        return

    fixed_level = _pick_level()

    allow_recreate = True
    need_recreate = [el for el in targets if not level_assign.can_assign_by_param(el)]
    if need_recreate:
        answer = forms.alert(
            u"У {} из {} элементов Revit не даёт поменять параметр «Уровень» — "
            u"уровень назначится только пересозданием экземпляра на том же месте.\n\n"
            u"Тип, положение, поворот, параметры экземпляра, рабочий набор и "
            u"электрические цепи переносятся, но у нового элемента будет другой ID, "
            u"а марки старого элемента удалятся вместе с ним.".format(
                len(need_recreate), len(targets)
            ),
            title=TITLE,
            options=[u"Пересоздать", u"Только без пересоздания", u"Отмена"],
        )
        if not answer or answer == u"Отмена":
            return
        allow_recreate = answer == u"Пересоздать"

    with revit.Transaction(TITLE):
        result = level_assign.assign_levels(doc, targets, fixed_level, allow_recreate)

    ids = result.resulting_ids()
    if ids:
        try:
            uidoc.Selection.SetElementIds(List[ElementId](ids))
        except Exception:
            pass

    _report(len(selected), skipped, result)


try:
    main()
except SystemExit:
    pass
except Exception:
    forms.alert(
        u"Сбой в «{}»:\n\n{}".format(TITLE, traceback.format_exc()),
        title=TITLE
    )
