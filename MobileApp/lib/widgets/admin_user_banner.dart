import 'package:flutter/material.dart';
import '../config/routes.dart';
import '../l10n/app_localizations.dart';
import '../models/shared/user.dart';
import '../utils/accessibility_helper.dart';
import '../utils/avatar_initials.dart';
import 'profile_leading_avatar.dart';
import '../utils/constants.dart';
import '../utils/ios_constants.dart';
import '../utils/theme_extensions.dart';

/// Profile-style gradient banner (admin hub / dashboard). Uses [AccessibilityHelper.bannerHeroForeground]
/// so saturated brand colors get light text; pale pastels get dark text. Avatar ring stays a light halo,
/// not [getAccessibleTextColor] black on orange.
class AdminUserBanner extends StatelessWidget {
  final User? user;

  const AdminUserBanner({super.key, required this.user});

  @override
  Widget build(BuildContext context) {
    final localizations = AppLocalizations.of(context)!;
    final displayName = user?.displayName ?? '';
    final email = user?.email ?? '';
    final title = user?.title;
    final role = user?.role ?? '';

    Color profileColor = Color(AppConstants.ifrcNavy);
    final profileColorHex = user?.profileColor;
    if (profileColorHex != null && profileColorHex.isNotEmpty) {
      try {
        final cleanColor = profileColorHex.replaceFirst('#', '0xFF');
        profileColor = Color(int.parse(cleanColor));
      } catch (_) {
        profileColor = Color(AppConstants.ifrcNavy);
      }
    }

    final primaryColor = profileColor;
    final secondaryColor = primaryColor.withValues(alpha: 0.7);
    final accentColor = primaryColor.withValues(alpha: 0.3);
    final onBanner = AccessibilityHelper.bannerHeroForeground(primaryColor);

    final isSystemManager = (user?.role ?? '').toLowerCase() == 'system_manager';
    final scheme = Theme.of(context).colorScheme;
    final Color roleBadgeBg;
    final Color roleBadgeBorder;
    final Color roleBadgeIconFg;
    final Color roleBadgeTextFg;
    if (isSystemManager) {
      if (Theme.of(context).brightness == Brightness.dark) {
        roleBadgeBg = Color.alphaBlend(
          Colors.black.withValues(alpha: 0.52),
          scheme.surfaceContainerHighest,
        );
        roleBadgeBorder = Colors.white.withValues(alpha: 0.2);
        roleBadgeIconFg = Colors.grey.shade100;
        roleBadgeTextFg = Colors.grey.shade100;
      } else {
        roleBadgeBg = Colors.black87;
        roleBadgeBorder = Colors.white.withValues(alpha: 0.22);
        roleBadgeIconFg = Colors.white;
        roleBadgeTextFg = Colors.white;
      }
    } else {
      roleBadgeBg = onBanner.withValues(alpha: 0.2);
      roleBadgeBorder = onBanner.withValues(alpha: 0.35);
      roleBadgeIconFg = onBanner.withValues(alpha: 0.95);
      roleBadgeTextFg = onBanner.withValues(alpha: 0.98);
    }
    final lightForeground = onBanner.computeLuminance() > 0.5;

    final splash = lightForeground
        ? Colors.white.withValues(alpha: 0.22)
        : Colors.black.withValues(alpha: 0.1);
    final highlight = lightForeground
        ? Colors.white.withValues(alpha: 0.12)
        : Colors.black.withValues(alpha: 0.06);
    final decoStrong =
        lightForeground ? Colors.white.withValues(alpha: 0.12) : Colors.black.withValues(alpha: 0.08);
    final decoSoft =
        lightForeground ? Colors.white.withValues(alpha: 0.09) : Colors.black.withValues(alpha: 0.06);

    final initials = avatarInitialsForProfile(
      name: user?.name,
      email: user?.email ?? '',
    );

    String getRoleDisplayName(String r) {
      switch (r.toLowerCase()) {
        case 'admin':
          return localizations.adminRole;
        case 'system_manager':
          return localizations.systemManagerRole;
        case 'focal_point':
          return localizations.focalPointRole;
        case 'viewer':
          return localizations.viewerRole;
        default:
          return r
              .split('_')
              .map((word) =>
                  word.isEmpty ? '' : word[0].toUpperCase() + word.substring(1))
              .join(' ');
      }
    }

    final avatarRing = Colors.white.withValues(alpha: 0.92);

    return Container(
      margin: const EdgeInsets.only(bottom: IOSSpacing.sm),
      decoration: BoxDecoration(
        gradient: LinearGradient(
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
          colors: [
            primaryColor,
            secondaryColor,
            accentColor,
          ],
        ),
        boxShadow: [
          BoxShadow(
            color: primaryColor.withValues(alpha: 0.4),
            blurRadius: 20,
            spreadRadius: 2,
            offset: const Offset(0, 8),
          ),
          BoxShadow(
            color: Theme.of(context).ambientShadow(
                lightOpacity: 0.1, darkOpacity: 0.4),
            blurRadius: 10,
            spreadRadius: 0,
            offset: const Offset(0, 4),
          ),
        ],
      ),
      child: Material(
        color: Colors.transparent,
        child: InkWell(
          onTap: () {
            Navigator.of(context).pushNamed(AppRoutes.settings);
          },
          splashColor: splash,
          highlightColor: highlight,
          child: Stack(
            children: [
              Positioned(
                right: -30,
                top: -30,
                child: Container(
                  width: 120,
                  height: 120,
                  decoration: BoxDecoration(
                    shape: BoxShape.circle,
                    color: decoStrong,
                  ),
                ),
              ),
              Positioned(
                right: -50,
                bottom: -40,
                child: Container(
                  width: 100,
                  height: 100,
                  decoration: BoxDecoration(
                    shape: BoxShape.circle,
                    color: decoSoft,
                  ),
                ),
              ),
              Padding(
                padding: const EdgeInsets.all(IOSSpacing.lg),
                child: Row(
                  children: [
                    Container(
                      width: 72,
                      height: 72,
                      decoration: BoxDecoration(
                        shape: BoxShape.circle,
                        color: avatarRing,
                        boxShadow: [
                          BoxShadow(
                            color: Theme.of(context).ambientShadow(
                                lightOpacity: 0.2, darkOpacity: 0.5),
                            blurRadius: 12,
                            spreadRadius: 2,
                            offset: const Offset(0, 4),
                          ),
                        ],
                      ),
                      child: Padding(
                        padding: const EdgeInsets.all(2),
                        child: ProfileLeadingAvatar(
                          initials: initials,
                          backgroundColor: primaryColor,
                          size: 68,
                          useGradient: true,
                          fillSlot: true,
                          initialsColor: onBanner,
                        ),
                      ),
                    ),
                    const SizedBox(width: IOSSpacing.md),
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        mainAxisSize: MainAxisSize.min,
                        children: [
                          Text(
                            displayName.isNotEmpty ? displayName : email,
                            style: IOSTextStyle.title3(context).copyWith(
                              fontWeight: FontWeight.bold,
                              color: onBanner,
                              shadows: [
                                Shadow(
                                  color: Theme.of(context).ambientShadow(
                                      lightOpacity: 0.26, darkOpacity: 0.6),
                                  blurRadius: 4,
                                ),
                              ],
                            ),
                            maxLines: 1,
                            overflow: TextOverflow.ellipsis,
                          ),
                          if (title != null && title.isNotEmpty) ...[
                            const SizedBox(height: IOSSpacing.xs + 2),
                            Container(
                              padding: const EdgeInsets.symmetric(
                                horizontal: IOSSpacing.sm + 2,
                                vertical: IOSSpacing.xs,
                              ),
                              decoration: BoxDecoration(
                                color: onBanner.withValues(alpha: 0.2),
                                borderRadius: BorderRadius.circular(12),
                                border: Border.all(
                                  color: onBanner.withValues(alpha: 0.35),
                                  width: 1,
                                ),
                              ),
                              child: Row(
                                mainAxisSize: MainAxisSize.min,
                                children: [
                                  Icon(
                                    Icons.work_outline,
                                    size: 14,
                                    color: onBanner.withValues(alpha: 0.95),
                                  ),
                                  const SizedBox(width: IOSSpacing.xs + 2),
                                  Flexible(
                                    child: Text(
                                      title,
                                      style: IOSTextStyle.caption1(context).copyWith(
                                        fontWeight: FontWeight.w600,
                                        color: onBanner.withValues(alpha: 0.98),
                                      ),
                                      maxLines: 1,
                                      overflow: TextOverflow.ellipsis,
                                    ),
                                  ),
                                ],
                              ),
                            ),
                          ],
                          const SizedBox(height: IOSSpacing.sm),
                          Container(
                            padding: const EdgeInsets.symmetric(
                              horizontal: IOSSpacing.sm + 2,
                              vertical: IOSSpacing.xs + 1,
                            ),
                            decoration: BoxDecoration(
                              color: roleBadgeBg,
                              borderRadius: BorderRadius.circular(12),
                              border: Border.all(
                                color: roleBadgeBorder,
                                width: 1,
                              ),
                            ),
                            child: Row(
                              mainAxisSize: MainAxisSize.min,
                              children: [
                                Icon(
                                  Icons.verified_user_outlined,
                                  size: 14,
                                  color: roleBadgeIconFg,
                                ),
                                const SizedBox(width: IOSSpacing.xs + 2),
                                Text(
                                  getRoleDisplayName(role),
                                  style: IOSTextStyle.caption2(context).copyWith(
                                    fontWeight: FontWeight.w600,
                                    color: roleBadgeTextFg,
                                  ),
                                ),
                              ],
                            ),
                          ),
                        ],
                      ),
                    ),
                    Material(
                      color: Colors.transparent,
                      child: InkWell(
                        onTap: () {
                          Navigator.of(context).pushNamed(AppRoutes.settings);
                        },
                        customBorder: const CircleBorder(),
                        splashColor: splash,
                        highlightColor: highlight,
                        child: Container(
                          padding: const EdgeInsets.all(IOSSpacing.sm),
                          decoration: BoxDecoration(
                            color: onBanner.withValues(alpha: 0.18),
                            shape: BoxShape.circle,
                            border: Border.all(
                              color: onBanner.withValues(alpha: 0.32),
                              width: 1,
                            ),
                          ),
                          child: Icon(
                            Icons.settings_outlined,
                            color: onBanner,
                            size: 20,
                          ),
                        ),
                      ),
                    ),
                  ],
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
