// Serveur Jellyfin (médiathèque locale) : films, séries et épisodes, lus directement depuis le serveur.
import 'dart:convert';
import 'dart:math';

import 'models.dart';
import 'net.dart';

class JellyfinError implements Exception {
  final String message;
  JellyfinError(this.message);
  @override
  String toString() => message;
}

class JellyfinClient {
  final String base;
  final String user;
  final String pwd;
  String token;
  String uid;
  final String deviceId;

  JellyfinClient(this.base, this.user, this.pwd, {this.token = '', this.uid = '', required this.deviceId});

  /// Construit le client depuis une source enregistrée ({server, user, password, token?, uid?, device?}).
  factory JellyfinClient.of(Map<String, dynamic> src) {
    var srv = '${src['server'] ?? ''}'.trim();
    if (!srv.contains('://')) srv = 'http://$srv';
    srv = srv.replaceAll(RegExp(r'/+$'), '').replaceAll(RegExp(r'/web(/index\.html)?.*$'), '');
    var dev = '${src['device'] ?? ''}';
    if (dev.isEmpty) {
      dev = List.generate(16, (_) => Random().nextInt(16).toRadixString(16)).join();
      src['device'] = dev;
    }
    return JellyfinClient(srv, '${src['user'] ?? ''}', '${src['password'] ?? ''}',
        token: '${src['token'] ?? ''}', uid: '${src['uid'] ?? ''}', deviceId: dev);
  }

  String get _authHeader =>
      'MediaBrowser Client="Asvind IPTV", Device="IPTV Player", DeviceId="$deviceId", Version="2.8"'
      '${token.isNotEmpty ? ', Token="$token"' : ''}';

  Map<String, String> get _h => {'X-Emby-Authorization': _authHeader, if (token.isNotEmpty) 'X-Emby-Token': token};

  Future<void> login() async {
    try {
      final r = await postJson('$base/Users/AuthenticateByName', {'Username': user, 'Pw': pwd}, headers: _h);
      token = '${r['AccessToken'] ?? ''}';
      uid = '${(r['User'] as Map?)?['Id'] ?? ''}';
      if (token.isEmpty || uid.isEmpty) throw JellyfinError('Réponse de connexion Jellyfin inattendue.');
    } on HttpStatusError catch (e) {
      if (e.code == 401 || e.code == 400) throw JellyfinError('Jellyfin : identifiant ou mot de passe refusé.');
      throw JellyfinError('Jellyfin : le serveur a répondu ${e.code}.');
    }
  }

  Future<dynamic> _get(String path, [Map<String, String> q = const {}, Duration timeout = const Duration(seconds: 120)]) async {
    if (token.isEmpty) await login();
    final url = '$base$path${q.isEmpty ? '' : '?${Uri(queryParameters: q).query}'}';
    try {
      return await getJson(url, headers: _h, timeout: timeout);
    } on HttpStatusError catch (e) {
      if (e.code != 401) rethrow;
      token = '';
      await login(); // jeton expiré : on se reconnecte une fois
      return getJson(url, headers: _h, timeout: timeout);
    }
  }

  /// Lecture directe du fichier (aucune conversion côté serveur).
  String streamUrl(String id) => '$base/Videos/$id/stream?static=true&api_key=$token';

  String image(String id, {String type = 'Primary', int w = 500, String tag = ''}) =>
      '$base/Items/$id/Images/$type?maxWidth=$w&quality=90${tag.isNotEmpty ? '&tag=$tag' : ''}';

  List<Map<String, dynamic>> _items(dynamic r) =>
      ((r is Map ? r['Items'] : r) as List? ?? const []).whereType<Map>().map((e) => Map<String, dynamic>.from(e)).toList();

  /// Toute la médiathèque. Renvoie (éléments, info du compte).
  Future<(List<Item>, String)> loadAll() async {
    if (token.isEmpty || uid.isEmpty) await login();
    final views = _items(await _get('/Users/$uid/Views'));
    final out = <Item>[];
    final seriesById = <String, Item>{};
    var nMovies = 0, nSeries = 0, nEps = 0;
    for (final v in views) {
      final ct = '${v['CollectionType'] ?? ''}';
      final lib = '${v['Name'] ?? 'Jellyfin'}';
      final vid = '${v['Id']}';
      if (ct == 'movies' || ct == 'homevideos' || ct == 'musicvideos' || ct.isEmpty) {
        final r = _items(await _get('/Users/$uid/Items', {
          'ParentId': vid, 'Recursive': 'true', 'IncludeItemTypes': ct == 'movies' || ct.isEmpty ? 'Movie' : 'Movie,Video,MusicVideo',
          'Fields': 'Genres,DateCreated,ProductionYear,CommunityRating', 'EnableImageTypes': 'Primary,Backdrop', 'ImageTypeLimit': '1',
        }));
        for (final m in r) {
          final id = '${m['Id']}';
          final year = m['ProductionYear'] != null ? ' (${m['ProductionYear']})' : '';
          out.add(Item.make('${m['Name']}$year', streamUrl(id),
              logo: image(id, tag: '${(m['ImageTags'] as Map?)?['Primary'] ?? ''}'),
              group: _group(m, lib), kind: 'movie', streamId: 'jf:$id',
              rating: '${m['CommunityRating'] ?? ''}', added: _added(m)));
          nMovies++;
        }
      } else if (ct == 'tvshows') {
        final r = _items(await _get('/Users/$uid/Items', {
          'ParentId': vid, 'Recursive': 'true', 'IncludeItemTypes': 'Series',
          'Fields': 'Genres,DateCreated,ProductionYear,CommunityRating', 'EnableImageTypes': 'Primary', 'ImageTypeLimit': '1',
        }));
        for (final m in r) {
          final id = '${m['Id']}';
          final it = Item.make('${m['Name']}', 'jellyfin-series:$id',
              logo: image(id, tag: '${(m['ImageTags'] as Map?)?['Primary'] ?? ''}'),
              group: _group(m, lib), kind: 'series', seriesId: 'jf:$id',
              rating: '${m['CommunityRating'] ?? ''}', added: _added(m));
          it.episodes = {};
          seriesById[id] = it;
          out.add(it);
          nSeries++;
        }
        final eps = _items(await _get('/Users/$uid/Items', {
          'ParentId': vid, 'Recursive': 'true', 'IncludeItemTypes': 'Episode',
          'Fields': 'Overview', 'EnableImageTypes': 'Primary', 'ImageTypeLimit': '1',
        }, const Duration(seconds: 240)));
        for (final e in eps) {
          final s = seriesById['${e['SeriesId']}'];
          if (s == null) continue;
          final id = '${e['Id']}';
          final season = '${e['ParentIndexNumber'] ?? 1}';
          final ticks = (e['RunTimeTicks'] as num?)?.toInt() ?? 0;
          s.episodes!.putIfAbsent(season, () => []).add(Ep(
                name: '${e['Name'] ?? ''}',
                number: (e['IndexNumber'] as num?)?.toInt() ?? 0,
                url: streamUrl(id),
                plot: '${e['Overview'] ?? ''}',
                runtime: ticks ~/ 600000000,
                still: (e['ImageTags'] as Map?)?['Primary'] != null ? image(id, w: 400) : '',
              ));
          nEps++;
        }
        for (final s in seriesById.values) {
          for (final l in s.episodes!.values) {
            l.sort((a, b) => a.number.compareTo(b.number));
          }
        }
      }
    }
    final info = jsonEncode({'type': 'jellyfin', 'server': base, 'movies': nMovies, 'series': nSeries, 'episodes': nEps});
    return (out, info);
  }

  static String _group(Map<String, dynamic> m, String lib) {
    final g = (m['Genres'] as List?)?.whereType<String>().toList() ?? const [];
    return g.isNotEmpty ? g.first : lib;
  }

  static String _added(Map<String, dynamic> m) {
    final d = DateTime.tryParse('${m['DateCreated'] ?? ''}');
    return d == null ? '' : '${d.millisecondsSinceEpoch ~/ 1000}';
  }
}

/// Jellyfin : lien de lecture directe du fichier (`/Videos/<id>/stream?static=true&api_key=…`).
bool jellyfinIsDirect(String u) => u.contains('/Videos/') && u.contains('static=true') && u.contains('api_key=');

/// Repli Jellyfin quand l'appareil ne sait pas lire le fichier tel quel : le serveur le convertit à la volée (HLS H.264/AAC).
String jellyfinTranscodeUrl(String u) {
  final m = RegExp(r'/Videos/([^/]+)/stream\?').firstMatch(u);
  final key = RegExp(r'api_key=([^&]+)').firstMatch(u)?.group(1) ?? '';
  if (m == null) return u;
  final id = m.group(1)!;
  return '${u.substring(0, m.start)}/Videos/$id/master.m3u8?MediaSourceId=$id&api_key=$key'
      '&VideoCodec=h264&AudioCodec=aac,mp3&VideoBitrate=20000000&AudioBitrate=320000'
      '&TranscodingMaxAudioChannels=6&SegmentContainer=ts&BreakOnNonKeyFrames=true&DeviceId=asvind-tv';
}
