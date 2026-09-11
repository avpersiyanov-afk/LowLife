# -*- coding: utf-8 -*-

__title__ = u"Фильтр\nвыбора"
__doc__ = (
    u"Выделение элементов на активном виде, ограниченное только нужными "
    u"категориями.\n\n"
    u"Обычный клик — сразу запускает выбор по категориям, отмеченным в "
    u"прошлый раз, без вопросов: выделяйте элементы кликом и/или рамкой "
    u"— подхватятся только они. Нажмите Enter (или ПКМ -> «Готово»), "
    u"чтобы завершить — выделение останется активным в Revit, а вкладка "
    u"«Свойства» сама станет активной для правки параметров.\n\n"
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
