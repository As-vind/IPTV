// Fonctions avancées (sans interface), identiques à la version Windows (windows/iptv_plus.py) :
// regroupement des chaînes et qualités, stabilité des flux, choix de la qualité, profils de lecture,
// réglages, guide TV XMLTV, nettoyage du cache.
import 'dart:convert';
import 'dart:io';
import 'dart:math';

import 'models.dart';
import 'text.dart';

// ============================================================ 1. qualités et regroupement
const Map<int, String> kQLabels = {4: '4K', 3: 'FHD', 2: 'HD', 1: 'SD', 0: ''};
const Map<String, int> kQCodes = {'4k': 4, 'fhd': 3, 'hd': 2, 'sd': 1};
// débit nécessaire (octets/s) pour chaque qualité
const Map<int, int> kQNeed = {4: 2200000, 3: 900000, 2: 450000, 1: 200000, 0: 450000};

String _sup(String s) => s
    .replaceAll('ᴴ', 'H')
    .replaceAll('ᴰ', 'D')
    .replaceAll('ᵁ', 'U')
    .replaceAll('ᶠ', 'F')
    .replaceAll('ˢ', 'S')
    .replaceAll('ᴷ', 'K')
    .replaceAll('⁴', '4');

RegExp _tok(String p) => RegExp('(?<![A-Za-z0-9])(?:$p)(?![A-Za-z0-9])', caseSensitive: false);
final List<(int, RegExp)> _qre = [
  (4, _tok(r'8K|4K|UHD|ULTRA\s*HD|2160[PI]?')),
  (3, _tok(r'FHD|FULL\s*HD|1080[PI]?')),
  (2, _tok(r'HD|720[PI]?|HQ')),
  (1, _tok(r'SD|576[PI]?|480[PI]?|360[PI]?|LQ|LOW')),
];
final RegExp _decorRe = RegExp(
    r'(?<![A-Za-z0-9])(?:HEVC|H\.?26[45]|X26[45]|AVC|\d{2,3}\s?FPS|HDR(?:10\+?)?|DV|DOLBY\s*VISION|'
    r'BACKUP|BK|ALT(?:ERNATIVE)?|RAW|VIP|NEW|ORIG(?:INAL)?|MULTI|DIRECT|LIVE|TEST|\(?\d\)?$)(?![A-Za-z0-9])',
    caseSensitive: false);
final RegExp _symbRe = RegExp(r'''[◉●○★☆✦✪♦◆▶►•|\[\](){}<>«»"'`~*#_]+''');

String _trimChars(String s, String chars) {
  var a = 0, b = s.length;
  while (a < b && chars.contains(s[a])) {
    a++;
  }
  while (b > a && chars.contains(s[b - 1])) {
    b--;
  }
  return s.substring(a, b);
}

/// Qualité d'après le nom puis la catégorie : 4 = 4K, 3 = FHD, 2 = HD, 1 = SD, 0 = inconnue.
int qualityOf(String name, [String group = '']) {
  for (final text in [name, group]) {
    final t = _sup(text);
    for (final (rank, rx) in _qre) {
      if (rx.hasMatch(t)) return rank;
    }
  }
  return 0;
}

String stripQuality(String name) {
  var t = _sup(name);
  for (final (_, rx) in _qre) {
    t = t.replaceAll(rx, ' ');
  }
  t = t.replaceAll(_decorRe, ' ').replaceAll(RegExp(r'[\[\(]\s*[\]\)]'), ' ');
  return _trimChars(t.replaceAll(RegExp(r'\s{2,}'), ' '), ' -|:._–/');
}

/// Nom affiché d'une chaîne regroupée : sans préfixe pays ni mention de qualité.
String displayName(String name) {
  var s = stripLeadTags(name);
  if (s.isEmpty) s = name;
  s = stripQuality(s);
  return s.isEmpty ? name.trim() : s;
}

/// Clé de regroupement : pays + nom sans qualité (les variantes régionales, de langue et « +1 » restent distinctes).
String? channelKey(String name, String country) {
  var s = stripLeadTags(name);
  if (s.isEmpty) s = name;
  s = stripQuality(s).replaceAll(_symbRe, ' ');
  s = norm(s).replaceAll(RegExp(r'[^a-z0-9+]+'), '');
  if (s.length < 2) return null;
  return '${country.isEmpty ? 'ZZ' : country}|$s';
}

bool _qualityOnlyGroup(String group) {
  var g = _sup(group).replaceAll(_symbRe, ' ');
  final st = stripLeadTags(g);
  if (st.isNotEmpty) g = st;
  for (final (_, rx) in _qre) {
    g = g.replaceAll(rx, ' ');
  }
  g = g.replaceAll(_decorRe, ' ').replaceAll(RegExp(r'\b(cha[iî]nes?|channels?|tv|live)\b', caseSensitive: false), ' ');
  return g.replaceAll(RegExp(r'[\s\-|:._/]+'), '').isEmpty;
}

/// Regroupe les chaînes identiques (SD / HD / FHD / 4K, flux de secours) en une seule entrée.
/// Les films et séries ne sont pas touchés. Les éléments renvoyés sont des copies.
List<Item> groupVariants(List<Item> items) {
  final out = <Item>[];
  final byKey = <String, Item>{};
  for (final it in items) {
    if (it.kind != 'live') {
      out.add(it);
      continue;
    }
    final v = Variant(url: it.url, name: it.name, q: qualityOf(it.name, it.group), group: it.group, opts: it.opts);
    final key = channelKey(it.name, it.country);
    final rep = key == null ? null : byKey[key];
    if (rep == null) {
      final c = it.copy()
        ..variants = [v]
        ..ckey = key ?? 'u|${it.url}';
      if (key != null) byKey[key] = c;
      out.add(c);
      continue;
    }
    if (rep.variants.any((x) => x.url == v.url)) continue;
    rep.variants.add(v);
    if (rep.logo.isEmpty && it.logo.isNotEmpty) rep.logo = it.logo;
    if (rep.streamId.isEmpty && it.streamId.isNotEmpty) rep.streamId = it.streamId;
    if (rep.tvgId.isEmpty && it.tvgId.isNotEmpty) rep.tvgId = it.tvgId;
    if (_qualityOnlyGroup(rep.group) && !_qualityOnlyGroup(it.group)) rep.group = it.group;
  }
  for (final rep in out) {
    if (rep.variants.length < 2) continue;
    rep.variants.sort((a, b) => b.q.compareTo(a.q));
    final labels = <String>[];
    for (final v in rep.variants) {
      final l = kQLabels[v.q] ?? '';
      if (l.isNotEmpty && !labels.contains(l)) labels.add(l);
    }
    rep.qlabels = labels.join(' · ');
    rep.grouped = true;
  }
  return out;
}

/// Identifiant qui survit à l'actualisation des listes (les liens changent souvent).
String? stableKey(Item it) {
  if (it.kind == 'live') {
    final k = it.ckey.isNotEmpty ? it.ckey : channelKey(it.name, it.country);
    return k == null ? null : 'live|$k';
  }
  final t = norm(it.title.isNotEmpty ? it.title : it.name).replaceAll(RegExp(r'[^a-z0-9]+'), '');
  return t.isEmpty ? null : '${it.kind}|$t|${it.year}';
}

/// Retrouve les favoris dont le lien a changé après une actualisation.
(List<String>, Map<String, String>, int) remapUrls(List<String> urls, Map<String, String> keymap, List<Item> items) {
  final byUrl = <String>{};
  final byKey = <String, String>{};
  for (final i in items) {
    byUrl.add(i.url);
    for (final v in i.variants) {
      byUrl.add(v.url);
    }
    final k = stableKey(i);
    if (k != null) byKey.putIfAbsent(k, () => i.url);
  }
  final out = <String>[];
  final newmap = <String, String>{};
  var changed = 0;
  for (final u in urls) {
    final k = keymap[u];
    if (byUrl.contains(u)) {
      out.add(u);
      if (k != null) newmap[u] = k;
    } else if (k != null && byKey.containsKey(k)) {
      final nu = byKey[k]!;
      out.add(nu);
      newmap[nu] = k;
      changed++;
    } else {
      out.add(u);
      if (k != null) newmap[u] = k;
    }
  }
  return (out.toSet().toList(), newmap, changed);
}

// ============================================================ 2. stabilité et choix du flux
String urlId(String url) {
  // empreinte courte et stable (FNV-1a 64 bits)
  var h = 0xcbf29ce484222325;
  for (final b in utf8.encode(url)) {
    h ^= b;
    h = (h * 0x100000001b3) & 0xFFFFFFFFFFFFFFFF;
  }
  return h.toRadixString(16);
}

class StreamStats {
  /// {id: [ok, échecs, coupures, dernier échec, dernier succès]} — conservé dans la configuration.
  final Map<String, dynamic> d;
  StreamStats(this.d);

  List<int> _row(String url) {
    final id = urlId(url);
    final r = d[id];
    if (r is List && r.length == 5) {
      final l = r.map((e) => (e as num).toInt()).toList();
      d[id] = l;
      return l;
    }
    final l = [0, 0, 0, 0, 0];
    d[id] = l;
    return l;
  }

  int _now() => DateTime.now().millisecondsSinceEpoch ~/ 1000;

  void ok(String url) {
    final r = _row(url);
    r[0]++;
    r[4] = _now();
    _trim();
  }

  void fail(String url) {
    final r = _row(url);
    r[1]++;
    r[3] = _now();
    _trim();
  }

  void stall(String url) {
    _row(url)[2]++;
    _trim();
  }

  List<int> row(String url) {
    final r = d[urlId(url)];
    return r is List && r.length == 5 ? r.map((e) => (e as num).toInt()).toList() : [0, 0, 0, 0, 0];
  }

  bool dead(String url) {
    final r = row(url);
    return r[3] > 0 && r[3] > r[4] && _now() - r[3] < 6 * 3600 && r[1] >= 2;
  }

  double score(String url) {
    final r = row(url);
    var s = r[0] - r[1] * 3.0 - r[2];
    if (r[3] > 0 && r[3] > r[4] && _now() - r[3] < 600) s -= 50;
    return s;
  }

  void _trim() {
    if (d.length <= 5000) return;
    final keys = d.keys.toList()
      ..sort((a, b) {
        int t(String k) => max((d[k] as List)[3] as int, (d[k] as List)[4] as int);
        return t(a).compareTo(t(b));
      });
    for (final k in keys.take(500)) {
      d.remove(k);
    }
  }
}

int? networkCap(num bytesPerS) {
  if (bytesPerS <= 0) return null;
  for (final q in [4, 3, 2]) {
    if (bytesPerS >= kQNeed[q]! * 1.25) return q;
  }
  return 1;
}

/// Indice du flux à lire (voir la version Windows : pick_variant).
int pickVariant(List<Variant> vs, {String pref = 'auto', int cap = 4, StreamStats? stats, Set<String> exclude = const {}, int? below}) {
  if (vs.isEmpty) return 0;
  var cands = [for (var i = 0; i < vs.length; i++) if (!exclude.contains(vs[i].url)) i];
  int eff(int i) => vs[i].q == 0 ? 2 : vs[i].q;
  double sc(int i) => stats?.score(vs[i].url) ?? 0;
  if (below != null) {
    final lower = cands.where((i) => eff(i) < below).toList();
    if (lower.isNotEmpty) cands = lower;
  }
  if (cands.isEmpty) cands = [for (var i = 0; i < vs.length; i++) i];
  int best(List<int> l, int Function(int, int) cmp) => l.reduce((a, b) => cmp(a, b) >= 0 ? a : b);
  int byQS(int a, int b) => eff(a) != eff(b) ? eff(a).compareTo(eff(b)) : sc(a).compareTo(sc(b));
  if (kQCodes.containsKey(pref)) {
    final want = kQCodes[pref]!;
    final exact = cands.where((i) => eff(i) == want).toList();
    if (exact.isNotEmpty) return best(exact, (a, b) => sc(a).compareTo(sc(b)));
    final lower = cands.where((i) => eff(i) < want).toList();
    if (lower.isNotEmpty) return best(lower, byQS);
    return best(cands, (a, b) => eff(b) != eff(a) ? eff(b).compareTo(eff(a)) : sc(a).compareTo(sc(b)));
  }
  var ok = cands.where((i) => eff(i) <= cap).toList();
  if (ok.isEmpty) ok = [best(cands, (a, b) => eff(b).compareTo(eff(a)))];
  final healthy = ok.where((i) => !(stats?.dead(vs[i].url) ?? false)).toList();
  return best(healthy.isEmpty ? ok : healthy, byQS);
}

// ============================================================ 3. profils et réglages
class Prof {
  final double liveCache;
  final int vodCache, stallTimeout, maxRetries;
  final bool fallback;
  final String mode;
  const Prof(this.liveCache, this.vodCache, this.stallTimeout, this.maxRetries, this.fallback, this.mode);
}

const Map<String, (double, int, int, int)> kProfiles = {
  'performance': (1.0, 3, 6, 2),
  'balanced': (3.0, 8, 9, 3),
  'antifreeze': (10.0, 20, 15, 5),
};
const List<double> kAutoSteps = [2.0, 4.0, 7.0, 10.0];

class Setting {
  final String section, key, label, type;
  final dynamic def;
  final List<(String, String)> choices;
  final num lo, hi;
  const Setting(this.section, this.key, this.label, this.type, this.def, {this.choices = const [], this.lo = 0, this.hi = 0});
}

const List<Setting> kSettings = [
  Setting('Lecture', 'profile', 'Profil de lecture', 'choice', 'auto', choices: [
    ('auto', 'AUTO — optimisation intelligente'),
    ('performance', 'Performance — zapping rapide'),
    ('balanced', 'Équilibré'),
    ('antifreeze', 'Anti-freeze — priorité à la continuité'),
    ('custom', 'Personnalisé'),
  ]),
  Setting('Lecture', 'c_live_cache', 'Personnalisé : mémoire tampon des chaînes (s)', 'float', 3.0, lo: 0.5, hi: 30),
  Setting('Lecture', 'c_vod_cache', 'Personnalisé : mémoire tampon des films (s)', 'int', 8, lo: 1, hi: 60),
  Setting('Lecture', 'c_stall_timeout', 'Personnalisé : blocage détecté après (s)', 'int', 9, lo: 3, hi: 60),
  Setting('Lecture', 'c_max_retries', 'Personnalisé : reconnexions avant changement de flux', 'int', 3, lo: 0, hi: 10),
  Setting('Lecture', 'reconnect', 'Reconnexion automatique', 'bool', true),
  Setting('Lecture', 'fallback', 'Basculer vers un autre flux / une qualité inférieure en cas de blocage', 'bool', true),
  Setting('Chaînes', 'dedupe', 'Regrouper les chaînes en double (SD, HD, FHD, 4K)', 'bool', true),
  Setting('Chaînes', 'quality', 'Qualité des chaînes', 'choice', 'auto', choices: [
    ('auto', "AUTO (selon le débit, l'écran et la stabilité)"),
    ('4k', '4K'),
    ('fhd', 'FHD'),
    ('hd', 'HD'),
    ('sd', 'SD'),
  ]),
  Setting('Chaînes', 'upgrade', 'Revenir à une meilleure qualité quand la connexion est stable', 'bool', true),
  Setting('Vidéo', 'hwdec', 'Accélération matérielle', 'bool', true),
  Setting('Vidéo', 'aspect', "Format d'image", 'choice', 'auto', choices: [
    ('auto', 'Automatique'),
    ('16:9', '16:9'),
    ('4:3', '4:3'),
    ('21:9', '21:9'),
    ('fill', "Remplir l'écran"),
    ('stretch', 'Étirer'),
  ]),
  Setting('Vidéo', 'deinterlace', 'Désentrelacement', 'choice', 'auto',
      choices: [('auto', 'Automatique'), ('on', 'Toujours'), ('off', 'Jamais')]),
  Setting('Vidéo', 'brightness', 'Luminosité', 'int', 0, lo: -100, hi: 100),
  Setting('Vidéo', 'contrast', 'Contraste', 'int', 0, lo: -100, hi: 100),
  Setting('Vidéo', 'saturation', 'Saturation', 'int', 0, lo: -100, hi: 100),
  Setting('Vidéo', 'sharpness', 'Netteté', 'int', 0, lo: 0, hi: 100),
  Setting('Vidéo', 'refresh', "Fréquence d'affichage", 'choice', 'off', choices: [
    ('off', 'Ne pas changer'),
    ('auto', 'Adapter au flux'),
    ('24', '24 Hz'),
    ('25', '25 Hz'),
    ('30', '30 Hz'),
    ('50', '50 Hz'),
    ('60', '60 Hz'),
  ]),
  Setting('Vidéo', 'hdr', 'HDR', 'choice', 'auto', choices: [('auto', "Automatique (selon l'écran)"), ('sdr', 'Convertir en SDR')]),
  Setting('Vidéo', 'max_res', 'Résolution maximale', 'choice', 'auto', choices: [
    ('auto', "Automatique (selon l'écran)"),
    ('4k', '4K'),
    ('fhd', '1080p'),
    ('hd', '720p'),
    ('sd', 'SD'),
  ]),
  Setting('Audio', 'a_lang', 'Langue audio préférée', 'choice', 'fr', choices: [
    ('fr', 'Français'),
    ('en', 'Anglais'),
    ('es', 'Espagnol'),
    ('de', 'Allemand'),
    ('it', 'Italien'),
    ('ar', 'Arabe'),
    ('pt', 'Portugais'),
    ('orig', 'Version originale'),
  ]),
  Setting('Audio', 's_lang', 'Sous-titres', 'choice', 'off', choices: [
    ('off', 'Désactivés'),
    ('auto', "Si la langue audio n'est pas la mienne"),
    ('fr', 'Français'),
    ('en', 'Anglais'),
  ]),
  Setting('Audio', 'av_delay', 'Synchronisation audio / vidéo (ms)', 'int', 0, lo: -2000, hi: 2000),
  Setting('Audio', 'normalize', 'Normalisation automatique du volume', 'bool', false),
  Setting('Audio', 'passthrough', "Son multicanal vers l'ampli (passthrough)", 'bool', false),
  Setting('Maintenance', 'auto_refresh_h', 'Actualisation automatique des listes (heures, 0 = jamais)', 'int', 24, lo: 0, hi: 168),
  Setting('Maintenance', 'cache_max_mb', "Taille maximale du cache d'images (Mo)", 'int', 500, lo: 50, hi: 5000),
  Setting('Maintenance', 'auto_backup', 'Sauvegarde automatique quotidienne de la configuration', 'bool', true),
];
final Map<String, Setting> kSettingByKey = {for (final s in kSettings) s.key: s};
const Map<String, String> kLang3 = {
  'fr': 'fr,fra,fre', 'en': 'en,eng', 'es': 'es,spa', 'de': 'de,deu,ger', 'it': 'it,ita', 'ar': 'ar,ara', 'pt': 'pt,por',
};

/// Valide une valeur reçue (interface, administration web) ; lève FormatException si elle est incorrecte.
dynamic coerceSetting(String key, dynamic value) {
  final s = kSettingByKey[key];
  if (s == null) throw FormatException('réglage inconnu : $key');
  switch (s.type) {
    case 'bool':
      if (value is String) return ['1', 'true', 'oui', 'yes', 'on'].contains(value.toLowerCase());
      return value == true;
    case 'int':
    case 'float':
      final v = value is num ? value.toDouble() : double.tryParse('$value');
      if (v == null) throw FormatException('valeur incorrecte pour $key');
      final c = v.clamp(s.lo.toDouble(), s.hi.toDouble());
      return s.type == 'int' ? c.round() : (c * 10).round() / 10;
    case 'choice':
      if (!s.choices.any((e) => e.$1 == value)) throw FormatException('valeur incorrecte pour $key');
      return value;
  }
  return value;
}

Prof effectiveProfile(Map<String, dynamic> p, Map<String, dynamic> cfg, String tier) {
  final mode = '${p['profile'] ?? 'auto'}';
  Prof prof;
  if (mode == 'custom') {
    prof = Prof((p['c_live_cache'] as num? ?? 3).toDouble(), (p['c_vod_cache'] as num? ?? 8).toInt(),
        (p['c_stall_timeout'] as num? ?? 9).toInt(), (p['c_max_retries'] as num? ?? 3).toInt(), p['fallback'] != false, mode);
  } else if (kProfiles.containsKey(mode)) {
    final x = kProfiles[mode]!;
    prof = Prof(x.$1, x.$2, x.$3, x.$4, true, mode);
  } else {
    final live = (cfg['auto_live_cache'] as num? ?? kAutoSteps[1]).toDouble();
    prof = Prof(live, tier == 'low' ? 6 : 10, max(7, live.toInt() + 5), 3, true, 'auto');
  }
  return Prof(prof.liveCache, prof.vodCache, prof.stallTimeout, p['reconnect'] == false ? 0 : prof.maxRetries,
      prof.fallback && p['fallback'] != false, prof.mode);
}

double autoCacheAfterStall(Map<String, dynamic> cfg) {
  final cur = (cfg['auto_live_cache'] as num? ?? kAutoSteps[1]).toDouble();
  final nxt = kAutoSteps.firstWhere((s) => s > cur + 0.01, orElse: () => kAutoSteps.last);
  cfg['auto_live_cache'] = nxt;
  cfg['auto_stable_since'] = DateTime.now().millisecondsSinceEpoch ~/ 1000;
  return nxt;
}

bool autoCacheRelax(Map<String, dynamic> cfg) {
  final now = DateTime.now().millisecondsSinceEpoch ~/ 1000;
  final since = (cfg['auto_stable_since'] as num?)?.toInt() ?? now;
  final cur = (cfg['auto_live_cache'] as num? ?? kAutoSteps[1]).toDouble();
  if (now - since >= 7200 && cur > kAutoSteps.first) {
    cfg['auto_live_cache'] = kAutoSteps.lastWhere((s) => s < cur - 0.01);
    cfg['auto_stable_since'] = now;
    return true;
  }
  return false;
}

/// Niveau de l'appareil d'après ses cœurs et sa mémoire.
(int, int, String) hardware() {
  final cores = Platform.numberOfProcessors;
  var ram = 0;
  try {
    if (Platform.isAndroid || Platform.isLinux) {
      final l = File('/proc/meminfo').readAsLinesSync().first;
      ram = (int.tryParse(RegExp(r'\d+').firstMatch(l)?.group(0) ?? '') ?? 0) ~/ 1024;
    }
  } catch (_) {}
  final tier = (cores <= 2 || (ram > 0 && ram < 2500)) ? 'low' : (cores >= 8 && ram >= 6000 ? 'high' : 'mid');
  return (cores, ram, tier);
}

// ============================================================ 4. guide TV XMLTV
final RegExp _progRe = RegExp(r'<programme\b([^>]*)>(.*?)</programme>', dotAll: true);
final RegExp _attrRe = RegExp(r'(\w+)="([^"]*)"');
final RegExp _titleRe = RegExp(r'<title\b[^>]*>(.*?)</title>', dotAll: true);
final RegExp _descRe = RegExp(r'<desc\b[^>]*>(.*?)</desc>', dotAll: true);
final RegExp _chanRe = RegExp(r'<channel\b[^>]*\bid="([^"]*)"[^>]*>(.*?)</channel>', dotAll: true);
final RegExp _dnameRe = RegExp(r'<display-name\b[^>]*>(.*?)</display-name>', dotAll: true);

String _xmlText(String s) {
  s = s.replaceAllMapped(RegExp(r'<!\[CDATA\[(.*?)\]\]>', dotAll: true), (m) => m.group(1)!);
  s = s.replaceAll(RegExp(r'<[^>]+>'), '');
  return s
      .replaceAll('&lt;', '<')
      .replaceAll('&gt;', '>')
      .replaceAll('&quot;', '"')
      .replaceAll('&apos;', "'")
      .replaceAll('&#39;', "'")
      .replaceAll('&amp;', '&')
      .trim();
}

int xmltvTime(String s) {
  final m = RegExp(r'(\d{4})(\d\d)(\d\d)(\d\d)(\d\d)(\d\d)\s*([+-]\d{4})?').firstMatch(s.trim());
  if (m == null) return 0;
  int g(int i) => int.parse(m.group(i)!);
  final utc = DateTime.utc(g(1), g(2), g(3), g(4), g(5), g(6)).millisecondsSinceEpoch ~/ 1000;
  final off = m.group(7) ?? '+0000';
  final secs = (off[0] == '+' ? 1 : -1) * (int.parse(off.substring(1, 3)) * 3600 + int.parse(off.substring(3, 5)) * 60);
  return utc - secs;
}

/// Lit un guide XMLTV (éventuellement .gz) ; à lancer dans un isolat (compute).
Map<String, dynamic> parseXmltv(List<int> data) {
  if (data.length > 2 && data[0] == 0x1f && data[1] == 0x8b) data = gzip.decode(data);
  final text = utf8.decode(data, allowMalformed: true);
  final now = DateTime.now().millisecondsSinceEpoch ~/ 1000;
  final lo = now - 3 * 3600, hi = now + 30 * 3600;
  final names = <String, String>{};
  for (final m in _chanRe.allMatches(text)) {
    for (final d in _dnameRe.allMatches(m.group(2)!)) {
      final k = norm(stripQuality(_xmlText(d.group(1)!))).replaceAll(RegExp(r'[^a-z0-9]+'), '');
      if (k.isNotEmpty) names.putIfAbsent(k, () => m.group(1)!);
    }
  }
  final progs = <String, List<List<dynamic>>>{};
  for (final m in _progRe.allMatches(text)) {
    final a = {for (final x in _attrRe.allMatches(m.group(1)!)) x.group(1)!: x.group(2)!};
    final st = xmltvTime(a['start'] ?? ''), sp0 = xmltvTime(a['stop'] ?? '');
    final sp = sp0 == 0 ? st + 1800 : sp0;
    if (st == 0 || sp < lo || st > hi) continue;
    final t = _titleRe.firstMatch(m.group(2)!), d = _descRe.firstMatch(m.group(2)!);
    var desc = d == null ? '' : _xmlText(d.group(1)!);
    if (desc.length > 400) desc = desc.substring(0, 400);
    progs.putIfAbsent(a['channel'] ?? '', () => []).add([st, sp, t == null ? '' : _xmlText(t.group(1)!), desc]);
  }
  for (final v in progs.values) {
    v.sort((a, b) => (a[0] as int).compareTo(b[0] as int));
  }
  return {'progs': progs, 'names': names, 'updated': now};
}

/// Programmes en cours et à venir d'une chaîne (même forme que l'EPG Xtream).
List<Map<String, dynamic>> guideEpg(Map<String, dynamic>? guide, Item it) {
  if (guide == null) return [];
  final progs = (guide['progs'] as Map?) ?? {};
  var cid = it.tvgId;
  if (!progs.containsKey(cid)) {
    final k = norm(displayName(it.name)).replaceAll(RegExp(r'[^a-z0-9]+'), '');
    cid = '${((guide['names'] as Map?) ?? {})[k] ?? ''}';
  }
  final now = DateTime.now().millisecondsSinceEpoch ~/ 1000;
  final out = <Map<String, dynamic>>[];
  for (final p in (progs[cid] as List?) ?? const []) {
    final l = p as List;
    if ((l[1] as num) > now) {
      out.add({'title': l[2], 'start_ts': (l[0] as num).toInt(), 'stop_ts': (l[1] as num).toInt(), 'desc': l[3]});
    }
    if (out.length >= 4) break;
  }
  return out;
}

// ============================================================ 5. maintenance
/// Supprime les fichiers trop vieux puis les plus anciens au-delà de maxMb. Renvoie (fichiers, octets).
Future<(int, int)> cleanCache(List<Directory> dirs, int maxMb, {int maxAgeDays = 60}) async {
  final files = <(DateTime, int, File)>[];
  final now = DateTime.now();
  var removed = 0, freed = 0;
  for (final d in dirs) {
    if (!await d.exists()) continue;
    await for (final e in d.list(recursive: true, followLinks: false)) {
      if (e is! File) continue;
      try {
        final st = await e.stat();
        if (now.difference(st.modified).inDays > maxAgeDays) {
          await e.delete();
          removed++;
          freed += st.size;
        } else {
          files.add((st.modified, st.size, e));
        }
      } catch (_) {}
    }
  }
  var total = files.fold<int>(0, (a, f) => a + f.$2);
  final limit = maxMb * 1024 * 1024;
  files.sort((a, b) => a.$1.compareTo(b.$1));
  for (final f in files) {
    if (total <= limit) break;
    try {
      await f.$3.delete();
      total -= f.$2;
      removed++;
      freed += f.$2;
    } catch (_) {}
  }
  return (removed, freed);
}

/// Teste qu'un flux répond et envoie des données.
Future<(bool, String)> probeStream(String url, String ua, {Duration timeout = const Duration(seconds: 8)}) async {
  final c = HttpClient()..connectionTimeout = timeout;
  try {
    final rq = await c.getUrl(Uri.parse(url)).timeout(timeout);
    rq.headers.set('User-Agent', ua);
    rq.headers.set('Range', 'bytes=0-65535');
    final rs = await rq.close().timeout(timeout);
    if (rs.statusCode >= 400) return (false, 'HTTP ${rs.statusCode}');
    final first = await rs.first.timeout(timeout);
    if (first.isEmpty) return (false, 'aucune donnée');
    final ct = rs.headers.contentType?.mimeType ?? '';
    if (ct.contains('html')) return (false, 'page web au lieu d’une vidéo');
    return (true, '${rs.statusCode} · $ct');
  } catch (e) {
    final m = '$e';
    return (false, m.length > 120 ? m.substring(0, 120) : m);
  } finally {
    c.close(force: true);
  }
}
