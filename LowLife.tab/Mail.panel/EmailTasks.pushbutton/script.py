# -*- coding: utf-8 -*-
__title__ = u"Задачи\nиз почты"
__doc__ = (
    u"Разбирает «Входящие» классического Outlook за последние N дней и "
    u"составляет список задач в Excel (Документы\\Задачи из почты). Письма "
    u"анализирует Claude или ChatGPT — через приложение (Claude Code / Codex "
    u"CLI, под вашей подпиской) или по ключу API. Почта только читается: "
    u"ничего не отправляется, не помечается прочитанным и не перемещается.\n\n"
    u"Shift+клик — настройки: способ подключения ИИ (со ссылками на "
    u"инструкции), модель, период, только непрочитанные, подпапка, промпт, "
    u"тестовый режим."
)
__author__ = "Pipers"
__context__ = "zero-doc"

import os
import io
import datetime

import clr
clr.AddReference("System.Windows.Forms")
from System.Windows.Forms import Application

from pyrevit import forms, script, EXEC_PARAMS

from lowlife import email_tasks_core as core
from lowlife import email_tasks_settings, email_ai, email_outlook, email_tasks_excel

BUNDLE_DIR = os.path.dirname(__file__)
PROMPT_FILE = os.path.join(BUNDLE_DIR, "prompt.txt")
TEST_EMAILS_FILE = os.path.join(BUNDLE_DIR, "test_emails.json")

try:
    config_mode = bool(EXEC_PARAMS.config_mode)
except Exception:
    config_mode = False

def _read_default_prompt():
    try:
        with io.open(PROMPT_FILE, "r", encoding="utf-8") as f:
            return f.read()
    except Exception:
        return u""


default_prompt = _read_default_prompt()

if config_mode:
    saved = email_tasks_settings.edit_interactive(default_prompt)
    forms.alert(u"Настройки сохранены." if saved else u"Отменено, настройки не изменены.")
    script.exit()


settings = email_tasks_settings.load()

prompt_text = email_tasks_settings.effective_prompt(settings, default_prompt)
if not prompt_text.strip():
    forms.alert(u"Промпт пуст: в настройках нет своего текста, а стандартный "
                u"файл не прочитался:\n{}\n\nВпишите промпт в настройках "
                u"(Shift+клик по кнопке).".format(PROMPT_FILE),
                exitscript=True)

try:
    engine = email_ai.prepare(settings)
except email_ai.AIError as ex:
    forms.alert(ex.message, title=u"Задачи из почты", exitscript=True)


def _pump():
    """Дать окну прогресса перерисоваться и обработать «Отмена»."""
    try:
        Application.DoEvents()
    except Exception:
        pass


def _set_indeterminate(pb, value):
    # Свойство есть не во всех версиях pyRevit
    try:
        pb.indeterminate = value
    except Exception:
        pass


def _fmt_date(value, with_time=False):
    if value is None:
        return u""
    return value.strftime("%d.%m.%Y %H:%M" if with_time else "%d.%m.%Y")


def _save_raw_answer(part, text):
    folder = os.path.join(os.environ.get("TEMP") or os.path.expanduser("~"), u"LowLifeEmailTasks")
    if not os.path.isdir(folder):
        os.makedirs(folder)
    path = os.path.join(folder, u"answer_{}_part{}.txt".format(
        datetime.datetime.now().strftime("%Y%m%d_%H%M%S"), part))
    with io.open(path, "w", encoding="utf-8") as f:
        f.write(text)
    return path


output = script.get_output()
today = datetime.date.today()
emails = []
folder_name = u""
read_warning = None
fatal_error = None
batch_errors = []
rows = []
cancelled = False

with forms.ProgressBar(title=u"Чтение почты…", cancellable=True) as pb:
    # --- 1. Чтение почты
    _set_indeterminate(pb, True)
    _pump()
    if settings["test_mode"]:
        folder_name = u"ТЕСТОВЫЙ РЕЖИМ: test_emails.json"
        try:
            emails = core.load_test_emails(TEST_EMAILS_FILE)
        except Exception as ex:
            fatal_error = u"Не удалось прочитать тестовые письма:\n{}\n\n{}".format(TEST_EMAILS_FILE, ex)
    else:
        def read_tick(count):
            pb.title = u"Чтение почты… писем: " + unicode(count)
            pb.update_progress(0, 1)
            _pump()
            return pb.cancelled
        try:
            emails, folder_name, read_warning = email_outlook.read_inbox(
                settings["days"], settings["unread_only"], settings["subfolder"],
                include_subfolders=settings["include_subfolders"], tick=read_tick)
        except email_outlook.Cancelled:
            cancelled = True
        except email_outlook.OutlookError as ex:
            fatal_error = ex.message
        except Exception as ex:
            fatal_error = u"Ошибка чтения почты из Outlook:\n{}".format(ex)

    # --- 2. Анализ в ИИ, пачками
    if emails and not fatal_error and not cancelled:
        emails_by_id = dict((e["id"], e) for e in emails)
        batches = core.make_batches(emails)
        total = len(batches)
        for part, batch in enumerate(batches, start=1):
            pb.title = u"Анализ писем в {}: часть {} из {} (писем: {})".format(
                engine.name, part, total, len(batch))
            pb.update_progress(part - 1, total)
            _set_indeterminate(pb, True)
            _pump()

            def ai_tick():
                _pump()
                return pb.cancelled

            request = core.build_request(prompt_text, batch, today)
            try:
                answer = engine.run(request, tick=ai_tick)
            except email_ai.Cancelled:
                cancelled = True
                break
            except email_ai.AIError as ex:
                text = ex.message
                if ex.details:
                    text += u"\n\nПодробности:\n" + ex.details[:1500]
                if ex.fatal:
                    fatal_error = text
                    break
                batch_errors.append(u"Часть {} из {}: {}".format(part, total, text))
                continue

            try:
                tasks = core.parse_tasks_json(answer)
            except core.ParseError as ex:
                raw_path = _save_raw_answer(part, answer)
                batch_errors.append(
                    u"Часть {} из {}: не удалось разобрать ответ {} ({}). "
                    u"Ответ сохранён: {}".format(part, total, engine.name, ex, raw_path))
                continue
            rows.extend(core.normalize_task(t, emails_by_id) for t in tasks)

        _set_indeterminate(pb, False)
        pb.update_progress(total, total)

    # --- 3. Excel
    rows = core.sort_rows([r for r in rows if r["task"]])
    excel_path = None
    excel_warnings = []
    excel_error = None
    if rows and not fatal_error and not cancelled:
        pb.title = u"Сохранение в Excel…"
        _set_indeterminate(pb, True)
        _pump()
        try:
            excel_path = email_tasks_excel.default_output_path()
            excel_warnings = email_tasks_excel.save_tasks(rows, excel_path)
        except email_tasks_excel.ExcelError as ex:
            excel_error = ex.message
            excel_path = None
        except Exception as ex:
            excel_error = u"Не удалось сохранить Excel: {}".format(ex)
            excel_path = None


# --- Итоги (после закрытия окна прогресса, чтобы сообщения не прятались за ним)
if cancelled:
    forms.alert(u"Отменено пользователем.", exitscript=True)

if fatal_error:
    forms.alert(fatal_error, title=u"Задачи из почты", exitscript=True)

if not emails:
    period = u"{} дн.".format(settings["days"])
    extra = u", только непрочитанные" if settings["unread_only"] else u""
    forms.alert(u"Нет писем за период ({}{}) в папке:\n{}".format(period, extra, folder_name or u"Входящие"),
                exitscript=True)

if batch_errors and not rows:
    forms.alert(
        u"Не удалось получить задачи:\n\n" + u"\n\n".join(batch_errors)[:3000],
        title=u"Задачи из почты")

output.print_md(u"## Задачи из почты — {}".format(_fmt_date(datetime.datetime.now(), with_time=True)))
output.print_md(u"Папка: **{}**, писем разобрано: **{}**, задач найдено: **{}**. ИИ: {}.".format(
    folder_name, len(emails), len(rows), engine.description))
if read_warning:
    output.print_md(u"> ⚠ " + read_warning)

if rows:
    table = []
    for i, row in enumerate(rows, start=1):
        table.append([
            i,
            row["task"],
            row["requester"],
            _fmt_date(row["deadline"]) or u"—",
            row["priority"],
            row["comment"],
            row["subject"],
            _fmt_date(row["received"], with_time=True),
        ])
    output.print_table(
        table_data=table,
        columns=[u"№", u"Задача", u"Кто просит", u"Срок", u"Приоритет",
                 u"Комментарий", u"Тема письма", u"Дата письма"],
    )
else:
    output.print_md(u"Задач, требующих ваших действий, не найдено.")

for warning in excel_warnings:
    output.print_md(u"> ⚠ " + warning)

if batch_errors:
    output.print_md(u"### Ошибки")
    for err in batch_errors:
        output.print_md(u"- " + err.replace(u"\n", u" "))

if excel_error:
    output.print_md(u"> ⚠ " + excel_error.replace(u"\n", u" "))
    forms.alert(excel_error + u"\n\nСписок задач — в окне вывода pyRevit.",
                title=u"Задачи из почты")

if excel_path:
    output.print_md(u"Сохранено в Excel: `{}` (файл открыт).".format(excel_path))
