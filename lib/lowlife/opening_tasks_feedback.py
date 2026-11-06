# -*- coding: utf-8 -*-
"""Read-only feedback from recipient models, independent of Revit."""
from lowlife import opening_tasks_core as core
from lowlife.i18n import tr


def evaluate(task, receipt=None, available=True, exists=True, matches=True):
    """Never treat an unloaded link as a deleted opening or an approval."""
    if not available:
        return 'unavailable'
    if not receipt:
        return 'withdraw_pending' if task['status']=='withdrawn' else 'pending'
    current=receipt.get('revisions',{}).get(core.task_key(task))==task['revision']
    if task['status']=='withdrawn':
        return 'withdrawn' if current and receipt.get('status')=='withdrawn' else 'withdraw_pending'
    if receipt.get('status')=='accepted':
        if not exists:
            return 'missing'
        if not matches:
            return 'modified'
    if not current:
        return 'outdated'
    return 'accepted' if receipt.get('status')=='accepted' else 'rejected' if receipt.get('status')=='rejected' else 'pending'


def describe(state):
    labels={
        'unavailable':(tr(u'Модель получателя недоступна',u'Recipient model unavailable'),tr(u'Загрузить связь нужной модели',u'Load the recipient model link')),
        'pending':(tr(u'Ожидает рассмотрения',u'Awaiting review'),tr(u'Получателю: обновить связь ВИС и рассмотреть',u'Recipient: reload VIS link and review')),
        'accepted':(tr(u'Принята актуальная ревизия',u'Current revision accepted'),tr(u'ВИС: проверить результат и подтвердить',u'VIS: review and confirm the result')),
        'rejected':(tr(u'Есть замечание получателя',u'Recipient comment'),tr(u'ВИС: исправить бокс и перевыдать задание',u'VIS: correct the draft and reissue')),
        'outdated':(tr(u'Ответ на предыдущую ревизию',u'Reply to an earlier revision'),tr(u'Получателю: обновить связь ВИС и принять новую ревизию',u'Recipient: reload VIS link and accept the new revision')),
        'missing':(tr(u'Проём удалён у получателя',u'Opening deleted by recipient'),tr(u'Получателю: восстановить проём или согласовать отзыв',u'Recipient: restore the opening or agree withdrawal')),
        'modified':(tr(u'Проём изменён у получателя',u'Opening modified by recipient'),tr(u'Согласовать изменения с получателем',u'Agree changes with the recipient')),
        'withdraw_pending':(tr(u'Отзыв не отработан',u'Withdrawal pending'),tr(u'Получателю: обновить связь ВИС и отработать отзыв',u'Recipient: reload VIS link and process withdrawal')),
        'withdrawn':(tr(u'Отзыв отработан',u'Withdrawal processed'),tr(u'Действий не требуется',u'No action required')),
    }
    return labels[state]
