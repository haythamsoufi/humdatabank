import 'package:flutter/material.dart';
import '../utils/theme_extensions.dart';
import '../utils/constants.dart';

/// A standardized SwitchListTile widget that ensures consistent styling
/// across all screens in the app.
class AppSwitchListTile extends StatelessWidget {
  /// Whether this switch is checked
  final bool value;

  /// Called when the user toggles the switch
  final ValueChanged<bool>? onChanged;

  /// The primary text displayed in the tile
  final String title;

  /// Optional secondary text displayed below the title
  final String? subtitle;

  /// Whether the switch is enabled
  final bool enabled;

  /// Optional icon to display on the leading side
  final IconData? icon;

  /// Optional content padding. If null, uses EdgeInsets.zero (for notification preferences style)
  /// or EdgeInsets.symmetric(horizontal: 16, vertical: 8) when icon is provided (for settings style)
  final EdgeInsetsGeometry? contentPadding;

  const AppSwitchListTile({
    super.key,
    required this.value,
    required this.onChanged,
    required this.title,
    this.subtitle,
    this.enabled = true,
    this.icon,
    this.contentPadding,
  });

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final textTheme = theme.textTheme;

    // Default padding: if icon is provided, match settings screen style
    // Otherwise, use zero padding for notification preferences style
    final EdgeInsetsGeometry effectivePadding = contentPadding ??
        (icon != null
            ? const EdgeInsets.symmetric(horizontal: 16, vertical: 8)
            : EdgeInsets.zero);

    return Semantics(
      label: subtitle != null ? '$title, $subtitle' : title,
      value: value ? 'On' : 'Off',
      toggled: value,
      enabled: enabled,
      child: SwitchListTile(
        value: value,
        onChanged: enabled ? onChanged : null,
        secondary: icon != null
            ? Icon(
                icon,
                color: theme.colorScheme.onSurface,
                size: IconTheme.of(context).size ?? 22,
              )
            : null,
        title: Text(
          title,
          style: (textTheme.titleMedium ?? const TextStyle()).copyWith(
            fontWeight: FontWeight.w500,
            color: context.textColor,
          ),
        ),
        subtitle: subtitle != null
            ? Text(
                subtitle!,
                style: (textTheme.bodySmall ?? const TextStyle()).copyWith(
                  color: context.textSecondaryColor,
                ),
              )
            : null,
        thumbColor: WidgetStateProperty.resolveWith((states) {
          if (states.contains(WidgetState.selected)) {
            return theme.isDarkTheme
                ? const Color(AppConstants.themeSwitchCheckboxActiveDark)
                : theme.colorScheme.primary;
          }
          return null;
        }),
        contentPadding: effectivePadding,
        dense: true,
      ),
    );
  }
}
