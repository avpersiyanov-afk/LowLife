# -*- coding: utf-8 -*-
"""
Обновление загружаемых семейств выбранной категории из папки-каталога
.rfa: подбор файла по похожему имени + перезагрузка семейства с заменой
значений параметров (overwrite parameter values).

Что делает кнопка «Обновить семейства» (Tools.panel):
1. запоминает путь к корневой папке каталога в
   %APPDATA%\\pyRevit\\LowLifeFamilyCatalog_settings.json (тот же подход,
   что у scs_settings.py — простой JSON, а не pyrevit.script.get_config());
2. рекурсивно собирает все .rfa из каталога (подпапки тоже), пропуская
   резервные копии Revit вида «Имя.0001.rfa»;
3. по выбранной пользователем категории берёт загруженные в проект
   семейства и для каждого ищет в каталоге файл с самым похожим именем
   (коэффициент Сёренсена—Дайса по буквенным биграммам нормализованных
   имён — без внешних зависимостей);
4. показывает таблицу «семейство → файл каталога (N%)» с галочками, где
   можно вручную сменить файл;
5. для отмеченных строк копирует .rfa во временный файл, ПЕРЕИМЕНОВАННЫЙ
   в имя семейства модели (Revit сопоставляет семейство при загрузке по
   имени файла), и вызывает Document.LoadFamily с IFamilyLoadOptions,
   возвращающим overwriteParameterValues = True — так значения параметров
   типов берутся из файла каталога.

Document.LoadFamily управляет собственной транзакцией и не должен
вызываться внутри открытой транзакции, поэтому кнопка не оборачивает
цикл загрузки в revit.Transaction — каждая перезагрузка семейства
является отдельным шагом отмены.
"""

import os
import io
import json
import shutil

import clr
clr.AddReference('RevitAPI')
clr.AddReference('PresentationFramework')
clr.AddReference('PresentationCore')

from Autodesk.Revit.DB import (
    FilteredElementCollector, Family, Element, ElementId,
    IFamilyLoadOptions, FamilySource
)

from pyrevit import forms

from System.Windows import (
    Window, WindowStartupLocation, Thickness,
    FontWeights, HorizontalAlignment, VerticalAlignment, TextWrapping
)
from System.Windows.Controls import (
    StackPanel, TextBlock, Button, CheckBox, Orientation, DockPanel, Dock,
    ScrollViewer, ScrollBarVisibility
)
from System.Windows.Media import Brushes


SETTINGS_FILE_NAME = "LowLifeFamilyCatalog_settings.json"
CATALOG_ROOT_KEY = "catalog_root"

# Порог, при котором строка предпросмотра включается галочкой сразу.
AUTO_CHECK_SCORE = 0.72

# Недопустимые в имени файла символы (заменяем на "_" во временном .rfa).
_BAD_FILENAME_CHARS = u'\\/:*?"<>|'


# --------------------------------------------------------------------------
# Хранение пути к каталогу
# --------------------------------------------------------------------------

def _settings_file_path():
    appdata = os.environ.get("APPDATA") or os.path.expanduser("~")
    folder = os.path.join(appdata, "pyRevit")

    if not os.path.isdir(folder):
        try:
            os.makedirs(folder)
        except:
            pass

    return os.path.join(folder, SETTINGS_FILE_NAME)


def _read_all():
    path = _settings_file_path()

    if not os.path.isfile(path):
        return {}

    try:
        with io.open(path, "r", encoding="utf-8") as f:
            text = f.read()
        if not text.strip():
            return {}
        return json.loads(text)
    except:
        return {}


def _write_all(data):
    path = _settings_file_path()

    try:
        with io.open(path, "w", encoding="utf-8") as f:
            f.write(unicode(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True)))
    except:
        forms.alert(u"Не удалось сохранить настройки каталога семейств:\n{}".format(path))


def load_catalog_root():
    """Сохранённый путь к корневой папке каталога либо пустая строка."""
    return _read_all().get(CATALOG_ROOT_KEY, u"") or u""


def save_catalog_root(path):
    data = _read_all()
    data[CATALOG_ROOT_KEY] = unicode(path or u"")
    _write_all(data)


# --------------------------------------------------------------------------
# Имена: нормализация и похожесть
# --------------------------------------------------------------------------

def _safe_element_name(el):
    """
    Имя элемента через Element.Name.GetValue(el): прямой el.Name в
    IronPython у Family/FamilySymbol падает с ошибкой неоднозначного
    связывания и незаметно уходит в except (см. scs_settings._safe_element_name).
    """
    try:
        return Element.Name.GetValue(el)
    except:
        try:
            return el.Name
        except:
            return None


def _norm(s):
    """Нижний регистр, только буквы и цифры (убирает пробелы, «_», «-», «.» и т.п.)."""
    s = unicode(s or u"").lower().strip()
    return u"".join(ch for ch in s if ch.isalnum())


def _bigrams(s):
    if len(s) < 2:
        return set([s]) if s else set()
    return set(s[i:i + 2] for i in range(len(s) - 1))


def similarity(a, b):
    """
    Похожесть имён 0..1 — коэффициент Сёренсена—Дайса по буквенным
    биграммам нормализованных имён. Точное совпадение после нормализации
    даёт 1.0; если одно имя целиком входит в другое — не ниже 0.9.
    Своя реализация вместо difflib — чтобы не зависеть от полноты
    стандартной библиотеки движка pyRevit.
    """
    na, nb = _norm(a), _norm(b)
    if not na or not nb:
        return 0.0
    if na == nb:
        return 1.0

    ba, bb = _bigrams(na), _bigrams(nb)
    denom = len(ba) + len(bb)
    dice = (2.0 * len(ba & bb) / denom) if denom else 0.0

    if na in nb or nb in na:
        dice = max(dice, 0.9)

    return dice


# --------------------------------------------------------------------------
# Каталог .rfa
# --------------------------------------------------------------------------

def _is_backup_rfa(filename):
    """«Имя.0001.rfa» — резервная копия, создаваемая Revit; в каталог не берём."""
    low = filename.lower()
    if not low.endswith(".rfa"):
        return False
    stem = low[:-4]
    tail = stem.rsplit(".", 1)[-1] if "." in stem else u""
    return len(tail) == 4 and tail.isdigit()


class CatalogEntry(object):
    """Файл семейства из каталога."""

    def __init__(self, path, root):
        self.path = path
        self.name = os.path.splitext(os.path.basename(path))[0]
        try:
            self.rel = os.path.relpath(path, root)
        except:
            self.rel = os.path.basename(path)

    def __str__(self):
        return self.rel


def scan_catalog(root):
    """Все .rfa из root и его подпапок (без резервных копий). Список CatalogEntry."""
    entries = []
    seen = set()

    for dirpath, _dirnames, filenames in os.walk(root):
        for fn in filenames:
            if not fn.lower().endswith(".rfa") or _is_backup_rfa(fn):
                continue
            full = os.path.join(dirpath, fn)
            key = os.path.normcase(os.path.abspath(full))
            if key in seen:
                continue
            seen.add(key)
            entries.append(CatalogEntry(full, root))

    entries.sort(key=lambda e: e.rel.lower())
    return entries


# --------------------------------------------------------------------------
# Семейства проекта
# --------------------------------------------------------------------------

def _iter_loadable_families(doc):
    for fam in FilteredElementCollector(doc).OfClass(Family):
        try:
            if fam.IsInPlace:
                continue
        except:
            pass
        try:
            cat = fam.FamilyCategory
        except:
            cat = None
        if cat is None:
            continue
        yield fam, cat


class CategoryOption(object):
    """Категория с числом загружаемых семейств — для forms.SelectFromList."""

    def __init__(self, cat, count):
        self.cat_id = cat.Id
        try:
            base = cat.Name
        except:
            base = _safe_element_name(cat)
        base = base or u"?"
        self.sort_name = base.lower()
        self.name = u"{} ({})".format(base, count)

    def __str__(self):
        return self.name


def list_family_categories(doc):
    """CategoryOption для каждой категории, где есть загружаемые (не in-place) семейства."""
    cats = {}
    counts = {}

    for fam, cat in _iter_loadable_families(doc):
        cid = cat.Id.IntegerValue
        cats[cid] = cat
        counts[cid] = counts.get(cid, 0) + 1

    options = [CategoryOption(cats[cid], counts[cid]) for cid in cats]
    options.sort(key=lambda o: o.sort_name)
    return options


def list_families_in_category(doc, cat_id):
    """Загружаемые семейства заданной категории (cat_id — ElementId)."""
    target = cat_id.IntegerValue
    result = []

    for fam, cat in _iter_loadable_families(doc):
        if cat.Id.IntegerValue == target:
            result.append(fam)

    result.sort(key=lambda f: (_safe_element_name(f) or u"").lower())
    return result


class MatchRow(object):
    """Строка сопоставления: семейство модели и подобранный файл каталога."""

    def __init__(self, family, family_name, entry, score):
        self.family = family
        self.family_name = family_name
        self.entry = entry          # CatalogEntry или None
        self.score = score          # 0..1


def build_matches(families, entries):
    """
    Для каждого семейства — лучший по имени файл каталога. Сортировка:
    сперва с наибольшей похожестью, затем по имени семейства.
    """
    rows = []

    for fam in families:
        fam_name = _safe_element_name(fam) or u"?"
        best = None
        best_score = 0.0

        for e in entries:
            sc = similarity(fam_name, e.name)
            if sc > best_score:
                best_score = sc
                best = e

        rows.append(MatchRow(fam, fam_name, best, best_score))

    rows.sort(key=lambda r: (-r.score, r.family_name.lower()))
    return rows


# --------------------------------------------------------------------------
# Перезагрузка семейства с заменой параметров
# --------------------------------------------------------------------------

class OverwriteFamilyLoadOptions(IFamilyLoadOptions):
    """
    IFamilyLoadOptions, всегда разрешающий перезапись значений параметров
    из загружаемого файла (overwriteParameterValues = True). Для общих
    семейств источником берётся сам загружаемый файл (FamilySource.Family).
    """

    def OnFamilyFound(self, familyInUse, overwriteParameterValues):
        overwriteParameterValues.Value = True
        return True

    def OnSharedFamilyFound(self, sharedFamily, familyInUse, source, overwriteParameterValues):
        source.Value = FamilySource.Family
        overwriteParameterValues.Value = True
        return True


def _safe_filename(name):
    out = name
    for ch in _BAD_FILENAME_CHARS:
        out = out.replace(ch, u"_")
    return out.strip() or u"family"


def reload_family(doc, src_path, target_family_name, temp_dir, options):
    """
    Перезагружает семейство target_family_name из файла src_path с заменой
    параметров. Файл копируется во temp_dir под именем «<имя семейства>.rfa»,
    т.к. Revit при загрузке сопоставляет семейство по имени файла — так
    файл каталога с другим именем всё равно обновит нужное семейство
    модели, а не создаст новое.

    Возвращает (True, None) при успехе либо (False, "текст ошибки").
    """
    dst = os.path.join(temp_dir, _safe_filename(target_family_name) + u".rfa")

    try:
        shutil.copyfile(src_path, dst)
    except Exception as ex:
        return (False, u"копирование во временный файл: {}".format(ex))

    try:
        res = doc.LoadFamily(dst, options)
    except Exception as ex:
        return (False, u"{}".format(ex))

    ok = bool(res[0]) if isinstance(res, tuple) else bool(res)
    if not ok:
        return (False, u"Revit отклонил загрузку (LoadFamily вернул False)")

    return (True, None)


# --------------------------------------------------------------------------
# Окно предпросмотра
# --------------------------------------------------------------------------

class EntryOption(object):
    """CatalogEntry для forms.SelectFromList при ручной смене файла."""

    def __init__(self, entry):
        self.entry = entry
        self.name = entry.rel

    def __str__(self):
        return self.name


def show_preview_form(rows, entries, catalog_root):
    """
    Таблица «семейство → файл каталога (N%)» с галочками. Возвращает список
    (family, src_path, target_family_name, display) для отмеченных строк
    либо None, если пользователь отменил.
    """
    result = {"confirmed": None}
    entry_options = [EntryOption(e) for e in entries]

    win = Window()
    win.Title = u"Обновление семейств из каталога"
    win.Width = 940
    win.Height = 720
    win.WindowStartupLocation = WindowStartupLocation.CenterScreen
    # Topmost намеренно не ставим — иначе forms.SelectFromList (кнопка
    # «Файл…») открывается позади этого окна (см. scs_settings).

    outer = DockPanel()
    outer.LastChildFill = True

    root_panel = StackPanel()
    root_panel.Margin = Thickness(16)

    title = TextBlock()
    title.Text = u"Отметьте семейства для обновления"
    title.FontSize = 16
    title.FontWeight = FontWeights.Bold
    title.Margin = Thickness(0, 0, 0, 4)
    root_panel.Children.Add(title)

    hint = TextBlock()
    hint.Text = (
        u"Каталог: {}\n"
        u"Отмеченные семейства перезагружаются из подобранного файла с заменой "
        u"значений параметров. «Файл…» — указать другой файл каталога вручную. "
        u"Уже отмечены совпадения от {}%.".format(
            catalog_root, int(round(AUTO_CHECK_SCORE * 100))
        )
    )
    hint.FontSize = 11
    hint.Foreground = Brushes.Gray
    hint.TextWrapping = TextWrapping.Wrap
    hint.Margin = Thickness(0, 0, 0, 10)
    root_panel.Children.Add(hint)

    row_states = []

    for r in rows:
        rowp = StackPanel()
        rowp.Orientation = Orientation.Horizontal
        rowp.Margin = Thickness(0, 3, 0, 0)

        cb = CheckBox()
        cb.Content = r.family_name
        cb.Width = 300
        cb.VerticalAlignment = VerticalAlignment.Center

        arrow = TextBlock()
        arrow.Text = u"→"
        arrow.Margin = Thickness(6, 0, 6, 0)
        arrow.VerticalAlignment = VerticalAlignment.Center

        tgt = TextBlock()
        tgt.Width = 380
        tgt.TextWrapping = TextWrapping.Wrap
        tgt.VerticalAlignment = VerticalAlignment.Center

        score_tb = TextBlock()
        score_tb.Width = 55
        score_tb.VerticalAlignment = VerticalAlignment.Center
        score_tb.Foreground = Brushes.Gray

        st = {
            "row": r,
            "cb": cb,
            "tgt_tb": tgt,
            "path": r.entry.path if r.entry else None,
            "disp": r.entry.rel if r.entry else None,
        }

        if r.entry:
            score_tb.Text = u"{}%".format(int(round(r.score * 100)))
            tgt.Text = r.entry.rel
            cb.IsChecked = r.score >= AUTO_CHECK_SCORE
        else:
            score_tb.Text = u"—"
            tgt.Text = u"(файл не подобран)"
            tgt.Foreground = Brushes.Gray
            cb.IsChecked = False

        pick = Button()
        pick.Content = u"Файл…"
        pick.Padding = Thickness(8, 2, 8, 2)
        pick.Margin = Thickness(8, 0, 0, 0)

        def on_pick(sender, args, st=st):
            sel = forms.SelectFromList.show(
                sorted(entry_options, key=lambda o: o.name.lower()),
                title=u"Файл каталога для «{}»".format(st["row"].family_name),
                button_name=u"Выбрать",
                multiselect=False
            )
            if sel:
                st["path"] = sel.entry.path
                st["disp"] = sel.entry.rel
                st["tgt_tb"].Text = sel.entry.rel
                st["tgt_tb"].Foreground = Brushes.Black
                st["cb"].IsChecked = True

        pick.Click += on_pick

        rowp.Children.Add(cb)
        rowp.Children.Add(arrow)
        rowp.Children.Add(tgt)
        rowp.Children.Add(score_tb)
        rowp.Children.Add(pick)
        root_panel.Children.Add(rowp)
        row_states.append(st)

    # --- кнопки внизу ---

    buttons = StackPanel()
    buttons.Orientation = Orientation.Horizontal
    buttons.HorizontalAlignment = HorizontalAlignment.Right
    buttons.Margin = Thickness(16, 8, 16, 12)
    DockPanel.SetDock(buttons, Dock.Bottom)

    check_all_btn = Button()
    check_all_btn.Content = u"Отметить все"
    check_all_btn.Padding = Thickness(10, 4, 10, 4)
    check_all_btn.Margin = Thickness(0, 0, 8, 0)

    uncheck_all_btn = Button()
    uncheck_all_btn.Content = u"Снять все"
    uncheck_all_btn.Padding = Thickness(10, 4, 10, 4)
    uncheck_all_btn.Margin = Thickness(0, 0, 8, 0)

    cancel_btn = Button()
    cancel_btn.Content = u"Отмена"
    cancel_btn.Padding = Thickness(10, 4, 10, 4)
    cancel_btn.Margin = Thickness(0, 0, 8, 0)

    ok_btn = Button()
    ok_btn.Content = u"Обновить отмеченные"
    ok_btn.Padding = Thickness(10, 4, 10, 4)
    ok_btn.FontWeight = FontWeights.Bold

    def on_check_all(sender, args):
        for st in row_states:
            if st["path"]:
                st["cb"].IsChecked = True

    def on_uncheck_all(sender, args):
        for st in row_states:
            st["cb"].IsChecked = False

    def on_ok(sender, args):
        confirmed = []
        for st in row_states:
            if st["cb"].IsChecked and st["path"]:
                confirmed.append((
                    st["row"].family,
                    st["path"],
                    st["row"].family_name,
                    st["disp"],
                ))
        result["confirmed"] = confirmed
        win.Close()

    def on_cancel(sender, args):
        win.Close()

    check_all_btn.Click += on_check_all
    uncheck_all_btn.Click += on_uncheck_all
    ok_btn.Click += on_ok
    cancel_btn.Click += on_cancel

    buttons.Children.Add(check_all_btn)
    buttons.Children.Add(uncheck_all_btn)
    buttons.Children.Add(cancel_btn)
    buttons.Children.Add(ok_btn)

    scroll = ScrollViewer()
    scroll.VerticalScrollBarVisibility = ScrollBarVisibility.Auto
    scroll.Content = root_panel

    outer.Children.Add(buttons)
    outer.Children.Add(scroll)

    win.Content = outer
    win.ShowDialog()

    return result["confirmed"]
