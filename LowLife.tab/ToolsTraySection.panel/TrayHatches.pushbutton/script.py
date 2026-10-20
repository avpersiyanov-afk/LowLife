# -*- coding: utf-8 -*-
try:
    unicode  # noqa: F821 — IronPython/Python 2
except NameError:  # Python 3
    unicode = str

__title__ = u"Лючки на\nуровнях"
__author__ = "Pipers"

from pyrevit import revit, forms, script, EXEC_PARAMS

from lowlife import tray_hatch, tray_hatch_settings

doc = revit.doc
uidoc = revit.uidoc


try:
    config_mode = bool(EXEC_PARAMS.config_mode)
except Exception:
    config_mode = False

if config_mode:
    edited = tray_hatch_settings.get_settings_interactive()
    forms.alert(
        u"Отменено, настройки не изменены." if edited is None
        else u"Настройки сохранены."
    )
    script.exit()


settings = tray_hatch_settings.get_settings_silent()
tray_hatch_settings.require(settings, ["hatch_type_filter", "hatch_width_param", "hatch_length_param"])
type_filter = settings["hatch_type_filter"].strip()
width_param = settings["hatch_width_param"].strip()
length_param = settings["hatch_length_param"].strip()
margin = float(settings.get("hatch_margin_mm") or 0.0) * tray_hatch.MM_TO_FT
offset = float(settings.get("hatch_offset_mm") or 0.0) * tray_hatch.MM_TO_FT

symbols = tray_hatch.find_hatch_symbols(doc, type_filter)
if not symbols:
    forms.alert(
        u"В проекте нет загруженного семейства, в имени типа которого есть «{}».\n\n"
        u"Загрузите семейство лючка или поменяйте текст в настройках "
        u"(Shift+клик по кнопке).".format(type_filter),
        exitscript=True
    )
symbol = symbols[0]
if len(symbols) > 1:
    by_label = dict((tray_hatch.symbol_label(s), s) for s in symbols)
    picked = forms.SelectFromList.show(
        sorted(by_label), title=u"Какой лючок ставить?",
        button_name=u"Ставить", multiselect=False
    )
    if not picked:
        script.exit()
    symbol = by_label[picked]

trays, from_selection = tray_hatch.collect_trays(doc, uidoc)
if not trays:
    forms.alert(u"В модели нет кабельных лотков.", exitscript=True)
levels = tray_hatch.collect_levels(doc)
if not levels:
    forms.alert(u"В модели нет уровней.", exitscript=True)

try:
    with revit.Transaction(u"Лючки на уровнях"):
        result = tray_hatch.place_hatches(
            doc, trays, levels, symbol, width_param, length_param, margin, offset
        )
except tray_hatch.HatchError as err:
    forms.alert(unicode(err), exitscript=True)

source = u"выделенных лотков" if from_selection else u"лотков модели"
if not result.placed and not result.updated:
    forms.alert(
        u"Ни один из {} ({} шт.) не проходит через уровни — лючки не нужны.\n\n"
        u"Учитываются лотки круче 30° к горизонту, пересекающие отметку уровня "
        u"(плюс смещение из настроек).".format(source, len(trays))
    )
    script.exit()

lines = [
    u"Лючок: {}".format(tray_hatch.symbol_label(symbol)),
    u"Лотков, проходящих через уровни: {} (из {} {})".format(
        result.trays_crossing, len(trays), source),
    u"Поставлено новых лючков: {}".format(result.placed),
    u"Обновлено уже стоявших: {}".format(result.updated),
]
if result.created_types:
    lines.append(u"")
    lines.append(u"Созданы типы под размеры: {}".format(u", ".join(result.created_types)))
forms.alert(u"\n".join(lines))
