# -*- coding: utf-8 -*-

__title__ = u"Поймать id\nкоманды"
__doc__ = (
    u"Диагностика: узнать точный идентификатор кнопки «Экспорт» ModPlus "
    u"(или любой другой кнопки ленты). Нужен, чтобы сделать хук автозапуска "
    u"переименования выгрузки, а журналы Revit не пишутся.\n\n"
    u"Порядок:\n"
    u"1. Обычный клик по этой кнопке — включает перехват.\n"
    u"2. Нажать кнопку «Экспорт» в ModPlus.\n"
    u"3. Shift+клик по этой кнопке — покажет пойманный id (и запишет его "
    u"в лог %APPDATA%\\pyRevit\\LowLifeExportRename_commands.log)."
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
