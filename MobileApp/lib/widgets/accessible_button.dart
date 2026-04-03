import 'package:flutter/material.dart';
import '../l10n/app_localizations.dart';

/// Wrapper for buttons with built-in accessibility support
class AccessibleButton extends StatelessWidget {
  final Widget child;
  final VoidCallback? onPressed;
  final String? semanticLabel;
  final String? semanticHint;
  final bool isButton;
  final ButtonStyle? style;

  const AccessibleButton({
    super.key,
    required this.child,
    this.onPressed,
    this.semanticLabel,
    this.semanticHint,
    this.isButton = true,
    this.style,
  });

  @override
  Widget build(BuildContext context) {
    final localizations = AppLocalizations.of(context);

    return Semantics(
      label: semanticLabel,
      hint: semanticHint,
      button: isButton,
      enabled: onPressed != null,
      child: ElevatedButton(
        onPressed: onPressed,
        style: style,
        child: child,
      ),
    );
  }
}

/// Wrapper for text buttons with accessibility
class AccessibleTextButton extends StatelessWidget {
  final Widget child;
  final VoidCallback? onPressed;
  final String? semanticLabel;
  final String? semanticHint;
  final ButtonStyle? style;

  const AccessibleTextButton({
    super.key,
    required this.child,
    this.onPressed,
    this.semanticLabel,
    this.semanticHint,
    this.style,
  });

  @override
  Widget build(BuildContext context) {
    return Semantics(
      label: semanticLabel,
      hint: semanticHint,
      button: true,
      enabled: onPressed != null,
      child: TextButton(
        onPressed: onPressed,
        style: style,
        child: child,
      ),
    );
  }
}

/// Wrapper for filled buttons with accessibility
class AccessibleFilledButton extends StatelessWidget {
  final Widget child;
  final VoidCallback? onPressed;
  final String? semanticLabel;
  final String? semanticHint;
  final ButtonStyle? style;

  const AccessibleFilledButton({
    super.key,
    required this.child,
    this.onPressed,
    this.semanticLabel,
    this.semanticHint,
    this.style,
  });

  @override
  Widget build(BuildContext context) {
    return Semantics(
      label: semanticLabel,
      hint: semanticHint,
      button: true,
      enabled: onPressed != null,
      child: FilledButton(
        onPressed: onPressed,
        style: style,
        child: child,
      ),
    );
  }
}

/// Wrapper for icon buttons with accessibility
class AccessibleIconButton extends StatelessWidget {
  final Icon icon;
  final VoidCallback? onPressed;
  final String? semanticLabel;
  final String? semanticHint;
  final Color? color;
  final double? iconSize;

  const AccessibleIconButton({
    super.key,
    required this.icon,
    this.onPressed,
    this.semanticLabel,
    this.semanticHint,
    this.color,
    this.iconSize,
  });

  @override
  Widget build(BuildContext context) {
    return Semantics(
      label: semanticLabel ?? icon.semanticLabel,
      hint: semanticHint,
      button: true,
      enabled: onPressed != null,
      child: IconButton(
        icon: icon,
        onPressed: onPressed,
        color: color,
        iconSize: iconSize,
      ),
    );
  }
}

/// Wrapper for text fields with accessibility
class AccessibleTextField extends StatelessWidget {
  final TextEditingController? controller;
  final String? labelText;
  final String? hintText;
  final String? semanticLabel;
  final String? semanticHint;
  final TextInputType? keyboardType;
  final bool obscureText;
  final String? Function(String?)? validator;
  final InputDecoration? decoration;
  final void Function(String)? onChanged;
  final TextInputAction? textInputAction;
  final void Function(String)? onFieldSubmitted;

  const AccessibleTextField({
    super.key,
    this.controller,
    this.labelText,
    this.hintText,
    this.semanticLabel,
    this.semanticHint,
    this.keyboardType,
    this.obscureText = false,
    this.validator,
    this.decoration,
    this.onChanged,
    this.textInputAction,
    this.onFieldSubmitted,
  });

  @override
  Widget build(BuildContext context) {
    return Semantics(
      label: semanticLabel ?? labelText,
      hint: semanticHint ?? hintText,
      textField: true,
      child: TextField(
        controller: controller,
        decoration: decoration ??
            InputDecoration(
              labelText: labelText,
              hintText: hintText,
            ),
        keyboardType: keyboardType,
        obscureText: obscureText,
        onChanged: onChanged,
        textInputAction: textInputAction,
        onSubmitted: onFieldSubmitted,
      ),
    );
  }
}

/// Wrapper for text form fields with accessibility
class AccessibleTextFormField extends StatelessWidget {
  final TextEditingController? controller;
  final String? labelText;
  final String? hintText;
  final String? semanticLabel;
  final String? semanticHint;
  final TextInputType? keyboardType;
  final bool obscureText;
  final String? Function(String?)? validator;
  final InputDecoration? decoration;
  final void Function(String)? onChanged;
  final TextInputAction? textInputAction;
  final void Function(String)? onFieldSubmitted;

  const AccessibleTextFormField({
    super.key,
    this.controller,
    this.labelText,
    this.hintText,
    this.semanticLabel,
    this.semanticHint,
    this.keyboardType,
    this.obscureText = false,
    this.validator,
    this.decoration,
    this.onChanged,
    this.textInputAction,
    this.onFieldSubmitted,
  });

  @override
  Widget build(BuildContext context) {
    return Semantics(
      label: semanticLabel ?? labelText,
      hint: semanticHint ?? hintText,
      textField: true,
      child: TextFormField(
        controller: controller,
        decoration: decoration ??
            InputDecoration(
              labelText: labelText,
              hintText: hintText,
            ),
        keyboardType: keyboardType,
        obscureText: obscureText,
        validator: validator,
        onChanged: onChanged,
        textInputAction: textInputAction,
        onFieldSubmitted: onFieldSubmitted,
      ),
    );
  }
}
