import sys
from pathlib import Path

# Ensure the package parent (the directory that contains the 'sqf_to_tcl' folder)
# is on sys.path so imports like 'sqf_to_tcl.converter' work when pytest runs
tests_dir = Path(__file__).resolve().parent
project_dir = tests_dir.parent
project_parent = project_dir.parent
if str(project_parent) not in sys.path:
    sys.path.insert(0, str(project_parent))
