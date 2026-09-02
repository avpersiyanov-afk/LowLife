# -*- coding: utf-8 -*-

__title__ = u"Обновить\nсемейства"
__doc__ = u"Обновляет семейства выбранной категории из папки-каталога .rfa: подбор по похожему имени + перезагрузка с заменой параметров"
__author__ = "Pipers"

import os
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


def _pick_and_save_root(current):
    try:
        picked = forms.pick_folder(
            title=u"Папка-каталог семейств (.rfa, включая подпапки)"
        )
    except TypeError:
        picked = forms.pick_folder()
    if picked and os.path.isdir(picked):
        fc.save_catalog_root(picked)
        return picked
    return current if (current and os.path.isdir(current)) else None


try:
    root = fc.load_catalog_root()

    try:
        config_mode = bool(EXEC_PARAMS.config_mode)
    except Exception:
        config_mode = False

    # Shift+клик по кнопке или отсутствующий/битый путь — выбрать папку заново.
    if config_mode or not root or not os.path.isdir(root):
        root = _pick_and_save_root(root)

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

    updated = []
    failed = []

    try:
        for family, src_path, target_name, disp in confirmed:
            ok, err = fc.reload_family(doc, src_path, target_name, temp_dir, options)
            if ok:
                updated.append((target_name, disp))
            else:
                failed.append((target_name, disp, err))
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)

    if updated:
        output.print_md(u"### Обновлены семейства ({})".format(len(updated)))
        output.print_md(u"\n".join(
            u"- **{}**  ←  `{}`".format(name, disp) for name, disp in updated
        ))
    if failed:
        output.print_md(u"### Не удалось обновить ({})".format(len(failed)))
        output.print_md(u"\n".join(
            u"- **{}**  ←  `{}` — {}".format(name, disp, err)
            for name, disp, err in failed
        ))

    summary = [u"Готово.", u"", u"Обновлено семейств: {}".format(len(updated))]
    if failed:
        summary.append(u"Ошибок: {} (подробности в окне вывода)".format(len(failed)))
    summary.append(u"")
    summary.append(u"Каждая перезагрузка — отдельный шаг отмены (Ctrl+Z).")
    forms.alert(u"\n".join(summary), title=u"Обновить семейства")

except Exception:
    forms.alert(
        u"Сбой при обновлении семейств:\n\n{}".format(traceback.format_exc()),
        title=u"Обновить семейства"
    )
