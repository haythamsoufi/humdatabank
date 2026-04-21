"""
Compatibility wrapper.

Use `scripts/trigger_automated_trace_review.py` instead.
"""

from __future__ import annotations

import warnings

from trigger_automated_trace_review import main


if __name__ == "__main__":
    warnings.warn(
        "scripts/export_trace_reviews.py is deprecated. "
        "Use scripts/trigger_automated_trace_review.py instead.",
        DeprecationWarning,
        stacklevel=1,
    )
    main()
