import 'package:flutter/material.dart';

/// Chooses between a loading widget, an error widget, or main [child] content.
///
/// Parent decides [whenLoading] / [whenError] (e.g. empty list + error).
class AsyncBody extends StatelessWidget {
  const AsyncBody({
    super.key,
    required this.whenLoading,
    required this.whenError,
    required this.loading,
    this.error,
    required this.child,
  });

  final bool whenLoading;
  final bool whenError;
  final Widget loading;
  final Widget? error;
  final Widget child;

  @override
  Widget build(BuildContext context) {
    if (whenLoading) {
      return loading;
    }
    if (whenError && error != null) {
      return error!;
    }
    return child;
  }
}
