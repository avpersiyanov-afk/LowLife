import shutil
import subprocess
from pathlib import Path
import pytest

def test_apps_script_authorization_publication_retries_and_projections():
    node=shutil.which('node')
    if not node:
        pytest.skip('Node is required to execute Apps Script protocol tests')
    root=Path(__file__).resolve().parents[1]
    subprocess.run([node,str(root/'tests/opening_journal_server.cjs'),
                    str(root/'docs/opening-journal/Code.gs')],check=True,capture_output=True,text=True)
