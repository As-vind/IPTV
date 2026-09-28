// Accueil : bannière, reprise, chaînes du moment, films/séries en ce moment, catégories, nouveautés.
import 'dart:async';
import 'dart:math';

import 'package:flutter/material.dart';

import '../core/models.dart';
import '../core/store.dart';
import '../core/text.dart';
import 'nav.dart';
import 'scope.dart';
import 'settings.dart';
import 'theme.dart';
import 'widgets.dart';

class HomeView extends StatefulWidget {
  final void Function(int tab) onTab;
  const HomeView({super.key, required this.onTab});
  @override
  State<HomeView> createState() => _HomeViewState();
}

class _HomeViewState extends State<HomeView> {
  int _builtFor = -1;
  List<Item> _hero = [];
  List<Item> _chans = [];
  List<Item> _news = [];
  final Map<String, Map<String, dynamic>> _epg = {};
  final Map<String, Map<String, dynamic>> _meta = {};

  void _prepare(AppState s) {
    if (_builtFor == s.libVersion) return;
    _builtFor = s.libVersion;
    final pool = [...s.recent('movie', 30), ...s.recent('series', 20)].where((i) => i.logo.isNotEmpty).toList()..shuffle(Random());
    _hero = pool.take(6).toList();
    _chans = s.trendingChannels(24);
    _news = [...s.recent('movie', 12), ...s.recent('series', 8)]..sort((a, b) => b.addedInt.compareTo(a.addedInt));
    _epg.clear();
    for (final c in _chans) {
      if (c.streamId.isEmpty) continue;
      s.epg(c).then((p) {
        if (p.isNotEmpty && mounted) setState(() => _epg[c.url] = p.first);
      });
    }
    for (final i in [..._news, ..._hero]) {
      s.meta(i).then((m) {
        if (m != null && mounted) setState(() => _meta[i.url] = m);
      });
    }
    for (final c in s.continueItems()) {
      if (c.lib != null) {
        s.meta(c.lib!).then((m) {
          if (m != null && mounted) setState(() => _meta[c.lib!.url] = m);
        });
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    final s = AppScope.of(context);
    if (s.sources.isEmpty) return const _Welcome();
    if (s.items.isEmpty) {
      return Center(
        child: s.loading
            ? const Column(mainAxisSize: MainAxisSize.min, children: [
                CircularProgressIndicator(color: kAccent), SizedBox(height: 14), Text('Chargement de votre liste…')])
            : const Text('Aucun contenu pour le moment.', style: TextStyle(color: kMuted)),
      );
    }
    _prepare(s);
    final cont = s.continueItems();
    final wideW = WideCard.width(context);
    final wideH = wideW * 9 / 16 + 50;
    final posterW = PosterCard.width(context);
    final posterH = posterW * 1.5 + 46;
    final cat = CatTileCard.size(context);
    final movieCats = s.categories('movie', limit: 20, special: true);
    final seriesCats = s.categories('series', limit: 20, special: true);
    final topMovieGroups = s.categories('movie', limit: 3);
    final topSeriesGroups = s.categories('series', limit: 2);

    return ListView(padding: const EdgeInsets.only(bottom: 70), children: [
      if (_hero.isNotEmpty) HeroCarousel(items: _hero, meta: _meta),
      if (cont.isNotEmpty)
        Section(
          title: 'Reprendre la lecture',
          height: wideH,
          count: cont.length,
          itemBuilder: (c, i) {
            final e = cont[i];
            final m = e.lib == null ? null : _meta[e.lib!.url];
            return WideCard(
              image: '${m?['backdrop'] ?? ''}'.isNotEmpty ? '${m!['backdrop']}' : e.logo,
              title: e.title, sub: e.sub, progress: e.progress,
              onTap: () => playItems(c, [e.item], 0),
            );
          },
        ),
      if (_chans.isNotEmpty)
        Section(
          title: 'Les chaînes du moment',
          subtitle: 'Les chaînes les plus regardées actuellement',
          badge: 'LIVE',
          onMore: () => widget.onTab(3),
          height: wideH,
          count: _chans.length,
          itemBuilder: (c, i) {
            final ch = _chans[i];
            final e = _epg[ch.url];
            String sub = prettyGroup(ch.group);
            if (e != null) {
              final st = e['start_ts'] as int?, en = e['stop_ts'] as int?;
              if (st != null && en != null) {
                sub = '${fmtHm(DateTime.fromMillisecondsSinceEpoch(st * 1000))} – ${fmtHm(DateTime.fromMillisecondsSinceEpoch(en * 1000))}';
              }
            }
            return WideCard(
              image: ch.logo, logoMode: true, overlay: ch.title, badge: 'LIVE',
              title: '${e?['title'] ?? ''}'.isNotEmpty ? '${e!['title']}' : ch.title, sub: sub,
              onTap: () => openItem(c, ch, playlist: _chans),
            );
          },
        ),
      if ((s.byKind['movie'] ?? []).isNotEmpty)
        _posterRow(context, s, 'Films en ce moment', s.recent('movie', 40), posterH, () => widget.onTab(1)),
      if (movieCats.length > 1)
        Section(
          title: '', height: cat.height, count: movieCats.length,
          itemBuilder: (c, i) => CatTileCard(tile: movieCats[i], onTap: () => openCategory(c, movieCats[i])),
        ),
      if ((s.byKind['series'] ?? []).isNotEmpty)
        _posterRow(context, s, 'Séries en ce moment', s.recent('series', 40), posterH, () => widget.onTab(2)),
      if (_news.isNotEmpty)
        Section(
          title: 'Nouveautés sur IPTV',
          height: wideH,
          count: _news.length,
          itemBuilder: (c, i) {
            final it = _news[i];
            final m = _meta[it.url];
            return WideCard(
              image: '${m?['backdrop'] ?? ''}'.isNotEmpty ? '${m!['backdrop']}' : it.logo,
              title: '${m?['title'] ?? ''}'.isNotEmpty ? '${m!['title']}' : it.title,
              sub: [it.kind == 'series' ? 'Série' : 'Film', it.year, prettyGroup(it.group)].where((e) => e.isNotEmpty).join(' · '),
              badge: 'NOUVEAU',
              onTap: () => openItem(c, it),
            );
          },
        ),
      if (seriesCats.length > 1)
        Section(
          title: '', height: cat.height, count: seriesCats.length,
          itemBuilder: (c, i) => CatTileCard(tile: seriesCats[i], onTap: () => openCategory(c, seriesCats[i])),
        ),
      for (final t in topMovieGroups)
        _posterRow(context, s, 'Films · ${t.name}', (s.byKind['movie'] ?? []).where((i) => i.group == t.group).take(40).toList(),
            posterH, () => openCategory(context, t)),
      for (final t in topSeriesGroups)
        _posterRow(context, s, 'Séries · ${t.name}', (s.byKind['series'] ?? []).where((i) => i.group == t.group).take(40).toList(),
            posterH, () => openCategory(context, t)),
    ]);
  }

  Widget _posterRow(BuildContext context, AppState s, String title, List<Item> items, double h, VoidCallback more) {
    return Section(
      title: title,
      onMore: more,
      height: h,
      count: items.length,
      itemBuilder: (c, i) => PosterCard(item: items[i], fav: s.isFav(items[i].url), onTap: () => openItem(c, items[i])),
    );
  }
}

class _Welcome extends StatelessWidget {
  const _Welcome();
  @override
  Widget build(BuildContext context) {
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(32),
        child: Column(mainAxisSize: MainAxisSize.min, children: [
          const Logo(height: 70),
          const SizedBox(height: 26),
          const Text('Bienvenue 👋', style: TextStyle(fontSize: 28, fontWeight: FontWeight.w800)),
          const SizedBox(height: 8),
          const Text('Ajoutez une liste M3U ou un compte Xtream Codes pour commencer.',
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

/// Grande bannière défilante (films / séries).
class HeroCarousel extends StatefulWidget {
  final List<Item> items;
  final Map<String, Map<String, dynamic>> meta;
  const HeroCarousel({super.key, required this.items, required this.meta});
  @override
  State<HeroCarousel> createState() => _HeroCarouselState();
}

class _HeroCarouselState extends State<HeroCarousel> {
  int _i = 0;
  Timer? _t;
  @override
  void initState() {
    super.initState();
    _t = Timer.periodic(const Duration(seconds: 10), (_) {
      if (mounted) setState(() => _i = (_i + 1) % widget.items.length);
    });
  }

  @override
  void dispose() {
    _t?.cancel();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final wide = isWide(context);
    final h = wide ? 440.0 : 300.0;
    final it = widget.items[_i % widget.items.length];
    final m = widget.meta[it.url];
    final backdrop = '${m?['backdrop'] ?? ''}';
    final title = '${m?['title'] ?? ''}'.isNotEmpty ? '${m!['title']}' : it.title;
    final genres = ((m?['genres'] as List?) ?? []).take(3).join(' · ');
    final rating = '${m?['rating'] ?? ''}';
    final bits = [
      '${m?['year'] ?? it.year}', genres,
      rating.isNotEmpty && rating != '0' ? '★ $rating' : '',
      fmtRuntime(m?['runtime']),
    ].where((e) => e.isNotEmpty && e != 'null').join('   ·   ');
    final ov = '${m?['overview'] ?? ''}';
    final pad = wide ? 32.0 : 16.0;
    return SizedBox(
      height: h,
      child: Stack(fit: StackFit.expand, children: [
        AnimatedSwitcher(
          duration: const Duration(milliseconds: 600),
          child: SizedBox.expand(
            key: ValueKey(it.url + backdrop),
            child: backdrop.isNotEmpty
                ? NetImg(backdrop, radius: 0, alignment: Alignment.topCenter, cacheWidth: 1280)
                : ColorFiltered(
                    colorFilter: ColorFilter.mode(Colors.black.withValues(alpha: .35), BlendMode.darken),
                    child: NetImg(it.logo, radius: 0, alignment: Alignment.topCenter, cacheWidth: 600)),
          ),
        ),
        const DecoratedBox(
          decoration: BoxDecoration(
            gradient: LinearGradient(colors: [kBg, Color(0x990E1016), Color(0x000E1016)], stops: [0, .45, .85]),
          ),
        ),
        const DecoratedBox(
          decoration: BoxDecoration(
            gradient: LinearGradient(
                begin: Alignment.topCenter, end: Alignment.bottomCenter,
                colors: [Color(0x000E1016), kBg], stops: [.55, 1]),
          ),
        ),
        Positioned(
          left: pad, right: pad, bottom: 18,
          child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Text(it.kind == 'series' ? 'SÉRIE' : 'FILM',
                style: const TextStyle(color: kAccent, fontWeight: FontWeight.w900, letterSpacing: 2, fontSize: 12)),
            const SizedBox(height: 4),
            ConstrainedBox(
              constraints: const BoxConstraints(maxWidth: 700),
              child: Text(title, maxLines: 2, overflow: TextOverflow.ellipsis,
                  style: TextStyle(fontSize: wide ? 38 : 26, fontWeight: FontWeight.w900, color: Colors.white, height: 1.1)),
            ),
            if (bits.isNotEmpty) Padding(padding: const EdgeInsets.only(top: 6), child: Text(bits, style: const TextStyle(color: kMuted))),
            if (ov.isNotEmpty && wide)
              ConstrainedBox(
                constraints: const BoxConstraints(maxWidth: 620),
                child: Padding(
                  padding: const EdgeInsets.only(top: 8),
                  child: Text(ov, maxLines: 3, overflow: TextOverflow.ellipsis, style: const TextStyle(fontSize: 15, height: 1.4)),
                ),
              ),
            const SizedBox(height: 14),
            Row(children: [
              FilledButton.icon(
                onPressed: () => it.kind == 'movie' ? playItems(context, [PlayItem.of(it)], 0) : openItem(context, it),
                icon: const Icon(Icons.play_arrow),
                label: const Text('Lecture'),
              ),
              const SizedBox(width: 10),
              OutlinedButton.icon(
                onPressed: () => openItem(context, it),
                icon: const Icon(Icons.info_outline),
                label: const Text("Plus d'infos"),
              ),
              const Spacer(),
              for (var j = 0; j < widget.items.length; j++)
                GestureDetector(
                  onTap: () => setState(() => _i = j),
                  child: Container(
                    margin: const EdgeInsets.symmetric(horizontal: 3),
                    width: j == _i ? 18 : 7, height: 7,
                    decoration: BoxDecoration(
                        color: j == _i ? Colors.white : Colors.white38, borderRadius: BorderRadius.circular(4)),
                  ),
                ),
            ]),
          ]),
        ),
      ]),
    );
  }
}
