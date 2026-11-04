# -*- coding: utf-8 -*-
"""Настроить виды связанных моделей сразу на нескольких основных видах."""
from pyrevit import forms, revit, script
from lowlife import link_views, link_views_dialog, select_list
from lowlife.i18n import tr

__title__ = u"Виды\nсвязей"
__doc__ = u"Выбрать основные виды одного типа и настроить виды связей отдельно для каждого."


def main():
    doc = revit.doc
    view = revit.active_view
    title = tr(u"Виды связанных моделей", u"Linked model views")
    if doc is None or view is None:
        forms.alert(tr(u"Откройте модель и вид.", u"Open a model and a view."), title=title)
        return
    try:
        views = select_list.select_views(
            title=tr(u"Выберите виды того же типа, что и текущий", u"Select views of the same type as the current view"),
            multiple=True, doc=doc,
            filterfunc=lambda v: not v.IsTemplate and v.ViewType == view.ViewType)
        if not views:
            return
        for host in views:
            problem = link_views.availability(doc, host)
            if problem:
                forms.alert(u"{}: {}".format(link_views.safe_name(host), problem), title=title)
                return
        rows = [link_views.collect_rows(doc, host) for host in views]
        if not any(rows):
            forms.alert(tr(u"В модели нет связей Revit.", u"The model has no Revit links."), title=title)
            return
        choices = link_views_dialog.show(views, rows)
        if choices is None:
            return
        count = link_views.apply_assignments(doc, choices)
        forms.alert(tr(u"Настроено видов: {}. Применено настроек связей: {}",
                       u"Views configured: {}. Link settings applied: {}").format(len(choices), count), title=title)
    except Exception as ex:
        script.get_logger().exception('Linked model view settings failed')
        forms.alert(tr(u"Не удалось настроить связи. Изменения не сохранены.\n{}",
                       u"Could not configure links. Changes were not saved.\n{}").format(ex), title=title)


main()
