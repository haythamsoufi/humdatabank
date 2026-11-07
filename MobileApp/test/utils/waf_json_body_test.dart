import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:hum_databank_app/utils/waf_json_body.dart';

Map<String, dynamic> _unwrap(Map<String, dynamic> envelope) {
  final parts = <String>[envelope['payload'] as String];
  for (var i = 1; envelope.containsKey('payload__c$i'); i++) {
    parts.add(envelope['payload__c$i'] as String);
  }
  return jsonDecode(utf8.decode(base64.decode(parts.join()))) as Map<String, dynamic>;
}

void main() {
  group('wrapWafJsonBody', () {
    test('small bodies fit in a single payload key', () {
      final env = wrapWafJsonBody({'message': 'hi'});
      expect(env.keys, ['payload']);
      expect(_unwrap(env), {'message': 'hi'});
    });

    test('long bodies with HTML/SQL-like history are chunked and round-trip', () {
      final inner = {
        'message': 'And for Kenya?',
        'conversationHistory': [
          {'isUser': true, 'message': 'Volunteers in Syria over time'},
          {
            'isUser': false,
            'message': '<table><tr><td>2019</td></tr></table> | Year | Value | -- SELECT * FROM x; ' * 20,
          },
        ],
        'preferred_language': 'ar',
        'note': 'مرحبا',
      };
      final env = wrapWafJsonBody(inner);
      expect(env.keys.length, greaterThan(1));
      for (final v in env.values) {
        expect((v as String).length, lessThanOrEqualTo(wafJsonMaxChunk));
      }
      expect(env.keys.first, 'payload');
      expect(_unwrap(env), inner);
    });
  });
}
