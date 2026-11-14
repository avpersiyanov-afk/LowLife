# -*- coding: utf-8 -*-
"""Выбор типов и текста задания АР; общие окна и JSON — settings_core."""
try:
    unicode
except NameError:
    unicode = str

from lowlife import settings_core, equipment_tags_settings
from lowlife.cloud_io import dumps_ascii
from lowlife.i18n import tr

FILE_NAME = 'LowLifeARTaskAnnotations_settings.json'
STORE = settings_core.JsonStore(FILE_NAME)


def type_key(symbol):
    """Имена вместо ElementId: настройка переносится между проектами."""
    from lowlife.equipment_tags import id_int, _safe_name
    # Revit 2024+ возвращает System.Int64: IronPython JSON не считает его
    # обычным числом. Нормализуем и используем общий безопасный ASCII JSON.
    return 'text:' + dumps_ascii([int(id_int(symbol.Category.Id)),
                                 unicode(symbol.FamilyName), unicode(_safe_name(symbol))])


def text_for(symbol, settings):
    key = type_key(symbol)
    if key not in settings.get('selected_types', []):
        return u''
    value = settings.get(key, u'')
    return unicode(value or u'').replace(u'\\n', u'\r').replace(u'\r\n', u'\r').replace(u'\n', u'\r')


def load():
    values = dict(STORE.read())
    for field in equipment_tags_settings.SETTINGS.fields:
        values[field.key] = field.coerce(values.get(field.key, field.default))
    return values


def edit(doc):
    from Autodesk.Revit.DB import CategoryType, FilteredElementCollector, TextNoteType
    from pyrevit import forms
    from lowlife import select_list, scs_settings, settings_transfer
    from lowlife.equipment_tags import _safe_name

    while True:
        saved = load()
        symbols = [s for s in scs_settings.list_symbols_by_categories(doc)
                   if s.Category is not None and s.Category.CategoryType == CategoryType.Model]
        options = []
        for symbol in symbols:
            label = u'{} | {}'.format(symbol.Category.Name, scs_settings.TypeOption(symbol).name)
            option = forms.TemplateListItem(label, checked=type_key(symbol) in saved.get('selected_types', []))
            option.symbol = symbol
            options.append(option)
        chosen = select_list.SelectFromList.show(
            sorted(options, key=lambda o: o.name), multiselect=True, return_all=True,
            title=tr(u'Задание АР — выберите типы семейств', u'AR task — select family types'),
            button_name=tr(u'Далее — текст и отступы', u'Next — text and spacing'))
        if chosen is None:
            return None
        selected = [option.symbol for option in chosen if option.state]
        note_types = sorted(list(FilteredElementCollector(doc).OfClass(TextNoteType)), key=_safe_name)
        if not note_types:
            forms.alert(tr(u'В проекте нет типов текста.', u'The project has no text types.'))
            return None
        fields = [settings_core.ChoiceField(
            'text_type_name', u'', tr(u'Тип текста', u'Text type'),
            [(_safe_name(t), _safe_name(t)) for t in note_types])]
        fields.extend(equipment_tags_settings.SETTINGS.fields)
        for symbol in selected:
            fields.append(settings_core.TextField(
                type_key(symbol), u'{} | {}'.format(symbol.Category.Name, scs_settings.TypeOption(symbol).name),
                tr(u'Текст аннотации (пусто — не подписывать)', u'Annotation text (blank — skip)'),
                hint=tr(u'Для переноса строки введите \\n.', u'Enter \\n for a line break.')))
        editor = settings_core.TextSettings(
            FILE_NAME, u'Маркировка задания для АР',
            tr(u'Текст задания для каждого типоразмера', u'Task text for each family type'),
            tr(u'маркировки задания для АР', u'AR task annotations'), fields,
            intro=tr(u'Расстояния — в мм на листе. Для изменения списка типов снова откройте Shift+клик.',
                     u'Distances are in paper mm. Shift-click again to change the type selection.'),
            height=700)
        edited = editor.show_settings_form(editor.load_saved_values())
        if edited == settings_transfer.RELOAD:
            continue
        if edited is None:
            return None
        edited['selected_types'] = [type_key(symbol) for symbol in selected]
        STORE.update(edited)
        return load()
