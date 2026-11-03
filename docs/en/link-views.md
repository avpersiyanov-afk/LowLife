# Linked model views

**LowLife → General → Tools → Linked views**. Requires Revit 2024 or later.

1. Open the host model view whose link display you want to configure.
2. Click **Linked views** to see link instances and their current display settings.
3. Click **Choose view…** for each link and search for its view by name.
   Choosing a view checks that instance automatically; uncheck it to leave it unchanged.
4. Click **Apply** to switch the checked instances to **By linked view** together.

Each model can use a different view. Multiple instances of one model are listed
separately with their IDs. Only non-template views of the same type as the host
view are offered. Revit performs the final compatibility validation.
Unloaded links and links without matching view types are listed but disabled.

When the host view template controls **Revit Links**, the command asks you to
exclude that parameter from template control. It does not edit the template.

The batch is one transaction and one Revit Undo step. An error rolls back the
entire batch. Cancel or closing the window changes nothing. Link types and
linked documents are not edited.

Manual Revit validation: assign different views to two links, including two
instances of the same model, and inspect **Visibility/Graphics → Revit Links**.
Check Undo, cancellation, unloaded links, template control and reopening the dialog.

[Русский](../link-views.md)
