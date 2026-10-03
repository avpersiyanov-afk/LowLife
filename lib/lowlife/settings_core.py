# -*- coding: utf-8 -*-
"""
Общий модуль настроек кнопок: хранение в JSON-файле + типовое окно из
текстовых полей.

Хранилище (JsonStore)
---------------------
Каждая кнопка/дисциплина хранит свои настройки одним JSON-файлом в
%APPDATA%\\pyRevit\\<file_name> — обычный файл, намеренно НЕ
pyrevit.script.get_config() (тот не гарантированно делил секцию конфига
между разными script.py, см. CLAUDE.md). Раньше путь/чтение/запись были
скопированы в ~20 модулей *_settings.py; теперь они берут JsonStore:

    _STORE = settings_core.JsonStore("LowLifeXxx_settings.json", u"СКС")
    _settings_file_path = _STORE.path
    _read_all = _STORE.read
    _write_all = _STORE.write

Формат файла не изменился — уже сохранённые настройки читаются как раньше.

Типовое окно (TextSettings)
---------------------------
Для кнопок, у которых настройки — просто несколько текстовых полей (имена
параметров, маски, префиксы), всё остальное — загрузка с умолчаниями,
require(), окно, «Выгрузить/Загрузить настройки…», Shift+клик/тихий
режим — делает TextSettings по описанию полей:

    SETTINGS = settings_core.TextSettings(
        file_name="LowLifeRoomLots_settings.json",
        button_name=u"Двухуровневые лоты",
        heading=u"Параметры имени лота и номера секции",
        transfer_label=u"двухуровневых лотов",
        fields=[
            settings_core.TextField(
                "lot_param_name", u"① Имя лота",
                u"Параметр помещения (в связи АР)",
                hint=u"...", required=True),
        ],
    )

Нестандартные окна (таблицы, выбор типоразмеров, мнемосхемы) пока
остаются в своих модулях и берут отсюда только JsonStore.

WPF и pyrevit импортируются лениво (внутри функций), чтобы модуль
импортировался вне Revit — его хранилище и логика полей покрыты тестами
(tests/test_settings_core.py).
"""

import io
import json
import os

try:
    _text = unicode  # noqa: F821 — IronPython/Python 2
except NameError:  # Python 3 (тесты)
    _text = str


SETTINGS_FOLDER_NAME = "pyRevit"


def _alert(message, **kwargs):
    """forms.alert, если pyrevit доступен; вне Revit — молча ничего."""
    try:
        from pyrevit import forms
    except Exception:
        return None
    return forms.alert(message, **kwargs)


def settings_folder():
    """%APPDATA%\\pyRevit (создаётся при необходимости)."""
    appdata = os.environ.get("APPDATA") or os.path.expanduser("~")
    folder = os.path.join(appdata, SETTINGS_FOLDER_NAME)

    if not os.path.isdir(folder):
        try:
            os.makedirs(folder)
        except Exception:
            pass

    return folder


class JsonStore(object):
    """
    Один JSON-файл настроек в %APPDATA%\\pyRevit.

    file_name — имя файла или функция без аргументов, возвращающая имя
                (fire_alarm_settings: файл зависит от текущей системы).
    label     — что вставить в сообщение об ошибке записи («СКС»,
                «зон обзора», …); строка или функция. Пусто — общее
                «Не удалось сохранить настройки в файл».
    """

    def __init__(self, file_name, label=None):
        self._file_name = file_name
        self._label = label

    def _resolve(self, value):
        return value() if callable(value) else value

    def path(self):
        return os.path.join(settings_folder(), self._resolve(self._file_name))

    def read(self):
        """Весь словарь из файла; {} — если файла нет, он пуст или битый."""
        path = self.path()

        if not os.path.isfile(path):
            return {}

        try:
            with io.open(path, "r", encoding="utf-8") as f:
                text = f.read()
            if not text.strip():
                return {}
            data = json.loads(text)
        except Exception:
            return {}

        return data if isinstance(data, dict) else {}

    def write(self, data):
        """Перезаписывает файл целиком. True — записано; иначе alert и False."""
        path = self.path()

        try:
            with io.open(path, "w", encoding="utf-8") as f:
                f.write(_text(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True)))
            return True
        except Exception:
            label = self._resolve(self._label)
            what = u"настройки {}".format(label) if label else u"настройки"
            _alert(u"Не удалось сохранить {} в файл:\n{}".format(what, path))
            return False

    def update(self, values):
        """Дописывает/заменяет переданные ключи, остальные оставляет как есть."""
        data = self.read()
        data.update(values)
        return self.write(data)


# --- типовое окно из текстовых полей ------------------------------------------

class TextField(object):
    """
    Одно текстовое поле окна настроек.

    key      — ключ в JSON-файле.
    section  — жирный заголовок раздела над полем («① Имя лота»).
    label    — подпись поля; у обязательных к ней добавляется « *».
    hint     — серое пояснение под полем.
    default  — значение, пока пользователь ничего не сохранил.
    required — показывать « *»; сама проверка — require(settings, keys),
               ключи передаёт кнопка (у одной настройки разные кнопки могут
               требовать разное).
    """

    def __init__(self, key, section, label, hint=u"", default=u"", required=False):
        self.key = key
        self.section = section
        self.label = label
        self.hint = hint
        self.default = default
        self.required = required


class TextSettings(object):
    """
    Настройки кнопки из нескольких текстовых полей: хранение + окно.

    file_name      — имя JSON-файла в %APPDATA%\\pyRevit.
    button_name    — название кнопки на ленте (заголовок окна, подсказка
                     «Shift+клик по кнопке …» в require).
    heading        — крупный заголовок в окне.
    transfer_label — для «Выгрузить/Загрузить настройки…» (имя файла и
                     сообщения: «Настройки <transfer_label> выгружены…»).
    fields         — список TextField, в порядке показа.
    migrate        — необязательная функция (saved, values) → None, правит
                     values на месте после подстановки умолчаний: перенос
                     старых ключей в новые.
    width, height  — размер окна.
    """

    def __init__(self, file_name, button_name, heading, transfer_label, fields,
                 migrate=None, width=720, height=440):
        self.store = JsonStore(file_name)
        self.button_name = button_name
        self.heading = heading
        self.transfer_label = transfer_label
        self.fields = list(fields)
        self.migrate = migrate
        self.width = width
        self.height = height

    # --- данные -----------------------------------------------------------

    def labels(self):
        return dict((f.key, f.label) for f in self.fields)

    def load_saved_values(self):
        """Строковые значения: из файла, иначе — умолчания полей."""
        saved = self.store.read()
        values = dict((f.key, saved.get(f.key, f.default)) for f in self.fields)
        if self.migrate is not None:
            self.migrate(saved, values)
        return values

    def save_values(self, values):
        self.store.update(values)

    def missing(self, settings, keys):
        """Подписи незаполненных полей из keys (в порядке keys)."""
        labels = self.labels()
        result = []
        for key in keys:
            value = settings.get(key)
            if not (value and _text(value).strip()):
                result.append(labels.get(key, key))
        return result

    def require(self, settings, keys):
        """
        Проверяет, что перечисленные ключи заполнены. Останавливает скрипт
        через forms.alert(exitscript=True), если чего-то не хватает.
        """
        missing = self.missing(settings, keys)
        if missing:
            _alert(
                u"Не заполнены обязательные настройки:\n\n{}\n\n"
                u"Откройте настройки: Shift+клик по кнопке «{}».".format(
                    u"\n".join(missing), self.button_name
                ),
                exitscript=True
            )

    # --- окно -------------------------------------------------------------

    def show_settings_form(self, values):
        """
        Модальное окно редактирования. Возвращает словарь строковых
        значений, settings_transfer.RELOAD (настройки загружены из файла —
        открыть заново) или None, если пользователь отменил.
        """
        import clr
        clr.AddReference('PresentationFramework')
        clr.AddReference('PresentationCore')

        from System.Windows import (
            Window, WindowStartupLocation, Thickness,
            FontWeights, HorizontalAlignment, TextWrapping
        )
        from System.Windows.Controls import (
            StackPanel, TextBlock, TextBox, Button, Orientation, DockPanel, Dock,
            ScrollViewer, ScrollBarVisibility
        )
        from System.Windows.Media import Brushes

        from lowlife import settings_transfer

        result = {"values": None}

        win = Window()
        win.Title = u"Настройки: {}".format(self.button_name)
        win.Width = self.width
        win.Height = self.height
        win.WindowStartupLocation = WindowStartupLocation.CenterScreen

        outer = DockPanel()
        outer.LastChildFill = True

        root = StackPanel()
        root.Margin = Thickness(16)

        title = TextBlock()
        title.Text = self.heading
        title.FontSize = 16
        title.FontWeight = FontWeights.Bold
        title.Margin = Thickness(0, 0, 0, 4)
        root.Children.Add(title)

        hint = TextBlock()
        hint.Text = u"Значения сохраняются и подставляются при следующих запусках."
        hint.FontSize = 11
        hint.Foreground = Brushes.Gray
        hint.Margin = Thickness(0, 0, 0, 10)
        root.Children.Add(hint)

        boxes = {}

        for field in self.fields:
            section = TextBlock()
            section.Text = field.section
            section.FontWeight = FontWeights.Bold
            section.Margin = Thickness(0, 16, 0, 2)
            root.Children.Add(section)

            label = TextBlock()
            label.Text = field.label + (u" *" if field.required else u"")
            label.Margin = Thickness(0, 2, 0, 2)
            label.TextWrapping = TextWrapping.Wrap
            root.Children.Add(label)

            box = TextBox()
            box.Text = values.get(field.key, u"")
            box.Padding = Thickness(4)
            root.Children.Add(box)
            boxes[field.key] = box

            if field.hint:
                field_hint = TextBlock()
                field_hint.Text = field.hint
                field_hint.FontSize = 11
                field_hint.Foreground = Brushes.Gray
                field_hint.TextWrapping = TextWrapping.Wrap
                field_hint.Margin = Thickness(0, 2, 0, 0)
                root.Children.Add(field_hint)

        if any(f.required for f in self.fields):
            required_hint = TextBlock()
            required_hint.Text = u"* обязательные поля"
            required_hint.FontSize = 11
            required_hint.Foreground = Brushes.Gray
            required_hint.Margin = Thickness(0, 10, 0, 0)
            root.Children.Add(required_hint)

        buttons = StackPanel()
        buttons.Orientation = Orientation.Horizontal
        buttons.HorizontalAlignment = HorizontalAlignment.Right
        buttons.Margin = Thickness(16, 8, 16, 12)
        DockPanel.SetDock(buttons, Dock.Bottom)

        cancel_btn = Button()
        cancel_btn.Content = u"Отмена"
        cancel_btn.Padding = Thickness(10, 4, 10, 4)
        cancel_btn.Margin = Thickness(0, 0, 8, 0)

        ok_btn = Button()
        ok_btn.Content = u"Сохранить"
        ok_btn.Padding = Thickness(10, 4, 10, 4)
        ok_btn.FontWeight = FontWeights.Bold

        def on_ok(sender, args):
            result["values"] = dict((key, box.Text) for key, box in boxes.items())
            win.Close()

        def on_cancel(sender, args):
            win.Close()

        ok_btn.Click += on_ok
        cancel_btn.Click += on_cancel

        buttons.Children.Add(cancel_btn)
        buttons.Children.Add(ok_btn)

        def _on_settings_imported():
            result["values"] = settings_transfer.RELOAD
            win.Close()

        settings_transfer.add_transfer_buttons(
            buttons, self.store.read, self.store.write,
            self.transfer_label, _on_settings_imported
        )

        # Длинные пояснения не должны обрезаться при маленькой высоте окна.
        scroll = ScrollViewer()
        scroll.VerticalScrollBarVisibility = ScrollBarVisibility.Auto
        scroll.Content = root

        outer.Children.Add(buttons)
        outer.Children.Add(scroll)

        win.Content = outer
        win.ShowDialog()

        return result["values"]

    def get_settings_interactive(self):
        """
        Показывает окно настроек, сохраняет введённые значения и возвращает
        их. None — пользователь нажал «Отмена». Для Shift+клика по кнопке.
        """
        from lowlife import settings_transfer

        while True:
            saved = self.load_saved_values()
            edited = self.show_settings_form(saved)

            if edited == settings_transfer.RELOAD:
                # настройки загружены из файла и уже записаны — открываем заново
                continue

            if edited is None:
                return None

            self.save_values(edited)
            return edited

    def get_settings_silent(self):
        """Уже сохранённые значения без окна (или умолчания полей)."""
        return self.load_saved_values()
