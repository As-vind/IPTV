// Administration web locale (même page et même API que la version Windows : windows/admin.html).
// Accessible uniquement depuis le réseau local, protégée par un code PIN.
import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'dart:math';
import 'dart:typed_data';

import 'package:flutter/services.dart' show rootBundle;

import 'channels.dart';
import 'countries.dart';
import 'models.dart';
import 'playlist_import.dart';
import 'store.dart';
import 'text.dart';

class AdminServer {
  final AppState s;
  HttpServer? _srv;
  int port = 8080;
  String pin = '';
  final Map<String, DateTime> tokens = {};
  final Map<String, (int, DateTime)> _fails = {};
  List<String> urls = [];
  String? _html;

  AdminServer(this.s);

  bool get running => _srv != null;

  Future<void> start(int wanted, String code) async {
    pin = code;
    if (_srv != null) return;
    _html ??= await rootBundle.loadString('windows/admin.html');
    Object? last;
    for (final p in [wanted, for (var i = 8081; i < 8100; i++) i]) {
      try {
        _srv = await HttpServer.bind(InternetAddress.anyIPv4, p);
        port = p;
        break;
      } catch (e) {
        last = e;
      }
    }
    if (_srv == null) throw SocketException('aucun port libre ($last)');
    final ip = await LanImport.localIp();
    urls = [if (ip != null) 'http://$ip:$port', 'http://127.0.0.1:$port'];
    _srv!.listen(_handle, onError: (_) {});
  }

  Future<void> stop() async {
    await _srv?.close(force: true);
    _srv = null;
    urls = [];
  }

  static bool _local(InternetAddress a) {
    if (a.isLoopback || a.isLinkLocal) return true;
    final b = a.rawAddress;
    if (a.type == InternetAddressType.IPv4) {
      return b[0] == 10 || (b[0] == 172 && b[1] >= 16 && b[1] <= 31) || (b[0] == 192 && b[1] == 168);
    }
    return (b[0] & 0xfe) == 0xfc; // IPv6 privée (fc00::/7)
  }

  Future<void> _send(HttpRequest rq, int code, Object body, {String? ctype, Map<String, String> extra = const {}}) async {
    final r = rq.response;
    r.statusCode = code;
    r.headers.set('Cache-Control', 'no-store');
    r.headers.set('X-Content-Type-Options', 'nosniff');
    r.headers.set('Referrer-Policy', 'no-referrer');
    extra.forEach(r.headers.set);
    if (body is String && ctype != null) {
      r.headers.contentType = ContentType.parse(ctype);
      r.add(utf8.encode(body));
    } else {
      r.headers.contentType = ContentType.json;
      r.add(utf8.encode(jsonEncode(body)));
    }
    await r.close();
  }

  Future<Uint8List> _body(HttpRequest rq, int limit) async {
    final b = BytesBuilder(copy: false);
    await for (final c in rq) {
      b.add(c);
      if (b.length > limit) throw const FormatException('envoi trop volumineux');
    }
    return b.takeBytes();
  }

  Future<void> _handle(HttpRequest rq) async {
    final ip = rq.connectionInfo?.remoteAddress;
    try {
      if (ip == null || !_local(ip)) return await _send(rq, 403, {'error': 'réseau local uniquement'});
      final path = rq.uri.path;
      final q = rq.uri.queryParameters;
      if (rq.method == 'GET' && (path == '/' || path == '/index.html')) {
        return await _send(rq, 200, _html ?? '', ctype: 'text/html; charset=utf-8', extra: {
          'Content-Security-Policy':
              "default-src 'self'; img-src * data:; style-src 'self' 'unsafe-inline'; script-src 'self' 'unsafe-inline'",
        });
      }
      if (path == '/api/login' && rq.method == 'POST') {
        final key = ip.address;
        final f = _fails[key];
        if (f != null && f.$2.isAfter(DateTime.now())) {
          return await _send(rq, 429, {'error': 'trop d’essais, réessayez dans 30 s'});
        }
        String code = '';
        try {
          code = '${(jsonDecode(utf8.decode(await _body(rq, 4096))) as Map)['pin'] ?? ''}';
        } catch (_) {}
        if (code.length == pin.length && code == pin) {
          _fails.remove(key);
          final r = Random.secure();
          final tok = base64Url.encode(List.generate(24, (_) => r.nextInt(256)));
          tokens[tok] = DateTime.now().add(const Duration(hours: 12));
          s.log('Connexion à l’administration depuis ${ip.address}');
          return await _send(rq, 200, {'token': tok});
        }
        final n = (f?.$1 ?? 0) + 1;
        _fails[key] = (n, n >= 5 ? DateTime.now().add(const Duration(seconds: 30)) : DateTime.now());
        s.log('Code PIN incorrect depuis ${ip.address}');
        return await _send(rq, 401, {'error': 'code PIN incorrect'});
      }
      if (!path.startsWith('/api/')) return await _send(rq, 404, {'error': 'introuvable'});
      final tok = rq.headers.value('x-token') ?? '';
      final exp = tokens[tok];
      if (exp == null || exp.isBefore(DateTime.now())) return await _send(rq, 401, {'error': 'connexion requise'});
      tokens[tok] = DateTime.now().add(const Duration(hours: 12));
      final p = path.substring(5);
      if (p == 'logs') return await _send(rq, 200, {'lines': s.appLog});
      if (p == 'backup') {
        final n = DateTime.now();
        return await _send(rq, 200, const JsonEncoder.withIndent(' ').convert(s.backupData()),
            ctype: 'application/json; charset=utf-8',
            extra: {'Content-Disposition': 'attachment; filename="iptv-player-sauvegarde-${n.year}${n.month}${n.day}.json"'});
      }
      if (p == 'upload' && rq.method == 'POST') {
        final name = Uri.decodeComponent(rq.headers.value('x-name') ?? 'liste.m3u');
        final data = await _body(rq, 200 * 1024 * 1024);
        final n = await countEntriesAsync(data);
        if (n == 0) return await _send(rq, 400, {'error': '« $name » n’est pas une liste M3U (aucune ligne #EXTINF).'});
        final id = AppState.newId();
        final file = await savePlaylist(s.dataDir, id, data);
        s.addSource({'id': id, 'type': 'm3u', 'name': name.replaceAll(RegExp(r'\.(m3u8?|txt)$', caseSensitive: false), ''), 'url': file, 'file': name});
        s.log('Liste envoyée depuis le navigateur : $name ($n entrées)');
        return await _send(rq, 200, {'id': id, 'entries': n});
      }
      Map<String, dynamic> body = {};
      if (rq.method == 'POST') {
        final raw = await _body(rq, 20 * 1024 * 1024);
        if (raw.isNotEmpty) body = Map<String, dynamic>.from(jsonDecode(utf8.decode(raw)) as Map);
      }
      final res = await _api(rq.method, p, q, body);
      if (rq.method == 'POST') s.log('$p : ok');
      return await _send(rq, 200, res ?? {'ok': true});
    } on FormatException catch (e) {
      await _send(rq, 400, {'error': e.message});
    } on ArgumentError catch (e) {
      await _send(rq, 400, {'error': '${e.message}'});
    } catch (e) {
      s.log('Erreur ${rq.uri.path} : $e');
      try {
        await _send(rq, 500, {'error': '$e'});
      } catch (_) {}
    }
  }

  // ---------------------------------------------------------------- API
  Future<Object?> _api(String method, String p, Map<String, String> q, Map<String, dynamic> body) async {
    if (method == 'GET') {
      switch (p) {
        case 'state':
          return _state();
        case 'categories':
          return _categories(q['kind'] ?? 'live');
        case 'channels':
          return _channels(q['group'] ?? '', q['q'] ?? '', int.tryParse(q['limit'] ?? '') ?? 300, q['favs'] == '1');
        case 'diag':
          return s.diag?.call() ?? {'état': 'arrêté'};
      }
      throw const FormatException('demande inconnue');
    }
    switch (p) {
      case 'settings':
        final out = <String, dynamic>{};
        body.forEach((k, v) => out[k] = s.setSetting(k, v));
        return out;
      case 'sources/add':
        return _addSource(body);
      case 'categories':
        s.setHiddenGroups([for (final g in (body['hidden'] as List?) ?? const []) '$g'],
            body['order'] is List ? [for (final g in body['order'] as List) '$g'] : null);
        return null;
      case 'favorites':
        final url = '${body['url'] ?? ''}';
        if (!s.byUrl.containsKey(url)) throw const FormatException('chaîne introuvable');
        if ((body['on'] == true) != s.isFav(url)) s.toggleFavorite(url);
        return null;
      case 'maintenance':
        return _maintenance('${body['action'] ?? ''}', body);
      case 'restore':
        await s.restore(Map<String, dynamic>.from((body['config'] ?? body) as Map));
        return null;
    }
    if (p.startsWith('sources/')) {
      final act = p.substring(8);
      final sid = '${body['id'] ?? ''}';
      final src = s.sources.where((e) => e['id'] == sid).firstOrNull;
      if (src == null) throw const FormatException('source introuvable');
      switch (act) {
        case 'select':
          unawaited(s.setSource(sid));
        case 'refresh':
          unawaited(s.setSource(sid, force: true));
        case 'delete':
          await s.deleteSource(sid);
        case 'rename':
          final n = '${body['name'] ?? ''}'.trim();
          if (n.isNotEmpty) src['name'] = n.length > 80 ? n.substring(0, 80) : n;
          s.save();
          s.touch();
        case 'epg':
          final u = '${body['url'] ?? ''}'.trim();
          if (u.isNotEmpty && !RegExp(r'^https?://', caseSensitive: false).hasMatch(u)) {
            throw const FormatException("l'adresse du guide doit commencer par http:// ou https://");
          }
          if (u.isEmpty) {
            src.remove('epg');
          } else {
            src['epg'] = u;
          }
          s.guides.remove(sid);
          s.save();
          if (s.epgUrl(src).isNotEmpty) unawaited(s.loadGuide(src, force: true));
        default:
          throw const FormatException('action inconnue');
      }
      return null;
    }
    throw const FormatException('demande inconnue');
  }

  Map<String, dynamic> _state() {
    final cur = s.currentSource?['id'];
    final c = <String, int>{};
    for (final i in s.items) {
      c[i.kind] = (c[i.kind] ?? 0) + 1;
    }
    return {
      'app': kAppTitle,
      'version': kAppVersion,
      'platform': Platform.isAndroid ? 'Android' : Platform.isIOS ? 'iPhone / iPad' : Platform.operatingSystem,
      'sources': [
        for (final src in s.sources)
          {
            'id': src['id'], 'name': src['name'], 'type': src['type'], 'current': src['id'] == cur,
            'file': src['file'] ?? '', 'epg': src['epg'] ?? '', 'epg_auto': src['epg_auto'] ?? '',
            'url': src['type'] == 'm3u' && src['file'] == null ? src['url'] ?? '' : '',
            'server': src['server'] ?? '', 'updated': src['updated_ts'] ?? 0,
          }
      ],
      'counts': {
        'live': c['live'] ?? 0,
        'live_raw': s.rawItems.where((i) => i.kind == 'live').length,
        'movie': c['movie'] ?? 0,
        'series': c['series'] ?? 0,
      },
      'settings': [
        for (final st in kSettings)
          {
            'section': st.section, 'key': st.key, 'label': st.label, 'type': st.type, 'default': st.def,
            'value': s.pset[st.key] ?? st.def,
            'choices': st.type == 'choice' ? [for (final c in st.choices) [c.$1, c.$2]] : null,
            'min': st.type == 'int' || st.type == 'float' ? st.lo : null,
            'max': st.type == 'int' || st.type == 'float' ? st.hi : null,
          }
      ],
      'profile': s.profile?['name'] ?? '',
      'hardware': {'cores': s.cores, 'ram_mb': s.ramMb, 'tier': s.hwTier},
      'favorites': s.favorites.length,
      'hidden_groups': s.cfg['hidden_groups'] ?? [],
    };
  }

  List<Map<String, dynamic>> _categories(String kind) {
    final counts = <String, int>{};
    for (final i in s.rawItems) {
      if (i.kind == kind) counts[i.group] = (counts[i.group] ?? 0) + 1;
    }
    final hidden = ((s.cfg['hidden_groups'] as List?) ?? const []).map((e) => '$e').toSet();
    final order = {for (final (i, g) in ((s.cfg['group_order'] as List?) ?? const []).indexed) '$g': i};
    final rows = [
      for (final e in counts.entries)
        {
          'group': e.key, 'name': prettyGroup(e.key), 'count': e.value, 'hidden': hidden.contains(e.key),
          'country': kind == 'live' ? countryName(detectCountry(group: e.key)) : '',
        }
    ];
    rows.sort((a, b) {
      final oa = order[a['group']] ?? 1000000, ob = order[b['group']] ?? 1000000;
      return oa != ob ? oa.compareTo(ob) : (b['count'] as int).compareTo(a['count'] as int);
    });
    return rows;
  }

  List<Map<String, dynamic>> _channels(String group, String query, int limit, bool favsOnly) {
    final terms = norm(query).split(RegExp(r'\s+')).where((e) => e.isNotEmpty).toList();
    final out = <Map<String, dynamic>>[];
    for (final it in s.byKind['live'] ?? const <Item>[]) {
      if (group.isNotEmpty && it.group != group) continue;
      if (favsOnly && !s.isFav(it.url)) continue;
      if (terms.isNotEmpty && !terms.every(it.q.contains)) continue;
      final vs = it.variants.isEmpty ? [Variant(url: it.url, name: it.name, q: 0)] : it.variants;
      final rows = [for (final v in vs) s.stats.row(v.url)];
      out.add({
        'url': it.url, 'name': it.title.isEmpty ? it.name : it.title, 'group': prettyGroup(it.group), 'logo': it.logo,
        'qualities': it.qlabels.isNotEmpty ? it.qlabels : (kQLabels[vs.first.q] ?? ''), 'variants': vs.length,
        'fav': s.isFav(it.url), 'dead': vs.every((v) => s.stats.dead(v.url)),
        'ok': rows.fold<int>(0, (a, r) => a + r[0]), 'fail': rows.fold<int>(0, (a, r) => a + r[1]),
      });
      if (out.length >= limit) break;
    }
    return out;
  }

  Map<String, dynamic> _addSource(Map<String, dynamic> b) {
    final id = AppState.newId();
    final name = '${b['name'] ?? ''}'.trim();
    Map<String, dynamic> src;
    if (b['type'] == 'xtream') {
      final server = '${b['server'] ?? ''}'.trim(), user = '${b['user'] ?? ''}'.trim(), pwd = '${b['password'] ?? ''}'.trim();
      if (server.isEmpty || user.isEmpty || pwd.isEmpty) throw const FormatException('serveur, identifiant et mot de passe requis');
      src = {
        'id': id, 'type': 'xtream', 'server': server, 'user': user, 'password': pwd, 'live_ext': b['live_ext'] ?? 'ts',
        'name': name.isNotEmpty ? name : (Uri.tryParse(server.contains('://') ? server : 'http://$server')?.host ?? server),
      };
    } else {
      final url = '${b['url'] ?? ''}'.trim();
      if (!RegExp(r'^https?://', caseSensitive: false).hasMatch(url)) {
        throw const FormatException('le lien doit commencer par http:// ou https://');
      }
      final u = Uri.parse(url);
      final qp = u.queryParameters;
      if (u.path.toLowerCase().contains('get.php') && (qp['username'] ?? '').isNotEmpty && (qp['password'] ?? '').isNotEmpty) {
        src = {
          'id': id, 'type': 'xtream', 'name': name.isNotEmpty ? name : u.host, 'server': '${u.scheme}://${u.authority}',
          'user': qp['username'], 'password': qp['password'], 'live_ext': 'ts',
        };
      } else {
        src = {'id': id, 'type': 'm3u', 'name': name.isNotEmpty ? name : (u.host.isEmpty ? 'Liste M3U' : u.host), 'url': url};
      }
    }
    final epg = '${b['epg'] ?? ''}'.trim();
    if (epg.isNotEmpty) src['epg'] = epg;
    s.addSource(src);
    s.log('Source ajoutée depuis l’administration web : ${src['name']}');
    return {'id': id};
  }

  Future<Object?> _maintenance(String act, Map<String, dynamic> body) async {
    switch (act) {
      case 'refresh_all':
        final cur = s.currentSource?['id'];
        if (cur != null) unawaited(s.setSource('$cur', force: true));
      case 'clear_cache':
        unawaited(s.cleanNow());
      case 'check_favorites':
        unawaited(s.checkItems((s.byKind['live'] ?? const <Item>[]).where((i) => s.isFav(i.url)).toList()));
      case 'check_group':
        final g = '${body['group'] ?? ''}';
        unawaited(s.checkItems((s.byKind['live'] ?? const <Item>[]).where((i) => i.group == g).take(150).toList()));
      case 'reset_settings':
        s.resetSettings();
      case 'backup_now':
        await s.autoBackup();
      default:
        throw const FormatException('action inconnue');
    }
    return null;
  }
}
