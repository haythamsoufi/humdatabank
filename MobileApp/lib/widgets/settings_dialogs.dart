import 'package:flutter/material.dart';
import '../providers/shared/auth_provider.dart';
import '../utils/constants.dart';
import '../utils/ios_constants.dart';
import '../utils/ui_helpers.dart';
import '../l10n/app_localizations.dart';

/// Shows a change-password dialog with current / new / confirm fields,
/// visibility toggles, validation, and server-side submission via
/// [authProvider.changePassword].
void showChangePasswordDialog(
    BuildContext context, AuthProvider authProvider) {
  final localizations = AppLocalizations.of(context)!;
  final theme = Theme.of(context);

  final currentPasswordController = TextEditingController();
  final newPasswordController = TextEditingController();
  final confirmPasswordController = TextEditingController();

  final formKey = GlobalKey<FormState>();
  bool obscureCurrentPassword = true;
  bool obscureNewPassword = true;
  bool obscureConfirmPassword = true;

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
                  TextFormField(
                    controller: currentPasswordController,
                    obscureText: obscureCurrentPassword,
                    decoration: InputDecoration(
                      labelText: localizations.currentPassword,
                      hintText: localizations.enterCurrentPassword,
                      prefixIcon: const Icon(Icons.lock_outline),
                      suffixIcon: IconButton(
                        icon: Icon(
                          obscureCurrentPassword
                              ? Icons.visibility_outlined
                              : Icons.visibility_off_outlined,
                        ),
                        onPressed: () {
                          setState(() {
                            obscureCurrentPassword = !obscureCurrentPassword;
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
                  const SizedBox(height: IOSSpacing.md),
                  TextFormField(
                    controller: newPasswordController,
                    obscureText: obscureNewPassword,
                    decoration: InputDecoration(
                      labelText: localizations.newPassword,
                      hintText: localizations.enterNewPassword,
                      prefixIcon: const Icon(Icons.lock_outline),
                      suffixIcon: IconButton(
                        icon: Icon(
                          obscureNewPassword
                              ? Icons.visibility_outlined
                              : Icons.visibility_off_outlined,
                        ),
                        onPressed: () {
                          setState(() {
                            obscureNewPassword = !obscureNewPassword;
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
                  const SizedBox(height: IOSSpacing.md),
                  TextFormField(
                    controller: confirmPasswordController,
                    obscureText: obscureConfirmPassword,
                    decoration: InputDecoration(
                      labelText: localizations.confirmPassword,
                      hintText: localizations.confirmNewPassword,
                      prefixIcon: const Icon(Icons.lock_outline),
                      suffixIcon: IconButton(
                        icon: Icon(
                          obscureConfirmPassword
                              ? Icons.visibility_outlined
                              : Icons.visibility_off_outlined,
                        ),
                        onPressed: () {
                          setState(() {
                            obscureConfirmPassword = !obscureConfirmPassword;
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
                Navigator.of(context).pop();

                showAppLoadingOverlay(context);

                final error = await authProvider.changePassword(
                  currentPassword: currentPasswordController.text,
                  newPassword: newPasswordController.text,
                );

                if (context.mounted) {
                  dismissAppLoadingOverlay(context);

                  if (error == null) {
                    showAppSnackBar(
                      context,
                      message: localizations.passwordChangedSuccessfully,
                      isSuccess: true,
                    );
                  } else {
                    showAppSnackBar(
                      context,
                      message: error,
                      isError: true,
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

/// Shows a single-field edit dialog used for profile fields like name or title.
///
/// * [currentValue] – pre-filled text (may be null).
/// * [fieldLabel] – used as both the dialog title and the input label.
/// * [hintText] – placeholder shown inside the text field.
/// * [onSave] – called with the trimmed value (or `null` when cleared);
///   must return `true` on success.
/// * [maxLength] – optional character limit on the text field.
/// * [validator] – optional custom validator; when omitted, rejects
///   whitespace-only input using [emptyValidationMessage].
/// * [emptyValidationMessage] – fallback message when the default validator
///   triggers and no custom [validator] is supplied.
/// * [prefixIcon] – icon shown at the start of the input field.
void showEditProfileFieldDialog(
  BuildContext context, {
  required String? currentValue,
  required String fieldLabel,
  required String hintText,
  required Future<bool> Function(String?) onSave,
  int? maxLength,
  String? Function(String?)? validator,
  String? emptyValidationMessage,
  IconData prefixIcon = Icons.edit_outlined,
}) {
  final localizations = AppLocalizations.of(context)!;
  final theme = Theme.of(context);

  final controller = TextEditingController(text: currentValue ?? '');
  final formKey = GlobalKey<FormState>();

  showDialog(
    context: context,
    builder: (context) => AlertDialog(
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(AppConstants.radiusLarge),
      ),
      title: Text(
        fieldLabel,
        style: IOSTextStyle.title3(context).copyWith(
          fontWeight: FontWeight.bold,
        ),
      ),
      content: SizedBox(
        width: double.maxFinite,
        child: Form(
          key: formKey,
          child: TextFormField(
            controller: controller,
            autofocus: true,
            maxLength: maxLength,
            decoration: InputDecoration(
              labelText: fieldLabel,
              hintText: hintText,
              prefixIcon: Icon(prefixIcon),
              border: OutlineInputBorder(
                borderRadius: BorderRadius.circular(AppConstants.radiusLarge),
              ),
              filled: true,
              fillColor: theme.inputDecorationTheme.fillColor,
            ),
            validator: validator ??
                (value) {
                  if (value != null && value.trim().isEmpty) {
                    return emptyValidationMessage;
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
              final trimmed = controller.text.trim();

              Navigator.of(context).pop();

              if (context.mounted) {
                showAppLoadingOverlay(context);
              }

              final success =
                  await onSave(trimmed.isEmpty ? null : trimmed);

              if (context.mounted) {
                dismissAppLoadingOverlay(context);

                showAppSnackBar(
                  context,
                  message: success
                      ? localizations.profileUpdatedSuccessfully
                      : localizations.errorUpdatingProfile,
                  isSuccess: success,
                  isError: !success,
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
