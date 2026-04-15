import 'package:flutter_test/flutter_test.dart';
import 'package:hum_databank_app/models/shared/ai_chat_launch_args.dart';

void main() {
  group('AiChatLaunchArgs.parse', () {
    test('returns default args when arguments is null', () {
      final args = AiChatLaunchArgs.parse(null);

      expect(args.bottomNavTabIndex, 2);
      expect(args.initialText, isNull);
      expect(args.sendImmediately, false);
      expect(args.startNewConversation, false);
    });

    test('returns same instance when arguments is AiChatLaunchArgs', () {
      const original = AiChatLaunchArgs(
        bottomNavTabIndex: 3,
        initialText: 'Tell me about health data',
        sendImmediately: true,
        startNewConversation: true,
      );

      final parsed = AiChatLaunchArgs.parse(original);

      expect(identical(parsed, original), true);
      expect(parsed.bottomNavTabIndex, 3);
      expect(parsed.initialText, 'Tell me about health data');
      expect(parsed.sendImmediately, true);
      expect(parsed.startNewConversation, true);
    });

    test('wraps int into bottomNavTabIndex', () {
      final args = AiChatLaunchArgs.parse(5);

      expect(args.bottomNavTabIndex, 5);
      expect(args.initialText, isNull);
      expect(args.sendImmediately, false);
      expect(args.startNewConversation, false);
    });

    test('returns default args for unknown type', () {
      final args = AiChatLaunchArgs.parse('unexpected');

      expect(args.bottomNavTabIndex, 2);
      expect(args.initialText, isNull);
      expect(args.sendImmediately, false);
    });

    test('returns default args for a map (unsupported type)', () {
      final args = AiChatLaunchArgs.parse({'key': 'value'});

      expect(args.bottomNavTabIndex, 2);
    });
  });

  group('AiChatLaunchArgs.bottomNavIndexFrom', () {
    test('returns default index when arguments is null', () {
      expect(AiChatLaunchArgs.bottomNavIndexFrom(null), 2);
    });

    test('returns int directly from int argument', () {
      expect(AiChatLaunchArgs.bottomNavIndexFrom(4), 4);
    });

    test('extracts index from AiChatLaunchArgs', () {
      const args = AiChatLaunchArgs(bottomNavTabIndex: 1);
      expect(AiChatLaunchArgs.bottomNavIndexFrom(args), 1);
    });

    test('returns default index for unknown type', () {
      expect(AiChatLaunchArgs.bottomNavIndexFrom(true), 2);
    });
  });

  group('AiChatLaunchArgs constructor defaults', () {
    test('default const constructor uses expected values', () {
      const args = AiChatLaunchArgs();

      expect(args.bottomNavTabIndex, 2);
      expect(args.initialText, isNull);
      expect(args.sendImmediately, false);
      expect(args.startNewConversation, false);
    });
  });
}
