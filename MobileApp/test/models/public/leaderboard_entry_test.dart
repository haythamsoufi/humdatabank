import 'package:flutter_test/flutter_test.dart';
import 'package:hum_databank_app/models/public/leaderboard_entry.dart';

void main() {
  group('LeaderboardEntry.fromJson', () {
    test('parses all fields correctly', () {
      final json = {
        'rank': 1,
        'user_id': 42,
        'name': 'Alice',
        'email': 'alice@example.org',
        'score': 950,
      };

      final entry = LeaderboardEntry.fromJson(json);

      expect(entry.rank, 1);
      expect(entry.userId, 42);
      expect(entry.name, 'Alice');
      expect(entry.email, 'alice@example.org');
      expect(entry.score, 950);
    });

    test('parses second-place entry', () {
      final entry = LeaderboardEntry.fromJson({
        'rank': 2,
        'user_id': 7,
        'name': 'Bob',
        'email': 'bob@test.io',
        'score': 800,
      });

      expect(entry.rank, 2);
      expect(entry.userId, 7);
      expect(entry.name, 'Bob');
      expect(entry.email, 'bob@test.io');
      expect(entry.score, 800);
    });

    test('handles zero score', () {
      final entry = LeaderboardEntry.fromJson({
        'rank': 99,
        'user_id': 1,
        'name': 'New User',
        'email': 'new@test.io',
        'score': 0,
      });

      expect(entry.score, 0);
      expect(entry.rank, 99);
    });

    test('handles high rank number', () {
      final entry = LeaderboardEntry.fromJson({
        'rank': 10000,
        'user_id': 555,
        'name': 'Last Place',
        'email': 'last@test.io',
        'score': 1,
      });

      expect(entry.rank, 10000);
      expect(entry.userId, 555);
    });
  });
}
