# -*- coding: utf-8 -*-
"""
После завершения команды ModPlus «Экспорт» (или другой команды, чей
идентификатор подходит под настроенные подстроки) — предложить
переименовать выгруженные файлы «0000» → «000».

Определить папку выгрузки программно нельзя (ModPlus в этой среде нет,
его конфиг не читаем), поэтому дальше работает полуавтомат из
lowlife.export_rename.run_after_export: спрашивает папку с уже
подставленным прошлым путём (подтверждается Enter'ом), показывает список
и переименовывает файлы. В модели Revit ничего не меняется — транзакция
не нужна.

Настройка: Shift+клик по кнопке Tools.panel «Переименование выгрузки».
Подстроки-триггеры по умолчанию — ["modplus"]; если срабатывает на
лишних командах ModPlus, сузьте до точного идентификатора команды
экспорта (он показывается в окне настроек как «последняя пойманная
команда»).

Хук без [command_id] в имени файла срабатывает после любой команды —
если конкретная сборка pyRevit так не умеет и хук молчит, переименуйте
файл в hooks/command-after-exec[<точный id команды>].py.
"""

try:
    from pyrevit import EXEC_PARAMS
    from lowlife import export_rename
except Exception:
    EXEC_PARAMS = None
    export_rename = None


def _command_id_text(args):
    for getter in (
        lambda: args.CommandId.Name,
        lambda: args.CommandId.Id,
        lambda: args.CommandId,
    ):
        try:
            value = getter()
        except Exception:
            continue
        if value:
            return unicode(value)
    return u""


def _succeeded(args):
    """True, если команда не была отменена/провалена (или статус недоступен)."""
    try:
        from Autodesk.Revit.UI import Result
        return args.Status == Result.Succeeded
    except Exception:
        return True


def _run():
    if export_rename is None or EXEC_PARAMS is None:
        return

    try:
        cfg = export_rename.load_config()
    except Exception:
        return

    if not cfg.get("enabled") or not cfg.get("trigger_substrings"):
        return

    try:
        args = EXEC_PARAMS.event_args
    except Exception:
        args = None
    if args is None:
        return

    if not _succeeded(args):
        return

    command_id_text = _command_id_text(args)
    if not export_rename.command_matches(command_id_text, cfg):
        return

    try:
        export_rename.run_after_export(command_id_text=command_id_text, cfg=cfg)
    except Exception:
        pass


_run()
