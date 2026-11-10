# -*- coding: utf-8 -*-
"""Merge numbered PDF exports without removing sources before verification."""
import os
import re
import tempfile

from lowlife.i18n import tr
from lowlife.link_datums_core import natural_key


def plan_merges(folder):
    """Return (output, sources) groups in this folder only; ignore singletons."""
    groups = {}
    for name in sorted(os.listdir(folder), key=natural_key):
        match = re.match(r'^(.+)_([0-9]+)\.pdf$', name, re.I)
        if match and os.path.isfile(os.path.join(folder, name)):
            key = match.group(1).lower()
            groups.setdefault(key, [match.group(1), []])[1].append(
                (int(match.group(2)), os.path.join(folder, name)))
    return [(os.path.join(folder, stem + '.pdf'),
             [path for number, path in sorted(items)])
            for stem, items in sorted(groups.values(), key=lambda g: natural_key(g[0]))
            if len(items) > 1]


def merge_group(output, sources):
    """Publish verified PDF, then delete its sources; return cleanup failures.

    os.rename refuses an existing destination on Windows. All input streams stay
    open until writing finishes (PDF objects may be resolved lazily).
    """
    from lowlife._vendor.PyPDF2 import PdfFileReader, PdfFileWriter

    if os.path.exists(output):
        raise IOError(tr(u'Итоговый файл уже существует.', u'The output file already exists.'))
    if len(sources) < 2 or len(set(os.path.normcase(os.path.abspath(p)) for p in sources)) != len(sources):
        raise ValueError('Expected at least two distinct source PDFs')
    if os.path.normcase(os.path.abspath(output)) in [os.path.normcase(os.path.abspath(p)) for p in sources]:
        raise ValueError('Output must differ from all sources')
    streams = []
    temporary = None
    try:
        writer = PdfFileWriter()
        count = 0
        snapshots = [(os.path.getsize(p), os.path.getmtime(p)) for p in sources]
        for path in sources:
            stream = open(path, 'rb')
            streams.append(stream)
            reader = PdfFileReader(stream, strict=False)
            if reader.isEncrypted or reader.getNumPages() == 0:
                raise ValueError(tr(u'Защищённый или пустой PDF: {}', u'Encrypted or empty PDF: {}').format(path))
            for page in reader.pages:
                writer.addPage(page)
                count += 1
        fd, temporary = tempfile.mkstemp(prefix='.lowlife-merge-', suffix='.tmp', dir=os.path.dirname(output))
        with os.fdopen(fd, 'wb') as stream:
            writer.write(stream)
            stream.flush()
            os.fsync(stream.fileno())
        with open(temporary, 'rb') as stream:
            verified = PdfFileReader(stream, strict=False)
            if verified.getNumPages() != count:
                raise ValueError('PDF page count mismatch')
            for page in verified.pages:
                page.getContents()
        if snapshots != [(os.path.getsize(p), os.path.getmtime(p)) for p in sources]:
            raise IOError(tr(u'Исходные PDF изменились во время объединения.', u'Source PDFs changed during merging.'))
        for stream in streams:
            stream.close()
        os.rename(temporary, output)
        temporary = None
    finally:
        for stream in streams:
            stream.close()
        if temporary and os.path.exists(temporary):
            os.remove(temporary)
    errors = []
    for path in sources:
        try:
            os.remove(path)
        except OSError as exc:
            errors.append((path, str(exc)))
    return errors


def run():
    """Folder picker and explicit preview of files that will be removed."""
    from pyrevit import forms
    from lowlife.settings_core import JsonStore

    title = tr(u'Объединить PDF', u'Merge PDFs')
    store = JsonStore('LowLifePdfMerge_settings.json')
    folder = forms.pick_folder(title=title)
    if not folder:
        return
    store.update({'last_folder': folder})
    plans = plan_merges(folder)
    if not plans:
        forms.alert(tr(u'Группы PDF с суффиксами _1, _2, … не найдены.',
                       u'No PDF groups with suffixes _1, _2, … found.'), title=title)
        return
    preview = u'\n\n'.join(u'{}\n  {}'.format(os.path.basename(out),
        u' → '.join(os.path.basename(p) for p in paths)) for out, paths in plans)
    if not forms.alert(tr(u'Объединить группы? Исходные файлы будут удалены после проверки результата. Занятые имена пропускаются.\n\n{}',
                         u'Merge groups? Source files will be deleted after verification. Existing output names are skipped.\n\n{}').format(preview),
                       title=title, yes=True, no=True):
        return
    completed = 0
    errors = []
    for output, sources in plans:
        try:
            cleanup = merge_group(output, sources)
            completed += 1
            errors.extend(u'{}: {}'.format(path, error) for path, error in cleanup)
        except Exception as exc:
            errors.append(u'{}: {}'.format(os.path.basename(output), exc))
    forms.alert(tr(u'Создано PDF: {}', u'PDFs created: {}').format(completed)
                + (u'\n\n' + u'\n'.join(errors) if errors else u''), title=title)
