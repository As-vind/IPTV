// Réseau : client HTTP tolérant (certificats IPTV souvent invalides) + décodage.
import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:flutter/foundation.dart';
import 'package:http/http.dart' as http;
import 'package:http/io_client.dart';

const String kUserAgent = 'VLC/3.0.21 LibVLC/3.0.21';

class LaxHttpOverrides extends HttpOverrides {
  @override
  HttpClient createHttpClient(SecurityContext? context) {
    final c = super.createHttpClient(context);
    c.badCertificateCallback = (cert, host, port) => true;
    c.connectionTimeout = const Duration(seconds: 20);
    return c;
  }
}

final http.Client _client = IOClient(HttpClient()
  ..badCertificateCallback = ((cert, host, port) => true)
  ..connectionTimeout = const Duration(seconds: 20));

String decodeBody(List<int> bytes) {
  var b = bytes;
  if (b.length >= 3 && b[0] == 0xEF && b[1] == 0xBB && b[2] == 0xBF) b = b.sublist(3);
  try {
    return utf8.decode(b);
  } catch (_) {
    return latin1.decode(b, allowInvalid: true);
  }
}

Future<String> getText(String url, {Map<String, String>? headers, Duration timeout = const Duration(seconds: 90)}) async {
  final h = {'User-Agent': kUserAgent, 'Accept': '*/*', ...?headers};
  final r = await _client.get(Uri.parse(url), headers: h).timeout(timeout);
  if (r.statusCode >= 400) {
    throw HttpStatusError(r.statusCode, url, r.headers['retry-after']);
  }
  return decodeBody(r.bodyBytes);
}

/// Erreur HTTP avec son code (pour savoir s'il faut réessayer).
class HttpStatusError extends HttpException {
  final int code;
  final String? retryAfter;
  HttpStatusError(this.code, String url, [this.retryAfter]) : super('Erreur HTTP $code', uri: Uri.tryParse(url));
}

/// Limite le nombre de requêtes simultanées (TMDB refuse les rafales).
class Semaphore {
  int _free;
  final List<Completer<void>> _queue = [];
  Semaphore(this._free);
  Future<T> run<T>(Future<T> Function() task) async {
    if (_free > 0) {
      _free--;
    } else {
      final c = Completer<void>();
      _queue.add(c);
      await c.future;
    }
    try {
      return await task();
    } finally {
      if (_queue.isNotEmpty) {
        _queue.removeAt(0).complete();
      } else {
        _free++;
      }
    }
  }
}

dynamic _jsonDecode(String s) => jsonDecode(s);

Future<dynamic> getJson(String url, {Map<String, String>? headers, Duration timeout = const Duration(seconds: 90)}) async {
  final txt = (await getText(url, headers: headers, timeout: timeout)).trim();
  if (txt.isEmpty) return null;
  if (txt.length > 200000) return compute(_jsonDecode, txt);
  return jsonDecode(txt);
}
