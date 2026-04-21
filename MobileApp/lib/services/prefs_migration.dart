import '../config/app_config.dart';
import 'storage_service.dart';

/// One-time style migration from unprefixed SharedPreferences keys to
/// [AppConfig] env-prefixed keys (staging/dev/prod isolation).
///
/// Idempotent: safe to run on every launch; copies legacy → canonical then
/// removes legacy when canonical was empty.
Future<void> migrateLegacySharedPreferencesKeys(StorageService storage) async {
  await storage.init();

  Future<void> migrateString(String legacy, String canonical) async {
    // Production uses an empty [_storagePrefix], so legacy and canonical are
    // the same string. Removing "legacy" would delete the live preference
    // every cold start — skip when there is nothing to migrate.
    if (legacy == canonical) return;

    final hasNew = await storage.getString(canonical);
    if (hasNew != null) {
      await storage.remove(legacy);
      return;
    }
    final old = await storage.getString(legacy);
    if (old != null) {
      await storage.setString(canonical, old);
      await storage.remove(legacy);
    }
  }

  await migrateString('theme_mode', AppConfig.themeModeKey);
  await migrateString('selected_language', AppConfig.selectedLanguageKey);
  await migrateString('arabic_text_font', AppConfig.arabicTextFontKey);
  await migrateString(
    'humdb_chatbot_ai_policy_acknowledged',
    AppConfig.chatbotAiPolicyAcknowledgedKey,
  );
  await migrateString('humdb_chatbot_sources', AppConfig.chatbotSourcesKey);
  await migrateString(
    'humdb_chatbot_pinned_conversation_ids',
    AppConfig.chatbotPinnedConversationIdsKey,
  );
  await migrateString('last_synced_timestamp', AppConfig.lastSyncedTimestampKey);
  await migrateString(
    'audit_trail_widget_activity_filters_v1',
    AppConfig.auditTrailWidgetActivityFiltersKey,
  );

  const roleKeys = ['admin', 'focal', 'auth', 'guest'];
  for (final rk in roleKeys) {
    await migrateString(
      'tab_customization_$rk',
      '${AppConfig.tabCustomizationKeyPrefix}$rk',
    );
  }
}
