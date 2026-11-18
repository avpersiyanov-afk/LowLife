# -*- coding: utf-8 -*-
"""Настроить виды связанных моделей сразу на нескольких основных видах."""
from pyrevit import forms, revit, script
from lowlife import link_views, link_views_dialog
from lowlife.i18n import tr

__title__ = u"Выбрать виды\nдля связанных моделей"
__doc__ = u"Выбрать основные виды одного типа и настроить виды связей отдельно для каждого."


def main():
    doc = revit.doc
    view = revit.active_view
    title = tr(u"Виды связанных моделей", u"Linked model views")
    if doc is None or view is None:
        forms.alert(tr(u"Откройте модель и вид.", u"Open a model and a view."), title=title)
        return
    try:
        views = link_views.host_views(doc)
        rows = [link_views.collect_rows(doc, host)
                if host.ViewType == view.ViewType else [] for host in views]
        if not any(rows):
            forms.alert(tr(u"В модели нет связей Revit.", u"The model has no Revit links."), title=title)
            return
        choices = link_views_dialog.show(views, rows, active_view=view)
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
