# apps/mail — «Задачи из почты» без Revit

Отдельное приложение `LowLifeMail.exe` для тех, у кого нет Revit:
инструкция для пользователя — [docs/email-tasks-app.md](../../docs/email-tasks-app.md).
Кнопка в Revit (`LowLife.tab/Mail.panel/EmailTasks`) остаётся; обе
работают на одном коде.

Папка `apps/` лежит вне `LowLife.tab`, поэтому pyRevit её не загружает.

## Что общее с кнопкой

Весь сценарий — `lib/lowlife/email_tasks_run.run(...)`: чтение писем,
разбор ИИ пачками, запись Excel. Отличаются только окна и то, через что
идут Outlook, процессы/HTTP и Excel:

| | Revit (IronPython, .NET) | Приложение (CPython 3) |
|---|---|---|
| Окна | WPF / pyRevit (`script.py`, `email_tasks_settings.py`, `ai_settings.py`) | tkinter (`mail_window.py`, `mail_settings_window.py`) |
| Outlook | `email_outlook` через `System.Activator` | `email_outlook` через pywin32 |
| claude/codex, HTTP API | `email_ai_clr` | `email_ai_std` (subprocess, urllib) |
| Excel | `email_tasks_excel` (COM Excel) | `email_tasks_xlsx` (openpyxl) |

`email_ai_net` и `email_outlook` сами выбирают вариант: есть `clr` — .NET,
нет — stdlib/pywin32. Настройки (`email_tasks_settings_core`,
`ai_settings_core`) — без окон, общие. Промпт и тестовые письма берутся
из папки кнопки (`prompt.txt`, `test_emails.json`), значок — её `icon.png`.

## Запуск из исходников

Windows, Python 3.12:

```bat
python -m pip install -r apps\mail\requirements.txt
python apps\mail\lowlife_mail.py
```

## Сборка .exe

```bat
apps\mail\build.bat
```

Ставит зависимости (`requirements-build.txt`), собирает PyInstaller'ом по
`lowlife_mail.spec` один файл `dist\LowLifeMail.exe` (без консоли) и
проверяет его: `LowLifeMail.exe --self-test <папка>` прогоняет тестовые
письма через весь сценарий с подставным ИИ и пишет `.xlsx` — код выхода 0
и `self-test.log` в папке.

То же делает GitHub Actions (`.github/workflows/mail-app.yml`) на каждое
изменение приложения или `lib/lowlife/email_*` в `main` и в PR: `.exe` —
в артефактах запуска.

## Выпуск для пользователей

Тег `mail-v*` публикует `.exe` в Releases репозитория:

```bash
git tag mail-v1.0
git push origin mail-v1.0
```

Или без тега в git: GitHub → Actions → «Задачи из почты (exe)» → Run
workflow на `main`, поле «Тег выпуска» — `mail-v1.0`; релиз создаст тег сам.

Ссылку на Releases можно давать коллегам — см. docs/email-tasks-app.md.
