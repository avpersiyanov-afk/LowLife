# Hide in link

**Tools → Hide in link**, **General** theme, Revit 2024+.

Open a graphical project view, click the button and define a criterion using
family name, type name, parameter value or workset name. For a parameter,
choose instance, type, or instance with a type fallback only when the instance
parameter does not exist. Select loaded link instances and categories, review
matching elements, uncheck anything to keep, then click **Hide selected**.
Canceling leaves visibility unchanged. Shift+click edits settings only.

Conditions include contains, equals, their negatives, starts with, empty and
not empty. Matching uses literal text without case or surrounding whitespace.
Numeric parameters use their displayed Revit text, not numeric comparisons.
Missing parameters never match, including negative conditions; an existing
parameter without a value is empty. Ambiguous parameter names stop the operation.

This is a one-time hide operation in the current view. It is not a live Revit
filter: run again for new elements or changed parameter values. Use Revit's
Reveal Hidden Elements / Unhide in View, or Undo, to restore visibility.
Only selected link instances are targeted. Nested links are not traversed;
linked documents, host elements, view templates and link overrides are not edited.

Settings: `%APPDATA%\pyRevit\LowLifeLinkHide_settings.json`. Parameter name
suggestions and shared settings export/import are available.

Candidates come from Revit's host-view/link-instance collector (2024+), whose
visibility is not a pixel or occlusion test. Hiding uses linked references and
Revit's native Hide Elements command, queued after the script exits. Successful
queueing does not prove execution. See the [Autodesk example](https://blog.autodesk.io/revit-2025-api-video-and-hiding-linked-elements/).

Manual acceptance: insert the same link twice and check that hiding affects
only the selected instance; test parameter scopes, missing/empty values,
categories, negative conditions, preview exclusions, cancellation, view templates,
unloaded links, unsupported views, unavailable commands, repeated runs and Undo.
Check both interface languages and both icon themes.
