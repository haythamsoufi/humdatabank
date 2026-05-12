# Freezed Model Migration Guide

## Overview

This project is transitioning from hand-written model classes to [freezed](https://pub.dev/packages/freezed) + [json_serializable](https://pub.dev/packages/json_serializable) for immutable data classes with JSON serialization.

## Setup

Dependencies are already configured in `pubspec.yaml`. The `analysis_options.yaml` excludes generated files (`*.freezed.dart`, `*.g.dart`).

## Running Code Generation

```bash
cd MobileApp
dart run build_runner build --delete-conflicting-outputs
```

For watch mode during development:
```bash
dart run build_runner watch --delete-conflicting-outputs
```

## Migration Pattern

### Before (hand-written)

```dart
class Resource {
  final int id;
  final String? title;
  final bool isPublished;

  Resource({required this.id, this.title, this.isPublished = false});

  factory Resource.fromJson(Map<String, dynamic> json) {
    return Resource(
      id: json['id'] as int,
      title: json['title'] as String?,
      isPublished: json['is_published'] as bool? ?? false,
    );
  }
}
```

### After (freezed)

```dart
import 'package:freezed_annotation/freezed_annotation.dart';

part 'resource.freezed.dart';
part 'resource.g.dart';

@freezed
abstract class Resource with _$Resource {
  const factory Resource({
    required int id,
    String? title,
    @JsonKey(name: 'is_published') @Default(false) bool isPublished,
  }) = _Resource;

  factory Resource.fromJson(Map<String, dynamic> json) =>
      _$ResourceFromJson(json);
}
```

## What You Get for Free

- `==` and `hashCode` (value equality)
- `toString()` with all fields
- `copyWith()` with nullable field support
- `toJson()` serialization
- Compile-time exhaustive matching for union types

## Migration Priority

1. **Shared models** (`lib/models/shared/`) — used across screens
2. **Admin models** (`lib/models/admin/`) — used in admin screens
3. **Public models** (`lib/models/public/`) — used in public screens
4. **Indicator bank models** (`lib/models/indicator_bank/`) — domain-specific

## Reference Implementation

See `lib/models/shared/resource.freezed_model.dart` for a complete example.

## CI Integration

The `mobileapp-analyze.yml` workflow should include a build_runner step to verify generated code is up to date:

```yaml
- name: Verify generated code
  run: dart run build_runner build --delete-conflicting-outputs && git diff --exit-code
```
