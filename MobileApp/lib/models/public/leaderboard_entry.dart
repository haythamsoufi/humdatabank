/// Leaderboard entry model
class LeaderboardEntry {
  final int rank;
  final int userId;
  final String name;
  final String email;
  final int score;

  LeaderboardEntry({
    required this.rank,
    required this.userId,
    required this.name,
    required this.email,
    required this.score,
  });

  factory LeaderboardEntry.fromJson(Map<String, dynamic> json) {
    return LeaderboardEntry(
      rank: json['rank'] as int,
      userId: json['user_id'] as int,
      name: json['name'] as String,
      email: json['email'] as String,
      score: json['score'] as int,
    );
  }
}
