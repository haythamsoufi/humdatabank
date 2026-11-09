class User {
  final int id;
  final String email;
  final String? name;
  final String? title;
  final String role;
  final bool chatbotEnabled;
  final String? profileColor;
  final List<int>? countryIds;
  final bool aiBetaTester;

  /// Server toggle: AI is limited to selected users.
  /// False when the field is absent (older servers), so chat stays usable.
  final bool aiBetaRestricted;

  /// RBAC role codes from profile (e.g. `assignment_documents_uploader`).
  final List<String> rbacRoleCodes;

  /// From mobile profile when the server supports it; otherwise null (use [rbacRoleCodes]).
  final bool? canOpenEntityDocuments;

  User({
    required this.id,
    required this.email,
    this.name,
    this.title,
    required this.role,
    this.chatbotEnabled = false,
    this.profileColor,
    this.countryIds,
    this.aiBetaTester = false,
    this.aiBetaRestricted = false,
    this.rbacRoleCodes = const [],
    this.canOpenEntityDocuments,
  });

  /// Chat is locked when beta restriction is on and this user is not allow-listed.
  bool get aiBetaAccessLocked => aiBetaRestricted && !aiBetaTester;

  User copyWith({
    int? id,
    String? email,
    String? name,
    String? title,
    String? role,
    bool? chatbotEnabled,
    String? profileColor,
    List<int>? countryIds,
    bool? aiBetaTester,
    bool? aiBetaRestricted,
    List<String>? rbacRoleCodes,
    bool? canOpenEntityDocuments,
  }) {
    return User(
      id: id ?? this.id,
      email: email ?? this.email,
      name: name ?? this.name,
      title: title ?? this.title,
      role: role ?? this.role,
      chatbotEnabled: chatbotEnabled ?? this.chatbotEnabled,
      profileColor: profileColor ?? this.profileColor,
      countryIds: countryIds ?? this.countryIds,
      aiBetaTester: aiBetaTester ?? this.aiBetaTester,
      aiBetaRestricted: aiBetaRestricted ?? this.aiBetaRestricted,
      rbacRoleCodes: rbacRoleCodes ?? this.rbacRoleCodes,
      canOpenEntityDocuments:
          canOpenEntityDocuments ?? this.canOpenEntityDocuments,
    );
  }

  bool get canOpenEntityDocumentRepository {
    final explicit = canOpenEntityDocuments;
    if (explicit != null) return explicit;
    return rbacRoleCodes.any(
      (c) => c.toLowerCase() == 'assignment_documents_uploader',
    );
  }

  factory User.fromJson(Map<String, dynamic> json) {
    return User(
      id: json['id'] ?? 0,
      email: json['email'] ?? '',
      name: json['name'],
      title: json['title'],
      role: json['role'] ?? 'focal_point',
      chatbotEnabled: json['chatbot_enabled'] ?? false,
      profileColor: json['profile_color'],
      countryIds: json['country_ids'] != null
          ? List<int>.from(json['country_ids'])
          : null,
      aiBetaTester: json['ai_beta_tester'] == true,
      aiBetaRestricted: json['ai_beta_restricted'] == true,
      rbacRoleCodes: parseRbacRoleCodesFromProfile(json),
      canOpenEntityDocuments: parseCanOpenEntityDocumentsFromProfile(json),
    );
  }

  static bool? parseCanOpenEntityDocumentsFromProfile(Map<String, dynamic> json) {
    if (!json.containsKey('can_open_entity_documents')) return null;
    return json['can_open_entity_documents'] == true;
  }

  static List<String> parseRbacRoleCodesFromProfile(Map<String, dynamic> json) {
    final raw = json['rbac_role_codes'] ?? json['rbac_roles'];
    if (raw is! List) return const [];
    final codes = <String>[];
    for (final item in raw) {
      if (item is String && item.trim().isNotEmpty) {
        codes.add(item.trim());
        continue;
      }
      if (item is Map) {
        final code = item['code'];
        if (code != null && '$code'.trim().isNotEmpty) {
          codes.add('$code'.trim());
        }
      }
    }
    return codes;
  }

  Map<String, dynamic> toJson() {
    return {
      'id': id,
      'email': email,
      'name': name,
      'title': title,
      'role': role,
      'chatbot_enabled': chatbotEnabled,
      'profile_color': profileColor,
      'country_ids': countryIds,
      'ai_beta_tester': aiBetaTester,
      'ai_beta_restricted': aiBetaRestricted,
      'rbac_role_codes': rbacRoleCodes,
      if (canOpenEntityDocuments != null)
        'can_open_entity_documents': canOpenEntityDocuments,
    };
  }

  String get displayName => name ?? email.split('@').first;

  bool get isAdmin => role == 'admin' || role == 'system_manager';
  bool get isFocalPoint => role == 'focal_point';
}
