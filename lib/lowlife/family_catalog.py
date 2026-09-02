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
   резервные копии Revit вида «Имя.0001.rfa» и папки с «архив» в имени
   (EXCLUDED_DIR_KEYWORDS);
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
   типов берутся из файла каталога;
6. если в окне включён флажок «переименовывать» и имя файла каталога
   отличается от имени семейства модели — после загрузки семейство модели
   переименовывается в имя файла каталога (rename_family, в транзакции).
   Это и есть сценарий «в каталоге семейство переименовали»: LoadFamily
   при совпадающем содержимом вернёт False (status="unchanged", НЕ ошибка),
   а нужное изменение — само переименование.

Document.LoadFamily управляет собственной транзакцией и не должен
вызываться внутри открытой транзакции, поэтому кнопка не оборачивает
цикл загрузки в revit.Transaction — каждая перезагрузка семейства
является отдельным шагом отмены.

После успешной загрузки в сам элемент Family пишется скрытая метка
(ExtensibleStorage, схема SCHEMA_GUID) с датой изменения файла .rfa в
каталоге. Кнопка «Актуальность семейств» потом сравнивает эту метку с
текущей датой файла и показывает, какие семейства устарели. Запись метки
идёт SetEntity — это уже требует открытой транзакции, поэтому пометка
выполняется отдельным проходом ПОСЛЕ всех LoadFamily, внутри
revit.Transaction (см. write_stamp).
"""

import os
import io
import json
import shutil
import tempfile
import datetime

import clr
clr.AddReference('RevitAPI')
clr.AddReference('System')
clr.AddReference('PresentationFramework')
clr.AddReference('PresentationCore')
clr.AddReference('WindowsBase')

from Autodesk.Revit.DB import (
    FilteredElementCollector, Family, Element, ElementId,
    IFamilyLoadOptions, FamilySource, Transaction
)
from Autodesk.Revit.DB.ExtensibleStorage import (
    Schema, SchemaBuilder, AccessLevel, Entity
)

from System import Guid, String
from System.Collections.Generic import List

from pyrevit import forms

from System.Windows import (
    Window, WindowStartupLocation, Thickness,
    FontWeights, HorizontalAlignment, VerticalAlignment, TextWrapping
)
from System.Windows.Controls import (
    StackPanel, TextBlock, Button, CheckBox, Orientation, DockPanel, Dock,
    ScrollViewer, ScrollBarVisibility,
    DataGrid, DataGridCheckBoxColumn, DataGridTextColumn,
    DataGridLength, DataGridLengthUnitType,
    DataGridHeadersVisibility, DataGridGridLinesVisibility, DataGridSelectionMode
)
from System.Windows.Data import Binding, BindingMode, UpdateSourceTrigger
from System.Windows.Media import Brushes
from System.ComponentModel import ListSortDirection


SETTINGS_FILE_NAME = "LowLifeFamilyCatalog_settings.json"
CATALOG_ROOT_KEY = "catalog_root"

# Порог, при котором строка предпросмотра включается галочкой сразу.
AUTO_CHECK_SCORE = 0.72

# Ниже этой похожести имя-в-каталоге считается «не тем файлом»: подсказка
# в таблице остаётся, но статус актуальности = «нет в каталоге» (иначе
# дату метки сравнивали бы со случайным непохожим файлом).
MATCH_FLOOR = 0.45

# Недопустимые в имени файла символы (заменяем на "_" во временном .rfa).
_BAD_FILENAME_CHARS = u'\\/:*?"<>|'

# Схема скрытой метки на элементе Family (ExtensibleStorage). GUID
# фиксированный — менять нельзя, иначе старые метки перестанут читаться.
SCHEMA_GUID = Guid("d7b1e6a2-4c3f-4b9a-9e21-6f8c1a2b3c4d")
SCHEMA_NAME = "LowLifeFamilyCatalogStamp"
SCHEMA_VENDOR = "LOWLIFE"

_F_MTIME_EPOCH = "catalog_mtime_epoch"   # строка float-секунд (для сравнения)
_F_MTIME_ISO = "catalog_mtime_iso"       # "ГГГГ-ММ-ДД ЧЧ:ММ" (для человека)
_F_CATALOG_FILE = "catalog_file"         # относительный путь файла каталога
_F_UPDATED_AT = "updated_at_iso"         # когда кнопка проставила метку

# Насколько новее должен быть файл каталога, чтобы считать семейство
# устаревшим (сек) — запас против расхождения часов/округления mtime.
STALE_TOLERANCE_SEC = 90

# Статусы актуальности (assess_families / MatchRow.status).
STATUS_STALE = u"устарело"
STATUS_NO_STAMP = u"нет метки"
STATUS_CURRENT = u"актуально"
STATUS_NO_CATALOG = u"нет в каталоге"


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


def pick_catalog_root(current=None):
    """
    Диалог выбора папки-каталога + сохранение. Возвращает новый путь; если
    пользователь отменил — прежний current (когда он валиден) либо None.
    """
    try:
        picked = forms.pick_folder(
            title=u"Папка-каталог семейств (.rfa, включая подпапки)"
        )
    except TypeError:
        picked = forms.pick_folder()

    if picked and os.path.isdir(picked):
        save_catalog_root(picked)
        return picked

    if current and os.path.isdir(current):
        return current
    return None


def resolve_catalog_root(force_pick=False):
    """
    Путь к каталогу для рабочих кнопок: сохранённый; если его нет/он битый
    или force_pick=True (Shift+клик / config.py) — спросить папку и сохранить.
    Возвращает путь либо None.
    """
    root = load_catalog_root()
    if force_pick or not root or not os.path.isdir(root):
        root = pick_catalog_root(root)
    return root


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

# Папки, чьё имя содержит одно из этих слов (без учёта регистра), в обход
# каталога не заходят вместе со всем содержимым — например «Архив», «Архив 2023».
EXCLUDED_DIR_KEYWORDS = (u"архив", u"archive", u"archiv")


def _is_excluded_dir(name):
    low = unicode(name or u"").lower()
    return any(kw in low for kw in EXCLUDED_DIR_KEYWORDS)


def _is_backup_rfa(filename):
    """«Имя.0001.rfa» — резервная копия, создаваемая Revit; в каталог не берём."""
    low = filename.lower()
    if not low.endswith(".rfa"):
        return False
    stem = low[:-4]
    tail = stem.rsplit(".", 1)[-1] if "." in stem else u""
    return len(tail) == 4 and tail.isdigit()


def file_mtime(path):
    """(epoch_float, "ГГГГ-ММ-ДД ЧЧ:ММ") для файла либо (None, None)."""
    try:
        epoch = os.path.getmtime(path)
    except:
        return (None, None)
    try:
        iso = datetime.datetime.fromtimestamp(epoch).strftime("%Y-%m-%d %H:%M")
    except:
        iso = u""
    return (epoch, iso)


class CatalogEntry(object):
    """Файл семейства из каталога."""

    def __init__(self, path, root):
        self.path = path
        self.name = os.path.splitext(os.path.basename(path))[0]
        try:
            self.rel = os.path.relpath(path, root)
        except:
            self.rel = os.path.basename(path)
        self.mtime, self.mtime_iso = file_mtime(path)

    def __str__(self):
        return self.rel


def scan_catalog(root):
    """
    Все .rfa из root и его подпапок (без резервных копий Revit). Папки,
    чьё имя содержит «архив» (см. EXCLUDED_DIR_KEYWORDS), пропускаются
    целиком. Список CatalogEntry.
    """
    entries = []
    seen = set()

    for dirpath, dirnames, filenames in os.walk(root):
        # правим dirnames на месте — os.walk не зайдёт в отброшенные папки
        dirnames[:] = [d for d in dirnames if not _is_excluded_dir(d)]

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
# Скрытая метка даты каталога на элементе Family (ExtensibleStorage)
# --------------------------------------------------------------------------

def _get_or_create_schema():
    schema = Schema.Lookup(SCHEMA_GUID)
    if schema is not None:
        return schema

    sb = SchemaBuilder(SCHEMA_GUID)
    sb.SetSchemaName(SCHEMA_NAME)
    sb.SetVendorId(SCHEMA_VENDOR)
    sb.SetReadAccessLevel(AccessLevel.Public)
    sb.SetWriteAccessLevel(AccessLevel.Public)
    # Все поля строковые — так у SimpleField не требуется указывать
    # единицы/спецификацию (обязательно для double/int в Revit 2022+).
    sb.AddSimpleField(_F_MTIME_EPOCH, String)
    sb.AddSimpleField(_F_MTIME_ISO, String)
    sb.AddSimpleField(_F_CATALOG_FILE, String)
    sb.AddSimpleField(_F_UPDATED_AT, String)
    return sb.Finish()


def read_stamp(family):
    """
    dict со скрытой меткой семейства {epoch, iso, file, updated_at} либо
    None, если метки нет. epoch — float или None.
    """
    try:
        schema = Schema.Lookup(SCHEMA_GUID)
        if schema is None:
            return None
        ent = family.GetEntity(schema)
        if ent is None or not ent.IsValid():
            return None
        epoch_str = ent.Get[String](_F_MTIME_EPOCH)
        try:
            epoch = float(epoch_str) if epoch_str else None
        except:
            epoch = None
        return {
            "epoch": epoch,
            "iso": ent.Get[String](_F_MTIME_ISO),
            "file": ent.Get[String](_F_CATALOG_FILE),
            "updated_at": ent.Get[String](_F_UPDATED_AT),
        }
    except:
        return None


def write_stamp(family, mtime_epoch, mtime_iso, catalog_file):
    """
    Пишет скрытую метку даты каталога в элемент Family. **Требует открытой
    транзакции** (SetEntity). Возвращает True/False.
    """
    try:
        schema = _get_or_create_schema()
        ent = Entity(schema)
        ent.Set[String](_F_MTIME_EPOCH, u"{}".format(mtime_epoch if mtime_epoch is not None else u""))
        ent.Set[String](_F_MTIME_ISO, mtime_iso or u"")
        ent.Set[String](_F_CATALOG_FILE, catalog_file or u"")
        ent.Set[String](_F_UPDATED_AT, datetime.datetime.now().strftime("%Y-%m-%d %H:%M"))
        family.SetEntity(ent)
        return True
    except:
        return False


def stamp_status(stamp, entry):
    """
    Статус актуальности семейства по скрытой метке и текущему файлу
    каталога: STATUS_NO_CATALOG / STATUS_NO_STAMP / STATUS_STALE / STATUS_CURRENT.
    """
    if entry is None:
        return STATUS_NO_CATALOG
    if not stamp:
        return STATUS_NO_STAMP
    stamp_epoch = stamp.get("epoch")
    if stamp_epoch is None or entry.mtime is None:
        return STATUS_NO_STAMP
    if entry.mtime > stamp_epoch + STALE_TOLERANCE_SEC:
        return STATUS_STALE
    return STATUS_CURRENT


def find_family_by_name(doc, name):
    for fam in FilteredElementCollector(doc).OfClass(Family):
        if _safe_element_name(fam) == name:
            return fam
    return None


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

    def __init__(self, family, family_name, entry, score, stamp, status):
        self.family = family
        self.family_name = family_name
        self.entry = entry          # CatalogEntry или None
        self.score = score          # 0..1
        self.stamp = stamp          # dict скрытой метки или None
        self.status = status        # STATUS_* — актуальность по метке


# Порядок статусов для сортировки/отчёта: сперва то, что требует внимания.
_STATUS_ORDER = {
    STATUS_STALE: 0,
    STATUS_NO_STAMP: 1,
    STATUS_NO_CATALOG: 2,
    STATUS_CURRENT: 3,
}


def build_matches(families, entries):
    """
    Для каждого семейства — лучший по имени файл каталога + статус
    актуальности по скрытой метке. Сортировка: сперва устаревшие/без
    метки, затем по убыванию похожести и имени.
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

        stamp = read_stamp(fam)
        confident = best if best_score >= MATCH_FLOOR else None
        status = stamp_status(stamp, confident)
        rows.append(MatchRow(fam, fam_name, best, best_score, stamp, status))

    rows.sort(key=lambda r: (
        _STATUS_ORDER.get(r.status, 9), -r.score, r.family_name.lower()
    ))
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


def _set_element_name(el, name):
    """
    Присвоение имени элементу: el.Name = ... у Family/FamilySymbol в
    IronPython падает с ошибкой неоднозначного связывания так же, как
    чтение (см. _safe_element_name), поэтому сначала пробуем статическое
    свойство через рефлексию.
    """
    try:
        Element.Name.SetValue(el, name)
        return True
    except:
        try:
            el.Name = name
            return True
        except:
            return False


def reload_family(doc, src_path, target_family_name, temp_dir, options):
    """
    Перезагружает семейство target_family_name из файла src_path с заменой
    параметров. Файл копируется во temp_dir под именем «<имя семейства>.rfa»,
    т.к. Revit при загрузке сопоставляет семейство по имени файла — так
    файл каталога с другим именем всё равно обновит нужное семейство
    модели, а не создаст новое.

    Возвращает (status, payload):
      ("loaded",    family_element) — семейство перезагружено;
      ("unchanged", family_element) — Document.LoadFamily вернул False, т.е.
            содержимое в модели и в файле совпадает (это НЕ ошибка — часто
            бывает, когда в каталоге поменяли только имя файла: переименование
            в модель переносит вызывающий код через rename_family);
      ("error",     "текст ошибки").
    family_element нужен вызывающему коду для write_stamp / rename_family.
    """
    dst = os.path.join(temp_dir, _safe_filename(target_family_name) + u".rfa")

    try:
        shutil.copyfile(src_path, dst)
    except Exception as ex:
        return (u"error", u"копирование во временный файл: {}".format(ex))

    try:
        res = doc.LoadFamily(dst, options)
    except Exception as ex:
        return (u"error", u"{}".format(ex))

    loaded = None
    if isinstance(res, tuple):
        changed = bool(res[0])
        if len(res) > 1:
            loaded = res[1]
    else:
        changed = bool(res)

    try:
        valid = loaded is not None and loaded.IsValidObject
    except:
        valid = False
    if not valid:
        loaded = find_family_by_name(doc, target_family_name)

    return (u"loaded" if changed else u"unchanged", loaded)


def rename_family(doc, family, new_name):
    """
    Переименовывает семейство модели в new_name (например по имени файла
    каталога). **Требует открытой транзакции.** Возвращает (True, None)
    либо (False, "причина") — если имя уже совпадает, занято другим
    семейством, пустое или Revit его отклонил.
    """
    try:
        new_name = unicode(new_name or u"").strip()
        if not new_name:
            return (False, u"пустое имя файла")
        if _safe_element_name(family) == new_name:
            return (False, u"имя уже совпадает")

        existing = find_family_by_name(doc, new_name)
        if existing is not None and existing.Id != family.Id:
            return (False, u"в проекте уже есть семейство «{}»".format(new_name))

        if _set_element_name(family, new_name):
            return (True, None)
        return (False, u"Revit отклонил имя «{}»".format(new_name))
    except Exception as ex:
        return (False, u"{}".format(ex))


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
    Таблица «семейство → файл каталога (N%)» с галочками.

    Возвращает (confirmed, do_rename) либо None, если пользователь отменил:
      confirmed — список кортежей
        (family, src_path, target_family_name, display, catalog_name)
        для отмеченных строк (может быть пустым);
      do_rename — bool: переименовывать ли семейство модели по имени файла
        каталога, когда имена различаются.
    """
    result = {"confirmed": None, "rename": True}
    entry_options = [EntryOption(e) for e in entries]

    win = Window()
    win.Title = u"Обновление семейств из каталога"
    win.Width = 1100
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
        u"Автоматически отмечены устаревшие (файл каталога новее метки в модели) "
        u"и семейства без метки с совпадением имени от {}%; «актуальные» — нет.".format(
            catalog_root, int(round(AUTO_CHECK_SCORE * 100))
        )
    )
    hint.FontSize = 11
    hint.Foreground = Brushes.Gray
    hint.TextWrapping = TextWrapping.Wrap
    hint.Margin = Thickness(0, 0, 0, 8)
    root_panel.Children.Add(hint)

    rename_cb = CheckBox()
    rename_cb.Content = (
        u"Переименовывать семейство модели по имени файла каталога, если они "
        u"различаются (нужно, когда в каталоге переименовали семейство)"
    )
    rename_cb.IsChecked = True
    rename_cb.Margin = Thickness(0, 0, 0, 10)
    root_panel.Children.Add(rename_cb)

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
        score_tb.Width = 50
        score_tb.VerticalAlignment = VerticalAlignment.Center
        score_tb.Foreground = Brushes.Gray

        status_tb = TextBlock()
        status_tb.Width = 105
        status_tb.VerticalAlignment = VerticalAlignment.Center
        status_tb.Text = r.status
        if r.status == STATUS_STALE:
            status_tb.Foreground = Brushes.DarkOrange
            status_tb.FontWeight = FontWeights.Bold
        elif r.status == STATUS_CURRENT:
            status_tb.Foreground = Brushes.Green
        else:
            status_tb.Foreground = Brushes.Gray

        rename_tb = TextBlock()
        rename_tb.Width = 160
        rename_tb.TextWrapping = TextWrapping.Wrap
        rename_tb.VerticalAlignment = VerticalAlignment.Center
        rename_tb.Foreground = Brushes.SteelBlue

        st = {
            "row": r,
            "cb": cb,
            "tgt_tb": tgt,
            "rename_tb": rename_tb,
            "path": r.entry.path if r.entry else None,
            "disp": r.entry.rel if r.entry else None,
            "catalog_name": r.entry.name if r.entry else None,
        }

        def _rename_note(catalog_name, fam_name):
            if catalog_name and catalog_name != fam_name:
                return u"→ «{}»".format(catalog_name)
            return u""

        if r.entry:
            score_tb.Text = u"{}%".format(int(round(r.score * 100)))
            tgt.Text = u"{}  ({})".format(r.entry.rel, r.entry.mtime_iso or u"?")
            rename_tb.Text = _rename_note(r.entry.name, r.family_name)
            if r.status == STATUS_STALE:
                cb.IsChecked = True
            elif r.status == STATUS_NO_STAMP:
                cb.IsChecked = r.score >= AUTO_CHECK_SCORE
            else:  # STATUS_CURRENT — уже актуально
                cb.IsChecked = False
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
                st["catalog_name"] = sel.entry.name
                st["tgt_tb"].Text = u"{}  ({})".format(
                    sel.entry.rel, sel.entry.mtime_iso or u"?"
                )
                st["tgt_tb"].Foreground = Brushes.Black
                st["rename_tb"].Text = _rename_note(
                    sel.entry.name, st["row"].family_name
                )
                st["cb"].IsChecked = True

        pick.Click += on_pick

        rowp.Children.Add(cb)
        rowp.Children.Add(arrow)
        rowp.Children.Add(tgt)
        rowp.Children.Add(score_tb)
        rowp.Children.Add(status_tb)
        rowp.Children.Add(rename_tb)
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
                    st["catalog_name"],
                ))
        result["confirmed"] = confirmed
        result["rename"] = bool(rename_cb.IsChecked)
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

    if result["confirmed"] is None:
        return None
    return (result["confirmed"], result["rename"])


# --------------------------------------------------------------------------
# Окно актуальности (кнопка «Актуальность семейств») — таблица + выбор
# --------------------------------------------------------------------------

def _status_brush(status):
    if status == STATUS_STALE:
        return Brushes.Firebrick
    if status == STATUS_NO_STAMP:
        return Brushes.DarkOrange
    if status == STATUS_CURRENT:
        return Brushes.Green
    return Brushes.Gray


class _StatusRow(object):
    """Строка DataGrid окна актуальности (свойства читаются WPF-биндингом)."""

    def __init__(self, mr):
        self.mr = mr
        self.FamilyName = mr.family_name
        self.Status = mr.status
        self.ModelDate = (mr.stamp or {}).get("iso") or u"—"
        self.CatalogDate = (mr.entry.mtime_iso if mr.entry and mr.entry.mtime_iso else u"—")
        self.CatalogFile = mr.entry.rel if mr.entry else u"—"
        self.Score = float(mr.score)
        self.ScoreText = (u"{}%".format(int(round(mr.score * 100))) if mr.entry else u"—")
        # по умолчанию отмечены те, что имеет смысл обновить
        self.Selected = bool(mr.entry) and mr.status in (STATUS_STALE, STATUS_NO_STAMP)


def show_status_form(rows, catalog_root):
    """
    Окно «Актуальность семейств»: информация + сортируемая таблица (имя
    семейства, статус зелёным/красным, даты, файл, похожесть) с галочками
    выбора. Возвращает (jobs, do_rename) для отмеченных строк с файлом в
    каталоге, либо None, если пользователь просто закрыл окно.
    jobs — как у show_preview_form: (family, src_path, target_family_name,
    display, catalog_name).
    """
    counts = {STATUS_STALE: 0, STATUS_NO_STAMP: 0, STATUS_NO_CATALOG: 0, STATUS_CURRENT: 0}
    for mr in rows:
        counts[mr.status] = counts.get(mr.status, 0) + 1

    data = List[object]()
    for mr in rows:
        data.Add(_StatusRow(mr))

    result = {"jobs": None, "rename": True}

    win = Window()
    win.Title = u"Актуальность семейств"
    win.Width = 1040
    win.Height = 700
    win.WindowStartupLocation = WindowStartupLocation.CenterScreen

    outer = DockPanel()
    outer.LastChildFill = True

    header = StackPanel()
    header.Margin = Thickness(16, 12, 16, 8)
    DockPanel.SetDock(header, Dock.Top)

    title = TextBlock()
    title.Text = u"Актуальность семейств относительно каталога"
    title.FontSize = 16
    title.FontWeight = FontWeights.Bold
    header.Children.Add(title)

    info = TextBlock()
    info.Text = (
        u"Каталог: {}\n"
        u"Устарели: {}   ·   без метки: {}   ·   нет в каталоге: {}   ·   актуальны: {}\n"
        u"Красным — требуют обновления, оранжевым — без метки, зелёным — актуальны. "
        u"Заголовки столбцов сортируют. Отметьте, что обновить, и нажмите "
        u"«Обновить отмеченные»; чтобы просто посмотреть — закройте окно.".format(
            catalog_root,
            counts.get(STATUS_STALE, 0), counts.get(STATUS_NO_STAMP, 0),
            counts.get(STATUS_NO_CATALOG, 0), counts.get(STATUS_CURRENT, 0)
        )
    )
    info.FontSize = 11
    info.Foreground = Brushes.Gray
    info.TextWrapping = TextWrapping.Wrap
    info.Margin = Thickness(0, 4, 0, 0)
    header.Children.Add(info)

    grid = DataGrid()
    grid.Margin = Thickness(16, 0, 16, 0)
    grid.AutoGenerateColumns = False
    grid.CanUserAddRows = False
    grid.CanUserDeleteRows = False
    grid.CanUserResizeRows = False
    grid.HeadersVisibility = DataGridHeadersVisibility.Column
    grid.GridLinesVisibility = DataGridGridLinesVisibility.Horizontal
    grid.SelectionMode = DataGridSelectionMode.Extended
    grid.IsReadOnly = False
    grid.ItemsSource = data

    def _star(n):
        return DataGridLength(n, DataGridLengthUnitType.Star)

    def _txt(hdr, path, width=None, sort_path=None):
        c = DataGridTextColumn()
        c.Header = hdr
        c.Binding = Binding(path)
        c.IsReadOnly = True
        # для сортировки по «Похожесть» сортируем по числовому Score,
        # а не по строке "12%" (иначе "100%" < "12%")
        c.SortMemberPath = sort_path or path
        c.Width = width if width is not None else DataGridLength.Auto
        return c

    _sel_b = Binding("Selected")
    _sel_b.Mode = BindingMode.TwoWay
    _sel_b.UpdateSourceTrigger = UpdateSourceTrigger.PropertyChanged

    chk = DataGridCheckBoxColumn()
    chk.Header = u"Обновить"
    chk.Binding = _sel_b
    chk.CanUserSort = False

    grid.Columns.Add(chk)
    grid.Columns.Add(_txt(u"Семейство", "FamilyName", _star(3)))
    grid.Columns.Add(_txt(u"Статус", "Status"))
    grid.Columns.Add(_txt(u"Дата в модели", "ModelDate"))
    grid.Columns.Add(_txt(u"Дата в каталоге", "CatalogDate"))
    grid.Columns.Add(_txt(u"Файл каталога", "CatalogFile", _star(3)))
    grid.Columns.Add(_txt(u"Похожесть", "ScoreText", sort_path="Score"))

    def on_loading_row(sender, e):
        try:
            e.Row.Foreground = _status_brush(e.Row.Item.Status)
        except:
            pass

    grid.LoadingRow += on_loading_row

    # Сортировка по клику на заголовок — своя, по атрибутам _StatusRow
    # (не полагаемся на разрешение путей WPF к python-объектам).
    sort_state = {"path": None, "asc": True}

    def _sort_key(row, path):
        val = getattr(row, path, None)
        if isinstance(val, basestring):
            return (0, val.lower())
        if val is None:
            return (1, u"")
        return (0, val)

    def on_sorting(sender, e):
        col = e.Column
        path = col.SortMemberPath
        if not path:
            e.Handled = True
            return
        asc = not (sort_state["path"] == path and sort_state["asc"])
        sort_state["path"] = path
        sort_state["asc"] = asc

        items = sorted(list(data), key=lambda r: _sort_key(r, path), reverse=not asc)
        data.Clear()
        for it in items:
            data.Add(it)
        try:
            grid.Items.Refresh()
        except:
            pass

        for c in grid.Columns:
            c.SortDirection = None
        col.SortDirection = (
            ListSortDirection.Ascending if asc else ListSortDirection.Descending
        )
        e.Handled = True

    grid.Sorting += on_sorting

    # --- нижняя панель ---

    bottom = StackPanel()
    bottom.Margin = Thickness(16, 8, 16, 12)
    DockPanel.SetDock(bottom, Dock.Bottom)

    rename_cb = CheckBox()
    rename_cb.Content = (
        u"Переименовывать семейство модели по имени файла каталога, если они различаются"
    )
    rename_cb.IsChecked = True
    rename_cb.Margin = Thickness(0, 0, 0, 8)
    bottom.Children.Add(rename_cb)

    buttons = StackPanel()
    buttons.Orientation = Orientation.Horizontal
    buttons.HorizontalAlignment = HorizontalAlignment.Right
    bottom.Children.Add(buttons)

    def _select_where(pred):
        try:
            grid.CommitEdit()
        except:
            pass
        for row in data:
            row.Selected = pred(row)
        grid.Items.Refresh()

    sel_stale_btn = Button()
    sel_stale_btn.Content = u"Отметить требующие обновления"
    sel_stale_btn.Padding = Thickness(10, 4, 10, 4)
    sel_stale_btn.Margin = Thickness(0, 0, 8, 0)
    sel_stale_btn.Click += lambda s, a: _select_where(
        lambda r: r.mr.entry is not None and r.mr.status in (STATUS_STALE, STATUS_NO_STAMP)
    )

    sel_none_btn = Button()
    sel_none_btn.Content = u"Снять все"
    sel_none_btn.Padding = Thickness(10, 4, 10, 4)
    sel_none_btn.Margin = Thickness(0, 0, 8, 0)
    sel_none_btn.Click += lambda s, a: _select_where(lambda r: False)

    close_btn = Button()
    close_btn.Content = u"Закрыть"
    close_btn.Padding = Thickness(10, 4, 10, 4)
    close_btn.Margin = Thickness(0, 0, 8, 0)

    run_btn = Button()
    run_btn.Content = u"Обновить отмеченные"
    run_btn.Padding = Thickness(10, 4, 10, 4)
    run_btn.FontWeight = FontWeights.Bold

    def on_run(sender, args):
        try:
            grid.CommitEdit()
        except:
            pass
        jobs = []
        skipped = 0
        for row in data:
            if not row.Selected:
                continue
            if row.mr.entry is None:
                skipped += 1
                continue
            jobs.append((
                row.mr.family,
                row.mr.entry.path,
                row.mr.family_name,
                row.mr.entry.rel,
                row.mr.entry.name,
            ))
        if not jobs:
            forms.alert(u"Не отмечено ни одного семейства с файлом в каталоге.")
            return
        result["jobs"] = jobs
        result["rename"] = bool(rename_cb.IsChecked)
        win.Close()

    def on_close(sender, args):
        win.Close()

    run_btn.Click += on_run
    close_btn.Click += on_close

    buttons.Children.Add(sel_stale_btn)
    buttons.Children.Add(sel_none_btn)
    buttons.Children.Add(close_btn)
    buttons.Children.Add(run_btn)

    outer.Children.Add(header)
    outer.Children.Add(bottom)
    outer.Children.Add(grid)

    win.Content = outer
    win.ShowDialog()

    if result["jobs"] is None:
        return None
    return (result["jobs"], result["rename"])


# --------------------------------------------------------------------------
# Применение обновлений (общее для обеих кнопок)
# --------------------------------------------------------------------------

def apply_updates(doc, jobs, do_rename):
    """
    jobs — список (family, src_path, target_family_name, display, catalog_name).

    Грузит каждое семейство (reload_family, вне транзакции), затем одной
    транзакцией: при do_rename и различии имён переименовывает семейство
    модели по имени файла каталога (rename_family) и пишет скрытую метку
    даты (write_stamp).

    Возвращает dict со списками для отчёта:
      updated       — (final_name, display, iso)  содержимое перезагружено;
      unchanged     — (final_name, display, iso)  LoadFamily=False, совпало;
      renamed       — (old_name, new_name);
      rename_failed — (old_name, new_name, err);
      failed        — (target_name, display, err) ошибка загрузки;
      stamp_failed  — final_name.
    """
    result = {
        "updated": [], "unchanged": [], "renamed": [],
        "rename_failed": [], "failed": [], "stamp_failed": [],
    }
    if not jobs:
        return result

    options = OverwriteFamilyLoadOptions()
    temp_dir = tempfile.mkdtemp(prefix="lowlife_famcat_")
    loaded = []

    try:
        for family, src_path, target_name, disp, catalog_name in jobs:
            status, payload = reload_family(doc, src_path, target_name, temp_dir, options)
            if status == u"error":
                result["failed"].append((target_name, disp, payload))
            else:
                loaded.append((payload, target_name, disp, src_path, catalog_name, status))
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)

    if not loaded:
        return result

    t = Transaction(doc, u"Обновление семейств из каталога: имена и метки")
    t.Start()
    try:
        for fam_elem, target_name, disp, src_path, catalog_name, status in loaded:
            epoch, iso = file_mtime(src_path)
            final_name = target_name
            was_renamed = False

            if do_rename and fam_elem and catalog_name and catalog_name != target_name:
                ok_rn, err_rn = rename_family(doc, fam_elem, catalog_name)
                if ok_rn:
                    result["renamed"].append((target_name, catalog_name))
                    final_name = catalog_name
                    was_renamed = True
                else:
                    result["rename_failed"].append((target_name, catalog_name, err_rn))

            ok_stamp = write_stamp(fam_elem, epoch, iso, disp) if fam_elem else False
            if not ok_stamp:
                result["stamp_failed"].append(final_name)

            if status == u"loaded":
                result["updated"].append((final_name, disp, iso))
            elif not was_renamed:
                result["unchanged"].append((final_name, disp, iso))
        t.Commit()
    except:
        if t.HasStarted() and not t.HasEnded():
            t.RollBack()
        raise

    return result


def render_result_md(output, result):
    """Печатает разделы отчёта apply_updates в окно вывода pyRevit."""
    up = result["updated"]
    ch = result["unchanged"]
    rn = result["renamed"]
    rf = result["rename_failed"]
    fl = result["failed"]
    sf = result["stamp_failed"]

    if up:
        output.print_md(u"### Обновлены семейства ({})".format(len(up)))
        output.print_md(u"\n".join(
            u"- **{}**  ←  `{}`  _(файл {})_".format(n, d, i or u"?") for n, d, i in up
        ))
    if rn:
        output.print_md(u"### Переименованы по файлу каталога ({})".format(len(rn)))
        output.print_md(u"\n".join(u"- «{}»  →  «{}»".format(a, b) for a, b in rn))
    if ch:
        output.print_md(u"### Без изменений — содержимое совпадает ({})".format(len(ch)))
        output.print_md(u"\n".join(
            u"- **{}**  ←  `{}`  _(файл {})_".format(n, d, i or u"?") for n, d, i in ch
        ))
    if fl:
        output.print_md(u"### Не удалось загрузить ({})".format(len(fl)))
        output.print_md(u"\n".join(
            u"- **{}**  ←  `{}` — {}".format(n, d, e) for n, d, e in fl
        ))
    if rf:
        output.print_md(u"### Обновлены, но не переименованы ({})".format(len(rf)))
        output.print_md(u"\n".join(
            u"- «{}»  →  «{}» — {}".format(a, b, e) for a, b, e in rf
        ))
    if sf:
        output.print_md(u"### Метку даты записать не удалось ({})\n{}".format(
            len(sf), u"\n".join(u"- {}".format(x) for x in sf)
        ))


def result_summary_lines(result):
    """Короткая сводка apply_updates для forms.alert."""
    lines = [u"Обновлено: {}".format(len(result["updated"]))]
    if result["renamed"]:
        lines.append(u"Переименовано: {}".format(len(result["renamed"])))
    if result["unchanged"]:
        lines.append(u"Без изменений: {}".format(len(result["unchanged"])))
    if result["failed"]:
        lines.append(u"Ошибок загрузки: {}".format(len(result["failed"])))
    if result["rename_failed"]:
        lines.append(u"Не переименовано: {}".format(len(result["rename_failed"])))
    if result["stamp_failed"]:
        lines.append(u"Без метки даты: {}".format(len(result["stamp_failed"])))
    return lines
