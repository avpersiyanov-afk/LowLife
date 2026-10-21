# -*- coding: utf-8 -*-
"""«Обратная связь» по LowLife: окно (панель → кнопка → описание) и отправка в Google Таблицу автора.

Таблица — отдельная от «Заметок по проекту» и принадлежит автору расширения: веб-приложение
(`docs/feedback/Code.gs`) дописывает строки, а прочитать через него можно только статус и ответ
автора на свои сообщения — по их случайным ID из локальной истории (`sent.json`). Ответы
проверяются в фоне (при запуске Revit и открытии модели, не чаще раза в несколько часов, и при
открытии окна) и показываются на вкладке «Мои сообщения»; о новом ответе напоминает уведомление.
Адрес веб-приложения общий для всех пользователей, поэтому он записан здесь, в FEEDBACK_URL.
"""
import os
import json
import uuid
import traceback
import datetime

from pyrevit import forms
import System
from System.Windows import Visibility, Thickness, CornerRadius, FontWeights, TextWrapping
from System.Windows.Controls import Border, StackPanel, TextBlock, TextBox
from System.Windows.Input import Key, Keyboard, ModifierKeys
from System.Windows.Media import BrushConverter

from pnotes import core
from lowlife import about, ribbon_catalog, feedback_core


# Адрес веб-приложения обратной связи (…/exec) — см. docs/feedback-panel.md.
# Если адрес пуст, отзывы копятся на компьютере пользователя и уйдут, когда он появится.
FEEDBACK_URL = u'https://script.google.com/macros/s/AKfycbzByb8QevXsU_6u9kMImtZCxRD8Dh_kHpSeH6LnCQkI1BuFBm-LgbSgykBif52ftDM5/exec'

USER_DIR = os.path.join(os.environ.get('APPDATA') or os.path.expanduser('~'), 'pyRevit', 'LowLifeFeedback')
# Необязательный личный адрес — чтобы проверить веб-приложение до того, как вписать его в FEEDBACK_URL
USER_CONFIG = os.path.join(USER_DIR, 'config.json')
QUEUE_FILE = os.path.join(USER_DIR, 'queue.json')
STATE_FILE = os.path.join(USER_DIR, 'state.json')
HISTORY_FILE = os.path.join(USER_DIR, 'sent.json')  # свои отправленные сообщения — по ним ищутся ответы

KIND_PROBLEM = u'Проблема'
KIND_IDEA = u'Предложение'
GENERAL_PANEL = u'Общее — LowLife в целом'
WHOLE_PANEL = u'Вся панель / не знаю'

MAX_TEXT = 5000
CONSENT_REQUIRED = u'Чтобы отправить сообщение, отметьте согласие на обработку персональных данных.'


def feedback_url():
    personal = (core._read_json(USER_CONFIG, {}) or {}).get('url') or u''
    return personal.strip() or FEEDBACK_URL.strip()


# ---------------------------------------------------------------- отправка

def _call(payload, timeout_ms=15000, track=False):
    url = feedback_url()
    if not url:
        raise core.ApiError(u'Адрес таблицы обратной связи ещё не задан.')
    body = core._dumps(payload)
    try:
        try:
            raw = core._post(url, body, timeout_ms, track=track)
        except Exception as ex:
            if not core._is_transient(ex, timeout=True):  # запросы всегда в фоне
                raise
            raw = core._post(url, body, timeout_ms, track=track)  # разовый сбой Google — один повтор
    except Exception as ex:
        raise core.ApiError(u'Нет связи с таблицей обратной связи: ' + core.err_text(ex))
    try:
        resp = json.loads(raw)
    except Exception:
        raise core.ApiError(u'Таблица ответила не данными, а страницей — проверьте адрес веб-приложения.')
    if not resp.get('ok'):
        raise core.ApiError(resp.get('error') or u'Неизвестная ошибка')
    return resp


def _send(item, timeout_ms=15000):
    _call({'action': 'feedback', 'feedback': item}, timeout_ms)


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
    """Кладёт сообщение в локальную очередь — с этого момента оно не потеряется —
    и в историю своих сообщений, по которой потом ищутся ответы автора."""
    with core._QueueLock(QUEUE_LOCK):
        queue = core._read_json(QUEUE_FILE, []) or []
        queue.append(item)
        core._write_json(QUEUE_FILE, queue)
    try:
        _update_history(lambda h: feedback_core.add_to_history(h, item))
    except Exception:
        pass  # без истории не будет только ответа в окне — сообщение всё равно уйдёт


def send_detached():
    """Отправка очереди в фоне после закрытия окна (у кнопки постоянный движок pyRevit)."""
    if feedback_url():
        core.run_detached('lowlife_feedback_sending', lambda: flush_queue(30000))


# ---------------------------------------------------------------- ответы автора

HISTORY_LOCK = 'lowlife_feedback_history_lock'
REPLIES_FLAG = 'lowlife_feedback_replies'
NOTIFIED_KEY = 'lowlife_feedback_notified'  # о каких ответах уже напоминали в этом сеансе Revit


def load_history():
    return core._read_json(HISTORY_FILE, []) or []


def _update_history(change):
    with core._QueueLock(HISTORY_LOCK):
        history = change(load_history())
        core._write_json(HISTORY_FILE, history)
    return history


def mark_seen():
    return _update_history(feedback_core.mark_seen)


def fetch_replies(timeout_ms=15000, track=False):
    """Спрашивает таблицу о статусе и ответе на свои сообщения. Возвращает (история, новых ответов)."""
    ids = feedback_core.ids_to_check(load_history())
    _save_state(replies_checked=datetime.datetime.now().strftime(feedback_core.TIME_FORMAT))
    if not ids:
        return load_history(), 0
    replies = _call({'action': 'replies', 'ids': ids}, timeout_ms, track=track).get('replies') or []
    changed = [0]

    def merge(history):
        history, changed[0] = feedback_core.merge_replies(history, replies)
        return history
    return _update_history(merge), changed[0]


def _unread_key(unread):
    return u'|'.join(sorted(u'{}:{}'.format(h.get('id'), len(h.get('reply') or u'')) for h in unread))


def notify_unread():
    """Напоминание о непрочитанных ответах — без сети, по локальной истории; об одних и тех же
    ответах — один раз за сеанс Revit. Никогда не падает."""
    try:
        unread = feedback_core.unread(load_history())
        if not unread:
            return
        domain = System.AppDomain.CurrentDomain
        key = _unread_key(unread)
        if domain.GetData(NOTIFIED_KEY) == key:
            return
        domain.SetData(NOTIFIED_KEY, key)
        forms.toast(feedback_core.unread_notice(len(unread)), title=u'LowLife — ответ автора')
    except Exception:
        pass


def check_replies_detached(force=False):
    """Фоновая проверка ответов (хуки запуска Revit и открытия модели): не чаще раза
    в feedback_core.CHECK_HOURS часов; заодно досылает сообщения, не ушедшие без связи.
    Новый ответ — сразу уведомление. Никогда не падает."""
    try:
        if not feedback_url():
            return
        if queue_size():
            send_detached()
        if not load_history():
            return
        if not force and not feedback_core.check_due(_load_state().get('replies_checked')):
            return

        def work():
            try:
                _, changed = fetch_replies(30000)
                if changed:
                    notify_unread()
            except Exception:
                pass
            return 0, 0
        core.run_detached(REPLIES_FLAG, work)
    except Exception:
        pass


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


def _make(cls, **props):
    """WPF-элемент со свойствами: Cls(Prop=...) понимает только IronPython, не pythonnet."""
    obj = cls()
    for name, value in props.items():
        setattr(obj, name, value)
    return obj


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
        self._init_consent()

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

        self._fresh = set()  # ID ответов, новых на момент открытия вкладки, — подсвечены
        self.history = load_history()
        self.tabs.SelectionChanged += self.on_tab
        self.btnRefresh.Click += lambda s, e: self._refresh()
        self._render_history()
        if feedback_core.unread(self.history):
            self.tabs.SelectedItem = self.tabHistory  # есть непрочитанный ответ — сразу к нему
        self._refresh()

    # ---------------------------------------------------- мои сообщения

    def _history_open(self):
        return self.tabs.SelectedItem == self.tabHistory

    def on_tab(self, sender, e):
        # SelectionChanged всплывает и от списков «Панель»/«Кнопка» — проверяем саму вкладку
        if self._history_open() and feedback_core.unread(self.history):
            self._show_replies()

    def _show_replies(self):
        """Вкладка открыта — новые ответы прочитаны (подсветка остаётся до закрытия окна)."""
        self._fresh.update(h['id'] for h in feedback_core.unread(self.history))
        try:
            self.history = mark_seen()
        except Exception:
            pass
        self._render_history()

    def _refresh(self):
        if not feedback_url() or not self.history:
            return
        self.btnRefresh.IsEnabled = False
        self.txtHistoryInfo.Text = u'Проверяю ответы…'
        from pnotes import ui
        ui.in_background(self, lambda: fetch_replies(15000, track=True), self._refreshed)

    def _refreshed(self, result, error):
        self.btnRefresh.IsEnabled = True
        if error:
            self._render_history(u'Не удалось проверить ответы: ' + error)
            return
        self.history = result[0]
        if self._history_open() and feedback_core.unread(self.history):
            self._show_replies()
        else:
            self._render_history()

    def _render_history(self, info=None):
        unread = len(feedback_core.unread(self.history))
        self.tabHistory.Header = (u'Мои сообщения · новых ответов: {}'.format(unread) if unread
                                  else u'Мои сообщения')
        replied = len([h for h in self.history if h.get('reply')])
        if info is None:
            info = (u'Ответы автора на ваши сообщения: {} из {}.'.format(replied, len(self.history))
                    if self.history else
                    u'Здесь появятся ваши сообщения и ответы автора на них. Сообщения, отправленные '
                    u'до этой версии LowLife, здесь не показываются.')
        self.txtHistoryInfo.Text = info
        self.btnRefresh.Visibility = Visibility.Visible if self.history else Visibility.Collapsed
        queued = set(i.get('id') for i in (core._read_json(QUEUE_FILE, []) or []))
        self.pnlHistory.Children.Clear()
        for h in reversed(self.history):
            self.pnlHistory.Children.Add(self._card(h, h.get('id') in queued))

    def _card(self, h, queued):
        brush = BrushConverter().ConvertFromString
        card = StackPanel()
        border = _make(Border, Child=card, Padding=Thickness(10, 8, 10, 8), Margin=Thickness(0, 0, 4, 8),
                       CornerRadius=CornerRadius(4), BorderThickness=Thickness(1),
                       BorderBrush=brush('#DDDDDD'), Background=brush('#FAFBFC'))
        if queued:
            status = u'Ещё не отправлено — уйдёт, когда будет связь'
        elif h.get('delivered'):
            status = u'Статус: ' + (h.get('status') or u'получено')
        else:
            status = u''
        head = u'   ·   '.join(v for v in (h.get('created'), h.get('kind'), feedback_core.where_text(h), status)
                                if v)
        card.Children.Add(_make(TextBlock, Text=head, Foreground=brush('#666666'), FontSize=12,
                                TextWrapping=TextWrapping.Wrap))
        text = h.get('text') or u''
        if len(text) > 600:
            text = text[:600].rstrip() + u'…'
        card.Children.Add(_make(TextBlock, Text=text, TextWrapping=TextWrapping.Wrap, Margin=Thickness(0, 4, 0, 0)))

        reply = h.get('reply') or u''
        if not reply:
            card.Children.Add(_make(TextBlock, Text=u'Ответа пока нет.', Foreground=brush('#999999'),
                                    FontSize=12, Margin=Thickness(0, 6, 0, 0)))
            return border
        fresh = h.get('id') in self._fresh or feedback_core.is_unread(h)
        title = u' · '.join(v for v in (u'Ответ автора', h.get('replied'), fresh and u'новый') if v)
        box = StackPanel()
        box.Children.Add(_make(TextBlock, Text=title, FontWeight=FontWeights.SemiBold, FontSize=12,
                               Foreground=brush('#B05A00')))
        # TextBox только для чтения — ответ можно выделить и скопировать (ссылку, команду)
        box.Children.Add(_make(TextBox, Text=reply, IsReadOnly=True, TextWrapping=TextWrapping.Wrap,
                               BorderThickness=Thickness(0), Background=brush('Transparent'),
                               Padding=Thickness(0), Margin=Thickness(0, 2, 0, 0)))
        card.Children.Add(_make(Border, Child=box, Margin=Thickness(0, 8, 0, 0), Padding=Thickness(8, 6, 8, 6),
                                BorderThickness=Thickness(3, 0, 0, 0), BorderBrush=brush('#F08C28'),
                                Background=brush('#FFF3E6' if fresh else '#FFF8F0')))
        return border

    def _init_consent(self):
        # согласие даётся на каждое сообщение: галочка не запоминается, без неё «Отправить» недоступна
        self.chkConsent.IsChecked = False
        self.btnSend.IsEnabled = False

        def changed(s, e):
            self.btnSend.IsEnabled = bool(self.chkConsent.IsChecked)
            if self.chkConsent.IsChecked and self.txtStatus.Text == CONSENT_REQUIRED:
                self.txtStatus.Text = u''
        self.chkConsent.Checked += changed
        self.chkConsent.Unchecked += changed

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
            self.tabs.SelectedItem = self.tabNew
            self.txtText.Focus()
            return
        if not self.chkConsent.IsChecked:  # Ctrl+Enter работает и при недоступной «Отправить»
            self.txtStatus.Text = CONSENT_REQUIRED
            self.tabs.SelectedItem = self.tabNew
            self.chkConsent.Focus()
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
    # остаётся в очереди и уйдёт со следующим (или при следующей проверке ответов)
    core.begin_requests()  # окно при закрытии оборвало свою проверку ответов — повтор отправки не запрещать
    send_detached()
    try:
        forms.show_balloon(u'LowLife', u'Спасибо! Сообщение отправляется.')
    except Exception:
        pass
