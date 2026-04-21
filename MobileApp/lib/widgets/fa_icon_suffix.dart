import 'package:flutter/material.dart';
import 'package:font_awesome_flutter/font_awesome_flutter.dart';

/// Maps Backoffice `actor_action_icon` suffix (e.g. `fa-key`) to Font Awesome icons.
IconData faIconForSuffix(String? suffix) {
  if (suffix == null || suffix.isEmpty) {
    return FontAwesomeIcons.bell;
  }
  var s = suffix.trim();
  if (!s.startsWith('fa')) {
    s = 'fa-$s';
  }
  switch (s) {
    case 'fa-key':
      return FontAwesomeIcons.key;
    case 'fa-user-plus':
      return FontAwesomeIcons.userPlus;
    case 'fa-paper-plane':
      return FontAwesomeIcons.paperPlane;
    case 'fa-check':
      return FontAwesomeIcons.check;
    case 'fa-undo':
      return FontAwesomeIcons.arrowRotateLeft;
    case 'fa-plus-circle':
      return FontAwesomeIcons.circlePlus;
    case 'fa-file-upload':
      return FontAwesomeIcons.fileArrowUp;
    case 'fa-user-check':
      return FontAwesomeIcons.userCheck;
    case 'fa-inbox':
      return FontAwesomeIcons.inbox;
    case 'fa-pen':
      return FontAwesomeIcons.pen;
    case 'fa-file-alt':
      return FontAwesomeIcons.fileLines;
    case 'fa-clipboard-list':
      return FontAwesomeIcons.clipboardList;
    case 'fa-clock':
      return FontAwesomeIcons.clock;
    case 'fa-bell':
      return FontAwesomeIcons.bell;
    default:
      return FontAwesomeIcons.bell;
  }
}

IconData faIconFromApiIconClass(String? iconClass) {
  if (iconClass == null || iconClass.isEmpty) {
    return FontAwesomeIcons.bell;
  }
  final parts = iconClass.trim().split(RegExp(r'\s+'));
  if (parts.isEmpty) return FontAwesomeIcons.bell;
  final last = parts.last;
  if (last.startsWith('fa-')) {
    return faIconForSuffix(last);
  }
  return FontAwesomeIcons.bell;
}
