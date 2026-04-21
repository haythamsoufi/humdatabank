import 'package:get_it/get_it.dart';

import '../services/storage_service.dart';
import '../services/connectivity_service.dart';
import '../services/performance_service.dart';
import '../services/organization_config_service.dart';
import '../services/offline_cache_service.dart';
import '../services/offline_queue_service.dart';
import '../services/ai_chat_persistence_service.dart';
import '../services/api_service.dart';
import '../services/session_service.dart';
import '../services/user_scope_service.dart';
import '../services/user_profile_service.dart';
import '../services/notification_service.dart';
import '../services/ai_chat_service.dart';
import '../services/push_notification_service.dart';
import '../services/global_overview_data_service.dart';
import '../services/auth_service.dart';
import '../services/auth_error_handler.dart';
import '../services/error_handler.dart';
import '../services/analytics_service.dart';
import '../services/deep_link_service.dart';
import '../services/dio_client.dart';

final sl = GetIt.instance;

/// Register all services with GetIt in dependency order.
///
/// Each service is registered as a lazy singleton: the factory constructor
/// returns the existing `_instance` from the hard-wired singleton, so the
/// service locator wraps (not replaces) the current pattern. In tests,
/// [sl.registerSingleton] or [sl.allowReassignment] can substitute mocks.
void setupServiceLocator() {
  // ── Tier 1: Leaf services (no service dependencies) ──────────────────
  sl.registerLazySingleton<StorageService>(() => StorageService());
  sl.registerLazySingleton<ConnectivityService>(() => ConnectivityService());
  sl.registerLazySingleton<PerformanceService>(() => PerformanceService());
  sl.registerLazySingleton<OrganizationConfigService>(
      () => OrganizationConfigService());
  sl.registerLazySingleton<OfflineCacheService>(() => OfflineCacheService());
  sl.registerLazySingleton<OfflineQueueService>(() => OfflineQueueService());
  sl.registerLazySingleton<AiChatPersistenceService>(
      () => AiChatPersistenceService());
  sl.registerLazySingleton<AnalyticsService>(() => AnalyticsService());
  sl.registerLazySingleton<DeepLinkService>(() => DeepLinkService());
  sl.registerLazySingleton<DioClient>(() => DioClient());

  // ── Tier 2: Depend on Tier 1 (StorageService) ────────────────────────
  sl.registerLazySingleton<ApiService>(() => ApiService());
  sl.registerLazySingleton<SessionService>(() => SessionService());
  sl.registerLazySingleton<UserScopeService>(() => UserScopeService());

  // ── Tier 3: Depend on Tier 2 (ApiService, StorageService) ────────────
  sl.registerLazySingleton<UserProfileService>(() => UserProfileService());
  sl.registerLazySingleton<NotificationService>(() => NotificationService());
  sl.registerLazySingleton<AiChatService>(() => AiChatService());
  sl.registerLazySingleton<PushNotificationService>(
      () => PushNotificationService());
  sl.registerLazySingleton<GlobalOverviewDataService>(
      () => GlobalOverviewDataService());

  // ── Tier 4: Depend on Tier 3 (multiple lower-tier services) ──────────
  sl.registerLazySingleton<AuthService>(() => AuthService());

  // ── Tier 5: Depend on AuthService ────────────────────────────────────
  sl.registerLazySingleton<AuthErrorHandler>(() => AuthErrorHandler());

  // ── Tier 6: Depend on AuthErrorHandler ───────────────────────────────
  sl.registerLazySingleton<ErrorHandler>(() => ErrorHandler());
}
