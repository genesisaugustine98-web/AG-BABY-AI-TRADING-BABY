"""Allow `python -m apps.trading_runtime` to run the canonical process."""
from .main import main

raise SystemExit(main())
