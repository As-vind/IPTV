// Modèles de données : éléments (chaîne, film, série) et épisodes.
import 'countries.dart';

class Ep {
  String name;
  int number;
  String url;
  List<String> opts;
  String plot;
  int runtime;
  String still;
  String rating;
  String airDate;

  Ep({
    required this.name,
    required this.number,
    required this.url,
    this.opts = const [],
    this.plot = '',
    this.runtime = 0,
    this.still = '',
    this.rating = '',
    this.airDate = '',
  });

  Map<String, dynamic> toJson() => {
        'name': name, 'num': number, 'url': url, 'opts': opts, 'plot': plot,
        'runtime': runtime, 'still': still, 'rating': rating, 'air_date': airDate,
      };

  factory Ep.fromJson(Map<String, dynamic> j) => Ep(
        name: '${j['name'] ?? ''}',
        number: (j['num'] as num?)?.toInt() ?? 0,
        url: '${j['url'] ?? ''}',
        opts: ((j['opts'] as List?) ?? const []).map((e) => '$e').toList(),
        plot: '${j['plot'] ?? ''}',
        runtime: (j['runtime'] as num?)?.toInt() ?? 0,
        still: '${j['still'] ?? ''}',
        rating: '${j['rating'] ?? ''}',
        airDate: '${j['air_date'] ?? ''}',
      );
}

class Item {
  String name;
  String url;
  String logo;
  String group;
  String kind; // live | movie | series
  String country;
  String streamId;
  String seriesId;
  String rating;
  String added;
  String tvgId;
  List<String> opts;
  Map<String, List<Ep>>? episodes; // séries reconstituées depuis une liste M3U

  // Champs calculés (non sauvegardés)
  String title = '';
  String year = '';
  String q = '';
  String ratingStr = '';
  String sub = '';

  Item({
    required this.name,
    required this.url,
    this.logo = '',
    this.group = 'Sans catégorie',
    this.kind = 'live',
    String? country,
    this.streamId = '',
    this.seriesId = '',
    this.rating = '',
    this.added = '',
    this.tvgId = '',
    this.opts = const [],
    this.episodes,
  }) : country = country ?? detectCountry(group: group, name: name);

  static Item make(String name, String url,
      {String? logo, String? group, String kind = 'live', String? country, String streamId = '',
      String seriesId = '', String rating = '', String added = '', String tvgId = '', List<String> opts = const []}) {
    final g = (group ?? '').trim().isEmpty ? 'Sans catégorie' : group!.trim();
    final n = name.trim().isEmpty ? 'Sans nom' : name.trim();
    return Item(
      name: n, url: url, logo: (logo ?? '').trim(), group: g, kind: kind,
      country: country ?? detectCountry(group: g, name: n), streamId: streamId, seriesId: seriesId,
      rating: rating, added: added, tvgId: tvgId, opts: opts,
    );
  }

  int get addedInt => int.tryParse(added) ?? 0;

  Map<String, dynamic> toJson() => {
        'name': name, 'url': url, 'logo': logo, 'group': group, 'kind': kind, 'country': country,
        if (streamId.isNotEmpty) 'stream_id': streamId,
        if (seriesId.isNotEmpty) 'series_id': seriesId,
        if (rating.isNotEmpty) 'rating': rating,
        if (added.isNotEmpty) 'added': added,
        if (tvgId.isNotEmpty) 'tvg_id': tvgId,
        if (opts.isNotEmpty) 'opts': opts,
        if (episodes != null)
          'episodes': episodes!.map((k, v) => MapEntry(k, v.map((e) => e.toJson()).toList())),
      };

  factory Item.fromJson(Map<String, dynamic> j) {
    Map<String, List<Ep>>? eps;
    final e = j['episodes'];
    if (e is Map) {
      eps = e.map((k, v) => MapEntry('$k', ((v as List?) ?? const [])
          .map((x) => Ep.fromJson(Map<String, dynamic>.from(x as Map)))
          .toList()));
    }
    return Item(
      name: '${j['name'] ?? ''}',
      url: '${j['url'] ?? ''}',
      logo: '${j['logo'] ?? ''}',
      group: '${j['group'] ?? 'Sans catégorie'}',
      kind: '${j['kind'] ?? 'live'}',
      country: j['country'] == null ? null : '${j['country']}',
      streamId: '${j['stream_id'] ?? ''}',
      seriesId: '${j['series_id'] ?? ''}',
      rating: '${j['rating'] ?? ''}',
      added: '${j['added'] ?? ''}',
      tvgId: '${j['tvg_id'] ?? ''}',
      opts: ((j['opts'] as List?) ?? const []).map((x) => '$x').toList(),
      episodes: eps,
    );
  }
}

/// Élément à lire dans le lecteur (chaîne, film ou épisode).
class PlayItem {
  final String name;
  final String url;
  final String kind; // live | movie | episode
  final String logo;
  final String group;
  final String streamId;
  final List<String> opts;
  final Map<String, dynamic>? series; // {url, name, logo, season, num, ep_name}

  const PlayItem({
    required this.name,
    required this.url,
    required this.kind,
    this.logo = '',
    this.group = '',
    this.streamId = '',
    this.opts = const [],
    this.series,
  });

  factory PlayItem.of(Item it) => PlayItem(
        name: it.kind == 'live' ? (it.title.isEmpty ? it.name : it.title) : it.name,
        url: it.url, kind: it.kind, logo: it.logo, group: it.group, streamId: it.streamId, opts: it.opts,
      );

  Map<String, dynamic> toJson() => {
        'name': name, 'url': url, 'kind': kind, 'logo': logo, 'group': group,
        'stream_id': streamId, 'opts': opts, if (series != null) 'series': series,
      };

  factory PlayItem.fromJson(Map<String, dynamic> j) => PlayItem(
        name: '${j['name'] ?? ''}',
        url: '${j['url'] ?? ''}',
        kind: '${j['kind'] ?? 'movie'}',
        logo: '${j['logo'] ?? ''}',
        group: '${j['group'] ?? ''}',
        streamId: '${j['stream_id'] ?? ''}',
        opts: ((j['opts'] as List?) ?? const []).map((x) => '$x').toList(),
        series: j['series'] is Map ? Map<String, dynamic>.from(j['series'] as Map) : null,
      );
}
