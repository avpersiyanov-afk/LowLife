# -*- coding: utf-8 -*-

__title__ = u"Обновить\nсемейства"
__doc__ = u"Обновляет семейства выбранной категории из папки-каталога .rfa: подбор по похожему имени + перезагрузка с заменой параметров. Shift+клик — сменить папку каталога."
__author__ = "Pipers"

import shutil
import tempfile
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

    # Shift+клик (config_mode) или отсутствующий/битый путь — выбрать папку.
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
        title=u"Категория семейств для обновления",
        button_name=u"Далее",
        multiselect=False
    )
    if not chosen:
        script.exit()

    families = fc.list_families_in_category(doc, chosen.cat_id)
    if not families:
        forms.alert(u"В выбранной категории нет загружаемых семейств.", exitscript=True)

    rows = fc.build_matches(families, entries)

    confirmed = fc.show_preview_form(rows, entries, root)
    if not confirmed:
        script.exit()

    options = fc.OverwriteFamilyLoadOptions()
    temp_dir = tempfile.mkdtemp(prefix="lowlife_famcat_")

    # (family_elem, target_name, disp, src_path)
    loaded = []
    failed = []  # (target_name, disp, err)

    try:
        for family, src_path, target_name, disp in confirmed:
            ok, res = fc.reload_family(doc, src_path, target_name, temp_dir, options)
            if ok:
                loaded.append((res, target_name, disp, src_path))
            else:
                failed.append((target_name, disp, res))
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)

    # Метка даты каталога — отдельным проходом: SetEntity требует транзакции,
    # а LoadFamily выше должен идти вне неё.
    updated = []       # (target_name, disp, mtime_iso)
    stamp_failed = []  # target_name
    if loaded:
        with revit.Transaction(u"Метки даты каталога для обновлённых семейств"):
            for fam_elem, target_name, disp, src_path in loaded:
                _epoch, iso = fc.file_mtime(src_path)
                ok_stamp = fc.write_stamp(fam_elem, _epoch, iso, disp) if fam_elem else False
                updated.append((target_name, disp, iso))
                if not ok_stamp:
                    stamp_failed.append(target_name)

    if updated:
        output.print_md(u"### Обновлены семейства ({})".format(len(updated)))
        output.print_md(u"\n".join(
            u"- **{}**  ←  `{}`  _(файл {})_".format(name, disp, iso or u"?")
            for name, disp, iso in updated
        ))
    if failed:
        output.print_md(u"### Не удалось обновить ({})".format(len(failed)))
        output.print_md(u"\n".join(
            u"- **{}**  ←  `{}` — {}".format(name, disp, err)
            for name, disp, err in failed
        ))
    if stamp_failed:
        output.print_md(
            u"### Обновлены, но метку даты записать не удалось ({})\n{}".format(
                len(stamp_failed),
                u"\n".join(u"- {}".format(n) for n in stamp_failed)
            )
        )

    summary = [u"Готово.", u"", u"Обновлено семейств: {}".format(len(updated))]
    if failed:
        summary.append(u"Ошибок загрузки: {} (подробности в окне вывода)".format(len(failed)))
    if stamp_failed:
        summary.append(u"Без метки даты: {}".format(len(stamp_failed)))
    summary.append(u"")
    summary.append(u"Каждая перезагрузка — отдельный шаг отмены (Ctrl+Z).")
    forms.alert(u"\n".join(summary), title=u"Обновить семейства")

except Exception:
    forms.alert(
        u"Сбой при обновлении семейств:\n\n{}".format(traceback.format_exc()),
        title=u"Обновить семейства"
    )
