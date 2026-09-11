# -*- coding: utf-8 -*-

__title__ = u"Фильтр\nвыбора"
__doc__ = (
    u"Ограничивает, что можно выбрать на активном виде, только нужными "
    u"категориями.\n\n"
    u"Обычный клик — сразу временно изолирует на виде категории, "
    u"отмеченные в прошлый раз (как штатный Isolate Category у Revit): "
    u"всё остальное скрывается. Дальше выбирайте элементы как обычно — "
    u"кликом, рамкой, Ctrl/Shift, сколько угодно раз — панель «Свойства» "
    u"работает как всегда и сразу показывает параметры. Снять изоляцию — "
    u"значок внизу окна вида -> «Reset Temporary Hide/Isolate», либо "
    u"снова нажать эту кнопку.\n\n"
    u"Shift+клик — настройка: список категорий активного вида (с числом "
    u"элементов в каждой), отметьте нужные галочками и нажмите "
    u"«Сохранить»."
)
__author__ = "Pipers"

from pyrevit import revit, EXEC_PARAMS

from lowlife import filter_selection

doc = revit.doc
uidoc = revit.uidoc
view = doc.ActiveView

try:
    config_mode = bool(EXEC_PARAMS.config_mode)
except Exception:
    config_mode = False


# ------------------------------------------------------------
# ОСНОВНОЙ СЦЕНАРИЙ
# ------------------------------------------------------------

if config_mode:
    filter_selection.configure(doc, view)
else:
    filter_selection.run(doc, uidoc, view)
