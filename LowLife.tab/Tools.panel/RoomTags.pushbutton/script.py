# -*- coding: utf-8 -*-

__title__ = u"Марки\nпомещений"
__doc__ = (
    u"Расставляет и обновляет марки помещений из связанной модели на "
    u"активном плане. Типоразмер марки выбирается из списка (все "
    u"загруженные марки категории «Марки помещений»). Марки, ставшие "
    u"«???» после того как АР переделал помещение, пересоздаются на "
    u"месте. На время вставки временно снимается подложка вида — она "
    u"мешает Revit ставить марки помещений.\n\n"
    u"Shift+клик — выбрать несколько планов списком, обновить марки "
    u"сразу на всех."
)
__author__ = "Pipers"

from Autodesk.Revit.DB import ViewPlan
from pyrevit import revit, forms, EXEC_PARAMS

from lowlife import room_tags

doc = revit.doc


class _Named(object):
    def __init__(self, name):
        self.name = name

    def __str__(self):
        return self.name


class TagTypeOption(_Named):
    def __init__(self, symbol):
        _Named.__init__(self, room_tags.tag_type_label(symbol))
        self.symbol = symbol


class ViewOption(_Named):
    def __init__(self, view):
        _Named.__init__(self, room_tags.view_label(view))
        self.view = view


try:
    pick_views = bool(EXEC_PARAMS.config_mode)
except Exception:
    pick_views = False


if pick_views:
    plan_views = room_tags.get_taggable_plan_views(doc)
    if not plan_views:
        forms.alert(u"В проекте нет планов для простановки марок.", exitscript=True)

    picked = forms.SelectFromList.show(
        sorted([ViewOption(v) for v in plan_views], key=lambda o: o.name.lower()),
        title=u"Виды для обновления марок помещений (можно несколько)",
        button_name=u"Обновить и расставить",
        multiselect=True
    )
    if not picked:
        forms.alert(u"Отменено.", exitscript=True)
    target_views = [o.view for o in picked]
else:
    view = doc.ActiveView
    if view is None or not isinstance(view, ViewPlan):
        forms.alert(
            u"Откройте план этажа или потолочный план — либо нажмите "
            u"кнопку с Shift, чтобы выбрать несколько планов списком.",
            exitscript=True
        )
    if view.IsTemplate:
        forms.alert(u"Активен шаблон вида. Откройте настоящий план.", exitscript=True)
    target_views = [view]


tag_types = room_tags.get_room_tag_types(doc)
if not tag_types:
    forms.alert(
        u"В проекте нет ни одного типоразмера марки помещения. "
        u"Загрузите семейство марки помещения и повторите.",
        exitscript=True
    )

chosen = forms.SelectFromList.show(
    sorted([TagTypeOption(s) for s in tag_types], key=lambda o: o.name.lower()),
    title=u"Марка помещения",
    button_name=u"Обновить и расставить",
    multiselect=False
)
if not chosen:
    forms.alert(u"Отменено.", exitscript=True)


KEYS = ("added", "recreated", "retyped", "already",
        "orphan_unresolved", "out_of_view", "room_no_point")
totals = dict((k, 0) for k in KEYS)

with revit.Transaction(u"Марки помещений из связи"):
    for target in target_views:
        stats = room_tags.run(doc, target, chosen.symbol.Id)
        for k in KEYS:
            totals[k] += stats[k]

header = (
    u"Готово. Обработано планов: {}\n\n".format(len(target_views))
    if len(target_views) > 1 else u"Готово.\n\n"
)

forms.alert(
    header +
    u"Добавлено марок: {added}\n"
    u"Пересоздано «???»: {recreated}\n"
    u"Сменён типоразмер: {retyped}\n"
    u"Уже стояли: {already}\n"
    u"«???» без помещения рядом: {orphan_unresolved}\n"
    u"Помещений вне области вида: {out_of_view}\n"
    u"Помещений без точки размещения: {room_no_point}".format(**totals)
)
