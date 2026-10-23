# -*- coding: utf-8 -*-
"""
«Задачи из почты» — отдельное приложение для тех, у кого нет Revit. Делает
то же, что кнопка Mail.panel/EmailTasks в Revit, на том же коде
(lib/lowlife/email_*): читает «Входящие» классического Outlook, отдаёт
письма ИИ (Claude Code / Codex CLI / Anthropic API / OpenAI API) и пишет
задачи в Excel.

Запуск из репозитория (Python 3 на Windows, pip install -r requirements.txt):

    python apps\\mail\\lowlife_mail.py

Сборка в один .exe — build.bat (PyInstaller, lowlife_mail.spec); её же
делает GitHub Actions (.github/workflows/mail-app.yml).

    LowLifeMail.exe --self-test [папка]   проверка сборки без Outlook и ИИ:
                                          тестовые письма → .xlsx, код выхода 0
"""

import io
import json
import os
import sys
import tempfile
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
FROZEN = getattr(sys, "frozen", False)

if FROZEN:
    DATA_DIR = os.path.join(sys._MEIPASS, "data")  # noqa — есть только в сборке PyInstaller
else:
    REPO = os.path.dirname(os.path.dirname(HERE))
    sys.path.insert(0, os.path.join(REPO, "lib"))
    DATA_DIR = os.path.join(REPO, "LowLife.tab", "Mail.panel", "EmailTasks.pushbutton")

PROMPT_FILE = os.path.join(DATA_DIR, "prompt.txt")
TEST_EMAILS_FILE = os.path.join(DATA_DIR, "test_emails.json")
ICON_FILE = os.path.join(DATA_DIR, "icon.png")


def _setup_settings_folder():
    """Настройки — рядом с настройками кнопки в Revit, если она тут уже
    настроена, иначе в %APPDATA%\\LowLife (см. email_app_core)."""
    from lowlife import email_app_core, settings_core
    settings_core.SETTINGS_FOLDER_NAME = email_app_core.settings_folder_name(os.environ.get("APPDATA"))


def _read_default_prompt():
    try:
        with io.open(PROMPT_FILE, "r", encoding="utf-8") as f:
            return f.read()
    except Exception:
        return u""


# ---------------------------------------------------------------- self-test

class _QuietProgress(object):
    def title(self, text):
        pass

    def progress(self, done, total):
        pass

    def busy(self):
        pass

    def cancelled(self):
        return False


class _FakeEngine(object):
    """Вместо ИИ: по задаче на каждое из первых трёх писем пачки."""
    name = u"self-test"
    description = u"self-test, без ИИ"

    def run(self, request_text, tick=None):
        import re
        ids = [int(x) for x in re.findall(u"email_id=(\\d+)", request_text)][:3]
        return json.dumps({"tasks": [
            {"email_id": i, "task": u"Проверочная задача {}".format(i), "requester": u"Тест",
             "deadline": None, "priority": u"высокий" if i == 1 else u"средний", "comment": u""}
            for i in ids]})


class _TempExcel(object):
    def __init__(self, folder):
        from lowlife import email_tasks_xlsx
        self._xlsx = email_tasks_xlsx
        self.ExcelError = email_tasks_xlsx.ExcelError
        self._folder = folder

    def default_output_path(self):
        return os.path.join(self._folder, u"self-test.xlsx")

    def save_tasks(self, rows, path):
        return self._xlsx.save_tasks(rows, path, open_file=False)


def self_test(folder=None):
    """Проверяет, что в сборку попало всё нужное. Возвращает код выхода."""
    folder = folder or tempfile.mkdtemp(prefix=u"lowlife-mail-")
    if not os.path.isdir(folder):
        os.makedirs(folder)
    log = os.path.join(folder, u"self-test.log")
    lines = []
    code = 0
    try:
        from lowlife import email_ai_net, email_outlook, email_tasks_run  # noqa: F401
        lines.append(u"ИИ: {}".format(email_ai_net.run_process.__module__))
        if os.name == "nt":
            import win32com.client  # noqa: F401 — Outlook
            lines.append(u"pywin32: ok")
        settings = {"days": 3, "unread_only": False, "subfolder": u"", "include_subfolders": True,
                    "test_mode": True}
        result = email_tasks_run.run(settings, _read_default_prompt() or u"prompt", _FakeEngine(),
                                     _QuietProgress(), _TempExcel(folder), test_emails_file=TEST_EMAILS_FILE)
        lines.append(u"Писем: {}, задач: {}, файл: {}".format(
            len(result.emails), len(result.rows), result.excel_path))
        if result.fatal_error or result.excel_error or not result.excel_path or not result.rows:
            lines.append(u"ОШИБКА: {}".format(result.fatal_error or result.excel_error or u"нет файла"))
            code = 1
        if not os.path.isfile(ICON_FILE):
            lines.append(u"ОШИБКА: нет значка {}".format(ICON_FILE))
            code = 1
    except Exception:
        lines.append(traceback.format_exc())
        code = 1
    lines.append(u"OK" if code == 0 else u"FAILED")
    with io.open(log, "w", encoding="utf-8") as f:
        f.write(u"\n".join(lines) + u"\n")
    if sys.stdout is not None:  # у оконной сборки консоли нет
        print(u"\n".join(lines))
    return code


# ---------------------------------------------------------------------- GUI

def _dpi_aware():
    if os.name != "nt":
        return
    try:
        import ctypes
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass


def main(argv):
    _setup_settings_folder()
    if len(argv) > 1 and argv[1] == u"--self-test":
        return self_test(argv[2] if len(argv) > 2 else None)

    _dpi_aware()
    import tkinter as tk
    from tkinter import messagebox

    root = tk.Tk()
    try:
        import mail_window
        mail_window.MainWindow(root, _read_default_prompt(), TEST_EMAILS_FILE, ICON_FILE)
    except Exception:
        messagebox.showerror(u"Задачи из почты", u"Не удалось запустить программу:\n\n" + traceback.format_exc())
        root.destroy()
        return 1
    root.mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
