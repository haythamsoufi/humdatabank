"""
Documentation rendering/navigation service.

This module provides shared helpers to:
- Discover Markdown files under Backoffice/docs/
- Build a hierarchical navigation (categories/groups/items)
- Render Markdown safely (sanitize HTML, rewrite relative links)
- Support language variants (e.g. add-user.fr.md)
- Filter docs shown in navigation based on the logged-in user's access level
- Hide selected `user-guides/common/*` pages from non-admins (nav + direct URL), via `USER_GUIDES_COMMON_ADMIN_ONLY_STEMS`

It is used by both:
- Admin docs UI (/admin/docs)
- Non-admin help/docs UI (e.g. /help/docs)
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

import bleach
from bleach.css_sanitizer import CSSSanitizer
import markdown as md
from bs4 import BeautifulSoup
from flask import abort, current_app, session
from flask_babel import _
from markupsafe import Markup


@dataclass(frozen=True)
class DocItem:
    title: str
    rel_path: str  # posix path under docs root, includes ".md" (language-agnostic)
    url: str


@dataclass(frozen=True)
class NavGroup:
    name: str
    display_name: str
    items: List[DocItem]


@dataclass(frozen=True)
class NavCategory:
    name: str
    display_name: str
    groups: List[NavGroup]
    icon: Optional[str] = None


def docs_root() -> Path:
    """
    Resolve docs root path: Backoffice/docs/

    current_app.root_path -> Backoffice/app
    """
    return (Path(current_app.root_path).parent / "docs").resolve()


def _is_within_root(root: Path, candidate: Path) -> bool:
    try:
        candidate.resolve().relative_to(root.resolve())
        return True
    except Exception as e:
        current_app.logger.debug("_is_within_root failed: %s", e)
        return False


def _extract_title_from_markdown(text: str, fallback: str) -> str:
    """Extract the first H1 or H2 title from markdown."""
    for raw in text.splitlines():
        line = raw.strip()
        if line.startswith("#"):
            level = len(line) - len(line.lstrip("#"))
            if level <= 2:
                title = line.lstrip("#").strip()
                if title:
                    return title
    return fallback


def _prettify_stem(stem: str) -> str:
    """Convert filename stem to readable title."""
    # Handle language suffix in filenames like: add-user.es.md
    parts = stem.split(".")
    if len(parts) >= 2 and len(parts[-1]) in (2, 3) and parts[-1].isalpha():
        stem = ".".join(parts[:-1])
    return stem.replace("_", " ").replace("-", " ").strip().title() or "Documentation"


def _get_user_language() -> str:
    """
    Get current UI language from session (canonical session/request language).
    """
    from app.utils.form_localization import get_translation_key
    return get_translation_key()


def _split_rel_lang(rel: str) -> Tuple[str, Optional[str]]:
    """
    Split a docs-relative path into a language-agnostic "base" rel path and optional language code.

    Examples:
      - "user-guides/admin/add-user.md"    -> ("user-guides/admin/add-user.md", None)
      - "user-guides/admin/add-user.fr.md" -> ("user-guides/admin/add-user.md", "fr")
    """
    rel_path = Path(rel)
    name = rel_path.name
    parts = name.split(".")
    # Expect "...<base>.<lang>.md"
    if len(parts) >= 3 and parts[-1].lower() == "md":
        maybe_lang = parts[-2]
        if len(maybe_lang) in (2, 3) and maybe_lang.isalpha():
            base_name = ".".join(parts[:-2]) + ".md"
            base_rel = rel_path.with_name(base_name).as_posix()
            return base_rel, maybe_lang.lower()
    return rel, None


def _pick_variant(paths_by_lang: Dict[Optional[str], Path], lang: str) -> Path:
    """
    Pick the best variant for the current language.

    Preference:
      1) exact language variant (e.g. "fr")
      2) default (no language suffix)
      3) any available variant (stable by sorted lang key)
    """
    if lang in paths_by_lang:
        return paths_by_lang[lang]
    if None in paths_by_lang:
        return paths_by_lang[None]
    return paths_by_lang[sorted(paths_by_lang.keys(), key=lambda x: (x is None, str(x)))[0]]


def get_category_icon(category_name: str) -> str:
    """Return icon class for category."""
    icons = {
        "getting-started": "fas fa-rocket",
        "user-guides": "fas fa-book-open",
        "common": "fas fa-users",
        "focal-point": "fas fa-user-check",
        "admin": "fas fa-user-shield",
        "workflows": "fas fa-tasks",
        "api": "fas fa-code",
        "features": "fas fa-star",
        "setup": "fas fa-cog",
        "development": "fas fa-code-branch",
        "components": "fas fa-puzzle-piece",
        "translation": "fas fa-language",
        "notifications": "fas fa-bell",
        "plugins": "fas fa-plug",
        "integrations": "fas fa-link",
        "indicators": "fas fa-chart-bar",
        "data-migration": "fas fa-database",
        "archive": "fas fa-archive",
    }
    return icons.get(category_name.lower(), "fas fa-folder")


def get_category_display_name(category_name: str) -> str:
    """Get localized display name for documentation category."""
    display_names = {
        "getting-started": _("Getting Started"),
        "user-guides": _("User Guides"),
        "workflows": _("Workflows"),
        "api": _("API"),
        "features": _("Features"),
        "setup": _("Setup"),
        "development": _("Development"),
        "components": _("Components"),
        "translation": _("Translation"),
        "notifications": _("Notifications"),
        "plugins": _("Plugins"),
        "integrations": _("Integrations"),
        "indicators": _("Indicators"),
        "data-migration": _("Data Migration"),
        "archive": _("Archive"),
    }
    return display_names.get(category_name.lower(), category_name.replace("-", " ").replace("_", " ").title())


def _get_admin_subgroup(filename: str) -> Tuple[str, int]:
    """
    Map admin documentation filename to a logical subgroup and sort order.

    Returns:
        Tuple of (subgroup_name, sort_order) where sort_order determines
        the display order of groups within the admin category.
    """
    # Normalize filename (remove language suffix and extension)
    base_name = Path(filename).stem
    if "." in base_name:
        parts = base_name.split(".")
        if len(parts) >= 2 and len(parts[-1]) in (2, 3) and parts[-1].isalpha():
            base_name = ".".join(parts[:-1])

    base_name_lower = base_name.lower()

    # Define subgroups with their sort order and matching patterns
    subgroups = {
        "user-management": {
            "order": 1,
            "patterns": ["add-user", "manage-users", "user-roles", "role-recipes", "troubleshooting-access"],
        },
        "template-management": {
            "order": 2,
            "patterns": ["create-template", "edit-template", "form-builder-advanced"],
        },
        "assignment-management": {
            "order": 3,
            "patterns": ["create-assignment", "manage-assignments", "assignment-lifecycle",
                        "run-a-reporting-cycle", "review-approve-submissions", "public-url-submissions"],
        },
        "data-export": {
            "order": 4,
            "patterns": ["export-download-data", "exports-how-to-interpret", "supporting-documents"],
        },
        "tools-settings": {
            "order": 5,
            "patterns": ["indicator-bank", "notifications-and-communications", "ai-document-library-and-embeddings"],
        },
        "troubleshooting": {
            "order": 6,
            "patterns": ["troubleshooting-templates-and-assignments"],
        },
    }

    # Find matching subgroup (check exact match first, then substring match)
    # This ensures "troubleshooting-access" matches "troubleshooting-access"
    # before it could match "troubleshooting"
    for subgroup_name, config in subgroups.items():
        for pattern in config["patterns"]:
            # Exact match takes priority
            if base_name_lower == pattern:
                return (subgroup_name, config["order"])

    # If no exact match, try substring match (for flexibility)
    for subgroup_name, config in subgroups.items():
        for pattern in config["patterns"]:
            if pattern in base_name_lower:
                return (subgroup_name, config["order"])

    # Default: put in "other" group at the end
    return ("other", 99)


def _get_admin_subgroup_display_name(subgroup_name: str) -> str:
    """Get human-readable display name for admin subgroup."""
    display_names = {
        "user-management": _("User Management"),
        "template-management": _("Template Management"),
        "assignment-management": _("Assignment Management"),
        "data-export": _("Data & Export"),
        "tools-settings": _("Tools & Settings"),
        "troubleshooting": _("Troubleshooting"),
        "other": _("Other"),
    }
    return display_names.get(subgroup_name, subgroup_name.replace("-", " ").title())


# Language-agnostic stems (Path(...).stem of base *.md paths) under user-guides/common/
# that should not appear in the docs UI for focal points and other non-admin users.
# Extend this set as needed (e.g. internal policy or architecture detail).
USER_GUIDES_COMMON_ADMIN_ONLY_STEMS: frozenset[str] = frozenset(
    {
        "data-governance",
    }
)


def _user_is_admin_or_system_manager(user) -> bool:
    if not user or not getattr(user, "is_authenticated", False):
        return False
    try:
        from app.services.authorization_service import AuthorizationService
    except Exception as e:
        current_app.logger.debug("AuthorizationService import failed: %s", e)
        return False
    try:
        return bool(
            AuthorizationService.is_system_manager(user) or AuthorizationService.is_admin(user)
        )
    except Exception as e:
        current_app.logger.debug("_user_is_admin_or_system_manager failed: %s", e)
        return False


def user_guides_common_doc_requires_admin(base_rel: str) -> bool:
    """True if base_rel (language-agnostic, ends with .md) is a restricted common guide."""
    parts = Path(base_rel).parts
    if len(parts) < 3:
        return False
    if parts[0] != "user-guides" or parts[1] != "common":
        return False
    return Path(base_rel).stem in USER_GUIDES_COMMON_ADMIN_ONLY_STEMS


# Landing page for users who must not see docs/README.md (full internal index).
DOCS_NON_ADMIN_LANDING_REL = "user-guides/common/start-here.md"


def _is_root_readme_request(raw: str) -> bool:
    """True if raw points at the repo-root README (not e.g. user-guides/README)."""
    s = (raw or "").strip().lstrip("/").replace("\\", "/")
    if not s:
        return False
    p = Path(s)
    if len(p.parts) != 1:
        return False
    return p.stem.lower() == "readme"


def ensure_doc_page_access(
    user,
    base_rel: str,
    *,
    visible_top_level_dirs: Optional[set] = None,
) -> None:
    """
    Abort with 403 if the resolved doc (base_rel) must not be shown to this user.

    Used by admin docs and /help/docs after resolve_doc_path(...).
    """
    parts = Path(base_rel).parts

    if visible_top_level_dirs and parts:
        top = parts[0]
        if top not in visible_top_level_dirs:
            if (
                len(parts) == 1
                and top.lower() == "readme.md"
                and _user_is_admin_or_system_manager(user)
            ):
                pass
            else:
                abort(403)

    if len(parts) >= 3 and parts[0] == "user-guides":
        sub = parts[1]
        allowed_ug = _allowed_user_guides_subdirs_for_user(user)
        if sub not in allowed_ug:
            abort(403)

    if (
        len(parts) == 2
        and parts[0] == "user-guides"
        and parts[1].lower() == "readme.md"
        and not _user_is_admin_or_system_manager(user)
    ):
        abort(403)

    if user_guides_common_doc_requires_admin(base_rel) and not _user_is_admin_or_system_manager(user):
        abort(403)


def ensure_docs_asset_access(
    user,
    rel_asset: str,
    *,
    visible_top_level_dirs: set,
) -> None:
    """Abort 403 when serving /docs/assets/... if path is outside allowed doc areas for this user."""
    parts = Path((rel_asset or "").strip().lstrip("/").replace("\\", "/")).parts
    if not parts:
        abort(403)
    top = parts[0]
    if top not in visible_top_level_dirs:
        abort(403)
    if len(parts) >= 2 and parts[0] == "user-guides":
        sub = parts[1]
        if sub in ("README.md", "readme.md"):
            abort(403)
        allowed_ug = _allowed_user_guides_subdirs_for_user(user)
        if sub not in allowed_ug:
            abort(403)


def list_markdown_files(root: Path, subdir: Optional[Path] = None) -> List[Path]:
    """List all markdown files in directory, excluding hidden/internal files."""
    base = subdir if subdir else root
    files: List[Path] = []
    for p in base.rglob("*.md"):
        if not p.is_file():
            continue
        rel = p.relative_to(root).as_posix()
        # Skip any files under internal/hidden directories (e.g. docs/_internal/...).
        if any(part.startswith("_") for part in Path(rel).parts):
            continue
        # Hide helper docs from nav; still accessible if directly linked.
        if Path(rel).name.startswith("_"):
            continue
        # Skip archive folder by default (can be enabled later)
        if "archive" in rel.lower() and "archive" not in str(subdir or ""):
            continue
        files.append(p)
    return sorted(files, key=lambda x: x.relative_to(root).as_posix().lower())


def _allowed_user_guides_subdirs_for_user(user) -> set:
    """
    Return allowed subdirectories under docs/user-guides/ for a given user.

    Rules:
    - system_manager: common + focal-point + admin
    - admin: common + admin
    - focal point (assignment_editor_submitter): common + focal-point
    - other logged-in users: common
    """
    try:
        from app.services.authorization_service import AuthorizationService
    except Exception as e:
        current_app.logger.debug("AuthorizationService import failed: %s", e)
        AuthorizationService = None  # type: ignore

    allowed = {"common"}
    try:
        if not user or not getattr(user, "is_authenticated", False):
            return allowed
        if AuthorizationService and AuthorizationService.is_system_manager(user):
            return {"common", "focal-point", "admin"}
        if AuthorizationService and AuthorizationService.is_admin(user):
            return {"common", "admin"}
        if AuthorizationService and AuthorizationService.has_role(user, "assignment_editor_submitter"):
            return {"common", "focal-point"}
    except Exception as e:
        current_app.logger.debug("_get_allowed_doc_categories failed: %s", e)
        return allowed
    return allowed


def _should_merge_user_guides_common_focal_nav(allowed_groups: set) -> bool:
    """Focal-point users see common + focal-point; show one combined list instead of two nav sections."""
    return allowed_groups == {"common", "focal-point"}


def build_hierarchical_nav(
    *,
    root: Path,
    doc_url_builder: Callable[[str], str],
    visible_top_level_dirs: Optional[set] = None,
    user=None,
) -> List[NavCategory]:
    """
    Build navigation structure from docs directory.

    - Top-level folders become categories.
    - Immediate subfolders become groups (to reflect the on-disk structure in the nav pane).
    - Language variants (*.fr.md, *.ar.md, ...) are de-duplicated and the best variant is chosen
      based on the current UI language.
    - For user-guides, groups can be filtered based on user access.
    - For focal-point users (common + focal-point only), common and focal-point guides are merged into one category.
    """
    lang = _get_user_language()
    allowed_user_guide_groups = _allowed_user_guides_subdirs_for_user(user)

    visible_top_level_dirs = visible_top_level_dirs or set()

    # First pass: de-duplicate language variants by grouping them under a base rel path.
    variants: Dict[str, Dict[Optional[str], Path]] = {}
    for p in list_markdown_files(root):
        rel = p.relative_to(root).as_posix()
        base_rel, rel_lang = _split_rel_lang(rel)
        variants.setdefault(base_rel, {})[rel_lang] = p

    # Second pass: build nav items from chosen variants.
    root_items: List[DocItem] = []
    category_groups: Dict[str, Dict[str, List[DocItem]]] = {}

    for base_rel, paths_by_lang in variants.items():
        rel_path = Path(base_rel)

        # Restrict what appears in the docs nav.
        if visible_top_level_dirs and len(rel_path.parts) > 1 and rel_path.parts[0] not in visible_top_level_dirs:
            continue

        # Getting started: allow multiple pages (task-first onboarding).
        # (Previously restricted to README.md only.)

        # Role-based filtering for user guides
        if rel_path.parts and rel_path.parts[0] == "user-guides":
            # Allow only section README at root, and role-based subdirectories.
            if len(rel_path.parts) == 2 and rel_path.name.lower() != "readme.md":
                continue
            if len(rel_path.parts) >= 3 and rel_path.parts[1] not in allowed_user_guide_groups:
                continue

        if user_guides_common_doc_requires_admin(base_rel) and not _user_is_admin_or_system_manager(user):
            continue

        chosen_path = _pick_variant(paths_by_lang, lang=lang)
        try:
            text = chosen_path.read_text(encoding="utf-8", errors="replace")
        except Exception as e:
            current_app.logger.debug("read_text failed: %s", e)
            text = ""

        fallback_title = _prettify_stem(chosen_path.stem)
        title = _extract_title_from_markdown(text, fallback_title)

        item = DocItem(
            title=title,
            rel_path=base_rel,
            url=doc_url_builder(base_rel),
        )

        if len(rel_path.parts) == 1:
            root_items.append(item)
            continue

        category = rel_path.parts[0]
        # Group by immediate subfolder to reflect folder structure in nav
        group = rel_path.parts[1] if len(rel_path.parts) >= 3 else "_root"
        category_groups.setdefault(category, {}).setdefault(group, []).append(item)

    # Sort items within each group
    for cat_name in category_groups:
        for group_name in category_groups[cat_name]:
            category_groups[cat_name][group_name].sort(
                key=lambda x: (x.rel_path.count("/"), x.rel_path.lower())
            )

    nav_categories: List[NavCategory] = []

    # Skip root items - no Overview category

    # Helper functions for group display and sorting
    def _group_display(cat: str, group: str) -> str:
        if group == "_root":
            return _("Overview")
        if cat == "user-guides":
            mapping = {
                "admin": _("Admin"),
                "focal-point": _("Focal Point"),
                "common": _("Common"),
            }
            if group in mapping:
                return mapping[group]
        return group.replace("-", " ").replace("_", " ").title()

    def _group_sort_key(cat: str, group: str) -> Tuple[int, str]:
        if group == "_root":
            return (0, "")
        if cat == "user-guides":
            order = {"common": 1, "focal-point": 2, "admin": 3}
            return (order.get(group, 9), group.lower())
        return (1, group.lower())

    # Process categories
    for cat_name in sorted(category_groups.keys()):
        # Special handling for user-guides: promote groups to top-level categories
        if cat_name == "user-guides":
            if _should_merge_user_guides_common_focal_nav(allowed_user_guide_groups):
                merged_items: List[DocItem] = []
                for g in ("common", "focal-point"):
                    merged_items.extend(category_groups[cat_name].get(g, []))
                merged_items.sort(key=lambda x: (x.title.lower(), x.rel_path.lower()))
                if merged_items:
                    nav_categories.append(
                        NavCategory(
                            name="user-guides",
                            display_name=_("User Guides"),
                            groups=[
                                NavGroup(
                                    name="all-guides",
                                    display_name=_("User Guides"),
                                    items=merged_items,
                                )
                            ],
                            icon=get_category_icon("user-guides"),
                        )
                    )
                continue

            for group_name in sorted(
                category_groups[cat_name].keys(),
                key=lambda g: _group_sort_key(cat_name, g),
            ):
                # Skip _root group (user-guides/README.md)
                if group_name == "_root":
                    continue

                # Special handling for admin: create subgroups
                if group_name == "admin":
                    # Group admin items by logical subgroups
                    admin_subgroups: Dict[Tuple[str, int], List[DocItem]] = {}
                    for item in category_groups[cat_name][group_name]:
                        # Extract just the filename from the rel_path (e.g., "user-guides/admin/add-user.md" -> "add-user.md")
                        filename = Path(item.rel_path).name
                        subgroup_name, sort_order = _get_admin_subgroup(filename)
                        key = (subgroup_name, sort_order)
                        admin_subgroups.setdefault(key, []).append(item)

                    # Sort items within each subgroup alphabetically
                    for key in admin_subgroups:
                        admin_subgroups[key].sort(
                            key=lambda x: x.title.lower()
                        )

                    # Create NavGroups for each subgroup, sorted by order
                    admin_groups: List[NavGroup] = []
                    for (subgroup_name, sort_order) in sorted(
                        admin_subgroups.keys(),
                        key=lambda x: (x[1], x[0])  # Sort by order, then by name
                    ):
                        admin_groups.append(
                            NavGroup(
                                name=subgroup_name,
                                display_name=_get_admin_subgroup_display_name(subgroup_name),
                                items=admin_subgroups[(subgroup_name, sort_order)],
                            )
                        )

                    # Create category with multiple groups
                    nav_categories.append(
                        NavCategory(
                            name=group_name,
                            display_name=_group_display(cat_name, group_name),
                            groups=admin_groups,
                            icon=get_category_icon(group_name),
                        )
                    )
                else:
                    # Create a category directly from the group (focal-point, common)
                    nav_categories.append(
                        NavCategory(
                            name=group_name,
                            display_name=_group_display(cat_name, group_name),
                            groups=[
                                NavGroup(
                                    name=group_name,
                                    display_name=_group_display(cat_name, group_name),
                                    items=category_groups[cat_name][group_name],
                                )
                            ],
                            icon=get_category_icon(group_name),
                        )
                    )
        else:
            # For other categories, keep the original structure
            groups: List[NavGroup] = []
            for group_name in sorted(
                category_groups[cat_name].keys(),
                key=lambda g: _group_sort_key(cat_name, g),
            ):
                groups.append(
                    NavGroup(
                        name=group_name,
                        display_name=_group_display(cat_name, group_name),
                        items=category_groups[cat_name][group_name],
                    )
                )

            nav_categories.append(
                NavCategory(
                    name=cat_name,
                    display_name=get_category_display_name(cat_name),
                    groups=groups,
                    icon=get_category_icon(cat_name),
                )
            )

    return nav_categories


def resolve_doc_path(root: Path, doc_path: str, user=None) -> Tuple[Path, str]:
    """
    Resolve a requested doc path safely under root.

    Accepts:
      - "README.md"
      - "api/README.md"
      - "api/README" (appends .md)

    When doc_path is empty, non-admins land on a user guide (not docs/README.md, which lists internal areas).
    """
    raw = (doc_path or "").strip().lstrip("/").replace("\\", "/")
    if not raw:
        if _user_is_admin_or_system_manager(user):
            candidates = ("README.md",)
        else:
            candidates = (
                DOCS_NON_ADMIN_LANDING_REL,
                "getting-started/README.md",
            )
        chosen: Optional[str] = None
        for candidate in candidates:
            p = (root / candidate).resolve()
            if _is_within_root(root, p) and p.exists() and p.is_file():
                chosen = candidate
                break
        if not chosen:
            abort(404)
        raw = chosen

    if _is_root_readme_request(raw) and not _user_is_admin_or_system_manager(user):
        raw = DOCS_NON_ADMIN_LANDING_REL

    if not raw.lower().endswith(".md"):
        raw = f"{raw}.md"

    if raw.lower() == "readme.md" and not _user_is_admin_or_system_manager(user):
        raw = DOCS_NON_ADMIN_LANDING_REL

    # Language-aware resolution:
    # If user requests "file.md" and there is a "file.<lang>.md" for the current UI language,
    # serve it while keeping the current_rel stable (language-agnostic).
    lang = _get_user_language()
    base_rel, rel_lang = _split_rel_lang(raw)

    # Only auto-switch when the request doesn't already specify a language suffix.
    if rel_lang is None and lang and lang != "en":
        rel_path = Path(raw)
        variant_name = rel_path.with_name(f"{rel_path.stem}.{lang}{rel_path.suffix}").as_posix()
        variant_path = (root / variant_name).resolve()
        if _is_within_root(root, variant_path) and variant_path.exists() and variant_path.is_file():
            return variant_path, base_rel

    p = (root / raw).resolve()
    if not _is_within_root(root, p) or not p.exists() or not p.is_file():
        abort(404)
    return p, base_rel


def _sanitize_html(html: str) -> str:
    """Sanitize HTML while preserving documentation structure."""
    soup = BeautifulSoup(html, "html.parser")

    # Remove all inline event handler attributes
    event_attrs = [
        "onclick", "onerror", "onload", "onmouseover", "onmouseout",
        "onfocus", "onblur", "onchange", "onsubmit", "onkeydown",
        "onkeypress", "onkeyup", "onmousedown", "onmouseup",
        "onabort", "onbeforeunload", "onhashchange", "onpageshow",
        "onpagehide", "onresize", "onscroll", "onunload",
        "oncontextmenu", "ondblclick", "ondrag", "ondragend",
        "ondragenter", "ondragleave", "ondragover", "ondragstart",
        "ondrop", "onmousemove", "onmousewheel", "onwheel",
        "oncopy", "oncut", "onpaste", "oninput", "oninvalid",
        "onreset", "onsearch", "onselect", "ontoggle",
    ]

    for tag in soup.find_all(True):
        for attr in event_attrs:
            if attr in tag.attrs:
                del tag.attrs[attr]
        # Remove javascript: protocol from href/src/action
        for attr_name in ["href", "src", "action"]:
            if attr_name in tag.attrs:
                attr_value = tag.attrs[attr_name]
                if isinstance(attr_value, str) and attr_value.lower().startswith("javascript:"):
                    del tag.attrs[attr_name]

    html = str(soup)

    allowed_tags = set(bleach.sanitizer.ALLOWED_TAGS).union(
        {
            "p", "pre", "code", "span", "div", "hr", "br",
            "h1", "h2", "h3", "h4", "h5", "h6",
            "blockquote", "ul", "ol", "li", "dl", "dt", "dd",
            "table", "thead", "tbody", "tfoot", "tr", "th", "td",
            "img", "details", "summary",
            "strong", "em", "b", "i", "u", "s", "del", "ins",
            "mark", "sub", "sup", "kbd", "samp", "var",
            "abbr", "cite", "q", "time",
        }
    )
    allowed_attrs = {
        "*": ["class", "id", "style"],
        "a": ["href", "title", "target", "rel", "name"],
        "img": ["src", "alt", "title", "width", "height"],
        "th": ["colspan", "rowspan", "scope"],
        "td": ["colspan", "rowspan"],
        "code": ["class"],
        "pre": ["class"],
    }
    # Configure CSS sanitizer to allow safe CSS properties for documentation
    css_sanitizer = CSSSanitizer(
        allowed_css_properties=[
            "color", "background-color", "background",
            "font-size", "font-weight", "font-family", "font-style",
            "text-align", "text-decoration", "text-transform",
            "margin", "margin-top", "margin-right", "margin-bottom", "margin-left",
            "padding", "padding-top", "padding-right", "padding-bottom", "padding-left",
            "width", "height", "max-width", "max-height", "min-width", "min-height",
            "border", "border-width", "border-style", "border-color", "border-radius",
            "display", "float", "clear",
            "line-height", "letter-spacing", "word-spacing",
            "vertical-align", "white-space",
        ]
    )
    return bleach.clean(
        html,
        tags=list(allowed_tags),
        attributes=allowed_attrs,
        protocols=["http", "https", "mailto"],
        strip=True,
        css_sanitizer=css_sanitizer,
    )


def rewrite_relative_links(
    *,
    root: Path,
    current_rel: str,
    html: str,
    doc_url_builder: Callable[[str], str],
    asset_url_builder: Callable[[str], str],
) -> str:
    """
    Rewrite relative Markdown links so they route through the docs UI.

    - Links to other markdown files become doc_url_builder(...)
    - Relative images become asset_url_builder(...)
    """
    soup = BeautifulSoup(html, "html.parser")
    current_dir = Path(current_rel).parent if current_rel != Path(current_rel).name else Path("")

    def is_external(href: str) -> bool:
        h = (href or "").strip().lower()
        return h.startswith(("http://", "https://", "mailto:", "tel:", "//"))

    # Rewrite <a href="...">
    for a in soup.find_all("a"):
        href = a.get("href")
        if not href:
            continue
        if href.startswith("#") or is_external(href):
            if is_external(href):
                a["target"] = "_blank"
                a["rel"] = "noopener noreferrer"
            continue

        # Handle absolute paths starting with /
        if href.startswith("/"):
            href_clean = href.lstrip("/")
            candidate_md = (root / href_clean).resolve()
            if candidate_md.suffix.lower() != ".md":
                candidate_md = candidate_md.with_suffix(".md")
            if _is_within_root(root, candidate_md) and candidate_md.exists() and candidate_md.is_file():
                rel = candidate_md.relative_to(root).as_posix()
                a["href"] = doc_url_builder(rel)
            continue

        href_path, frag = (href.split("#", 1) + [""])[:2]
        href_path = href_path.strip()
        if not href_path:
            continue

        # Resolve to a markdown doc relative to current file
        candidate = (root / current_dir / href_path).resolve()
        candidate_md = candidate if candidate.suffix.lower() == ".md" else candidate.with_suffix(".md")

        if _is_within_root(root, candidate_md) and candidate_md.exists() and candidate_md.is_file():
            rel = candidate_md.relative_to(root).as_posix()
            new_href = doc_url_builder(rel)
            if frag:
                new_href = f"{new_href}#{frag}"
            a["href"] = new_href

    # Rewrite <img src="...">
    for img in soup.find_all("img"):
        src = img.get("src")
        if not src:
            continue
        s = src.strip()
        if s.startswith("/") or is_external(s) or s.startswith("data:"):
            if s.startswith("/"):
                src_clean = s.lstrip("/")
                asset_candidate = (root / src_clean).resolve()
                if _is_within_root(root, asset_candidate) and asset_candidate.exists() and asset_candidate.is_file():
                    rel_asset = asset_candidate.relative_to(root).as_posix()
                    img["src"] = asset_url_builder(rel_asset)
            continue

        asset_candidate = (root / current_dir / s).resolve()
        if _is_within_root(root, asset_candidate) and asset_candidate.exists() and asset_candidate.is_file():
            rel_asset = asset_candidate.relative_to(root).as_posix()
            img["src"] = asset_url_builder(rel_asset)

    return str(soup)


def render_markdown_file(
    *,
    root: Path,
    file_path: Path,
    current_rel: str,
    doc_url_builder: Callable[[str], str],
    asset_url_builder: Callable[[str], str],
) -> Markup:
    """Render markdown file to HTML with proper extensions, sanitization, and link rewriting."""
    try:
        text = file_path.read_text(encoding="utf-8", errors="replace")
    except Exception as e:
        current_app.logger.debug("read_text failed: %s", e)
        text = ""

    html = md.markdown(
        text,
        extensions=[
            "fenced_code",
            "tables",
            "toc",
            "sane_lists",
            "codehilite",
            "nl2br",
            "attr_list",
            "def_list",
            "footnotes",
        ],
        extension_configs={
            "toc": {"anchorlink": True, "permalink": False},
            "codehilite": {"css_class": "highlight", "use_pygments": False},
        },
        output_format="html5",
    )
    html = _sanitize_html(html)

    # Remove the first H1 element to avoid duplicate titles (page title is shown separately)
    soup = BeautifulSoup(html, "html.parser")
    first_h1 = soup.find("h1")
    if first_h1:
        # Remove the H1 but preserve any content that might follow it
        first_h1.decompose()
    html = str(soup)

    html = rewrite_relative_links(
        root=root,
        current_rel=current_rel,
        html=html,
        doc_url_builder=doc_url_builder,
        asset_url_builder=asset_url_builder,
    )
    return Markup(html)


def extract_page_title(file_path: Path) -> str:
    """Read markdown file and extract a user-visible page title."""
    try:
        text = file_path.read_text(encoding="utf-8", errors="replace")
    except Exception as e:
        current_app.logger.debug("read_text failed: %s", e)
        text = ""
    return _extract_title_from_markdown(text, _prettify_stem(file_path.stem))


def get_workflow_id_for_doc(file_path: Path, root: Path) -> Optional[str]:
    """
    Try to find a matching workflow ID for a documentation file.

    Maps documentation files to workflow IDs based on filename.
    For example: user-guides/admin/add-user.md -> add-user

    Args:
        file_path: Path to the documentation file
        root: Root path of the docs directory

    Returns:
        Workflow ID if found, None otherwise
    """
    try:
        rel_path = file_path.relative_to(root).as_posix()
        rel = Path(rel_path)

        # Skip if it's a README or index file
        if rel.stem.lower() in ("readme", "index"):
            return None

        # Only user-guides may have an associated workflow tour (by convention).
        if rel.parts and rel.parts[0] != "user-guides":
            return None

        # Use the filename stem as the workflow id: add-user.md -> add-user
        workflow_id = rel.stem

        # Only return a workflow id when an *interactive tour* exists for it.
        # Some workflow docs are informational (no "### Step N:" sections), so they
        # should not show a "Take the Tour" button.
        from app.services.workflow_docs_service import WorkflowDocsService

        service = WorkflowDocsService()
        workflow = service.get_workflow_by_id(workflow_id)
        if not workflow:
            return None

        # Steps are only populated when the workflow markdown includes the required
        # fields (Page/Selector/Help) under "### Step N:" headings.
        return workflow_id if getattr(workflow, "steps", None) else None
    except Exception as e:
        current_app.logger.debug("_extract_workflow_id failed: %s", e)
        return None
