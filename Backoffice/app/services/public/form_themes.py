"""Visual themes for public form links.

A public assignment link (``/forms/public/<token>``) is opened by people outside
the organisation, often for a campaign or an occasion. An admin can pick a theme
on the assignment so the form looks like the occasion instead of the back office.

A theme is code, not data. Adding one means:

1. Add a stylesheet under ``app/static/css/public-form-themes/``.
2. Optionally add a hero partial under ``app/templates/forms/public/themes/``
   (the banner shown above the form; it may also carry a language switcher).
3. Register it in ``PUBLIC_FORM_THEMES`` below.

The stylesheet loads after the normal form CSS, so it can restyle anything. The
shared ``base.css`` hides the back-office chrome (navigation, sidebar, assistant,
floating menus) on every themed page.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

# Stylesheet shared by all themes: hides the back-office shell and centres the form.
BASE_STYLESHEET = "css/public-form-themes/base.css"

# Value stored on the assignment for "no theme". The column is nullable, so an
# empty value means the same.
DEFAULT_THEME_KEY = ""


@dataclass(frozen=True)
class PublicFormTheme:
    key: str
    label: str
    description: str
    stylesheet: str
    # Template rendered above the form (relative to ``app/templates``), or None.
    hero_template: Optional[str] = None
    # Browser address-bar colour on mobile.
    theme_color: Optional[str] = None

    @property
    def base_stylesheet(self) -> str:
        return BASE_STYLESHEET


PUBLIC_FORM_THEMES: Dict[str, PublicFormTheme] = {
    theme.key: theme
    for theme in (
        PublicFormTheme(
            key="16_days_of_activism",
            label="16 Days of Activism against Gender-based Violence",
            description=(
                "Orange campaign look for 25 November to 10 December. "
                "Hides the back-office navigation and adds a campaign banner."
            ),
            stylesheet="css/public-form-themes/16-days-of-activism.css",
            hero_template="forms/public/themes/_16_days_of_activism_hero.html",
            theme_color="#ea580c",
        ),
    )
}


def normalize_theme_key(value: Optional[str]) -> str:
    """Stored key for ``value``; unknown or empty values mean "no theme"."""
    key = (value or "").strip()
    return key if key in PUBLIC_FORM_THEMES else DEFAULT_THEME_KEY


def get_public_form_theme(value: Optional[str]) -> Optional[PublicFormTheme]:
    """The theme registered under ``value``, or None for the default look."""
    return PUBLIC_FORM_THEMES.get(normalize_theme_key(value))


def public_form_theme_choices() -> List[Tuple[str, str]]:
    """``(key, label)`` pairs for a select field; the default look comes first."""
    return [(DEFAULT_THEME_KEY, "Default (standard back-office look)")] + [
        (theme.key, theme.label) for theme in PUBLIC_FORM_THEMES.values()
    ]


def public_form_theme_for_assignment(assignment) -> Optional[PublicFormTheme]:
    """Theme chosen on ``assignment``, or None when it uses the default look."""
    return get_public_form_theme(getattr(assignment, "public_form_theme", None))
