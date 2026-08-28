# -*- coding: utf-8 -*-
"""
JSON-манифест структурной схемы СКУД.

BuildSkudSchematic после раскладки пишет сюда полное описание того, что
поставлено (контроллеры → точки прохода → устройства, с id реальных и
схемных элементов, адресами, помещениями, именем подобранной группы).
UpdateSkudSchematic читает манифест и по нему обновляет схему без полной
пересборки.

Файл лежит рядом с .rvt: <путь_проекта_без_расширения>.skud_schematic.json.
Если проект не сохранён (doc.PathName пуст) — временный файл в
%APPDATA%\\pyRevit (и вызывающий скрипт предупреждает пользователя).
"""

import os
import io
import json

SCHEMA_VERSION = 1

_UNSAVED_FILE_NAME = "LowLifeSKUD_schematic_unsaved.json"


def manifest_path(doc):
    """(path, is_beside_project). Путь к файлу манифеста для документа."""
    project_path = u""
    try:
        project_path = doc.PathName or u""
    except:
        project_path = u""

    if project_path:
        base, _ext = os.path.splitext(project_path)
        return base + u".skud_schematic.json", True

    appdata = os.environ.get("APPDATA") or os.path.expanduser("~")
    folder = os.path.join(appdata, "pyRevit")
    if not os.path.isdir(folder):
        try:
            os.makedirs(folder)
        except:
            pass
    return os.path.join(folder, _UNSAVED_FILE_NAME), False


def write_manifest(doc, data):
    """Пишет data (dict) в файл манифеста. Возвращает (path, is_beside_project)."""
    path, beside = manifest_path(doc)
    payload = dict(data)
    payload["schema_version"] = SCHEMA_VERSION

    with io.open(path, "w", encoding="utf-8") as f:
        f.write(unicode(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)))

    return path, beside


def read_manifest(doc):
    """dict из файла манифеста, либо None если файла нет / он битый."""
    path, _beside = manifest_path(doc)

    if not os.path.isfile(path):
        return None

    try:
        with io.open(path, "r", encoding="utf-8") as f:
            text = f.read()
        if not text.strip():
            return None
        return json.loads(text)
    except:
        return None
