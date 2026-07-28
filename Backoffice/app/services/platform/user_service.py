"""
User Service - Centralized service for user-related database operations.

This service provides a unified interface for user queries, replacing
direct database queries in route handlers.
"""

from typing import Optional, List
from app.models import User
from app import db
from sqlalchemy.exc import SQLAlchemyError
from flask import current_app
from sqlalchemy import literal
from contextlib import suppress


class UserService:
    """Service class for user operations."""

    @staticmethod
    def _handle_db_error(e: Exception, operation: str) -> None:
        """Handle database errors by rolling back the transaction.

        Args:
            e: The exception that occurred
            operation: Description of the operation that failed
        """
        try:
            db.session.rollback()
            current_app.logger.error(f"Database error during {operation}: {e}")
        except Exception as rollback_error:
            current_app.logger.error(f"Failed to rollback transaction: {rollback_error}")
            # If rollback fails, try to close and recreate the session
            with suppress(Exception):
                db.session.close()

    @staticmethod
    def get_by_id(user_id: int) -> Optional[User]:
        """Get a user by ID.

        Args:
            user_id: User ID

        Returns:
            User instance or None if not found
        """
        try:
            return User.query.get(user_id)
        except SQLAlchemyError as e:
            UserService._handle_db_error(e, f"get_by_id({user_id})")
            return None
        except Exception as e:
            current_app.logger.error(f"Unexpected error in get_by_id: {e}")
            return None

    @staticmethod
    def get_by_email(email: str) -> Optional[User]:
        """Get a user by email address.

        Args:
            email: User email address

        Returns:
            User instance or None if not found
        """
        try:
            return User.query.filter_by(email=email.strip().lower()).first()
        except SQLAlchemyError as e:
            UserService._handle_db_error(e, f"get_by_email({email})")
            # Retry once after rollback
            try:
                return User.query.filter_by(email=email.strip().lower()).first()
            except Exception as retry_error:
                current_app.logger.error(f"Retry failed after rollback: {retry_error}")
                return None
        except Exception as e:
            current_app.logger.error(f"Unexpected error in get_by_email: {e}")
            return None

    @staticmethod
    def get_by_ids(user_ids: List[int]):
        """Get users by a list of IDs.

        Args:
            user_ids: List of user IDs

        Returns:
            Query object filtered by IDs
        """
        try:
            if not user_ids:
                return User.query.filter(literal(False))  # Empty query
            return User.query.filter(User.id.in_(user_ids))
        except SQLAlchemyError as e:
            UserService._handle_db_error(e, f"get_by_ids({user_ids})")
            return User.query.filter(literal(False))  # Return empty query on error
        except Exception as e:
            current_app.logger.error(f"Unexpected error in get_by_ids: {e}")
            return User.query.filter(literal(False))

    @staticmethod
    def exists(email: str) -> bool:
        """Check if a user exists with the given email.

        Args:
            email: User email address

        Returns:
            True if user exists, False otherwise
        """
        try:
            return User.query.filter_by(email=email.strip().lower()).first() is not None
        except SQLAlchemyError as e:
            UserService._handle_db_error(e, f"exists({email})")
            return False
        except Exception as e:
            current_app.logger.error(f"Unexpected error in exists: {e}")
            return False

    @staticmethod
    def get_all_active():
        """Get all active users.

        Returns:
            Query object for active users
        """
        try:
            return User.query.filter_by(active=True)
        except SQLAlchemyError as e:
            UserService._handle_db_error(e, "get_all_active")
            return User.query.filter(literal(False))  # Return empty query on error
        except Exception as e:
            current_app.logger.error(f"Unexpected error in get_all_active: {e}")
            return User.query.filter(literal(False))

    @staticmethod
    def get_all():
        """Get all users.

        Returns:
            Query object for all users
        """
        try:
            return User.query
        except SQLAlchemyError as e:
            UserService._handle_db_error(e, "get_all")
            return User.query.filter(literal(False))  # Return empty query on error
        except Exception as e:
            current_app.logger.error(f"Unexpected error in get_all: {e}")
            return User.query.filter(literal(False))
