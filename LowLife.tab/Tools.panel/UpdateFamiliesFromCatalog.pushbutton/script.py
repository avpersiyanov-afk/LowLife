# -*- coding: utf-8 -*-

__title__ = u"Каталог\nTEST-99"
__doc__ = u"Тестовая версия — проверяем, обновляется ли скрипт в pyRevit."
__author__ = "Pipers"

from pyrevit import forms

forms.alert(
    u"Скрипт обновился до версии TEST-99.\n\n"
    u"Если ты видишь это окно — pyRevit подхватил новый код, "
    u"и дальше будем чинить сам скрипт.\n"
    u"Если этого окна нет — pyRevit грузит старую (кэшированную) версию.",
    title=u"TEST-99"
)

import io
import os
import tempfile

LOG_PATH = os.path.join(tempfile.gettempdir(), "lowlife_famcat_debug.txt")
try:
    with io.open(LOG_PATH, "w", encoding="utf-8") as _f:
        _f.write(u"TEST-99 — скрипт выполнился\n")
    forms.alert(u"Лог записан:\n{}".format(LOG_PATH), title=u"TEST-99")
except Exception as ex:
    forms.alert(u"Лог НЕ записан: {}".format(ex), title=u"TEST-99")
