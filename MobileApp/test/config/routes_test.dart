import 'package:flutter_test/flutter_test.dart';
import 'package:hum_databank_app/config/routes.dart';

void main() {
  group('AppRoutes static constants', () {
    test('splash is "/"', () {
      expect(AppRoutes.splash, '/');
    });

    test('login is "/login"', () {
      expect(AppRoutes.login, '/login');
    });

    test('dashboard is "/dashboard"', () {
      expect(AppRoutes.dashboard, '/dashboard');
    });

    test('admin routes have correct values', () {
      expect(AppRoutes.admin, '/admin');
      expect(AppRoutes.adminDashboard, '/admin/dashboard');
      expect(AppRoutes.templates, '/admin/templates');
      expect(AppRoutes.assignments, '/admin/assignments');
      expect(AppRoutes.users, '/admin/users');
      expect(AppRoutes.indicatorBankAdmin, '/admin/indicator_bank');
      expect(AppRoutes.loginLogs, '/admin/login-logs');
      expect(AppRoutes.sessionLogs, '/admin/session-logs');
    });

    test('public routes have correct values', () {
      expect(AppRoutes.indicatorBank, '/indicator-bank');
      expect(AppRoutes.proposeIndicator, '/indicator-bank/propose');
      expect(AppRoutes.resources, '/resources');
      expect(AppRoutes.quizGame, '/quiz-game');
      expect(AppRoutes.leaderboard, '/leaderboard');
      expect(AppRoutes.aiChat, '/ai-chat');
    });
  });

  group('AppRoutes.editEntity', () {
    test('produces path without entityType', () {
      expect(AppRoutes.editEntity(5), '/admin/organization/edit/5');
    });

    test('produces path with entityType', () {
      expect(
        AppRoutes.editEntity(10, 'branch'),
        '/admin/organization/edit/branch/10',
      );
    });

    test('handles entityType with underscores', () {
      expect(
        AppRoutes.editEntity(3, 'regional_office'),
        '/admin/organization/edit/regional_office/3',
      );
    });
  });

  group('AppRoutes.indicatorDetail', () {
    test('produces correct path', () {
      expect(AppRoutes.indicatorDetail(42), '/indicator-bank/42');
    });

    test('handles large ids', () {
      expect(AppRoutes.indicatorDetail(99999), '/indicator-bank/99999');
    });
  });

  group('AppRoutes.editIndicator', () {
    test('produces correct path', () {
      expect(AppRoutes.editIndicator(7), '/admin/indicator_bank/edit/7');
    });
  });

  group('AppRoutes.documentDetail', () {
    test('produces correct path', () {
      expect(AppRoutes.documentDetail(42), '/admin/documents/42');
    });
  });

  group('AppRoutes.resourceDetail', () {
    test('produces correct path', () {
      expect(AppRoutes.resourceDetail(42), '/admin/resources/42');
    });
  });

  group('AppRoutes.isNativeAdminPath', () {
    test('returns true for exact admin paths', () {
      expect(AppRoutes.isNativeAdminPath('/admin'), true);
      expect(AppRoutes.isNativeAdminPath('/admin/dashboard'), true);
      expect(AppRoutes.isNativeAdminPath('/admin/templates'), true);
      expect(AppRoutes.isNativeAdminPath('/admin/assignments'), true);
      expect(AppRoutes.isNativeAdminPath('/admin/users'), true);
      expect(AppRoutes.isNativeAdminPath('/admin/access-requests'), true);
      expect(AppRoutes.isNativeAdminPath('/admin/documents'), true);
      expect(AppRoutes.isNativeAdminPath('/admin/documents/12'), true);
      expect(AppRoutes.isNativeAdminPath('/admin/documents/edit/12'), false);
      expect(AppRoutes.isNativeAdminPath('/admin/documents/serve/3'), false);
      expect(AppRoutes.isNativeAdminPath('/admin/documents/not-a-number'), false);
      expect(AppRoutes.isNativeAdminPath('/admin/translations/manage'), true);
      expect(AppRoutes.isNativeAdminPath('/admin/resources'), true);
      expect(AppRoutes.isNativeAdminPath('/admin/resources/12'), true);
      expect(AppRoutes.isNativeAdminPath('/admin/resources/new'), false);
      expect(AppRoutes.isNativeAdminPath('/admin/resources/edit/5'), false);
      expect(AppRoutes.isNativeAdminPath('/admin/organization'), true);
      expect(AppRoutes.isNativeAdminPath('/admin/indicator_bank'), true);
      expect(AppRoutes.isNativeAdminPath('/admin/analytics/dashboard'), true);
      expect(AppRoutes.isNativeAdminPath('/admin/analytics/audit-trail'), true);
    });

    test('returns true for indicator_bank edit paths with numeric id', () {
      expect(AppRoutes.isNativeAdminPath('/admin/indicator_bank/edit/5'), true);
      expect(AppRoutes.isNativeAdminPath('/admin/indicator_bank/edit/999'), true);
    });

    test('returns false for indicator_bank edit with non-numeric id', () {
      expect(AppRoutes.isNativeAdminPath('/admin/indicator_bank/edit/abc'), false);
    });

    test('returns true for organization edit with numeric id (no entityType)', () {
      expect(AppRoutes.isNativeAdminPath('/admin/organization/edit/42'), true);
    });

    test('returns true for organization edit with entityType and numeric id', () {
      expect(AppRoutes.isNativeAdminPath('/admin/organization/edit/branch/10'), true);
    });

    test('returns false for organization edit with non-numeric last segment', () {
      expect(AppRoutes.isNativeAdminPath('/admin/organization/edit/branch/abc'), false);
    });

    test('returns false for unknown /admin/... paths', () {
      expect(AppRoutes.isNativeAdminPath('/admin/some-unknown-page'), false);
      expect(AppRoutes.isNativeAdminPath('/admin/plugins'), false);
      expect(AppRoutes.isNativeAdminPath('/admin/settings'), false);
    });

    test('returns false for non-admin paths', () {
      expect(AppRoutes.isNativeAdminPath('/dashboard'), false);
      expect(AppRoutes.isNativeAdminPath('/login'), false);
      expect(AppRoutes.isNativeAdminPath('/indicator-bank'), false);
      expect(AppRoutes.isNativeAdminPath('/'), false);
    });

    test('strips query parameters before matching', () {
      expect(AppRoutes.isNativeAdminPath('/admin/dashboard?tab=users'), true);
      expect(AppRoutes.isNativeAdminPath('/admin/users?page=2'), true);
    });

    test('strips fragment before matching', () {
      expect(AppRoutes.isNativeAdminPath('/admin/dashboard#section'), true);
    });
  });
}
