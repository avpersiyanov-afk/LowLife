# -*- coding: utf-8 -*-
"""Safe Revit view/filter names; registry identity is unaffected by display names."""
import re
try:
    unicode
except NameError:
    unicode = str


def safe_name(value, limit=200):
    text=re.sub(u'[\\\\:{}\\[\\]|;<>?`~"\\x00-\\x1f]+',u' - ',unicode(value or u''))
    text=re.sub(u'\\s+',u' ',text).strip(u' -')
    return (text or u'LowLife')[:limit].rstrip()
