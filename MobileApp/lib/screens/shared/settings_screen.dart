import 'package:flutter/material.dart';
import 'package:flutter/cupertino.dart' as cupertino;
import 'package:provider/provider.dart';
import '../../providers/shared/auth_provider.dart';
import '../../providers/shared/language_provider.dart';
import '../../providers/shared/theme_provider.dart';
import '../../config/routes.dart';
import '../../utils/constants.dart';
import '../../utils/avatar_initials.dart';
import '../../widgets/profile_leading_avatar.dart';
import '../../utils/ios_constants.dart';
import '../../utils/arabic_text_font.dart';
import '../../utils/ios_settings_style.dart';
import '../../widgets/ios_list_tile.dart';
import '../../widgets/ios_settings_scaffold.dart';
import '../../widgets/ios_settings_controls.dart';
import '../../widgets/ios_dialog.dart';
import '../../widgets/bottom_navigation_bar.dart';
import '../../providers/shared/tab_customization_provider.dart';
import '../../widgets/profile_color_picker_dialog.dart';
import '../../widgets/settings_dialogs.dart';
import '../../l10n/app_localizations.dart';
import '../../models/shared/user.dart';

class SettingsScreen extends StatelessWidget {
  const SettingsScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return Consumer<AuthProvider>(
      builder: (context, authProvider, child) {
        final user = authProvider.user;
        final isAuthenticated = authProvider.isAuthenticated;

        final localizations = AppLocalizations.of(context)!;
        final bodyChildren = _buildSettingsBodyChildren(
          context,
          authProvider,
          user,
          isAuthenticated,
          localizations,
        );

        return IOSSettingsPageScaffold(
          title: localizations.accountSettings,
          children: bodyChildren,
        );
      },
    );
  }

  /// Shared scroll content for Material (ListView) and iOS (CustomScrollView) layouts.
  List<Widget> _buildSettingsBodyChildren(
    BuildContext context,
    AuthProvider authProvider,
    User? user,
    bool isAuthenticated,
    AppLocalizations localizations,
  ) {
    return [
      if (isAuthenticated && user != null) ...[
        _buildProfileSection(context, user),
        SizedBox(height: IOSSettingsStyle.sectionSpacing),
      ],
      if (isAuthenticated && user != null) ...[
        _buildAccountInfoSection(context, user),
        SizedBox(height: IOSSettingsStyle.sectionSpacing),
      ],
      if (isAuthenticated && user != null) ...[
        _buildPreferencesSection(context, user),
        SizedBox(height: IOSSettingsStyle.sectionSpacing),
      ],
      _buildAccountActionsSection(context, isAuthenticated),
      SizedBox(height: IOSSettingsStyle.sectionSpacing),
      Padding(
        padding: EdgeInsets.symmetric(
          horizontal: IOSSettingsStyle.pageHorizontalInset,
        ),
        child: _buildAuthButton(context, authProvider, isAuthenticated),
      ),
      const SizedBox(height: IOSSpacing.lg),
    ];
  }

  /// Builds the Profile section with user information (iPhone-style)
  Widget _buildProfileSection(BuildContext context, User user) {
    final displayName = user.displayName;
    final initials =
        avatarInitialsForProfile(name: user.name, email: user.email);

    final theme = Theme.of(context);
    return _buildSettingsCard(
      context: context,
      children: [
        IOSListTile(
          leading: ProfileLeadingAvatar(
            initials: initials,
            profileColorHex: user.profileColor,
            size: 56,
            useGradient: true,
          ),
          title: Text(
            displayName,
            style: IOSTextStyle.title2(context).copyWith(
              fontWeight: FontWeight.w400,
              color: theme.colorScheme.onSurface,
            ),
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
          ),
          subtitle: Text(
            user.email,
            style: IOSTextStyle.callout(context).copyWith(
              color: theme.colorScheme.onSurface.withValues(alpha: 0.6),
            ),
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
          ),
        ),
      ],
    );
  }

  /// Builds the Account Information section with editable fields (iPhone-style)
  Widget _buildAccountInfoSection(BuildContext context, User user) {
    final localizations = AppLocalizations.of(context)!;
    final theme = Theme.of(context);

    return _buildSettingsCard(
      context: context,
      children: [
        Semantics(
          label: '${localizations.name}, ${user.name ?? localizations.enterYourName}',
          button: true,
          child: IOSListTile(
            leading: IOSSettingsStyle.leadingIcon(
              context,
              cupertino.CupertinoIcons.person,
            ),
            title: Text(
              localizations.name,
              style: IOSSettingsStyle.rowTitleStyle(context),
            ),
            subtitle: Text(
              user.name ?? localizations.enterYourName,
              style: IOSSettingsStyle.rowSubtitleStyle(context).copyWith(
                color: user.name != null && user.name!.isNotEmpty
                    ? theme.colorScheme.onSurface.withValues(alpha: 0.6)
                    : theme.colorScheme.onSurface.withValues(alpha: 0.4),
              ),
            ),
            trailing: IOSSettingsStyle.disclosureChevron(context),
            onTap: () {
              final authProvider =
                  Provider.of<AuthProvider>(context, listen: false);
              showEditProfileFieldDialog(
                context,
                currentValue: user.name,
                fieldLabel: localizations.editName,
                hintText: localizations.enterYourName,
                prefixIcon: Icons.person_outline,
                emptyValidationMessage: localizations.nameCannotBeEmpty,
                onSave: (value) => authProvider.updateProfile(name: value),
              );
            },
          ),
        ),
        Semantics(
          label: '${localizations.title}, ${user.title ?? localizations.enterYourJobTitle}',
          button: true,
          child: IOSListTile(
            leading: IOSSettingsStyle.leadingIcon(
              context,
              cupertino.CupertinoIcons.briefcase,
            ),
            title: Text(
              localizations.title,
              style: IOSSettingsStyle.rowTitleStyle(context),
            ),
            subtitle: Text(
              user.title ?? localizations.enterYourJobTitle,
              style: IOSSettingsStyle.rowSubtitleStyle(context).copyWith(
                color: user.title != null && user.title!.isNotEmpty
                    ? theme.colorScheme.onSurface.withValues(alpha: 0.6)
                    : theme.colorScheme.onSurface.withValues(alpha: 0.4),
              ),
            ),
            trailing: IOSSettingsStyle.disclosureChevron(context),
            onTap: () {
              final authProvider =
                  Provider.of<AuthProvider>(context, listen: false);
              showEditProfileFieldDialog(
                context,
                currentValue: user.title,
                fieldLabel: localizations.editTitle,
                hintText: localizations.enterYourJobTitle,
                prefixIcon: Icons.work_outline,
                emptyValidationMessage: localizations.titleCannotBeEmpty,
                onSave: (value) => authProvider.updateProfile(title: value),
              );
            },
          ),
        ),
      ],
    );
  }

  /// Helper method to build iPhone-style settings card
  Widget _buildSettingsCard({
    required BuildContext context,
    required List<Widget> children,
  }) {
    return IOSGroupedList(
      margin: EdgeInsets.symmetric(
        horizontal: IOSSettingsStyle.pageHorizontalInset,
      ),
      children: children,
    );
  }

  /// Builds the Preferences section (Profile Color and Chatbot)
  /// Only shown for authenticated users (iPhone-style)
  Widget _buildPreferencesSection(BuildContext context, User user) {
    final localizations = AppLocalizations.of(context)!;
    final theme = Theme.of(context);
    // Safe color parsing
    Color? parseProfileColor(String? colorString) {
      if (colorString == null || colorString.isEmpty) return null;
      try {
        final cleanColor = colorString.replaceFirst('#', '0xFF');
        return Color(int.parse(cleanColor));
      } catch (e) {
        return null;
      }
    }

    final profileColor =
        parseProfileColor(user.profileColor) ?? const Color(AppConstants.semanticDefaultProfileAccent);

    return _buildSettingsCard(
      context: context,
      children: [
        IOSListTile(
          leading: IOSSettingsStyle.leadingIcon(
            context,
            cupertino.CupertinoIcons.color_filter,
          ),
          title: Text(
            localizations.profileColor,
            style: IOSSettingsStyle.rowTitleStyle(context),
          ),
          subtitle: Text(
            user.profileColor ?? '#3B82F6',
            style: IOSSettingsStyle.rowSubtitleStyle(context),
          ),
          trailing: Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              Container(
                width: 24,
                height: 24,
                decoration: BoxDecoration(
                  color: profileColor,
                  shape: BoxShape.circle,
                  border: Border.all(
                    color: theme.dividerColor,
                    width: 1,
                  ),
                ),
              ),
              const SizedBox(width: IOSSpacing.xs + 2),
              Icon(
                cupertino.CupertinoIcons.chevron_right,
                color: theme.colorScheme.onSurface.withValues(alpha: 0.3),
                size: 13,
              ),
            ],
          ),
          onTap: () {
            final authProvider =
                Provider.of<AuthProvider>(context, listen: false);
            _showColorPicker(context, authProvider, user);
          },
        ),
        IOSListSwitchTile(
          leading: cupertino.CupertinoIcons.chat_bubble_2,
          title: localizations.chatbot,
          subtitle: localizations.enableChatbotAssistance,
          value: user.chatbotEnabled,
          onChanged: (value) {
            _updateChatbotPreference(context, value);
          },
          semanticsLabel:
              '${localizations.chatbot}, ${localizations.enableChatbotAssistance}',
        ),
      ],
    );
  }

  /// Builds the Account Actions section (iPhone-style)
  /// - Change Password: Only for authenticated users
  /// - Theme: Available for everyone (light/dark/system)
  /// - Language: Available for everyone (app-level setting)
  Widget _buildAccountActionsSection(
      BuildContext context, bool isAuthenticated) {
    final localizations = AppLocalizations.of(context)!;
    final theme = Theme.of(context);
    final List<Widget> actions = [];

    // Change Password - Only for authenticated users
    if (isAuthenticated) {
      actions.add(
        Semantics(
          label: localizations.changePassword,
          button: true,
          child: IOSListTile(
            leading: Icon(
              cupertino.CupertinoIcons.lock,
              color: theme.colorScheme.onSurface,
              size: 22,
            ),
            title: Text(
              localizations.changePassword,
              style: IOSTextStyle.body(context).copyWith(
                fontWeight: FontWeight.w400,
                color: theme.colorScheme.onSurface,
              ),
            ),
            trailing: Icon(
              cupertino.CupertinoIcons.chevron_right,
              color: theme.colorScheme.onSurface.withValues(alpha: 0.3),
              size: 13,
            ),
            onTap: () {
              final authProvider =
                  Provider.of<AuthProvider>(context, listen: false);
              showChangePasswordDialog(context, authProvider);
            },
          ),
        ),
      );
    }

    // Theme (Light / Dark / System) - Available for everyone
    actions.add(
      Consumer<ThemeProvider>(
        builder: (context, themeProvider, child) {
          String modeLabel(String mode) {
            switch (mode) {
              case 'dark':
                return localizations.darkTheme;
              case 'light':
                // Reuse existing label if available; otherwise fall back to English.
                // (Keeping this lightweight avoids adding new l10n keys right now.)
                return 'Light theme';
              case 'system':
              default:
                return 'System';
            }
          }

          return IOSListTile(
            leading: IOSSettingsStyle.leadingIcon(
              context,
              cupertino.CupertinoIcons.circle_lefthalf_fill,
            ),
            title: Text(
              'Theme',
              style: IOSSettingsStyle.rowTitleStyle(context),
            ),
            subtitle: Text(
              modeLabel(themeProvider.currentThemeMode),
              style: IOSSettingsStyle.rowSubtitleStyle(context),
            ),
            trailing: IOSSettingsStyle.disclosureChevron(context),
            onTap: () {
              _showThemeModePicker(context, themeProvider);
            },
          );
        },
      ),
    );

    // Language - Available for everyone
    actions.add(
      Consumer<LanguageProvider>(
        builder: (context, languageProvider, child) {
          final currentLanguage = languageProvider.currentLanguage;
          final languageName =
              languageProvider.getLanguageName(currentLanguage);

          return IOSListTile(
            leading: IOSSettingsStyle.leadingIcon(
              context,
              cupertino.CupertinoIcons.globe,
            ),
            title: Text(
              localizations.language,
              style: IOSSettingsStyle.rowTitleStyle(context),
            ),
            subtitle: Text(
              languageName,
              style: IOSSettingsStyle.rowSubtitleStyle(context),
            ),
            trailing: IOSSettingsStyle.disclosureChevron(context),
            onTap: () {
              _showLanguagePicker(context, languageProvider);
            },
          );
        },
      ),
    );

    actions.add(
      Consumer<LanguageProvider>(
        builder: (context, languageProvider, child) {
          if (languageProvider.currentLanguage != 'ar') {
            return const SizedBox.shrink();
          }
          final subtitle =
              languageProvider.arabicTextFontPreference ==
                      ArabicTextFontPreference.system
                  ? localizations.arabicFontSystem
                  : localizations.arabicFontTajawal;
          return IOSListTile(
            leading: IOSSettingsStyle.leadingIcon(
              context,
              cupertino.CupertinoIcons.textformat,
            ),
            title: Text(
              localizations.arabicTextFont,
              style: IOSSettingsStyle.rowTitleStyle(context),
            ),
            subtitle: Text(
              subtitle,
              style: IOSSettingsStyle.rowSubtitleStyle(context),
            ),
            trailing: IOSSettingsStyle.disclosureChevron(context),
            onTap: () {
              _showArabicFontPicker(context, languageProvider);
            },
          );
        },
      ),
    );

    return _buildSettingsCard(
      context: context,
      children: actions,
    );
  }

  /// Builds the authentication button (Login or Logout) - iPhone style
  Widget _buildAuthButton(
    BuildContext context,
    AuthProvider authProvider,
    bool isAuthenticated,
  ) {
    final localizations = AppLocalizations.of(context)!;

    if (!isAuthenticated) {
      return IOSGroupedPlainButton(
        label: localizations.loginToAccount,
        textColor: Color(AppConstants.ifrcRed),
        onPressed: () {
          final user = authProvider.user;
          final tabProvider =
              Provider.of<TabCustomizationProvider>(context, listen: false);
          final settingsIdx = tabProvider.indexOfTab(
            TabIds.settings,
            isAdmin: user?.isAdmin ?? false,
            isAuthenticated: false,
            isFocalPoint: false,
            chatbotEnabled: user?.chatbotEnabled ?? false,
          );
          Navigator.of(context).pushNamed(
            AppRoutes.login,
            arguments: settingsIdx >= 0
                ? settingsIdx
                : AppBottomNavigationBar.noTabSelected,
          );
        },
      );
    }

    return IOSGroupedPlainButton(
      label: localizations.logout,
      textColor: const Color(AppConstants.errorColor),
      onPressed: () async {
        final confirm = await IOSAlertDialog.show<bool>(
          context: context,
          title: localizations.logout,
          message: localizations.areYouSureLogout,
          actions: [
            cupertino.CupertinoDialogAction(
              child: Text(
                localizations.cancel,
                style: IOSTextStyle.body(context),
              ),
              onPressed: () => Navigator.of(context).pop(false),
            ),
            cupertino.CupertinoDialogAction(
              isDestructiveAction: true,
              child: Text(
                localizations.logout,
                style: IOSTextStyle.body(context).copyWith(
                  fontWeight: FontWeight.w600,
                ),
              ),
              onPressed: () => Navigator.of(context).pop(true),
            ),
          ],
        );

        if (confirm == true) {
          await authProvider.logout();
          if (!context.mounted) return;
          Navigator.of(context).pushNamedAndRemoveUntil(
            AppRoutes.dashboard,
            (route) => false,
          );
        }
      },
    );
  }

  /// Shows a color picker dialog
  Future<void> _showColorPicker(
      BuildContext context, AuthProvider authProvider, user) async {
    final localizations = AppLocalizations.of(context)!;

    final currentColor = user.profileColor ?? '#3B82F6';
    final selectedColor = await showProfileColorPickerDialog(context, currentColor);

    if (selectedColor != null &&
        selectedColor != currentColor &&
        context.mounted) {
      // Show loading indicator
      showDialog(
        context: context,
        barrierDismissible: false,
        builder: (context) => const Center(
          child: CircularProgressIndicator(),
        ),
      );

      // Update profile color
      final success = await authProvider.updateProfileColor(selectedColor);

      if (context.mounted) {
        Navigator.of(context).pop(); // Close loading dialog

        if (success) {
          ScaffoldMessenger.of(context).showSnackBar(
            SnackBar(
              content: Text(localizations.profileColorUpdated),
              duration: const Duration(seconds: 2),
              backgroundColor: Color(AppConstants.ifrcRed),
            ),
          );
        } else {
          ScaffoldMessenger.of(context).showSnackBar(
            SnackBar(
              content: Text(localizations.profileColorUpdateFailed),
              duration: const Duration(seconds: 3),
              backgroundColor: const Color(AppConstants.errorColor),
            ),
          );
        }
      }
    }
  }

  /// Shows a language picker dialog
  void _showLanguagePicker(
      BuildContext context, LanguageProvider languageProvider) {
    final localizations = AppLocalizations.of(context)!;
    final theme = Theme.of(context);

    // Use Cupertino action sheet for iOS-native feel
    final actions = LanguageProvider.availableLanguages.map<cupertino.CupertinoActionSheetAction>((language) {
      final isSelected = languageProvider.currentLanguage == language['code'];
      return cupertino.CupertinoActionSheetAction(
        onPressed: () async {
          final selectedCode = language['code'];
          if (selectedCode != null) {
            await languageProvider.setLanguage(selectedCode);
            if (context.mounted) {
              Navigator.of(context).pop();
              ScaffoldMessenger.of(context).showSnackBar(
                SnackBar(
                  content: Text(localizations
                      .languageChangedTo(language['name']!)),
                  duration: const Duration(seconds: 2),
                  backgroundColor: Color(AppConstants.ifrcRed),
                ),
              );
            }
          }
        },
        child: Row(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            if (isSelected) ...[
              Icon(
                cupertino.CupertinoIcons.check_mark,
                color: IOSColors.getSystemBlue(context),
                size: 18,
              ),
              const SizedBox(width: IOSSpacing.sm),
            ],
            Text(
              language['name'] ?? '',
              style: IOSTextStyle.body(context).copyWith(
                fontWeight: isSelected ? FontWeight.w600 : FontWeight.w400,
                color: isSelected
                    ? IOSColors.getSystemBlue(context)
                    : theme.colorScheme.onSurface,
              ),
            ),
          ],
        ),
      );
    }).toList();

    IOSActionSheet.show(
      context: context,
      title: localizations.selectLanguage,
      actions: actions,
    );
  }

  /// Shows a theme mode picker dialog (Light / Dark / System)
  void _showThemeModePicker(BuildContext context, ThemeProvider themeProvider) {
    final theme = Theme.of(context);

    // Use Cupertino action sheet for iOS-native feel (consistent with language picker)
    final options = <Map<String, String>>[
      {'code': 'system', 'name': 'System'},
      {'code': 'light', 'name': 'Light theme'},
      {'code': 'dark', 'name': AppLocalizations.of(context)!.darkTheme},
    ];

    final actions = options.map<cupertino.CupertinoActionSheetAction>((opt) {
      final code = opt['code']!;
      final name = opt['name']!;
      final isSelected = themeProvider.currentThemeMode == code;

      return cupertino.CupertinoActionSheetAction(
        onPressed: () async {
          await themeProvider.setThemeMode(code);
          if (context.mounted) {
            Navigator.of(context).pop();
            ScaffoldMessenger.of(context).showSnackBar(
              SnackBar(
                content: Text(AppLocalizations.of(context)!.settingsThemeSetTo(name)),
                duration: const Duration(seconds: 2),
                backgroundColor: Color(AppConstants.ifrcRed),
              ),
            );
          }
        },
        child: Row(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            if (isSelected) ...[
              Icon(
                cupertino.CupertinoIcons.check_mark,
                color: IOSColors.getSystemBlue(context),
                size: 18,
              ),
              const SizedBox(width: IOSSpacing.sm),
            ],
            Text(
              name,
              style: IOSTextStyle.body(context).copyWith(
                fontWeight: isSelected ? FontWeight.w600 : FontWeight.w400,
                color: isSelected
                    ? IOSColors.getSystemBlue(context)
                    : theme.colorScheme.onSurface,
              ),
            ),
          ],
        ),
      );
    }).toList();

    IOSActionSheet.show(
      context: context,
      title: 'Select theme',
      actions: actions,
    );
  }

  void _showArabicFontPicker(
      BuildContext context, LanguageProvider languageProvider) {
    final localizations = AppLocalizations.of(context)!;
    final theme = Theme.of(context);

    final options = <(ArabicTextFontPreference, String)>[
      (ArabicTextFontPreference.tajawal, localizations.arabicFontTajawal),
      (ArabicTextFontPreference.system, localizations.arabicFontSystem),
    ];

    final sheetActions =
        options.map<cupertino.CupertinoActionSheetAction>((entry) {
      final pref = entry.$1;
      final name = entry.$2;
      final isSelected = languageProvider.arabicTextFontPreference == pref;

      return cupertino.CupertinoActionSheetAction(
        onPressed: () async {
          await languageProvider.setArabicTextFontPreference(pref);
          if (context.mounted) {
            Navigator.of(context).pop();
          }
        },
        child: Row(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            if (isSelected) ...[
              Icon(
                cupertino.CupertinoIcons.check_mark,
                color: IOSColors.getSystemBlue(context),
                size: 18,
              ),
              const SizedBox(width: IOSSpacing.sm),
            ],
            Text(
              name,
              style: IOSTextStyle.body(context).copyWith(
                fontWeight: isSelected ? FontWeight.w600 : FontWeight.w400,
                color: isSelected
                    ? IOSColors.getSystemBlue(context)
                    : theme.colorScheme.onSurface,
              ),
            ),
          ],
        ),
      );
    }).toList();

    IOSActionSheet.show(
      context: context,
      title: localizations.arabicTextFont,
      actions: sheetActions,
    );
  }

  /// Updates chatbot preference
  Future<void> _updateChatbotPreference(BuildContext context, bool value) async {
    final authProvider = Provider.of<AuthProvider>(context, listen: false);

    // Show loading indicator
    showDialog(
      context: context,
      barrierDismissible: false,
      builder: (context) => const Center(
        child: CircularProgressIndicator(),
      ),
    );

    // Update chatbot preference
    final success = await authProvider.updateProfile(
      chatbotEnabled: value,
    );

    if (context.mounted) {
      Navigator.of(context).pop(); // Close loading dialog

      final localizations = AppLocalizations.of(context)!;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(success
              ? localizations.profileUpdatedSuccessfully
              : localizations.errorUpdatingProfile),
          backgroundColor: success ? Colors.green : Colors.red,
          duration: const Duration(seconds: 2),
        ),
      );
    }
  }
}
