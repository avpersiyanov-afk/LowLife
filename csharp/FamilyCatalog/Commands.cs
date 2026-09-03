// FamilyCatalog — the two ribbon commands.

using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using Autodesk.Revit.ApplicationServices;
using Autodesk.Revit.Attributes;
using Autodesk.Revit.DB;
using Autodesk.Revit.UI;

namespace FamilyCatalog
{
    internal static class Shared
    {
        // Resolve the catalog root. Shift held => re-pick.
        public static string ResolveRoot(bool forcePick)
        {
            var root = Settings.LoadRoot();
            if (forcePick || string.IsNullOrEmpty(root) || !Directory.Exists(root))
            {
                var picked = Dialogs.PickFolder(root);
                if (!string.IsNullOrEmpty(picked)) { Settings.SaveRoot(picked); return picked; }
                return (!string.IsNullOrEmpty(root) && Directory.Exists(root)) ? root : null;
            }
            return root;
        }

        public static bool ShiftHeld()
        {
            try
            {
                return (System.Windows.Input.Keyboard.IsKeyDown(System.Windows.Input.Key.LeftShift)
                    || System.Windows.Input.Keyboard.IsKeyDown(System.Windows.Input.Key.RightShift));
            }
            catch { return false; }
        }

        public static List<string> TypeNamesFor(Application app, string rfaPath)
        {
            // 1) type catalog .txt next to .rfa
            var txt = Path.Combine(Path.GetDirectoryName(rfaPath),
                Path.GetFileNameWithoutExtension(rfaPath) + ".txt");
            if (File.Exists(txt))
            {
                var cat = Catalog.ReadTypeCatalogNames(txt);
                if (cat.Count > 0)
                    return cat.Distinct().OrderBy(x => x).ToList();
            }
            // 2) embedded FamilyManager.Types
            var names = new List<string>();
            Document fdoc = null;
            try
            {
                fdoc = app.OpenDocumentFile(rfaPath);
                foreach (FamilyType t in fdoc.FamilyManager.Types)
                {
                    try { if (!string.IsNullOrEmpty(t.Name)) names.Add(t.Name); }
                    catch { }
                }
            }
            catch { names.Clear(); }
            finally
            {
                if (fdoc != null) { try { fdoc.Close(false); } catch { } }
            }
            return names.Distinct().OrderBy(x => x).ToList();
        }
    }

    // ============================================================ SYNC / UPDATE
    [Transaction(TransactionMode.Manual)]
    public class SyncCommand : IExternalCommand
    {
        public Result Execute(ExternalCommandData data, ref string message,
            ElementSet elements)
        {
            var doc = data.Application.ActiveUIDocument.Document;
            try
            {
                if (doc.IsFamilyDocument)
                {
                    Dialogs.Alert("Работает в проекте, а не в редакторе семейств.",
                        "Семейства из каталога");
                    return Result.Cancelled;
                }

                var root = Shared.ResolveRoot(Shared.ShiftHeld());
                if (root == null) return Result.Cancelled;

                var entries = Catalog.Scan(root);
                if (entries.Count == 0)
                {
                    Dialogs.Alert("В каталоге не найдено ни одного .rfa:\n" + root,
                        "Семейства из каталога");
                    return Result.Cancelled;
                }

                var categories = Model.ListFamilyCategories(doc);
                if (categories.Count == 0)
                {
                    Dialogs.Alert("В проекте нет загружаемых семейств.", "Семейства из каталога");
                    return Result.Cancelled;
                }

                var chosen = Dialogs.MultiSelect("Категории семейств (можно несколько)",
                    categories, c => c.Display);
                if (chosen == null || chosen.Count == 0) return Result.Cancelled;

                var families = Model.ListFamiliesInCategories(doc,
                    chosen.Select(c => c.CatId));
                if (families.Count == 0)
                {
                    Dialogs.Alert("В выбранных категориях нет загружаемых семейств.",
                        "Семейства из каталога");
                    return Result.Cancelled;
                }

                var rows = Model.BuildMatches(families, entries);
                var picked = StatusWindow.Show(rows, root, entries);
                if (picked == null) return Result.Cancelled;

                var res = Apply.ApplyUpdates(doc, picked.Jobs, picked.Rename,
                    picked.Overwrite);

                var summary = string.Format(
                    "Готово.\n\nОбновлено: {0}\nПереименовано: {1}\nБез изменений: {2}\n" +
                    "Ошибок: {3}\nНе переименовано: {4}\nБез метки: {5}",
                    res.Updated.Count, res.Renamed.Count, res.Unchanged.Count,
                    res.Failed.Count, res.RenameFailed.Count, res.StampFailed.Count);
                Dialogs.Report("Семейства из каталога — отчёт",
                    summary + "\n\n" + Report.Update(res));
                return Result.Succeeded;
            }
            catch (Exception ex)
            {
                Dialogs.Alert("Сбой:\n\n" + ex, "Семейства из каталога");
                return Result.Failed;
            }
        }
    }

    // ============================================================ LOAD
    [Transaction(TransactionMode.Manual)]
    public class LoadCommand : IExternalCommand
    {
        public Result Execute(ExternalCommandData data, ref string message,
            ElementSet elements)
        {
            var uidoc = data.Application.ActiveUIDocument;
            var doc = uidoc.Document;
            try
            {
                if (doc.IsFamilyDocument)
                {
                    Dialogs.Alert("Работает в проекте, а не в редакторе семейств.",
                        "Загрузить семейства");
                    return Result.Cancelled;
                }

                var root = Shared.ResolveRoot(Shared.ShiftHeld());
                if (root == null) return Result.Cancelled;

                var entries = Catalog.Scan(root);
                if (entries.Count == 0)
                {
                    Dialogs.Alert("В каталоге не найдено ни одного .rfa:\n" + root,
                        "Загрузить семейства");
                    return Result.Cancelled;
                }

                // optional folder filter
                var folders = entries
                    .Select(e => { var d = Path.GetDirectoryName(e.Rel);
                        return string.IsNullOrEmpty(d) ? "." : d; })
                    .Distinct().OrderBy(x => x).ToList();
                var scoped = entries;
                if (folders.Count > 1)
                {
                    var pf = Dialogs.MultiSelect(
                        "Разделы каталога — можно несколько (Отмена = все)",
                        folders, x => x == "." ? "(корень каталога)" : x);
                    if (pf != null && pf.Count > 0)
                    {
                        var keep = new HashSet<string>(pf);
                        scoped = entries.Where(e =>
                        {
                            var d = Path.GetDirectoryName(e.Rel);
                            return keep.Contains(string.IsNullOrEmpty(d) ? "." : d);
                        }).ToList();
                    }
                }
                if (scoped.Count == 0)
                {
                    Dialogs.Alert("В выбранных разделах нет .rfa.", "Загрузить семейства");
                    return Result.Cancelled;
                }

                var present = Model.ProjectFamilyNames(doc);

                // steps loop: file table -> type picker (with Back)
                List<KeyValuePair<CatalogEntry, List<string>>> jobs = null;
                bool overwrite = true;
                while (jobs == null)
                {
                    var lr = LoadWindow.Show(scoped, present, root);
                    if (lr == null) return Result.Cancelled;
                    overwrite = lr.Overwrite;

                    var typeMap = new List<KeyValuePair<CatalogEntry, List<string>>>();
                    var passthru = new List<CatalogEntry>();
                    foreach (var e in lr.Entries)
                    {
                        var names = Shared.TypeNamesFor(doc.Application, e.Path);
                        if (names.Count > 0)
                            typeMap.Add(new KeyValuePair<CatalogEntry, List<string>>(e, names));
                        else
                            passthru.Add(e);
                    }

                    var sel = TypePicker.Show(typeMap);
                    if (sel == null) return Result.Cancelled;
                    if (ReferenceEquals(sel, TypePicker.Back)) continue;

                    var map = (Dictionary<CatalogEntry, HashSet<string>>)sel;
                    jobs = passthru
                        .Select(e => new KeyValuePair<CatalogEntry, List<string>>(e, null))
                        .ToList();
                    foreach (var kv in typeMap)
                    {
                        HashSet<string> chosen;
                        if (!map.TryGetValue(kv.Key, out chosen) || chosen.Count == 0)
                            continue;
                        var full = new HashSet<string>(kv.Value);
                        List<string> tn = chosen.SetEquals(full) ? null : chosen.OrderBy(x => x).ToList();
                        jobs.Add(new KeyValuePair<CatalogEntry, List<string>>(kv.Key, tn));
                    }
                }

                if (jobs.Count == 0)
                {
                    Dialogs.Alert("Нечего загружать.", "Загрузить семейства");
                    return Result.Cancelled;
                }

                var res = Apply.ApplyLoads(doc, jobs, present, overwrite);
                var summary = string.Format(
                    "Готово.\n\nЗагружено новых: {0}\nПерезагружено: {1}\nОшибок: {2}\nБез метки: {3}",
                    res.Loaded.Count, res.Updated.Count, res.Failed.Count,
                    res.StampFailed.Count);
                Dialogs.Report("Загрузить семейства — отчёт",
                    summary + "\n\n" + Report.Load(res));
                return Result.Succeeded;
            }
            catch (Exception ex)
            {
                Dialogs.Alert("Сбой:\n\n" + ex, "Загрузить семейства");
                return Result.Failed;
            }
        }
    }
}
