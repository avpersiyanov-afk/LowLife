// FamilyCatalog — WPF windows and simple dialogs (no XAML, all code-behind).

using System;
using System.Collections.Generic;
using System.Collections.ObjectModel;
using System.ComponentModel;
using System.Globalization;
using System.IO;
using System.Linq;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Media;
using WForms = System.Windows.Forms;
using TaskDialog = Autodesk.Revit.UI.TaskDialog;
using TaskDialogCommonButtons = Autodesk.Revit.UI.TaskDialogCommonButtons;

namespace FamilyCatalog
{
    internal static class Dialogs
    {
        public static void Alert(string msg, string title)
        {
            var td = new TaskDialog(title ?? "Каталог семейств");
            td.MainInstruction = msg;
            td.CommonButtons = TaskDialogCommonButtons.Close;
            td.Show();
        }

        public static string PickFolder(string initial)
        {
            using (var dlg = new WForms.FolderBrowserDialog())
            {
                dlg.Description = "Папка-каталог семейств (.rfa, включая подпапки)";
                if (!string.IsNullOrEmpty(initial) && Directory.Exists(initial))
                    dlg.SelectedPath = initial;
                var r = dlg.ShowDialog();
                if (r == WForms.DialogResult.OK && Directory.Exists(dlg.SelectedPath))
                    return dlg.SelectedPath;
            }
            return null;
        }

        // Multi-select checkbox list. Returns selected items or null (cancel).
        public static List<T> MultiSelect<T>(string title, IEnumerable<T> items,
            Func<T, string> label)
        {
            var win = new Window
            {
                Title = title,
                Width = 560,
                Height = 620,
                WindowStartupLocation = WindowStartupLocation.CenterScreen
            };
            var dock = new DockPanel { LastChildFill = true };

            var buttons = new StackPanel
            {
                Orientation = Orientation.Horizontal,
                HorizontalAlignment = HorizontalAlignment.Right,
                Margin = new Thickness(12)
            };
            DockPanel.SetDock(buttons, Dock.Bottom);

            var boxes = new List<CheckBox>();
            var list = items.ToList();
            var panel = new StackPanel { Margin = new Thickness(14) };
            foreach (var it in list)
            {
                var cb = new CheckBox { Content = label(it), Margin = new Thickness(0, 3, 0, 3) };
                boxes.Add(cb);
                panel.Children.Add(cb);
            }
            var scroll = new ScrollViewer
            {
                VerticalScrollBarVisibility = ScrollBarVisibility.Auto,
                Content = panel
            };

            var result = new List<T>();
            bool ok = false;

            var allBtn = MkBtn("Все");
            allBtn.Click += (s, e) => { foreach (var b in boxes) b.IsChecked = true; };
            var noneBtn = MkBtn("Ничего");
            noneBtn.Click += (s, e) => { foreach (var b in boxes) b.IsChecked = false; };
            var cancelBtn = MkBtn("Отмена");
            cancelBtn.Click += (s, e) => win.Close();
            var okBtn = MkBtn("Далее");
            okBtn.FontWeight = FontWeights.Bold;
            okBtn.Click += (s, e) =>
            {
                for (int i = 0; i < boxes.Count; i++)
                    if (boxes[i].IsChecked == true) result.Add(list[i]);
                ok = true;
                win.Close();
            };

            buttons.Children.Add(allBtn);
            buttons.Children.Add(noneBtn);
            buttons.Children.Add(cancelBtn);
            buttons.Children.Add(okBtn);

            dock.Children.Add(buttons);
            dock.Children.Add(scroll);
            win.Content = dock;
            win.ShowDialog();
            return ok ? result : null;
        }

        public static Button MkBtn(string text)
        {
            return new Button
            {
                Content = text,
                Padding = new Thickness(10, 4, 10, 4),
                Margin = new Thickness(0, 0, 8, 0)
            };
        }

        public static void Report(string title, string text)
        {
            var win = new Window
            {
                Title = title,
                Width = 900,
                Height = 640,
                WindowStartupLocation = WindowStartupLocation.CenterScreen
            };
            var dock = new DockPanel { LastChildFill = true };
            var close = MkBtn("Закрыть");
            close.HorizontalAlignment = HorizontalAlignment.Right;
            close.Margin = new Thickness(12);
            close.Click += (s, e) => win.Close();
            DockPanel.SetDock(close, Dock.Bottom);
            var tb = new TextBox
            {
                Text = text,
                IsReadOnly = true,
                TextWrapping = TextWrapping.NoWrap,
                VerticalScrollBarVisibility = ScrollBarVisibility.Auto,
                HorizontalScrollBarVisibility = ScrollBarVisibility.Auto,
                FontFamily = new FontFamily("Consolas"),
                Margin = new Thickness(12)
            };
            dock.Children.Add(close);
            dock.Children.Add(tb);
            win.Content = dock;
            win.ShowDialog();
        }
    }

    // ------------------------------------------------------------------ rows
    internal abstract class NotifyRow : INotifyPropertyChanged
    {
        public event PropertyChangedEventHandler PropertyChanged;
        protected void OnChanged(string name)
        {
            var h = PropertyChanged;
            if (h != null) h(this, new PropertyChangedEventArgs(name));
        }
        private bool _selected;
        public bool Selected
        {
            get { return _selected; }
            set { if (_selected != value) { _selected = value; OnChanged("Selected"); } }
        }
    }

    internal sealed class StatusRow : NotifyRow
    {
        public MatchRow Mr;
        public string FamilyName { get { return Mr.FamilyName; } }
        public string Category { get { return Mr.CategoryName ?? ""; } }
        public string Status { get { return Mr.Status; } }
        public string ModelDate
        {
            get { return Mr.Stamp != null && !string.IsNullOrEmpty(Mr.Stamp.Iso)
                ? Mr.Stamp.Iso : "—"; }
        }
        public string CatalogDate
        {
            get { return Mr.Entry != null && !string.IsNullOrEmpty(Mr.Entry.MtimeIso)
                ? Mr.Entry.MtimeIso : "—"; }
        }
        public string CatalogFile { get { return Mr.Entry != null ? Mr.Entry.Rel : "—"; } }
        public double Score { get { return Mr.Score; } }
        public string ScoreText
        {
            get { return Mr.Entry != null
                ? ((int)Math.Round(Mr.Score * 100)).ToString() + "%" : "—"; }
        }
        public void Refresh()
        {
            OnChanged("Status"); OnChanged("ModelDate"); OnChanged("CatalogDate");
            OnChanged("CatalogFile"); OnChanged("Score"); OnChanged("ScoreText");
        }
    }

    internal sealed class LoadRow : NotifyRow
    {
        public CatalogEntry Entry;
        public bool InModel;
        public string FileName { get { return Entry.Name; } }
        public string Folder
        {
            get
            {
                var d = Path.GetDirectoryName(Entry.Rel);
                return string.IsNullOrEmpty(d) ? "." : d;
            }
        }
        public string InModelText { get { return InModel ? "да" : "нет"; } }
        public string CatalogDate
        {
            get { return string.IsNullOrEmpty(Entry.MtimeIso) ? "—" : Entry.MtimeIso; }
        }
    }

    internal sealed class TypeRow : NotifyRow
    {
        public CatalogEntry Entry;
        public string FamilyName { get; set; }
        public string TypeName { get; set; }
    }

    // ------------------------------------------------------------------ helpers
    internal static class Grids
    {
        public static DataGrid New()
        {
            return new DataGrid
            {
                AutoGenerateColumns = false,
                CanUserAddRows = false,
                CanUserDeleteRows = false,
                CanUserResizeRows = false,
                HeadersVisibility = DataGridHeadersVisibility.Column,
                GridLinesVisibility = DataGridGridLinesVisibility.Horizontal,
                IsReadOnly = false,
                Margin = new Thickness(16, 0, 16, 0)
            };
        }

        public static DataGridTextColumn Text(string header, string path,
            double? star = null, string sortPath = null)
        {
            var c = new DataGridTextColumn
            {
                Header = header,
                Binding = new System.Windows.Data.Binding(path),
                IsReadOnly = true
            };
            if (sortPath != null) c.SortMemberPath = sortPath;
            if (star.HasValue)
                c.Width = new DataGridLength(star.Value, DataGridLengthUnitType.Star);
            return c;
        }

        public static DataGridCheckBoxColumn Check(string header)
        {
            var b = new System.Windows.Data.Binding("Selected")
            {
                Mode = System.Windows.Data.BindingMode.TwoWay,
                UpdateSourceTrigger = System.Windows.Data.UpdateSourceTrigger.PropertyChanged
            };
            return new DataGridCheckBoxColumn { Header = header, Binding = b };
        }
    }

    // ------------------------------------------------------------------ status window
    internal sealed class StatusResult
    {
        public List<JobUpdate> Jobs;
        public bool Rename;
        public bool Overwrite;
    }

    internal static class StatusWindow
    {
        public static StatusResult Show(List<MatchRow> rows, string catalogRoot,
            List<CatalogEntry> entries)
        {
            int stale = rows.Count(r => r.Status == C.StatusStale);
            int nostamp = rows.Count(r => r.Status == C.StatusNoStamp);
            int nocat = rows.Count(r => r.Status == C.StatusNoCatalog);
            int cur = rows.Count(r => r.Status == C.StatusCurrent);

            var data = new ObservableCollection<StatusRow>();
            foreach (var mr in rows)
            {
                var sr = new StatusRow { Mr = mr };
                sr.Selected = mr.Entry != null &&
                    (mr.Status == C.StatusStale || mr.Status == C.StatusNoStamp);
                data.Add(sr);
            }

            var win = new Window
            {
                Title = "Семейства из каталога — актуальность и обновление",
                Width = 1120,
                Height = 720,
                WindowStartupLocation = WindowStartupLocation.CenterScreen
            };
            var outer = new DockPanel { LastChildFill = true };

            var header = new StackPanel { Margin = new Thickness(16, 12, 16, 8) };
            DockPanel.SetDock(header, Dock.Top);
            header.Children.Add(new TextBlock
            {
                Text = "Актуальность семейств относительно каталога",
                FontSize = 16, FontWeight = FontWeights.Bold
            });
            header.Children.Add(new TextBlock
            {
                Text = string.Format(
                    "Каталог: {0}\nУстарели: {1}   ·   без метки: {2}   ·   нет в каталоге: {3}   ·   актуальны: {4}\n" +
                    "Красным — требуют обновления, оранжевым — без метки, зелёным — актуальны. " +
                    "Двойной клик по строке или «Файл…» — сменить файл каталога. Отметьте, что обновить.",
                    catalogRoot, stale, nostamp, nocat, cur),
                FontSize = 11, Foreground = Brushes.Gray, TextWrapping = TextWrapping.Wrap,
                Margin = new Thickness(0, 4, 0, 0)
            });

            var grid = Grids.New();
            grid.ItemsSource = data;
            grid.SelectionMode = DataGridSelectionMode.Single;
            grid.Columns.Add(Grids.Check("Обновить"));
            grid.Columns.Add(Grids.Text("Семейство", "FamilyName", 3));
            grid.Columns.Add(Grids.Text("Категория", "Category", 2));
            grid.Columns.Add(Grids.Text("Статус", "Status"));
            grid.Columns.Add(Grids.Text("Дата в модели", "ModelDate"));
            grid.Columns.Add(Grids.Text("Дата в каталоге", "CatalogDate"));
            grid.Columns.Add(Grids.Text("Файл каталога", "CatalogFile", 3));
            grid.Columns.Add(Grids.Text("Похожесть", "ScoreText", null, "Score"));
            grid.LoadingRow += (s, e) =>
            {
                var r = e.Row.Item as StatusRow;
                if (r == null) return;
                e.Row.Foreground = StatusBrush(r.Status);
            };

            Action<StatusRow> chooseFile = row =>
            {
                if (row == null) { Dialogs.Alert("Сначала выделите строку.", "Каталог семейств"); return; }
                var pick = Dialogs.MultiSelect("Файл каталога для «" + row.Mr.FamilyName + "»",
                    entries.OrderBy(x => x.Rel.ToLowerInvariant()), x => x.Rel);
                // MultiSelect returns a list; take first
                if (pick == null || pick.Count == 0) return;
                var e2 = pick[0];
                row.Mr.Entry = e2;
                row.Mr.Score = Names.Similarity(row.Mr.FamilyName, e2.Name);
                row.Mr.Status = StampStore.StatusOf(row.Mr.Stamp, e2);
                row.Refresh();
                row.Selected = true;
                grid.Items.Refresh();
            };
            grid.MouseDoubleClick += (s, e) => chooseFile(grid.SelectedItem as StatusRow);

            var bottom = new StackPanel { Margin = new Thickness(16, 8, 16, 12) };
            DockPanel.SetDock(bottom, Dock.Bottom);
            var overwriteCb = new CheckBox
            {
                Content = "Заменять значения параметров типоразмеров из файла каталога " +
                          "(как «Перезаписать существующую версию и значения параметров»)",
                IsChecked = true,
                Margin = new Thickness(0, 0, 0, 6)
            };
            var renameCb = new CheckBox
            {
                Content = "Переименовывать семейство модели по имени файла каталога, если они различаются",
                IsChecked = true,
                Margin = new Thickness(0, 0, 0, 8)
            };
            bottom.Children.Add(overwriteCb);
            bottom.Children.Add(renameCb);

            var btns = new StackPanel
            {
                Orientation = Orientation.Horizontal,
                HorizontalAlignment = HorizontalAlignment.Right
            };
            bottom.Children.Add(btns);

            Action<Func<StatusRow, bool>> selectWhere = pred =>
            {
                grid.CommitEdit();
                foreach (var r in data) r.Selected = pred(r);
                grid.Items.Refresh();
            };

            var fileBtn = Dialogs.MkBtn("Файл…");
            fileBtn.Click += (s, e) => chooseFile(grid.SelectedItem as StatusRow);
            var staleBtn = Dialogs.MkBtn("Отметить требующие обновления");
            staleBtn.Click += (s, e) => selectWhere(r => r.Mr.Entry != null &&
                (r.Mr.Status == C.StatusStale || r.Mr.Status == C.StatusNoStamp));
            var noneBtn = Dialogs.MkBtn("Снять все");
            noneBtn.Click += (s, e) => selectWhere(r => false);
            var closeBtn = Dialogs.MkBtn("Закрыть");
            closeBtn.Click += (s, e) => win.Close();
            var runBtn = Dialogs.MkBtn("Обновить отмеченные");
            runBtn.FontWeight = FontWeights.Bold;

            StatusResult result = null;
            runBtn.Click += (s, e) =>
            {
                grid.CommitEdit();
                var jobs = new List<JobUpdate>();
                foreach (var r in data)
                {
                    if (!r.Selected || r.Mr.Entry == null) continue;
                    jobs.Add(new JobUpdate
                    {
                        Family = r.Mr.Family,
                        SrcPath = r.Mr.Entry.Path,
                        TargetName = r.Mr.FamilyName,
                        Display = r.Mr.Entry.Rel,
                        CatalogName = r.Mr.Entry.Name
                    });
                }
                if (jobs.Count == 0)
                {
                    Dialogs.Alert("Не отмечено ни одного семейства с файлом в каталоге.",
                        "Каталог семейств");
                    return;
                }
                result = new StatusResult
                {
                    Jobs = jobs,
                    Rename = renameCb.IsChecked == true,
                    Overwrite = overwriteCb.IsChecked == true
                };
                win.Close();
            };

            btns.Children.Add(fileBtn);
            btns.Children.Add(staleBtn);
            btns.Children.Add(noneBtn);
            btns.Children.Add(closeBtn);
            btns.Children.Add(runBtn);

            outer.Children.Add(header);
            outer.Children.Add(bottom);
            outer.Children.Add(grid);
            win.Content = outer;
            win.ShowDialog();
            return result;
        }

        private static Brush StatusBrush(string status)
        {
            if (status == C.StatusStale) return Brushes.Firebrick;
            if (status == C.StatusNoStamp) return Brushes.DarkOrange;
            if (status == C.StatusCurrent) return Brushes.Green;
            return Brushes.Gray;
        }
    }

    // ------------------------------------------------------------------ load window
    internal sealed class LoadDlgResult
    {
        public List<CatalogEntry> Entries;
        public bool Overwrite;
    }

    internal static class LoadWindow
    {
        public static LoadDlgResult Show(List<CatalogEntry> entries,
            HashSet<string> presentNames, string catalogRoot)
        {
            var data = new ObservableCollection<LoadRow>();
            int nNew = 0;
            foreach (var e in entries)
            {
                bool inModel = presentNames.Contains(e.Name);
                if (!inModel) nNew++;
                data.Add(new LoadRow { Entry = e, InModel = inModel, Selected = !inModel });
            }

            var win = new Window
            {
                Title = "Загрузка семейств из каталога",
                Width = 1000,
                Height = 720,
                WindowStartupLocation = WindowStartupLocation.CenterScreen
            };
            var outer = new DockPanel { LastChildFill = true };
            var header = new StackPanel { Margin = new Thickness(16, 12, 16, 8) };
            DockPanel.SetDock(header, Dock.Top);
            header.Children.Add(new TextBlock
            {
                Text = "Загрузить семейства из каталога в модель",
                FontSize = 16, FontWeight = FontWeights.Bold
            });
            header.Children.Add(new TextBlock
            {
                Text = string.Format(
                    "Каталог: {0}\nФайлов: {1}   ·   новых: {2}   ·   уже в модели: {3}\n" +
                    "Зелёным — новые, серым — уже загружены (будут перезагружены). Отметьте нужные.",
                    catalogRoot, entries.Count, nNew, entries.Count - nNew),
                FontSize = 11, Foreground = Brushes.Gray, TextWrapping = TextWrapping.Wrap,
                Margin = new Thickness(0, 4, 0, 0)
            });

            var grid = Grids.New();
            grid.ItemsSource = data;
            grid.SelectionMode = DataGridSelectionMode.Extended;
            grid.Columns.Add(Grids.Check("Загрузить"));
            grid.Columns.Add(Grids.Text("Файл", "FileName", 3));
            grid.Columns.Add(Grids.Text("Папка", "Folder", 2));
            grid.Columns.Add(Grids.Text("В модели", "InModelText"));
            grid.Columns.Add(Grids.Text("Дата файла", "CatalogDate"));
            grid.LoadingRow += (s, e) =>
            {
                var r = e.Row.Item as LoadRow;
                if (r == null) return;
                e.Row.Foreground = r.InModel ? Brushes.Gray : Brushes.Green;
            };

            var bottom = new StackPanel { Margin = new Thickness(16, 8, 16, 12) };
            DockPanel.SetDock(bottom, Dock.Bottom);
            var overwriteCb = new CheckBox
            {
                Content = "Для уже присутствующих — заменять значения параметров типоразмеров",
                IsChecked = true,
                Margin = new Thickness(0, 0, 0, 8)
            };
            bottom.Children.Add(overwriteCb);
            var btns = new StackPanel
            {
                Orientation = Orientation.Horizontal,
                HorizontalAlignment = HorizontalAlignment.Right
            };
            bottom.Children.Add(btns);

            Action<Func<LoadRow, bool>> selectWhere = pred =>
            {
                grid.CommitEdit();
                foreach (var r in data) r.Selected = pred(r);
                grid.Items.Refresh();
            };

            var newBtn = Dialogs.MkBtn("Отметить новые");
            newBtn.Click += (s, e) => selectWhere(r => !r.InModel);
            var allBtn = Dialogs.MkBtn("Отметить все");
            allBtn.Click += (s, e) => selectWhere(r => true);
            var noneBtn = Dialogs.MkBtn("Снять все");
            noneBtn.Click += (s, e) => selectWhere(r => false);
            var closeBtn = Dialogs.MkBtn("Закрыть");
            closeBtn.Click += (s, e) => win.Close();
            var runBtn = Dialogs.MkBtn("Загрузить отмеченные");
            runBtn.FontWeight = FontWeights.Bold;

            LoadDlgResult result = null;
            runBtn.Click += (s, e) =>
            {
                grid.CommitEdit();
                var picked = data.Where(r => r.Selected).Select(r => r.Entry).ToList();
                if (picked.Count == 0)
                {
                    Dialogs.Alert("Не отмечено ни одного семейства.", "Каталог семейств");
                    return;
                }
                result = new LoadDlgResult
                {
                    Entries = picked,
                    Overwrite = overwriteCb.IsChecked == true
                };
                win.Close();
            };

            btns.Children.Add(newBtn);
            btns.Children.Add(allBtn);
            btns.Children.Add(noneBtn);
            btns.Children.Add(closeBtn);
            btns.Children.Add(runBtn);

            outer.Children.Add(header);
            outer.Children.Add(bottom);
            outer.Children.Add(grid);
            win.Content = outer;
            win.ShowDialog();
            return result;
        }
    }

    // ------------------------------------------------------------------ type picker
    internal static class TypePicker
    {
        public static readonly object Back = new object();

        // returns: Dictionary<CatalogEntry, HashSet<string>>  |  TypePicker.Back  |  null
        public static object Show(List<KeyValuePair<CatalogEntry, List<string>>> typeMap)
        {
            if (typeMap.Count == 0) return new Dictionary<CatalogEntry, HashSet<string>>();

            var data = new ObservableCollection<TypeRow>();
            foreach (var kv in typeMap)
            {
                var famName = Path.GetFileNameWithoutExtension(kv.Key.Path);
                foreach (var tn in kv.Value)
                    data.Add(new TypeRow
                    {
                        Entry = kv.Key, FamilyName = famName, TypeName = tn, Selected = true
                    });
            }

            var win = new Window
            {
                Title = "Выбор типоразмеров для загрузки",
                Width = 820,
                Height = 640,
                WindowStartupLocation = WindowStartupLocation.CenterScreen
            };
            var outer = new DockPanel { LastChildFill = true };
            var header = new StackPanel { Margin = new Thickness(16, 12, 16, 8) };
            DockPanel.SetDock(header, Dock.Top);
            header.Children.Add(new TextBlock
            {
                Text = "Отметьте типоразмеры для загрузки в модель",
                FontSize = 16, FontWeight = FontWeights.Bold
            });
            header.Children.Add(new TextBlock
            {
                Text = string.Format("Семейств: {0}   ·   типоразмеров: {1}",
                    typeMap.Count, data.Count),
                FontSize = 11, Foreground = Brushes.Gray, Margin = new Thickness(0, 4, 0, 0)
            });

            var grid = Grids.New();
            grid.ItemsSource = data;
            grid.SelectionMode = DataGridSelectionMode.Extended;
            grid.Columns.Add(Grids.Check("Загрузить"));
            grid.Columns.Add(Grids.Text("Семейство", "FamilyName", 2));
            grid.Columns.Add(Grids.Text("Типоразмер", "TypeName", 3));

            var bottom = new StackPanel { Margin = new Thickness(16, 8, 16, 12) };
            DockPanel.SetDock(bottom, Dock.Bottom);
            var btns = new StackPanel
            {
                Orientation = Orientation.Horizontal,
                HorizontalAlignment = HorizontalAlignment.Right
            };
            bottom.Children.Add(btns);

            Action<bool> selectAll = v =>
            {
                grid.CommitEdit();
                foreach (var r in data) r.Selected = v;
                grid.Items.Refresh();
            };

            object result = null;

            var backBtn = Dialogs.MkBtn("← Назад");
            backBtn.Click += (s, e) => { result = Back; win.Close(); };
            var allBtn = Dialogs.MkBtn("Отметить все");
            allBtn.Click += (s, e) => selectAll(true);
            var noneBtn = Dialogs.MkBtn("Снять все");
            noneBtn.Click += (s, e) => selectAll(false);
            var closeBtn = Dialogs.MkBtn("Закрыть");
            closeBtn.Click += (s, e) => win.Close();
            var runBtn = Dialogs.MkBtn("Загрузить отмеченные");
            runBtn.FontWeight = FontWeights.Bold;
            runBtn.Click += (s, e) =>
            {
                grid.CommitEdit();
                var map = new Dictionary<CatalogEntry, HashSet<string>>();
                foreach (var r in data)
                {
                    if (!r.Selected) continue;
                    HashSet<string> set;
                    if (!map.TryGetValue(r.Entry, out set))
                    { set = new HashSet<string>(); map[r.Entry] = set; }
                    set.Add(r.TypeName);
                }
                if (map.Count == 0)
                {
                    Dialogs.Alert("Не отмечено ни одного типоразмера.", "Каталог семейств");
                    return;
                }
                result = map;
                win.Close();
            };

            btns.Children.Add(backBtn);
            btns.Children.Add(allBtn);
            btns.Children.Add(noneBtn);
            btns.Children.Add(closeBtn);
            btns.Children.Add(runBtn);

            outer.Children.Add(header);
            outer.Children.Add(bottom);
            outer.Children.Add(grid);
            win.Content = outer;
            win.ShowDialog();
            return result;
        }
    }

    // ------------------------------------------------------------------ report text
    internal static class Report
    {
        public static string Update(UpdateResult r)
        {
            var sb = new System.Text.StringBuilder();
            Section(sb, "Обновлены семейства", r.Updated, a =>
                string.Format("  {0}  <-  {1}  (файл {2})", a[0], a[1], a[2] ?? "?"));
            Section(sb, "Переименованы по файлу каталога", r.Renamed, a =>
                string.Format("  «{0}»  ->  «{1}»", a[0], a[1]));
            Section(sb, "Без изменений — содержимое совпадает", r.Unchanged, a =>
                string.Format("  {0}  <-  {1}  (файл {2})", a[0], a[1], a[2] ?? "?"));
            Section(sb, "Не удалось загрузить", r.Failed, a =>
                string.Format("  {0}  <-  {1} — {2}", a[0], a[1], a[2]));
            Section(sb, "Обновлены, но не переименованы", r.RenameFailed, a =>
                string.Format("  «{0}»  ->  «{1}» — {2}", a[0], a[1], a[2]));
            if (r.StampFailed.Count > 0)
                sb.AppendLine().AppendLine("### Метку даты записать не удалось (" +
                    r.StampFailed.Count + ")").AppendLine("  " +
                    string.Join("\n  ", r.StampFailed));
            if (r.Debug.Count > 0)
                sb.AppendLine().AppendLine("### Диагностика").AppendLine("  " +
                    string.Join("\n  ", r.Debug));
            return sb.ToString();
        }

        public static string Load(LoadResult r)
        {
            var sb = new System.Text.StringBuilder();
            Section(sb, "Загружены новые семейства", r.Loaded, a =>
                string.Format("  {0}  <-  {1}  (файл {2})", a[0], a[1], a[2] ?? "?"));
            Section(sb, "Перезагружены (уже были в модели)", r.Updated, a =>
                string.Format("  {0}  <-  {1}  (файл {2})", a[0], a[1], a[2] ?? "?"));
            Section(sb, "Не удалось загрузить", r.Failed, a =>
                string.Format("  {0}  <-  {1} — {2}", a[0], a[1], a[2]));
            if (r.StampFailed.Count > 0)
                sb.AppendLine().AppendLine("### Метку даты записать не удалось (" +
                    r.StampFailed.Count + ")").AppendLine("  " +
                    string.Join("\n  ", r.StampFailed));
            return sb.ToString();
        }

        private static void Section(System.Text.StringBuilder sb, string title,
            List<string[]> rows, Func<string[], string> fmt)
        {
            if (rows.Count == 0) return;
            sb.AppendLine();
            sb.AppendLine(string.Format("### {0} ({1})", title, rows.Count));
            foreach (var a in rows) sb.AppendLine(fmt(a));
        }
    }
}
