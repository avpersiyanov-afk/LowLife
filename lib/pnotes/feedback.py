# -*- coding: utf-8 -*-
"""«Обратная связь» по LowLife: окно (панель → кнопка → описание) и отправка в Google Таблицу автора.

Таблица — отдельная от «Заметок по проекту» и принадлежит автору расширения: веб-приложение
(`docs/feedback/Code.gs`) умеет только дописывать строки, прочитать отзывы через него нельзя.
Адрес веб-приложения общий для всех пользователей, поэтому он записан здесь, в FEEDBACK_URL.
"""
import os
import json
import uuid
import traceback
import datetime

from pyrevit import forms
from System.Windows.Input import Key, Keyboard, ModifierKeys

from pnotes import core
from lowlife import about, ribbon_catalog


# Адрес веб-приложения обратной связи (…/exec) — см. docs/feedback-panel.md.
# Если адрес пуст, отзывы копятся на компьютере пользователя и уйдут, когда он появится.
FEEDBACK_URL = u'https://script.google.com/macros/s/AKfycbzByb8QevXsU_6u9kMImtZCxRD8Dh_kHpSeH6LnCQkI1BuFBm-LgbSgykBif52ftDM5/exec'

USER_DIR = os.path.join(os.environ.get('APPDATA') or os.path.expanduser('~'), 'pyRevit', 'LowLifeFeedback')
# Необязательный личный адрес — чтобы проверить веб-приложение до того, как вписать его в FEEDBACK_URL
USER_CONFIG = os.path.join(USER_DIR, 'config.json')
QUEUE_FILE = os.path.join(USER_DIR, 'queue.json')
STATE_FILE = os.path.join(USER_DIR, 'state.json')

KIND_PROBLEM = u'Проблема'
KIND_IDEA = u'Предложение'
GENERAL_PANEL = u'Общее — LowLife в целом'
WHOLE_PANEL = u'Вся панель / не знаю'

MAX_TEXT = 5000


def feedback_url():
    personal = (core._read_json(USER_CONFIG, {}) or {}).get('url') or u''
    return personal.strip() or FEEDBACK_URL.strip()


# ---------------------------------------------------------------- отправка

def _send(item, timeout_ms=15000):
    url = feedback_url()
    if not url:
        raise core.ApiError(u'Адрес таблицы обратной связи ещё не задан.')
    body = core._dumps({'action': 'feedback', 'feedback': item})
    try:
        try:
            raw = core._post(url, body, timeout_ms, track=False)
        except Exception as ex:
            if not core._is_transient(ex, timeout=True):  # отправка всегда в фоне
                raise
            raw = core._post(url, body, timeout_ms, track=False)  # разовый сбой Google — один повтор
    except Exception as ex:
        raise core.ApiError(u'Нет связи с таблицей обратной связи: ' + core.err_text(ex))
    try:
        resp = json.loads(raw)
    except Exception:
        raise core.ApiError(u'Таблица ответила не данными, а страницей — проверьте адрес веб-приложения.')
    if not resp.get('ok'):
        raise core.ApiError(resp.get('error') or u'Неизвестная ошибка')


QUEUE_LOCK = 'lowlife_feedback_queue_lock'


def queue_size():
    return len(core._read_json(QUEUE_FILE, []) or [])


def flush_queue(timeout_ms=15000):
    """Отправляет накопленные отзывы. Возвращает (отправлено, осталось).
    Из файла убираются только отправленные: добавленное во время отправки не теряется."""
    queue = core._read_json(QUEUE_FILE, []) or []
    if not queue:
        return 0, 0
    sent = set()
    for item in queue:
        try:
            _send(item, timeout_ms)
            sent.add(item.get('id'))
        except core.ApiError:
            break  # нет связи — остальные уйдут в следующий раз
    with core._QueueLock(QUEUE_LOCK):
        left = [i for i in (core._read_json(QUEUE_FILE, []) or []) if i.get('id') not in sent]
        if sent:
            core._write_json(QUEUE_FILE, left)
    return len(sent), len(left)


def queue_item(item):
    """Кладёт сообщение в локальную очередь — с этого момента оно не потеряется."""
    with core._QueueLock(QUEUE_LOCK):
        queue = core._read_json(QUEUE_FILE, []) or []
        queue.append(item)
        core._write_json(QUEUE_FILE, queue)


def send_detached():
    """Отправка очереди в фоне после закрытия окна (у кнопки постоянный движок pyRevit)."""
    if feedback_url():
        core.run_detached('lowlife_feedback_sending', lambda: flush_queue(30000))


def new_item(ctx, panel, button, kind, text, contact):
    return {
        'id': uuid.uuid4().hex[:16],
        'created': datetime.datetime.now().strftime('%Y-%m-%d %H:%M'),
        'user': ctx['user'],
        'windows_user': ctx['windows_user'],
        'contact': contact,
        'panel': panel,
        'button': button,
        'kind': kind,
        'text': text[:MAX_TEXT],
        'version': ctx['version'],
        'revit': ctx['revit'],
        'model': ctx['model'],
    }


def get_context(uiapp):
    app = uiapp.Application
    model = u''
    try:
        doc = uiapp.ActiveUIDocument.Document if uiapp.ActiveUIDocument is not None else None
        if doc is not None:
            model = core.short_file(doc.PathName) or doc.Title
    except Exception:
        pass
    try:
        revit = u'{} ({})'.format(app.VersionName, app.VersionBuild)
    except Exception:
        revit = u''
    return {
        'user': app.Username or u'',
        'windows_user': os.environ.get('USERNAME') or u'',
        'version': about.version_text(),
        'revit': revit,
        'model': model,
    }


def _load_state():
    return core._read_json(STATE_FILE, {}) or {}


def _save_state(**values):
    state = _load_state()
    state.update(values)
    try:
        core._write_json(STATE_FILE, state)
    except Exception:
        pass


# ---------------------------------------------------------------- окно

class FeedbackWindow(forms.WPFWindow):
    def __init__(self, ctx, panels):
        forms.WPFWindow.__init__(self, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                                    'xaml', 'feedback.xaml'))
        self.ctx = ctx
        self.buttons = dict(panels)
        self.result = None  # None — отменено, True — сообщение в очереди на отправку

        self.txtContext.Text = u'   ·   '.join(
            v for v in (u'Автор: ' + (ctx['user'] or ctx['windows_user'] or u'—'),
                        u'LowLife: ' + ctx['version'],
                        ctx['revit'] and u'Revit: ' + ctx['revit']) if v)

        self.cmbPanel.Items.Add(GENERAL_PANEL)
        for title, _ in panels:
            self.cmbPanel.Items.Add(title)
        state = _load_state()
        names = [GENERAL_PANEL] + [t for t, _ in panels]
        self.cmbPanel.SelectionChanged += self.on_panel
        self.cmbPanel.SelectedIndex = names.index(state['panel']) if state.get('panel') in names else 0
        self.txtContact.Text = state.get('contact') or u''

        if not feedback_url():
            self.txtStatus.Text = (u'Адрес таблицы обратной связи ещё не задан — сообщение сохранится '
                                   u'на этом компьютере и отправится, когда он появится в обновлении LowLife.')
        elif queue_size():
            self.txtStatus.Text = u'Ещё не отправлено сообщений: {} — уйдут вместе с этим.'.format(queue_size())
        try:
            from System.Windows.Markup import XmlLanguage
            self.txtText.Language = XmlLanguage.GetLanguage('ru-RU')
            self.txtText.SpellCheck.IsEnabled = True
        except Exception:
            pass

        self.btnSend.Click += self.on_send
        self.btnCancel.Click += lambda s, e: self.Close()
        self.PreviewKeyDown += self.on_key
        self.Loaded += lambda s, e: self.cmbPanel.Focus()

    def on_panel(self, sender, e):
        panel = self.cmbPanel.SelectedItem
        self.cmbButton.Items.Clear()
        self.cmbButton.Items.Add(WHOLE_PANEL)
        for title in self.buttons.get(panel, []):
            self.cmbButton.Items.Add(title)
        self.cmbButton.SelectedIndex = 0
        self.cmbButton.IsEnabled = panel != GENERAL_PANEL

    def on_key(self, sender, e):
        if e.Key == Key.Enter and Keyboard.Modifiers == ModifierKeys.Control:
            e.Handled = True
            self.on_send(None, None)

    def on_send(self, sender, e):
        text = (self.txtText.Text or u'').strip()
        if not text:
            self.txtStatus.Text = u'Опишите проблему или предложение.'
            self.txtText.Focus()
            return
        panel = self.cmbPanel.SelectedItem or GENERAL_PANEL
        button = self.cmbButton.SelectedItem if panel != GENERAL_PANEL else u''
        if button == WHOLE_PANEL:
            button = u''
        kind = KIND_IDEA if self.rbIdea.IsChecked else KIND_PROBLEM
        contact = (self.txtContact.Text or u'').strip()
        _save_state(panel=panel, contact=contact)
        item = new_item(self.ctx, u'' if panel == GENERAL_PANEL else panel, button, kind, text, contact)

        queue_item(item)
        self.result = True  # отправит _run в фоне, уже после закрытия окна
        self.Close()


def run(uiapp):
    try:
        _run(uiapp)
    except Exception as ex:
        forms.alert(core.err_text(ex), title=u'Обратная связь: ошибка', expanded=traceback.format_exc())


def _run(uiapp):
    win = FeedbackWindow(get_context(uiapp), ribbon_catalog.list_panels())
    win.ShowDialog()
    if not win.result:
        return
    if not feedback_url():
        forms.alert(u'Сообщение сохранено на этом компьютере и отправится, когда в обновлении LowLife '
                    u'появится адрес таблицы обратной связи.', title=u'Сообщение сохранено')
        return
    # не ждём таблицу: отправка идёт в фоне, Revit свободен сразу; без связи сообщение
    # остаётся в очереди и уйдёт со следующим
    send_detached()
    try:
        forms.show_balloon(u'LowLife', u'Спасибо! Сообщение отправляется.')
    except Exception:
        pass
