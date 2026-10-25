# -*- coding: utf-8 -*-
"""Translate literal XAML captions without changing bindings or trigger values.

Add ``<!-- lowlife:i18n -->`` to translated files so i18n_tool extracts their captions.
Only UI attributes and plain Hyperlink text are translated; the XAML structure stays intact.
"""
import io
import re
from xml.sax.saxutils import escape, unescape

from lowlife.i18n import tr

MARKER = '<!-- lowlife:i18n -->'
_ATTR = re.compile(r'(?P<head>\b(?:Title|Text|Content|Header|ToolTip)\s*=\s*)'
                   r'(?P<quote>[\"\x27])(?P<text>.*?)(?P=quote)', re.S)
_LINK = re.compile(r'(?P<head><Hyperlink\b[^>]*>)(?P<text>[^<]+)(?P<tail></Hyperlink>)', re.S)


def _literal(value):
    text = unescape(value, {'&quot;': '"', '&apos;': "'"})
    return text if text.strip() and not text.lstrip().startswith('{') else None


def strings(source):
    """Literal captions used by the catalog extractor (no Revit or WPF dependency)."""
    for pattern in (_ATTR, _LINK):
        for match in pattern.finditer(source):
            text = _literal(match.group('text'))
            if text:
                yield text


def translate(source):
    """Translate text with the current language, keeping non-caption attributes unchanged."""
    def replace(match):
        text = _literal(match.group('text'))
        translated = tr(text) if text else text
        if not text or translated == text:
            return match.group(0)
        encoded = escape(translated, {'"': '&quot;', "'": '&apos;'})
        if 'quote' in match.re.groupindex:
            quote = match.group('quote')
            return match.group('head') + quote + encoded + quote
        return match.group('head') + encoded + match.group('tail')
    return _LINK.sub(replace, _ATTR.sub(replace, source))


def load(path):
    with io.open(path, encoding='utf-8-sig') as stream:
        return translate(stream.read())
