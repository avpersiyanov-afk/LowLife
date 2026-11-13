# -*- coding: utf-8 -*-
"""Workset/link definition of the shared dockable visibility filter."""
from lowlife import datum_filter_panel as panel
from lowlife import model_filter_revit as api
from lowlife import model_filter_settings as cfg
from lowlife.i18n import N_

DEFINITION = panel.FilterDefinition(
    adapter=api, settings=cfg, mask_keys=cfg.MASK_KEYS,
    guid='37dad3d6-cbb0-4d41-9e6a-f723bd758358',
    state_key='LowLife.ModelFilter.Panel.v1', title=cfg.TITLE, manage=True, snapshot_caption=True,
    hint=N_(u'Видимость меняется только на виде. Закрытые наборы, незагруженные связи и наборы под управлением шаблона недоступны. Категории, шаблон и границы вида могут ограничивать видимость связей.'))


def install(uiapp):
    return panel.install(uiapp, DEFINITION)


def show(uiapp, settings=False):
    return panel.show(uiapp, settings, DEFINITION)
