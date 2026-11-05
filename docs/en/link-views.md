# Linked model views

**LowLife → General → Tools → Linked views**. Requires Revit 2024 or later.

1. Open the host model view whose link display you want to configure.
2. Click **Linked views** and select host views of the same type as the current view.
   Use the model checkboxes at the top of the dialog to choose which linked models
   to configure on all selected host views. All models are unchecked initially; check only the models you need.
   Unchecking a model hides its instances and excludes them from applying and copying
   settings. Assignments remain in the dialog if you check the model again.
   Each host view has its own section showing selected link instances and their current display settings.
3. For each link, choose a view from the **New view** dropdown in the same dialog.
   Revit 2025 and later also offer **Custom settings**. This switches the link display
   mode while retaining its existing graphics settings and assigned linked view.
   Edit individual settings in Revit's **Visibility/Graphics → Revit Links** dialog.
   The **Search** field above the dropdown filters views by part of a name or words
   in any order, ignoring case and supporting the wrong keyboard layout. Clear the
   search to restore all views. If the selected view no longer matches, its assignment is cleared.
   Choosing a view checks that instance automatically; uncheck it to leave it unchanged.
4. Use **Copy to other views…** in a section to copy its checked assignments to
   selected host views. This replaces assignments for the same links in those sections;
   other assignments are preserved.
5. Click **Apply** to switch checked instances to **By linked view** or **Custom settings**
   according to the selected option.

The same link can use different linked views on different host views.
Each model can use a different view. One model checkbox covers all its instances,
which are listed separately with their IDs for view assignment.
Only non-template views of the same type as the host
view are offered. Revit performs the final compatibility validation.
Unloaded links are listed but disabled. Links without matching views still offer
**Custom settings** in Revit 2025 and later.

Revit 2024 does not support enabling Custom through the API; configure it manually
in Revit. API support was [added in Revit 2025](https://blog.autodesk.io/whats-new-in-the-revit-2025-api/).

When the host view template controls **Revit Links**, the command asks you to
exclude that parameter from template control. It does not edit the template.

The batch is one transaction and one Revit Undo step. An error rolls back the
entire batch. Cancel or closing the window changes nothing. Link types and
linked documents are not edited.

Manual Revit validation: assign different views to two links, including two
instances of the same model, and inspect **Visibility/Graphics → Revit Links**.
Check Undo, cancellation, unloaded links, template control and reopening the dialog.
Also uncheck a model after assigning a view: its instances must remain unchanged
on all host views, including after copying settings.

[Русский](../link-views.md)

