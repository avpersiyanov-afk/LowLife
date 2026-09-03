// FamilyCatalog — IExternalApplication: builds the ribbon tab/panel with 2 buttons.

using System;
using System.Reflection;
using System.Windows.Media.Imaging;
using Autodesk.Revit.UI;

namespace FamilyCatalog
{
    public class App : IExternalApplication
    {
        private const string TabName = "Каталог семейств";
        private const string PanelName = "Семейства из каталога";

        public Result OnStartup(UIControlledApplication app)
        {
            try
            {
                try { app.CreateRibbonTab(TabName); } catch { /* already exists */ }
                RibbonPanel panel = null;
                foreach (var p in app.GetRibbonPanels(TabName))
                    if (p.Name == PanelName) { panel = p; break; }
                if (panel == null) panel = app.CreateRibbonPanel(TabName, PanelName);

                var asmPath = Assembly.GetExecutingAssembly().Location;
                var asmDir = System.IO.Path.GetDirectoryName(asmPath);

                var sync = new PushButtonData(
                    "FamilyCatalog_Sync", "Семейства\nиз каталога",
                    asmPath, "FamilyCatalog.SyncCommand");
                sync.ToolTip = "Сверить семейства выбранных категорий с папкой-каталогом .rfa " +
                    "и обновить отмеченные (перезагрузка, замена значений параметров, " +
                    "при различии имён — переименование). Shift+клик — сменить папку каталога.";
                sync.LargeImage = LoadPng(asmDir, "sync.png");

                var load = new PushButtonData(
                    "FamilyCatalog_Load", "Загрузить\nсемейства",
                    asmPath, "FamilyCatalog.LoadCommand");
                load.ToolTip = "Загрузить семейства из каталога .rfa в модель: выбор разделов, " +
                    "таблица файлов, окно выбора типоразмеров. Shift+клик — сменить папку каталога.";
                load.LargeImage = LoadPng(asmDir, "load.png");

                panel.AddItem(sync);
                panel.AddItem(load);
                return Result.Succeeded;
            }
            catch (Exception ex)
            {
                TaskDialog.Show("FamilyCatalog", "OnStartup: " + ex);
                return Result.Failed;
            }
        }

        public Result OnShutdown(UIControlledApplication app)
        {
            return Result.Succeeded;
        }

        private static BitmapImage LoadPng(string dir, string file)
        {
            try
            {
                var p = System.IO.Path.Combine(dir, file);
                if (!System.IO.File.Exists(p)) return null;
                var bmp = new BitmapImage();
                bmp.BeginInit();
                bmp.CacheOption = BitmapCacheOption.OnLoad;
                bmp.UriSource = new Uri(p, UriKind.Absolute);
                bmp.EndInit();
                bmp.Freeze();
                return bmp;
            }
            catch { return null; }
        }
    }
}
