// Client Xtream Codes (player_api.php).
import 'dart:convert';

import 'models.dart';
import 'net.dart';

class XtreamClient {
  late final String base;
  final String user;
  final String pwd;
  final String liveExt;

  XtreamClient(String server, this.user, this.pwd, {this.liveExt = 'ts'}) {
    var s = server.trim();
    while (s.endsWith('/')) {
      s = s.substring(0, s.length - 1);
    }
    if (!RegExp(r'^https?://', caseSensitive: false).hasMatch(s)) s = 'http://$s';
    s = s.replaceFirst(RegExp(r'/(player_api|get)\.php.*$', caseSensitive: false), '');
    base = s;
  }

  factory XtreamClient.of(Map<String, dynamic> src) => XtreamClient(
      '${src['server']}', '${src['user']}'.trim(), '${src['password']}'.trim(),
      liveExt: '${src['live_ext'] ?? 'ts'}');

  String get _qu => Uri.encodeComponent(user);
  String get _qp => Uri.encodeComponent(pwd);

  Future<dynamic> api([String? action, Map<String, String> params = const {}]) {
    final q = {'username': user, 'password': pwd, if (action != null) 'action': action, ...params};
    return getJson('$base/player_api.php?${Uri(queryParameters: q).query}');
  }

  static List<dynamic> list(dynamic v) {
    if (v is Map) return v.values.toList();
    if (v is List) return v;
    return const [];
  }

  static String _s(dynamic v) => v == null ? '' : '$v';

  Future<(List<Item>, String)> loadAll() async {
    final info = await api();
    final ui = info is Map ? info['user_info'] : null;
    if (ui is! Map || '${ui['auth']}' != '1') {
      throw Exception('Identifiants refusés par le serveur (ou serveur injoignable).');
    }
    final meta = <String>[];
    if (ui['status'] != null) meta.add('Statut : ${ui['status']}');
    final exp = int.tryParse('${ui['exp_date'] ?? ''}');
    if (exp != null) {
      final d = DateTime.fromMillisecondsSinceEpoch(exp * 1000);
      meta.add('Expire le ${d.day.toString().padLeft(2, '0')}/${d.month.toString().padLeft(2, '0')}/${d.year}');
    }
    if (ui['max_connections'] != null) meta.add('Connexions max : ${ui['max_connections']}');

    final items = <Item>[];
    const plan = [
      ['live', 'get_live_categories', 'get_live_streams'],
      ['movie', 'get_vod_categories', 'get_vod_streams'],
      ['series', 'get_series_categories', 'get_series'],
    ];
    for (final p in plan) {
      final kind = p[0];
      var cats = <String, String>{};
      try {
        for (final c in list(await api(p[1]))) {
          if (c is Map) cats['${c['category_id']}'] = _s(c['category_name']);
        }
      } catch (_) {}
      List<dynamic> streams;
      try {
        streams = list(await api(p[2]));
      } catch (_) {
        continue;
      }
      for (final s in streams) {
        if (s is! Map) continue;
        final group = cats['${s['category_id']}'] ?? 'Sans catégorie';
        final name = _s(s['name']);
        if (kind == 'live') {
          final sid = _s(s['stream_id']);
          items.add(Item.make(name, '$base/live/$_qu/$_qp/$sid.$liveExt',
              logo: _s(s['stream_icon']), group: group, kind: kind, streamId: sid, tvgId: _s(s['epg_channel_id'])));
        } else if (kind == 'movie') {
          final sid = _s(s['stream_id']);
          final ext = _s(s['container_extension']).isEmpty ? 'mp4' : _s(s['container_extension']);
          items.add(Item.make(name, '$base/movie/$_qu/$_qp/$sid.$ext',
              logo: _s(s['stream_icon']), group: group, kind: kind, streamId: sid,
              rating: _s(s['rating']), added: _s(s['added'])));
        } else {
          final sid = _s(s['series_id']);
          items.add(Item.make(name, 'xtream-series:$sid',
              logo: _s(s['cover']), group: group, kind: kind, seriesId: sid,
              rating: _s(s['rating']), added: _s(s['last_modified'])));
        }
      }
    }
    return (items, meta.join('  ·  '));
  }

  Future<Map<String, dynamic>> vodInfo(String streamId) async {
    final d = await api('get_vod_info', {'vod_id': streamId});
    return d is Map ? Map<String, dynamic>.from(d) : {};
  }

  Future<Map<String, dynamic>> seriesInfo(String seriesId) async {
    final d = await api('get_series_info', {'series_id': seriesId});
    return d is Map ? Map<String, dynamic>.from(d) : {};
  }

  String episodeUrl(String epId, String ext) => '$base/series/$_qu/$_qp/$epId.${ext.isEmpty ? 'mp4' : ext}';

  Future<List<Map<String, dynamic>>> shortEpg(String streamId, {int limit = 3}) async {
    final d = await api('get_short_epg', {'stream_id': streamId, 'limit': '$limit'});
    final out = <Map<String, dynamic>>[];
    if (d is! Map) return out;
    String dec(dynamic v) {
      if (v == null) return '';
      try {
        return utf8.decode(base64.decode('$v'), allowMalformed: true);
      } catch (_) {
        return '$v';
      }
    }

    for (final e in list(d['epg_listings'])) {
      if (e is! Map) continue;
      out.add({
        'title': dec(e['title']),
        'desc': dec(e['description']),
        'start': '${e['start'] ?? ''}',
        'end': '${e['end'] ?? ''}',
        'start_ts': int.tryParse('${e['start_timestamp'] ?? ''}'),
        'stop_ts': int.tryParse('${e['stop_timestamp'] ?? ''}'),
      });
    }
    return out;
  }
}
