using System;
using System.Text.RegularExpressions;
using Autodesk.Revit.Attributes;
using Autodesk.Revit.DB;
using Autodesk.Revit.UI;

namespace FamilyVersionStamp
{
    /// <summary>
    /// Проставляет в открытом семействе параметры "SMNX_Дата семейства"
    /// (текущая дата) и "SMNX_Версия семейства" (ver.N -> ver.(N+1), пусто ->
    /// ver.1), затем сохраняет файл семейства. Работает только с документом
    /// семейства (Family Editor).
    /// </summary>
    [Transaction(TransactionMode.Manual)]
    [Regeneration(RegenerationOption.Manual)]
    public class Command : IExternalCommand
    {
        private const string DateParamName = "SMNX_Дата семейства";
        private const string VersionParamName = "SMNX_Версия семейства";
        private static readonly Regex VersionPattern =
            new Regex(@"^\s*ver\.(\d+)\s*$", RegexOptions.IgnoreCase | RegexOptions.Compiled);

        public Result Execute(ExternalCommandData commandData, ref string message, ElementSet elements)
        {
            UIDocument uidoc = commandData.Application.ActiveUIDocument;
            if (uidoc == null)
            {
                message = "Нет открытого документа.";
                return Result.Failed;
            }

            Document doc = uidoc.Document;

            if (!doc.IsFamilyDocument)
            {
                TaskDialog.Show(
                    "Штамп версии семейства",
                    "Команда работает только с открытым документом семейства (Family Editor)."
                );
                return Result.Cancelled;
            }

            FamilyManager fm = doc.FamilyManager;

            FamilyParameter dateParam = FindParam(fm, DateParamName);
            FamilyParameter versionParam = FindParam(fm, VersionParamName);

            string missing = null;
            if (dateParam == null)
                missing = DateParamName;
            if (versionParam == null)
                missing = missing == null ? VersionParamName : missing + ", " + VersionParamName;

            if (missing != null)
            {
                TaskDialog.Show(
                    "Штамп версии семейства",
                    "В семействе не найден(ы) параметр(ы): " + missing +
                    "\n\nСоздайте их в диспетчере параметров семейства (текстовые) и запустите команду ещё раз."
                );
                return Result.Cancelled;
            }

            if (dateParam.StorageType != StorageType.String || versionParam.StorageType != StorageType.String)
            {
                TaskDialog.Show(
                    "Штамп версии семейства",
                    "Параметры \"" + DateParamName + "\" и \"" + VersionParamName +
                    "\" должны быть текстовыми (Text) — команда умеет писать только строковые значения."
                );
                return Result.Cancelled;
            }

            FamilyType currentType = fm.CurrentType;
            if (currentType == null)
            {
                TaskDialog.Show(
                    "Штамп версии семейства",
                    "В семействе нет ни одного типоразмера — нечего проставлять."
                );
                return Result.Cancelled;
            }

            string oldVersionValue = currentType.AsString(versionParam);
            string newVersionValue = NextVersion(oldVersionValue);
            string dateValue = DateTime.Now.ToString("dd.MM.yyyy");

            using (Transaction tx = new Transaction(doc, "Штамп даты/версии семейства"))
            {
                tx.Start();

                foreach (FamilyType type in fm.Types)
                {
                    fm.CurrentType = type;

                    if (!dateParam.IsDeterminedByFormula)
                        fm.Set(dateParam, dateValue);

                    if (!versionParam.IsDeterminedByFormula)
                        fm.Set(versionParam, newVersionValue);
                }

                fm.CurrentType = currentType;

                tx.Commit();
            }

            if (string.IsNullOrEmpty(doc.PathName))
            {
                TaskDialog.Show(
                    "Штамп версии семейства",
                    "Дата и версия проставлены (" + dateValue + ", " + newVersionValue + "),\n" +
                    "но файл семейства ещё ни разу не сохранялся — сохраните его вручную (Файл -> Сохранить как)."
                );
                return Result.Succeeded;
            }

            doc.Save();

            TaskDialog.Show(
                "Штамп версии семейства",
                "Готово.\n\nДата: " + dateValue +
                "\nВерсия: " + (string.IsNullOrEmpty(oldVersionValue) ? "(пусто)" : oldVersionValue) +
                " -> " + newVersionValue +
                "\nСохранено: " + doc.PathName
            );

            return Result.Succeeded;
        }

        private static FamilyParameter FindParam(FamilyManager fm, string name)
        {
            foreach (FamilyParameter p in fm.Parameters)
            {
                if (p.Definition.Name == name)
                    return p;
            }
            return null;
        }

        private static string NextVersion(string current)
        {
            if (!string.IsNullOrEmpty(current))
            {
                Match m = VersionPattern.Match(current);
                if (m.Success)
                {
                    int n = int.Parse(m.Groups[1].Value);
                    return "ver." + (n + 1);
                }
            }
            return "ver.1";
        }
    }
}
