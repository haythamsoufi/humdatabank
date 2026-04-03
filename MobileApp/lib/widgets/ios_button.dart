import 'package:flutter/material.dart';
import 'package:flutter/cupertino.dart' as cupertino;
import 'package:flutter/services.dart';
import '../utils/ios_constants.dart';
import '../l10n/app_localizations.dart';

/// iOS-style filled button with accessibility support
class IOSFilledButton extends StatelessWidget {
  final Widget child;
  final VoidCallback? onPressed;
  final String? semanticLabel;
  final String? semanticHint;
  final Color? color;
  final EdgeInsetsGeometry? padding;
  final double? borderRadius;
  final bool disabled;

  const IOSFilledButton({
    super.key,
    required this.child,
    this.onPressed,
    this.semanticLabel,
    this.semanticHint,
    this.color,
    this.padding,
    this.borderRadius,
    this.disabled = false,
  });

  @override
  Widget build(BuildContext context) {
    final localizations = AppLocalizations.of(context);
    final effectiveOnPressed = disabled ? null : onPressed;

    final buttonColor = color ?? IOSColors.getSystemBlue(context);
    final disabledButtonColor = color?.withOpacity(0.3) ??
        IOSColors.getSystemBlue(context).withOpacity(0.3);

    return Semantics(
      label: semanticLabel,
      hint: semanticHint,
      button: true,
      enabled: effectiveOnPressed != null,
      child: cupertino.CupertinoButton(
        onPressed: effectiveOnPressed != null
            ? () {
                HapticFeedback.mediumImpact();
                effectiveOnPressed!();
              }
            : null,
        padding: EdgeInsets.zero,
        borderRadius: BorderRadius.circular(borderRadius ?? 10),
        child: Container(
          padding: padding ??
              const EdgeInsets.symmetric(
                horizontal: IOSSpacing.xxl,
                vertical: IOSSpacing.md,
              ),
          decoration: BoxDecoration(
            color: effectiveOnPressed != null
                ? buttonColor
                : disabledButtonColor,
            borderRadius: BorderRadius.circular(borderRadius ?? 10),
          ),
          child: child,
        ),
      ),
    );
  }
}

/// iOS-style outlined button with accessibility support
class IOSOutlinedButton extends StatelessWidget {
  final Widget child;
  final VoidCallback? onPressed;
  final String? semanticLabel;
  final String? semanticHint;
  final Color? color;
  final EdgeInsetsGeometry? padding;
  final double? borderRadius;
  final bool disabled;

  const IOSOutlinedButton({
    super.key,
    required this.child,
    this.onPressed,
    this.semanticLabel,
    this.semanticHint,
    this.color,
    this.padding,
    this.borderRadius,
    this.disabled = false,
  });

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final textTheme = theme.textTheme;
    final effectiveOnPressed = disabled ? null : onPressed;
    final buttonColor = color ?? IOSColors.getSystemBlue(context);

    return Semantics(
      label: semanticLabel,
      hint: semanticHint,
      button: true,
      enabled: effectiveOnPressed != null,
      child: cupertino.CupertinoButton(
        onPressed: effectiveOnPressed != null
            ? () {
                HapticFeedback.lightImpact();
                effectiveOnPressed!();
              }
            : null,
        padding: padding ??
            const EdgeInsets.symmetric(
              horizontal: IOSSpacing.xxl,
              vertical: IOSSpacing.md,
            ),
        borderRadius: BorderRadius.circular(borderRadius ?? 10),
        color: Colors.transparent,
        disabledColor: Colors.transparent,
        child: Container(
          decoration: BoxDecoration(
            border: Border.all(
              color: effectiveOnPressed != null
                  ? buttonColor
                  : buttonColor.withOpacity(0.3),
              width: 1.5,
            ),
            borderRadius: BorderRadius.circular(borderRadius ?? 10),
          ),
          padding: padding ??
              const EdgeInsets.symmetric(
                horizontal: IOSSpacing.xxl,
                vertical: IOSSpacing.md,
              ),
          child: DefaultTextStyle(
            style: (textTheme.labelLarge ?? const TextStyle()).copyWith(
              color: effectiveOnPressed != null
                  ? buttonColor
                  : buttonColor.withOpacity(0.3),
              fontWeight: FontWeight.w600,
              letterSpacing: -0.2,
            ),
            child: child,
          ),
        ),
      ),
    );
  }
}

/// iOS-style icon button with accessibility support
class IOSIconButton extends StatelessWidget {
  final IconData icon;
  final VoidCallback? onPressed;
  final String? semanticLabel;
  final String? semanticHint;
  final Color? color;
  final double? iconSize;
  final String? tooltip;

  const IOSIconButton({
    super.key,
    required this.icon,
    this.onPressed,
    this.semanticLabel,
    this.semanticHint,
    this.tooltip,
    this.color,
    this.iconSize,
  });

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final iconColor = color ?? theme.iconTheme.color ?? theme.colorScheme.onSurface;

    Widget button = Semantics(
      label: semanticLabel ?? tooltip,
      hint: semanticHint,
      button: true,
      enabled: onPressed != null,
      child: cupertino.CupertinoButton(
        onPressed: onPressed != null
            ? () {
                HapticFeedback.lightImpact();
                onPressed!();
              }
            : null,
        padding: EdgeInsets.zero,
        minSize: 0,
        color: Colors.transparent,
        child: Icon(
          icon,
          size: iconSize ?? 24,
          color: onPressed != null ? iconColor : iconColor.withOpacity(0.3),
        ),
      ),
    );

    if (tooltip != null) {
      return Tooltip(
        message: tooltip!,
        child: button,
      );
    }

    return button;
  }
}
