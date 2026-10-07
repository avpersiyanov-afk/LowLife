# -*- coding: utf-8 -*-
"""Окно кнопки «Обрезать вид» после выбора рамки: что обрезать — этот вид
или его копию (view_crop.MODES) — и префикс имени копии.

Последний выбор запоминается в %APPDATA%\\pyRevit\\LowLifeCropView_settings.json
(settings_core.JsonStore). Только IronPython/WPF.
"""

from lowlife import settings_core, view_crop

STORE = settings_core.JsonStore("LowLifeCropView_settings.json", u"настройки «Обрезать вид»")


def load_choice():
    data = STORE.read()
    mode = data.get("mode") or view_crop.DEFAULT_MODE
    prefix = data.get("prefix")
    if prefix is None:
        prefix = view_crop.DEFAULT_PREFIX
    return mode, prefix


def save_choice(mode, prefix):
    STORE.update({"mode": mode, "prefix": prefix})


def ask(modes, source_name):
    """
    modes — [(ключ, подпись, ...)] из view_crop.available_modes. Возвращает
    (ключ режима, префикс) или None, если окно закрыли/отменили.
    """
    import clr
    clr.AddReference('PresentationFramework')
    clr.AddReference('PresentationCore')
    from System.Windows import (
        Window, WindowStartupLocation, Thickness, HorizontalAlignment,
        SizeToContent, ResizeMode, TextWrapping,
    )
    from System.Windows.Controls import (
        StackPanel, TextBlock, TextBox, Button, RadioButton, Orientation,
    )
    from System.Windows.Media import Brushes

    mode, prefix = load_choice()
    keys = [m[0] for m in modes]
    if mode not in keys:
        mode = view_crop.DEFAULT_MODE if view_crop.DEFAULT_MODE in keys else keys[0]

    win = Window()
    win.Title = u"Обрезать вид"
    win.SizeToContent = SizeToContent.WidthAndHeight
    win.ResizeMode = ResizeMode.NoResize
    win.WindowStartupLocation = WindowStartupLocation.CenterScreen
    win.MinWidth = 380

    root = StackPanel()
    root.Margin = Thickness(16)

    head = TextBlock()
    head.Text = u"Рамка выбрана. Что обрезать?"
    head.Margin = Thickness(0, 0, 0, 8)
    root.Children.Add(head)

    radios = []
    for key, label, _option in modes:
        rb = RadioButton()
        rb.Content = label
        rb.GroupName = "crop_mode"
        rb.IsChecked = (key == mode)
        rb.Margin = Thickness(0, 2, 0, 2)
        rb.Tag = key
        radios.append(rb)
        root.Children.Add(rb)

    lbl = TextBlock()
    lbl.Text = u"Префикс имени копии"
    lbl.Margin = Thickness(0, 12, 0, 2)
    root.Children.Add(lbl)
    box = TextBox()
    box.Text = prefix
    root.Children.Add(box)
    preview = TextBlock()
    preview.Foreground = Brushes.Gray
    preview.FontSize = 11
    preview.TextWrapping = TextWrapping.Wrap
    preview.MaxWidth = 420
    preview.Margin = Thickness(0, 4, 0, 0)
    root.Children.Add(preview)

    def selected():
        for rb in radios:
            if rb.IsChecked:
                return rb.Tag
        return keys[0]

    def refresh(*_args):
        is_copy = selected() != view_crop.MODE_SELF
        box.IsEnabled = is_copy
        lbl.Foreground = Brushes.Black if is_copy else Brushes.Gray
        preview.Text = (u"Имя копии: {}".format(
            view_crop.copy_name(box.Text, source_name, set())) if is_copy
            else u"Копия не создаётся — обрезается открытый вид.")

    for rb in radios:
        rb.Checked += refresh
    box.TextChanged += refresh
    refresh()

    buttons = StackPanel()
    buttons.Orientation = Orientation.Horizontal
    buttons.HorizontalAlignment = HorizontalAlignment.Right
    buttons.Margin = Thickness(0, 14, 0, 0)
    ok = Button()
    ok.Content = u"Обрезать"
    ok.IsDefault = True
    ok.MinWidth = 90
    cancel = Button()
    cancel.Content = u"Отмена"
    cancel.IsCancel = True
    cancel.MinWidth = 90
    cancel.Margin = Thickness(8, 0, 0, 0)
    buttons.Children.Add(ok)
    buttons.Children.Add(cancel)
    root.Children.Add(buttons)

    result = {"value": None}

    def on_ok(*_args):
        result["value"] = (selected(), box.Text)
        win.Close()

    ok.Click += on_ok
    win.Content = root
    win.ShowDialog()

    if result["value"] is not None:
        save_choice(*result["value"])
    return result["value"]
