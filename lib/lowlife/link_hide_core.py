# -*- coding: utf-8 -*-
"""Text criteria for linked elements; no Revit dependencies."""
try:
    unicode
except NameError:
    unicode = str

OPERATORS = ("contains", "equals", "not_contains", "not_equals", "starts_with", "empty", "not_empty")
FIELDS = ("family", "type", "parameter", "workset")
SCOPES = ("instance", "type", "instance_or_type")


def validate(settings):
    """Return an error code; never let an empty substring match everything."""
    if settings.get("field") not in FIELDS:
        return "field"
    if settings.get("operator") not in OPERATORS:
        return "operator"
    if settings.get("field") == "parameter":
        if not unicode(settings.get("filter_param_name") or u"").strip():
            return "parameter"
        if settings.get("scope") not in SCOPES:
            return "scope"
    if settings.get("operator") not in ("empty", "not_empty"):
        if not unicode(settings.get("value") or u"").strip():
            return "value"
    return None


def matches(actual, operator, expected=u""):
    """None means unavailable, never a match, including negative conditions.

    Compare literal text without case or surrounding whitespace. No regex or
    keyboard-layout conversion: these are model values, not a search box.
    """
    if operator not in OPERATORS:
        raise ValueError("Unknown operator: " + unicode(operator))
    if actual is None:
        return False
    actual = unicode(actual).strip().lower()
    expected = unicode(expected or u"").strip().lower()
    if operator == "empty":
        return not actual
    if operator == "not_empty":
        return bool(actual)
    if not expected:
        raise ValueError("Empty comparison value")
    if operator == "contains":
        return expected in actual
    if operator == "equals":
        return expected == actual
    if operator == "not_contains":
        return expected not in actual
    if operator == "not_equals":
        return expected != actual
    return actual.startswith(expected)
