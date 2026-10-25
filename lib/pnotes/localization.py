# -*- coding: utf-8 -*-
"""Display translations for the notes service; API values remain unchanged."""
from lowlife.i18n import tr, N_

_ERRORS = (
    N_(u'Некорректный запрос'),
    N_(u'Неверный токен. Сверьте его с меню таблицы «Заметки Revit → Показать токен».'),
    N_(u'Пустая заметка'),
    N_(u'Пустой текст заметки'),
    N_(u'Заметка не найдена в таблице — обновите сводку.'),
    N_(u'Вопрос нельзя закрыть без ответа.'),
    N_(u'Неизвестное действие'),
    N_(u'Пустое сообщение'),
    N_(u'Слишком много сообщений, попробуйте через минуту'),
)
_PREFIXES = (N_(u'Неизвестное действие: '), N_(u'Неизвестный статус: '))
_ANSWER_PREFIX = N_(u'Вопрос нельзя закрыть без ответа: заполните «Решение» (без ответа — ')
_ANSWER_SUFFIX = N_(u' шт.).')


def server_error(text):
    """Translate known server errors, retaining raw action/status values and unknown errors."""
    if text in _ERRORS:
        return tr(text)
    for prefix in _PREFIXES:
        if text.startswith(prefix):
            return tr(prefix) + text[len(prefix):]
    if text.startswith(_ANSWER_PREFIX) and text.endswith(_ANSWER_SUFFIX):
        count = text[len(_ANSWER_PREFIX):-len(_ANSWER_SUFFIX)]
        return tr(_ANSWER_PREFIX) + count + tr(_ANSWER_SUFFIX)
    return text
