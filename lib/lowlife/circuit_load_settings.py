# -*- coding: utf-8 -*-
from lowlife import settings_core

KEYS = ["conductor_mask", "voltage_param", "current_param", "power_param", "family_rules"]
SETTINGS = settings_core.TextSettings(
    file_name="LowLifeCircuitLoad_settings.json",
    button_name=u"Сохранить настройки",
    heading=u"Настройки диспетчера электрических цепей",
    transfer_label=u"Настройки нагрузки",
    fields=[
        settings_core.TextField("conductor_mask", u"Проводник", u"Маска проводника", u"Например: {mark} {section}мм²", default=u"{mark} {section}мм²", required=True),
        settings_core.TextField("voltage_param", u"Параметры оборудования", u"Параметр напряжения", default=u"Напряжение"),
        settings_core.TextField("current_param", u"Параметры оборудования", u"Параметр тока", default=u"Ток"),
        settings_core.TextField("power_param", u"Параметры оборудования", u"Параметр мощности", default=u"Мощность"),
        settings_core.TextField("family_rules", u"Параметры оборудования", u"Параметры по семействам", u"По одной строке: Семейство=Параметр", default=u""),
    ], width=760, height=520)
