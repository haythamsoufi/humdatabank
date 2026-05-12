import 'package:flutter/material.dart';
import 'package:flutter/cupertino.dart' as cupertino;

import '../utils/ios_constants.dart';
import '../utils/ios_settings_style.dart';

/// Full-width label inside a rounded grouped “cell”, iOS-style tap feedback.
class IOSGroupedPlainButton extends StatelessWidget {
  const IOSGroupedPlainButton({
    super.key,
    required this.label,
    required this.textColor,
    required this.onPressed,
    this.fontWeight = FontWeight.w500,
  });

  final String label;
  final Color textColor;
  final VoidCallback? onPressed;
  final FontWeight fontWeight;

  @override
  Widget build(BuildContext context) {
    final cellBg = IOSSettingsStyle.secondaryCellBackground(context);

    return Material(
      color: Colors.transparent,
      child: Container(
        decoration: BoxDecoration(
          color: cellBg,
          borderRadius: BorderRadius.circular(IOSDimensions.borderRadiusMedium),
        ),
        clipBehavior: Clip.antiAlias,
        child: cupertino.CupertinoButton(
          padding: IOSSettingsStyle.groupedPlainButtonPadding,
          minimumSize: const Size(
            double.infinity,
            IOSSettingsStyle.groupedPlainButtonMinHeight,
          ),
          color: cellBg,
          onPressed: onPressed,
          child: Text(
            label,
            style: IOSTextStyle.body(context).copyWith(
              fontWeight: fontWeight,
              color: textColor,
            ),
          ),
        ),
      ),
    );
  }
}
