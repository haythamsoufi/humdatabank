import 'dart:convert';
import 'dart:typed_data';

import 'package:dio/dio.dart';

class FakeAdapter implements HttpClientAdapter {
  FakeAdapter(this.routes);

  final Map<String, ({int status, String body})> routes;
  final List<String> requested = [];
  final Map<String, Map<String, dynamic>> headersByHost = {};

  /// Paths whose request never answers (until it is cancelled).
  final Set<String> hang = {};

  @override
  Future<ResponseBody> fetch(
    RequestOptions options,
    Stream<Uint8List>? requestStream,
    Future<void>? cancelFuture,
  ) async {
    requested.add(options.uri.path);
    if (hang.contains(options.uri.path)) {
      await cancelFuture;
      throw DioException.requestCancelled(
        requestOptions: options,
        reason: 'cancelled',
      );
    }
    headersByHost[options.uri.host] = Map.of(options.headers);
    final r = routes[options.uri.path];
    if (r == null) return ResponseBody.fromBytes(<int>[], 404);
    return ResponseBody.fromBytes(utf8.encode(r.body), r.status);
  }

  @override
  void close({bool force = false}) {}
}

const html =
    '<html><head>'
    '<link rel="stylesheet" href="/static/css/app.css?v=1">'
    '<script src="/static/js/app.js?v=1"></script>'
    '</head><body><form>form</form></body></html>';

Map<String, ({int status, String body})> routes({bool cssOk = true}) => {
  '/forms/assignment/5': (status: 200, body: html),
  '/forms/assignment/6': (status: 200, body: html),
  '/static/css/app.css': (status: cssOk ? 200 : 404, body: 'body{color:red}'),
  '/static/js/app.js': (status: 200, body: 'console.log(1);'),
};
