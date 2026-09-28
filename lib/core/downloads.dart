// Téléchargements hors ligne : un à la fois, reprise après coupure ou redémarrage.
import 'dart:async';
import 'dart:io';
import 'dart:math';

import 'package:flutter/foundation.dart';
import 'package:path_provider/path_provider.dart';

import 'models.dart';
import 'net.dart';
import 'store.dart';

const List<String> kVideoExts = ['.mp4', '.mkv', '.avi', '.mov', '.m4v', '.ts', '.wmv', '.flv', '.webm', '.mpg', '.mpeg'];

String safeFileName(String name) {
  var n = name.replaceAll(RegExp(r'[\\/:*?"<>|\r\n\t]+'), ' ').trim();
  n = n.replaceAll(RegExp(r'\s+'), ' ');
  while (n.endsWith('.')) {
    n = n.substring(0, n.length - 1);
  }
  if (n.length > 120) n = n.substring(0, 120);
  return n.isEmpty ? 'video' : n;
}

String fmtSize(num bytes) {
  final b = bytes.toDouble();
  if (b >= 1 << 30) return '${(b / (1 << 30)).toStringAsFixed(2).replaceAll('.', ',')} Go';
  if (b >= 1 << 20) return '${(b / (1 << 20)).toStringAsFixed(0)} Mo';
  return '${(b / 1024).toStringAsFixed(0)} Ko';
}

String fmtSecs(num secs) {
  final s = max(0, secs.toInt());
  if (s >= 3600) return '${s ~/ 3600} h ${((s % 3600) ~/ 60).toString().padLeft(2, '0')}';
  return '${s ~/ 60}:${(s % 60).toString().padLeft(2, '0')}';
}

class DownloadManager extends ChangeNotifier {
  final AppState s;
  DownloadManager(this.s);

  final Map<String, double> speed = {};
  String? _active;
  bool _stop = false;
  final Set<String> _removed = {};
  Directory? _dir;

  List<Map<String, dynamic>> get jobs {
    final l = s.cfg['downloads'];
    if (l is List) return l.whereType<Map>().map((e) => e as Map<String, dynamic>).toList();
    return [];
  }

  List _raw() => s.cfg['downloads'] as List;

  void init() {
    final raw = _raw();
    for (var i = 0; i < raw.length; i++) {
      raw[i] = Map<String, dynamic>.from(raw[i] as Map);
      if (raw[i]['state'] == 'downloading') raw[i]['state'] = 'queued';
    }
    Timer(const Duration(seconds: 3), _next);
  }

  Future<Directory> folder() async {
    if (_dir != null) return _dir!;
    Directory base;
    if (Platform.isAndroid) {
      base = (await getExternalStorageDirectory()) ?? await getApplicationDocumentsDirectory();
    } else {
      base = await getApplicationDocumentsDirectory();
    }
    final d = Directory('${base.path}/Téléchargements');
    await d.create(recursive: true);
    return _dir = d;
  }

  Map<String, dynamic>? jobFor(String url) {
    for (final j in jobs) {
      if (j['url'] == url) return j;
    }
    return null;
  }

  String? localFile(String url) {
    final j = jobFor(url);
    if (j != null && j['state'] == 'done' && File('${j['path']}').existsSync()) return '${j['path']}';
    return null;
  }

  int percent(Map j) {
    final size = (j['size'] as num?) ?? 0;
    return size > 0 ? (100 * ((j['done'] as num?) ?? 0) / size).floor() : 0;
  }

  Future<Map<String, dynamic>> add(PlayItem it, {String? title, bool quiet = false}) async {
    var j = jobFor(it.url);
    if (j != null && j['state'] == 'done' && !File('${j['path']}').existsSync()) {
      _raw().remove(j);
      j = null;
    }
    if (j != null) {
      if (j['state'] == 'error' || j['state'] == 'paused') resume('${j['id']}');
      return j;
    }
    final se = it.series;
    String name;
    if (se != null) {
      name = '${se['name']} - S${'${se['season']}'.padLeft(2, '0')}E${'${se['num']}'.padLeft(2, '0')}';
      final ep = '${se['ep_name'] ?? ''}';
      if (ep.isNotEmpty && !RegExp(r'^(Épisode|Episode)\s*\d+$').hasMatch(ep)) name += ' - $ep';
    } else {
      name = title ?? it.name;
    }
    var ext = '';
    final path = Uri.tryParse(it.url)?.path ?? '';
    final dot = path.lastIndexOf('.');
    if (dot >= 0) ext = path.substring(dot).toLowerCase();
    if (!kVideoExts.contains(ext)) ext = '.mp4';
    final dir = await folder();
    final base = safeFileName(name);
    var file = '${dir.path}/$base$ext';
    var k = 2;
    while (File(file).existsSync() || jobs.any((x) => x['path'] == file)) {
      file = '${dir.path}/$base ($k)$ext';
      k++;
    }
    j = {
      'id': AppState.newId(), 'url': it.url, 'name': name, 'kind': se != null ? 'episode' : it.kind,
      'logo': '${se?['logo'] ?? it.logo}', 'series': se, 'group': it.group, 'opts': it.opts,
      'path': file, 'size': 0, 'done': 0, 'state': 'queued', 'error': '',
      'added': DateTime.now().millisecondsSinceEpoch,
    };
    _raw().add(j);
    s.save();
    notifyListeners();
    _next();
    return j;
  }

  PlayItem playItem(Map j) => PlayItem(
        name: '${j['name']}', url: '${j['url']}', kind: j['series'] != null ? 'episode' : 'movie',
        logo: '${j['logo'] ?? ''}', group: '${j['group'] ?? ''}',
        opts: ((j['opts'] as List?) ?? []).map((e) => '$e').toList(),
        series: j['series'] is Map ? Map<String, dynamic>.from(j['series'] as Map) : null,
      );

  Map<String, dynamic>? _find(String id) {
    for (final j in jobs) {
      if (j['id'] == id) return j;
    }
    return null;
  }

  void pause(String id) {
    final j = _find(id);
    if (j == null) return;
    if (_active == id) {
      _stop = true;
    } else if (j['state'] == 'queued') {
      j['state'] = 'paused';
      s.save();
      notifyListeners();
    }
  }

  void resume(String id) {
    final j = _find(id);
    if (j != null && (j['state'] == 'paused' || j['state'] == 'error')) {
      j['state'] = 'queued';
      j['error'] = '';
      s.save();
      notifyListeners();
      _next();
    }
  }

  Future<void> remove(String id) async {
    final j = _find(id);
    if (j == null) return;
    _raw().remove(j);
    if (_active == id) {
      _removed.add(id);
      _stop = true;
    } else {
      for (final p in ['${j['path']}.part', '${j['path']}']) {
        try {
          await File(p).delete();
        } catch (_) {}
      }
    }
    s.save();
    notifyListeners();
  }

  void _next() {
    if (_active != null) return;
    final q = jobs.where((x) => x['state'] == 'queued');
    final j = q.isEmpty ? null : q.first;
    if (j == null) return;
    _active = '${j['id']}';
    _stop = false;
    j['state'] = 'downloading';
    j['error'] = '';
    notifyListeners();
    unawaited(_work(j));
  }

  Future<void> _work(Map<String, dynamic> j) async {
    final part = File('${j['path']}.part');
    var state = 'done';
    var err = '';
    var tries = 0;
    final client = HttpClient()
      ..badCertificateCallback = ((c, h, p) => true)
      ..connectionTimeout = const Duration(seconds: 25);
    while (true) {
      try {
        await part.parent.create(recursive: true);
        var have = await part.exists() ? await part.length() : 0;
        final req = await client.getUrl(Uri.parse('${j['url']}'));
        req.headers.set('User-Agent', kUserAgent);
        if (have > 0) req.headers.set('Range', 'bytes=$have-');
        final resp = await req.close();
        if (resp.statusCode >= 400) throw HttpException('Erreur HTTP ${resp.statusCode}');
        final ct = (resp.headers.contentType?.mimeType ?? '').toLowerCase();
        if (ct.contains('text/html') || ct.contains('mpegurl') || ct.contains('json')) {
          throw const HttpException('ce flux ne peut pas être téléchargé');
        }
        if (have > 0 && resp.statusCode != 206) have = 0;
        final cr = resp.headers.value('content-range') ?? '';
        final m = RegExp(r'/(\d+)').firstMatch(cr);
        if (m != null) {
          j['size'] = int.parse(m.group(1)!);
        } else if (resp.contentLength > 0) {
          j['size'] = resp.contentLength + (resp.statusCode == 206 ? have : 0);
        }
        j['done'] = have;
        final raf = await part.open(mode: have > 0 ? FileMode.append : FileMode.write);
        var t0 = DateTime.now(), b0 = have, last = DateTime.now();
        try {
          await for (final chunk in resp) {
            if (_stop) {
              state = 'paused';
              break;
            }
            await raf.writeFrom(chunk);
            j['done'] = (j['done'] as int) + chunk.length;
            final now = DateTime.now();
            final dt = now.difference(t0).inMilliseconds;
            if (dt >= 2000) {
              speed['${j['id']}'] = ((j['done'] as int) - b0) * 1000 / dt;
              t0 = now;
              b0 = j['done'] as int;
            }
            if (now.difference(last).inMilliseconds >= 500) {
              last = now;
              notifyListeners();
            }
          }
        } finally {
          await raf.close();
        }
        if (state == 'paused') break;
        final size = (j['size'] as num?) ?? 0;
        if (size > 0 && (j['done'] as int) < size) throw const HttpException('connexion interrompue');
        await part.rename('${j['path']}');
        state = 'done';
        break;
      } catch (e) {
        if (_stop) {
          state = 'paused';
          break;
        }
        tries++;
        if (tries <= 6) {
          await Future.delayed(Duration(seconds: 3 * tries));
          continue;
        }
        state = 'error';
        err = '$e'.replaceFirst('HttpException: ', '');
        break;
      }
    }
    client.close(force: true);
    speed.remove('${j['id']}');
    final id = '${j['id']}';
    if (_removed.remove(id)) {
      for (final p in ['${j['path']}.part', '${j['path']}']) {
        try {
          await File(p).delete();
        } catch (_) {}
      }
    } else {
      j['state'] = state;
      j['error'] = err;
    }
    _active = null;
    _stop = false;
    s.save();
    notifyListeners();
    if (state == 'done') onFinished?.call('Téléchargement terminé ✓  ${j['name']}');
    if (state == 'error') onFinished?.call('Échec du téléchargement : ${j['name']}');
    Timer(const Duration(milliseconds: 300), _next);
  }

  /// Message à afficher (fin de téléchargement).
  void Function(String msg)? onFinished;
}
