# -*- coding: utf-8 -*-
"""Shift+клик по кнопке «Семейства из каталога» — сменить папку-каталог
и включить/выключить тихий мониторинг актуальности при открытии проекта."""

from pyrevit import forms

from lowlife import family_catalog as fc

old = fc.load_catalog_root()
new = fc.pick_catalog_root(old)

if new and new != old:
    part = u"Новая папка-каталог семейств:\n{}".format(new)
elif new:
    part = u"Папка-каталог не изменена:\n{}".format(new)
else:
    part = u"Папка-каталог не задана."

# Тихий мониторинг: при открытии проекта проверять актуальность семейств
# (быстро, по скрытым меткам, без сканирования каталога) и показывать toast.
cur = fc.load_monitor_enabled()
choice = forms.alert(
    u"{}\n\nТихий мониторинг при открытии проекта сейчас: {}.\n"
    u"Проверяет по скрытым меткам (без сканирования каталога) и, если есть "
    u"устаревшие семейства, показывает уведомление.".format(
        part, u"ВКЛЮЧЁН" if cur else u"выключен"
    ),
    title=u"Семейства из каталога — настройки",
    options=[u"Включить мониторинг", u"Выключить мониторинг", u"Оставить как есть"]
)

if choice == u"Включить мониторинг":
    fc.save_monitor_enabled(True)
    forms.alert(u"Мониторинг при открытии проекта включён.",
                title=u"Семейства из каталога")
elif choice == u"Выключить мониторинг":
    fc.save_monitor_enabled(False)
    forms.alert(u"Мониторинг при открытии проекта выключен.",
                title=u"Семейства из каталога")
