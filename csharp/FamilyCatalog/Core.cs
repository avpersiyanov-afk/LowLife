// FamilyCatalog — standalone Revit add-in (no pyRevit).
// Core: catalog scan, name similarity, hidden date stamp (ExtensibleStorage),
// family load via "Load into Project", worksharing checkout, rename, apply loops.
// Ported from lib/lowlife/family_catalog.py.  C# 5 compatible.

using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Linq;
using System.Text;
using Autodesk.Revit.DB;
using Autodesk.Revit.DB.ExtensibleStorage;

namespace FamilyCatalog
{
    // ------------------------------------------------------------------ consts
    internal static class C
    {
        public const double AutoCheckScore = 0.72;
        public const double MatchFloor = 0.45;
        public const double StaleToleranceSec = 90.0;

        public static readonly Guid SchemaGuid =
            new Guid("d7b1e6a2-4c3f-4b9a-9e21-6f8c1a2b3c4d");
        public const string SchemaName = "LowLifeFamilyCatalogStamp";
        public const string SchemaVendor = "LOWLIFE";
        public const string FMtimeEpoch = "catalog_mtime_epoch";
        public const string FMtimeIso = "catalog_mtime_iso";
        public const string FCatalogFile = "catalog_file";
        public const string FUpdatedAt = "updated_at_iso";

        public const string StatusStale = "устарело";
        public const string StatusNoStamp = "нет метки";
        public const string StatusCurrent = "актуально";
        public const string StatusNoCatalog = "нет в каталоге";

        public static readonly string[] ExcludedDirKeywords = { "архив", "archive", "archiv" };

        public static readonly DateTime Epoch =
            new DateTime(1970, 1, 1, 0, 0, 0, DateTimeKind.Utc);
    }

    // ------------------------------------------------------------------ settings
    internal static class Settings
    {
        private static string Dir()
        {
            var d = Path.Combine(
                Environment.GetFolderPath(Environment.SpecialFolder.ApplicationData),
                "FamilyCatalog");
            try { if (!Directory.Exists(d)) Directory.CreateDirectory(d); }
            catch { }
            return d;
        }

        private static string RootFile() { return Path.Combine(Dir(), "catalog_root.txt"); }

        public static string LoadRoot()
        {
            try
            {
                var f = RootFile();
                if (File.Exists(f)) return (File.ReadAllText(f, Encoding.UTF8) ?? "").Trim();
            }
            catch { }
            return "";
        }

        public static void SaveRoot(string path)
        {
            try { File.WriteAllText(RootFile(), path ?? "", Encoding.UTF8); }
            catch { }
        }
    }

    // ------------------------------------------------------------------ names
    internal static class Names
    {
        public static string Norm(string s)
        {
            if (string.IsNullOrEmpty(s)) return "";
            var sb = new StringBuilder(s.Length);
            foreach (var ch in s.ToLowerInvariant())
                if (char.IsLetterOrDigit(ch)) sb.Append(ch);
            return sb.ToString();
        }

        private static HashSet<string> Bigrams(string s)
        {
            var r = new HashSet<string>();
            if (s.Length < 2) { if (s.Length > 0) r.Add(s); return r; }
            for (int i = 0; i < s.Length - 1; i++) r.Add(s.Substring(i, 2));
            return r;
        }

        public static double Similarity(string a, string b)
        {
            var na = Norm(a);
            var nb = Norm(b);
            if (na.Length == 0 || nb.Length == 0) return 0.0;
            if (na == nb) return 1.0;
            var ba = Bigrams(na);
            var bb = Bigrams(nb);
            int denom = ba.Count + bb.Count;
            int inter = ba.Count(x => bb.Contains(x));
            double dice = denom > 0 ? (2.0 * inter / denom) : 0.0;
            if (na.Contains(nb) || nb.Contains(na)) dice = Math.Max(dice, 0.9);
            return dice;
        }

        public static string SafeElementName(Element el)
        {
            try { return el.Name; } catch { return null; }
        }

        private static readonly char[] BadFileChars = "\\/:*?\"<>|".ToCharArray();

        public static string SafeFileName(string name)
        {
            var s = name ?? "";
            foreach (var ch in BadFileChars) s = s.Replace(ch, '_');
            s = s.Trim();
            return s.Length == 0 ? "family" : s;
        }

        public static bool SetElementName(Element el, string name)
        {
            try { el.Name = name; return true; } catch { return false; }
        }
    }

    // ------------------------------------------------------------------ catalog
    internal sealed class CatalogEntry
    {
        public string Path;
        public string Name;
        public string Rel;
        public double? Mtime;      // unix seconds (UTC)
        public string MtimeIso;    // local "yyyy-MM-dd HH:mm"

        public override string ToString() { return Rel; }
    }

    internal static class Catalog
    {
        public static void FileMtime(string path, out double? epoch, out string iso)
        {
            epoch = null; iso = "";
            try
            {
                var utc = File.GetLastWriteTimeUtc(path);
                epoch = (utc - C.Epoch).TotalSeconds;
                iso = File.GetLastWriteTime(path).ToString("yyyy-MM-dd HH:mm",
                    CultureInfo.InvariantCulture);
            }
            catch { epoch = null; iso = ""; }
        }

        private static bool IsExcludedDir(string name)
        {
            var low = (name ?? "").ToLowerInvariant();
            return C.ExcludedDirKeywords.Any(k => low.Contains(k));
        }

        private static bool IsBackupRfa(string filename)
        {
            var low = filename.ToLowerInvariant();
            if (!low.EndsWith(".rfa")) return false;
            var stem = low.Substring(0, low.Length - 4);
            int dot = stem.LastIndexOf('.');
            if (dot < 0) return false;
            var tail = stem.Substring(dot + 1);
            return tail.Length == 4 && tail.All(char.IsDigit);
        }

        public static List<CatalogEntry> Scan(string root)
        {
            var list = new List<CatalogEntry>();
            var seen = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
            Walk(root, root, list, seen);
            list.Sort((x, y) => string.Compare(x.Rel, y.Rel,
                StringComparison.OrdinalIgnoreCase));
            return list;
        }

        private static void Walk(string dir, string root, List<CatalogEntry> outp,
            HashSet<string> seen)
        {
            string[] files;
            try { files = Directory.GetFiles(dir); }
            catch { files = new string[0]; }

            foreach (var f in files)
            {
                var fn = System.IO.Path.GetFileName(f);
                if (!fn.ToLowerInvariant().EndsWith(".rfa") || IsBackupRfa(fn)) continue;
                string full;
                try { full = System.IO.Path.GetFullPath(f); } catch { full = f; }
                if (!seen.Add(full)) continue;

                var e = new CatalogEntry();
                e.Path = f;
                e.Name = System.IO.Path.GetFileNameWithoutExtension(f);
                try { e.Rel = RelPath(root, f); } catch { e.Rel = fn; }
                double? ep; string iso;
                FileMtime(f, out ep, out iso);
                e.Mtime = ep; e.MtimeIso = iso;
                outp.Add(e);
            }

            string[] subs;
            try { subs = Directory.GetDirectories(dir); }
            catch { subs = new string[0]; }
            foreach (var s in subs)
            {
                if (IsExcludedDir(System.IO.Path.GetFileName(s))) continue;
                Walk(s, root, outp, seen);
            }
        }

        public static string RelPath(string root, string full)
        {
            var r = root.TrimEnd('\\', '/') + "\\";
            if (full.StartsWith(r, StringComparison.OrdinalIgnoreCase))
                return full.Substring(r.Length);
            return System.IO.Path.GetFileName(full);
        }

        // Type catalog .txt: first data column of each non-header line.
        public static List<string> ReadTypeCatalogNames(string txtPath)
        {
            string[] lines = null;
            foreach (var enc in new[]
            {
                Encoding.Unicode, new UTF8Encoding(true), Encoding.GetEncoding(1251),
                Encoding.UTF8, Encoding.GetEncoding(28591)
            })
            {
                try
                {
                    var text = File.ReadAllText(txtPath, enc);
                    if (text.IndexOf('�') >= 0 && enc != Encoding.GetEncoding(28591))
                        continue;
                    lines = text.Replace("\r\n", "\n").Replace("\r", "\n").Split('\n');
                    break;
                }
                catch { lines = null; }
            }
            if (lines == null || lines.Length == 0) return new List<string>();

            var header = string.IsNullOrEmpty(lines[0]) ? "," : lines[0];
            char delim = (header[0] == ',' || header[0] == ';' || header[0] == '\t')
                ? header[0] : ',';

            var names = new List<string>();
            for (int i = 1; i < lines.Length; i++)
            {
                var ln = lines[i].Trim();
                if (ln.Length == 0) continue;
                int p = ln.IndexOf(delim);
                var name = (p < 0 ? ln : ln.Substring(0, p)).Trim().Trim('"');
                if (name.Length > 0) names.Add(name);
            }
            return names;
        }
    }

    // ------------------------------------------------------------------ stamp
    internal sealed class Stamp
    {
        public double? Epoch;
        public string Iso;
        public string File;
        public string UpdatedAt;
    }

    internal static class StampStore
    {
        private static Schema GetOrCreate()
        {
            var s = Schema.Lookup(C.SchemaGuid);
            if (s != null) return s;
            var sb = new SchemaBuilder(C.SchemaGuid);
            sb.SetSchemaName(C.SchemaName);
            sb.SetVendorId(C.SchemaVendor);
            sb.SetReadAccessLevel(AccessLevel.Public);
            sb.SetWriteAccessLevel(AccessLevel.Public);
            sb.AddSimpleField(C.FMtimeEpoch, typeof(string));
            sb.AddSimpleField(C.FMtimeIso, typeof(string));
            sb.AddSimpleField(C.FCatalogFile, typeof(string));
            sb.AddSimpleField(C.FUpdatedAt, typeof(string));
            return sb.Finish();
        }

        public static Stamp Read(Family fam)
        {
            try
            {
                var schema = Schema.Lookup(C.SchemaGuid);
                if (schema == null) return null;
                var ent = fam.GetEntity(schema);
                if (ent == null || !ent.IsValid()) return null;
                var st = new Stamp();
                var epochStr = ent.Get<string>(C.FMtimeEpoch);
                double ep;
                st.Epoch = double.TryParse(epochStr, NumberStyles.Any,
                    CultureInfo.InvariantCulture, out ep) ? (double?)ep : null;
                st.Iso = ent.Get<string>(C.FMtimeIso);
                st.File = ent.Get<string>(C.FCatalogFile);
                st.UpdatedAt = ent.Get<string>(C.FUpdatedAt);
                return st;
            }
            catch { return null; }
        }

        // Requires an open transaction.
        public static bool Write(Family fam, double? mtimeEpoch, string mtimeIso,
            string catalogFile)
        {
            try
            {
                var schema = GetOrCreate();
                var ent = new Entity(schema);
                ent.Set<string>(C.FMtimeEpoch, mtimeEpoch.HasValue
                    ? mtimeEpoch.Value.ToString(CultureInfo.InvariantCulture) : "");
                ent.Set<string>(C.FMtimeIso, mtimeIso ?? "");
                ent.Set<string>(C.FCatalogFile, catalogFile ?? "");
                ent.Set<string>(C.FUpdatedAt,
                    DateTime.Now.ToString("yyyy-MM-dd HH:mm", CultureInfo.InvariantCulture));
                fam.SetEntity(ent);
                return true;
            }
            catch { return false; }
        }

        public static string StatusOf(Stamp stamp, CatalogEntry entry)
        {
            if (entry == null) return C.StatusNoCatalog;
            if (stamp == null) return C.StatusNoStamp;
            if (!stamp.Epoch.HasValue || !entry.Mtime.HasValue) return C.StatusNoStamp;
            if (entry.Mtime.Value > stamp.Epoch.Value + C.StaleToleranceSec)
                return C.StatusStale;
            return C.StatusCurrent;
        }
    }

    // ------------------------------------------------------------------ families
    internal sealed class CategoryOption
    {
        public ElementId CatId;
        public string SortName;
        public string Display;
        public override string ToString() { return Display; }
    }

    internal sealed class MatchRow
    {
        public Family Family;
        public string FamilyName;
        public CatalogEntry Entry;     // best match or null
        public double Score;
        public Stamp Stamp;
        public string Status;
        public string CategoryName;
    }

    internal static class Model
    {
        private static IEnumerable<Family> LoadableFamilies(Document doc)
        {
            foreach (Family fam in new FilteredElementCollector(doc)
                         .OfClass(typeof(Family)).Cast<Family>())
            {
                bool inPlace;
                try { inPlace = fam.IsInPlace; } catch { inPlace = false; }
                if (inPlace) continue;
                Category cat;
                try { cat = fam.FamilyCategory; } catch { cat = null; }
                if (cat == null) continue;
                yield return fam;
            }
        }

        public static List<CategoryOption> ListFamilyCategories(Document doc)
        {
            var cats = new Dictionary<int, Category>();
            var counts = new Dictionary<int, int>();
            foreach (var fam in LoadableFamilies(doc))
            {
                var cat = fam.FamilyCategory;
                int id = cat.Id.IntegerValue;
                cats[id] = cat;
                counts[id] = counts.ContainsKey(id) ? counts[id] + 1 : 1;
            }
            var result = new List<CategoryOption>();
            foreach (var kv in cats)
            {
                string baseName;
                try { baseName = kv.Value.Name; }
                catch { baseName = "?"; }
                if (string.IsNullOrEmpty(baseName)) baseName = "?";
                result.Add(new CategoryOption
                {
                    CatId = kv.Value.Id,
                    SortName = (baseName ?? "?").ToLowerInvariant(),
                    Display = string.Format("{0} ({1})", baseName, counts[kv.Key])
                });
            }
            result.Sort((a, b) => string.Compare(a.SortName, b.SortName,
                StringComparison.Ordinal));
            return result;
        }

        public static List<Family> ListFamiliesInCategories(Document doc,
            IEnumerable<ElementId> catIds)
        {
            var targets = new HashSet<int>(catIds.Select(x => x.IntegerValue));
            var r = LoadableFamilies(doc)
                .Where(f => targets.Contains(f.FamilyCategory.Id.IntegerValue))
                .ToList();
            r.Sort((a, b) => string.Compare(
                (Names.SafeElementName(a) ?? "").ToLowerInvariant(),
                (Names.SafeElementName(b) ?? "").ToLowerInvariant(),
                StringComparison.Ordinal));
            return r;
        }

        public static HashSet<string> ProjectFamilyNames(Document doc)
        {
            var s = new HashSet<string>();
            foreach (Family fam in new FilteredElementCollector(doc)
                         .OfClass(typeof(Family)).Cast<Family>())
            {
                var nm = Names.SafeElementName(fam);
                if (!string.IsNullOrEmpty(nm)) s.Add(nm);
            }
            return s;
        }

        public static Family FindByName(Document doc, string name)
        {
            foreach (Family fam in new FilteredElementCollector(doc)
                         .OfClass(typeof(Family)).Cast<Family>())
                if (Names.SafeElementName(fam) == name) return fam;
            return null;
        }

        private static readonly Dictionary<string, int> StatusOrder =
            new Dictionary<string, int>
            {
                { C.StatusStale, 0 }, { C.StatusNoStamp, 1 },
                { C.StatusNoCatalog, 2 }, { C.StatusCurrent, 3 }
            };

        public static List<MatchRow> BuildMatches(IEnumerable<Family> families,
            List<CatalogEntry> entries)
        {
            var rows = new List<MatchRow>();
            foreach (var fam in families)
            {
                var famName = Names.SafeElementName(fam) ?? "?";
                CatalogEntry best = null;
                double bestScore = 0.0;
                foreach (var e in entries)
                {
                    var sc = Names.Similarity(famName, e.Name);
                    if (sc > bestScore) { bestScore = sc; best = e; }
                }
                var stamp = StampStore.Read(fam);
                var confident = bestScore >= C.MatchFloor ? best : null;
                string catName = "";
                try { catName = fam.FamilyCategory.Name; } catch { }
                rows.Add(new MatchRow
                {
                    Family = fam,
                    FamilyName = famName,
                    Entry = best,
                    Score = bestScore,
                    Stamp = stamp,
                    Status = StampStore.StatusOf(stamp, confident),
                    CategoryName = catName
                });
            }
            rows.Sort((a, b) =>
            {
                int oa = StatusOrder.ContainsKey(a.Status) ? StatusOrder[a.Status] : 9;
                int ob = StatusOrder.ContainsKey(b.Status) ? StatusOrder[b.Status] : 9;
                if (oa != ob) return oa - ob;
                if (a.Score != b.Score) return b.Score.CompareTo(a.Score);
                return string.Compare(a.FamilyName.ToLowerInvariant(),
                    b.FamilyName.ToLowerInvariant(), StringComparison.Ordinal);
            });
            return rows;
        }
    }

    // ------------------------------------------------------------------ loading
    internal sealed class OverwriteLoadOptions : IFamilyLoadOptions
    {
        private readonly bool _overwrite;
        public OverwriteLoadOptions(bool overwriteParamValues)
        {
            _overwrite = overwriteParamValues;
        }
        public bool OnFamilyFound(bool familyInUse, out bool overwriteParameterValues)
        {
            overwriteParameterValues = _overwrite;
            return true;
        }
        public bool OnSharedFamilyFound(Family sharedFamily, bool familyInUse,
            out FamilySource source, out bool overwriteParameterValues)
        {
            source = FamilySource.Family;
            overwriteParameterValues = _overwrite;
            return true;
        }
    }

    internal static class Loader
    {
        // "Load into Project" path: open the .rfa as a family document, load it
        // into targetDoc, close. Forces reload even for an older file version.
        public static Family LoadRfaIntoProject(Document doc, string rfaPath,
            IFamilyLoadOptions options, out string note)
        {
            var notes = new List<string>();
            Family fam = null;
            try
            {
                var fdoc = doc.Application.OpenDocumentFile(rfaPath);
                try
                {
                    fam = fdoc.LoadFamily(doc, options);
                    notes.Add("FamilyDoc.LoadFamily -> " + (fam != null ? "ok" : "None"));
                }
                finally
                {
                    try { fdoc.Close(false); }
                    catch (Exception cex) { notes.Add("Close искл: " + cex.Message); }
                }
            }
            catch (Exception ex) { notes.Add("FamilyDoc.LoadFamily искл: " + ex.Message); }

            if (fam == null)
            {
                try
                {
                    Family outF;
                    bool ok = doc.LoadFamily(rfaPath, options, out outF);
                    if (outF != null) fam = outF;
                    notes.Add("doc.LoadFamily -> " + ok);
                }
                catch (Exception ex) { notes.Add("doc.LoadFamily искл: " + ex.Message); }
            }
            note = string.Join("; ", notes);
            return fam;
        }

        public static string CheckoutFamily(Document doc, Family family)
        {
            try { if (!doc.IsWorkshared) return "модель не совместная"; }
            catch { return "IsWorkshared недоступен"; }
            string before, after, err = "";
            try { before = WorksharingUtils.GetCheckoutStatus(doc, family.Id).ToString(); }
            catch (Exception ex) { before = "?(" + ex.Message + ")"; }
            try
            {
                WorksharingUtils.CheckoutElements(doc,
                    new List<ElementId> { family.Id });
            }
            catch (Exception ex) { err = " checkout-искл=" + ex.Message; }
            try { after = WorksharingUtils.GetCheckoutStatus(doc, family.Id).ToString(); }
            catch (Exception ex) { after = "?(" + ex.Message + ")"; }
            return string.Format("co: {0} -> {1}{2}", before, after, err);
        }

        // Requires an open transaction.
        public static bool RenameFamily(Document doc, Family family, string newName,
            out string err)
        {
            err = null;
            try
            {
                newName = (newName ?? "").Trim();
                if (newName.Length == 0) { err = "пустое имя файла"; return false; }
                if (Names.SafeElementName(family) == newName)
                { err = "имя уже совпадает"; return false; }
                var existing = Model.FindByName(doc, newName);
                if (existing != null && existing.Id != family.Id)
                { err = "в проекте уже есть семейство «" + newName + "»"; return false; }
                if (Names.SetElementName(family, newName)) return true;
                err = "Revit отклонил имя «" + newName + "»";
                return false;
            }
            catch (Exception ex) { err = ex.Message; return false; }
        }
    }

    // ------------------------------------------------------------------ apply
    internal sealed class JobUpdate
    {
        public Family Family;
        public string SrcPath;
        public string TargetName;
        public string Display;
        public string CatalogName;
    }

    internal sealed class UpdateResult
    {
        public List<string[]> Updated = new List<string[]>();       // name, disp, iso
        public List<string[]> Unchanged = new List<string[]>();
        public List<string[]> Renamed = new List<string[]>();       // old, new
        public List<string[]> RenameFailed = new List<string[]>();  // old, new, err
        public List<string[]> Failed = new List<string[]>();        // name, disp, err
        public List<string> StampFailed = new List<string>();
        public List<string> Debug = new List<string>();
    }

    internal sealed class LoadResult
    {
        public List<string[]> Loaded = new List<string[]>();
        public List<string[]> Updated = new List<string[]>();
        public List<string[]> Failed = new List<string[]>();
        public List<string> StampFailed = new List<string>();
    }

    internal static class Apply
    {
        private static string TempDir()
        {
            var d = Path.Combine(Path.GetTempPath(),
                "familycatalog_" + Guid.NewGuid().ToString("N"));
            Directory.CreateDirectory(d);
            return d;
        }

        // status returned by ReloadFamily
        private enum RS { Loaded, Unchanged, Error }

        private static RS ReloadFamily(Document doc, string srcPath, string targetName,
            string tempDir, IFamilyLoadOptions options,
            out Family family, out string note)
        {
            family = null;
            var diag = new List<string>();
            diag.Add("файл: " + srcPath);

            var dst = Path.Combine(tempDir, Names.SafeFileName(targetName) + ".rfa");
            try
            {
                File.Copy(srcPath, dst, true);
                try { File.SetAttributes(dst, FileAttributes.Normal); } catch { }
                var srcTxt = Path.Combine(Path.GetDirectoryName(srcPath),
                    Path.GetFileNameWithoutExtension(srcPath) + ".txt");
                if (File.Exists(srcTxt))
                {
                    var dstTxt = Path.Combine(tempDir,
                        Path.GetFileNameWithoutExtension(dst) + ".txt");
                    File.Copy(srcTxt, dstTxt, true);
                    try { File.SetAttributes(dstTxt, FileAttributes.Normal); } catch { }
                }
            }
            catch (Exception ex)
            {
                note = "копирование во временный файл: " + ex.Message;
                return RS.Error;
            }

            var existing = Model.FindByName(doc, targetName);
            int nBefore = -1;
            if (existing == null) diag.Add("семейство «" + targetName + "» в модели НЕ найдено");
            else
            {
                try { nBefore = existing.GetFamilySymbolIds().Count; } catch { }
                diag.Add("типоразмеров до: " + nBefore);
                diag.Add(Loader.CheckoutFamily(doc, existing));
            }

            var dstTxt2 = Path.Combine(tempDir, Path.GetFileNameWithoutExtension(dst) + ".txt");
            var catTypes = File.Exists(dstTxt2)
                ? Catalog.ReadTypeCatalogNames(dstTxt2) : new List<string>();

            Family fam = null;
            if (catTypes.Count > 0)
            {
                var errs = new List<string>();
                foreach (var tn in catTypes)
                {
                    try
                    {
                        FamilySymbol sym;
                        doc.LoadFamilySymbol(dst, tn, options, out sym);
                    }
                    catch (Exception ex) { errs.Add("«" + tn + "»: " + ex.Message); }
                }
                fam = Model.FindByName(doc, targetName);
                diag.Add(string.Format("каталог типов: {0} шт{1}", catTypes.Count,
                    errs.Count > 0 ? " (ошибки: " + string.Join("; ", errs) + ")" : ""));
            }
            else
            {
                string n2;
                fam = Loader.LoadRfaIntoProject(doc, dst, options, out n2);
                diag.Add(n2);
            }

            bool changed = fam != null;
            Family loaded = fam;
            try { if (loaded != null && !loaded.IsValidObject) loaded = null; }
            catch { loaded = null; }
            if (loaded == null) loaded = Model.FindByName(doc, targetName);
            diag.Add("ссылка: " + (loaded != null ? "есть" : "НЕТ"));
            try
            {
                if (loaded != null)
                    diag.Add("типоразмеров после: " + loaded.GetFamilySymbolIds().Count);
            }
            catch { }

            family = loaded;
            note = string.Join("; ", diag);
            return changed ? RS.Loaded : RS.Unchanged;
        }

        public static UpdateResult ApplyUpdates(Document doc, List<JobUpdate> jobs,
            bool doRename, bool overwriteParams)
        {
            var res = new UpdateResult();
            if (jobs.Count == 0) return res;

            var options = new OverwriteLoadOptions(overwriteParams);
            var tempDir = TempDir();
            var loaded = new List<object[]>();  // family, target, disp, src, catName, status
            try
            {
                foreach (var j in jobs)
                {
                    Family fam; string note;
                    var st = ReloadFamily(doc, j.SrcPath, j.TargetName, tempDir,
                        options, out fam, out note);
                    res.Debug.Add("**" + j.TargetName + "** — " + note);
                    if (st == RS.Error)
                        res.Failed.Add(new[] { j.TargetName, j.Display, note });
                    else
                        loaded.Add(new object[] { fam, j.TargetName, j.Display,
                            j.SrcPath, j.CatalogName, st });
                }
            }
            finally { TryDeleteDir(tempDir); }

            if (loaded.Count == 0) return res;

            using (var t = new Transaction(doc, "Каталог семейств: имена и метки"))
            {
                t.Start();
                foreach (var row in loaded)
                {
                    var fam = (Family)row[0];
                    var target = (string)row[1];
                    var disp = (string)row[2];
                    var src = (string)row[3];
                    var catName = (string)row[4];
                    var st = (RS)row[5];

                    double? epoch; string iso;
                    Catalog.FileMtime(src, out epoch, out iso);
                    var finalName = target;
                    bool wasRenamed = false;

                    if (doRename && fam != null && !string.IsNullOrEmpty(catName)
                        && catName != target)
                    {
                        string err;
                        if (Loader.RenameFamily(doc, fam, catName, out err))
                        {
                            res.Renamed.Add(new[] { target, catName });
                            finalName = catName;
                            wasRenamed = true;
                        }
                        else res.RenameFailed.Add(new[] { target, catName, err });
                    }

                    bool okStamp = fam != null && StampStore.Write(fam, epoch, iso, disp);
                    if (!okStamp) res.StampFailed.Add(finalName);

                    if (st == RS.Loaded) res.Updated.Add(new[] { finalName, disp, iso });
                    else if (!wasRenamed) res.Unchanged.Add(new[] { finalName, disp, iso });
                }
                t.Commit();
            }
            return res;
        }

        public static LoadResult ApplyLoads(Document doc,
            List<KeyValuePair<CatalogEntry, List<string>>> jobs,
            HashSet<string> presentNames, bool overwriteParams)
        {
            var res = new LoadResult();
            if (jobs.Count == 0) return res;
            var options = new OverwriteLoadOptions(overwriteParams);
            var done = new List<object[]>(); // entry, family, wasPresent, nTypes(int?)

            foreach (var kv in jobs)
            {
                var e = kv.Key;
                var typeNames = kv.Value;   // null => whole family
                bool wasPresent = presentNames.Contains(e.Name);

                var existing = Model.FindByName(doc, e.Name);
                if (existing != null) Loader.CheckoutFamily(doc, existing);

                var txt = Path.Combine(Path.GetDirectoryName(e.Path),
                    Path.GetFileNameWithoutExtension(e.Path) + ".txt");
                List<string> want = null;
                if (typeNames != null && typeNames.Count > 0) want = typeNames;
                else if (File.Exists(txt)) want = Catalog.ReadTypeCatalogNames(txt);

                int? nTypes = null;
                Family fam = null;
                try
                {
                    if (want != null && want.Count > 0)
                    {
                        var errs = new List<string>();
                        foreach (var tn in want)
                        {
                            try
                            {
                                FamilySymbol sym;
                                doc.LoadFamilySymbol(e.Path, tn, options, out sym);
                            }
                            catch (Exception ex) { errs.Add("«" + tn + "»: " + ex.Message); }
                        }
                        fam = Model.FindByName(doc, e.Name);
                        nTypes = want.Count;
                        if (fam == null && !wasPresent)
                        {
                            res.Failed.Add(new[] { e.Name, e.Rel,
                                "типы из каталога не загрузились: " +
                                (errs.Count > 0 ? string.Join("; ", errs) : "?") });
                            continue;
                        }
                    }
                    else
                    {
                        string note;
                        fam = Loader.LoadRfaIntoProject(doc, e.Path, options, out note);
                        try { if (fam != null && !fam.IsValidObject) fam = null; }
                        catch { fam = null; }
                        if (fam == null) fam = Model.FindByName(doc, e.Name);
                    }
                }
                catch (Exception ex)
                {
                    res.Failed.Add(new[] { e.Name, e.Rel, ex.Message });
                    continue;
                }

                if (fam == null && !wasPresent)
                {
                    res.Failed.Add(new[] { e.Name, e.Rel, "семейство не загрузилось" });
                    continue;
                }
                done.Add(new object[] { e, fam, wasPresent, nTypes });
            }

            if (done.Count == 0) return res;

            using (var t = new Transaction(doc, "Каталог семейств: метки даты"))
            {
                t.Start();
                foreach (var row in done)
                {
                    var e = (CatalogEntry)row[0];
                    var fam = (Family)row[1];
                    var wasPresent = (bool)row[2];
                    var nTypes = (int?)row[3];
                    var nm = (fam != null ? Names.SafeElementName(fam) : null) ?? e.Name;
                    var disp = nTypes.HasValue
                        ? string.Format("{0} · типоразмеров: {1}", e.Rel, nTypes.Value)
                        : e.Rel;
                    bool okStamp = fam != null &&
                        StampStore.Write(fam, e.Mtime, e.MtimeIso, e.Rel);
                    if (!okStamp) res.StampFailed.Add(nm);
                    if (wasPresent) res.Updated.Add(new[] { nm, disp, e.MtimeIso });
                    else res.Loaded.Add(new[] { nm, disp, e.MtimeIso });
                }
                t.Commit();
            }
            return res;
        }

        private static void TryDeleteDir(string d)
        {
            try { if (Directory.Exists(d)) Directory.Delete(d, true); } catch { }
        }
    }
}
