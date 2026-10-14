# -*- coding: utf-8 -*-
"""Окно кнопки «Повернуть 3D вид»: какой 3D вид, вокруг какой оси (X/Y/Z
модели или ось сетки) и на какой угол.

Окно модальное и не закрывается после поворота: «Повернуть» сразу
поворачивает вид (через `apply`, который передаёт скрипт кнопки), так что
вид можно доворачивать по шагам. Последний выбор запоминается в
%APPDATA%\\pyRevit\\LowLifeRotate3DView_settings.json (settings_core.JsonStore).
Только IronPython/WPF.
"""

from lowlife import settings_core, view_rotate

STORE = settings_core.JsonStore("LowLifeRotate3DView_settings.json", u"настройки «Повернуть 3D вид»")

QUICK_ANGLES = (-90, -45, 45, 90, 180)


def load_choice():
    data = STORE.read()
    keys = [a[0] for a in view_rotate.AXES]
    axis = data.get("axis")
    if axis not in keys:
        axis = view_rotate.DEFAULT_AXIS
    angle = data.get("angle")
    if angle in (None, u""):
        angle = view_rotate.DEFAULT_ANGLE
    return {
        "axis": axis,
        "angle": angle,
        "grid": data.get("grid") or u"",
        "fit": bool(data.get("fit", True)),
    }


def save_choice(values):
    STORE.update(values)


def _fmt_angle(value):
    try:
        value = float(value)
    except (TypeError, ValueError):
        return unicode(value)
    if value == int(value):
        return unicode(int(value))
    return u"{:g}".format(value)


def show(views, grids, active_view_id, apply):
    """
    views — [(имя, View3D)], grids — [(имя, Grid)] из view_rotate.
    apply(view, axis_key, angle_deg, grid, fit) -> текст ошибки или None;
    вызывается по «Повернуть», окно остаётся открытым.
    """
    import clr
    clr.AddReference('PresentationFramework')
    clr.AddReference('PresentationCore')
    from System.Windows import (
        Window, WindowStartupLocation, Thickness, HorizontalAlignment,
        SizeToContent, ResizeMode, TextWrapping, MessageBox,
    )
    from System.Windows.Controls import (
        StackPanel, TextBlock, TextBox, Button, RadioButton, ComboBox,
        CheckBox, Orientation,
    )
    from System.Windows.Media import Brushes

    choice = load_choice()

    win = Window()
    win.Title = u"Повернуть 3D вид"
    win.SizeToContent = SizeToContent.WidthAndHeight
    win.ResizeMode = ResizeMode.NoResize
    win.WindowStartupLocation = WindowStartupLocation.CenterScreen
    win.MinWidth = 400

    root = StackPanel()
    root.Margin = Thickness(16)

    def label(text, top=12):
        tb = TextBlock()
        tb.Text = text
        tb.Margin = Thickness(0, top, 0, 4)
        root.Children.Add(tb)
        return tb

    label(u"3D вид", 0)
    view_box = ComboBox()
    view_box.MaxWidth = 420
    selected_index = 0
    for i, (name, v) in enumerate(views):
        view_box.Items.Add(name)
        if active_view_id is not None and v.Id == active_view_id:
            selected_index = i
    view_box.SelectedIndex = selected_index
    root.Children.Add(view_box)

    label(u"Ось поворота")
    radios = []
    for key, text in view_rotate.AXES:
        rb = RadioButton()
        rb.Content = text
        rb.GroupName = "rotate_axis"
        rb.Tag = key
        rb.IsChecked = (key == choice["axis"])
        rb.Margin = Thickness(0, 2, 0, 2)
        if key == view_rotate.AXIS_GRID and not grids:
            rb.IsEnabled = False
            rb.Content = text + u" (в проекте нет прямых осей)"
            rb.IsChecked = False
        radios.append(rb)
        root.Children.Add(rb)
    if not any(rb.IsChecked for rb in radios):
        for rb in radios:
            rb.IsChecked = (rb.Tag == view_rotate.DEFAULT_AXIS)

    grid_box = ComboBox()
    grid_box.Margin = Thickness(20, 2, 0, 0)
    grid_box.MaxWidth = 400
    for i, (name, _g) in enumerate(grids):
        grid_box.Items.Add(name)
        if name == choice["grid"]:
            grid_box.SelectedIndex = i
    if grids and grid_box.SelectedIndex < 0:
        grid_box.SelectedIndex = 0
    root.Children.Add(grid_box)

    label(u"Угол, градусы")
    angle_row = StackPanel()
    angle_row.Orientation = Orientation.Horizontal
    angle_box = TextBox()
    angle_box.Text = _fmt_angle(choice["angle"])
    angle_box.Width = 80
    angle_row.Children.Add(angle_box)
    for value in QUICK_ANGLES:
        b = Button()
        b.Content = (u"+" if value > 0 else u"") + unicode(value) + u"°"
        b.MinWidth = 44
        b.Margin = Thickness(6, 0, 0, 0)
        b.Tag = value

        def on_quick(sender, _args):
            angle_box.Text = unicode(sender.Tag)
        b.Click += on_quick
        angle_row.Children.Add(b)
    root.Children.Add(angle_row)

    hint = TextBlock()
    hint.Text = (u"Модель в кадре поворачивается против часовой стрелки, если "
                 u"смотреть с конца оси (минус — по часовой). Оси X/Y/Z проходят "
                 u"через центр рамки 3D вида, а без рамки — через центр вида.")
    hint.Foreground = Brushes.Gray
    hint.FontSize = 11
    hint.TextWrapping = TextWrapping.Wrap
    hint.MaxWidth = 400
    hint.Margin = Thickness(0, 6, 0, 0)
    root.Children.Add(hint)

    fit_box = CheckBox()
    fit_box.Content = u"Показать целиком после поворота (неоткрытый вид откроется\nпри закрытии окна)"
    fit_box.IsChecked = choice["fit"]
    fit_box.Margin = Thickness(0, 12, 0, 0)
    root.Children.Add(fit_box)

    status = TextBlock()
    status.FontSize = 11
    status.TextWrapping = TextWrapping.Wrap
    status.MaxWidth = 400
    status.Margin = Thickness(0, 8, 0, 0)
    root.Children.Add(status)

    def selected_axis():
        for rb in radios:
            if rb.IsChecked:
                return rb.Tag
        return view_rotate.DEFAULT_AXIS

    def refresh(*_args):
        grid_box.IsEnabled = selected_axis() == view_rotate.AXIS_GRID

    for rb in radios:
        rb.Checked += refresh
    refresh()

    buttons = StackPanel()
    buttons.Orientation = Orientation.Horizontal
    buttons.HorizontalAlignment = HorizontalAlignment.Right
    buttons.Margin = Thickness(0, 14, 0, 0)
    ok = Button()
    ok.Content = u"Повернуть"
    ok.IsDefault = True
    ok.MinWidth = 90
    close = Button()
    close.Content = u"Закрыть"
    close.IsCancel = True
    close.MinWidth = 90
    close.Margin = Thickness(8, 0, 0, 0)
    buttons.Children.Add(ok)
    buttons.Children.Add(close)
    root.Children.Add(buttons)

    def on_ok(*_args):
        status.Text = u""
        if view_box.SelectedIndex < 0:
            return
        try:
            angle = view_rotate.parse_angle(angle_box.Text)
        except ValueError as err:
            MessageBox.Show(unicode(err), win.Title)
            return
        axis = selected_axis()
        grid = None
        grid_name = u""
        if axis == view_rotate.AXIS_GRID:
            if grid_box.SelectedIndex < 0:
                MessageBox.Show(u"Выберите ось сетки.", win.Title)
                return
            grid_name, grid = grids[grid_box.SelectedIndex]
        view_name, view = views[view_box.SelectedIndex]
        fit = bool(fit_box.IsChecked)
        save_choice({"axis": axis, "angle": angle, "grid": grid_name or choice["grid"],
                     "fit": fit})
        error = apply(view, axis, angle, grid, fit)
        if error:
            MessageBox.Show(error, win.Title)
            return
        status.Foreground = Brushes.Gray
        status.Text = u"«{}» повёрнут на {}°.".format(view_name, _fmt_angle(angle))

    ok.Click += on_ok
    win.Content = root
    win.ShowDialog()
