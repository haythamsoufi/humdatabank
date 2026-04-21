import 'package:flutter/material.dart';

import '../l10n/app_localizations.dart';
import '../utils/constants.dart';
import '../utils/ios_constants.dart';
import '../utils/theme_extensions.dart';

/// Backend `PROFILE_COLORS` palette — keep in sync with [SettingsScreen] / backoffice.
const List<Map<String, String>> kProfileColorChoices = [
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

bool _hexEquals(String a, String b) {
  var na = a.trim();
  var nb = b.trim();
  if (!na.startsWith('#')) na = '#$na';
  if (!nb.startsWith('#')) nb = '#$nb';
  return na.toUpperCase() == nb.toUpperCase();
}

Color? _parseHexColor(String? colorString) {
  if (colorString == null || colorString.isEmpty) return null;
  try {
    final cleanColor = colorString.replaceFirst('#', '0xFF');
    return Color(int.parse(cleanColor));
  } catch (_) {
    return null;
  }
}

/// Grid dialog to pick a profile accent hex (`#RRGGBB`). Returns `null` if cancelled.
Future<String?> showProfileColorPickerDialog(
  BuildContext context,
  String currentHex,
) async {
  final localizations = AppLocalizations.of(context)!;

  final uniqueColors = <String, Map<String, String>>{};
  for (final colorData in kProfileColorChoices) {
    final c = colorData['color']!;
    uniqueColors.putIfAbsent(c, () => colorData);
  }
  final colorsList = uniqueColors.values.toList();

  final current = currentHex.trim().isEmpty ? '#3B82F6' : currentHex.trim();
  final currentColorObj =
      _parseHexColor(current) ?? const Color(AppConstants.semanticDefaultProfileAccent);

  return showDialog<String>(
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
              const SizedBox(height: IOSSpacing.md),
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
                  final colorObj =
                      _parseHexColor(colorHex) ?? const Color(AppConstants.semanticDefaultProfileAccent);
                  final isSelected = _hexEquals(colorHex, current);

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
                                  color: colorObj.withValues(alpha: 0.4),
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
                                color: Theme.of(context).colorScheme.onPrimary,
                                size: 20,
                              ),
                            )
                          : null,
                    ),
                  );
                },
              ),
              const SizedBox(height: IOSSpacing.md),
              Container(
                padding: const EdgeInsets.all(IOSSpacing.md - 4),
                decoration: BoxDecoration(
                  color: context.subtleSurfaceColor,
                  borderRadius: BorderRadius.circular(AppConstants.radiusMedium),
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
                    const SizedBox(width: IOSSpacing.md - 4),
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
                          const SizedBox(height: IOSSpacing.xs / 2),
                          Text(
                            current.startsWith('#') ? current : '#$current',
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
}
