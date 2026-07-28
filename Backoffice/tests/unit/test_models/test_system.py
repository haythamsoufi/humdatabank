"""
Unit tests for system.py models to achieve 100% code coverage.

Covers: CountryAccessRequest, AdminActionLog, SecurityEvent, Notification,
        NotificationPreferences, NotificationCampaign, EmailDeliveryLog,
        UserDevice, EntityActivityLog, SystemSettings
"""
import pytest
from unittest.mock import patch, MagicMock
from datetime import datetime

from app.models.system import (
    CountryAccessRequest,
    AdminActionLog,
    SecurityEvent,
    Notification,
    NotificationPreferences,
    NotificationCampaign,
    EmailDeliveryLog,
    UserDevice,
    EntityActivityLog,
    SystemSettings,
)
from app.models.enums import (
    CountryAccessRequestStatusValue,
    NotificationType,
    NotificationCampaignStatusValue,
    EmailDeliveryStatusValue,
)
from tests.factories import create_test_user, create_test_country


@pytest.mark.unit
class TestCountryAccessRequest:
    """Tests for CountryAccessRequest model."""

    def test_create_request(self, db_session, app):
        """Test creating a country access request."""
        with app.app_context():
            user = create_test_user(db_session)
            country = create_test_country(db_session)
            req = CountryAccessRequest(
                user_id=user.id,
                country_id=country.id,
                request_message='Please grant access',
            )
            db_session.add(req)
            db_session.commit()
            db_session.refresh(req)
            assert req.id is not None
            assert req.status == CountryAccessRequestStatusValue.pending.value

    def test_repr(self, db_session, app):
        """Test __repr__."""
        with app.app_context():
            user = create_test_user(db_session)
            country = create_test_country(db_session)
            req = CountryAccessRequest(user_id=user.id, country_id=country.id)
            db_session.add(req)
            db_session.commit()
            result = repr(req)
            assert 'CountryAccessRequest' in result
            assert str(user.id) in result


@pytest.mark.unit
class TestAdminActionLog:
    """Tests for AdminActionLog model."""

    def test_create_log(self, db_session, app):
        """Test creating an admin action log."""
        with app.app_context():
            user = create_test_user(db_session)
            log = AdminActionLog(
                admin_user_id=user.id,
                action_type='user_create',
                action_description='Created a user',
                ip_address='127.0.0.1',
            )
            db_session.add(log)
            db_session.commit()
            db_session.refresh(log)
            assert log.id is not None
            assert log.risk_level == 'low'
            assert log.requires_review is False

    def test_repr(self, db_session, app):
        """Test __repr__."""
        with app.app_context():
            user = create_test_user(db_session)
            log = AdminActionLog(
                admin_user_id=user.id,
                action_type='user_delete',
                action_description='Deleted a user',
                ip_address='127.0.0.1',
            )
            db_session.add(log)
            db_session.commit()
            db_session.refresh(log)
            result = repr(log)
            assert 'user_delete' in result

    def test_with_optional_fields(self, db_session, app):
        """Test log with all optional fields."""
        with app.app_context():
            user = create_test_user(db_session)
            log = AdminActionLog(
                admin_user_id=user.id,
                action_type='form_assign',
                action_description='Assigned form to country',
                ip_address='192.168.1.1',
                target_type='country',
                target_id=1,
                target_description='Kenya',
                user_agent='Mozilla/5.0',
                endpoint='/admin/assign',
                old_values={'status': 'pending'},
                new_values={'status': 'active'},
                risk_level='high',
                requires_review=True,
            )
            db_session.add(log)
            db_session.commit()
            db_session.refresh(log)
            assert log.risk_level == 'high'
            assert log.requires_review is True


@pytest.mark.unit
class TestSecurityEvent:
    """Tests for SecurityEvent model."""

    def test_create_event(self, db_session, app):
        """Test creating a security event."""
        with app.app_context():
            event = SecurityEvent(
                event_type='multiple_failed_logins',
                severity='medium',
                description='5 failed login attempts',
                ip_address='192.168.1.1',
            )
            db_session.add(event)
            db_session.commit()
            db_session.refresh(event)
            assert event.id is not None
            assert event.is_resolved is False

    def test_repr(self, db_session, app):
        """Test __repr__."""
        with app.app_context():
            event = SecurityEvent(
                event_type='suspicious_activity',
                severity='high',
                description='Suspicious access pattern',
                ip_address='10.0.0.1',
            )
            db_session.add(event)
            db_session.commit()
            result = repr(event)
            assert 'suspicious_activity' in result

    def test_with_user(self, db_session, app):
        """Test security event linked to user."""
        with app.app_context():
            user = create_test_user(db_session)
            event = SecurityEvent(
                user_id=user.id,
                event_type='brute_force',
                severity='critical',
                description='Brute force attack',
                ip_address='10.0.0.1',
                context_data={'attempts': 100},
            )
            db_session.add(event)
            db_session.commit()
            db_session.refresh(event)
            assert event.user_id == user.id


@pytest.mark.unit
class TestNotification:
    """Tests for Notification model."""

    def _create_notification(self, db_session, user, **kwargs):
        import uuid
        defaults = {
            'user_id': user.id,
            'notification_type': NotificationType.assignment_created,
            'title': 'New Assignment',
            'message': 'A new assignment has been created',
            'notification_hash': uuid.uuid4().hex,
        }
        defaults.update(kwargs)
        n = Notification(**defaults)
        db_session.add(n)
        db_session.commit()
        db_session.refresh(n)
        return n

    def test_create_notification(self, db_session, app):
        """Test creating a notification."""
        with app.app_context():
            user = create_test_user(db_session)
            n = self._create_notification(db_session, user)
            assert n.id is not None
            assert n.is_read is False
            assert n.is_archived is False

    def test_repr(self, db_session, app):
        """Test __repr__."""
        with app.app_context():
            user = create_test_user(db_session)
            n = self._create_notification(db_session, user, title='Test Notification')
            result = repr(n)
            assert 'Test Notification' in result

    def test_with_entity_scope(self, db_session, app):
        """Test notification with entity_type/entity_id."""
        with app.app_context():
            user = create_test_user(db_session)
            country = create_test_country(db_session)
            n = self._create_notification(
                db_session, user,
                entity_type='country',
                entity_id=country.id,
            )
            assert n.entity_type == 'country'
            assert n.entity_id == country.id

    def test_with_all_optional_fields(self, db_session, app):
        """Test notification with all optional fields."""
        with app.app_context():
            user = create_test_user(db_session)
            import uuid
            n = self._create_notification(
                db_session, user,
                priority='high',
                icon='bell',
                related_object_type='form',
                related_object_id=1,
                related_url='/forms/1',
                group_id='group123',
                category='assignment',
                tags=['urgent'],
                action_buttons=[{'label': 'View', 'action': 'view', 'endpoint': '/view'}],
                title_key='notification.title',
                title_params={'name': 'Test'},
                message_key='notification.msg',
                message_params={'count': 1},
                notification_hash=uuid.uuid4().hex,
            )
            assert n.priority == 'high'
            assert n.category == 'assignment'


@pytest.mark.unit
class TestNotificationPreferences:
    """Tests for NotificationPreferences model."""

    def test_create_preferences(self, db_session, app):
        """Test creating notification preferences."""
        with app.app_context():
            user = create_test_user(db_session)
            prefs = NotificationPreferences(user_id=user.id)
            db_session.add(prefs)
            db_session.commit()
            db_session.refresh(prefs)
            assert prefs.id is not None
            assert prefs.email_notifications is True
            assert prefs.push_notifications is True

    def test_repr(self, db_session, app):
        """Test __repr__."""
        with app.app_context():
            user = create_test_user(db_session)
            prefs = NotificationPreferences(user_id=user.id)
            db_session.add(prefs)
            db_session.commit()
            result = repr(prefs)
            assert str(user.id) in result


@pytest.mark.unit
class TestNotificationCampaign:
    """Tests for NotificationCampaign model."""

    def test_create_campaign(self, db_session, app):
        """Test creating a notification campaign."""
        with app.app_context():
            user = create_test_user(db_session)
            campaign = NotificationCampaign(
                name='Test Campaign',
                title='Campaign Title',
                message='Campaign message body',
                created_by=user.id,
            )
            db_session.add(campaign)
            db_session.commit()
            db_session.refresh(campaign)
            assert campaign.id is not None
            assert campaign.status == NotificationCampaignStatusValue.draft.value

    def test_repr(self, db_session, app):
        """Test __repr__."""
        with app.app_context():
            user = create_test_user(db_session)
            campaign = NotificationCampaign(
                name='My Campaign',
                title='Title',
                message='Body',
                created_by=user.id,
            )
            db_session.add(campaign)
            db_session.commit()
            result = repr(campaign)
            assert 'My Campaign' in result

    def test_with_optional_fields(self, db_session, app):
        """Test campaign with all optional fields."""
        with app.app_context():
            user = create_test_user(db_session)
            campaign = NotificationCampaign(
                name='Entity Campaign',
                title='Entity Title',
                message='Entity message',
                created_by=user.id,
                description='Campaign description',
                priority='high',
                category='assignment',
                tags=['urgent', 'deadline'],
                send_email=True,
                send_push=False,
                override_preferences=True,
                redirect_type='app',
                redirect_url='/assignments',
                user_selection_type='filter',
                user_filters={'role': 'focal_point'},
                entity_selection=[{'entity_type': 'country', 'entity_id': 1}],
                email_distribution_rules={'organization_in': 'to'},
                attachment_config={'static_attachments': []},
            )
            db_session.add(campaign)
            db_session.commit()
            db_session.refresh(campaign)
            assert campaign.priority == 'high'
            assert campaign.send_push is False


@pytest.mark.unit
class TestEmailDeliveryLog:
    """Tests for EmailDeliveryLog model."""

    def test_create_log(self, db_session, app):
        """Test creating an email delivery log."""
        with app.app_context():
            user = create_test_user(db_session)
            log = EmailDeliveryLog(
                user_id=user.id,
                email_address=user.email,
                subject='Test Email',
            )
            db_session.add(log)
            db_session.commit()
            db_session.refresh(log)
            assert log.id is not None
            assert log.status == EmailDeliveryStatusValue.pending.value
            assert log.retry_count == 0

    def test_repr(self, db_session, app):
        """Test __repr__."""
        with app.app_context():
            user = create_test_user(db_session)
            log = EmailDeliveryLog(
                user_id=user.id,
                email_address='test@example.com',
            )
            db_session.add(log)
            db_session.commit()
            result = repr(log)
            assert 'test@example.com' in result

    def test_with_notification(self, db_session, app):
        """Test delivery log linked to notification."""
        with app.app_context():
            user = create_test_user(db_session)
            import uuid
            n = Notification(
                user_id=user.id,
                notification_type=NotificationType.admin_message,
                title='Test',
                message='Test msg',
                notification_hash=uuid.uuid4().hex,
            )
            db_session.add(n)
            db_session.flush()
            log = EmailDeliveryLog(
                notification_id=n.id,
                user_id=user.id,
                email_address=user.email,
            )
            db_session.add(log)
            db_session.commit()
            assert log.notification_id == n.id


@pytest.mark.unit
class TestUserDevice:
    """Tests for UserDevice model."""

    def test_create_device(self, db_session, app):
        """Test creating a user device."""
        with app.app_context():
            user = create_test_user(db_session)
            device = UserDevice(
                user_id=user.id,
                device_token='token123abc',
                platform='ios',
            )
            db_session.add(device)
            db_session.commit()
            db_session.refresh(device)
            assert device.id is not None
            assert device.platform == 'ios'
            assert device.consecutive_failures == 0

    def test_repr(self, db_session, app):
        """Test __repr__."""
        with app.app_context():
            user = create_test_user(db_session)
            device = UserDevice(
                user_id=user.id,
                device_token='token456def',
                platform='android',
            )
            db_session.add(device)
            db_session.commit()
            result = repr(device)
            assert 'android' in result

    def test_with_optional_fields(self, db_session, app):
        """Test device with all optional fields."""
        with app.app_context():
            user = create_test_user(db_session)
            device = UserDevice(
                user_id=user.id,
                device_token='token789ghi',
                platform='ios',
                app_version='1.2.3',
                device_model='iPhone 14 Pro',
                device_name='My iPhone',
                os_version='iOS 17.0',
                ip_address='192.168.1.100',
                timezone='America/New_York',
            )
            db_session.add(device)
            db_session.commit()
            db_session.refresh(device)
            assert device.device_model == 'iPhone 14 Pro'
            assert device.timezone == 'America/New_York'


@pytest.mark.unit
class TestEntityActivityLog:
    """Tests for EntityActivityLog model."""

    def test_create_log(self, db_session, app):
        """Test creating an entity activity log."""
        with app.app_context():
            user = create_test_user(db_session)
            log = EntityActivityLog(
                user_id=user.id,
                entity_type='country',
                entity_id=1,
                activity_type='form_submitted',
                activity_description='Submitted form',
                summary_key='activity.form_submitted',
                activity_category='assignment',
            )
            db_session.add(log)
            db_session.commit()
            db_session.refresh(log)
            assert log.id is not None
            assert log.activity_category == 'assignment'

    def test_repr(self, db_session, app):
        """Test __repr__."""
        with app.app_context():
            user = create_test_user(db_session)
            log = EntityActivityLog(
                user_id=user.id,
                entity_type='country',
                entity_id=1,
                activity_type='approved',
                activity_description='Approved data',
                summary_key='activity.approved',
            )
            db_session.add(log)
            db_session.commit()
            result = repr(log)
            assert 'approved' in result

    def test_entity_property_calls_service(self, db_session, app):
        """Test entity property calls EntityService."""
        with app.app_context():
            user = create_test_user(db_session)
            country = create_test_country(db_session)
            log = EntityActivityLog(
                user_id=user.id,
                entity_type='country',
                entity_id=country.id,
                activity_type='test',
                activity_description='Test activity',
                summary_key='test.key',
            )
            db_session.add(log)
            db_session.commit()
            with patch('app.services.organization.entity_service.EntityService.get_entity', return_value=country):
                entity = log.entity
                assert entity is not None

    def test_with_optional_fields(self, db_session, app):
        """Test log with all optional fields."""
        with app.app_context():
            user = create_test_user(db_session)
            country = create_test_country(db_session)
            log = EntityActivityLog(
                user_id=user.id,
                entity_type='country',
                entity_id=country.id,
                country_id=country.id,
                activity_type='form_submitted',
                activity_description='Submitted form',
                summary_key='activity.form_submitted',
                summary_params={'form_name': 'Test Form'},
                related_object_type='form',
                related_object_id=1,
                assignment_id=1,
                related_url='/forms/1',
                icon='check',
                activity_category='assignment',
            )
            db_session.add(log)
            db_session.commit()
            db_session.refresh(log)
            assert log.country_id == country.id
            assert log.summary_params == {'form_name': 'Test Form'}


@pytest.mark.unit
class TestSystemSettings:
    """Tests for SystemSettings model."""

    def test_create_setting(self, db_session, app):
        """Test creating a system setting."""
        with app.app_context():
            setting = SystemSettings(
                setting_key='test.setting',
                setting_value={'enabled': True},
                description='Test setting',
            )
            db_session.add(setting)
            db_session.commit()
            db_session.refresh(setting)
            assert setting.id is not None
            assert setting.setting_value == {'enabled': True}

    def test_repr(self, db_session, app):
        """Test __repr__."""
        with app.app_context():
            setting = SystemSettings(
                setting_key='my.key',
                setting_value='my_value',
            )
            db_session.add(setting)
            db_session.commit()
            result = repr(setting)
            assert 'my.key' in result

    def test_get_value_existing(self, db_session, app):
        """Test get_value returns value for existing key."""
        with app.app_context():
            SystemSettings(
                setting_key='get.test',
                setting_value={'x': 42},
            )
            db_session.add(SystemSettings(setting_key='get.test', setting_value={'x': 42}))
            db_session.commit()
            result = SystemSettings.get_value('get.test')
            assert result == {'x': 42}

    def test_get_value_missing_returns_default(self, db_session, app):
        """Test get_value returns default for missing key."""
        with app.app_context():
            result = SystemSettings.get_value('missing.key', default='fallback')
            assert result == 'fallback'

    def test_get_value_missing_returns_none(self, db_session, app):
        """Test get_value returns None when no default for missing key."""
        with app.app_context():
            result = SystemSettings.get_value('also.missing.key')
            assert result is None

    def test_set_value_creates_new(self, db_session, app):
        """Test set_value creates new setting."""
        with app.app_context():
            setting = SystemSettings.set_value('new.setting', 'hello', description='A new setting')
            assert setting is not None
            assert SystemSettings.get_value('new.setting') == 'hello'

    def test_set_value_updates_existing(self, db_session, app):
        """Test set_value updates existing setting."""
        with app.app_context():
            SystemSettings.set_value('update.test', 'original')
            SystemSettings.set_value('update.test', 'updated')
            result = SystemSettings.get_value('update.test')
            assert result == 'updated'

    def test_set_value_updates_description(self, db_session, app):
        """Test set_value updates description on update."""
        with app.app_context():
            SystemSettings.set_value('desc.test', 'value', description='Old desc')
            SystemSettings.set_value('desc.test', 'value2', description='New desc')
            setting = SystemSettings.query.filter_by(setting_key='desc.test').first()
            assert setting.description == 'New desc'

    def test_set_value_with_user_id(self, db_session, app):
        """Test set_value stores user_id."""
        with app.app_context():
            user = create_test_user(db_session)
            setting = SystemSettings.set_value('user.setting', 42, user_id=user.id)
            assert setting.updated_by_user_id == user.id

    def test_set_value_update_with_user_id(self, db_session, app):
        """Test set_value updates user_id on existing setting."""
        with app.app_context():
            user = create_test_user(db_session)
            SystemSettings.set_value('user.update.setting', 'v1')
            SystemSettings.set_value('user.update.setting', 'v2', user_id=user.id)
            setting = SystemSettings.query.filter_by(setting_key='user.update.setting').first()
            assert setting.updated_by_user_id == user.id

    def test_get_all_as_dict(self, db_session, app):
        """Test get_all_as_dict returns all settings."""
        with app.app_context():
            SystemSettings.set_value('dict.key1', 'val1')
            SystemSettings.set_value('dict.key2', 'val2')
            result = SystemSettings.get_all_as_dict()
            assert isinstance(result, dict)
            assert result.get('dict.key1') == 'val1'
            assert result.get('dict.key2') == 'val2'
