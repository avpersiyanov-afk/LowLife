# -*- coding: utf-8 -*-
"""Graphite Studio (dark) / Precision Pro (light), scoped to LowLife windows.

Revit's theme takes precedence over Windows. Icons and model data are untouched.
"""
try:
    unicode
except NameError:
    unicode = str

import io
import os

RESOURCE_PATH = os.path.join(os.path.dirname(__file__), 'xaml', 'ui_theme.xaml')
_STATE_KEY = 'LowLife.Theme.State'
_LAYOUT_KEY = 'LowLife.Theme.Layout'
PALETTES = {
    'dark': {
        'Background': '#202124', 'Surface': '#27282C', 'Chrome': '#191A1D',
        'Foreground': '#F3F1ED', 'Muted': '#B1B1B8', 'Border': '#45464C',
        'Selected': '#35363C', 'Accent': '#F08C28', 'AccentText': '#21180D',
        'Danger': '#F29AA9', 'DangerSurface': '#40272E',
    },
    'light': {
        'Background': '#F5F6F8', 'Surface': '#FFFFFF', 'Chrome': '#FFFFFF',
        'Foreground': '#242932', 'Muted': '#626B79', 'Border': '#CCD2DC',
        'Selected': '#EAEFF5', 'Accent': '#F08C28', 'AccentText': '#21180D',
        'Danger': '#A92340', 'DangerSurface': '#FCE8EC',
    },
}


def current_theme():
    """Reuse pyRevit's theme helper; Windows app preference is the standalone fallback."""
    try:
        from pyrevit.revit.ui import get_current_theme
        name = unicode(get_current_theme()).lower()
        if name in PALETTES:
            return name
    except (ImportError, AttributeError, RuntimeError):
        pass
    try:
        try:
            import winreg
        except ImportError:
            import _winreg as winreg
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                            r'Software\Microsoft\Windows\CurrentVersion\Themes\Personalize')
        try:
            value, _kind = winreg.QueryValueEx(key, 'AppsUseLightTheme')
            return 'light' if value else 'dark'
        finally:
            winreg.CloseKey(key)
    except (ImportError, OSError):
        return 'light'


def button_role(caption):
    """Shared action roles, independent of language and appearance."""
    text = unicode(caption or u'').strip().lower()
    groups = (
        ('danger', (u'удал', u'очист', 'delete', 'remove', 'clear')),
        ('neutral', (u'отмена', u'закрыть', u'назад', 'cancel', 'close', 'back')),
        ('transfer', (u'загруз', u'выгруз', u'импорт', u'экспорт', 'import', 'export', 'load')),
        ('primary', (u'сохран', u'примен', u'созда', u'запуст', u'продолж', u'разобрать',
                     u'выполн', u'выбрать', 'save', 'apply', 'create', 'run',
                     'continue', 'select', 'analyse', 'analyze', 'ok', u'ок')),
    )
    for role, prefixes in groups:
        if text.startswith(prefixes):
            return role
    return 'secondary'


def _recolour(item, prop, foreground=False, default=None):
    """Replace only literal neutral UI colours; retain bindings and semantic colours."""
    from System.Windows.Media import SolidColorBrush
    from System.Windows.Data import BindingOperations
    from System.Windows import DependencyProperty
    if BindingOperations.IsDataBound(item, prop):
        return
    brush = item.ReadLocalValue(prop)
    if brush == DependencyProperty.UnsetValue and default:
        item.SetResourceReference(prop, 'LowLife.' + default)
        return
    if not isinstance(brush, SolidColorBrush) or brush.Color.A == 0:
        return
    values = (int(brush.Color.R), int(brush.Color.G), int(brush.Color.B))
    if max(values) - min(values) > 64:
        return
    brightness = sum(values) / 3.0
    if prop.Name == 'BorderBrush':
        key = 'Border'
    elif foreground:
        key = 'Muted' if 80 <= brightness < 210 else 'Foreground'
    else:
        if brightness < 60:  # Preserve black brand banners.
            return
        key = 'Surface' if brightness >= 242 else 'Selected'
    item.SetResourceReference(prop, 'LowLife.' + key)


def _decorate(root, resources):
    import clr
    from System.Windows import LogicalTreeHelper, DependencyObject, FontWeights
    from System.Windows.Controls import (
        Button, TextBox, TextBlock, Panel, Border, Control, Canvas,
        ToolTipService, ComboBox, DataGrid, ListBox, TabControl, TabItem, CheckBox,
        RadioButton, GroupBox,
    )
    from System.Windows.Media import Brushes
    from System.Windows.Documents import TextElement
    from System.Windows.Controls.Primitives import DataGridColumnHeader
    pending = [root]
    while pending:
        item = pending.pop()
        if not isinstance(item, DependencyObject):
            continue
        if isinstance(item, Canvas):  # Technical diagrams keep their own colours.
            if item.Background is None:
                item.Background = Brushes.White
            TextElement.SetForeground(item, Brushes.Black)
            continue
        if isinstance(item, Button):
            role = button_role(item.Content if isinstance(item.Content, (str, unicode)) else item.Name)
            item.Style = resources['LowLife.Button.' + role]
            item.ClearValue(Button.BackgroundProperty)
            item.ClearValue(Button.ForegroundProperty)
            item.ClearValue(Button.BorderBrushProperty)
        elif isinstance(item, (TextBox, ComboBox, DataGrid, ListBox, TabControl,
                               TabItem, CheckBox, RadioButton, GroupBox, DataGridColumnHeader)):
            _recolour(item, Control.BackgroundProperty, default='Surface')
            _recolour(item, Control.ForegroundProperty, True, 'Foreground')
            _recolour(item, Control.BorderBrushProperty, default='Border')
            if isinstance(item, (TextBox, ComboBox)):
                # Old window-local styles still provide padding/minimum sizes, while
                # the shared template removes their hardcoded light native surfaces.
                kind = TextBox if isinstance(item, TextBox) else ComboBox
                for setter in resources[clr.GetClrType(kind)].Setters:
                    if setter.Property == Control.TemplateProperty:
                        item.Template = setter.Value
            if isinstance(item, DataGrid):
                item.SetResourceReference(DataGrid.RowBackgroundProperty, 'LowLife.Surface')
                item.SetResourceReference(DataGrid.AlternatingRowBackgroundProperty, 'LowLife.Background')
        elif isinstance(item, TextBlock):
            _recolour(item, TextBlock.ForegroundProperty, True)
            _recolour(item, TextBlock.BackgroundProperty)
            if (item.FontWeight == FontWeights.Bold and item.Margin.Top >= 12
                    and item.FontSize < 16):
                item.Style = resources['LowLife.Section']
        elif isinstance(item, Border):
            _recolour(item, Border.BackgroundProperty)
            _recolour(item, Border.BorderBrushProperty)
        elif isinstance(item, Panel):
            _recolour(item, Panel.BackgroundProperty)
        if isinstance(item, TextBox):
            parent = LogicalTreeHelper.GetParent(item)
            if isinstance(parent, Panel):
                index = parent.Children.IndexOf(item)
                if index + 1 < parent.Children.Count:
                    following = parent.Children[index + 1]
                    if (isinstance(following, TextBlock) and following.Text
                            and following.FontSize <= 11.5):
                        detail = unicode(following.Text)
                        old = unicode(item.ToolTip or u'')
                        if detail not in old:
                            item.ToolTip = detail + (u'\n\n' + old if old else u'')
        ToolTipService.SetShowDuration(item, 60000)
        ToolTipService.SetInitialShowDelay(item, 350)
        pending.extend(LogicalTreeHelper.GetChildren(item))


def apply(surface, theme=None):
    """Apply/update local resources; optional explicit theme supports preview rendering."""
    # Revit hosts pyRevit WPF windows and dockable panes inside its own UI
    # tree.  Replacing templates and subscribing to the host ThemeChanged
    # event from an IronPython engine can corrupt that tree and take down the
    # whole Revit process.  Keep the native WPF surface until this integration
    # is reworked around a dedicated, isolated host window.
    return surface

    # The implementation below is retained for the standalone preview and
    # future isolated hosts; do not call it from Revit until the host boundary
    # is explicit.
    import clr
    clr.AddReference('PresentationFramework')
    clr.AddReference('PresentationCore')
    from System.Windows import FrameworkElement, SystemColors, CornerRadius
    from System.Windows.Controls import Control
    from System.Windows.Markup import XamlReader
    from System.Windows.Media import BrushConverter, FontFamily
    if not isinstance(surface, FrameworkElement) or getattr(surface, 'AllowsTransparency', False):
        return surface
    name = theme or current_theme()
    colours = PALETTES[name]
    state = surface.Resources[_STATE_KEY] if surface.Resources.Contains(_STATE_KEY) else None
    if state is None:
        with io.open(RESOURCE_PATH, encoding='utf-8') as stream:
            resources = XamlReader.Parse(stream.read())
        surface.Resources.MergedDictionaries.Add(resources)
        state = {'name': None, 'resources': resources, 'app': None, 'handler': None}
        surface.Resources[_STATE_KEY] = state

        def changed(sender, args):
            apply(surface)

        def loaded(sender, args):
            apply(surface, theme)
            _decorate(surface, resources)
            if theme is None and state['app'] is None:
                try:
                    from pyrevit import HOST_APP
                    app = HOST_APP.uiapp
                    app.ThemeChanged += changed
                    state['app'], state['handler'] = app, changed
                except (ImportError, AttributeError):
                    pass

        def unloaded(sender, args):
            if state['app'] is not None:
                state['app'].ThemeChanged -= state['handler']
                state['app'], state['handler'] = None, None

        surface.Loaded += loaded
        surface.Unloaded += unloaded
    if state['name'] == name:
        return surface
    resources = state['resources']
    converter = BrushConverter()
    for key, value in colours.items():
        resources['LowLife.' + key] = converter.ConvertFromString(value)
    resources['LowLife.CornerRadius'] = CornerRadius(6 if name == 'dark' else 4)
    for key, role in ((SystemColors.WindowBrushKey, 'Surface'),
                      (SystemColors.WindowTextBrushKey, 'Foreground'),
                      (SystemColors.ControlBrushKey, 'Background'),
                      (SystemColors.ControlTextBrushKey, 'Foreground'),
                      (SystemColors.HighlightBrushKey, 'Selected'),
                      (SystemColors.HighlightTextBrushKey, 'Foreground'),
                      (SystemColors.GrayTextBrushKey, 'Muted')):
        resources[key] = resources['LowLife.' + role]
    if isinstance(surface, Control):
        surface.SetResourceReference(Control.BackgroundProperty, 'LowLife.Background')
        surface.SetResourceReference(Control.ForegroundProperty, 'LowLife.Foreground')
        surface.FontFamily = FontFamily('Segoe UI')
    state['name'] = name
    if surface.Resources.Contains(_LAYOUT_KEY):
        surface.Resources[_LAYOUT_KEY](name)
    _decorate(surface, resources)
    return surface


def settings_form(surface, heading, intro, fields, buttons):
    """Lay out existing controls without duplicating parsing, storage or autocomplete.

    Theme changes move the same controls in place, preserving unsaved input.
    """
    from System.Windows import Thickness, FontWeights, TextWrapping, Visibility, GridLength, GridUnitType
    from System.Windows.Controls import (
        Border, DockPanel, Dock, Grid, ColumnDefinition, RowDefinition, StackPanel,
        TextBlock, Button, ScrollViewer, ScrollBarVisibility,
    )
    from lowlife.i18n import tr
    outer = DockPanel()
    outer.SetResourceReference(DockPanel.BackgroundProperty, 'LowLife.Background')
    header = Border()
    header.Padding = Thickness(24, 20, 24, 16)
    header.SetResourceReference(Border.BackgroundProperty, 'LowLife.Chrome')
    header_stack = StackPanel()
    title = TextBlock()
    title.Text, title.FontSize = heading, 22
    title.TextWrapping = TextWrapping.Wrap
    header_stack.Children.Add(title)
    subtitle = TextBlock()
    subtitle.Text, subtitle.FontSize = intro, 12
    subtitle.TextWrapping = TextWrapping.Wrap
    subtitle.Margin = Thickness(0, 6, 0, 0)
    subtitle.SetResourceReference(TextBlock.ForegroundProperty, 'LowLife.Muted')
    header_stack.Children.Add(subtitle)
    header.Child = header_stack
    DockPanel.SetDock(header, Dock.Top)
    outer.Children.Add(header)

    footer = Border()
    footer.Padding = Thickness(24, 12, 24, 16)
    footer.BorderThickness = Thickness(0, 1, 0, 0)
    footer.SetResourceReference(Border.BorderBrushProperty, 'LowLife.Border')
    buttons.Margin = Thickness(0)
    footer.Child = buttons
    DockPanel.SetDock(footer, Dock.Bottom)
    outer.Children.Add(footer)

    inspector = Border()
    inspector.Margin = Thickness(24, 0, 24, 16)
    inspector.Padding = Thickness(14, 10, 12, 10)
    inspector.BorderThickness = Thickness(2, 0, 0, 0)
    inspector.SetResourceReference(Border.BorderBrushProperty, 'LowLife.Accent')
    inspector.SetResourceReference(Border.BackgroundProperty, 'LowLife.Selected')
    inspector_stack = StackPanel()
    inspector_title, inspector_text = TextBlock(), TextBlock()
    inspector_title.FontWeight = FontWeights.SemiBold
    inspector_text.FontSize = 12
    inspector_text.TextWrapping = TextWrapping.Wrap
    inspector_text.Margin = Thickness(0, 6, 0, 0)
    inspector_text.SetResourceReference(TextBlock.ForegroundProperty, 'LowLife.Muted')
    inspector_stack.Children.Add(inspector_title)
    inspector_stack.Children.Add(inspector_text)
    inspector_scroll = ScrollViewer()
    inspector_scroll.MaxHeight = 125
    inspector_scroll.VerticalScrollBarVisibility = ScrollBarVisibility.Auto
    inspector_scroll.Content = inspector_stack
    inspector.Child = inspector_scroll
    DockPanel.SetDock(inspector, Dock.Bottom)
    outer.Children.Add(inspector)

    content = Grid()
    content.ColumnDefinitions.Add(ColumnDefinition())
    content.ColumnDefinitions.Add(ColumnDefinition())
    content.ColumnDefinitions[0].Width = GridLength.Auto
    sidebar = StackPanel()
    sidebar.Width, sidebar.Margin = 155, Thickness(16, 20, 12, 12)
    content.Children.Add(sidebar)
    root = StackPanel()
    root.Margin = Thickness(24, 8, 24, 20)
    scroll = ScrollViewer()
    scroll.VerticalScrollBarVisibility = ScrollBarVisibility.Auto
    scroll.Content = root
    Grid.SetColumn(scroll, 1)
    content.Children.Add(scroll)
    outer.Children.Add(content)
    entries, sections = [], []

    def explain(field):
        inspector_title.Text = field.title()
        inspector_text.Text = field.help_text()

    for field, control in fields:
        if field.section and field.label:
            section = TextBlock()
            section.Text = tr(field.section)
            section.FontSize = 12
            section.FontWeight = FontWeights.SemiBold
            section.Margin = Thickness(0, 14, 0, 10)
            section.SetResourceReference(TextBlock.ForegroundProperty, 'LowLife.Muted')
            root.Children.Add(section)
            sections.append((section.Text, section))
        row = Grid()
        row.Margin = Thickness(0, 6, 0, 14)
        for _index in range(2):
            row.ColumnDefinitions.Add(ColumnDefinition())
        for _index in range(3):
            definition = RowDefinition()
            definition.Height = GridLength.Auto
            row.RowDefinitions.Add(definition)
        label = TextBlock()
        label.Text = field.title() + (u' *' if field.required else u'')
        label.TextWrapping = TextWrapping.Wrap
        label.FontWeight = FontWeights.SemiBold
        label.FontSize = 13
        row.Children.Add(label)
        control.ToolTip = field.help_text()
        control.Padding = Thickness(8, 6, 8, 6)
        row.Children.Add(control)
        hint = TextBlock()
        hint.Text = tr(field.hint) if field.hint else u''
        hint.FontSize = 12
        hint.TextWrapping = TextWrapping.Wrap
        hint.Margin = Thickness(0, 7, 0, 0)
        hint.SetResourceReference(TextBlock.ForegroundProperty, 'LowLife.Muted')
        Grid.SetRow(hint, 2)
        Grid.SetColumnSpan(hint, 2)
        row.Children.Add(hint)
        control.GotKeyboardFocus += lambda sender, args, field=field: explain(field)
        entries.append((row, label, control, hint))
        root.Children.Add(row)
    for caption, target in sections:
        nav = Button()
        nav.Content = caption
        nav.Margin = Thickness(0, 0, 0, 8)
        nav.Click += lambda sender, args, target=target: target.BringIntoView()
        sidebar.Children.Add(nav)
    if fields:
        explain(fields[0][0])

    def update(name):
        dark = name == 'dark'
        sidebar.Visibility = Visibility.Visible if dark and len(sections) > 1 else Visibility.Collapsed
        inspector.Visibility = Visibility.Collapsed if dark else Visibility.Visible
        for row, label, control, hint in entries:
            row.ColumnDefinitions[0].Width = GridLength(1 if dark else 0.38, GridUnitType.Star)
            row.ColumnDefinitions[1].Width = GridLength(0 if dark else 0.62, GridUnitType.Star)
            Grid.SetColumnSpan(label, 2 if dark else 1)
            Grid.SetRow(control, 1 if dark else 0)
            Grid.SetColumn(control, 0 if dark else 1)
            Grid.SetColumnSpan(control, 2 if dark else 1)
            label.Margin = Thickness(0, 0 if dark else 7, 12, 7 if dark else 0)
            hint.Visibility = Visibility.Visible if dark and hint.Text else Visibility.Collapsed
    surface.Resources[_LAYOUT_KEY] = update
    surface.Content = outer


def apply_tk(surface, theme=None):
    """Use Windows light/dark appearance for the standalone mail application."""
    from tkinter import ttk, Text, Canvas
    colours = PALETTES[theme or current_theme()]
    style = ttk.Style(surface)
    if style.theme_use() != 'clam':
        style.theme_use('clam')
    style.configure('.', font=('Segoe UI', 10), background=colours['Background'], foreground=colours['Foreground'])
    style.configure('TEntry', fieldbackground=colours['Surface'], foreground=colours['Foreground'])
    style.configure('TCombobox', fieldbackground=colours['Surface'], foreground=colours['Foreground'])
    style.configure('Treeview', background=colours['Surface'], fieldbackground=colours['Surface'],
                    foreground=colours['Foreground'], rowheight=26)
    style.map('Treeview', background=[('selected', colours['Selected'])],
              foreground=[('selected', colours['Foreground'])])
    for role in ('primary', 'secondary', 'transfer', 'danger', 'neutral'):
        background = colours['Accent'] if role == 'primary' else colours['Surface']
        foreground = colours['AccentText'] if role == 'primary' else colours['Foreground']
        if role == 'danger':
            background, foreground = colours['DangerSurface'], colours['Danger']
        key = 'LowLife.' + role + '.TButton'
        style.configure(key, background=background, foreground=foreground,
                        bordercolor=colours['Border'], padding=(12, 6))
        style.map(key, background=[('disabled', colours['Background']), ('pressed', colours['Selected']),
                                   ('active', background)],
                  foreground=[('disabled', colours['Muted']), ('pressed', colours['Foreground'])])
    surface.configure(background=colours['Background'])
    pending = [surface]
    while pending:
        widget = pending.pop()
        if isinstance(widget, ttk.Button):
            widget.configure(style='LowLife.' + button_role(widget.cget('text')) + '.TButton')
        elif isinstance(widget, Text):
            widget.configure(background=colours['Surface'], foreground=colours['Foreground'],
                             insertbackground=colours['Foreground'])
        elif isinstance(widget, Canvas):
            widget.configure(background=colours['Background'])
        elif isinstance(widget, ttk.Label) and unicode(widget.cget('foreground')).lower() in ('gray', 'grey', '#666666', '#888888'):
            widget.configure(foreground=colours['Muted'])
        pending.extend(widget.winfo_children())
