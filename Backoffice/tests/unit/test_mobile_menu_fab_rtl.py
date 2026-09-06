"""Guard that the admin side-menu FAB swaps corners in RTL (Arabic)."""

from pathlib import Path

_CSS_DIR = Path(__file__).resolve().parents[2] / "app" / "static" / "css"


def test_mobile_menu_fab_rtl_moves_to_end_corner():
    rtl = (_CSS_DIR / "rtl.css").read_text(encoding="utf-8")
    responsive = (_CSS_DIR / "responsive.css").read_text(encoding="utf-8")

    assert 'html[dir="rtl"] #mobileMenuFAB' in rtl
    assert 'html[dir="rtl"] #mobileMenuFAB' in responsive
    assert "right: calc(1.5rem + env(safe-area-inset-right, 0px))" in rtl
    assert "left: auto !important" in rtl.split('html[dir="rtl"] #mobileMenuFAB', 1)[1]

    # Pair stays opposite: chatbot stays on the start side in RTL.
    assert 'html[dir="rtl"] #aiChatbotFAB' in rtl
    assert "left: calc(1.5rem + env(safe-area-inset-left, 0px))" in rtl
