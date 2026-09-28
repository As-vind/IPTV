// Fiches films / séries / acteurs : données Xtream enrichies par TMDB.
import 'models.dart';
import 'net.dart';
import 'text.dart';
import 'xtream.dart';

const String kTmdbApi = 'https://api.themoviedb.org/3';
const String kTmdbImg = 'https://image.tmdb.org/t/p/';

String tmdbImg(dynamic path, [String size = 'w500']) =>
    (path == null || '$path'.isEmpty) ? '' : '$kTmdbImg$size$path';

class Tmdb {
  final String key;
  final String lang;
  Tmdb(String k, [String l = 'fr-FR'])
      : key = k.trim(),
        lang = l.isEmpty ? 'fr-FR' : l;

  Future<Map<String, dynamic>> get(String path, [Map<String, String> params = const {}]) async {
    final p = <String, String>{'language': lang, ...params};
    final headers = <String, String>{'Accept': 'application/json'};
    if (key.length > 40) {
      headers['Authorization'] = 'Bearer $key';
    } else {
      p['api_key'] = key;
    }
    final d = await getJson('$kTmdbApi$path?${Uri(queryParameters: p).query}',
        headers: headers, timeout: const Duration(seconds: 20));
    return d is Map ? Map<String, dynamic>.from(d) : {};
  }

  Future<int?> search(String kind, String title, String year) async {
    final params = <String, String>{'query': title, 'include_adult': 'false'};
    if (year.isNotEmpty) params[kind == 'movie' ? 'year' : 'first_air_date_year'] = year;
    var res = (await get('/search/$kind', params))['results'] as List? ?? [];
    if (res.isEmpty && year.isNotEmpty) {
      res = (await get('/search/$kind', {'query': title}))['results'] as List? ?? [];
    }
    return res.isEmpty ? null : ((res.first as Map)['id'] as num?)?.toInt();
  }

  Future<Map<String, dynamic>> movie(int id) => get('/movie/$id',
      {'append_to_response': 'credits,videos,release_dates', 'include_video_language': '${lang.substring(0, 2)},en,null'});
  Future<Map<String, dynamic>> tv(int id) => get('/tv/$id',
      {'append_to_response': 'credits,videos,content_ratings', 'include_video_language': '${lang.substring(0, 2)},en,null'});
  Future<Map<String, dynamic>> season(int id, int n) => get('/tv/$id/season/$n');

  Future<Map<String, dynamic>> person(int id) async {
    final d = await get('/person/$id', {'append_to_response': 'combined_credits'});
    if ('${d['biography'] ?? ''}'.trim().isEmpty && !lang.startsWith('en')) {
      try {
        d['biography'] = (await get('/person/$id', {'language': 'en-US'}))['biography'] ?? '';
      } catch (_) {}
    }
    return d;
  }

  Future<List<Map<String, dynamic>>> searchPerson(String name) async {
    final r = (await get('/search/person', {'query': name}))['results'] as List? ?? [];
    return r.whereType<Map>().map((e) => Map<String, dynamic>.from(e)).toList();
  }
}

String _yt(dynamic key) {
  final k = '${key ?? ''}';
  if (k.isEmpty) return '';
  return k.startsWith('http') ? k : 'https://www.youtube.com/watch?v=$k';
}

List<String> _splitList(dynamic s) {
  if (s is List) return s.map((e) => '$e'.trim()).where((e) => e.isNotEmpty).toList();
  return '${s ?? ''}'.split(RegExp(r'\s*[,/]\s*')).map((e) => e.trim()).where((e) => e.isNotEmpty).toList();
}

String _first(dynamic v) {
  if (v is List) return v.isEmpty ? '' : '${v.first}';
  return '${v ?? ''}';
}

int _toMinutes(Map info) {
  final secs = int.tryParse('${info['duration_secs'] ?? ''}') ?? 0;
  if (secs > 0) return secs ~/ 60;
  final d = '${info['duration'] ?? info['episode_run_time'] ?? ''}';
  final m = RegExp(r'^(\d+):(\d+)(?::(\d+))?$').firstMatch(d);
  if (m != null) {
    return m.group(3) != null ? int.parse(m.group(1)!) * 60 + int.parse(m.group(2)!) : int.parse(m.group(1)!);
  }
  final m2 = RegExp(r'^(\d+)').firstMatch(d);
  return m2 != null ? int.parse(m2.group(1)!) : 0;
}

void _mergeTmdb(Map<String, dynamic> meta, Map<String, dynamic> d, String kind, String lang2) {
  if (d.isEmpty) return;
  meta['tmdb_id'] = d['id'];
  meta['title'] = d['title'] ?? d['name'] ?? meta['title'];
  meta['original_title'] = d['original_title'] ?? d['original_name'] ?? '';
  final ov = '${d['overview'] ?? ''}'.trim();
  if (ov.isNotEmpty) meta['overview'] = ov;
  final genres = (d['genres'] as List? ?? []).whereType<Map>().map((g) => '${g['name'] ?? ''}').where((g) => g.isNotEmpty).toList();
  if (genres.isNotEmpty) meta['genres'] = genres;
  final va = d['vote_average'];
  if (va is num && va > 0) meta['rating'] = (va * 10).round() / 10;
  final date = '${d['release_date'] ?? d['first_air_date'] ?? ''}';
  if (date.length >= 4 && int.tryParse(date.substring(0, 4)) != null) meta['year'] = date.substring(0, 4);
  if (d['backdrop_path'] != null) meta['backdrop'] = tmdbImg(d['backdrop_path'], 'w1280');
  if (d['poster_path'] != null) meta['poster'] = tmdbImg(d['poster_path'], 'w500');
  if ('${d['tagline'] ?? ''}'.isNotEmpty) meta['tagline'] = d['tagline'];
  final credits = (d['credits'] as Map?) ?? {};
  final cast = <Map<String, dynamic>>[];
  for (final c in (credits['cast'] as List? ?? []).take(24)) {
    if (c is! Map) continue;
    cast.add({'name': '${c['name'] ?? ''}', 'role': '${c['character'] ?? ''}',
      'photo': tmdbImg(c['profile_path'], 'w185'), 'tmdb_id': c['id']});
  }
  if (cast.isNotEmpty) meta['cast'] = cast;
  var directors = (credits['crew'] as List? ?? [])
      .whereType<Map>().where((c) => c['job'] == 'Director').map((c) => '${c['name']}').toList();
  if (kind == 'tv' && d['created_by'] is List && (d['created_by'] as List).isNotEmpty) {
    directors = (d['created_by'] as List).whereType<Map>().map((c) => '${c['name']}').toList();
  }
  if (directors.isNotEmpty) meta['director'] = directors.take(3).join(', ');
  final vids = ((d['videos'] as Map?)?['results'] as List? ?? [])
      .whereType<Map>()
      .where((v) => v['site'] == 'YouTube' && (v['type'] == 'Trailer' || v['type'] == 'Teaser'))
      .toList();
  vids.sort((a, b) {
    int score(Map v) => (v['type'] == 'Trailer' ? 0 : 2) + (v['iso_639_1'] == lang2 ? 0 : 1);
    return score(a).compareTo(score(b));
  });
  if (vids.isNotEmpty) meta['trailer'] = _yt(vids.first['key']);
}

String _pickCert(List entries, String cc, String Function(Map) getter) {
  for (final c in [cc, 'FR', 'US']) {
    for (final e in entries.whereType<Map>()) {
      if (e['iso_3166_1'] == c) {
        final v = getter(e);
        if (v.isNotEmpty) return v;
      }
    }
  }
  return '';
}

Map<String, dynamic> _baseMeta(Item item, String kind) {
  final (title, year) = cleanTitle(item.name);
  return {
    'kind': kind, 'title': title, 'year': year, 'overview': '', 'genres': <String>[],
    'rating': item.rating, 'runtime': 0, 'age': '', 'backdrop': '', 'poster': item.logo,
    'trailer': '', 'director': '', 'cast': <Map<String, dynamic>>[],
  };
}

Future<Map<String, dynamic>> movieMeta(Map<String, dynamic>? src, Item item, String tmdbKey, String lang) async {
  final meta = _baseMeta(item, 'movie');
  dynamic tmdbId;
  if (src != null && src['type'] == 'xtream' && item.streamId.isNotEmpty) {
    try {
      final info = (await XtreamClient.of(src).vodInfo(item.streamId))['info'];
      if (info is Map) {
        meta['overview'] = '${info['plot'] ?? info['description'] ?? ''}'.trim();
        meta['genres'] = _splitList(info['genre']);
        if ('${info['rating'] ?? ''}'.isNotEmpty) meta['rating'] = '${info['rating']}';
        meta['runtime'] = _toMinutes(info);
        meta['director'] = '${info['director'] ?? ''}';
        meta['cast'] = _splitList(info['cast'] ?? info['actors'])
            .take(24).map((n) => <String, dynamic>{'name': n, 'role': '', 'photo': ''}).toList();
        meta['backdrop'] = _first(info['backdrop_path']);
        final poster = '${info['movie_image'] ?? info['cover_big'] ?? ''}';
        if (poster.isNotEmpty) meta['poster'] = poster;
        meta['trailer'] = _yt(info['youtube_trailer']);
        meta['age'] = '${info['age'] ?? info['mpaa_rating'] ?? ''}';
        final rd = '${info['releasedate'] ?? info['release_date'] ?? ''}';
        if (rd.length >= 4 && int.tryParse(rd.substring(0, 4)) != null) meta['year'] = rd.substring(0, 4);
        tmdbId = info['tmdb_id'] ?? info['tmdb'];
      }
    } catch (_) {}
  }
  if (tmdbKey.isNotEmpty) {
    final tm = Tmdb(tmdbKey, lang);
    try {
      var id = int.tryParse('${tmdbId ?? ''}');
      id ??= await tm.search('movie', '${meta['title']}', '${meta['year']}');
      if (id != null) {
        final d = await tm.movie(id);
        _mergeTmdb(meta, d, 'movie', lang.substring(0, 2));
        if (d['runtime'] is num && (d['runtime'] as num) > 0) meta['runtime'] = (d['runtime'] as num).toInt();
        final cc = lang.contains('-') ? lang.split('-').last.toUpperCase() : 'FR';
        final cert = _pickCert(((d['release_dates'] as Map?)?['results'] as List?) ?? [], cc, (e) {
          for (final r in (e['release_dates'] as List? ?? []).whereType<Map>()) {
            if ('${r['certification'] ?? ''}'.isNotEmpty) return '${r['certification']}';
          }
          return '';
        });
        if (cert.isNotEmpty) meta['age'] = cert;
      }
    } catch (_) {}
  }
  return meta;
}

String _epCleanName(String? name, String show) {
  var s = name ?? '';
  if (show.isNotEmpty && norm(s).startsWith(norm(show))) s = s.substring(show.length);
  s = s.replaceFirst(RegExp(r'^[\s\-|:._]*S\d{1,2}[\s._\-]*E\d{1,4}[\s\-|:._]*', caseSensitive: false), '');
  return s.trim().replaceAll(RegExp(r'^[\s\-|:._]+|[\s\-|:._]+$'), '');
}

Future<Map<String, dynamic>> seriesMeta(Map<String, dynamic>? src, Item item, String tmdbKey, String lang) async {
  final meta = _baseMeta(item, 'series');
  dynamic tmdbId;
  final seasons = <Map<String, dynamic>>[];
  if (item.seriesId.isNotEmpty && src != null && src['type'] == 'xtream') {
    final cl = XtreamClient.of(src);
    final data = await cl.seriesInfo(item.seriesId);
    final info = data['info'] is Map ? data['info'] as Map : {};
    meta['overview'] = '${info['plot'] ?? ''}'.trim();
    meta['genres'] = _splitList(info['genre']);
    if ('${info['rating'] ?? ''}'.isNotEmpty) meta['rating'] = '${info['rating']}';
    meta['director'] = '${info['director'] ?? ''}';
    meta['cast'] = _splitList(info['cast'])
        .take(24).map((n) => <String, dynamic>{'name': n, 'role': '', 'photo': ''}).toList();
    meta['backdrop'] = _first(info['backdrop_path']);
    final cover = '${info['cover'] ?? ''}';
    if (cover.isNotEmpty) meta['poster'] = cover;
    meta['trailer'] = _yt(info['youtube_trailer']);
    meta['runtime'] = _toMinutes(info);
    final rd = '${info['releaseDate'] ?? info['release_date'] ?? ''}';
    if (rd.length >= 4 && int.tryParse(rd.substring(0, 4)) != null) meta['year'] = rd.substring(0, 4);
    tmdbId = info['tmdb'] ?? info['tmdb_id'];
    final eps = data['episodes'];
    final pairs = <MapEntry<String, dynamic>>[];
    if (eps is Map) {
      eps.forEach((k, v) => pairs.add(MapEntry('$k', v)));
    } else if (eps is List) {
      for (var i = 0; i < eps.length; i++) {
        pairs.add(MapEntry('${i + 1}', eps[i]));
      }
    }
    final seasonInfo = <String, Map>{};
    for (final s in XtreamClient.list(data['seasons'])) {
      if (s is Map) seasonInfo['${s['season_number']}'] = s;
    }
    for (final p in pairs) {
      final out = <Map<String, dynamic>>[];
      for (final e in XtreamClient.list(p.value)) {
        if (e is! Map) continue;
        final ei = e['info'] is Map ? e['info'] as Map : {};
        final num = int.tryParse('${e['episode_num'] ?? ''}') ?? 0;
        final n = _epCleanName('${e['title'] ?? ''}', item.name);
        out.add({
          'name': n.isEmpty ? 'Épisode $num' : n,
          'num': num,
          'url': cl.episodeUrl('${e['id']}', '${e['container_extension'] ?? ''}'),
          'plot': '${ei['plot'] ?? ''}'.trim(),
          'runtime': _toMinutes(ei),
          'still': '${ei['movie_image'] ?? ''}',
          'rating': '${ei['rating'] ?? ''}',
          'air_date': '${ei['releasedate'] ?? ei['air_date'] ?? ''}',
          'opts': <String>[],
        });
      }
      out.sort((a, b) => (a['num'] as int).compareTo(b['num'] as int));
      final si = seasonInfo[p.key] ?? {};
      seasons.add({'number': int.tryParse(p.key) ?? 0, 'name': '${si['name'] ?? ''}',
        'poster': '${si['cover'] ?? ''}', 'episodes': out});
    }
  } else if (item.episodes != null) {
    item.episodes!.forEach((sn, lst) {
      seasons.add({
        'number': int.tryParse(sn) ?? 0, 'name': '', 'poster': '',
        'episodes': lst.map((e) => e.toJson()).toList(),
      });
    });
  }
  seasons.sort((a, b) => (a['number'] as int).compareTo(b['number'] as int));
  if (tmdbKey.isNotEmpty) {
    final tm = Tmdb(tmdbKey, lang);
    try {
      var id = int.tryParse('${tmdbId ?? ''}');
      id ??= await tm.search('tv', '${meta['title']}', '${meta['year']}');
      if (id != null) {
        final d = await tm.tv(id);
        _mergeTmdb(meta, d, 'tv', lang.substring(0, 2));
        final ert = d['episode_run_time'];
        if (ert is List && ert.isNotEmpty) meta['runtime'] = (ert.first as num).toInt();
        final cc = lang.contains('-') ? lang.split('-').last.toUpperCase() : 'FR';
        final cert = _pickCert(((d['content_ratings'] as Map?)?['results'] as List?) ?? [], cc, (e) => '${e['rating'] ?? ''}');
        if (cert.isNotEmpty) meta['age'] = cert;
        for (final s in seasons.take(25)) {
          Map<String, dynamic> sd;
          try {
            sd = await tm.season(id, s['number'] as int);
          } catch (_) {
            continue;
          }
          if ('${s['name']}'.isEmpty) s['name'] = '${sd['name'] ?? ''}';
          if (sd['poster_path'] != null) s['poster'] = tmdbImg(sd['poster_path'], 'w342');
          final byNum = <int, Map>{};
          for (final e in (sd['episodes'] as List? ?? []).whereType<Map>()) {
            final n = (e['episode_number'] as num?)?.toInt();
            if (n != null) byNum[n] = e;
          }
          for (final e in (s['episodes'] as List).cast<Map<String, dynamic>>()) {
            final t = byNum[e['num']];
            if (t == null) continue;
            if (t['still_path'] != null) e['still'] = tmdbImg(t['still_path'], 'w300');
            if ('${t['overview'] ?? ''}'.trim().isNotEmpty) e['plot'] = '${t['overview']}'.trim();
            final tn = '${t['name'] ?? ''}';
            if (tn.isNotEmpty && ('${e['name']}'.isEmpty || RegExp(r'^(Épisode|Episode)\s*\d+$').hasMatch('${e['name']}'))) {
              e['name'] = tn;
            }
            if (t['runtime'] is num && (e['runtime'] ?? 0) == 0) e['runtime'] = (t['runtime'] as num).toInt();
            if (t['air_date'] != null) e['air_date'] = '${t['air_date']}';
          }
        }
      }
    } catch (_) {}
  }
  meta['seasons'] = seasons;
  return meta;
}

Future<Map<String, dynamic>?> personMeta(String tmdbKey, String lang, {int? id, String name = ''}) async {
  final tm = Tmdb(tmdbKey, lang);
  var pid = id;
  if (pid == null) {
    final res = await tm.searchPerson(name);
    if (res.isEmpty) return null;
    pid = (res.first['id'] as num?)?.toInt();
    if (pid == null) return null;
  }
  final d = await tm.person(pid);
  final credits = <Map<String, dynamic>>[];
  final seen = <String>{};
  for (final c in (((d['combined_credits'] as Map?)?['cast'] as List?) ?? []).whereType<Map>()) {
    final key = '${c['media_type']}:${c['id']}';
    if (!seen.add(key)) continue;
    final date = '${c['release_date'] ?? c['first_air_date'] ?? ''}';
    credits.add({
      'title': '${c['title'] ?? c['name'] ?? ''}',
      'original_title': '${c['original_title'] ?? c['original_name'] ?? ''}',
      'year': date.length >= 4 ? date.substring(0, 4) : '',
      'poster': tmdbImg(c['poster_path'], 'w342'),
      'kind': c['media_type'] == 'movie' ? 'movie' : 'series',
      'role': '${c['character'] ?? ''}',
      'votes': (c['vote_count'] as num?)?.toInt() ?? 0,
    });
  }
  credits.sort((a, b) => (b['votes'] as int).compareTo(a['votes'] as int));
  final gender = d['gender'];
  return {
    'tmdb_id': pid,
    'name': '${d['name'] ?? name}',
    'bio': '${d['biography'] ?? ''}'.trim(),
    'photo': tmdbImg(d['profile_path'], 'h632'),
    'birthday': '${d['birthday'] ?? ''}',
    'deathday': '${d['deathday'] ?? ''}',
    'place': '${d['place_of_birth'] ?? ''}',
    'born_word': gender == 1 ? 'Née' : (gender == 2 ? 'Né' : 'Né(e)'),
    'credits': credits,
  };
}
