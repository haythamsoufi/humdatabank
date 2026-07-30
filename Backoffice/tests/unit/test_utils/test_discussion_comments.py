"""Tests for discussion comment helpers."""

import pytest

from app.utils.discussion_comments import (
    DISCUSSION_SOURCE_UPR_EXCEL,
    discussion_comment_author_label,
    discussion_comment_can_be_managed_by,
    discussion_comment_is_imported,
)

pytestmark = [pytest.mark.unit]


class _CommentStub:
    def __init__(self, *, source=None, user=None):
        self.source = source
        self.created_by_user = user
        self.created_by_user_id = getattr(user, 'id', None)


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

    def test_can_be_managed_by_author(self):
        user = _UserStub(name="Jane Doe", email="j@example.com")
        user.id = 5
        user.is_authenticated = True
        comment = _CommentStub(user=user)
        comment.created_by_user_id = 5
        assert discussion_comment_can_be_managed_by(comment, user) is True

    def test_cannot_manage_imported(self):
        user = _UserStub(name="Jane Doe", email="j@example.com")
        user.id = 5
        user.is_authenticated = True
        comment = _CommentStub(source=DISCUSSION_SOURCE_UPR_EXCEL, user=user)
        comment.created_by_user_id = 5
        assert discussion_comment_can_be_managed_by(comment, user) is False

    def test_cannot_manage_other_users_comment(self):
        user = _UserStub(name="Jane Doe", email="j@example.com")
        user.id = 5
        user.is_authenticated = True
        comment = _CommentStub(user=_UserStub(name="Other"))
        comment.created_by_user_id = 9
        assert discussion_comment_can_be_managed_by(comment, user) is False
