// Pages principales façon OCTO+ : Accueil, Films, Séries, Chaînes TV, collections (plateformes, studios).
import 'dart:math';

import 'package:flutter/material.dart';

import '../core/meta.dart';
import '../core/models.dart';
import '../core/store.dart';
import '../core/text.dart';
import 'browse.dart';
import 'hero.dart';
import 'nav.dart';
import 'octo.dart';
import 'scope.dart';
import 'settings.dart';
import 'theme.dart';
import 'widgets.dart';

typedef ListCompute = Future<List<Map<String, dynamic>>> Function(String key, String lang);

// ---------------------------------------------------------------- rapprochement TMDB ↔ liste
List<CardData> matchCards(BuildContext context, AppState s, List<Map<String, dynamic>> res, CardStyle style,
    {bool onlyAvailable = true}) {
  final out = <CardData>[];
  final seen = <String>{};
  for (final r in res) {
    final lib = s.matchTitle('${r['kind']}', '${r['title']}', '${r['original_title'] ?? ''}', '${r['year'] ?? ''}');
    if (onlyAvailable && lib == null) continue;
    if (lib != null && !seen.add(lib.url)) continue;
    final poster = '${r['poster'] ?? ''}';
    final img = switch (style) {
      CardStyle.land || CardStyle.big || CardStyle.resume => '${r['backdrop'] ?? ''}'.isNotEmpty ? '${r['backdrop']}' : poster,
      _ => poster.isEmpty ? '' : hires(poster, 'w500'),
    };
    final title = '${r['title']}';
    out.add(CardData(
      title: title, image: img, lib: lib, unavailable: lib == null,
      onTap: () => lib != null ? openItem(context, lib) : toast(context, '« $title » n\'est pas disponible dans votre liste.'),
    ));
  }
  return out;
}

/// Rangée alimentée par une liste TMDB (mise en cache pour la journée), chargée quand elle apparaît.
class AsyncRow extends StatefulWidget {
  final String title;
  final CardStyle style;
  final String listName;
  final ListCompute compute;
  final List<CardData> Function(BuildContext c, List<Map<String, dynamic>> res) toCards;
  final List<CardData> Function(BuildContext c)? fallback;
  final int minItems;
  final void Function(BuildContext c, List<CardData> all)? onMore;
  const AsyncRow({super.key, required this.title, required this.style, required this.listName, required this.compute,
      required this.toCards, this.fallback, this.minItems = 3, this.onMore});
  @override
  State<AsyncRow> createState() => _AsyncRowState();
}

class _AsyncRowState extends State<AsyncRow> {
  List<Map<String, dynamic>>? _res;
  @override
  void initState() {
    super.initState();
    final s = AppScope.read(context);
    _res = s.listNow(widget.listName);
    if (_res == null && s.tmdbKey.isNotEmpty) {
      s.tmdbList(widget.listName, widget.compute).then((r) {
        if (mounted) setState(() => _res = r);
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    final s = AppScope.of(context);
    List<CardData> cards;
    if (s.tmdbKey.isEmpty || (_res != null && _res!.isEmpty)) {
      cards = widget.fallback?.call(context) ?? const [];
    } else {
      cards = _res == null ? const [] : widget.toCards(context, _res!);
    }
    if (cards.length < widget.minItems) return const SizedBox.shrink();
    return OctoRow(
      title: widget.title, style: widget.style, items: cards.take(40).toList(),
      onMore: widget.onMore == null ? null : () => widget.onMore!(context, cards),
    );
  }
}

// ---------------------------------------------------------------- rangées communes
List<CardData> resumeCards(BuildContext context, AppState s, {String? kind}) {
  final out = <CardData>[];
  for (final e in s.continueItems()) {
    final k = e.item.series != null ? 'series' : e.item.kind;
    if (kind != null && k != kind) continue;
    final pr = s.progressOf(e.url);
    final len = ((pr?['len'] as num?) ?? 0).toInt(), pos = ((pr?['pos'] as num?) ?? 0).toInt();
    final mins = max(1, (len - pos) ~/ 60000);
    final se = e.item.series;
    out.add(CardData(
      title: e.title, image: e.logo, lib: e.lib, progress: e.progress,
      remain: se != null ? 'S${se['season']}, E${se['num']}  •  ${mins}mn' : '${mins}mn',
      onTap: () => playItems(context, [e.item], 0),
    ));
  }
  return out;
}

List<CardData> tileCards(BuildContext context, AppState s, String kind, {int limit = 24}) => [
      for (final t in s.categories(kind, limit: limit, special: true))
        CardData(title: t.name, sub: t.sub, c1: t.special ? 0xFF2A3140 : 0, onTap: () => openCategory(context, t)),
    ];

Widget actorsRow(AppState s) => AsyncRow(
      title: 'Les acteurs populaires',
      style: CardStyle.actor,
      listName: 'people',
      compute: tmdbPopularPeople,
      toCards: (c, res) => [
        for (final p in res.take(30))
          CardData(title: '${p['name']}', image: '${p['photo']}',
              onTap: () => openPerson(c, name: '${p['name']}', id: (p['tmdb_id'] as num?)?.toInt(), photo: '${p['photo']}')),
      ],
    );

Widget trendingRow(AppState s, String kind, {String title = 'Top de la semaine', CardStyle style = CardStyle.land}) {
  final tk = kind == 'movie' ? 'movie' : 'tv';
  return AsyncRow(
    title: title,
    style: style,
    listName: 'trend3-$tk',
    compute: (k, l) => tmdbTrending(k, l, tk),
    toCards: (c, res) => matchCards(c, s, res, style),
    fallback: (c) {
      final pool = List<Item>.of(s.byKind[kind] ?? [])
        ..sort((a, b) => (double.tryParse(b.ratingStr) ?? 0).compareTo(double.tryParse(a.ratingStr) ?? 0));
      return [for (final it in pool.take(14)) CardData(title: it.title, image: it.logo, lib: it, onTap: () => openItem(c, it))];
    },
    onMore: (c, all) => openCollection(c, title, cards: all),
  );
}

/// Chaînes (programme en cours ou à venir via l'EPG Xtream).
class ChannelsRow extends StatefulWidget {
  final String title;
  final List<Item> channels;
  final bool next; // « À ne pas manquer » : programme suivant + heure
  final bool epg;
  final VoidCallback? onMore;
  const ChannelsRow({super.key, required this.title, required this.channels, this.next = false, this.epg = true, this.onMore});
  @override
  State<ChannelsRow> createState() => _ChannelsRowState();
}

class _ChannelsRowState extends State<ChannelsRow> {
  final Map<String, List<Map<String, dynamic>>> _epg = {};
  @override
  void initState() {
    super.initState();
    if (!widget.epg) return;
    final s = AppScope.read(context);
    for (final c in widget.channels.take(14)) {
      if (c.streamId.isEmpty) continue;
      s.epg(c).then((p) {
        if (p.isNotEmpty && mounted) setState(() => _epg[c.url] = p);
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    final list = widget.channels;
    final cards = <CardData>[];
    for (final ch in list) {
      final p = _epg[ch.url];
      final prog = p == null ? null : (widget.next ? (p.length > 1 ? p[1] : null) : p.first);
      if (widget.next && prog == null) continue;
      var progress = 0.0;
      var time = '';
      final st = prog?['start_ts'], en = prog?['stop_ts'];
      if (st is int && en is int) {
        if (widget.next) {
          time = fmtHm(DateTime.fromMillisecondsSinceEpoch(st * 1000));
        } else {
          final now = DateTime.now().millisecondsSinceEpoch / 1000;
          progress = clampK((now - st) / max(1, en - st), .02, 1);
        }
      }
      cards.add(CardData(
        title: '${prog?['title'] ?? ''}'.isNotEmpty ? '${prog!['title']}' : ch.title,
        overlay: ch.title, image: ch.logo, logoMode: true, progress: progress, time: time,
        onTap: () => openItem(context, ch, playlist: list),
      ));
    }
    return OctoRow(title: widget.title, style: CardStyle.wide, items: cards, onMore: widget.onMore);
  }
}

// ---------------------------------------------------------------- collections (plateformes, studios, « voir tout »)
void openCollection(BuildContext context, String title,
    {List<CardData>? cards, String? listName, ListCompute? compute}) {
  Navigator.of(context).push(MaterialPageRoute(
      builder: (_) => CollectionScreen(title: title, cards: cards, listName: listName, compute: compute)));
}

class CollectionScreen extends StatefulWidget {
  final String title;
  final List<CardData>? cards;
  final String? listName;
  final ListCompute? compute;
  const CollectionScreen({super.key, required this.title, this.cards, this.listName, this.compute});
  @override
  State<CollectionScreen> createState() => _CollectionScreenState();
}

class _CollectionScreenState extends State<CollectionScreen> {
  List<Map<String, dynamic>>? _res;
  @override
  void initState() {
    super.initState();
    if (widget.cards == null && widget.listName != null && widget.compute != null) {
      AppScope.read(context).tmdbList(widget.listName!, widget.compute!).then((r) {
        if (mounted) setState(() => _res = r);
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    final s = AppScope.of(context);
    final phone = isPhone(context);
    final sz = MediaQuery.sizeOf(context);
    final k = scaleFor(sz.width, sz.height, phone);
    final cards = widget.cards ?? (_res == null ? null : matchCards(context, s, _res!, CardStyle.posterBig));
    final img = cardImageSize(CardStyle.posterBig, k);
    return UiK(
      k: k,
      phone: phone,
      child: Scaffold(
        appBar: AppBar(title: Text(widget.title, style: const TextStyle(fontWeight: FontWeight.w800))),
        body: cards == null
            ? const Center(child: CircularProgressIndicator(color: kAccent))
            : cards.isEmpty
                ? const Center(
                    child: Padding(
                      padding: EdgeInsets.all(30),
                      child: Text("Aucun titre de cette sélection n'est disponible dans votre liste pour le moment.",
                          textAlign: TextAlign.center, style: TextStyle(color: kMuted)),
                    ))
                : GridView.builder(
                    padding: EdgeInsets.fromLTRB(phone ? 14 : 26, 12, phone ? 14 : 26, 60),
                    gridDelegate: SliverGridDelegateWithMaxCrossAxisExtent(
                      maxCrossAxisExtent: img.width + 16, mainAxisExtent: img.height + 16,
                      crossAxisSpacing: 12, mainAxisSpacing: 14),
                    itemCount: cards.length,
                    itemBuilder: (c, i) => Center(child: OctoCard(style: CardStyle.posterBig, d: cards[i], k: k)),
                  ),
      ),
    );
  }
}

Widget providersRow(AppState s, String kind) {
  final tk = kind == 'movie' ? 'movie' : 'tv';
  return AsyncRow(
    title: 'En streaming sur',
    style: CardStyle.provider,
    listName: 'providers-$tk',
    compute: (k, l) => tmdbProviderLogos(k, l, tk),
    minItems: 1,
    toCards: (c, res) {
      final logos = {for (final r in res) '${r['id']}': '${r['logo']}'};
      return [
        for (final (id, name) in kProviders)
          CardData(
            title: name, image: logos['$id'] ?? '',
            onTap: () => openCollection(c, name,
                listName: 'prov-$tk-$id',
                compute: (k, l) => tmdbDiscover(k, l, tk, pages: 6,
                    params: {'with_watch_providers': '$id', 'watch_region': 'FR', 'sort_by': 'popularity.desc'})),
          ),
      ];
    },
  );
}

Widget studiosRow(BuildContext context) => OctoRow(
      title: '',
      style: CardStyle.studio,
      items: [
        for (final (name, ids, c1, c2) in kStudios)
          CardData(
            title: name, c1: c1, c2: c2,
            onTap: () => openCollection(context, name,
                listName: 'studio-$ids',
                compute: (k, l) => tmdbDiscover(k, l, 'movie', pages: 6, params: {'with_companies': ids, 'sort_by': 'popularity.desc'})),
          ),
      ],
    );

// ---------------------------------------------------------------- Accueil
class HomePage extends StatefulWidget {
  final bool collapsed;
  const HomePage({super.key, this.collapsed = false});
  @override
  State<HomePage> createState() => _HomePageState();
}

class _HomePageState extends State<HomePage> {
  int _built = -1;
  List<Item> _hero = [];
  Set<String> _new = {};

  void _prepare(AppState s) {
    if (_built == s.libVersion) return;
    _built = s.libVersion;
    final news = [...s.recent('movie', 10), ...s.recent('series', 8)];
    final pool = news.where((i) => i.logo.isNotEmpty).toList()..shuffle(Random());
    _hero = pool.take(7).toList();
    _new = news.map((e) => e.url).toSet();
  }

  @override
  Widget build(BuildContext context) {
    final s = AppScope.of(context);
    if (s.sources.isEmpty) return const _Welcome();
    if (s.items.isEmpty) return const _Loading();
    _prepare(s);
    final news = [...s.recent('movie', 8), ...s.recent('series', 6)]..sort((a, b) => b.addedInt.compareTo(a.addedInt));
    return ListView(
      key: PageStorageKey('home-${s.libVersion}'),
      padding: const EdgeInsets.only(bottom: 90),
      children: [
        if (_hero.isNotEmpty)
          HeroBanner(key: ValueKey('hero-home-${s.libVersion}'), pageTitle: 'Accueil', items: _hero, newUrls: _new,
              collapsed: widget.collapsed)
        else
          const PageTitle('Accueil'),
        OctoRow(title: 'Reprendre', style: CardStyle.resume, items: resumeCards(context, s)),
        ChannelsRow(key: ValueKey('ch-${s.libVersion}'), title: 'Les chaînes du moment', channels: s.trendingChannels(24),
            onMore: () => openRoot(context, 'live')),
        trendingRow(s, 'movie'),
        OctoRow(title: 'Films en ce moment', style: CardStyle.posterSm, onMore: () => openBrowse(context, 'movie'), items: [
          for (final it in s.recent('movie', 40)) CardData(title: it.title, image: it.logo, lib: it, fetchMeta: false, onTap: () => openItem(context, it)),
        ]),
        OctoRow(title: 'Séries en ce moment', style: CardStyle.posterSm, onMore: () => openBrowse(context, 'series'), items: [
          for (final it in s.recent('series', 40)) CardData(title: it.title, image: it.logo, lib: it, fetchMeta: false, onTap: () => openItem(context, it)),
        ]),
        OctoRow(title: '', style: CardStyle.tile, items: tileCards(context, s, 'movie')),
        OctoRow(title: 'Nouveautés sur $kAppTitle', style: CardStyle.big, items: [
          for (final it in news)
            CardData(title: it.title, image: it.logo, lib: it, badge: 'Nouveauté',
                sub: '${it.kind == 'series' ? 'Séries' : 'Films'} · ${prettyGroup(it.group)}', onTap: () => openItem(context, it)),
        ]),
        OctoRow(title: '', style: CardStyle.tile, items: tileCards(context, s, 'series')),
        actorsRow(s),
      ],
    );
  }
}

// ---------------------------------------------------------------- Films / Séries
class MediaPage extends StatefulWidget {
  final String kind;
  final bool collapsed;
  const MediaPage({super.key, required this.kind, this.collapsed = false});
  @override
  State<MediaPage> createState() => _MediaPageState();
}

class _MediaPageState extends State<MediaPage> {
  int _built = -1;
  List<Item> _hero = [];
  List<Item> _fav = [];

  void _prepare(AppState s) {
    if (_built == s.libVersion) return;
    _built = s.libVersion;
    final pool = s.recent(widget.kind, 20).where((i) => i.logo.isNotEmpty).toList()..shuffle(Random());
    _hero = pool.take(7).toList();
    final all = s.byKind[widget.kind] ?? [];
    final rated = all.where((i) => (double.tryParse(i.ratingStr) ?? 0) >= 7).toList()..shuffle(Random());
    _fav = (rated.isNotEmpty ? rated : (List<Item>.of(all)..shuffle(Random()))).take(12).toList();
  }

  @override
  Widget build(BuildContext context) {
    final s = AppScope.of(context);
    final kind = widget.kind;
    final title = kind == 'movie' ? 'Films' : 'Séries';
    final all = s.byKind[kind] ?? [];
    if (all.isEmpty) {
      return ListView(children: [
        PageTitle(title, top: widget.collapsed ? 96 : 38),
        Padding(
          padding: const EdgeInsets.all(34),
          child: Text(s.loading ? 'Chargement…' : 'Rien ici pour le moment.', style: const TextStyle(color: kMuted)),
        ),
      ]);
    }
    _prepare(s);
    final subKind = kind == 'series' ? 'Séries' : 'Films';
    final tk = kind == 'movie' ? 'movie' : 'tv';
    final year = DateTime.now().year;
    final dateKey = tk == 'movie' ? 'primary_release_year' : 'first_air_date_year';
    final sortHit = tk == 'movie' ? 'revenue.desc' : 'popularity.desc';
    final recent = s.recent(kind, 14);
    final groups = s.categories(kind, limit: 3);
    return ListView(
      key: PageStorageKey('$kind-${s.libVersion}'),
      padding: const EdgeInsets.only(bottom: 90),
      children: [
        if (_hero.isNotEmpty)
          HeroBanner(key: ValueKey('hero-$kind-${s.libVersion}'), pageTitle: title, items: _hero,
              newUrls: recent.map((e) => e.url).toSet(), collapsed: widget.collapsed)
        else
          PageTitle(title, top: widget.collapsed ? 96 : 38),
        OctoRow(title: 'Reprendre', style: CardStyle.resume, items: resumeCards(context, s, kind: kind)),
        trendingRow(s, kind),
        OctoRow(title: '', style: CardStyle.tile, items: tileCards(context, s, kind)),
        OctoRow(
          title: 'Nouveautés sur $kAppTitle', style: CardStyle.big, onMore: () => openBrowse(context, kind),
          items: [
            for (final it in recent)
              CardData(title: it.title, image: it.logo, lib: it, badge: 'Nouveauté',
                  sub: '$subKind · ${prettyGroup(it.group)}', onTap: () => openItem(context, it)),
          ],
        ),
        if (!kStoreBuild) providersRow(s, kind),
        AsyncRow(
          title: "Les plus gros succès de l'année", style: CardStyle.posterBig, listName: 'hits-$tk-$year',
          compute: (k, l) async => [
            ...await tmdbDiscover(k, l, tk, pages: 4, params: {'sort_by': sortHit, dateKey: '$year'}),
            ...await tmdbDiscover(k, l, tk, pages: 3, params: {'sort_by': sortHit, dateKey: '${year - 1}'}),
          ],
          toCards: (c, res) => matchCards(c, s, res, CardStyle.posterBig),
          onMore: (c, all) => openCollection(c, "Les plus gros succès de l'année", cards: all),
        ),
        AsyncRow(
          title: 'Top du mois', style: CardStyle.posterSm, listName: 'month-$tk',
          compute: (k, l) async => [
            ...await tmdbTrending(k, l, tk, pages: 2, window: 'day'),
            ...await tmdbDiscover(k, l, tk, pages: 4, params: {'sort_by': 'popularity.desc'}),
          ],
          toCards: (c, res) => matchCards(c, s, res, CardStyle.posterSm),
          onMore: (c, all) => openCollection(c, 'Top du mois', cards: all),
        ),
        OctoRow(title: 'Coups de cœur $kAppTitle', style: CardStyle.coeur, items: [
          for (final it in _fav)
            CardData(title: it.title, lib: it, sub: '$subKind · ${prettyGroup(it.group)}', onTap: () => openItem(context, it)),
        ]),
        if (kind == 'movie' && !kStoreBuild) studiosRow(context),
        for (final g in groups)
          OctoRow(
            title: g.name, style: CardStyle.posterSm, onMore: () => openCategory(context, g),
            items: [
              for (final it in all.where((i) => i.group == g.group).take(40))
                CardData(title: it.title, image: it.logo, lib: it, fetchMeta: false, onTap: () => openItem(context, it)),
            ],
          ),
        actorsRow(s),
      ],
    );
  }
}

// ---------------------------------------------------------------- Chaînes TV
class LivePage extends StatelessWidget {
  final bool collapsed;
  const LivePage({super.key, this.collapsed = false});
  @override
  Widget build(BuildContext context) {
    final s = AppScope.of(context);
    final live = s.byKind['live'] ?? [];
    final phone = isPhone(context);
    final header = PageTitle(
      'Chaînes TV',
      top: collapsed ? 96 : (phone ? 20 : 38),
      right: OutlinedButton(onPressed: () => openBrowse(context, 'live'), child: const Text('Toutes les chaînes')),
    );
    if (live.isEmpty) {
      return ListView(children: [
        header,
        Padding(padding: const EdgeInsets.all(34),
            child: Text(s.loading ? 'Chargement…' : 'Aucune chaîne pour le moment.', style: const TextStyle(color: kMuted))),
      ]);
    }
    final trending = s.trendingChannels(24);
    final cats = s.categories('live', limit: 40);
    final top = s.categories('live', limit: 6);
    return ListView(
      key: PageStorageKey('live-${s.libVersion}'),
      padding: const EdgeInsets.only(bottom: 90),
      children: [
        SafeArea(bottom: false, child: header),
        ChannelsRow(key: ValueKey('now-${s.libVersion}'), title: 'Les chaînes du moment', channels: trending),
        ChannelsRow(key: ValueKey('next-${s.libVersion}'), title: "À ne pas manquer aujourd'hui", channels: trending, next: true),
        OctoRow(title: '', style: CardStyle.tile, items: [
          CardData(title: 'Chaînes par catégories', c1: 0xFF2A3140,
              onTap: () => openCategory(context, const CatTile(kind: 'live', name: 'Chaînes par catégories', special: true))),
          CardData(title: 'Par pays', c1: 0xFF3B5BDB, onTap: () => openBrowse(context, 'live')),
          CardData(title: 'Mes chaînes favorites', c1: 0xFFE67700, onTap: () => openRoot(context, 'favorites')),
          CardData(title: 'Toutes les chaînes', c1: 0xFF364FC7, onTap: () => openBrowse(context, 'live')),
        ]),
        OctoRow(title: 'Catégories', style: CardStyle.tileBig, items: [
          for (final t in cats) CardData(title: t.name, sub: t.sub, onTap: () => openCategory(context, t)),
        ]),
        for (final g in top)
          ChannelsRow(
            key: ValueKey('g-${g.group}-${s.libVersion}'),
            title: g.name, epg: false, onMore: () => openCategory(context, g),
            channels: live.where((i) => i.group == g.group).take(40).toList(),
          ),
      ],
    );
  }
}

void openBrowse(BuildContext context, String kind) {
  final title = {'live': 'Chaînes TV', 'movie': 'Films', 'series': 'Séries'}[kind]!;
  Navigator.of(context).push(MaterialPageRoute(
      builder: (_) => Scaffold(appBar: AppBar(title: Text(title)), body: BrowseView(kind: kind, compact: true))));
}

/// Aller à une page principale (Accueil, Films…) depuis n'importe où.
void openRoot(BuildContext context, String key) {
  Navigator.of(context).popUntil((r) => r.isFirst);
  RootNav.of(context)?.go(key);
}

/// Accès à la navigation principale (menu latéral / barre du bas).
abstract class RootNavigator {
  void go(String key);
}

class RootNav extends InheritedWidget {
  final RootNavigator nav;
  const RootNav({super.key, required this.nav, required super.child});
  static RootNavigator? of(BuildContext c) => c.getInheritedWidgetOfExactType<RootNav>()?.nav;
  @override
  bool updateShouldNotify(RootNav old) => false;
}

class _Loading extends StatelessWidget {
  const _Loading();
  @override
  Widget build(BuildContext context) {
    final s = AppScope.of(context);
    return Center(
      child: s.loading
          ? const Column(mainAxisSize: MainAxisSize.min, children: [
              CircularProgressIndicator(color: kAccent), SizedBox(height: 14), Text('Chargement de votre liste…')])
          : const Text('Aucun contenu pour le moment.', style: TextStyle(color: kMuted)),
    );
  }
}

class _Welcome extends StatelessWidget {
  const _Welcome();
  @override
  Widget build(BuildContext context) {
    return Center(
      child: SingleChildScrollView(
        padding: const EdgeInsets.all(32),
        child: Column(mainAxisSize: MainAxisSize.min, children: [
          const Logo(height: 70),
          const SizedBox(height: 26),
          const Text('Bienvenue 👋', style: TextStyle(fontSize: 28, fontWeight: FontWeight.w800)),
          const SizedBox(height: 8),
          const Text('Ajoutez votre liste M3U ou votre compte Xtream Codes pour commencer.\n'
              "Aucun contenu n'est fourni avec l'application.",
              textAlign: TextAlign.center, style: TextStyle(color: kMuted, fontSize: 15)),
          const SizedBox(height: 22),
          FilledButton.icon(
            autofocus: true,
            onPressed: () => showSourceDialog(context),
            icon: const Icon(Icons.add),
            label: const Text('Ajouter une source'),
          ),
        ]),
      ),
    );
  }
}
