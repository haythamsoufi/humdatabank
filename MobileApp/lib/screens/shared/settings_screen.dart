import 'package:flutter/material.dart';
import 'package:flutter/cupertino.dart' as cupertino;
import 'package:provider/provider.dart';
import '../../providers/shared/auth_provider.dart';
import '../../providers/shared/language_provider.dart';
import '../../providers/shared/theme_provider.dart';
import '../../widgets/app_bar.dart';
import '../../widgets/app_switch_list_tile.dart';
import '../../config/routes.dart';
import '../../utils/constants.dart';
import '../../utils/theme_extensions.dart';
import '../../utils/ios_constants.dart';
import '../../widgets/ios_card.dart';
import '../../widgets/ios_list_tile.dart';
import '../../widgets/ios_dialog.dart';
import '../../l10n/app_localizations.dart';

class SettingsScreen extends StatelessWidget {
  const SettingsScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return Consumer<AuthProvider>(
      builder: (context, authProvider, child) {
        final user = authProvider.user;
        final isAuthenticated = authProvider.isAuthenticated;

        final localizations = AppLocalizations.of(context)!;

        return Scaffold(
          appBar: AppAppBar(
            title: localizations.accountSettings,
          ),
          body: SafeArea(
            child: Container(
              color: IOSColors.getGroupedBackground(context),
              child: ListView(
                padding: EdgeInsets.zero,
                children: [
                  // Profile Section - Only show for authenticated users
                  if (isAuthenticated && user != null) ...[
                    _buildProfileSection(context, user),
                    SizedBox(height: IOSSpacing.xxl),
                  ],

                  // Account Information Section - Only show for authenticated users
                  if (isAuthenticated && user != null) ...[
                    _buildAccountInfoSection(context, user),
                    SizedBox(height: IOSSpacing.xxl),
                  ],

                  // Preferences Section - Only show for authenticated users
                  if (isAuthenticated && user != null) ...[
                    _buildPreferencesSection(context, user),
                    SizedBox(height: IOSSpacing.xxl),
                  ],

                  // Account Actions Section
                  _buildAccountActionsSection(context, isAuthenticated),

                  SizedBox(height: IOSSpacing.xxl),

                  // Login/Logout Button
                  Padding(
                    padding: EdgeInsets.symmetric(horizontal: IOSSpacing.md),
                    child: _buildAuthButton(
                        context, authProvider, isAuthenticated),
                  ),
                  SizedBox(height: IOSSpacing.lg),
                ],
              ),
            ),
          ),
        );
      },
    );
  }

  /// Builds the Profile section with user information (iPhone-style)
  Widget _buildProfileSection(BuildContext context, user) {
    final localizations = AppLocalizations.of(context)!;
    // Safe extraction of initial for avatar
    final displayName = user.displayName;
    final initial = displayName.isNotEmpty
        ? displayName.substring(0, 1).toUpperCase()
        : 'U';

    // Parse profile color
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
        parseProfileColor(user.profileColor) ?? const Color(0xFF3B82F6);

    final theme = Theme.of(context);
    return _buildSettingsCard(
      context: context,
      children: [
        IOSListTile(
          leading: Container(
            width: 56,
            height: 56,
            decoration: BoxDecoration(
              gradient: LinearGradient(
                colors: [
                  profileColor,
                  profileColor.withOpacity(0.8),
                ],
              ),
              shape: BoxShape.circle,
            ),
            child: Center(
              child: Text(
                initial,
                style: IOSTextStyle.title1(context).copyWith(
                  color: Colors.white,
                  fontWeight: FontWeight.w500,
                ),
              ),
            ),
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
              color: theme.colorScheme.onSurface.withOpacity(0.6),
            ),
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
          ),
        ),
      ],
    );
  }

  /// Builds the Account Information section with editable fields (iPhone-style)
  Widget _buildAccountInfoSection(BuildContext context, user) {
    final localizations = AppLocalizations.of(context)!;
    final theme = Theme.of(context);

    return _buildSettingsCard(
      context: context,
      children: [
        Semantics(
          label: '${localizations.name}, ${user.name ?? localizations.enterYourName}',
          button: true,
          child: IOSListTile(
            leading: Icon(
              Icons.person_outline,
              color: theme.colorScheme.onSurface,
              size: 20,
            ),
            title: Text(
              localizations.name,
              style: IOSTextStyle.body(context).copyWith(
                fontWeight: FontWeight.w400,
                color: theme.colorScheme.onSurface,
              ),
            ),
            subtitle: Text(
              user.name ?? localizations.enterYourName,
              style: IOSTextStyle.callout(context).copyWith(
                color: user.name != null && user.name!.isNotEmpty
                    ? theme.colorScheme.onSurface.withOpacity(0.6)
                    : theme.colorScheme.onSurface.withOpacity(0.4),
              ),
            ),
            trailing: Icon(
              cupertino.CupertinoIcons.chevron_right,
              color: theme.colorScheme.onSurface.withOpacity(0.3),
              size: 13,
            ),
            onTap: () {
              _showEditNameDialog(context, user);
            },
          ),
        ),
        Semantics(
          label: '${localizations.title}, ${user.title ?? localizations.enterYourJobTitle}',
          button: true,
          child: IOSListTile(
            leading: Icon(
              Icons.work_outline,
              color: theme.colorScheme.onSurface,
              size: 20,
            ),
            title: Text(
              localizations.title,
              style: IOSTextStyle.body(context).copyWith(
                fontWeight: FontWeight.w400,
                color: theme.colorScheme.onSurface,
              ),
            ),
            subtitle: Text(
              user.title ?? localizations.enterYourJobTitle,
              style: IOSTextStyle.callout(context).copyWith(
                color: user.title != null && user.title!.isNotEmpty
                    ? theme.colorScheme.onSurface.withOpacity(0.6)
                    : theme.colorScheme.onSurface.withOpacity(0.4),
              ),
            ),
            trailing: Icon(
              cupertino.CupertinoIcons.chevron_right,
              color: theme.colorScheme.onSurface.withOpacity(0.3),
              size: 13,
            ),
            onTap: () {
              _showEditTitleDialog(context, user);
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
      margin: EdgeInsets.symmetric(horizontal: IOSSpacing.md),
      children: children,
    );
  }

  /// Builds the Preferences section (Profile Color and Chatbot)
  /// Only shown for authenticated users (iPhone-style)
  Widget _buildPreferencesSection(BuildContext context, user) {
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
        parseProfileColor(user.profileColor) ?? const Color(0xFF3B82F6);

    return _buildSettingsCard(
      context: context,
      children: [
        IOSListTile(
          leading: Icon(
            Icons.color_lens,
            color: theme.colorScheme.onSurface,
            size: 20,
          ),
          title: Text(
            localizations.profileColor,
            style: IOSTextStyle.body(context).copyWith(
              fontWeight: FontWeight.w400,
              color: theme.colorScheme.onSurface,
            ),
          ),
          subtitle: Text(
            user.profileColor ?? '#3B82F6',
            style: IOSTextStyle.callout(context).copyWith(
              color: theme.colorScheme.onSurface.withOpacity(0.6),
            ),
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
              SizedBox(width: IOSSpacing.xs + 2),
              Icon(
                cupertino.CupertinoIcons.chevron_right,
                color: theme.colorScheme.onSurface.withOpacity(0.3),
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
        AppSwitchListTile(
          value: user.chatbotEnabled,
          onChanged: (value) {
            _updateChatbotPreference(context, value);
          },
          title: localizations.chatbot,
          subtitle: localizations.enableChatbotAssistance,
          icon: Icons.chat_bubble_outline,
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
              Icons.lock_outline,
              color: theme.colorScheme.onSurface,
              size: 20,
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
              color: theme.colorScheme.onSurface.withOpacity(0.3),
              size: 13,
            ),
            onTap: () {
              final authProvider =
                  Provider.of<AuthProvider>(context, listen: false);
              _showChangePasswordDialog(context, authProvider);
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
            leading: Icon(
              Icons.brightness_6_outlined,
              color: theme.colorScheme.onSurface,
              size: 20,
            ),
            title: Text(
              'Theme',
              style: IOSTextStyle.body(context).copyWith(
                fontWeight: FontWeight.w400,
                color: theme.colorScheme.onSurface,
              ),
            ),
            subtitle: Text(
              modeLabel(themeProvider.currentThemeMode),
              style: IOSTextStyle.callout(context).copyWith(
                color: theme.colorScheme.onSurface.withOpacity(0.6),
              ),
            ),
            trailing: Icon(
              cupertino.CupertinoIcons.chevron_right,
              color: theme.colorScheme.onSurface.withOpacity(0.3),
              size: 13,
            ),
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
            leading: Icon(
              Icons.language,
              color: theme.colorScheme.onSurface,
              size: 20,
            ),
            title: Text(
              localizations.language,
              style: IOSTextStyle.body(context).copyWith(
                fontWeight: FontWeight.w400,
                color: theme.colorScheme.onSurface,
              ),
            ),
            subtitle: Text(
              languageName,
              style: IOSTextStyle.callout(context).copyWith(
                color: theme.colorScheme.onSurface.withOpacity(0.6),
              ),
            ),
            trailing: Icon(
              cupertino.CupertinoIcons.chevron_right,
              color: theme.colorScheme.onSurface.withOpacity(0.3),
              size: 13,
            ),
            onTap: () {
              _showLanguagePicker(context, languageProvider);
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
    final theme = Theme.of(context);

    if (!isAuthenticated) {
      // Login Button for non-authenticated users
      return IOSGroupedList(
        margin: EdgeInsets.symmetric(horizontal: IOSSpacing.md),
        children: [
          IOSListTile(
            title: Center(
              child: Text(
                localizations.loginToAccount,
                style: IOSTextStyle.body(context).copyWith(
                  fontWeight: FontWeight.w400,
                  color: Color(AppConstants.ifrcRed),
                ),
              ),
            ),
            onTap: () {
              Navigator.of(context).pushNamed(AppRoutes.login);
            },
            showSeparator: false,
          ),
        ],
      );
    } else {
      // Logout Button for authenticated users - iPhone style (red text in card)
      return IOSGroupedList(
        margin: EdgeInsets.symmetric(horizontal: IOSSpacing.md),
        children: [
          IOSListTile(
            title: Center(
              child: Text(
                localizations.logout,
                style: IOSTextStyle.body(context).copyWith(
                  fontWeight: FontWeight.w400,
                  color: const Color(AppConstants.errorColor),
                ),
              ),
            ),
            onTap: () async {
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

            if (confirm == true && context.mounted) {
              await authProvider.logout();
              // Navigate back to main navigation (dashboard) instead of login
              // This allows users to browse as non-authenticated users
              Navigator.of(context).pushNamedAndRemoveUntil(
                AppRoutes.dashboard,
                (route) => false,
              );
            }
          },
          showSeparator: false,
        ),
      ],
      );
    }
  }

  /// Shows a color picker dialog
  void _showColorPicker(
      BuildContext context, AuthProvider authProvider, user) async {
    final localizations = AppLocalizations.of(context)!;

    // Available profile colors (matching backend PROFILE_COLORS)
    final availableColors = [
      {'color': '#3B82F6', 'name': 'Blue'},
      {'color': '#EF4444', 'name': 'Red'},
      {'color': '#10B981', 'name': 'Green'},
      {'color': '#F59E0B', 'name': 'Yellow'},
      {'color': '#8B5CF6', 'name': 'Purple'},
      {'color': '#F97316', 'name': 'Orange'},
      {'color': '#EC4899', 'name': 'Pink'},
      {'color': '#06B6D4', 'name': 'Cyan'},
      {'color': '#84CC16', 'name': 'Lime'},
      {'color': '#F43F5E', 'name': 'Rose'},
      {'color': '#6366F1', 'name': 'Indigo'},
      {'color': '#14B8A6', 'name': 'Teal'},
      {'color': '#FBBF24', 'name': 'Amber'},
      {'color': '#A855F7', 'name': 'Violet'},
      {'color': '#E11D48', 'name': 'Rose Red'},
      {'color': '#0EA5E9', 'name': 'Sky Blue'},
      {'color': '#22C55E', 'name': 'Emerald'},
    ];

    // Remove duplicates while preserving order
    final uniqueColors = <String, Map<String, String>>{};
    for (final colorData in availableColors) {
      if (!uniqueColors.containsKey(colorData['color'])) {
        uniqueColors[colorData['color']!] = colorData;
      }
    }
    final colorsList = uniqueColors.values.toList();

    // Parse current color
    Color? parseColor(String? colorString) {
      if (colorString == null || colorString.isEmpty) return null;
      try {
        final cleanColor = colorString.replaceFirst('#', '0xFF');
        return Color(int.parse(cleanColor));
      } catch (e) {
        return null;
      }
    }

    final currentColor = user.profileColor ?? '#3B82F6';
    final currentColorObj = parseColor(currentColor) ?? const Color(0xFF3B82F6);

    final selectedColor = await showDialog<String>(
      context: context,
      builder: (context) => AlertDialog(
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(AppConstants.radiusLarge),
        ),
        title: Text(
          localizations.profileColor,
          style: IOSTextStyle.title3(context).copyWith(
            fontWeight: FontWeight.bold,
          ),
        ),
        content: SizedBox(
          width: double.maxFinite,
          child: SingleChildScrollView(
            child: Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  localizations.selectColor,
                  style: IOSTextStyle.subheadline(context).copyWith(
                    color: context.textSecondaryColor,
                  ),
                ),
                SizedBox(height: IOSSpacing.md),
                // Color grid
                GridView.builder(
                  shrinkWrap: true,
                  physics: const NeverScrollableScrollPhysics(),
                  gridDelegate: const SliverGridDelegateWithFixedCrossAxisCount(
                    crossAxisCount: 5,
                    crossAxisSpacing: IOSSpacing.md - 4,
                    mainAxisSpacing: IOSSpacing.md - 4,
                    childAspectRatio: 1.0,
                  ),
                  itemCount: colorsList.length,
                  itemBuilder: (context, index) {
                    final colorData = colorsList[index];
                    final colorHex = colorData['color']!;
                    final colorName = colorData['name']!;
                    final colorObj =
                        parseColor(colorHex) ?? const Color(0xFF3B82F6);
                    final isSelected = colorHex == currentColor;

                    return GestureDetector(
                      onTap: () {
                        Navigator.of(context).pop(colorHex);
                      },
                      child: Container(
                        decoration: BoxDecoration(
                          color: colorObj,
                          shape: BoxShape.circle,
                          border: Border.all(
                            color: isSelected
                                ? Color(AppConstants.ifrcRed)
                                : context.borderColor,
                            width: isSelected ? 3 : 2,
                          ),
                          boxShadow: isSelected
                              ? [
                                  BoxShadow(
                                    color: colorObj.withOpacity(0.4),
                                    blurRadius: 8,
                                    spreadRadius: 2,
                                  ),
                                ]
                              : null,
                        ),
                        child: isSelected
                            ? Center(
                                child: Icon(
                                  Icons.check,
                                  color:
                                      Theme.of(context).colorScheme.onPrimary,
                                  size: 20,
                                ),
                              )
                            : null,
                      ),
                    );
                  },
                ),
                SizedBox(height: IOSSpacing.md),
                // Current color display
                Container(
                  padding: EdgeInsets.all(IOSSpacing.md - 4),
                  decoration: BoxDecoration(
                    color: context.subtleSurfaceColor,
                    borderRadius:
                        BorderRadius.circular(AppConstants.radiusMedium),
                    border: Border.all(
                      color: context.borderColor,
                    ),
                  ),
                  child: Row(
                    children: [
                      Container(
                        width: 32,
                        height: 32,
                        decoration: BoxDecoration(
                          color: currentColorObj,
                          shape: BoxShape.circle,
                          border: Border.all(
                            color: context.borderColor,
                            width: 2,
                          ),
                        ),
                      ),
                      SizedBox(width: IOSSpacing.md - 4),
                      Expanded(
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Text(
                              localizations.currentColor,
                              style: IOSTextStyle.caption1(context).copyWith(
                                color: context.textSecondaryColor,
                              ),
                            ),
                            SizedBox(height: IOSSpacing.xs / 2),
                            Text(
                              currentColor,
                              style: IOSTextStyle.subheadline(context).copyWith(
                                fontWeight: FontWeight.w600,
                                color: context.textColor,
                              ),
                            ),
                          ],
                        ),
                      ),
                    ],
                  ),
                ),
              ],
            ),
          ),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(context).pop(),
            child: Text(localizations.cancel),
          ),
        ],
      ),
    );

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

  /// Shows a change password dialog
  void _showChangePasswordDialog(
      BuildContext context, AuthProvider authProvider) {
    final localizations = AppLocalizations.of(context)!;
    final theme = Theme.of(context);

    final currentPasswordController = TextEditingController();
    final newPasswordController = TextEditingController();
    final confirmPasswordController = TextEditingController();

    final formKey = GlobalKey<FormState>();
    bool _obscureCurrentPassword = true;
    bool _obscureNewPassword = true;
    bool _obscureConfirmPassword = true;

    showDialog(
      context: context,
      builder: (context) => StatefulBuilder(
        builder: (context, setState) => AlertDialog(
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(AppConstants.radiusLarge),
          ),
          title: Text(
            localizations.changePassword,
            style: IOSTextStyle.title3(context).copyWith(
              fontWeight: FontWeight.bold,
            ),
          ),
          content: SizedBox(
            width: double.maxFinite,
            child: Form(
              key: formKey,
              child: SingleChildScrollView(
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    // Current Password Field
                    TextFormField(
                      controller: currentPasswordController,
                      obscureText: _obscureCurrentPassword,
                      decoration: InputDecoration(
                        labelText: localizations.currentPassword,
                        hintText: localizations.enterCurrentPassword,
                        prefixIcon: const Icon(Icons.lock_outline),
                        suffixIcon: IconButton(
                          icon: Icon(
                            _obscureCurrentPassword
                                ? Icons.visibility_outlined
                                : Icons.visibility_off_outlined,
                          ),
                          onPressed: () {
                            setState(() {
                              _obscureCurrentPassword =
                                  !_obscureCurrentPassword;
                            });
                          },
                        ),
                        border: OutlineInputBorder(
                          borderRadius:
                              BorderRadius.circular(AppConstants.radiusLarge),
                        ),
                        filled: true,
                        fillColor: theme.inputDecorationTheme.fillColor,
                      ),
                      validator: (value) {
                        if (value == null || value.isEmpty) {
                          return localizations.pleaseEnterPassword;
                        }
                        return null;
                      },
                    ),
                    SizedBox(height: IOSSpacing.md),

                    // New Password Field
                    TextFormField(
                      controller: newPasswordController,
                      obscureText: _obscureNewPassword,
                      decoration: InputDecoration(
                        labelText: localizations.newPassword,
                        hintText: localizations.enterNewPassword,
                        prefixIcon: const Icon(Icons.lock_outline),
                        suffixIcon: IconButton(
                          icon: Icon(
                            _obscureNewPassword
                                ? Icons.visibility_outlined
                                : Icons.visibility_off_outlined,
                          ),
                          onPressed: () {
                            setState(() {
                              _obscureNewPassword = !_obscureNewPassword;
                            });
                          },
                        ),
                        border: OutlineInputBorder(
                          borderRadius:
                              BorderRadius.circular(AppConstants.radiusLarge),
                        ),
                        filled: true,
                        fillColor: theme.inputDecorationTheme.fillColor,
                      ),
                      validator: (value) {
                        if (value == null || value.isEmpty) {
                          return localizations.pleaseEnterPassword;
                        }
                        if (value.length < 6) {
                          return 'Password must be at least 6 characters';
                        }
                        if (value == currentPasswordController.text) {
                          return 'New password must be different from current password';
                        }
                        return null;
                      },
                    ),
                    SizedBox(height: IOSSpacing.md),

                    // Confirm Password Field
                    TextFormField(
                      controller: confirmPasswordController,
                      obscureText: _obscureConfirmPassword,
                      decoration: InputDecoration(
                        labelText: localizations.confirmPassword,
                        hintText: localizations.confirmNewPassword,
                        prefixIcon: const Icon(Icons.lock_outline),
                        suffixIcon: IconButton(
                          icon: Icon(
                            _obscureConfirmPassword
                                ? Icons.visibility_outlined
                                : Icons.visibility_off_outlined,
                          ),
                          onPressed: () {
                            setState(() {
                              _obscureConfirmPassword =
                                  !_obscureConfirmPassword;
                            });
                          },
                        ),
                        border: OutlineInputBorder(
                          borderRadius:
                              BorderRadius.circular(AppConstants.radiusLarge),
                        ),
                        filled: true,
                        fillColor: theme.inputDecorationTheme.fillColor,
                      ),
                      validator: (value) {
                        if (value == null || value.isEmpty) {
                          return localizations.pleaseEnterPassword;
                        }
                        if (value != newPasswordController.text) {
                          return localizations.passwordsDoNotMatch;
                        }
                        return null;
                      },
                    ),
                  ],
                ),
              ),
            ),
          ),
          actions: [
            TextButton(
              onPressed: () {
                Navigator.of(context).pop();
              },
              child: Text(localizations.cancel),
            ),
            ElevatedButton(
              onPressed: () async {
                if (formKey.currentState!.validate()) {
                  // Close dialog first
                  Navigator.of(context).pop();

                  // Show loading indicator
                  showDialog(
                    context: context,
                    barrierDismissible: false,
                    builder: (context) => const Center(
                      child: CircularProgressIndicator(),
                    ),
                  );

                  // Change password
                  final error = await authProvider.changePassword(
                    currentPassword: currentPasswordController.text,
                    newPassword: newPasswordController.text,
                  );

                  if (context.mounted) {
                    Navigator.of(context).pop(); // Close loading dialog

                    if (error == null) {
                      // Success
                      ScaffoldMessenger.of(context).showSnackBar(
                        SnackBar(
                          content:
                              Text(localizations.passwordChangedSuccessfully),
                          duration: const Duration(seconds: 2),
                          backgroundColor:
                              const Color(AppConstants.successColor),
                        ),
                      );
                    } else {
                      // Error
                      ScaffoldMessenger.of(context).showSnackBar(
                        SnackBar(
                          content: Text(error),
                          duration: const Duration(seconds: 3),
                          backgroundColor: const Color(AppConstants.errorColor),
                        ),
                      );
                    }
                  }
                }
              },
              style: ElevatedButton.styleFrom(
                backgroundColor: Color(AppConstants.ifrcRed),
                foregroundColor: Theme.of(context).colorScheme.onPrimary,
                shape: RoundedRectangleBorder(
                  borderRadius:
                      BorderRadius.circular(AppConstants.radiusMedium),
                ),
              ),
              child: Text(localizations.save),
            ),
          ],
        ),
      ),
    );
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
              SizedBox(width: IOSSpacing.sm),
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
                content: Text('Theme set to $name'),
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
              SizedBox(width: IOSSpacing.sm),
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

  /// Shows a dialog to edit user name
  void _showEditNameDialog(BuildContext context, user) {
    final localizations = AppLocalizations.of(context)!;
    final theme = Theme.of(context);
    final authProvider = Provider.of<AuthProvider>(context, listen: false);

    final nameController = TextEditingController(text: user.name ?? '');
    final formKey = GlobalKey<FormState>();

    showDialog(
      context: context,
      builder: (context) => AlertDialog(
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(AppConstants.radiusLarge),
        ),
        title: Text(
          localizations.editName,
          style: IOSTextStyle.title3(context).copyWith(
            fontWeight: FontWeight.bold,
          ),
        ),
        content: SizedBox(
          width: double.maxFinite,
          child: Form(
            key: formKey,
            child: TextFormField(
              controller: nameController,
              autofocus: true,
              decoration: InputDecoration(
                labelText: localizations.name,
                hintText: localizations.enterYourName,
                prefixIcon: const Icon(Icons.person_outline),
                border: OutlineInputBorder(
                  borderRadius: BorderRadius.circular(AppConstants.radiusLarge),
                ),
                filled: true,
                fillColor: theme.inputDecorationTheme.fillColor,
              ),
              validator: (value) {
                // Name is optional, but if provided, should not be empty
                if (value != null && value.trim().isEmpty) {
                  return localizations.nameCannotBeEmpty;
                }
                return null;
              },
            ),
          ),
        ),
        actions: [
          TextButton(
            onPressed: () {
              Navigator.of(context).pop();
            },
            child: Text(localizations.cancel),
          ),
          ElevatedButton(
            onPressed: () async {
              if (formKey.currentState!.validate()) {
                final newName = nameController.text.trim();

                // Close dialog first
                Navigator.of(context).pop();

                // Show loading indicator
                if (context.mounted) {
                  showDialog(
                    context: context,
                    barrierDismissible: false,
                    builder: (context) => const Center(
                      child: CircularProgressIndicator(),
                    ),
                  );
                }

                // Update name
                final success = await authProvider.updateProfile(
                  name: newName.isEmpty ? null : newName,
                );

                if (context.mounted) {
                  Navigator.of(context).pop(); // Close loading dialog

                  ScaffoldMessenger.of(context).showSnackBar(
                    SnackBar(
                      content: Text(success
                          ? localizations.profileUpdatedSuccessfully
                          : localizations.errorUpdatingProfile),
                      backgroundColor: success
                          ? Colors.green
                          : Colors.red,
                      duration: const Duration(seconds: 2),
                    ),
                  );
                }
              }
            },
            child: Text(localizations.save),
          ),
        ],
      ),
    );
  }

  /// Shows a dialog to edit user title
  void _showEditTitleDialog(BuildContext context, user) {
    final localizations = AppLocalizations.of(context)!;
    final theme = Theme.of(context);
    final authProvider = Provider.of<AuthProvider>(context, listen: false);

    final titleController = TextEditingController(text: user.title ?? '');
    final formKey = GlobalKey<FormState>();

    showDialog(
      context: context,
      builder: (context) => AlertDialog(
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(AppConstants.radiusLarge),
        ),
        title: Text(
          localizations.editTitle,
          style: IOSTextStyle.title3(context).copyWith(
            fontWeight: FontWeight.bold,
          ),
        ),
        content: SizedBox(
          width: double.maxFinite,
          child: Form(
            key: formKey,
            child: TextFormField(
              controller: titleController,
              autofocus: true,
              decoration: InputDecoration(
                labelText: localizations.title,
                hintText: localizations.enterYourJobTitle,
                prefixIcon: const Icon(Icons.work_outline),
                border: OutlineInputBorder(
                  borderRadius: BorderRadius.circular(AppConstants.radiusLarge),
                ),
                filled: true,
                fillColor: theme.inputDecorationTheme.fillColor,
              ),
              validator: (value) {
                // Title is optional, but if provided, should not be empty
                if (value != null && value.trim().isEmpty) {
                  return localizations.titleCannotBeEmpty;
                }
                return null;
              },
            ),
          ),
        ),
        actions: [
          TextButton(
            onPressed: () {
              Navigator.of(context).pop();
            },
            child: Text(localizations.cancel),
          ),
          ElevatedButton(
            onPressed: () async {
              if (formKey.currentState!.validate()) {
                final newTitle = titleController.text.trim();

                // Close dialog first
                Navigator.of(context).pop();

                // Show loading indicator
                if (context.mounted) {
                  showDialog(
                    context: context,
                    barrierDismissible: false,
                    builder: (context) => const Center(
                      child: CircularProgressIndicator(),
                    ),
                  );
                }

                // Update title
                final success = await authProvider.updateProfile(
                  title: newTitle.isEmpty ? null : newTitle,
                );

                if (context.mounted) {
                  Navigator.of(context).pop(); // Close loading dialog

                  ScaffoldMessenger.of(context).showSnackBar(
                    SnackBar(
                      content: Text(success
                          ? localizations.profileUpdatedSuccessfully
                          : localizations.errorUpdatingProfile),
                      backgroundColor: success
                          ? Colors.green
                          : Colors.red,
                      duration: const Duration(seconds: 2),
                    ),
                  );
                }
              }
            },
            child: Text(localizations.save),
          ),
        ],
      ),
    );
  }

  /// Updates chatbot preference
  Future<void> _updateChatbotPreference(BuildContext context, bool value) async {
    final localizations = AppLocalizations.of(context)!;
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
