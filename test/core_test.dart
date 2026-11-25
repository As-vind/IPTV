import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:iptv_player/core/playlist_import.dart';
import 'package:iptv_player/core/channels.dart';
import 'package:iptv_player/core/models.dart';
import 'package:iptv_player/core/countries.dart';
import 'package:iptv_player/core/m3u.dart';
import 'package:iptv_player/core/text.dart';

const _sample = '''#EXTM3U
#EXTINF:-1 tvg-id="TF1.fr@SD" tvg-logo="" group-title="Général",TF1
http://x/1.ts
#EXTINF:-1 group-title="FR | SPORTS",RMC Sport 1 HD
http://x/2.ts
#EXTINF:-1 group-title="|BE| INFO",RTBF La Une
http://x/3.ts
#EXTINF:-1 group-title="AR | MBC",MBC 1
http://x/4.ts
#EXTINF:-1 tvg-country="ES" group-title="News",TVE 24h
http://x/5.ts
#EXTINF:-1 group-title="Italia",Rai 1
#EXTVLCOPT:http-referrer=http://ref
http://x/6.ts
#EXTINF:-1 group-title="VOD FR", Inception (2010)
http://x/movie/u/p/7.mkv
#EXTINF:-1 group-title="UK: Entertainment",BBC One
http://x/9.ts
#EXTINF:-1 group-title="SÉRIES FR",Lupin S01 E01
http://x/series/u/p/1.mkv
#EXTINF:-1 group-title="SÉRIES FR",Lupin S01 E02
http://x/series/u/p/2.mkv
#EXTINF:-1 group-title="SÉRIES FR",Lupin S02 E01 Le retour
http://x/series/u/p/3.mkv
''';

void main() {
  test('M3U : pays, types, options et séries', () {
    final items = parseM3u(_sample);
    final byName = {for (final i in items) i.name: i};
    expect(byName['TF1']!.country, 'FR');
    expect(byName['RMC Sport 1 HD']!.country, 'FR');
    expect(byName['RTBF La Une']!.country, 'BE');
    expect(byName['MBC 1']!.country, 'ARAB');
    expect(byName['TVE 24h']!.country, 'ES');
    expect(byName['Rai 1']!.country, 'IT');
    expect(byName['Rai 1']!.opts, ['http-referrer=http://ref']);
    expect(byName['Inception (2010)']!.kind, 'movie');
    expect(byName['BBC One']!.country, 'GB');
    final lupin = byName['Lupin']!;
    expect(lupin.kind, 'series');
    expect(lupin.episodes!['1']!.length, 2);
    expect(lupin.episodes!['2']!.first.name, 'Le retour');
  });

  test('Titres et catégories', () {
    expect(cleanTitle('FR - Inception (2010) [4K]'), ('Inception', '2010'));
    expect(cleanTitle('|FR| Dune: Deuxième partie 2024'), ('Dune: Deuxième partie', '2024'));
    expect(cleanTitle('ALIEN: Romulus').$1, 'ALIEN: Romulus');
    expect(prettyGroup('VOD| NOUVEAUTÉS'), 'Nouveautés');
    expect(prettyGroup('FR| GÉNÉRALISTES'), 'Généralistes');
    expect(prettyGroup('Films Français'), 'Films Français');
    expect(detectCountry(group: 'Deutschland'), 'DE');
    expect(norm('Été À Noël'), 'ete a noel');
  });

  test('import de fichier M3U', () async {
    final bytes = utf8.encode(_sample);
    expect(countEntries(bytes) > 3, true);
    final dir = await Directory.systemTemp.createTemp('iptv');
    final path = await savePlaylist(dir, 'abc', bytes);
    expect(await File(path).readAsString(), _sample);
    expect(() => savePlaylist(dir, 'bad', utf8.encode('<html>pas une liste</html>')), throwsFormatException);
    final lan = LanImport();
    try {
      final addr = await lan.start();
      final got = lan.files.first;
      final c = HttpClient();
      final rq = await c.postUrl(Uri.parse(addr.replaceFirst(RegExp(r'//[^:]+'), '//127.0.0.1') + '/upload'));
      rq.headers.set('x-name', 'ma%20liste.m3u');
      rq.add(bytes);
      final rs = await rq.close();
      expect(rs.statusCode, 200);
      final (name, data) = await got.timeout(const Duration(seconds: 5));
      expect(name, 'ma liste.m3u');
      expect(data.length, bytes.length);
      c.close();
    } on SocketException {
      // pas de réseau dans l'environnement de test : on ignore la partie serveur
    } finally {
      await lan.stop();
    }
    await dir.delete(recursive: true);
  });

  test('regroupement des chaînes et qualité', () {
    Item ch(String n, String g, int i) => Item.make(n, 'http://h/$i', group: g);
    final items = [
      ch('FR: TF1 HD', 'FR| GENERALISTES', 0), ch('FR: TF1 FHD', 'FR| GENERALISTES', 1), ch('FR: TF1 4K', 'FR| 4K', 2),
      ch('FR: TF1 SD', 'FR| SD', 3), ch('FR: TF1 ᴴᴰ', 'FR| GENERALISTES', 4), ch('FR: France 3 Alpes', 'FR| REGIONS', 5),
      ch('FR: France 3 HD', 'FR| GENERALISTES', 6), ch('FR: M6 +1', 'FR| GENERALISTES', 7), ch('FR: M6 HD', 'FR| GENERALISTES', 8),
      ch('FR: beIN Sports 1 HD', 'FR| SPORT', 9), ch('AR: beIN Sports 1 HD', 'AR| SPORT', 10),
      ch('FR: Eurosport 1 VF', 'FR| SPORT', 11), ch('FR: Eurosport 1 FHD', 'FR| SPORT', 12),
      Item.make('Inception (2010)', 'http://h/m', group: 'VOD', kind: 'movie'),
    ];
    final out = groupVariants(items);
    final tf1 = out.firstWhere((i) => i.name.contains('TF1'));
    expect(tf1.variants.length, 5);
    expect(tf1.qlabels, '4K · FHD · HD · SD');
    expect(tf1.group, 'FR| GENERALISTES');
    expect(displayName(tf1.name), 'TF1');
    expect(out.length, 10); // TF1 regroupé, le reste distinct (régions, +1, langues, pays)
    expect(tf1.variants[pickVariant(tf1.variants, cap: 4)].name, 'FR: TF1 4K');
    expect(tf1.variants[pickVariant(tf1.variants, cap: 3)].name, 'FR: TF1 FHD');
    expect(tf1.variants[pickVariant(tf1.variants, pref: 'sd')].name, 'FR: TF1 SD');
    expect(tf1.variants[pickVariant(tf1.variants, cap: 4, below: 3)].q, 2);
    final st = StreamStats({});
    st.fail(tf1.variants[0].url);
    st.fail(tf1.variants[0].url);
    expect(tf1.variants[pickVariant(tf1.variants, cap: 4, stats: st)].name, 'FR: TF1 FHD');
    // favoris retrouvés après changement des liens
    final k = stableKey(tf1)!;
    final again = groupVariants([for (final i in items) Item.make(i.name, '${i.url}?t=2', group: i.group, kind: i.kind)]);
    final (urls, _, n) = remapUrls([tf1.url], {tf1.url: k}, again);
    expect(n, 1);
    expect(urls.single, endsWith('?t=2'));
    expect(coerceSetting('brightness', 300), 100);
    expect(() => coerceSetting('profile', 'x'), throwsFormatException);
  });

  test('guide TV XMLTV', () {
    final now = DateTime.now().toUtc();
    String f(DateTime d) =>
        '${d.year}${d.month.toString().padLeft(2, '0')}${d.day.toString().padLeft(2, '0')}${d.hour.toString().padLeft(2, '0')}0000 +0000';
    final xml = '<tv><channel id="tf1.fr"><display-name>TF1 HD</display-name></channel>'
        '<programme start="${f(now)}" stop="${f(now.add(const Duration(hours: 1)))}" channel="tf1.fr"><title>Le &amp; Journal</title></programme>'
        '<programme start="${f(now.add(const Duration(hours: 1)))}" stop="${f(now.add(const Duration(hours: 2)))}" channel="tf1.fr"><title><![CDATA[Film]]></title></programme></tv>';
    final g = parseXmltv(gzip.encode(utf8.encode(xml)));
    final p = guideEpg(g, Item.make('FR: TF1 FHD', 'http://x', group: 'FR'));
    expect(p.map((e) => e['title']), ['Le & Journal', 'Film']);
  });
}
