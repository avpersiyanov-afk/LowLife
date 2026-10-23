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

from lowlife import email_tasks_settings, email_ai, email_tasks_excel, email_tasks_run

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


class _Progress(object):
    """Окно прогресса pyRevit для email_tasks_run.run."""

    def __init__(self, pb):
        self._pb = pb

    def title(self, text):
        self._pb.title = text

    def progress(self, done, total):
        self._indeterminate(False)
        self._pb.update_progress(done, total)

    def busy(self):
        self._indeterminate(True)

    def cancelled(self):
        # Дать окну прогресса перерисоваться и обработать «Отмена»
        try:
            Application.DoEvents()
        except Exception:
            pass
        return self._pb.cancelled

    def _indeterminate(self, value):
        # Свойство есть не во всех версиях pyRevit
        try:
            self._pb.indeterminate = value
        except Exception:
            pass


output = script.get_output()

with forms.ProgressBar(title=u"Чтение почты…", cancellable=True) as pb:
    result = email_tasks_run.run(settings, prompt_text, engine, _Progress(pb), email_tasks_excel,
                                 test_emails_file=TEST_EMAILS_FILE)


# --- Итоги (после закрытия окна прогресса, чтобы сообщения не прятались за ним)
if result.cancelled:
    forms.alert(u"Отменено пользователем.", exitscript=True)

if result.fatal_error:
    forms.alert(result.fatal_error, title=u"Задачи из почты", exitscript=True)

if not result.emails:
    forms.alert(result.no_emails_text, exitscript=True)

if result.batch_errors and not result.rows:
    forms.alert(
        u"Не удалось получить задачи:\n\n" + u"\n\n".join(result.batch_errors)[:3000],
        title=u"Задачи из почты")

output.print_md(u"## Задачи из почты — {}".format(
    email_tasks_run.fmt_date(datetime.datetime.now(), with_time=True)))
output.print_md(u"Папка: **{}**, писем разобрано: **{}**, задач найдено: **{}**. ИИ: {}.".format(
    result.folder_name, len(result.emails), len(result.rows), engine.description))
if result.read_warning:
    output.print_md(u"> ⚠ " + result.read_warning)

if result.rows:
    output.print_table(table_data=email_tasks_run.table(result.rows),
                       columns=email_tasks_run.TABLE_COLUMNS)
else:
    output.print_md(u"Задач, требующих ваших действий, не найдено.")

for warning in result.excel_warnings:
    output.print_md(u"> ⚠ " + warning)

if result.batch_errors:
    output.print_md(u"### Ошибки")
    for err in result.batch_errors:
        output.print_md(u"- " + err.replace(u"\n", u" "))

if result.excel_error:
    output.print_md(u"> ⚠ " + result.excel_error.replace(u"\n", u" "))
    forms.alert(result.excel_error + u"\n\nСписок задач — в окне вывода pyRevit.",
                title=u"Задачи из почты")

if result.excel_path:
    output.print_md(u"Сохранено в Excel: `{}` (файл открыт).".format(result.excel_path))
