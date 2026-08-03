import { initAiSettings } from './ai-settings.js';
import { initNotificationSettings } from './notification-settings.js';
import { getSettingsPageConfig } from './common.js';

const cfg = getSettingsPageConfig();
initNotificationSettings(cfg);
initAiSettings(cfg);
