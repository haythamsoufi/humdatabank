"""
Notification Analytics Service

Provides analytics and statistics about notification delivery, read rates, and user engagement.
"""

from typing import Dict, List, Any, Optional
from datetime import datetime, timedelta
from flask import current_app
from app import db
from app.models import Notification, NotificationType, NotificationPreferences
from sqlalchemy import func, and_, or_, case
from sqlalchemy.orm import Query
import logging
from app.utils.datetime_helpers import utcnow
from app.utils.api_helpers import service_error, GENERIC_ERROR_MESSAGE

logger = logging.getLogger(__name__)


class NotificationAnalytics:
    """Service for notification analytics and statistics"""

    @classmethod
    def get_summary(cls, days: int = 30) -> Dict[str, Any]:
        """
        Get summary statistics for notifications.

        Args:
            days: Number of days to look back

        Returns:
            Dictionary with summary statistics
        """
        try:
            cutoff_date = utcnow() - timedelta(days=days)

            # Total notifications created
            total_created = Notification.query.filter(
                Notification.created_at >= cutoff_date
            ).count()

            # Total unread notifications
            total_unread = Notification.query.filter(
                Notification.created_at >= cutoff_date,
                Notification.is_read == False,
                Notification.is_archived == False
            ).count()

            # Total read notifications
            total_read = Notification.query.filter(
                Notification.created_at >= cutoff_date,
                Notification.is_read == True
            ).count()

            # Total archived notifications
            total_archived = Notification.query.filter(
                Notification.created_at >= cutoff_date,
                Notification.is_archived == True
            ).count()

            # Total expired notifications
            now = utcnow()
            total_expired = Notification.query.filter(
                Notification.expires_at.isnot(None),
                Notification.expires_at < now,
                Notification.created_at >= cutoff_date
            ).count()

            # Read rate
            read_rate = (total_read / total_created * 100) if total_created > 0 else 0

            return {
                'success': True,
                'period_days': days,
                'total_created': total_created,
                'total_unread': total_unread,
                'total_read': total_read,
                'total_archived': total_archived,
                'total_expired': total_expired,
                'read_rate': round(read_rate, 2),
                'unread_rate': round(100 - read_rate, 2) if total_created > 0 else 0
            }
        except Exception as e:
            logger.error(f"Error getting notification summary: {str(e)}", exc_info=True)
            return service_error(GENERIC_ERROR_MESSAGE)

    @classmethod
    def get_delivery_rates(cls, days: int = 30) -> Dict[str, Any]:
        """
        Get delivery rates by notification type.

        Args:
            days: Number of days to look back

        Returns:
            Dictionary with delivery rates by type
        """
        try:
            cutoff_date = utcnow() - timedelta(days=days)

            # Get counts by notification type
            results = db.session.query(
                Notification.notification_type,
                func.count(Notification.id).label('total'),
                func.sum(case((Notification.is_read == True, 1), else_=0)).label('read_count'),
                func.sum(case((Notification.is_archived == True, 1), else_=0)).label('archived_count')
            ).filter(
                Notification.created_at >= cutoff_date
            ).group_by(
                Notification.notification_type
            ).all()

            delivery_rates = []
            for notif_type, total, read_count, archived_count in results:
                read_count = read_count or 0
                archived_count = archived_count or 0
                read_rate = (read_count / total * 100) if total > 0 else 0

                delivery_rates.append({
                    'notification_type': notif_type.value if hasattr(notif_type, 'value') else str(notif_type),
                    'total': total,
                    'read_count': read_count,
                    'archived_count': archived_count,
                    'read_rate': round(read_rate, 2),
                    'unread_count': total - read_count - archived_count
                })

            # Sort by total descending
            delivery_rates.sort(key=lambda x: x['total'], reverse=True)

            return {
                'success': True,
                'period_days': days,
                'delivery_rates': delivery_rates
            }
        except Exception as e:
            logger.error(f"Error getting delivery rates: {str(e)}", exc_info=True)
            return service_error(GENERIC_ERROR_MESSAGE)

    @classmethod
    def get_read_rates(cls, days: int = 30) -> Dict[str, Any]:
        """
        Get read rates by notification type and priority.

        Args:
            days: Number of days to look back

        Returns:
            Dictionary with read rates
        """
        try:
            cutoff_date = utcnow() - timedelta(days=days)

            # Read rates by type
            type_results = db.session.query(
                Notification.notification_type,
                func.count(Notification.id).label('total'),
                func.sum(case((Notification.is_read == True, 1), else_=0)).label('read_count')
            ).filter(
                Notification.created_at >= cutoff_date
            ).group_by(
                Notification.notification_type
            ).all()

            type_rates = []
            for notif_type, total, read_count in type_results:
                read_count = read_count or 0
                read_rate = (read_count / total * 100) if total > 0 else 0

                type_rates.append({
                    'notification_type': notif_type.value if hasattr(notif_type, 'value') else str(notif_type),
                    'total': total,
                    'read_count': read_count,
                    'read_rate': round(read_rate, 2)
                })

            # Read rates by priority
            priority_results = db.session.query(
                Notification.priority,
                func.count(Notification.id).label('total'),
                func.sum(case((Notification.is_read == True, 1), else_=0)).label('read_count')
            ).filter(
                Notification.created_at >= cutoff_date
            ).group_by(
                Notification.priority
            ).all()

            priority_rates = []
            for priority, total, read_count in priority_results:
                read_count = read_count or 0
                read_rate = (read_count / total * 100) if total > 0 else 0

                priority_rates.append({
                    'priority': priority,
                    'total': total,
                    'read_count': read_count,
                    'read_rate': round(read_rate, 2)
                })

            return {
                'success': True,
                'period_days': days,
                'by_type': type_rates,
                'by_priority': priority_rates
            }
        except Exception as e:
            logger.error(f"Error getting read rates: {str(e)}", exc_info=True)
            return service_error(GENERIC_ERROR_MESSAGE)

    @classmethod
    def get_peak_times(cls, days: int = 30) -> Dict[str, Any]:
        """
        Get peak notification times (by hour of day).

        Args:
            days: Number of days to look back

        Returns:
            Dictionary with peak times
        """
        try:
            cutoff_date = utcnow() - timedelta(days=days)

            # Get counts by hour of day
            results = db.session.query(
                func.extract('hour', Notification.created_at).label('hour'),
                func.count(Notification.id).label('count')
            ).filter(
                Notification.created_at >= cutoff_date
            ).group_by(
                func.extract('hour', Notification.created_at)
            ).order_by(
                func.count(Notification.id).desc()
            ).all()

            hourly_counts = {hour: count for hour, count in results}

            # Fill in missing hours with 0
            for hour in range(24):
                if hour not in hourly_counts:
                    hourly_counts[hour] = 0

            # Get top 5 peak hours
            sorted_hours = sorted(hourly_counts.items(), key=lambda x: x[1], reverse=True)
            peak_hours = [{'hour': hour, 'count': count} for hour, count in sorted_hours[:5]]

            return {
                'success': True,
                'period_days': days,
                'hourly_counts': hourly_counts,
                'peak_hours': peak_hours,
                'total_notifications': sum(hourly_counts.values())
            }
        except Exception as e:
            logger.error(f"Error getting peak times: {str(e)}", exc_info=True)
            return service_error(GENERIC_ERROR_MESSAGE)

    @classmethod
    def get_user_engagement(cls, days: int = 30, limit: int = 20) -> Dict[str, Any]:
        """
        Get user engagement statistics (top users by notification activity).

        Args:
            days: Number of days to look back
            limit: Maximum number of users to return

        Returns:
            Dictionary with user engagement stats
        """
        try:
            cutoff_date = utcnow() - timedelta(days=days)

            # Get user engagement stats
            results = db.session.query(
                Notification.user_id,
                func.count(Notification.id).label('total_received'),
                func.sum(case((Notification.is_read == True, 1), else_=0)).label('total_read'),
                func.sum(case((Notification.is_archived == True, 1), else_=0)).label('total_archived')
            ).filter(
                Notification.created_at >= cutoff_date
            ).group_by(
                Notification.user_id
            ).order_by(
                func.count(Notification.id).desc()
            ).limit(limit).all()

            user_stats = []
            for user_id, total_received, total_read, total_archived in results:
                total_read = total_read or 0
                total_archived = total_archived or 0
                read_rate = (total_read / total_received * 100) if total_received > 0 else 0

                user_stats.append({
                    'user_id': user_id,
                    'total_received': total_received,
                    'total_read': total_read,
                    'total_archived': total_archived,
                    'read_rate': round(read_rate, 2)
                })

            return {
                'success': True,
                'period_days': days,
                'user_engagement': user_stats
            }
        except Exception as e:
            logger.error(f"Error getting user engagement: {str(e)}", exc_info=True)
            return service_error(GENERIC_ERROR_MESSAGE)
