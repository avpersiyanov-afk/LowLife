# -*- coding: utf-8 -*-

__title__ = u"Актуальность\nсемейств"
__doc__ = u"Сравнивает семейства выбранной категории с папкой-каталогом .rfa по скрытой метке даты и показывает, какие устарели. Ничего не меняет. Shift+клик — сменить папку каталога."
__author__ = "Pipers"

import traceback

import clr
clr.AddReference('RevitAPI')
clr.AddReference('RevitAPIUI')

from pyrevit import revit, forms, script, EXEC_PARAMS

from lowlife import family_catalog as fc

doc = revit.doc
output = script.get_output()


try:
    try:
        config_mode = bool(EXEC_PARAMS.config_mode)
    except Exception:
        config_mode = False

    root = fc.resolve_catalog_root(force_pick=config_mode)
    if not root:
        script.exit()

    entries = fc.scan_catalog(root)
    if not entries:
        forms.alert(
            u"В каталоге не найдено ни одного .rfa:\n{}".format(root),
            exitscript=True
        )

    categories = fc.list_family_categories(doc)
    if not categories:
        forms.alert(u"В проекте нет загружаемых семейств.", exitscript=True)

    chosen = forms.SelectFromList.show(
        categories,
        title=u"Категория семейств для проверки",
        button_name=u"Проверить",
        multiselect=False
    )
    if not chosen:
        script.exit()

    families = fc.list_families_in_category(doc, chosen.cat_id)
    if not families:
        forms.alert(u"В выбранной категории нет загружаемых семейств.", exitscript=True)

    rows = fc.build_matches(families, entries)

    groups = {
        fc.STATUS_STALE: [],
        fc.STATUS_NO_STAMP: [],
        fc.STATUS_NO_CATALOG: [],
        fc.STATUS_CURRENT: [],
    }
    for r in rows:
        groups.get(r.status, groups[fc.STATUS_NO_CATALOG]).append(r)

    output.print_md(u"# Актуальность семейств — категория «{}»".format(chosen.name))
    output.print_md(u"Каталог: `{}`".format(root))

    def _dump(status, header, with_dates):
        bucket = groups.get(status) or []
        if not bucket:
            return
        output.print_md(u"## {} ({})".format(header, len(bucket)))
        lines = []
        for r in bucket:
            if with_dates:
                model_iso = (r.stamp or {}).get("iso") or u"—"
                cat_iso = r.entry.mtime_iso if r.entry else u"—"
                lines.append(
                    u"- **{}**  ←  `{}`  · в модели: {} · в каталоге: {}".format(
                        r.family_name,
                        r.entry.rel if r.entry else u"?",
                        model_iso, cat_iso
                    )
                )
            elif r.entry:
                lines.append(u"- **{}**  ←  `{}` ({}%)".format(
                    r.family_name, r.entry.rel, int(round(r.score * 100))
                ))
            else:
                lines.append(u"- **{}**".format(r.family_name))
        output.print_md(u"\n".join(lines))

    _dump(fc.STATUS_STALE, u"Устарели — файл каталога новее метки", True)
    _dump(fc.STATUS_NO_STAMP, u"Без метки — не обновлялись этой кнопкой", False)
    _dump(fc.STATUS_NO_CATALOG, u"Нет похожего файла в каталоге", False)
    _dump(fc.STATUS_CURRENT, u"Актуальны", True)

    n_stale = len(groups[fc.STATUS_STALE])
    n_nostamp = len(groups[fc.STATUS_NO_STAMP])
    forms.alert(
        u"\n".join([
            u"Проверено семейств: {}".format(len(rows)),
            u"",
            u"Устарели: {}".format(n_stale),
            u"Без метки: {}".format(n_nostamp),
            u"Нет в каталоге: {}".format(len(groups[fc.STATUS_NO_CATALOG])),
            u"Актуальны: {}".format(len(groups[fc.STATUS_CURRENT])),
            u"",
            u"Подробности — в окне вывода. Обновить: кнопка «Обновить семейства».",
        ]),
        title=u"Актуальность семейств"
    )

except Exception:
    forms.alert(
        u"Сбой при проверке актуальности:\n\n{}".format(traceback.format_exc()),
        title=u"Актуальность семейств"
    )
