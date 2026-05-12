class AccessRequestUserRef {
  final int? id;
  final String? email;
  final String? name;

  const AccessRequestUserRef({
    this.id,
    this.email,
    this.name,
  });

  static int? _parseInt(dynamic v) {
    if (v == null) return null;
    if (v is int) return v;
    if (v is num) return v.toInt();
    return int.tryParse(v.toString());
  }

  factory AccessRequestUserRef.fromJson(Map<String, dynamic>? json) {
    if (json == null) {
      return const AccessRequestUserRef();
    }
    return AccessRequestUserRef(
      id: _parseInt(json['id']),
      email: json['email']?.toString(),
      name: json['name']?.toString(),
    );
  }
}

class AccessRequestCountryRef {
  final int? id;
  final String? name;
  final String? iso2;

  const AccessRequestCountryRef({
    this.id,
    this.name,
    this.iso2,
  });

  factory AccessRequestCountryRef.fromJson(Map<String, dynamic>? json) {
    if (json == null) {
      return const AccessRequestCountryRef();
    }
    return AccessRequestCountryRef(
      id: AccessRequestUserRef._parseInt(json['id']),
      name: json['name']?.toString(),
      iso2: json['iso2']?.toString(),
    );
  }
}

class CountryAccessRequestItem {
  final int id;
  final String status;
  final String? requestMessage;
  final String? createdAt;
  final String? processedAt;
  final String? adminNotes;
  final AccessRequestUserRef user;
  final AccessRequestCountryRef country;
  final AccessRequestUserRef? processedBy;

  const CountryAccessRequestItem({
    required this.id,
    required this.status,
    this.requestMessage,
    this.createdAt,
    this.processedAt,
    this.adminNotes,
    required this.user,
    required this.country,
    this.processedBy,
  });

  factory CountryAccessRequestItem.fromJson(Map<String, dynamic> json) {
    final id = AccessRequestUserRef._parseInt(json['id']) ?? 0;
    final userMap = json['user'];
    final AccessRequestUserRef user;
    if (userMap is Map<String, dynamic>) {
      user = AccessRequestUserRef.fromJson(userMap);
    } else {
      user = AccessRequestUserRef(
        id: AccessRequestUserRef._parseInt(json['user_id']),
        email: json['user_email']?.toString(),
        name: json['user_name']?.toString(),
      );
    }

    final countryMap = json['country'];
    final AccessRequestCountryRef country;
    if (countryMap is Map<String, dynamic>) {
      country = AccessRequestCountryRef.fromJson(countryMap);
    } else {
      country = AccessRequestCountryRef(
        id: AccessRequestUserRef._parseInt(json['country_id']),
        name: json['country_name']?.toString(),
        iso2: json['country_iso2']?.toString() ?? json['iso2']?.toString(),
      );
    }

    final processedMap = json['processed_by'];
    final AccessRequestUserRef? processedBy;
    if (processedMap is Map<String, dynamic>) {
      processedBy = AccessRequestUserRef.fromJson(processedMap);
    } else if (json['processed_by_user_id'] != null ||
        json['processed_by_email'] != null ||
        json['processed_by_name'] != null) {
      processedBy = AccessRequestUserRef(
        id: AccessRequestUserRef._parseInt(json['processed_by_user_id']),
        email: json['processed_by_email']?.toString(),
        name: json['processed_by_name']?.toString(),
      );
    } else {
      processedBy = null;
    }

    return CountryAccessRequestItem(
      id: id,
      status: json['status']?.toString() ?? '',
      requestMessage: json['request_message']?.toString(),
      createdAt: json['created_at']?.toString(),
      processedAt: json['processed_at']?.toString(),
      adminNotes: json['admin_notes']?.toString(),
      user: user,
      country: country,
      processedBy: processedBy,
    );
  }
}
