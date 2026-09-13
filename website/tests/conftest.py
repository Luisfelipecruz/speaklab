import sys
from pathlib import Path

# The builder and the notes script are run as `python website/<script>.py`, which puts
# website/ first on the path; the tests import them the same way.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
