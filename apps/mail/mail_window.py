# -*- coding: utf-8 -*-
"""Главное окно приложения «Задачи из почты»: запуск разбора, прогресс,
таблица найденных задач, сообщения. Вся работа — lowlife.email_tasks_run,
та же, что у кнопки в Revit."""

import datetime
import os
import tkinter as tk
from tkinter import messagebox, ttk

from lowlife import email_ai, email_tasks_run, email_tasks_xlsx
from lowlife import email_tasks_settings_core as settings_core
from lowlife.email_app_core import app_text

import mail_settings_window

TITLE = u"Задачи из почты"
# Ширины колонок таблицы (TABLE_COLUMNS), в пикселях
COLUMN_WIDTHS = [36, 360, 150, 80, 80, 220, 220, 115]


class _Progress(object):
    """Полоса прогресса окна для email_tasks_run.run; cancelled() даёт окну
    перерисоваться (весь разбор идёт в потоке окна, как у кнопки в Revit)."""

    def __init__(self, window):
        self._window = window

    def title(self, text):
        self._window.status.set(text)

    def progress(self, done, total):
        bar = self._window.bar
        bar.stop()
        bar.configure(mode=u"determinate", maximum=max(total, 1), value=done)

    def busy(self):
        bar = self._window.bar
        if str(bar.cget(u"mode")) != u"indeterminate":
            bar.configure(mode=u"indeterminate")
            bar.start(15)

    def cancelled(self):
        self._window.root.update()
        return self._window.cancel_requested


class MainWindow(object):
    def __init__(self, root, default_prompt, test_emails_file, icon_file=None):
        self.root = root
        self.default_prompt = default_prompt
        self.test_emails_file = test_emails_file
        self.running = False
        self.cancel_requested = False
        self.close_after_run = False  # окно закрыли во время разбора
        self.excel_path = None
        self.rows = []

        root.title(TITLE)
        root.geometry(u"1180x680")
        root.minsize(760, 480)
        if icon_file and os.path.isfile(icon_file):
            try:
                self._icon = tk.PhotoImage(file=icon_file)
                root.iconphoto(True, self._icon)
            except tk.TclError:
                pass
        root.protocol(u"WM_DELETE_WINDOW", self.on_close)

        outer = ttk.Frame(root, padding=12)
        outer.pack(fill=tk.BOTH, expand=True)

        ttk.Label(outer, text=TITLE, font=(u"Segoe UI", 14, u"bold")).pack(anchor=tk.W)
        intro = ttk.Label(outer, foreground=u"gray", text=(
            u"Разбирает «Входящие» классического Outlook и составляет список задач в Excel "
            u"(Документы\\Задачи из почты). Почта только читается: ничего не отправляется, "
            u"не помечается прочитанным и не перемещается."))
        intro.pack(anchor=tk.W, fill=tk.X, pady=(2, 8))
        intro.bind(u"<Configure>", lambda e: intro.configure(wraplength=max(e.width - 4, 200)))

        self.summary = tk.StringVar()
        ttk.Label(outer, textvariable=self.summary).pack(anchor=tk.W)

        buttons = ttk.Frame(outer)
        buttons.pack(fill=tk.X, pady=(8, 6))
        self.run_btn = ttk.Button(buttons, text=u"Разобрать почту", command=self.on_run)
        self.run_btn.pack(side=tk.LEFT)
        self.cancel_btn = ttk.Button(buttons, text=u"Отмена", command=self.on_cancel, state=tk.DISABLED)
        self.cancel_btn.pack(side=tk.LEFT, padx=(6, 0))
        self.settings_btn = ttk.Button(buttons, text=u"Настройки", command=self.on_settings)
        self.settings_btn.pack(side=tk.LEFT, padx=(6, 0))
        self.folder_btn = ttk.Button(buttons, text=u"Открыть папку", command=self.on_open_folder)
        self.folder_btn.pack(side=tk.RIGHT)
        self.excel_btn = ttk.Button(buttons, text=u"Открыть Excel", command=self.on_open_excel,
                                    state=tk.DISABLED)
        self.excel_btn.pack(side=tk.RIGHT, padx=(0, 6))

        self.status = tk.StringVar(value=u"Готово к запуску.")
        ttk.Label(outer, textvariable=self.status).pack(anchor=tk.W)
        self.bar = ttk.Progressbar(outer, mode=u"determinate")
        self.bar.pack(fill=tk.X, pady=(2, 8))

        panes = ttk.PanedWindow(outer, orient=tk.VERTICAL)
        panes.pack(fill=tk.BOTH, expand=True)

        table_frame = ttk.Frame(panes)
        columns = [u"c{}".format(i) for i in range(len(email_tasks_run.TABLE_COLUMNS))]
        self.table = ttk.Treeview(table_frame, columns=columns, show=u"headings", selectmode=u"browse")
        for col, title, width in zip(columns, email_tasks_run.TABLE_COLUMNS, COLUMN_WIDTHS):
            self.table.heading(col, text=title)
            self.table.column(col, width=width, minwidth=30, stretch=(title == u"Задача"))
        scroll_y = ttk.Scrollbar(table_frame, orient=tk.VERTICAL, command=self.table.yview)
        scroll_x = ttk.Scrollbar(table_frame, orient=tk.HORIZONTAL, command=self.table.xview)
        self.table.configure(yscrollcommand=scroll_y.set, xscrollcommand=scroll_x.set)
        self.table.grid(row=0, column=0, sticky=u"nsew")
        scroll_y.grid(row=0, column=1, sticky=u"ns")
        scroll_x.grid(row=1, column=0, sticky=u"ew")
        table_frame.rowconfigure(0, weight=1)
        table_frame.columnconfigure(0, weight=1)
        self.table.bind(u"<<TreeviewSelect>>", self.on_select)
        panes.add(table_frame, weight=3)

        # Подробности выбранной задачи и сообщения разбора
        self.details = tk.Text(panes, height=8, wrap=tk.WORD, relief=tk.FLAT, font=(u"Segoe UI", 9),
                               background=root.cget(u"background"))
        self.details.configure(state=tk.DISABLED)
        panes.add(self.details, weight=1)

        self.refresh_summary()

    # ------------------------------------------------------------ состояние

    def refresh_summary(self):
        settings = settings_core.load()
        try:
            ai_text = email_ai.prepare(settings).description
        except email_ai.AIError as ex:
            ai_text = u"не настроен — " + app_text(ex.message).split(u"\n")[0]
        source = (u"тестовые письма" if settings["test_mode"] else
                  u"«Входящие»" + (u" / " + settings["subfolder"] if settings["subfolder"] else u""))
        self.summary.set(u"Почта: {}, за {} дн.{}   •   ИИ: {}".format(
            source, settings["days"], u", только непрочитанные" if settings["unread_only"] else u"",
            ai_text))

    def _set_running(self, running):
        self.running = running
        self.run_btn.configure(state=tk.DISABLED if running else tk.NORMAL)
        self.settings_btn.configure(state=tk.DISABLED if running else tk.NORMAL)
        self.cancel_btn.configure(state=tk.NORMAL if running else tk.DISABLED)
        if not running:
            self.bar.stop()
            self.bar.configure(mode=u"determinate", value=0)

    def _show_text(self, text):
        self.details.configure(state=tk.NORMAL)
        self.details.delete(u"1.0", tk.END)
        self.details.insert(tk.END, text)
        self.details.configure(state=tk.DISABLED)

    def _fill_table(self, rows):
        self.table.delete(*self.table.get_children())
        for values in email_tasks_run.table(rows):
            self.table.insert(u"", tk.END, values=[u"" if v is None else v for v in values])

    # ------------------------------------------------------------ действия

    def on_run(self):
        settings = settings_core.load()
        prompt_text = settings_core.effective_prompt(settings, self.default_prompt)
        if not prompt_text.strip():
            messagebox.showerror(TITLE, u"Промпт пуст. Впишите промпт в настройках.", parent=self.root)
            return
        try:
            engine = email_ai.prepare(settings)
        except email_ai.AIError as ex:
            messagebox.showerror(TITLE, app_text(ex.message), parent=self.root)
            return

        self.cancel_requested = False
        self.excel_path = None
        self.excel_btn.configure(state=tk.DISABLED)
        self._fill_table([])
        self._show_text(u"")
        self._set_running(True)
        try:
            result = email_tasks_run.run(settings, prompt_text, engine, _Progress(self),
                                         email_tasks_xlsx, test_emails_file=self.test_emails_file)
        except Exception as ex:  # не должно случаться: run сам ловит ошибки шагов
            self._set_running(False)
            messagebox.showerror(TITLE, u"Непредвиденная ошибка:\n{}".format(ex), parent=self.root)
            return
        self._set_running(False)
        if self.close_after_run:
            self.root.destroy()
            return
        self._show_result(result, engine)

    def _show_result(self, result, engine):
        if result.cancelled:
            self.status.set(u"Отменено.")
            return
        if result.fatal_error:
            self.status.set(u"Ошибка — разбор остановлен.")
            self._show_text(app_text(result.fatal_error))
            messagebox.showerror(TITLE, app_text(result.fatal_error), parent=self.root)
            return
        if not result.emails:
            self.status.set(u"Писем нет.")
            messagebox.showinfo(TITLE, result.no_emails_text, parent=self.root)
            return

        self.rows = result.rows
        self._fill_table(result.rows)
        stamp = email_tasks_run.fmt_date(datetime.datetime.now(), with_time=True)
        self.status.set(u"{} — {}".format(stamp, result.describe(engine)))

        lines = []
        if result.read_warning:
            lines.append(u"⚠ " + result.read_warning)
        if not result.rows:
            lines.append(u"Задач, требующих ваших действий, не найдено.")
        lines.extend(u"⚠ " + w for w in result.excel_warnings)
        if result.batch_errors:
            lines.append(u"Ошибки:")
            lines.extend(u"• " + app_text(e) for e in result.batch_errors)
        if result.excel_error:
            lines.append(u"⚠ " + result.excel_error)
        if result.excel_path:
            self.excel_path = result.excel_path
            self.excel_btn.configure(state=tk.NORMAL)
            lines.append(u"Сохранено в Excel: {} (файл открыт).".format(result.excel_path))
        self._show_text(u"\n".join(lines))

        if result.batch_errors and not result.rows:
            messagebox.showwarning(TITLE, u"Не удалось получить задачи:\n\n" + app_text(
                u"\n\n".join(result.batch_errors))[:3000], parent=self.root)
        elif result.excel_error:
            messagebox.showwarning(TITLE, result.excel_error + u"\n\nСписок задач — в окне программы.",
                                   parent=self.root)

    def on_select(self, _event=None):
        selected = self.table.selection()
        if not selected:
            return
        index = self.table.index(selected[0])
        if index >= len(self.rows):
            return
        row = self.rows[index]
        parts = [
            u"Задача: " + (row.get("task") or u""),
            u"Кто просит: " + (row.get("requester") or u""),
            u"Срок: " + (email_tasks_run.fmt_date(row.get("deadline")) or u"—"),
            u"Приоритет: " + (row.get("priority") or u""),
        ]
        if row.get("comment"):
            parts.append(u"Комментарий: " + row["comment"])
        parts.append(u"Письмо: «{}» от {}, {}".format(
            row.get("subject") or u"", row.get("sender") or u"",
            email_tasks_run.fmt_date(row.get("received"), with_time=True)))
        self._show_text(u"\n".join(parts))

    def on_cancel(self):
        self.cancel_requested = True
        self.status.set(u"Отмена…")

    def on_settings(self):
        if mail_settings_window.edit(self.root, self.default_prompt):
            self.refresh_summary()

    def on_open_excel(self):
        if self.excel_path and os.path.isfile(self.excel_path):
            self._open(self.excel_path)

    def on_open_folder(self):
        try:
            folder = os.path.dirname(email_tasks_xlsx.default_output_path())
        except Exception as ex:
            messagebox.showerror(TITLE, u"Папка недоступна:\n{}".format(ex), parent=self.root)
            return
        self._open(folder)

    def _open(self, path):
        try:
            email_tasks_xlsx.open_path(path)
        except Exception as ex:
            messagebox.showerror(TITLE, u"Не удалось открыть:\n{}\n\n{}".format(path, ex), parent=self.root)

    def on_close(self):
        if self.running:
            # Разбор идёт внутри on_run — окно закроется, когда он остановится
            self.cancel_requested = True
            self.close_after_run = True
            self.status.set(u"Отмена…")
            return
        self.root.destroy()
