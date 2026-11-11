# -*- coding: utf-8 -*-

try:
    unicode  # noqa: F821 — IronPython/Python 2
except NameError:  # Python 3
    unicode = str

__title__ = u"Внесение\nизменений"
__doc__ = (
    u"Показывает все изменения проекта (типы семейства облака изменений с "
    u"шифром, номером и датой) и ведёт пошаговое создание нового: шифр "
    u"альбома, номер изменения (по умолчанию — следующий за уже "
    u"существующими по этому шифру), дата (дд.мм.гг), код изменения (1–5) и "
    u"содержание. Создаёт новый тип семейства по маске "
    u"«имя семейства_шифр_номер», вставляет облако в точку, указанную "
    u"кликом на активном виде, и "
    u"записывает данные в параметры типа и экземпляра; порядковый номер "
    u"облака на листе проставляется автоматически (у каждого изменения на "
    u"листе — своя нумерация с 1).\n\n"
    u"Двойной клик по строке списка — вставить ещё один экземпляр этого типа: "
    u"шифр, номер и дата берутся из типа, спрашиваются код (1–5) и "
    u"содержание.\n\n"
    u"Shift+клик — настройки: семейство, маска имени типа, параметры типа "
    u"(шифр, номер, дата) и экземпляра (код, содержание, порядковый номер)."
)
__author__ = "Pipers"

from lowlife.i18n import tr

from pyrevit import revit, forms, script, EXEC_PARAMS
from lowlife import select_list

from lowlife import change_clouds
from lowlife import change_clouds_core as core
from lowlife import change_clouds_settings as settings_mod
from lowlife import change_clouds_ui
from lowlife import selection

TITLE = tr(u"Внесение изменений")

REQUIRED_KEYS = [
    u"family_name",
    u"cipher_param",
    u"number_param",
    u"date_param",
    u"code_param",
    u"content_param",
    u"order_param",
]

CODE_CHOICES = [u"1", u"2", u"3", u"4", u"5"]


try:
    config_mode = bool(EXEC_PARAMS.config_mode)
except Exception:
    config_mode = False

if config_mode:
    settings_mod.get_settings_interactive()
    script.exit()


doc = revit.doc
uidoc = revit.uidoc

settings = settings_mod.get_settings_silent()
if settings_mod.missing(settings, REQUIRED_KEYS):
    forms.alert(tr(u"Заполните настройки кнопки (семейство и имена параметров)."))
    edited = settings_mod.get_settings_interactive()
    if edited is None:
        script.exit()
    settings = edited
still_missing = settings_mod.missing(settings, REQUIRED_KEYS)
if still_missing:
    forms.alert(tr(u"Не заполнены обязательные настройки: {}").format(
        u", ".join(still_missing)), exitscript=True)

view = doc.ActiveView
if view is None:
    forms.alert(tr(u"Нет активного вида — откройте лист или план."),
                title=TITLE, exitscript=True)


def _pick_point():
    """Точка вставки облака — клик на виде. None, если отказались (Esc)."""
    return selection.pick_point(
        uidoc, tr(u"Укажите точку вставки облака изменения",
                  u"Pick a point to place the change cloud"))


def _ask_new_change(rows):
    """Пошаговый опрос «новое изменение»; None на любом отказе."""
    cipher = forms.ask_for_string(title=TITLE, prompt=tr(u"Шифр альбома:"))
    if cipher is None:
        return
    cipher = cipher.strip()
    if not cipher:
        forms.alert(tr(u"Шифр не введён."), title=TITLE)
        return

    default_number = change_clouds.suggest_next_number(rows, cipher)
    number_text = forms.ask_for_string(
        default=u"{}".format(default_number),
        title=TITLE, prompt=tr(u"Номер изменения:"))
    if number_text is None:
        return
    number = core.parse_number(number_text)
    if number is None:
        forms.alert(tr(u"Номер изменения — целое положительное число."), title=TITLE)
        return

    date_text = forms.ask_for_string(
        default=core.today_text(),
        title=TITLE, prompt=tr(u"Дата изменения (дд.мм.гг):"))
    if date_text is None:
        return
    date_text = core.parse_date(date_text)
    if date_text is None:
        forms.alert(tr(u"Дата не распознана — введите как дд.мм.гг."), title=TITLE)
        return

    code = select_list.CommandSwitchWindow.show(
        CODE_CHOICES,
        title=TITLE,
        message=tr(u"Код изменения (1–5):"))
    if code is None:
        return

    content = forms.ask_for_string(title=TITLE, prompt=tr(u"Содержание изменения:"))
    if content is None:
        return

    point = _pick_point()
    if point is None:
        return
    try:
        symbol, instance = change_clouds.create_change(
            doc, view, settings, cipher, number, date_text, code, content,
            point)
    except change_clouds.ChangeCloudsError as ex:
        message = ex.args[0] if ex.args else unicode(ex)
        forms.alert(message, title=TITLE)
        return
    except Exception as ex:
        forms.alert(u"{}".format(ex), title=TITLE)
        return
    forms.alert(tr(u"Создан тип «{}», облако вставлено на вид «{}».").format(
        change_clouds.safe_element_name(symbol),
        change_clouds.safe_element_name(view)), title=TITLE)


def _ask_instance(symbol_id):
    """Экземпляр существующего типа (двойной клик по строке списка): только
    код, содержание и точка вставки — шифр/номер/дата уже в типе."""
    code = select_list.CommandSwitchWindow.show(
        CODE_CHOICES,
        title=TITLE,
        message=tr(u"Код изменения (1–5):"))
    if code is None:
        return
    content = forms.ask_for_string(title=TITLE, prompt=tr(u"Содержание изменения:"))
    if content is None:
        return
    point = _pick_point()
    if point is None:
        return
    try:
        symbol, instance = change_clouds.place_instance(
            doc, view, settings, symbol_id, code, content, point)
    except change_clouds.ChangeCloudsError as ex:
        message = ex.args[0] if ex.args else unicode(ex)
        forms.alert(message, title=TITLE)
        return
    except Exception as ex:
        forms.alert(u"{}".format(ex), title=TITLE)
        return
    forms.alert(tr(u"Облако «{}» вставлено на вид «{}».").format(
        change_clouds.safe_element_name(symbol),
        change_clouds.safe_element_name(view)), title=TITLE)


while True:
    family, rows = change_clouds.list_changes(doc, settings)
    family_name = settings.get(u"family_name") if family is not None else None
    action = change_clouds_ui.show_changes_window(family_name, rows)
    if isinstance(action, tuple) and action[0] == u"instance":
        _ask_instance(action[1])
        continue
    if action == u"settings":
        edited = settings_mod.get_settings_interactive()
        if edited is not None:
            settings = edited
        continue
    if action == u"new":
        if family is None:
            forms.alert(tr(u"Семейство «{}» не загружено в проект — сначала "
                           u"загрузите его или проверьте настройки.").format(
                settings.get(u"family_name") or u""), title=TITLE)
            continue
        _ask_new_change(rows)
        continue
    break
