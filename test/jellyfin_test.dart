// Serveur Jellyfin simulé : connexion, bibliothèques films + séries, épisodes rangés par saison.
import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:iptv_player/core/jellyfin.dart';
import 'package:iptv_player/ui/octo.dart';

void main() {
  late HttpServer srv;
  var logins = 0;
  setUp(() async {
    srv = await HttpServer.bind(InternetAddress.loopbackIPv4, 0);
    srv.listen((req) async {
      final p = req.uri.path;
      final q = req.uri.queryParameters;
      Object? body;
      if (p == '/Users/AuthenticateByName') {
        final b = jsonDecode(await utf8.decoder.bind(req).join()) as Map;
        if (b['Username'] == 'bob' && b['Pw'] == 'pw') {
          logins++;
          body = {'AccessToken': 'tok$logins', 'User': {'Id': 'u1'}};
        } else {
          req.response.statusCode = 401;
        }
      } else if (req.headers.value('X-Emby-Token') == null) {
        req.response.statusCode = 401;
      } else if (p == '/Users/u1/Views') {
        body = {'Items': [
          {'Id': 'v1', 'Name': 'Films', 'CollectionType': 'movies'},
          {'Id': 'v2', 'Name': 'Séries', 'CollectionType': 'tvshows'},
          {'Id': 'v3', 'Name': 'Musique', 'CollectionType': 'music'},
        ]};
      } else if (p == '/Users/u1/Items' && q['ParentId'] == 'v1') {
        body = {'Items': [
          {'Id': 'm1', 'Name': 'Le Film', 'ProductionYear': 2021, 'Genres': ['Drame'], 'ImageTags': {'Primary': 'a'},
           'DateCreated': '2026-01-02T10:00:00Z', 'CommunityRating': 7.4},
        ]};
      } else if (p == '/Users/u1/Items' && q['ParentId'] == 'v2' && q['IncludeItemTypes'] == 'Series') {
        body = {'Items': [{'Id': 's1', 'Name': 'Ma Série', 'Genres': [], 'ImageTags': {'Primary': 'b'}}]};
      } else if (p == '/Users/u1/Items' && q['ParentId'] == 'v2' && q['IncludeItemTypes'] == 'Episode') {
        body = {'Items': [
          {'Id': 'e2', 'Name': 'Deux', 'SeriesId': 's1', 'ParentIndexNumber': 1, 'IndexNumber': 2, 'RunTimeTicks': 27000000000},
          {'Id': 'e1', 'Name': 'Un', 'SeriesId': 's1', 'ParentIndexNumber': 1, 'IndexNumber': 1, 'Overview': 'Début'},
          {'Id': 'e3', 'Name': 'Trois', 'SeriesId': 's1', 'ParentIndexNumber': 2, 'IndexNumber': 1},
        ]};
      } else {
        req.response.statusCode = 404;
      }
      if (body != null) req.response.write(jsonEncode(body));
      await req.response.close();
    });
  });
  tearDown(() => srv.close(force: true));

  test('Jellyfin : films, séries et épisodes', () async {
    final src = <String, dynamic>{'server': '127.0.0.1:${srv.port}/web/index.html', 'user': 'bob', 'password': 'pw'};
    final cl = JellyfinClient.of(src);
    expect(cl.base, 'http://127.0.0.1:${srv.port}');
    final (items, info) = await cl.loadAll();
    expect(info, contains('"movies":1'));
    final movie = items.firstWhere((i) => i.kind == 'movie');
    expect(movie.name, 'Le Film (2021)');
    expect(movie.group, 'Drame');
    expect(movie.url, 'http://127.0.0.1:${srv.port}/Videos/m1/stream?static=true&api_key=tok1');
    expect(movie.logo, contains('/Items/m1/Images/Primary'));
    final show = items.firstWhere((i) => i.kind == 'series');
    expect(show.group, 'Séries');
    expect(show.episodes!.keys.toSet(), {'1', '2'});
    expect(show.episodes!['1']!.map((e) => e.name).toList(), ['Un', 'Deux']);
    expect(show.episodes!['1']![1].runtime, 45);
    // jeton déjà connu : pas de nouvelle connexion
    final again = JellyfinClient.of({...src, 'token': cl.token, 'uid': cl.uid, 'device': cl.deviceId});
    await again.loadAll();
    expect(logins, 1);
  });

  test('Jellyfin : mauvais mot de passe → message clair', () async {
    final cl = JellyfinClient.of({'server': 'http://127.0.0.1:${srv.port}', 'user': 'bob', 'password': 'non'});
    expect(cl.login(), throwsA(isA<JellyfinError>()));
  });

  test('Jellyfin : repli converti par le serveur', () {
    const d = 'http://192.168.1.20:8096/Videos/abc123/stream?static=true&api_key=tok';
    expect(jellyfinIsDirect(d), true);
    expect(jellyfinIsDirect('http://x/live/u/p/1.ts'), false);
    final t = jellyfinTranscodeUrl(d);
    expect(t, startsWith('http://192.168.1.20:8096/Videos/abc123/master.m3u8?MediaSourceId=abc123&api_key=tok'));
    expect(t, contains('VideoCodec=h264'));
    expect(jellyfinIsDirect(t), false);
  });

  test('rangées : un nombre entier de cases remplit la largeur', () {
    for (final w in [700.0, 920.0, 1100.0, 1400.0, 1800.0, 2400.0]) {
      for (final st in [CardStyle.posterSm, CardStyle.land, CardStyle.big]) {
        const gap = 12.0;
        final k = fitRowK(st, .8, w, gap, 100);
        final cw = cardImageSize(st, k).width;
        final n = ((w + gap) / (cw + gap)).round();
        expect((n * cw + (n - 1) * gap - w).abs() < 1, true, reason: '$st à $w px');
        expect(k / .8, inInclusiveRange(.7, 1.3));
      }
    }
  });
}
