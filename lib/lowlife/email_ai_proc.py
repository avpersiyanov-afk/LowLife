# -*- coding: utf-8 -*-
"""
Общие для обеих обвязок ИИ (email_ai_clr — .NET в Revit, email_ai_std —
stdlib в отдельном приложении «Задачи из почты») функции без .NET: поиск
программы (claude/codex), кавычки командной строки Windows, временная
папка запуска.
"""

try:
    unicode  # noqa: F821 — IronPython/Python 2
except NameError:  # Python 3
    unicode = str


import os

TIMEOUT_SECONDS = 180


def find_executable(configured_path, names, extra_candidates=()):
    """
    Путь к программе или None. Порядок: путь из настроек (файл или папка) →
    PATH → extra_candidates. PATH процесса Revit может быть старым (программу
    поставили после запуска Revit), поэтому известные папки установки
    передаются отдельно.
    """
    configured_path = (configured_path or u"").strip().strip('"')
    if configured_path:
        path = os.path.expandvars(configured_path)
        if os.path.isdir(path):
            for name in names:
                if os.path.isfile(os.path.join(path, name)):
                    return os.path.join(path, name)
            return None
        return path if os.path.isfile(path) else None

    candidates = []
    for folder in (os.environ.get("PATH") or u"").split(os.pathsep):
        folder = folder.strip().strip('"')
        if folder:
            candidates.extend(os.path.join(folder, name) for name in names)
    candidates.extend(extra_candidates)
    for path in candidates:
        if os.path.isfile(path):
            return path
    return None


def quote(arg):
    """Аргумент командной строки Windows (правила CommandLineToArgvW)."""
    arg = unicode(arg)
    if arg and not any(ch in arg for ch in u' \t"'):
        return arg
    result = u'"'
    backslashes = 0
    for ch in arg:
        if ch == u"\\":
            backslashes += 1
        elif ch == u'"':
            result += u"\\" * (backslashes * 2 + 1) + u'"'
            backslashes = 0
        else:
            result += u"\\" * backslashes + ch
            backslashes = 0
    result += u"\\" * (backslashes * 2) + u'"'
    return result


def command_line(exe_path, args, comspec=None):
    """(программа, строка аргументов) для запуска: npm-шим (.cmd/.bat)
    запускается через cmd.exe, остальное — напрямую."""
    arguments = u" ".join(quote(a) for a in args)
    if os.path.splitext(exe_path)[1].lower() in (u".cmd", u".bat"):
        return (comspec or os.environ.get("ComSpec") or u"cmd.exe",
                u'/d /s /c "{} {}"'.format(quote(exe_path), arguments))
    return exe_path, arguments


def work_dir():
    """Временная папка запуска: программа не подхватит CLAUDE.md/AGENTS.md
    случайного рабочего каталога Revit."""
    folder = os.path.join(os.environ.get("TEMP") or os.path.expanduser("~"), u"LowLifeEmailTasks")
    if not os.path.isdir(folder):
        try:
            os.makedirs(folder)
        except Exception:
            pass
    return folder
