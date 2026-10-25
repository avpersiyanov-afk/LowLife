# -*- coding: utf-8 -*-
"""Exercise feedback submission logic without WPF, a real queue, or network access."""
import ast
import io
import os

from lowlife import i18n


class Box(object):
    def __init__(self, **values):
        self.__dict__.update(values)


def _window(monkeypatch, consent):
    path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'lib', 'pnotes', 'feedback.py')
    with io.open(path, encoding='utf-8') as stream:
        tree = ast.parse(stream.read())
    names = {'KIND_PROBLEM', 'KIND_IDEA', 'GENERAL_PANEL', 'WHOLE_PANEL', 'CONSENT_REQUIRED'}
    tree.body = [n for n in tree.body if
                 isinstance(n, ast.ClassDef) and n.name == 'FeedbackWindow' or
                 isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id in names for t in n.targets)]
    queued, saved = [], []
    namespace = {'forms': Box(WPFWindow=object), 'N_': i18n.N_, 'tr': i18n.tr,
                 '_save_state': lambda **values: saved.append(values),
                 'new_item': lambda ctx, panel, button, kind, text, contact:
                     dict(panel=panel, button=button, kind=kind, text=text),
                 'queue_item': queued.append}
    exec(compile(tree, path, 'exec'), namespace)
    window = namespace['FeedbackWindow'].__new__(namespace['FeedbackWindow'])
    window.ctx = {}
    window._panel_names = [namespace['GENERAL_PANEL'], u'СОТ']
    window._button_names = [namespace['WHOLE_PANEL'], u'Марки оборудования']
    window.cmbPanel = Box(SelectedIndex=1, SelectedItem=u'CCTV')
    window.cmbButton = Box(SelectedIndex=1, SelectedItem=u'Equipment tags')
    window.txtText = Box(Text=u'Текст пользователя', Focus=lambda: None)
    window.txtContact = Box(Text=u'')
    window.chkConsent = Box(IsChecked=consent, Focus=lambda: None)
    window.rbIdea = Box(IsChecked=True)
    window.txtStatus = Box(Text=u'')
    window.tabs = Box(SelectedItem=None)
    window.tabNew = object()
    window.Close = lambda: None
    monkeypatch.setattr(i18n, 'current', lambda: i18n.EN)
    return window, queued, saved


def test_english_choices_submit_original_values(monkeypatch):
    window, queued, saved = _window(monkeypatch, consent=True)
    window.on_send(None, None)
    assert queued == [dict(panel=u'СОТ', button=u'Марки оборудования',
                           kind=u'Предложение', text=u'Текст пользователя')]
    assert saved[0]['panel'] == u'СОТ'
    assert window.result is True


def test_english_consent_is_required_even_for_keyboard_submission(monkeypatch):
    window, queued, saved = _window(monkeypatch, consent=False)
    window.on_send(None, None)
    assert queued == [] and saved == []
    assert window.txtStatus.Text == u'To send a message, check the personal data consent box.'
    assert window.tabs.SelectedItem is window.tabNew
