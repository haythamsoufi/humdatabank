import 'package:flutter_test/flutter_test.dart';
import 'package:hum_databank_app/models/shared/focal_point_contact.dart';

void main() {
  group('FocalPointContact', () {
    test('fromJson parses contact fields', () {
      final contact = FocalPointContact.fromJson({
        'id': 7,
        'name': 'Jane Doe',
        'title': 'Data Manager',
        'email': 'jane@example.org',
      });

      expect(contact.id, 7);
      expect(contact.displayName, 'Jane Doe');
      expect(contact.title, 'Data Manager');
      expect(contact.email, 'jane@example.org');
      expect(contact.initials, 'JD');
    });

    test('displayName falls back to email when name missing', () {
      final contact = FocalPointContact.fromJson({
        'id': 1,
        'email': 'user@ifrc.org',
      });

      expect(contact.displayName, 'user@ifrc.org');
      expect(contact.initials, 'U');
    });

    test('toJson round-trips core fields', () {
      const contact = FocalPointContact(
        id: 3,
        name: 'Alex',
        title: 'Officer',
        email: 'alex@example.org',
      );

      final restored = FocalPointContact.fromJson(contact.toJson());
      expect(restored.id, contact.id);
      expect(restored.name, contact.name);
      expect(restored.title, contact.title);
      expect(restored.email, contact.email);
    });
  });
}
