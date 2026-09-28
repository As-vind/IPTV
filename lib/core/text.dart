// Utilitaires texte : normalisation, titres propres, catégories lisibles.
import 'countries.dart';

const Map<String, String> _accents = {
  'à': 'a', 'á': 'a', 'â': 'a', 'ã': 'a', 'ä': 'a', 'å': 'a', 'ç': 'c', 'è': 'e', 'é': 'e',
  'ê': 'e', 'ë': 'e', 'ì': 'i', 'í': 'i', 'î': 'i', 'ï': 'i', 'ñ': 'n', 'ò': 'o', 'ó': 'o',
  'ô': 'o', 'õ': 'o', 'ö': 'o', 'ù': 'u', 'ú': 'u', 'û': 'u', 'ü': 'u', 'ý': 'y', 'ÿ': 'y',
  'œ': 'oe', 'æ': 'ae', 'ß': 'ss',
};

String norm(String? s) {
  final l = (s ?? '').toLowerCase();
  final b = StringBuffer();
  for (final r in l.runes) {
    final c = String.fromCharCode(r);
    b.write(_accents[c] ?? c);
  }
  return b.toString();
}

String titleKey(String s) => norm(s).replaceAll(RegExp(r'[^a-z0-9]+'), '');

String initials(String? name) {
  final words = RegExp(r'[A-Za-zÀ-ÿ0-9]+').allMatches(name ?? '').map((m) => m.group(0)!).toList();
  if (words.isEmpty) return 'TV';
  if (words.length == 1) {
    final w = words.first;
    return (w.length > 3 ? w.substring(0, 3) : w).toUpperCase();
  }
  return (words[0][0] + words[1][0]).toUpperCase();
}

final RegExp _leadTagRe = RegExp(r'^\s*(?:[\[\(|]\s*([A-Za-z\-]{2,7})\s*[\]\)|]|([A-Z\-]{2,7})\s*(?:[:|»–]|\s-\s))\s*');
const Set<String> _leadOk = {'VF', 'VFF', 'VFQ', 'VOST', 'VOSTFR', 'MULTI', '4K', 'UHD', 'FHD', 'HD', 'NEW', 'VIP', 'TOP'};

String stripLeadTags(String s) {
  var out = s;
  for (var i = 0; i < 3; i++) {
    final m = _leadTagRe.firstMatch(out);
    if (m == null) break;
    final tok = (m.group(1) ?? m.group(2) ?? '').toUpperCase();
    if (resolveCountry(tok) != null || _leadOk.contains(tok)) {
      out = out.substring(m.end);
    } else {
      break;
    }
  }
  final t = out.trim();
  return t.isEmpty ? s : t;
}

final RegExp _qualityRe = RegExp(
    r'(?<![A-Za-z0-9])(4K|UHD|FHD|HD|SD|HEVC|H\.?265|H\.?264|x265|x264|2160p|1080p|720p|MULTI|VOSTFR|VOST|VFF|VFQ|VFi|VF|TRUEFRENCH|FRENCH|HDR10?|DV|3D|REMUX|WEB-?DL|BLURAY)(?![A-Za-z0-9])',
    caseSensitive: false);
final RegExp _yearParen = RegExp(r'[\(\[]\s*((?:19|20)\d{2})\s*[\)\]]');
final RegExp _yearEnd = RegExp(r'(?:\s[-–]\s*|\s)((?:19|20)\d{2})\s*$');

String _trimChars(String s, String chars) {
  var start = 0, end = s.length;
  while (start < end && chars.contains(s[start])) {
    start++;
  }
  while (end > start && chars.contains(s[end - 1])) {
    end--;
  }
  return s.substring(start, end);
}

/// « FR - Inception (2010) [4K] » → ('Inception', '2010')
(String, String) cleanTitle(String? name) {
  var s = stripLeadTags(name ?? '');
  var year = '';
  final m = _yearParen.firstMatch(s);
  if (m != null) {
    year = m.group(1)!;
    s = s.substring(0, m.start) + s.substring(m.end);
  } else {
    final m2 = _yearEnd.firstMatch(s);
    if (m2 != null) {
      year = m2.group(1)!;
      s = s.substring(0, m2.start);
    }
  }
  s = s.replaceAll(_qualityRe, '');
  s = s.replaceAll(RegExp(r'[\[\(]\s*[\]\)]'), '');
  s = s.replaceAll(RegExp(r'\s{2,}'), ' ');
  s = _trimChars(s, ' -|:._–');
  return (s.isEmpty ? (name ?? '').trim() : s, year);
}

final RegExp _grpPrefix = RegExp(
    r'^\s*[|\[(]?\s*(?:VOD|FILMS?|MOVIES?|S[ÉE]RIES?|TV|LIVE|CHA[IÎ]NES?)\s*(?:[|\])]\s*[|:\-–»]*|[|:\-–»]+)\s*',
    caseSensitive: false);

/// « VOD| ACTION » → « Action », « FR| GÉNÉRALISTES » → « Généralistes »
String prettyGroup(String? g) {
  final src = g ?? '';
  var s = _trimChars(stripLeadTags(src.replaceFirst(_grpPrefix, '')), ' |-:');
  s = _trimChars(stripLeadTags(s), ' |-:');
  if (s.isEmpty) s = src;
  if (s == s.toUpperCase() && s != s.toLowerCase() && s.length > 3) {
    s = s[0] + s.substring(1).toLowerCase();
  }
  return s;
}

String fmtMs(int ms) {
  var s = ms ~/ 1000;
  if (s < 0) s = 0;
  final h = s ~/ 3600, m = (s % 3600) ~/ 60, sec = s % 60;
  String two(int v) => v.toString().padLeft(2, '0');
  return h > 0 ? '$h:${two(m)}:${two(sec)}' : '${two(m)}:${two(sec)}';
}

String fmtRuntime(dynamic minutes) {
  final m = minutes is int ? minutes : int.tryParse('${minutes ?? ''}') ?? 0;
  if (m <= 0) return '';
  return m >= 60 ? '${m ~/ 60} h ${(m % 60).toString().padLeft(2, '0')}' : '$m min';
}

String fmtDate(String? s) {
  if (s == null || s.length < 10) return s ?? '';
  final p = s.substring(0, 10).split('-');
  if (p.length != 3) return s;
  return '${p[2]}/${p[1]}/${p[0]}';
}

String fmtHm(DateTime d) => '${d.hour.toString().padLeft(2, '0')}:${d.minute.toString().padLeft(2, '0')}';

/// Petite empreinte (FNV-1a 64 bits) pour nommer les fichiers de cache.
String fnv(String s) {
  var h = BigInt.parse('cbf29ce484222325', radix: 16);
  final prime = BigInt.parse('100000001b3', radix: 16);
  final mask = (BigInt.one << 64) - BigInt.one;
  for (final c in s.codeUnits) {
    h = ((h ^ BigInt.from(c)) * prime) & mask;
  }
  return h.toRadixString(16).padLeft(16, '0');
}

final RegExp adultRe = RegExp(r'(\badult[e]?s?\b|xxx|porn|\b18\s*\+|\+\s*18\b|erotic|érotique|\bsexy\b)', caseSensitive: false);

double clampD(double v, double lo, double hi) => v < lo ? lo : (v > hi ? hi : v);
