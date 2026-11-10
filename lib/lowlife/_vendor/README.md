# Bundled PDF dependency

PyPDF2 1.26.0 (BSD-3-Clause; see [LICENSE](PyPDF2/LICENSE)) is bundled unchanged
from the PyPI source distribution to support IronPython 2.7 and CPython 3
without a runtime package install. Imported through `lowlife._vendor.PyPDF2`.
Used only for local PDF export merging. No Revit or model dependencies.
