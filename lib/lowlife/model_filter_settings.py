# -*- coding: utf-8 -*-
"""Name masks for host worksets and Revit link instances."""
from lowlife import settings_core
from lowlife.datum_filter_settings import MaskField, HINT
from lowlife.i18n import N_

MASK_KEYS = ('workset_mask', 'link_mask')
TITLE = N_(u'Фильтр наборов и связей')

SETTINGS = settings_core.TextSettings(
    file_name='LowLifeModelFilter_settings.json',
    button_name=TITLE,
    heading=N_(u'Группировка рабочих наборов и связей по имени'),
    transfer_label=N_(u'фильтра наборов и связей'),
    fields=[
        MaskField('workset_mask', N_(u'Рабочие наборы'), N_(u'Маска имени рабочего набора'),
                  hint=HINT, default=u'*', required=False),
        MaskField('link_mask', N_(u'Связанные модели'), N_(u'Маска имени экземпляра связи'),
                  hint=HINT, default=u'*', required=False),
    ], width=740, height=530)
