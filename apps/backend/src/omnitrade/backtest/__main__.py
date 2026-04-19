"""Entry point: ``python -m omnitrade.backtest``."""

from __future__ import annotations

import sys

from omnitrade.backtest.cli import main

if __name__ == "__main__":
    sys.exit(main())
