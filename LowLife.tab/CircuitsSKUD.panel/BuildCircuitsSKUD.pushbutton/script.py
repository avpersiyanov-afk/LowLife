# -*- coding: utf-8 -*-
__title__ = u"Цепи\nСКУД"
__doc__ = (
    u"Ручное построение цепей СКУД: выберите панель (контроллер), затем "
    u"устройства — кнопка создаёт отдельную электрическую цепь на каждое "
    u"устройство («домашний прогон» без промежуточных узлов). Тип цепи по "
    u"умолчанию — Security, можно поменять в диалоге при запуске."
)
__author__ = "Pipers"

from lowlife.manual_circuits import run_manual_circuit_button

run_manual_circuit_button(u"СКУД", "Security")
