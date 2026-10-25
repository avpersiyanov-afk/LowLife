# -*- coding: utf-8 -*-
"""XAML captions must translate without changing WPF bindings or notes API values."""
import io
import os
import xml.etree.ElementTree as ET

from lowlife import i18n, xaml_i18n
from pnotes import localization


def test_captions_translate_but_bindings_and_trigger_values_do_not(monkeypatch):
    source = (u'<Window Title="Сводка по проекту"><TextBlock Text="{Binding text}"/>'
              u'<DataTrigger Binding="{Binding status}" Value="Не отправлено"/>'
              u'<Button Content="Сохранить"/><Hyperlink>Открыть таблицу</Hyperlink></Window>')
    monkeypatch.setattr(i18n, 'current', lambda: i18n.EN)
    translated = xaml_i18n.translate(source)
    root = ET.fromstring(translated)
    assert root.get('Title') == u'Project summary'
    assert root.find('Button').get('Content') == u'Save'
    assert root.find('Hyperlink').text == u'Open sheet'
    assert root.find('TextBlock').get('Text') == u'{Binding text}'
    assert root.find('DataTrigger').get('Value') == u'Не отправлено'
    monkeypatch.setattr(i18n, 'current', lambda: i18n.RU)
    assert xaml_i18n.translate(source) == source


def test_escaped_captions_remain_valid_xml(monkeypatch):
    source = u'<Button ToolTip="Сохранить &amp; закрыть" Content=\'Сохранить\'/>'
    monkeypatch.setattr(xaml_i18n, 'tr', lambda text: u'Save "A" & \'B\' <now>')
    root = ET.fromstring(xaml_i18n.translate(source))
    assert root.get('ToolTip') == u'Save "A" & \'B\' <now>'
    assert root.get('Content') == root.get('ToolTip')


def test_notes_xaml_translates_including_headers_and_keeps_pending_trigger(monkeypatch):
    folder = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'lib', 'pnotes', 'xaml')
    monkeypatch.setattr(i18n, 'current', lambda: i18n.EN)
    expected = {'note': 'New project note', 'summary': 'Project summary',
                'setup': 'Project notes setup', 'answer': 'Answer / resolution'}
    for name, title in expected.items():
        path = os.path.join(folder, name + '.xaml')
        with io.open(path, encoding='utf-8') as stream:
            source = stream.read()
        assert xaml_i18n.MARKER in source
        translated = xaml_i18n.load(path)
        assert ET.fromstring(translated).get('Title') == title
        assert source.count('Binding=') == translated.count('Binding=')
        if name == 'summary':
            assert 'Binding="{Binding status}" Value="Не отправлено"' in translated
            assert 'Header="Status" Binding="{Binding status_display}"' in translated


def test_server_errors_translate_without_translating_status_values(monkeypatch):
    monkeypatch.setattr(i18n, 'current', lambda: i18n.EN)
    assert localization.server_error(u'Неизвестный статус: В работе') == u'Unknown status: В работе'
    assert localization.server_error(u'Пустая заметка') == u'Empty note'
    question = u'Вопрос нельзя закрыть без ответа: заполните «Решение» (без ответа — 3 шт.).'
    assert localization.server_error(question) == (
        u'Questions cannot be closed without answers. Fill in «Resolution» (unanswered — 3 items).')
    unknown = u'Custom error: Сведения о проекте'
    assert localization.server_error(unknown) == unknown
    monkeypatch.setattr(i18n, 'current', lambda: i18n.RU)
    assert localization.server_error(question) == question
