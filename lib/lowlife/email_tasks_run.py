# -*- coding: utf-8 -*-
"""
Сценарий «Задач из почты» целиком — чтение писем, разбор ИИ пачками,
запись в Excel — общий для кнопки в Revit (Mail.panel/EmailTasks) и
отдельного приложения (apps/mail). Окна у них разные, поэтому окно
прогресса передаётся объектом с методами:

    title(text)            подпись окна прогресса
    progress(done, total)  полоса с долей (done из total)
    busy()                 полоса «в процессе» без доли
    cancelled()            дать окну перерисоваться; True — нажата «Отмена»

а запись в Excel — модулем (email_tasks_excel в Revit, email_tasks_xlsx в
приложении) с default_output_path(), save_tasks(rows, path) и ExcelError.
Итоги (сообщения, таблица) показывает сам вызывающий по RunResult.
"""

try:
    unicode  # noqa: F821 — IronPython/Python 2
except NameError:  # Python 3
    unicode = str


import datetime
from lowlife.i18n import tr, N_
import io
import os

from lowlife import email_ai, email_outlook
from lowlife import email_tasks_core as core

TABLE_COLUMNS = [u"№", N_(u"Задача"), N_(u"Кто просит"), N_(u"Срок"), N_(u"Приоритет"),
                 N_(u"Комментарий"), N_(u"Тема письма"), N_(u"Дата письма")]


class RunResult(object):
    def __init__(self):
        self.emails = []
        self.folder_name = u""
        self.read_warning = None
        self.fatal_error = None
        self.batch_errors = []
        self.rows = []
        self.cancelled = False
        self.excel_path = None
        self.excel_warnings = []
        self.excel_error = None
        self.period = u""  # «3 дн., только непрочитанные» — для сообщения «нет писем»

    @property
    def no_emails_text(self):
        return tr(u"Нет писем за период ({}) в папке:\n{}").format(
            self.period, self.folder_name or tr(u"Входящие"))

    def describe(self, engine):
        return tr(u"Папка: {}, писем разобрано: {}, задач найдено: {}. ИИ: {}.").format(
            self.folder_name, len(self.emails), len(self.rows), engine.description)


def fmt_date(value, with_time=False):
    if value is None:
        return u""
    return value.strftime("%d.%m.%Y %H:%M" if with_time else "%d.%m.%Y")


def table(rows):
    """Строки для показа на экране (колонки TABLE_COLUMNS)."""
    return [[i, row["task"], row["requester"], fmt_date(row["deadline"]) or u"—",
             row["priority"], row["comment"], row["subject"], fmt_date(row["received"], with_time=True)]
            for i, row in enumerate(rows, start=1)]


def save_raw_answer(part, text):
    """Ответ ИИ, который не удалось разобрать, — в файл для разбора вручную."""
    folder = os.path.join(os.environ.get("TEMP") or os.path.expanduser("~"), u"LowLifeEmailTasks")
    if not os.path.isdir(folder):
        os.makedirs(folder)
    path = os.path.join(folder, u"answer_{}_part{}.txt".format(
        datetime.datetime.now().strftime("%Y%m%d_%H%M%S"), part))
    with io.open(path, "w", encoding="utf-8") as f:
        f.write(text)
    return path


def run(settings, prompt_text, engine, progress, excel, test_emails_file=None, today=None):
    """Весь разбор; возвращает RunResult. Исключения чтения/ИИ/Excel
    превращаются в поля результата, чтобы окно прогресса закрылось штатно."""
    result = RunResult()
    extra = tr(u", только непрочитанные") if settings["unread_only"] else u""
    result.period = tr(u"{} дн.{}").format(settings["days"], extra)
    today = today or datetime.date.today()

    _read(settings, progress, result, test_emails_file)
    if result.emails and not result.fatal_error and not result.cancelled:
        _analyze(prompt_text, engine, progress, result, today)

    result.rows = core.sort_rows([r for r in result.rows if r["task"]])
    if result.rows and not result.fatal_error and not result.cancelled:
        progress.title(tr(u"Сохранение в Excel…"))
        progress.busy()
        progress.cancelled()
        try:
            result.excel_path = excel.default_output_path()
            result.excel_warnings = excel.save_tasks(result.rows, result.excel_path) or []
        except excel.ExcelError as ex:
            result.excel_error = ex.message
            result.excel_path = None
        except Exception as ex:
            result.excel_error = tr(u"Не удалось сохранить Excel: {}").format(ex)
            result.excel_path = None
    return result


def _read(settings, progress, result, test_emails_file):
    progress.title(tr(u"Чтение почты…"))
    progress.busy()
    progress.cancelled()
    if settings["test_mode"]:
        result.folder_name = tr(u"ТЕСТОВЫЙ РЕЖИМ: test_emails.json")
        try:
            result.emails = core.load_test_emails(test_emails_file)
        except Exception as ex:
            result.fatal_error = tr(u"Не удалось прочитать тестовые письма:\n{}\n\n{}").format(
                test_emails_file, ex)
        return

    def read_tick(count):
        progress.title(tr(u"Чтение почты… писем: ") + unicode(count))
        return progress.cancelled()

    try:
        result.emails, result.folder_name, result.read_warning = email_outlook.read_inbox(
            settings["days"], settings["unread_only"], settings["subfolder"],
            include_subfolders=settings["include_subfolders"], tick=read_tick)
    except email_outlook.Cancelled:
        result.cancelled = True
    except email_outlook.OutlookError as ex:
        result.fatal_error = ex.message
    except Exception as ex:
        result.fatal_error = tr(u"Ошибка чтения почты из Outlook:\n{}").format(ex)


def _analyze(prompt_text, engine, progress, result, today):
    emails_by_id = dict((e["id"], e) for e in result.emails)
    batches = core.make_batches(result.emails)
    total = len(batches)
    for part, batch in enumerate(batches, start=1):
        progress.title(tr(u"Анализ писем в {}: часть {} из {} (писем: {})").format(
            engine.name, part, total, len(batch)))
        progress.progress(part - 1, total)
        progress.busy()
        progress.cancelled()

        request = core.build_request(prompt_text, batch, today)
        try:
            answer = engine.run(request, tick=progress.cancelled)
        except email_ai.Cancelled:
            result.cancelled = True
            return
        except email_ai.AIError as ex:
            text = ex.message
            if ex.details:
                text += tr(u"\n\nПодробности:\n") + ex.details[:1500]
            if ex.fatal:
                result.fatal_error = text
                return
            result.batch_errors.append(tr(u"Часть {} из {}: {}").format(part, total, text))
            continue

        try:
            tasks = core.parse_tasks_json(answer)
        except core.ParseError as ex:
            raw_path = save_raw_answer(part, answer)
            result.batch_errors.append(
                tr(u"Часть {} из {}: не удалось разобрать ответ {} ({}). "
                u"Ответ сохранён: {}").format(part, total, engine.name, ex, raw_path))
            continue
        result.rows.extend(core.normalize_task(t, emails_by_id) for t in tasks)

    progress.progress(total, total)
