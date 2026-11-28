// Réseau : client HTTP tolérant (certificats IPTV souvent invalides) + décodage.
import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';

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

Future<List<int>> getBytes(String url, {Map<String, String>? headers, Duration timeout = const Duration(seconds: 90)}) async {
  final h = {'User-Agent': kUserAgent, 'Accept': '*/*', ...?headers};
  final r = await _client.get(Uri.parse(url), headers: h).timeout(timeout);
  if (r.statusCode >= 400) throw HttpStatusError(r.statusCode, url, r.headers['retry-after']);
  return r.bodyBytes;
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

/// Vrai dans l'isolat d'actualisation : on y est déjà hors de l'écran principal, inutile d'en lancer un autre.
bool inWorker = false;

Future<dynamic> getJson(String url, {Map<String, String>? headers, Duration timeout = const Duration(seconds: 90)}) async {
  final txt = (await getText(url, headers: headers, timeout: timeout)).trim();
  if (txt.isEmpty) return null;
  if (txt.length > 200000 && !inWorker) return compute(_jsonDecode, txt);
  return jsonDecode(txt);
}

/// POST JSON (connexion Jellyfin…). Renvoie le JSON décodé.
Future<dynamic> postJson(String url, Object body, {Map<String, String>? headers, Duration timeout = const Duration(seconds: 30)}) async {
  final h = {'User-Agent': kUserAgent, 'Content-Type': 'application/json', 'Accept': 'application/json', ...?headers};
  final r = await _client.post(Uri.parse(url), headers: h, body: jsonEncode(body)).timeout(timeout);
  if (r.statusCode >= 400) throw HttpStatusError(r.statusCode, url, r.headers['retry-after']);
  return jsonDecode(decodeBody(r.bodyBytes));
}

/// Lit une grande réponse JSON (tableau ou objet d'objets) au fil de l'eau : chaque objet de premier niveau est
/// décodé seul puis passé à [onObj]. La réponse entière n'est jamais gardée en mémoire (indispensable sur TV :
/// un catalogue Xtream de 50 Mo décodé d'un bloc dépasse la mémoire de beaucoup d'appareils).
Future<int> streamJsonObjects(String url, void Function(Map<String, dynamic>) onObj,
    {Map<String, String>? headers, Duration timeout = const Duration(seconds: 240)}) async {
  final rq = http.Request('GET', Uri.parse(url))..headers.addAll({'User-Agent': kUserAgent, 'Accept': '*/*', ...?headers});
  final r = await _client.send(rq).timeout(const Duration(seconds: 60));
  if (r.statusCode >= 400) throw HttpStatusError(r.statusCode, url, r.headers['retry-after']);
  final sc = JsonObjectScanner(onObj);
  await r.stream.timeout(const Duration(seconds: 60)).forEach(sc.add).timeout(timeout);
  sc.close();
  return sc.count;
}

/// Découpe un flux d'octets JSON en objets de premier niveau (sans jamais garder tout le texte).
class JsonObjectScanner {
  final void Function(Map<String, dynamic>) onObj;
  JsonObjectScanner(this.onObj);
  int count = 0;
  int _depth = 0;
  bool _inStr = false, _esc = false, _root = false;
  final BytesBuilder _buf = BytesBuilder(copy: false);
  int _rootKind = 0; // 0x5B tableau, 0x7B objet

  void add(List<int> chunk) {
    var start = -1; // début de l'objet en cours dans ce morceau
    if (_depth >= 2) start = 0;
    for (var i = 0; i < chunk.length; i++) {
      final b = chunk[i];
      if (_inStr) {
        if (_esc) {
          _esc = false;
        } else if (b == 0x5C) {
          _esc = true;
        } else if (b == 0x22) {
          _inStr = false;
        }
        continue;
      }
      if (b == 0x22) {
        _inStr = true;
      } else if (b == 0x7B || b == 0x5B) {
        if (!_root) {
          _root = true;
          _rootKind = b;
          _depth = 1;
          continue;
        }
        if (_depth == 1 && b == 0x7B) start = i;
        _depth++;
      } else if (b == 0x7D || b == 0x5D) {
        _depth--;
        if (_depth == 1 && start >= 0) {
          _buf.add(chunk.sublist(start, i + 1));
          start = -1;
          _emit();
        }
      }
    }
    if (_depth >= 2 && start >= 0) _buf.add(chunk.sublist(start));
  }

  void _emit() {
    final bytes = _buf.takeBytes();
    try {
      final v = jsonDecode(decodeBody(bytes));
      if (v is Map) {
        count++;
        onObj(Map<String, dynamic>.from(v));
      }
    } catch (_) {}
  }

  /// Fin du flux : une réponse qui n'était ni un tableau ni un objet JSON est une erreur.
  void close() {
    if (!_root || (_rootKind != 0x5B && _rootKind != 0x7B)) throw const FormatException('Réponse JSON vide ou invalide');
  }
}

/// Télécharge vers un fichier, au fil de l'eau (aucune copie complète en mémoire).
Future<void> downloadToFile(String url, String path, {Duration timeout = const Duration(seconds: 180)}) async {
  final rq = http.Request('GET', Uri.parse(url))..headers.addAll({'User-Agent': kUserAgent, 'Accept': '*/*'});
  final r = await _client.send(rq).timeout(const Duration(seconds: 60));
  if (r.statusCode >= 400) throw HttpStatusError(r.statusCode, url, r.headers['retry-after']);
  final sink = File(path).openWrite();
  try {
    await sink.addStream(r.stream.timeout(const Duration(seconds: 60))).timeout(timeout);
  } finally {
    await sink.close();
  }
}
