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
  });

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
    );
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
    };
  }

  String get displayName => name ?? email.split('@').first;
}
