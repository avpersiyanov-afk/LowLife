# -*- coding: utf-8 -*-

__title__ = u"Поймать id\nкоманды"
__doc__ = (
    u"Диагностика авто-переименования выгрузки.\n\n"
    u"Обычный клик — включает перехват кнопок ленты (чтобы узнать id "
    u"кнопки «Экспорт» ModPlus).\n"
    u"Нажать «Экспорт» в ModPlus.\n"
    u"Shift+клик — показывает: пойманные кнопки, состояние watcher'а "
    u"(подписался ли на Idling/ItemExecuted, взведён ли, сколько тиков), "
    u"хвост лога %APPDATA%\\pyRevit\\LowLifeExportRename_watcher.log.\n\n"
    u"Если «не работает» — пришли содержимое этого окна."
)
__author__ = "Pipers"

from pyrevit import EXEC_PARAMS

from lowlife import command_probe

try:
    config_mode = bool(EXEC_PARAMS.config_mode)
except Exception:
    config_mode = False

if config_mode:
    command_probe.show_results()
else:
    command_probe.arm()
