// Lecture des listes M3U / M3U8 (+ regroupement des épisodes en séries).
import 'countries.dart';
import 'models.dart';
import 'text.dart';

final RegExp _attrRe = RegExp(r'([A-Za-z0-9_\-]+)\s*=\s*"([^"]*)"');
final RegExp _epRe = RegExp(r'^(.*?)[\s._\-|:]*\bS(\d{1,2})[\s._\-]*E(\d{1,4})\b(.*)$', caseSensitive: false);

String guessKind(String url) {
  final u = url.toLowerCase();
  if (u.contains('/series/')) return 'series';
  if (u.contains('/movie/') || u.contains('/vod/') || RegExp(r'\.(mkv|mp4|avi|mov|wmv)(\?|$)').hasMatch(u)) {
    return 'movie';
  }
  return 'live';
}

String _strip(String s) {
  const chars = ' -|:._';
  var a = 0, b = s.length;
  while (a < b && chars.contains(s[a])) {
    a++;
  }
  while (b > a && chars.contains(s[b - 1])) {
    b--;
  }
  return s.substring(a, b);
}

/// Fonction de premier niveau : utilisable dans un isolat (compute).
List<Item> parseM3u(String text) {
  final items = <Item>[];
  Map<String, String>? cur;
  var opts = <String>[];
  for (final raw in const LineSplitter2().split(text)) {
    final line = raw.trim();
    if (line.isEmpty) continue;
    final up = line.length > 12 ? line.substring(0, 12).toUpperCase() : line.toUpperCase();
    if (up.startsWith('#EXTINF')) {
      final idx = line.indexOf(':');
      final body = idx >= 0 ? line.substring(idx + 1) : '';
      final attrs = <String, String>{};
      for (final m in _attrRe.allMatches(body)) {
        attrs[m.group(1)!.toLowerCase()] = m.group(2)!;
      }
      final rest = body.replaceAll(_attrRe, '');
      final ci = rest.indexOf(',');
      final name = ci >= 0 ? rest.substring(ci + 1).trim() : '';
      cur = {
        'name': name.isNotEmpty ? name : (attrs['tvg-name'] ?? ''),
        'logo': attrs['tvg-logo'] ?? attrs['logo'] ?? '',
        'group': attrs['group-title'] ?? '',
        'tvg_country': attrs['tvg-country'] ?? '',
        'tvg_id': attrs['tvg-id'] ?? '',
      };
    } else if (up.startsWith('#EXTGRP:')) {
      if (cur != null && (cur['group'] ?? '').isEmpty) cur['group'] = line.substring(8).trim();
    } else if (up.startsWith('#EXTVLCOPT:')) {
      opts.add(line.substring(11).trim());
    } else if (line.startsWith('#')) {
      continue;
    } else {
      final c = cur ?? {'name': line.split('/').last, 'logo': '', 'group': '', 'tvg_country': '', 'tvg_id': ''};
      final country = detectCountry(
          group: c['group'] ?? '', name: c['name'] ?? '', tvgCountry: c['tvg_country'] ?? '', tvgId: c['tvg_id'] ?? '');
      items.add(Item.make(c['name'] ?? '', line,
          logo: c['logo'], group: c['group'], kind: guessKind(line), country: country,
          opts: List.of(opts), tvgId: c['tvg_id'] ?? ''));
      cur = null;
      opts = <String>[];
    }
  }
  return groupM3uSeries(items);
}

List<Item> groupM3uSeries(List<Item> items) {
  final out = <Item>[];
  final series = <String, Item>{};
  for (final it in items) {
    if (it.kind == 'series' || it.kind == 'movie') {
      final m = _epRe.firstMatch(it.name);
      if (m != null && _strip(m.group(1)!).isNotEmpty) {
        final show = _strip(m.group(1)!);
        final key = '${titleKey(cleanTitle(show).$1)}|${it.group}';
        var s = series[key];
        if (s == null) {
          s = Item.make(show, 'm3u-series:${fnv(key)}', logo: it.logo, group: it.group, kind: 'series', country: it.country);
          s.episodes = {};
          series[key] = s;
          out.add(s);
        }
        final num = int.parse(m.group(3)!);
        final season = '${int.parse(m.group(2)!)}';
        final epName = _strip(m.group(4)!);
        s.episodes!.putIfAbsent(season, () => []).add(
            Ep(name: epName.isEmpty ? 'Épisode $num' : epName, num: num, url: it.url, opts: it.opts));
        if (s.logo.isEmpty && it.logo.isNotEmpty) s.logo = it.logo;
        continue;
      }
    }
    out.add(it);
  }
  for (final s in series.values) {
    for (final eps in s.episodes!.values) {
      eps.sort((a, b) => a.num.compareTo(b.num));
    }
  }
  return out;
}

/// Découpe en lignes (\n, \r\n ou \r) sans dépendre de dart:convert dans l'isolat.
class LineSplitter2 {
  const LineSplitter2();
  Iterable<String> split(String s) sync* {
    var start = 0;
    for (var i = 0; i < s.length; i++) {
      final c = s.codeUnitAt(i);
      if (c == 10 || c == 13) {
        yield s.substring(start, i);
        if (c == 13 && i + 1 < s.length && s.codeUnitAt(i + 1) == 10) i++;
        start = i + 1;
      }
    }
    if (start < s.length) yield s.substring(start);
  }
}
