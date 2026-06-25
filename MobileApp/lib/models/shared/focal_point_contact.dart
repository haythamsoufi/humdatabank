class FocalPointContact {
  final int id;
  final String? name;
  final String? title;
  final String email;

  const FocalPointContact({
    required this.id,
    this.name,
    this.title,
    required this.email,
  });

  factory FocalPointContact.fromJson(Map<String, dynamic> json) {
    return FocalPointContact(
      id: json['id'] as int? ?? 0,
      name: json['name'] as String?,
      title: json['title'] as String?,
      email: json['email'] as String? ?? '',
    );
  }

  Map<String, dynamic> toJson() {
    return {
      'id': id,
      'name': name,
      'title': title,
      'email': email,
    };
  }

  String get displayName {
    final trimmedName = name?.trim();
    if (trimmedName != null && trimmedName.isNotEmpty) {
      return trimmedName;
    }
    return email;
  }

  String get initials {
    final source = displayName;
    if (source.contains('@')) {
      final local = source.split('@').first;
      if (local.isEmpty) return '?';
      return local.substring(0, 1).toUpperCase();
    }
    final parts = source.trim().split(RegExp(r'\s+'));
    if (parts.length >= 2) {
      return '${parts.first[0]}${parts.last[0]}'.toUpperCase();
    }
    return source.substring(0, 1).toUpperCase();
  }
}
