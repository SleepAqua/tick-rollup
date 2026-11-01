"""tick-rollup: turn a tick CSV into OHLCV bars, session by session.

Pure standard library. No dependencies, no network, no data from anywhere but
the file you point it at.
"""

from .bars import Bar
from .sessions import DEFAULT_SESSIONS, SessionSpec

__version__ = "1.0.0"
__all__ = ["Bar", "SessionSpec", "DEFAULT_SESSIONS", "__version__"]
