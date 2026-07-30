"""Helpers for submission discussion comments."""

DISCUSSION_SOURCE_UPR_EXCEL = 'upr_excel_import'


def discussion_comment_author_label(comment, *, gettext_fn=None):
    """Human-readable author line for a SubmissionDiscussionComment."""
    source = getattr(comment, 'source', None)
    if source == DISCUSSION_SOURCE_UPR_EXCEL:
        if gettext_fn:
            return gettext_fn('Imported from UPR Excel')
        return 'Imported from UPR Excel'
    user = getattr(comment, 'created_by_user', None)
    if user:
        return user.name or user.email or 'Unknown user'
    if gettext_fn:
        return gettext_fn('Unknown user')
    return 'Unknown user'


def discussion_comment_is_imported(comment) -> bool:
    return getattr(comment, 'source', None) == DISCUSSION_SOURCE_UPR_EXCEL
