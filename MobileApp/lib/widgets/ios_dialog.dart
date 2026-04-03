import 'package:flutter/material.dart';
import 'package:flutter/cupertino.dart' as cupertino;
import '../utils/ios_constants.dart';
import '../l10n/app_localizations.dart';

/// iOS-native alert dialog using CupertinoAlertDialog
class IOSAlertDialog extends StatelessWidget {
  final String? title;
  final String? message;
  final List<Widget>? actions;
  final Widget? content;

  const IOSAlertDialog({
    super.key,
    this.title,
    this.message,
    this.actions,
    this.content,
  });

  static Future<T?> show<T>({
    required BuildContext context,
    String? title,
    String? message,
    List<Widget>? actions,
    Widget? content,
  }) {
    return showDialog<T>(
      context: context,
      barrierDismissible: true,
      builder: (context) => IOSAlertDialog(
        title: title,
        message: message,
        actions: actions,
        content: content,
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return cupertino.CupertinoAlertDialog(
      title: title != null ? Text(title!) : null,
      content: content ?? (message != null ? Text(message!) : null),
      actions: actions ?? [
        cupertino.CupertinoDialogAction(
          child: Text(
            AppLocalizations.of(context)?.cancel ?? 'Cancel',
            style: IOSTextStyle.body(context),
          ),
          onPressed: () => Navigator.of(context).pop(),
        ),
      ],
    );
  }
}

/// iOS-style action sheet
class IOSActionSheet extends StatelessWidget {
  final String? title;
  final String? message;
  final List<cupertino.CupertinoActionSheetAction> actions;
  final cupertino.CupertinoActionSheetAction? cancelButton;

  const IOSActionSheet({
    super.key,
    this.title,
    this.message,
    required this.actions,
    this.cancelButton,
  });

  static Future<T?> show<T>({
    required BuildContext context,
    String? title,
    String? message,
    required List<cupertino.CupertinoActionSheetAction> actions,
    cupertino.CupertinoActionSheetAction? cancelButton,
  }) {
    return showModalBottomSheet<T>(
      context: context,
      backgroundColor: Colors.transparent,
      builder: (context) => IOSActionSheet(
        title: title,
        message: message,
        actions: actions,
        cancelButton: cancelButton,
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return cupertino.CupertinoActionSheet(
      title: title != null ? Text(title!) : null,
      message: message != null ? Text(message!) : null,
      actions: actions,
      cancelButton: cancelButton ??
          cupertino.CupertinoActionSheetAction(
            isDestructiveAction: false,
            onPressed: () => Navigator.of(context).pop(),
            child: Text(
              AppLocalizations.of(context)?.cancel ?? 'Cancel',
              style: IOSTextStyle.body(context).copyWith(
                fontWeight: FontWeight.w600,
              ),
            ),
          ),
    );
  }
}
