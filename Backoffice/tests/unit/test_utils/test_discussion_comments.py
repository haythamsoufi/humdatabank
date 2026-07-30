"""Tests for discussion comment helpers."""

import pytest

from app.utils.discussion_comments import (
    DISCUSSION_SOURCE_UPR_EXCEL,
    discussion_comment_author_label,
    discussion_comment_is_imported,
)

pytestmark = [pytest.mark.unit]


class _CommentStub:
    def __init__(self, *, source=None, user=None):
        self.source = source
        self.created_by_user = user


class _UserStub:
    def __init__(self, name=None, email=None):
        self.name = name
        self.email = email


class TestDiscussionCommentHelpers:
    def test_imported_label(self):
        comment = _CommentStub(source=DISCUSSION_SOURCE_UPR_EXCEL)
        assert discussion_comment_is_imported(comment) is True
        assert discussion_comment_author_label(comment) == "Imported from UPR Excel"

    def test_user_label(self):
        comment = _CommentStub(user=_UserStub(name="Jane Doe", email="j@example.com"))
        assert discussion_comment_author_label(comment) == "Jane Doe"

    def test_user_fallback_email(self):
        comment = _CommentStub(user=_UserStub(email="j@example.com"))
        assert discussion_comment_author_label(comment) == "j@example.com"

    def test_unknown_without_user_or_source(self):
        comment = _CommentStub()
        assert discussion_comment_is_imported(comment) is False
        assert discussion_comment_author_label(comment) == "Unknown user"
