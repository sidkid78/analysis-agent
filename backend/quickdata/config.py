"""Runtime configuration.

``DATA_DIR`` is where bundled sample datasets live. It defaults to the repo's
``backend/data`` directory but can be overridden with the ``QUICKDATA_DATA_DIR``
environment variable — needed when the package is installed into a container's
site-packages, where the source-relative path no longer points at the data.
"""

from __future__ import annotations

import os
from pathlib import Path

_DEFAULT = Path(__file__).resolve().parent.parent / "data"

DATA_DIR = Path(os.getenv("QUICKDATA_DATA_DIR") or _DEFAULT)
