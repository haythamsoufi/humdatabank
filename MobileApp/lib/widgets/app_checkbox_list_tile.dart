import 'package:flutter/material.dart';
import '../utils/theme_extensions.dart';
import '../utils/constants.dart';

/// A standardized CheckboxListTile widget that ensures consistent styling
/// across all screens in the app.
class AppCheckboxListTile extends StatelessWidget {
  /// Whether this checkbox is checked
  final bool? value;

  /// Called when the user toggles the checkbox
  final ValueChanged<bool?>? onChanged;

  /// The primary text displayed in the tile
  final String title;

  /// Optional secondary text displayed below the title
  final String? subtitle;

  /// Whether the checkbox is enabled
  final bool enabled;

  /// The color to use when the checkbox is checked
  /// If null, uses theme-aware color (ifrcRed for light, blue for dark)
  final Color? activeColor;

  const AppCheckboxListTile({
    super.key,
    required this.value,
    required this.onChanged,
    required this.title,
    this.subtitle,
    this.enabled = true,
    this.activeColor,
  });

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    // Determine active color: use provided, or theme-aware default
    final Color effectiveActiveColor = activeColor ??
        (theme.brightness == Brightness.dark
            ? const Color(0xFF4A90E2)
            : Color(AppConstants.ifrcRed));

    return CheckboxListTile(
      value: value,
      onChanged: enabled ? onChanged : null,
      title: Text(
        title,
        style: TextStyle(
          fontSize: 15,
          fontWeight: FontWeight.w500,
          color: context.textColor,
        ),
      ),
      subtitle: subtitle != null
          ? Text(
              subtitle!,
              style: TextStyle(
                fontSize: 13,
                color: context.textSecondaryColor,
              ),
            )
          : null,
      activeColor: effectiveActiveColor,
      contentPadding: EdgeInsets.zero,
      dense: true,
    );
  }
}
