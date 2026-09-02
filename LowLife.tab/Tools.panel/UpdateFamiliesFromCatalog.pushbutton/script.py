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

    picked = fc.show_preview_form(rows, entries, root)
    if not picked:
        script.exit()
    confirmed, do_rename = picked
    if not confirmed:
        script.exit()

    options = fc.OverwriteFamilyLoadOptions()
    temp_dir = tempfile.mkdtemp(prefix="lowlife_famcat_")

    # (family_elem, target_name, disp, src_path, catalog_name, status)
    loaded = []
    failed = []  # (target_name, disp, err)

    try:
        for family, src_path, target_name, disp, catalog_name in confirmed:
            status, payload = fc.reload_family(
                doc, src_path, target_name, temp_dir, options
            )
            if status == u"error":
                failed.append((target_name, disp, payload))
            else:
                loaded.append((payload, target_name, disp, src_path, catalog_name, status))
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)

    # Переименование по имени файла каталога + метка даты — отдельным проходом:
    # SetEntity и Family.Name требуют транзакции, а LoadFamily должен идти вне неё.
    updated = []        # (final_name, disp, iso)  — содержимое реально перезагружено
    unchanged = []      # (final_name, disp, iso)  — LoadFamily=False (совпадает)
    renamed = []        # (old_name, new_name)
    rename_failed = []  # (old_name, new_name, err)
    stamp_failed = []   # final_name

    if loaded:
        with revit.Transaction(u"Обновление семейств из каталога: имена и метки"):
            for fam_elem, target_name, disp, src_path, catalog_name, status in loaded:
                _epoch, iso = fc.file_mtime(src_path)
                final_name = target_name
                was_renamed = False

                if do_rename and fam_elem and catalog_name and catalog_name != target_name:
                    ok_rn, err_rn = fc.rename_family(doc, fam_elem, catalog_name)
                    if ok_rn:
                        renamed.append((target_name, catalog_name))
                        final_name = catalog_name
                        was_renamed = True
                    else:
                        rename_failed.append((target_name, catalog_name, err_rn))

                ok_stamp = fc.write_stamp(fam_elem, _epoch, iso, disp) if fam_elem else False
                if not ok_stamp:
                    stamp_failed.append(final_name)

                if status == u"loaded":
                    updated.append((final_name, disp, iso))
                elif not was_renamed:
                    unchanged.append((final_name, disp, iso))

    if updated:
        output.print_md(u"### Обновлены семейства ({})".format(len(updated)))
        output.print_md(u"\n".join(
            u"- **{}**  ←  `{}`  _(файл {})_".format(name, disp, iso or u"?")
            for name, disp, iso in updated
        ))
    if renamed:
        output.print_md(u"### Переименованы по файлу каталога ({})".format(len(renamed)))
        output.print_md(u"\n".join(
            u"- «{}»  →  «{}»".format(old, new) for old, new in renamed
        ))
    if unchanged:
        output.print_md(u"### Без изменений — содержимое совпадает ({})".format(len(unchanged)))
        output.print_md(u"\n".join(
            u"- **{}**  ←  `{}`  _(файл {})_".format(name, disp, iso or u"?")
            for name, disp, iso in unchanged
        ))
    if failed:
        output.print_md(u"### Не удалось загрузить ({})".format(len(failed)))
        output.print_md(u"\n".join(
            u"- **{}**  ←  `{}` — {}".format(name, disp, err)
            for name, disp, err in failed
        ))
    if rename_failed:
        output.print_md(u"### Обновлены, но не переименованы ({})".format(len(rename_failed)))
        output.print_md(u"\n".join(
            u"- «{}»  →  «{}» — {}".format(old, new, err)
            for old, new, err in rename_failed
        ))
    if stamp_failed:
        output.print_md(
            u"### Метку даты записать не удалось ({})\n{}".format(
                len(stamp_failed),
                u"\n".join(u"- {}".format(n) for n in stamp_failed)
            )
        )

    summary = [u"Готово.", u""]
    summary.append(u"Обновлено: {}".format(len(updated)))
    if renamed:
        summary.append(u"Переименовано: {}".format(len(renamed)))
    if unchanged:
        summary.append(u"Без изменений: {}".format(len(unchanged)))
    if failed:
        summary.append(u"Ошибок загрузки: {}".format(len(failed)))
    if rename_failed:
        summary.append(u"Не переименовано: {}".format(len(rename_failed)))
    if stamp_failed:
        summary.append(u"Без метки даты: {}".format(len(stamp_failed)))
    summary.append(u"")
    summary.append(u"Подробности — в окне вывода. Каждая перезагрузка — отдельный шаг отмены (Ctrl+Z).")
    forms.alert(u"\n".join(summary), title=u"Обновить семейства")

except Exception:
    forms.alert(
        u"Сбой при обновлении семейств:\n\n{}".format(traceback.format_exc()),
        title=u"Обновить семейства"
    )
