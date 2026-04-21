import '../models/shared/user.dart';

/// Two-letter initials for profile avatars (aligned with notifications + drawer).
String _initialsFromEmailLocal(String email) {
  final e = email.trim();
  if (e.isEmpty) return 'U';
  final local = e.split('@').first;
  if (local.isEmpty) return '?';
  if (local.length >= 2) return local.substring(0, 2).toUpperCase();
  return local.toUpperCase();
}

/// Derives initials from a display [name] when present, otherwise from [email]'s local part.
String avatarInitialsForProfile({String? name, required String email}) {
  final raw = name?.trim();
  if (raw != null && raw.isNotEmpty) {
    final parts = raw.split(RegExp(r'\s+'));
    if (parts.length == 1) {
      final p = parts[0];
      if (p.isEmpty) return _initialsFromEmailLocal(email);
      return p.length >= 2 ? p.substring(0, 2).toUpperCase() : p.toUpperCase();
    }
    final a = parts.first.isNotEmpty ? parts.first[0] : '';
    final b = parts.last.isNotEmpty ? parts.last[0] : '';
    return ('$a$b').toUpperCase();
  }
  return _initialsFromEmailLocal(email);
}

/// Same rules as [avatarInitialsForProfile], using [User.name] and [User.email].
String avatarInitialsForUser(User user) =>
    avatarInitialsForProfile(name: user.name, email: user.email);
