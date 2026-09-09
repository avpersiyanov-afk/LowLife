# -*- coding: utf-8 -*-

__title__ = u"Помещение\nиз связи"
__doc__ = (
    u"Переносит значение помещения из связанной модели в параметр "
    u"выбранных элементов активного документа. Для каждого выбранного "
    u"элемента ищется помещение (Room) во всех подключённых связях, в "
    u"которое попадает точка/центр элемента, и по МАСКЕ собирается "
    u"строка из параметров этого помещения — она пишется в целевой "
    u"параметр.\n\n"
    u"Shift+клик — настройки: параметр-приёмник в этой модели и маска "
    u"(например «Имя (Номер)» или «Имя, Номер»)."
)
__author__ = "Pipers"

from pyrevit import revit, forms, script, EXEC_PARAMS

from lowlife import room_info_settings
from lowlife.room_info import apply_room_info

doc = revit.doc
uidoc = revit.uidoc


try:
    config_mode = bool(EXEC_PARAMS.config_mode)
except Exception:
    config_mode = False

if config_mode:
    edited = room_info_settings.get_settings_interactive()
    forms.alert(
        u"Отменено, настройки не изменены." if edited is None
        else u"Настройки сохранены."
    )
    script.exit()


settings = room_info_settings.get_settings_silent()
room_info_settings.require(settings, ["target_param_name", "room_mask"])

selected_ids = uidoc.Selection.GetElementIds()

if not selected_ids:
    forms.alert(
        u"Сначала выберите элементы в модели, потом запустите кнопку.\n\n"
        u"Настройки (параметр-приёмник и маска) — Shift+клик по кнопке.",
        exitscript=True
    )

elements = [doc.GetElement(eid) for eid in selected_ids]

with revit.Transaction(u"Помещение из связи"):
    results = apply_room_info(
        doc, elements,
        settings["target_param_name"],
        settings["room_mask"]
    )

written = [r for r in results if r[1] == "written"]
not_found = [r for r in results if r[1] == "not_found"]
no_point = [r for r in results if r[1] == "no_point"]
no_param = [r for r in results if r[1] == "no_param"]
write_error = [r for r in results if r[1] == "write_error"]

forms.alert(
    u"Готово.\n\n"
    u"Записано: {}\n"
    u"Помещение не найдено: {}\n"
    u"Нет точки расположения: {}\n"
    u"Нет параметра «{}»: {}\n"
    u"Ошибка записи: {}".format(
        len(written), len(not_found), len(no_point),
        settings["target_param_name"], len(no_param),
        len(write_error)
    )
)
