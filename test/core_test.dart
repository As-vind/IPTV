import 'package:flutter_test/flutter_test.dart';
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
}
