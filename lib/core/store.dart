// État global de l'application : sources, profils, bibliothèque, favoris, reprise, fiches.
import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'dart:math';

import 'package:flutter/foundation.dart';
import 'package:path_provider/path_provider.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'admin.dart';
import 'channels.dart';
import 'countries.dart';
import 'downloads.dart';
import 'm3u.dart';
import 'meta.dart';
import 'models.dart';
import 'net.dart';
import 'text.dart';
import 'xtream.dart';

const String kAppTitle = 'IPTV Player';
const String kAppVersion = '2.8';

/// Clé TMDB intégrée (jaquettes, fonds, acteurs). Un secret GitHub TMDB_KEY, s'il existe, la remplace.
const String _kTmdbDefault =
    'eyJhbGciOiJIUzI1NiJ9.eyJhdWQiOiIyOWY2NWExMTI1MjcyNzVmYTU2OGMyODcyYmRhZmMzYSIsIm5iZiI6MTc0MzI3NDQ5OC43NjE5OTk4LCJzdWIiOiI2N2U4NDIwMjhmMzAzZDJmOTVkZGIyZDciLCJzY29wZXMiOlsiYXBpX3JlYWQiXSwidmVyc2lvbiI6MX0.3SJ9Hu2wA19lIcXGCFlknP_K68OSZztLZFC7zrDBrNY';
const String _kTmdbEnv = String.fromEnvironment('TMDB_KEY');
const String kTmdbBuiltin = _kTmdbEnv == '' ? _kTmdbDefault : _kTmdbEnv;

/// Version « stores » (App Store / Google Play) : sans logos ni marques de plateformes tierces.
const bool kStoreBuild = bool.fromEnvironment('STORE');
const String kAppAuthor = 'Asvind';

const List<int> kAvatarColors = [0xFFE8252C, 0xFF1A5FD8, 0xFFF6A600, 0xFF0E9A48, 0xFF8B3FD9, 0xFFE0457B, 0xFF11A3B5, 0xFF5B6478];
const List<String> kAvatarEmojis = ['', '🦤', '🦁', '🐯', '🦊', '🐼', '🐸', '🐙', '🦄', '🐬', '🚀', '⚽', '🎮', '🎬', '🎧', '⭐'];

// ---------------------------------------------------------------- isolats
String _encodeCache(Map<String, dynamic> m) => jsonEncode(m);

/// Lecture du cache d'une source entièrement hors de l'écran principal (lecture + décodage en une fois).
(List<Item>, String) _loadCache(String path) {
  final d = jsonDecode(File(path).readAsStringSync());
  final list = (d is Map ? d['items'] : d) as List? ?? const [];
  final its = list.whereType<Map>().map((e) => Item.fromJson(Map<String, dynamic>.from(e))).toList();
  return (its, d is Map ? '${d['info'] ?? ''}' : '');
}

class CatTile {
  final String kind;
  final String group;
  final String name;
  final String sub;
  final String logo;
  final bool special;
  const CatTile({required this.kind, this.group = '', required this.name, this.sub = '', this.logo = '', this.special = false});
}

class ContinueEntry {
  final String url;
  final PlayItem item;
  final String title;
  final String sub;
  final String logo;
  final double progress;
  final Item? lib;
  const ContinueEntry({required this.url, required this.item, required this.title, required this.sub,
      required this.logo, required this.progress, this.lib});
}

class AppState extends ChangeNotifier {
  late SharedPreferences _prefs;
  late Directory _dir;
  Map<String, dynamic> cfg = {};

  // bibliothèque
  List<Item> _raw = [];
  List<Item> items = [];
  Map<String, List<Item>> byKind = {'live': [], 'movie': [], 'series': []};
  Map<String, Item> byUrl = {};
  final Map<String, Map<String, List<Item>>> _titles = {'movie': {}, 'series': {}};
  final Map<String, Set<String>> _actorIndex = {};
  String sourceInfo = '';
  bool loading = false;

  /// Vrai dès que la liste de la source courante a été chargée au moins une fois (cache ou réseau).
  bool ready = false;
  String? error;
  int libVersion = 0;

  Map<String, dynamic>? currentSource;
  late StreamStats stats;
  int cores = 0, ramMb = 0;
  String hwTier = 'mid';
  final List<String> appLog = [];
  final Map<String, Map<String, dynamic>> guides = {};
  final Map<String, Future<void>> _guideLoading = {};
  AdminServer? admin;
  Timer? _maintT;
  /// Liste complète (avant catégories masquées et regroupement) : administration web.
  List<Item> get rawItems => _raw;
  Map<String, dynamic>? profile;
  Set<String> favorites = {};

  final Map<String, Map<String, dynamic>> _metaMem = {};
  final Map<String, List<Map<String, dynamic>>> _listMem = {};
  final Map<String, Future<List<Map<String, dynamic>>>> _listPending = {};
  late final DownloadManager downloads = DownloadManager(this);
  final Map<String, Future<Map<String, dynamic>?>> _metaPending = {};
  Timer? _saveTimer;

  // ------------------------------------------------------------ init
  Future<void> init() async {
    _prefs = await SharedPreferences.getInstance();
    _dir = await getApplicationSupportDirectory();
    for (final d in ['cache', 'meta']) {
      await Directory('${_dir.path}/$d').create(recursive: true);
    }
    try {
      final s = _prefs.getString('config');
      if (s != null) cfg = Map<String, dynamic>.from(jsonDecode(s) as Map);
    } catch (_) {}
    cfg.putIfAbsent('sources', () => <dynamic>[]);
    cfg.putIfAbsent('tmdb_key', () => '');
    cfg.putIfAbsent('lang', () => 'fr-FR');
    cfg.putIfAbsent('pdata', () => <String, dynamic>{});
    cfg.putIfAbsent('downloads', () => <dynamic>[]);
    cfg.putIfAbsent('buffer_min', () => 0);
    cfg.putIfAbsent('live_cache', () => 3);
    _ensureSettings();
    stats = StreamStats(Map<String, dynamic>.from((cfg['stream_stats'] as Map?) ?? {}));
    cfg['stream_stats'] = stats.d;
    (cores, ramMb, hwTier) = hardware();
    if ((cfg['profiles'] as List?)?.isNotEmpty != true) {
      cfg['profiles'] = [
        {'id': 'p1', 'name': 'Principal', 'color': kAvatarColors[0], 'emoji': '🦤', 'kids': false, 'pin': ''}
      ];
    }
    for (final p in profiles) {
      _pd(p['id'] as String);
    }
    final last = profiles.where((p) => p['id'] == cfg['current_profile']).toList();
    if (profiles.length == 1 && '${profiles.first['pin'] ?? ''}'.isEmpty) {
      selectProfile(profiles.first['id'] as String, notify: false);
    } else if (last.isNotEmpty && '${last.first['pin'] ?? ''}'.isEmpty && !askProfileAtStart) {
      selectProfile(last.first['id'] as String, notify: false);
    }
    downloads.init();
    _maintT = Timer.periodic(const Duration(minutes: 10), (_) => maintenanceTick());
    Timer(const Duration(seconds: 90), maintenanceTick);
    if ((cfg['admin'] as Map)['enabled'] == true) unawaited(setAdmin(true));
    final srcs = sources;
    if (srcs.isNotEmpty) {
      final sid = srcs.any((s) => s['id'] == cfg['last_source']) ? cfg['last_source'] as String : srcs.first['id'] as String;
      unawaited(setSource(sid));
    }
  }

  bool get askProfileAtStart => profiles.length > 1;
  List<Map<String, dynamic>> get sources => (cfg['sources'] as List).cast<Map<String, dynamic>>();
  List<Map<String, dynamic>> get profiles =>
      (cfg['profiles'] as List).map((e) => Map<String, dynamic>.from(e as Map)).toList();
  String get userTmdbKey => '${cfg['tmdb_key'] ?? ''}';
  String get tmdbKey => userTmdbKey.trim().isNotEmpty ? userTmdbKey.trim() : kTmdbBuiltin;
  int get bufferMin => (cfg['buffer_min'] as num?)?.toInt() ?? 0;
  int get liveCacheSecs => (cfg['live_cache'] as num?)?.toInt() ?? 3;
  Directory get dataDir => _dir;

  /// Téléchargements hors ligne (retirés de la version App Store : règle 5.2.3 d'Apple).
  bool get downloadsEnabled => !(kStoreBuild && Platform.isIOS);
  String get lang => '${cfg['lang'] ?? 'fr-FR'}';

  Map<String, dynamic> _pd(String pid) {
    final all = cfg['pdata'] as Map<String, dynamic>;
    final d = Map<String, dynamic>.from((all[pid] as Map?) ?? {});
    d.putIfAbsent('favorites', () => <dynamic>[]);
    d.putIfAbsent('progress', () => <String, dynamic>{});
    d.putIfAbsent('live_hist', () => <String, dynamic>{});
    d['progress'] = Map<String, dynamic>.from(d['progress'] as Map);
    d['live_hist'] = Map<String, dynamic>.from(d['live_hist'] as Map);
    all[pid] = d;
    return d;
  }

  Map<String, dynamic> get pdata => _pd('${profile?['id'] ?? 'p1'}');
  Map<String, dynamic> get progress => pdata['progress'] as Map<String, dynamic>;
  Map<String, dynamic> get liveHist => pdata['live_hist'] as Map<String, dynamic>;

  void save({bool now = false}) {
    if (profile != null) pdata['favorites'] = favorites.toList()..sort();
    _saveTimer?.cancel();
    void doSave() => _prefs.setString('config', jsonEncode(cfg));
    if (now) {
      doSave();
    } else {
      _saveTimer = Timer(const Duration(seconds: 2), doSave);
    }
  }

  // ------------------------------------------------------------ profils
  void selectProfile(String pid, {bool notify = true}) {
    if (profile != null) pdata['favorites'] = favorites.toList();
    final p = profiles.firstWhere((e) => e['id'] == pid, orElse: () => profiles.first);
    final kidsChanged = (profile?['kids'] == true) != (p['kids'] == true);
    profile = p;
    cfg['current_profile'] = p['id'];
    favorites = ((pdata['favorites'] as List?) ?? []).map((e) => '$e').toSet();
    save();
    if (kidsChanged || notify) _applyLibrary(_raw, sourceInfo);
    if (notify) notifyListeners();
  }

  void logoutProfile() {
    save(now: true);
    profile = null;
    notifyListeners();
  }

  void upsertProfile(Map<String, dynamic> p) {
    final list = cfg['profiles'] as List;
    final i = list.indexWhere((e) => (e as Map)['id'] == p['id']);
    if (i >= 0) {
      list[i] = p;
    } else {
      list.add(p);
    }
    _pd(p['id'] as String);
    if (profile?['id'] == p['id']) profile = p;
    save();
    notifyListeners();
  }

  void deleteProfile(String pid) {
    (cfg['profiles'] as List).removeWhere((e) => (e as Map)['id'] == pid);
    (cfg['pdata'] as Map).remove(pid);
    if (profile?['id'] == pid) profile = null;
    save();
    notifyListeners();
  }

  // ------------------------------------------------------------ sources
  String _cachePath(String sid) => '${_dir.path}/cache/$sid.json';

  Future<void> setSource(String sid, {bool force = false}) async {
    final src = sources.firstWhere((s) => s['id'] == sid, orElse: () => {});
    if (src.isEmpty) return;
    final changed = currentSource?['id'] != sid;
    currentSource = src;
    cfg['last_source'] = sid;
    save();
    error = null;
    final f = File(_cachePath(sid));
    if (!force && await f.exists()) {
      // l'écran affiche « Chargement… » pendant la lecture du cache (jamais un écran vide)
      loading = true;
      notifyListeners();
      try {
        final (its, info) = await compute(_loadCache, f.path);
        _applyLibrary(its, info);
        loading = false;
        ready = true;
        notifyListeners();
        return;
      } catch (_) {}
    }
    if (changed) _applyLibrary([], '');
    loading = true;
    notifyListeners();
    try {
      List<Item> its;
      String info;
      if (src['type'] == 'xtream') {
        (its, info) = await XtreamClient.of(src).loadAll();
      } else {
        final loc = '${src['url']}'.trim();
        if (RegExp(r'^https?://', caseSensitive: false).hasMatch(loc)) {
          final text = await getText(loc, timeout: const Duration(seconds: 120));
          if (!RegExp('#EXTINF', caseSensitive: false).hasMatch(text)) {
            throw Exception("Le contenu reçu n'est pas une liste M3U valide.");
          }
          its = await compute(parseM3u, text);
          _noteEpgHeader(src, text.length > 4000 ? text.substring(0, 4000) : text);
        } else {
          // fichier local : lecture, décodage et analyse hors de l'écran principal
          final f = File(loc.replaceFirst('file://', ''));
          if (!await f.exists()) throw Exception('Fichier introuvable : ${f.path}');
          final (fits, head) = await compute(_parseM3uFile, f.path);
          its = fits;
          _noteEpgHeader(src, head);
        }
        info = '';
      }
      final now = DateTime.now();
      info = [info, 'Mise à jour : ${fmtDate(now.toIso8601String())} ${fmtHm(now)}'].where((e) => e.isNotEmpty).join('\n');
      final payload = {'info': info, 'items': its.map((e) => e.toJson()).toList()};
      final enc = await compute(_encodeCache, payload);
      await File(_cachePath(sid)).writeAsString(enc);
      src['updated_ts'] = DateTime.now().millisecondsSinceEpoch ~/ 1000;
      save();
      if (currentSource?['id'] == sid) _applyLibrary(its, info);
    } catch (e) {
      error = 'Impossible de charger « ${src['name']} » : $e';
    } finally {
      loading = false;
      ready = true;
      notifyListeners();
    }
  }

  void addSource(Map<String, dynamic> src) {
    sources.add(src);
    save();
    setSource(src['id'] as String, force: true);
  }

  Future<void> deleteSource(String sid) async {
    sources.removeWhere((s) => s['id'] == sid);
    try {
      await File(_cachePath(sid)).delete();
    } catch (_) {}
    try {
      await File('${_dir.path}/playlists/$sid.m3u').delete();
    } catch (_) {}
    if (currentSource?['id'] == sid) {
      currentSource = null;
      _applyLibrary([], '');
      if (sources.isNotEmpty) unawaited(setSource(sources.first['id'] as String));
    }
    save();
    notifyListeners();
  }

  // ------------------------------------------------------------ bibliothèque
  void _applyLibrary(List<Item> raw, String info) {
    _raw = raw;
    sourceInfo = info;
    var its = raw;
    if (profile?['kids'] == true) {
      its = raw.where((i) => !adultRe.hasMatch('${i.group} ${i.name}')).toList();
    }
    final hidden = ((cfg['hidden_groups'] as List?) ?? const []).map((e) => '$e').toSet();
    if (hidden.isNotEmpty) its = its.where((i) => !hidden.contains(i.group)).toList();
    if (pset['dedupe'] != false) its = groupVariants(its);
    items = its;
    byKind = {'live': [], 'movie': [], 'series': []};
    byUrl = {};
    _titles['movie']!.clear();
    _titles['series']!.clear();
    for (final it in its) {
      byUrl[it.url] = it;
      if (it.kind == 'movie' || it.kind == 'series') {
        final (t, y) = cleanTitle(it.name);
        it.title = t;
        it.year = y;
        it.q = norm('${it.name} $t');
        final rv = double.tryParse(it.rating);
        it.ratingStr = (rv != null && rv > 0) ? (rv > 10 ? rv / 10 : rv).toStringAsFixed(1) : '';
        it.sub = [it.year, prettyGroup(it.group)].where((e) => e.isNotEmpty).join(' · ');
        _titles[it.kind]!.putIfAbsent(titleKey(t), () => []).add(it);
      } else {
        it.title = it.grouped ? displayName(it.name) : stripLeadTags(it.name);
        it.q = norm('${it.name} ${it.title}');
        it.sub = prettyGroup(it.group);
      }
      byKind.putIfAbsent(it.kind, () => []).add(it);
    }
    _remapSaved();
    libVersion++;
  }

  List<Item> recent(String kind, int n) {
    final lst = byKind[kind] ?? [];
    if (!lst.take(200).any((i) => i.added.isNotEmpty)) {
      return lst.reversed.take(n).toList();
    }
    final s = List<Item>.of(lst)..sort((a, b) => b.addedInt.compareTo(a.addedInt));
    return s.take(n).toList();
  }

  Item? matchTitle(String kind, String title, [String original = '', String year = '']) {
    for (final t in [title, original]) {
      if (t.isEmpty) continue;
      final c = _titles[kind]?[titleKey(t)];
      if (c != null && c.isNotEmpty) {
        if (year.isNotEmpty) {
          for (final x in c) {
            if (x.year == year) return x;
          }
        }
        return c.first;
      }
    }
    return null;
  }

  List<Item> titlesWithActor(String name) {
    final urls = _actorIndex[norm(name)] ?? {};
    return items.where((i) => urls.contains(i.url)).toList();
  }

  List<Item> search(String query, String kind, {int limit = 80}) {
    final terms = norm(query).split(RegExp(r'\s+')).where((e) => e.isNotEmpty).toList();
    if (terms.isEmpty) return [];
    return (byKind[kind] ?? []).where((i) => terms.every(i.q.contains)).take(limit).toList();
  }

  List<Item> trendingChannels(int n) {
    final live = byKind['live'] ?? [];
    if (live.isEmpty) return [];
    final out = <Item>[];
    final seen = <String>{};
    final hist = liveHist.entries.toList()..sort((a, b) => (b.value as num).compareTo(a.value as num));
    for (final e in hist) {
      final it = byUrl[e.key];
      if (it != null && it.kind == 'live' && seen.add(it.url)) out.add(it);
    }
    for (final i in live) {
      if (favorites.contains(i.url) && seen.add(i.url)) out.add(i);
    }
    final counts = <String, int>{};
    for (final i in live) {
      if (i.country != 'ZZ') counts[i.country] = (counts[i.country] ?? 0) + 1;
    }
    String? top;
    if (counts.isNotEmpty) top = (counts.entries.toList()..sort((a, b) => b.value.compareTo(a.value))).first.key;
    for (final i in live) {
      if (out.length >= n) break;
      if ((top == null || i.country == top) && seen.add(i.url)) out.add(i);
    }
    return out.take(n).toList();
  }

  List<CatTile> categories(String kind, {int limit = 10000, bool special = false}) {
    final pool = byKind[kind] ?? [];
    final counts = <String, int>{};
    final firstImg = <String, String>{};
    for (final i in pool) {
      counts[i.group] = (counts[i.group] ?? 0) + 1;
      if (i.logo.isNotEmpty) firstImg.putIfAbsent(i.group, () => i.logo);
    }
    final unit = kind == 'live' ? 'chaîne' : 'titre';
    final out = <CatTile>[];
    if (special) {
      out.add(CatTile(kind: kind, special: true, name: {
            'movie': 'Films par catégories', 'series': 'Séries par catégories', 'live': 'Chaînes par catégories'
          }[kind]!));
    }
    final order = {for (final (i, g) in ((cfg['group_order'] as List?) ?? const []).indexed) '$g': i};
    final entries = counts.entries.toList()
      ..sort((a, b) {
        final oa = order[a.key] ?? 1000000, ob = order[b.key] ?? 1000000;
        return oa != ob ? oa.compareTo(ob) : b.value.compareTo(a.value);
      });
    for (final e in entries.take(limit)) {
      final cc = kind == 'live' ? detectCountry(group: e.key) : 'ZZ';
      final u = e.value > 1 ? '${unit}s' : unit;
      out.add(CatTile(
          kind: kind, group: e.key, name: prettyGroup(e.key),
          sub: cc != 'ZZ' ? '${countryName(cc)} · ${e.value} $u' : '${e.value} $u', logo: firstImg[e.key] ?? ''));
    }
    return out;
  }

  // ------------------------------------------------------------ favoris / reprise
  bool isFav(String url) => favorites.contains(url);

  void toggleFavorite(String url) {
    if (!favorites.remove(url)) {
      favorites.add(url);
      final it = byUrl[url];
      final k = it == null ? null : stableKey(it);
      if (k != null) (cfg['fav_keys'] as Map)[url] = k;
    }
    save();
    notifyListeners();
  }

  void noteLive(PlayItem it) {
    if (it.kind != 'live' || profile == null) return;
    final h = liveHist;
    h[it.url] = ((h[it.url] as num?) ?? 0) + 1;
    if (h.length > 300) {
      final e = h.entries.toList()..sort((a, b) => (a.value as num).compareTo(b.value as num));
      for (final x in e.take(h.length - 300)) {
        h.remove(x.key);
      }
    }
    save();
  }

  void saveProgress(PlayItem it, int pos, int len) {
    if (it.kind == 'live' || len <= 0) return;
    final done = pos / len >= 0.95;
    progress[it.url] = {
      'pos': pos, 'len': len, 't': DateTime.now().millisecondsSinceEpoch, 'done': done,
      'src': currentSource?['id'], 'item': it.toJson(),
      if (it.series != null) 'series': it.series,
    };
    if (progress.length > 500) {
      final e = progress.entries.toList()
        ..sort((a, b) => ((a.value as Map)['t'] as num).compareTo((b.value as Map)['t'] as num));
      for (final x in e.take(progress.length - 500)) {
        progress.remove(x.key);
      }
    }
    save();
  }

  Map<String, dynamic>? progressOf(String url) {
    final p = progress[url];
    return p is Map ? Map<String, dynamic>.from(p) : null;
  }

  List<ContinueEntry> continueItems() {
    final src = currentSource?['id'];
    final out = <ContinueEntry>[];
    final seenSeries = <String>{};
    final entries = progress.entries.toList()
      ..sort((a, b) => ((b.value as Map)['t'] as num).compareTo((a.value as Map)['t'] as num));
    for (final e in entries) {
      final v = e.value as Map;
      if (v['src'] != src || v['done'] == true || ((v['len'] as num?) ?? 0) <= 0) continue;
      final it = PlayItem.fromJson(Map<String, dynamic>.from(v['item'] as Map));
      final s = v['series'] is Map ? Map<String, dynamic>.from(v['series'] as Map) : null;
      final frac = (v['pos'] as num) / (v['len'] as num);
      if (s != null) {
        if (!seenSeries.add('${s['url']}')) continue;
        out.add(ContinueEntry(
            url: e.key, item: PlayItem(name: it.name, url: it.url, kind: it.kind, logo: it.logo, opts: it.opts, series: s),
            title: '${s['name']}', sub: 'S${s['season']} E${s['num']} · ${s['ep_name'] ?? ''}',
            logo: '${s['logo'] ?? it.logo}', progress: frac.toDouble(), lib: byUrl['${s['url']}']));
      } else {
        out.add(ContinueEntry(
            url: e.key, item: it, title: cleanTitle(it.name).$1,
            sub: 'Reste ${fmtMs(((v['len'] as num) - (v['pos'] as num)).toInt())}',
            logo: it.logo, progress: frac.toDouble(), lib: byUrl[e.key]));
      }
      if (out.length >= 20) break;
    }
    return out;
  }

  void clearProgress() {
    progress.clear();
    save();
    notifyListeners();
  }

  // ------------------------------------------------------------ fiches
  File _metaFile(String key) => File('${_dir.path}/meta/${fnv(key)}.json');

  String _metaKey(Item item) => 'v3|${item.kind}|${currentSource?['id']}|${item.url}|$lang|${tmdbKey.isNotEmpty}';

  /// Fiche déjà en mémoire (affichage immédiat, sans attendre).
  Map<String, dynamic>? metaNow(Item item) => _metaMem[_metaKey(item)];

  Future<Map<String, dynamic>> _computeMeta(Item item) => item.kind == 'series'
      ? seriesMeta(currentSource, item, tmdbKey, lang)
      : movieMeta(currentSource, item, tmdbKey, lang);

  void _indexCast(Item item, Map<String, dynamic> m) {
    for (final c in (m['cast'] as List? ?? []).whereType<Map>()) {
      final n = '${c['name'] ?? ''}';
      if (n.isNotEmpty) _actorIndex.putIfAbsent(norm(n), () => {}).add(item.url);
    }
  }

  /// Fiche d'un film / d'une série. Mise en cache ; actualisée en arrière-plan une fois par jour ;
  /// redemandée 20 minutes plus tard si TMDB n'avait pas répondu.
  Future<Map<String, dynamic>?> meta(Item item, {bool force = false}) {
    final key = _metaKey(item);
    final mem = _metaMem[key];
    if (mem != null && !force) return Future.value(mem);
    return _metaPending[key] ??= () async {
      try {
        final f = _metaFile(key);
        Map<String, dynamic>? m;
        var stale = false;
        if (!force && await f.exists()) {
          final age = DateTime.now().difference(await f.lastModified());
          m = Map<String, dynamic>.from(jsonDecode(await f.readAsString()) as Map);
          final failed = m['_tmdb'] == 'fail';
          if (failed && age.inMinutes >= 20) {
            m = null;
          } else if (age.inHours >= 24) {
            stale = true;
          }
        }
        if (m == null) {
          m = await _computeMeta(item);
          await f.writeAsString(jsonEncode(m));
        }
        _metaMem[key] = m;
        _indexCast(item, m);
        if (stale) {
          unawaited(() async {
            try {
              final fresh = await _computeMeta(item);
              if (fresh['_tmdb'] != 'fail') {
                await f.writeAsString(jsonEncode(fresh));
                _metaMem[key] = fresh;
              }
            } catch (_) {}
          }());
        }
        return m;
      } catch (_) {
        return null;
      } finally {
        _metaPending.remove(key);
      }
    }();
  }

  /// Listes TMDB (tendances, succès, plateformes…) mises en cache pour la journée.
  List<Map<String, dynamic>>? listNow(String name) => _listMem['$name|$lang|${_today()}'];

  Future<List<Map<String, dynamic>>> tmdbList(String name, Future<List<Map<String, dynamic>>> Function(String key, String lang) compute) {
    final key = '$name|$lang|${_today()}';
    final mem = _listMem[key];
    if (mem != null) return Future.value(mem);
    if (tmdbKey.isEmpty) return Future.value(const []);
    return _listPending[key] ??= () async {
      final f = _metaFile('list|$key');
      try {
        if (await f.exists()) {
          final l = (jsonDecode(await f.readAsString()) as List).map((e) => Map<String, dynamic>.from(e as Map)).toList();
          _listMem[key] = l;
          return l;
        }
        final l = await compute(tmdbKey, lang);
        if (l.isNotEmpty) await f.writeAsString(jsonEncode(l));
        _listMem[key] = l;
        return l;
      } catch (_) {
        return const <Map<String, dynamic>>[];
      } finally {
        _listPending.remove(key);
      }
    }();
  }

  static String _today() {
    final n = DateTime.now();
    return '${n.year}-${n.month}-${n.day}';
  }

  Future<Map<String, dynamic>?> person({int? id, required String name, bool force = false}) async {
    if (tmdbKey.isEmpty) return null;
    final key = 'person|${id ?? norm(name)}|$lang';
    final mem = _metaMem[key];
    if (mem != null && !force) return mem;
    try {
      final f = _metaFile(key);
      Map<String, dynamic>? m;
      if (!force && await f.exists() && DateTime.now().difference(await f.lastModified()).inDays < 1) {
        m = Map<String, dynamic>.from(jsonDecode(await f.readAsString()) as Map);
      } else {
        m = await personMeta(tmdbKey, lang, id: id, name: name);
        if (m != null) await f.writeAsString(jsonEncode(m));
      }
      if (m != null) _metaMem[key] = m;
      return m;
    } catch (_) {
      return null;
    }
  }

  Future<List<Map<String, dynamic>>> epg(Item it) async {
    final src = currentSource;
    if (src == null || src['type'] != 'xtream' || it.streamId.isEmpty) return [];
    try {
      return await XtreamClient.of(src).shortEpg(it.streamId);
    } catch (_) {
      return [];
    }
  }

  Future<List<Map<String, dynamic>>> epgById(String streamId) async {
    final src = currentSource;
    if (src == null || src['type'] != 'xtream' || streamId.isEmpty) return [];
    try {
      return await XtreamClient.of(src).shortEpg(streamId);
    } catch (_) {
      return [];
    }
  }

  String epgUrl(Map<String, dynamic>? src) => '${src?['epg'] ?? src?['epg_auto'] ?? ''}'.trim();

  void _noteEpgHeader(Map<String, dynamic> src, String head) {
    final m = RegExp(r'(?:url-tvg|x-tvg-url)\s*=\s*"([^"]+)"', caseSensitive: false).firstMatch(head);
    if (m != null) {
      final u = m.group(1)!.split(',').first.trim();
      if (u != src['epg_auto']) {
        src['epg_auto'] = u;
        guides.remove(src['id']);
      }
    }
  }

  /// Programme en cours et à venir : compte Xtream, sinon guide XMLTV (de la liste ou choisi).
  Future<List<Map<String, dynamic>>> epgFor(PlayItem it) async {
    final src = currentSource;
    if (src == null) return [];
    if (src['type'] == 'xtream' && it.streamId.isNotEmpty && '${src['epg'] ?? ''}'.isEmpty) return epgById(it.streamId);
    if (epgUrl(src).isEmpty) return [];
    await loadGuide(src);
    final probe = Item.make(it.name, it.url, group: it.group, tvgId: it.tvgId);
    return guideEpg(guides[src['id']], probe);
  }

  Future<void> loadGuide(Map<String, dynamic> src, {bool force = false}) {
    final sid = '${src['id']}';
    if (!force && guides.containsKey(sid)) return Future.value();
    return _guideLoading[sid] ??= () async {
      try {
        final f = File('${_dir.path}/epg/$sid.json');
        if (!force && await f.exists() && DateTime.now().difference(await f.lastModified()).inHours < 12) {
          guides[sid] = Map<String, dynamic>.from(jsonDecode(await f.readAsString()) as Map);
          return;
        }
        final bytes = await getBytes(epgUrl(src), timeout: const Duration(seconds: 180));
        final g = await compute(parseXmltv, bytes);
        await f.parent.create(recursive: true);
        await f.writeAsString(jsonEncode(g));
        guides[sid] = g;
        log('Guide TV chargé : ${(g['progs'] as Map).length} chaînes');
      } catch (e) {
        guides[sid] = {};
        log('Guide TV indisponible : $e');
      } finally {
        _guideLoading.remove(sid);
      }
    }();
  }

  // ------------------------------------------------------------ réglages avancés
  Map<String, dynamic> get pset => cfg['player'] as Map<String, dynamic>;

  void _ensureSettings() {
    final p = Map<String, dynamic>.from((cfg['player'] as Map?) ?? {});
    for (final st in kSettings) {
      p.putIfAbsent(st.key, () => st.def);
    }
    if (p['_migrated'] != true) {
      p['c_live_cache'] = ((cfg['live_cache'] as num?) ?? 3).toDouble();
      p['_migrated'] = true;
    }
    cfg['player'] = p;
    cfg['ch_quality'] = Map<String, dynamic>.from((cfg['ch_quality'] as Map?) ?? {});
    cfg['fav_keys'] = Map<String, dynamic>.from((cfg['fav_keys'] as Map?) ?? {});
    cfg.putIfAbsent('hidden_groups', () => <dynamic>[]);
    cfg.putIfAbsent('group_order', () => <dynamic>[]);
    cfg.putIfAbsent('auto_live_cache', () => kAutoSteps[1]);
    final adm = Map<String, dynamic>.from((cfg['admin'] as Map?) ?? {});
    adm.putIfAbsent('enabled', () => false);
    adm.putIfAbsent('port', () => 8080);
    if (!RegExp(r'^\d{6}$').hasMatch('${adm['pin'] ?? ''}')) {
      adm['pin'] = (Random.secure().nextInt(900000) + 100000).toString();
    }
    cfg['admin'] = adm;
  }

  dynamic setSetting(String key, dynamic value) {
    final v = coerceSetting(key, value);
    final old = pset[key];
    pset[key] = v;
    save();
    if (key == 'dedupe' && old != v) _applyLibrary(_raw, sourceInfo);
    notifyListeners();
    return v;
  }

  void resetSettings() {
    for (final st in kSettings) {
      pset[st.key] = st.def;
    }
    cfg['ch_quality'] = <String, dynamic>{};
    cfg['auto_live_cache'] = kAutoSteps[1];
    save();
    _applyLibrary(_raw, sourceInfo);
    notifyListeners();
  }

  Prof get prof => effectiveProfile(pset, cfg, hwTier);

  void log(String m) {
    final n = DateTime.now();
    String two(int x) => x.toString().padLeft(2, '0');
    appLog.add('${two(n.day)}/${two(n.month)} ${two(n.hour)}:${two(n.minute)}:${two(n.second)}  $m');
    if (appLog.length > 400) appLog.removeRange(0, appLog.length - 400);
  }

  void setHiddenGroups(List<String> hidden, List<String>? order) {
    cfg['hidden_groups'] = hidden.take(5000).toList();
    if (order != null) cfg['group_order'] = order.take(5000).toList();
    save();
    _applyLibrary(_raw, sourceInfo);
    notifyListeners();
  }

  /// Favoris et historique dont le lien a changé à l'actualisation : retrouvés par nom de chaîne / titre.
  void _remapSaved() {
    if (items.isEmpty) return;
    final km = (cfg['fav_keys'] as Map).map((k, v) => MapEntry('$k', '$v'));
    for (final u in favorites) {
      final it = byUrl[u];
      if (!km.containsKey(u) && it != null) {
        final k = stableKey(it);
        if (k != null) km[u] = k;
      }
    }
    final (favs, newmap, n) = remapUrls(favorites.toList()..sort(), km, items);
    if (n > 0) {
      favorites = favs.toSet();
      log('$n favori(s) retrouvé(s) après l\'actualisation de la liste');
    }
    cfg['fav_keys'] = {...km, ...newmap};
    final alias = <String, String>{};
    for (final it in byKind['live'] ?? const <Item>[]) {
      for (final v in it.variants) {
        if (v.url != it.url) alias[v.url] = it.url;
      }
    }
    if (alias.isNotEmpty) {
      final moved = favorites.where(alias.containsKey).map((u) => alias[u]!).toSet();
      if (moved.isNotEmpty) favorites = favorites.where((u) => !alias.containsKey(u)).toSet()..addAll(moved);
      final h = liveHist;
      for (final u in h.keys.where(alias.containsKey).toList()) {
        final to = alias[u]!;
        h[to] = ((h[to] as num?) ?? 0) + ((h.remove(u) as num?) ?? 0);
      }
    }
  }

  // ------------------------------------------------------------ maintenance
  DateTime _lastClean = DateTime.fromMillisecondsSinceEpoch(0);

  Future<void> maintenanceTick() async {
    final now = DateTime.now();
    if (pset['auto_backup'] != false) await autoBackup();
    final h = (pset['auto_refresh_h'] as num? ?? 24).toInt();
    final src = currentSource;
    final upd = (src?['updated_ts'] as num?)?.toInt() ?? 0;
    if (h > 0 && src != null && !loading && now.millisecondsSinceEpoch ~/ 1000 - upd > h * 3600 && !playing) {
      log('Actualisation automatique de « ${src['name']} »');
      unawaited(setSource('${src['id']}', force: true));
    }
    if (now.difference(_lastClean).inHours >= 24) unawaited(cleanNow());
    if (autoCacheRelax(cfg)) log('Profil AUTO : connexion stable, mémoire tampon ramenée à ${cfg['auto_live_cache']} s');
    save();
  }

  /// Vrai pendant la lecture (pas d'actualisation automatique à ce moment-là).
  bool playing = false;

  /// Mesures du lecteur en cours (panneau Diagnostic et administration web).
  Map<String, dynamic> Function()? diag;

  /// Chaîne → (qualité maximale après un repli, heure) : mémorisé le temps de la session.
  final Map<String, (int, DateTime)> degraded = {};

  Future<int> cleanNow() async {
    _lastClean = DateTime.now();
    final mb = (pset['cache_max_mb'] as num? ?? 500).toInt();
    final (n1, b1) = await cleanCache([Directory('${_dir.path}/meta')], mb);
    final (n2, b2) = await cleanCache([Directory('${_dir.path}/epg'), Directory('${_dir.path}/tampon')], 300, maxAgeDays: 7);
    log('Nettoyage du cache : ${n1 + n2} fichiers, ${((b1 + b2) / 1048576).toStringAsFixed(1)} Mo libérés');
    return b1 + b2;
  }

  Future<void> autoBackup() async {
    try {
      final d = Directory('${_dir.path}/sauvegardes');
      await d.create(recursive: true);
      final n = DateTime.now();
      final name = 'config-${n.year}${n.month.toString().padLeft(2, '0')}${n.day.toString().padLeft(2, '0')}.json';
      final f = File('${d.path}/$name');
      if (await f.exists()) return;
      await f.writeAsString(jsonEncode(backupData()));
      final olds = (await d.list().where((e) => e.path.endsWith('.json')).toList())..sort((a, b) => a.path.compareTo(b.path));
      for (final o in olds.take(max(0, olds.length - 7))) {
        await o.delete();
      }
      log('Sauvegarde automatique de la configuration');
    } catch (_) {}
  }

  Map<String, dynamic> backupData() {
    if (profile != null) pdata['favorites'] = favorites.toList()..sort();
    final d = Map<String, dynamic>.from(jsonDecode(jsonEncode(cfg)) as Map);
    d.remove('stream_stats');
    d['_backup'] = {'app': kAppTitle, 'version': kAppVersion, 'date': DateTime.now().toIso8601String()};
    return d;
  }

  Future<void> restore(Map<String, dynamic> data) async {
    if (data['sources'] is! List || data['profiles'] is! List) {
      throw const FormatException("ce fichier n'est pas une sauvegarde d'IPTV Player");
    }
    final keepAdmin = cfg['admin'];
    final keepStats = cfg['stream_stats'];
    cfg = {for (final e in data.entries) if (!e.key.startsWith('_')) e.key: e.value};
    cfg['admin'] = keepAdmin;
    cfg['stream_stats'] = keepStats;
    _ensureSettings();
    profile = null;
    selectProfile(profiles.first['id'] as String, notify: false);
    save(now: true);
    final srcs = sources;
    if (srcs.isNotEmpty) {
      await setSource(srcs.any((s) => s['id'] == cfg['last_source']) ? '${cfg['last_source']}' : '${srcs.first['id']}');
    }
    log('Configuration restaurée');
    notifyListeners();
  }

  /// Vérifie une liste de chaînes (favoris, catégorie). Renvoie (ok, en échec).
  Future<(int, int)> checkItems(List<Item> its) async {
    final urls = <String>[for (final i in its) ...(i.variants.isEmpty ? [i.url] : i.variants.map((v) => v.url))];
    var ok = 0, bad = 0;
    final queue = urls.take(400).toList();
    Future<void> worker() async {
      while (queue.isNotEmpty) {
        final u = queue.removeLast();
        final (good, _) = await probeStream(u, kUserAgent);
        if (good) {
          ok++;
          stats.ok(u);
        } else {
          bad++;
          stats.fail(u);
        }
      }
    }

    await Future.wait(List.generate(6, (_) => worker()));
    save();
    log('Vérification : $ok flux OK, $bad indisponibles');
    return (ok, bad);
  }

  // ------------------------------------------------------------ administration web
  Future<String?> setAdmin(bool on) async {
    final adm = cfg['admin'] as Map<String, dynamic>;
    if (on) {
      admin ??= AdminServer(this);
      try {
        await admin!.start((adm['port'] as num? ?? 8080).toInt(), '${adm['pin']}');
        adm['enabled'] = true;
        adm['port'] = admin!.port;
        log('Administration web : ${admin!.urls.isEmpty ? '' : admin!.urls.first}');
      } catch (e) {
        adm['enabled'] = false;
        save();
        notifyListeners();
        return '$e';
      }
    } else {
      await admin?.stop();
      adm['enabled'] = false;
    }
    save();
    notifyListeners();
    return null;
  }

  void newAdminPin() {
    final adm = cfg['admin'] as Map<String, dynamic>;
    adm['pin'] = (Random.secure().nextInt(900000) + 100000).toString();
    admin?.pin = '${adm['pin']}';
    admin?.tokens.clear();
    save();
    notifyListeners();
  }

  void touch() => notifyListeners();

  // ------------------------------------------------------------ réglages
  void setTmdbKey(String k) {
    cfg['tmdb_key'] = k.trim();
    _metaMem.clear();
    save();
    notifyListeners();
  }

  void setBufferMin(int v) {
    cfg['buffer_min'] = v;
    save();
    notifyListeners();
  }

  void setLiveCache(int v) {
    cfg['live_cache'] = v;
    save();
    notifyListeners();
  }

  void setLang(String l) {
    cfg['lang'] = l;
    _metaMem.clear();
    save();
    notifyListeners();
  }

  Future<void> clearMetaCache() async {
    _metaMem.clear();
    _listMem.clear();
    try {
      await Directory('${_dir.path}/meta').delete(recursive: true);
      await Directory('${_dir.path}/meta').create(recursive: true);
    } catch (_) {}
  }

  static String newId() {
    final r = Random();
    return List.generate(12, (_) => '0123456789abcdef'[r.nextInt(16)]).join();
  }
}

/// Lit et analyse un fichier M3U (exécuté dans un isolat séparé) ; renvoie aussi l'en-tête (guide TV).
(List<Item>, String) _parseM3uFile(String path) {
  final text = decodeBody(File(path).readAsBytesSync());
  if (!RegExp('#EXTINF', caseSensitive: false).hasMatch(text)) {
    throw Exception("Le fichier n'est pas une liste M3U valide.");
  }
  return (parseM3u(text), text.length > 4000 ? text.substring(0, 4000) : text);
}
