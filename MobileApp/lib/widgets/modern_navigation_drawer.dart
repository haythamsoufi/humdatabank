import 'package:flutter/material.dart';
import '../models/shared/user.dart';
import '../utils/avatar_initials.dart';
import 'profile_leading_avatar.dart';
import '../utils/constants.dart';
import '../utils/theme_extensions.dart';
import '../utils/ios_constants.dart';

/// Drawer panel flush with the scaffold edge (no corner rounding).
ShapeBorder modernDrawerShape() {
  return const RoundedRectangleBorder();
}

/// Top block: title + optional signed-in user row.
class ModernDrawerHeader extends StatelessWidget {
  const ModernDrawerHeader({
    super.key,
    required this.title,
    this.user,
    this.onProfileTap,
    this.profileTapSemanticLabel,
  });

  final String title;
  final User? user;

  /// When set (typically with a signed-in [user]), the profile row is tappable.
  final VoidCallback? onProfileTap;

  /// Accessibility label for [onProfileTap] (e.g. localized "Settings").
  final String? profileTapSemanticLabel;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final cs = theme.colorScheme;

    return DecoratedBox(
      decoration: BoxDecoration(
        gradient: LinearGradient(
          begin: Alignment.topCenter,
          end: Alignment.bottomCenter,
          colors: [
            cs.surface,
            Color.alphaBlend(
              cs.primary.withValues(alpha: theme.isDarkTheme ? 0.06 : 0.04),
              cs.surface,
            ),
          ],
        ),
      ),
      child: Padding(
        padding: const EdgeInsets.fromLTRB(
          IOSSpacing.lg,
          IOSSpacing.md + 4,
          IOSSpacing.lg,
          IOSSpacing.md,
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              title,
              style:
                  theme.textTheme.headlineSmall?.copyWith(
                    fontWeight: FontWeight.w700,
                    letterSpacing: -0.5,
                    color: cs.onSurface,
                  ) ??
                  IOSTextStyle.title2(context),
            ),
            const SizedBox(height: IOSSpacing.sm),
            Row(
              children: [
                Container(
                  width: 40,
                  height: 3,
                  decoration: BoxDecoration(
                    color: Color(AppConstants.ifrcRed),
                    borderRadius: BorderRadius.circular(2),
                  ),
                ),
                Expanded(
                  child: Padding(
                    padding: const EdgeInsets.only(left: IOSSpacing.sm),
                    child: Divider(
                      height: 1,
                      thickness: 1,
                      color: cs.outlineVariant.withValues(alpha: 0.45),
                    ),
                  ),
                ),
              ],
            ),
            if (user != null) ...[
              const SizedBox(height: IOSSpacing.md),
              Builder(
                builder: (context) {
                  final u = user!;
                  final profileRow = Row(
                    children: [
                      ProfileLeadingAvatar(
                        initials: avatarInitialsForUser(u),
                        profileColorHex: u.profileColor,
                        size: 44,
                      ),
                      const SizedBox(width: IOSSpacing.md),
                      Expanded(
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Text(
                              u.displayName,
                              maxLines: 1,
                              overflow: TextOverflow.ellipsis,
                              style: theme.textTheme.titleSmall?.copyWith(
                                fontWeight: FontWeight.w600,
                              ),
                            ),
                            if (u.title != null && u.title!.isNotEmpty)
                              Text(
                                u.title!,
                                maxLines: 1,
                                overflow: TextOverflow.ellipsis,
                                style: theme.textTheme.bodySmall?.copyWith(
                                  color: theme.isDarkTheme
                                      ? Colors.white.withValues(alpha: 0.65)
                                      : cs.onSurfaceVariant,
                                ),
                              ),
                          ],
                        ),
                      ),
                    ],
                  );

                  final tappable = onProfileTap != null;
                  Widget child = profileRow;
                  if (tappable) {
                    child = Material(
                      color: Colors.transparent,
                      child: InkWell(
                        onTap: onProfileTap,
                        borderRadius: BorderRadius.circular(
                          AppConstants.radiusLarge,
                        ),
                        splashColor: cs.primary.withValues(alpha: 0.12),
                        highlightColor: cs.primary.withValues(alpha: 0.06),
                        child: Padding(
                          padding: const EdgeInsets.symmetric(vertical: 4),
                          child: profileRow,
                        ),
                      ),
                    );
                  }

                  return Semantics(
                    button: tappable,
                    label: tappable ? profileTapSemanticLabel : null,
                    child: child,
                  );
                },
              ),
            ],
          ],
        ),
      ),
    );
  }
}

class ModernDrawerSectionTitle extends StatelessWidget {
  const ModernDrawerSectionTitle({super.key, required this.label});

  final String label;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final cs = theme.colorScheme;
    return Padding(
      padding: const EdgeInsets.fromLTRB(
        IOSSpacing.lg,
        IOSSpacing.lg + 4,
        IOSSpacing.lg,
        IOSSpacing.sm,
      ),
      child: Row(
        children: [
          Container(
            width: 3,
            height: 14,
            decoration: BoxDecoration(
              color: cs.primary.withValues(alpha: 0.85),
              borderRadius: BorderRadius.circular(2),
            ),
          ),
          const SizedBox(width: IOSSpacing.sm),
          Expanded(
            child: Text(
              label,
              style:
                  theme.textTheme.labelLarge?.copyWith(
                    fontWeight: FontWeight.w600,
                    letterSpacing: 1.15,
                    color: cs.onSurfaceVariant,
                  ) ??
                  IOSTextStyle.footnote(context).copyWith(
                    fontWeight: FontWeight.w600,
                    letterSpacing: 0.5,
                    color: cs.onSurfaceVariant,
                  ),
            ),
          ),
        ],
      ),
    );
  }
}

/// One navigation row: coloured icon, label, chevron.
class ModernDrawerTile extends StatelessWidget {
  const ModernDrawerTile({
    super.key,
    required this.icon,
    required this.title,
    required this.onTap,
    this.showChevron = true,
    this.iconColor,
    this.selected = false,
  });

  final IconData icon;
  final String title;
  final VoidCallback onTap;
  final bool showChevron;
  final Color? iconColor;

  /// Highlights the row when it matches the current screen (e.g. Home).
  final bool selected;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final cs = theme.colorScheme;
    final iconTint = iconColor ??
        (selected ? cs.primary : cs.primary.withValues(alpha: 0.88));
    final rowFill = selected
        ? cs.primary.withValues(alpha: theme.isDarkTheme ? 0.14 : 0.08)
        : Colors.transparent;
    final titleStyle =
        (theme.textTheme.titleSmall ?? IOSTextStyle.body(context)).copyWith(
          fontWeight: selected ? FontWeight.w600 : FontWeight.w500,
          color: selected ? cs.onSurface : null,
        );

    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 2),
      child: Material(
        color: rowFill,
        borderRadius: BorderRadius.circular(AppConstants.radiusLarge),
        clipBehavior: Clip.antiAlias,
        child: InkWell(
          onTap: onTap,
          borderRadius: BorderRadius.circular(AppConstants.radiusLarge),
          splashColor: cs.primary.withValues(alpha: 0.12),
          highlightColor: cs.primary.withValues(alpha: 0.06),
          child: Padding(
            padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 10),
            child: Row(
              children: [
                SizedBox(
                  width: 40,
                  height: 40,
                  child: Icon(icon, color: iconTint, size: 24),
                ),
                const SizedBox(width: 14),
                Expanded(
                  child: Text(
                    title,
                    maxLines: 2,
                    overflow: TextOverflow.ellipsis,
                    style: titleStyle,
                  ),
                ),
                if (showChevron)
                  Icon(
                    Icons.chevron_right_rounded,
                    color: selected
                        ? cs.primary.withValues(alpha: 0.65)
                        : cs.onSurfaceVariant.withValues(alpha: 0.45),
                    size: 22,
                  ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}
