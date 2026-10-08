# -*- coding: utf-8 -*-
"""Окна «Заметок по проекту»: новая заметка, сводка, настройка, напоминания."""
import os
import io
import time
import datetime
import traceback

from pyrevit import forms

import clr
clr.AddReference('System.Data')
import System
from System.Data import DataTable
from System.Diagnostics import Process, ProcessStartInfo
from System.Windows import Visibility
from System.Windows.Input import Key, Keyboard, ModifierKeys, Cursors
from System.Collections.Generic import List
from System.Threading import Thread, ThreadStart
from Autodesk.Revit.DB import ElementId

from pnotes import core


XAML_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'xaml')
STR = clr.GetClrType(System.String)
BOOL = clr.GetClrType(System.Boolean)


def _xaml(name):
    return os.path.join(XAML_DIR, name)


def _fill(combo, items, selected=None):
    combo.Items.Clear()
    for item in items:
        combo.Items.Add(item)
    if selected in items:
        combo.SelectedIndex = list(items).index(selected)
    elif items:
        combo.SelectedIndex = 0


def fmt_date(iso):
    """'2026-10-02' → '02.10.2026', '2026-10-02 14:30' → '02.10.2026 14:30'."""
    if not iso:
        return u''
    try:
        y, m, d = iso[:10].split('-')
        return u'{}.{}.{}{}'.format(d, m, y, iso[10:])
    except Exception:
        return iso


def _spellcheck(textbox):
    """Проверка орфографии — только если она есть в системе: на части машин WPF падает при её включении."""
    try:
        from System.Windows.Markup import XmlLanguage
        textbox.Language = XmlLanguage.GetLanguage('ru-RU')
        textbox.SpellCheck.IsEnabled = True
    except Exception:
        pass


ERROR_LOG = os.path.join(core.USER_DIR, 'error.log')

REPO_URL = u'https://github.com/avpersiyanov-afk/LowLife'
GUIDE_URL = REPO_URL + u'/blob/main/docs/notes-panel.md#подключение-для-новой-команды-или-компании'
SCRIPT_URL = REPO_URL + u'/blob/main/docs/notes/Code.gs'


def open_url(url):
    """Открыть ссылку в браузере; UseShellExecute нужен в Revit 2025+ (.NET 8)."""
    info = ProcessStartInfo(url)
    info.UseShellExecute = True
    Process.Start(info)


def guarded(func):
    """Точка входа кнопки: любая ошибка — понятное окно и запись в error.log, а не пустое окно pyRevit."""
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception as ex:
            details = traceback.format_exc()
            _log_error(func.__name__, details)
            forms.alert(u'{}\n\nПодробности записаны в файл:\n{}'.format(core.err_text(ex), ERROR_LOG),
                        title=u'Заметки: ошибка', expanded=details)
    wrapper.__name__ = func.__name__
    return wrapper


def _log_error(where, details):
    try:
        if not os.path.isdir(core.USER_DIR):
            os.makedirs(core.USER_DIR)
        with io.open(ERROR_LOG, 'a', encoding='utf-8') as f:
            f.write(u'\n==== {} — {}\n{}'.format(
                datetime.datetime.now().strftime('%d.%m.%Y %H:%M:%S'), where, details))
    except Exception:
        pass


def in_background(window, work, done):
    """work() — в фоновом потоке (только сеть и файлы, без Revit API), затем done(результат, ошибка)
    — в потоке окна. Пока идёт запрос, окно живое и Revit не «зависает».
    При закрытии окна идущие запросы обрываются, а потоки дожидаются (_stop_background)."""
    if not getattr(window, '_bg_threads', None):
        window._bg_threads = []
        window._bg_closed = False
        window.Closed += lambda s, e: _stop_background(window)
    core.begin_requests()

    def deliver(result, error):
        if window._bg_closed:
            return
        try:
            done(result, error)
        except Exception:
            _log_error(getattr(done, '__name__', 'done'), traceback.format_exc())

    def body():
        result, error = None, None
        try:
            result = work()
        except core.ApiError as ex:
            error = core.err_text(ex)
        except Exception as ex:
            error = core.err_text(ex)
            _log_error(getattr(work, '__name__', 'work'), traceback.format_exc())
        except:  # noqa: E722 — из фонового потока не должно вылететь ничего: это уронило бы Revit
            error = u'ошибка'
        try:
            window.Dispatcher.BeginInvoke(System.Action(lambda: deliver(result, error)))
        except:  # noqa: E722
            pass

    thread = Thread(ThreadStart(body))
    thread.IsBackground = True
    window._bg_threads.append(thread)
    thread.Start()


def _stop_background(window):
    window._bg_closed = True
    core.abort_requests()
    for thread in window._bg_threads:
        try:
            thread.Join(3000)
        except Exception:
            pass
    core.begin_requests()


def _balloon(text):
    try:
        forms.show_balloon(u'Заметки', text)
    except Exception:
        pass


# ================================================================ новая заметка

EDIT_FIELDS = ('type', 'section', 'text', 'due', 'assignee')


class NoteWindow(forms.WPFWindow):
    """Новая заметка; с note=... — редактирование существующей (результат в self.changes)."""

    def __init__(self, ctx, settings, online, note=None):
        """online=None — настройки взяты из копии, связь проверяется в фоне после открытия окна."""
        forms.WPFWindow.__init__(self, _xaml('note.xaml'))
        self.ctx = ctx
        self.note = note
        self.result = None  # None — отменено, True — заметка в очереди на отправку
        self.changes = None  # редактирование: {поле: новое значение} или None — отменено

        if ctx['name'] and ctx['name'] != ctx['key']:
            self.txtProject.Text = u'{} — {}'.format(ctx['key'], ctx['name'])
        else:
            self.txtProject.Text = ctx['key']
        details = []
        if ctx['view']:
            details.append(u'Вид: ' + ctx['view'])
        details.append(u'Автор: ' + ctx['user'])
        if ctx['key_from_file']:
            details.append(u'код проекта не заполнен — используется имя файла')
        self.txtContext.Text = u'   ·   '.join(details)

        state = core.load_state()
        if note is not None:
            state = {'type': note.get('type'), 'section': note.get('section')}
        _fill(self.cmbType, self._with(settings['types'], state.get('type')), state.get('type'))
        _fill(self.cmbSection, self._with(settings['sections'], state.get('section')), state.get('section'))
        for person in settings.get('people') or []:
            self.cmbAssignee.Items.Add(person)
        if note is not None:
            self._init_edit(note)

        count = len(ctx['selection'])
        if count:
            self.chkElements.Content = u'Привязать выбранные элементы ({})'.format(count)
            self.chkElements.IsChecked = True
        else:
            self.chkElements.Content = u'Привязать выбранные элементы (сейчас ничего не выбрано)'
            self.chkElements.IsEnabled = False

        if online is False and note is None:
            self._offline_notice()
        elif note is None:
            waiting = core.queue_size()
            if waiting:
                self.txtStatus.Text = u'Ещё не отправлено заметок: {} — уйдут вместе с этой.'.format(waiting)

        _spellcheck(self.txtText)
        self.btnSave.Click += self.on_save
        self.btnCancel.Click += lambda s, e: self.Close()
        self.PreviewKeyDown += self.on_key
        self.Loaded += lambda s, e: self.cmbType.Focus()
        if online is None and note is None:
            # обновить копию настроек команды, пока пишется заметка (Revit не ждёт)
            self.Loaded += lambda s, e: in_background(self, lambda: core.get_settings(timeout_ms=30000)[1],
                                                      self._settings_checked)

    def _offline_notice(self):
        self.txtStatus.Text = u'Нет связи с таблицей — заметка сохранится на этом компьютере и отправится при следующей возможности.'

    def _settings_checked(self, online, error):
        if not online and self.result is None:
            self._offline_notice()

    @staticmethod
    def _with(items, value):
        """Список из настроек + текущее значение заметки, если его там уже нет."""
        items = list(items)
        if value and value not in items:
            items.append(value)
        return items

    def _init_edit(self, note):
        self.Title = u'Редактирование заметки'
        self.btnSave.Content = u'Сохранить изменения'
        details = [u'Автор: ' + (note.get('author') or u'—'), u'Создано: ' + fmt_date(note.get('created'))]
        if note.get('view'):
            details.insert(0, u'Вид: ' + note['view'])
        self.txtContext.Text = u'   ·   '.join(details)
        self.txtText.Text = note.get('text') or u''
        self.cmbAssignee.Text = note.get('assignee') or u''
        due = core.due_date(note)
        if due is not None:
            self.dpDue.SelectedDate = System.DateTime(due.year, due.month, due.day)
        # привязка элементов при редактировании не меняется
        self.chkElements.Visibility = Visibility.Collapsed

    def on_key(self, sender, e):
        if e.Key == Key.Enter and Keyboard.Modifiers == ModifierKeys.Control:
            e.Handled = True
            self.on_save(None, None)

    def on_save(self, sender, e):
        text = (self.txtText.Text or u'').strip()
        if not text:
            self.txtStatus.Text = u'Напишите текст заметки.'
            self.txtText.Focus()
            return
        due = u''
        if self.dpDue.SelectedDate is not None:
            due = self.dpDue.SelectedDate.ToString('yyyy-MM-dd')
        ntype = self.cmbType.SelectedItem or u''
        section = self.cmbSection.SelectedItem or u''
        assignee = (self.cmbAssignee.Text or u'').strip()
        if self.note is not None:
            values = {'type': ntype, 'section': section, 'text': text, 'due': due, 'assignee': assignee}
            self.changes = dict((k, v) for k, v in values.items()
                                if v != (self.note.get(k) or u'')[:10 if k == 'due' else None])
            self.Close()
            return
        elements = self.ctx['selection'] if self.chkElements.IsChecked else []
        note = core.new_note(self.ctx, ntype, section, text, due, assignee, elements)
        core.save_state(type=ntype, section=section)

        core.queue_note(note)  # с этого момента заметка не потеряется, даже если связи нет
        self.result = True  # отправит run_new_note в фоне, уже после закрытия окна
        self.Close()


# ================================================================ сводка

COLUMNS = ('id', 'due', 'type', 'section', 'text', 'answer', 'assignee', 'author', 'created',
           'status', 'view', 'model', 'overdue', 'closed', 'need_answer')

FILTER_STATUS = (u'Открытые', u'Все', u'Закрытые')
ALL_TYPES = u'Все типы'
ALL_SECTIONS = u'Все разделы'
ALL_AUTHORS = u'Все авторы'


def _sorted(notes):
    """Сначала открытые; среди них — по сроку (без срока в конце); свежие выше."""
    notes = sorted(notes, key=lambda n: n.get('created') or u'', reverse=True)
    return sorted(notes, key=lambda n: (core.is_closed(n), not n.get('due'), n.get('due') or u''))


class SummaryWindow(forms.WPFWindow):
    def __init__(self, ctx, settings, notes, error=None, uidoc=None, reminders_mode=False, load=False):
        """load=True — notes это сохранённая копия; свежие заметки подгружаются в фоне после открытия."""
        forms.WPFWindow.__init__(self, _xaml('summary.xaml'))
        self._ready = False
        self.ctx = ctx
        self.settings = settings
        self.notes = notes
        self.uidoc = uidoc
        self.reminders_mode = reminders_mode
        self._settings_refreshed = False
        self._pending = 0  # изменений, ещё не дошедших до таблицы
        self._overrides = []  # изменения из этого окна — поверх загрузки, начатой до их сохранения
        self._close_when_done = False
        self._load_timing = None

        title = ctx['key'] if ctx['name'] == ctx['key'] else u'{} — {}'.format(ctx['key'], ctx['name'])
        if reminders_mode:
            self.Title = u'Напоминания по проекту'
            self.txtProject.Text = u'{}: сроки подходят или задачи назначены вам'.format(title)
            self.btnShow.Visibility = Visibility.Collapsed
            self.btnView.Visibility = Visibility.Collapsed
        else:
            self.txtProject.Text = title
        self._notice(error)

        present_types = [n.get('type') for n in notes if n.get('type')]
        present_sections = [n.get('section') for n in notes if n.get('section')]
        _fill(self.cmbStatus, FILTER_STATUS)
        _fill(self.cmbType, [ALL_TYPES] + self._merge(settings['types'], present_types))
        _fill(self.cmbSection, [ALL_SECTIONS] + self._merge(settings['sections'], present_sections))
        self._fill_authors()

        for combo in (self.cmbStatus, self.cmbType, self.cmbSection, self.cmbAuthor):
            combo.SelectionChanged += self.refresh
        self.txtSearch.TextChanged += self.refresh
        self.chkMine.Checked += self.refresh
        self.chkMine.Unchecked += self.refresh
        self.dg.MouseDoubleClick += self.on_show
        self.btnDone.Click += lambda s, e: self.change_status(core.STATUS_DONE)
        self.btnWork.Click += lambda s, e: self.change_status(core.STATUS_WORK)
        self.btnCancelNote.Click += lambda s, e: self.change_status(core.STATUS_CANCEL)
        self.btnReopen.Click += lambda s, e: self.change_status(core.STATUS_OPEN)
        self.btnAnswer.Click += self.on_answer
        self.btnEdit.Click += self.on_edit
        self.btnShow.Click += self.on_show
        self.btnView.Click += self.on_view
        self.btnRefresh.Click += self.on_reload
        self.btnSheet.Click += self.on_sheet
        self.btnClose.Click += lambda s, e: self.Close()
        self.Closing += self.on_closing
        self.btnSheet.IsEnabled = bool(settings.get('sheet_url'))

        self._ready = True
        self.refresh()
        if load:
            self.Loaded += self.on_reload

    @staticmethod
    def _merge(base, extra):
        result = list(base)
        for item in extra:
            if item not in result:
                result.append(item)
        return result

    def _fill_authors(self):
        """Авторы, у которых есть заметки по проекту; выбранный сохраняется при обновлении."""
        current = self.cmbAuthor.SelectedItem
        authors = sorted(set(n.get('author') for n in self.notes if n.get('author')), key=lambda a: a.lower())
        _fill(self.cmbAuthor, [ALL_AUTHORS] + authors, current)

    def _notice(self, text):
        self.txtNotice.Text = text or u''
        self.txtNotice.Visibility = Visibility.Visible if text else Visibility.Collapsed

    def _visible_notes(self):
        status = self.cmbStatus.SelectedIndex
        ntype = self.cmbType.SelectedItem
        section = self.cmbSection.SelectedItem
        author = self.cmbAuthor.SelectedItem
        query = (self.txtSearch.Text or u'').strip().lower()
        mine = bool(self.chkMine.IsChecked)
        result = []
        for n in self.notes:
            closed = core.is_closed(n)
            if status == 0 and closed or status == 2 and not closed:
                continue
            if ntype and ntype != ALL_TYPES and n.get('type') != ntype:
                continue
            if section and section != ALL_SECTIONS and n.get('section') != section:
                continue
            if author and author != ALL_AUTHORS and n.get('author') != author:
                continue
            if mine and not core.is_mine(n, self.ctx['user']):
                continue
            if query and query not in u' '.join(
                    [n.get(k) or u'' for k in ('text', 'answer', 'author', 'assignee', 'view')]).lower():
                continue
            result.append(n)
        return _sorted(result)

    def refresh(self, *args):
        if not self._ready:
            return
        table = DataTable()
        for col in COLUMNS:
            table.Columns.Add(col, STR)
        today = datetime.date.today()
        visible = self._visible_notes()
        for n in visible:
            row = table.NewRow()
            row['id'] = n.get('id') or u''
            row['due'] = fmt_date(n.get('due'))
            row['type'] = n.get('type') or u''
            row['section'] = n.get('section') or u''
            row['text'] = n.get('text') or u''
            row['answer'] = n.get('answer') or u''
            row['need_answer'] = u'1' if core.needs_answer(n) else u'0'
            row['assignee'] = n.get('assignee') or u''
            row['author'] = n.get('author') or u''
            row['created'] = fmt_date(n.get('created'))
            row['status'] = n.get('status') or u''
            row['view'] = n.get('view') or u''
            row['model'] = core.short_file(n.get('file'))
            row['overdue'] = u'1' if core.is_overdue(n, today) else u'0'
            row['closed'] = u'1' if core.is_closed(n) else u'0'
            table.Rows.Add(row)
        self.dg.ItemsSource = table.DefaultView

        open_count = len([n for n in self.notes if not core.is_closed(n)])
        overdue = len([n for n in self.notes if core.is_overdue(n, today)])
        unanswered = len([n for n in self.notes if core.needs_answer(n)])
        self.txtInfo.Text = u'Показано {} из {}   ·   открытых {}   ·   просрочено {}   ·   вопросов без ответа {}'.format(
            len(visible), len(self.notes), open_count, overdue, unanswered)
        if self._load_timing is not None:
            t = self._load_timing
            text = u'   ·   загружено из таблицы за {:.1f} с'.format(float(t['total']))
            parts = []
            if t['server'] is not None:
                script = t['server'] / 1000.0
                parts.append(u'скрипт Google {:.1f} с'.format(script))
                parts.append(u'сеть и запуск веб-приложения {:.1f} с'.format(
                    max(0.0, float(t['total'] - t['queue']) - script)))
            if t['queue'] >= 0.1:
                parts.append(u'отправка неотправленных {:.1f} с'.format(float(t['queue'])))
            if parts:
                text += u' (' + u', '.join(parts) + u')'
            self.txtInfo.Text += text

    def _selected(self):
        ids = [drv.Row['id'] for drv in self.dg.SelectedItems]
        return [n for n in self.notes if n.get('id') in ids]

    def change_status(self, status):
        selected = [n for n in self._selected() if n.get('status') != core.STATUS_PENDING]
        if not selected:
            self.txtInfo.Text = u'Выделите одну или несколько заметок (Ctrl/Shift — несколько).'
            return
        if status == core.STATUS_DONE:
            unanswered = [n for n in selected if core.needs_answer(n)]
            if len(selected) == 1 and unanswered:
                self._answer(selected[0], close=True)
                return
            if unanswered:
                forms.alert(u'Среди выбранных {} вопрос(ов) без ответа. Вопрос закрывается только с ответом — '
                            u'выделите его и нажмите «Ответ / решение».'.format(len(unanswered)),
                            title=u'Нужен ответ')
                return
        ids, user = [n['id'] for n in selected], self.ctx['user']
        self._apply(selected, {'status': status}, lambda: core.set_status(ids, status, user),
                    u'Не удалось изменить статус')

    def on_edit(self, sender, e):
        selected = self._selected()
        if len(selected) != 1:
            self.txtInfo.Text = u'Выделите одну заметку, чтобы изменить её.'
            return
        note = selected[0]
        dlg = NoteWindow(self.ctx, self.settings, True, note=note)
        dlg.Owner = self
        dlg.ShowDialog()
        if not dlg.changes:
            return
        changes, user, sent = dict(dlg.changes), self.ctx['user'], dict(note)
        self._apply([note], changes, lambda: core.update_note(sent, changes, user),
                    u'Не удалось сохранить изменения')

    def on_answer(self, sender, e):
        selected = [n for n in self._selected() if n.get('status') != core.STATUS_PENDING]
        if len(selected) != 1:
            self.txtInfo.Text = u'Выделите одну заметку, чтобы записать ответ / решение.'
            return
        self._answer(selected[0], close=not core.is_closed(selected[0]))

    def _answer(self, note, close):
        dlg = AnswerWindow(note, close)
        dlg.Owner = self
        dlg.ShowDialog()
        if dlg.answer is None:
            return
        status = core.STATUS_DONE if dlg.mark_done else None
        changes = {'answer': dlg.answer}
        if status:
            changes['status'] = status
        note_id, answer, user = note['id'], dlg.answer, self.ctx['user']
        self._apply([note], changes, lambda: core.set_answer(note_id, answer, status, user),
                    u'Не удалось записать решение')

    def _apply(self, notes, changes, send, fail_title):
        """Изменение видно в сводке сразу, а в таблицу уходит в фоне. Не прошло — откатывается.
        Пока изменения отправляются, окно не закрывается (закроется само, когда они уйдут)."""
        before = [dict((k, n.get(k)) for k in changes) for n in notes]
        for n in notes:
            n.update(changes)
        self.refresh()
        self._pending += 1
        self._notice(u'Сохранение в таблицу…')
        # если параллельно идёт загрузка из таблицы, её данные могут быть старше этого изменения
        override = {'ids': set(n.get('id') for n in notes), 'changes': changes, 'done_at': None}
        self._overrides.append(override)

        def done(result, error):
            self._pending -= 1
            override['done_at'] = time.time()
            if error is not None:
                self._overrides.remove(override)
                for n, old in zip(notes, before):
                    n.update(old)
                self.refresh()
            if not self._pending:
                self._notice(None)
                if self._close_when_done:
                    self.Close()
                    return
            if error is not None:
                forms.alert(error, title=fail_title)
        in_background(self, send, done)

    def on_closing(self, sender, e):
        if self._pending:
            e.Cancel = True
            self._close_when_done = True
            self._notice(u'Изменения ещё отправляются в таблицу — окно закроется, как только они сохранятся.')

    def on_show(self, sender, e):
        if self.uidoc is None or self.reminders_mode:
            return
        doc = self.uidoc.Document
        found, other_model, missing = List[ElementId](), 0, 0
        for n in self._selected():
            raw = [x for x in (n.get('elements') or u'').split(';') if x.strip()]
            if not raw:
                continue
            if core.short_file(n.get('file')) != core.short_file(self.ctx['file']):
                other_model += 1
                continue
            for x in raw:
                try:
                    eid = core.to_element_id(int(x))
                except ValueError:
                    continue
                if doc.GetElement(eid) is not None:
                    found.Add(eid)
                else:
                    missing += 1
        if found.Count == 0:
            msg = u'У выбранных заметок нет привязанных элементов в этой модели.'
            if other_model:
                msg = u'Элементы привязаны в другой модели проекта ({} шт.).'.format(other_model)
            elif missing:
                msg = u'Привязанные элементы удалены из модели.'
            self.txtInfo.Text = msg
            return
        self.Close()
        self.uidoc.Selection.SetElementIds(found)
        try:
            self.uidoc.ShowElements(found)
        except Exception:
            pass

    def on_view(self, sender, e):
        """Открыть вид или лист, на котором была создана заметка."""
        if self.uidoc is None or self.reminders_mode:
            return
        selected = self._selected()
        if len(selected) != 1:
            self.txtInfo.Text = u'Выделите одну заметку, чтобы открыть её вид или лист.'
            return
        note = selected[0]
        label = note.get('view') or u''
        if not label:
            self.txtInfo.Text = u'У заметки не записан вид.'
            return
        if core.short_file(note.get('file')) != core.short_file(self.ctx['file']):
            self.txtInfo.Text = u'Заметка создана в другой модели проекта: {} (вид «{}»).'.format(
                core.short_file(note.get('file')), label)
            return
        view = core.find_view(self.uidoc.Document, label)
        if view is None:
            self.txtInfo.Text = u'Вид «{}» не найден в модели — возможно, его переименовали или удалили.'.format(label)
            return
        self.Close()
        try:
            self.uidoc.ActiveView = view
        except Exception:
            self.uidoc.RequestViewChange(view)

    def on_reload(self, sender, e):
        if not self.btnRefresh.IsEnabled:
            return
        self.btnRefresh.IsEnabled = False
        self.Cursor = Cursors.AppStarting
        if not self.notes:
            self.txtInfo.Text = u'Загрузка заметок из таблицы…'
        self._notice(u'Обновление из таблицы…')
        key = self.ctx['key']
        started = time.time()

        def work():
            # очередь отдельно — чтобы в строке состояния было видно, на что ушло время
            try:
                core.flush_queue(20000, retry_timeout=True)
            except Exception:
                pass
            flushed = time.time()
            core.last_server_ms[0] = None
            # 20 с на попытку и один повтор: «зависший» у Google запрос дольше ждать бессмысленно —
            # новый обычно проходит за несколько секунд
            notes, online, error = core.load_notes(key, timeout_ms=20000, retry_timeout=True)
            timing = {'total': time.time() - started, 'queue': flushed - started,
                      'server': core.last_server_ms[0], 'started': started}
            return notes, online, error, timing
        in_background(self, work, self._loaded)

    def _loaded(self, result, error):
        self.btnRefresh.IsEnabled = True
        self.Cursor = None
        if error is not None:  # сбой вне load_notes — оставить то, что уже показано
            self._notice(error)
            return
        notes, online, error, timing = result
        self._load_timing = timing if online else None
        for o in self._overrides:
            if o['done_at'] is None or o['done_at'] > timing['started']:
                for n in notes:
                    if n.get('id') in o['ids']:
                        n.update(o['changes'])
        if self.reminders_mode:
            notes = core.reminders(notes, self.ctx['user'], self.settings.get('remind_days'))
        self.notes = notes
        self._notice(error or (u'Сохранение в таблицу…' if self._pending else None))
        self._ready = False
        self._fill_authors()
        self._ready = True
        self.refresh()
        if online and not self._settings_refreshed:
            # копию настроек команды обновляем отдельным запросом уже после показа заметок — их он не задерживает
            self._settings_refreshed = True
            in_background(self, lambda: core.get_settings(timeout_ms=30000), self._settings_loaded)

    def _settings_loaded(self, result, error):
        if error is None and result[1]:
            self.settings = result[0]
            self.btnSheet.IsEnabled = bool(self.settings.get('sheet_url'))

    def on_sheet(self, sender, e):
        url = self.settings.get('sheet_url')
        if url:
            open_url(url)


# ================================================================ ответ / решение

class AnswerWindow(forms.WPFWindow):
    def __init__(self, note, close):
        forms.WPFWindow.__init__(self, _xaml('answer.xaml'))
        self.answer = None  # None — отменено
        self.mark_done = False
        self.is_question = core.is_question(note)
        head = [x for x in (note.get('type'), note.get('section'), note.get('author')) if x]
        self.txtHead.Text = u'   ·   '.join(head)
        self.txtQuestion.Text = note.get('text') or u''
        self.txtAnswer.Text = note.get('answer') or u''
        self.chkClose.IsChecked = close
        if core.is_closed(note):
            self.chkClose.IsChecked = False
            self.chkClose.Visibility = Visibility.Collapsed
        if self.is_question:
            self.txtHint.Text = u'Это вопрос — закрыть его можно только с ответом.'
        _spellcheck(self.txtAnswer)
        self.btnSave.Click += self.on_save
        self.btnCancel.Click += lambda s, e: self.Close()
        self.PreviewKeyDown += self.on_key
        self.Loaded += lambda s, e: self.txtAnswer.Focus()

    def on_key(self, sender, e):
        if e.Key == Key.Enter and Keyboard.Modifiers == ModifierKeys.Control:
            e.Handled = True
            self.on_save(None, None)

    def on_save(self, sender, e):
        text = (self.txtAnswer.Text or u'').strip()
        close = bool(self.chkClose.IsChecked)
        if not text and (close or self.is_question):
            self.txtHint.Text = u'Напишите ответ / решение.'
            self.txtAnswer.Focus()
            return
        self.answer = text
        self.mark_done = close
        self.Close()


# ================================================================ настройка

class SetupWindow(forms.WPFWindow):
    def __init__(self, doc, settings):
        forms.WPFWindow.__init__(self, _xaml('setup.xaml'))
        self.saved = False
        self.doc = doc
        cfg = core.load_config()
        self.txtUrl.Text = cfg['url']
        self.txtToken.Text = cfg['token']

        self.params = core.list_project_params(doc)
        filled = [p for p in self.params if p['value']]
        self.txtAnalysis.Text = (
            u'В «Сведениях о проекте» этой модели {} параметров, заполнено {}. '
            u'Выберите, какой параметр — код проекта (по нему заметки разных моделей одного объекта '
            u'попадут в одну сводку) и какой — название.'
        ).format(len(self.params), len(filled))

        refs = [p['ref'] for p in self.params]
        extras = settings.get('extra_params') or self._suggest_extras()
        self.table = DataTable()
        for col in ('name', 'value', 'kind', 'ref', 'filled'):
            self.table.Columns.Add(col, STR)
        self.table.Columns.Add('extra', BOOL)
        for p in self.params:
            row = self.table.NewRow()
            row['name'] = p['name']
            row['value'] = p['value'] or u'— пусто —'
            row['kind'] = p['kind']
            row['ref'] = p['ref']
            row['filled'] = u'1' if p['value'] else u'0'
            row['extra'] = p['ref'] in extras
            self.table.Rows.Add(row)
        self.dg.ItemsSource = self.table.DefaultView

        self.key_refs = [core.FILE_KEY] + refs
        self.name_refs = [core.FILE_KEY] + refs
        labels = [u'{} (сейчас: {})'.format(core.FILE_KEY, core.file_key(doc))] + [
            u'{}   =   {}'.format(p['name'], p['value'] or u'(пусто)') for p in self.params]
        _fill(self.cmbKey, labels)
        _fill(self.cmbName, labels)
        self.cmbKey.SelectedIndex = self._index(self.key_refs, settings.get('key_param'),
                                                self._suggest(('PROJECT_NUMBER',), (u'шифр', u'код', u'номер')))
        self.cmbName.SelectedIndex = self._index(self.name_refs, settings.get('name_param'),
                                                 self._suggest(('PROJECT_NAME', 'PROJECT_BUILDING_NAME'), (u'наимен', u'назван')))

        self.cmbKey.SelectionChanged += self.update_preview
        self.cmbName.SelectionChanged += self.update_preview
        self.btnTest.Click += self.on_test
        self.lnkGuide.Click += lambda s, e: open_url(GUIDE_URL)
        self.lnkScript.Click += lambda s, e: open_url(SCRIPT_URL)
        self.btnSave.Click += self.on_save
        self.btnCancel.Click += lambda s, e: self.Close()
        self.update_preview()

    def _suggest(self, bips, words):
        """Сначала заполненный встроенный параметр, потом заполненный по ключевому слову, потом встроенный пустой."""
        for bip in bips:
            for p in self.params:
                if p['value'] and p['ref'].endswith(u'[{}]'.format(bip)):
                    return p['ref']
        for p in self.params:
            if p['value'] and any(w in p['name'].lower() for w in words):
                return p['ref']
        for p in self.params:
            if p['ref'].endswith(u'[{}]'.format(bips[0])):
                return p['ref']
        return core.FILE_KEY

    def _suggest_extras(self):
        wanted = ('[CLIENT_NAME]', '[PROJECT_STATUS]', '[PROJECT_ADDRESS]')
        return [p['ref'] for p in self.params if p['value'] and p['ref'].endswith(wanted)]

    @staticmethod
    def _index(refs, current, fallback):
        for value in (current, fallback):
            if value in refs:
                return refs.index(value)
        return 0

    def _ref(self, combo, refs):
        i = combo.SelectedIndex
        return refs[i] if 0 <= i < len(refs) else core.FILE_KEY

    def update_preview(self, *args):
        key_ref = self._ref(self.cmbKey, self.key_refs)
        key = core.read_param(self.doc, key_ref)
        if key:
            text = u'В этой модели код проекта = «{}».'.format(key)
        else:
            text = u'В этой модели код будет взят из имени файла: «{}».'.format(core.file_key(self.doc))
            if key_ref != core.FILE_KEY:
                text += u' Параметр пуст — лучше его заполнить, иначе заметки разных моделей одного объекта разойдутся.'
        self.txtPreview.Text = text

    def _save_connection(self):
        url = (self.txtUrl.Text or u'').strip()
        token = (self.txtToken.Text or u'').strip()
        if not url or not token:
            self.txtConn.Text = u'Укажите адрес и токен.'
            return False
        core.save_user_config(url, token)
        return True

    def on_test(self, sender, e):
        if not self._save_connection():
            return
        self.Cursor = Cursors.Wait
        try:
            started = time.time()
            resp = core.call('ping', timeout_ms=15000)
            self.txtConn.Text = u'✓ Связь есть, таблица «{}», ответ за {:.1f} с.'.format(
                resp.get('sheet') or u'', float(time.time() - started))
        except core.ApiError as ex:
            self.txtConn.Text = core.err_text(ex)
        finally:
            self.Cursor = None

    def on_save(self, sender, e):
        if not self._save_connection():
            return
        extras = [row['ref'] for row in self.table.Rows if row['extra'] == True]  # noqa: E712 — DBNull не равен True
        self.Cursor = Cursors.Wait
        try:
            core.save_mapping(self._ref(self.cmbKey, self.key_refs),
                              self._ref(self.cmbName, self.name_refs), extras)
        except core.ApiError as ex:
            self.txtStatus.Text = core.err_text(ex)
            return
        finally:
            self.Cursor = None
        self.saved = True
        self.Close()


# ================================================================ точки входа кнопок

def _project_doc(uidoc):
    if uidoc is None:
        forms.alert(u'Откройте модель проекта.')
        return None
    doc = uidoc.Document
    if doc.IsFamilyDocument:
        forms.alert(u'Заметки ведутся по проектам — откройте модель проекта, а не семейство.')
        return None
    return doc


@guarded
def run_setup(doc, settings=None):
    if settings is None:
        settings = core.get_settings_fast()
    win = SetupWindow(doc, settings)
    win.ShowDialog()
    return win.saved


@guarded
def run_new_note(uidoc):
    doc = _project_doc(uidoc)
    if doc is None:
        return
    if not core.is_configured():
        forms.alert(u'Сначала подключим Google Таблицу и посмотрим, что заполнено в «Сведениях о проекте».')
        if not run_setup(doc):
            return
    if core.has_cached_settings():
        # копия настроек — окно открывается сразу; свежие настройки и связь проверяются в фоне
        settings, online = core.get_settings(online=False)[0], None
    else:
        settings, online = core.get_settings()
    if not settings.get('key_param') and core.has_cached_settings():
        forms.alert(u'Первый запуск: посмотрим, что заполнено в «Сведениях о проекте», '
                    u'и выберем, по какому параметру различать проекты.')
        if run_setup(doc, settings):
            settings = core.get_settings(online=False)[0]

    ctx = core.get_context(doc, uidoc, settings)
    win = NoteWindow(ctx, settings, online)
    win.ShowDialog()
    if win.result:
        # не ждём таблицу: отправка идёт в фоне, Revit свободен сразу
        core.send_queue_detached()
        _balloon(u'Заметка сохранена и отправляется в таблицу.')


@guarded
def run_summary(uidoc):
    doc = _project_doc(uidoc)
    if doc is None:
        return
    if not core.is_configured():
        forms.alert(u'Подключение к таблице ещё не настроено — нажмите «Настройка».')
        return
    settings = core.get_settings_fast()
    ctx = core.get_context(doc, uidoc, settings)
    # окно открывается сразу с последней копией, свежие заметки подгружаются в фоне
    notes, _ = core.cached_notes(ctx['key'])
    SummaryWindow(ctx, settings, notes, uidoc=uidoc, load=True).ShowDialog()


def run_open_reminders(doc):
    """Вызывается хуком при открытии модели. Без сети и без настроек — молча выходит."""
    if doc is None or doc.IsFamilyDocument or getattr(doc, 'IsLinked', False):
        return
    if not core.is_configured() or not core.has_cached_settings():
        return
    settings = core.get_settings(online=False)[0]
    if not settings.get('remind_on_open', True):
        return
    ctx = core.get_context(doc, None, settings)

    # один раз за сеанс Revit на проект
    flag = u'pnotes_reminded_' + ctx['key']
    domain = System.AppDomain.CurrentDomain
    if domain.GetData(flag):
        return
    domain.SetData(flag, True)

    notes, online, error = core.load_notes(ctx['key'], timeout_ms=5000)
    if not online:
        return
    due = core.reminders(notes, ctx['user'], settings.get('remind_days'))
    if due:
        SummaryWindow(ctx, settings, due, reminders_mode=True).ShowDialog()
