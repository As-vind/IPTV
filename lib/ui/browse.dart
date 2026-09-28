// Parcourir : chaînes / films / séries par pays et catégories + Ma liste.
import 'package:flutter/material.dart';

import '../core/countries.dart';
import '../core/models.dart';
import '../core/store.dart';
import '../core/text.dart';
import 'nav.dart';
import 'scope.dart';
import 'theme.dart';
import 'widgets.dart';

class BrowseView extends StatefulWidget {
  final String kind;
  final String? initialGroup;
  final bool compact;
  const BrowseView({super.key, required this.kind, this.initialGroup, this.compact = false});
  @override
  State<BrowseView> createState() => _BrowseViewState();
}

class _BrowseViewState extends State<BrowseView> {
  String _country = '*';
  String _group = '*';
  String _q = '';
  int _sort = 0; // 0 fournisseur, 1 A→Z, 2 récents, 3 notes

  @override
  void initState() {
    super.initState();
    if (widget.initialGroup != null) _group = widget.initialGroup!;
  }

  List<Item> _filtered(AppState s) {
    var res = s.byKind[widget.kind] ?? [];
    if (_country != '*') res = res.where((i) => i.country == _country).toList();
    if (_group != '*') res = res.where((i) => i.group == _group).toList();
    if (_q.isNotEmpty) {
      final terms = norm(_q).split(RegExp(r'\s+')).where((e) => e.isNotEmpty).toList();
      res = res.where((i) => terms.every(i.q.contains)).toList();
    }
    if (_sort == 1) {
      res = List.of(res)..sort((a, b) => norm(a.title).compareTo(norm(b.title)));
    } else if (_sort == 2) {
      res = List.of(res)..sort((a, b) => b.addedInt.compareTo(a.addedInt));
    } else if (_sort == 3) {
      res = List.of(res)..sort((a, b) => (double.tryParse(b.ratingStr) ?? 0).compareTo(double.tryParse(a.ratingStr) ?? 0));
    }
    return res;
  }

  Widget _chips<T>(List<(T, String)> values, T selected, void Function(T) onSel) {
    final pad = isWide(context) ? 32.0 : 16.0;
    return SizedBox(
      height: 44,
      child: ListView.separated(
        scrollDirection: Axis.horizontal,
        padding: EdgeInsets.symmetric(horizontal: pad),
        itemCount: values.length,
        separatorBuilder: (_, __) => const SizedBox(width: 8),
        itemBuilder: (c, i) {
          final (v, label) = values[i];
          final sel = v == selected;
          return ChoiceChip(
            label: Text(label),
            selected: sel,
            showCheckmark: false,
            labelStyle: TextStyle(color: sel ? kBg : kText, fontWeight: FontWeight.w700),
            onSelected: (_) => onSel(v),
          );
        },
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final s = AppScope.of(context);
    final pool = s.byKind[widget.kind] ?? [];
    final countryCounts = <String, int>{};
    for (final i in pool) {
      countryCounts[i.country] = (countryCounts[i.country] ?? 0) + 1;
    }
    final countries = countryCounts.keys.toList()
      ..sort((a, b) => a == 'ZZ' ? 1 : (b == 'ZZ' ? -1 : norm(countryName(a)).compareTo(norm(countryName(b)))));
    final sub = _country == '*' ? pool : pool.where((i) => i.country == _country).toList();
    final groups = <String>[];
    final seen = <String>{};
    for (final i in sub) {
      if (seen.add(i.group)) groups.add(i.group);
    }
    if (_group != '*' && !seen.contains(_group)) _group = '*';
    final res = _filtered(s);
    final wide = isWide(context);
    final pad = wide ? 32.0 : 16.0;
    final live = widget.kind == 'live';
    final cardW = live ? ChannelCard.width(context) : PosterCard.width(context);
    final cardH = live ? cardW * .6 + 48 : cardW * 1.5 + 50;

    return Column(children: [
      Padding(
        padding: EdgeInsets.fromLTRB(pad, 14, pad, 8),
        child: Row(children: [
          if (!widget.compact)
            Text({'live': 'Chaînes TV', 'movie': 'Films', 'series': 'Séries'}[widget.kind]!,
                style: TextStyle(fontSize: 24 * uiScale(context), fontWeight: FontWeight.w800)),
          const SizedBox(width: 10),
          Text('${res.length} ${live ? 'chaînes' : 'titres'}', style: const TextStyle(color: kMuted)),
          const Spacer(),
          SizedBox(
            width: wide ? 260 : 150,
            child: TextField(
              decoration: const InputDecoration(hintText: 'Filtrer…', prefixIcon: Icon(Icons.search), isDense: true),
              onChanged: (v) => setState(() => _q = v.trim()),
            ),
          ),
          if (!live)
            PopupMenuButton<int>(
              tooltip: 'Trier',
              icon: const Icon(Icons.sort),
              initialValue: _sort,
              onSelected: (v) => setState(() => _sort = v),
              itemBuilder: (_) => const [
                PopupMenuItem(value: 0, child: Text('Ordre du fournisseur')),
                PopupMenuItem(value: 1, child: Text('A → Z')),
                PopupMenuItem(value: 2, child: Text('Récemment ajoutés')),
                PopupMenuItem(value: 3, child: Text('Mieux notés')),
              ],
            ),
        ]),
      ),
      if (countries.length > 1)
        _chips<String>([
          ('*', '🌍 Tous les pays'),
          for (final c in countries) (c, '${countryName(c)}  ${countryCounts[c]}'),
        ], _country, (v) => setState(() {
              _country = v;
              _group = '*';
            })),
      const SizedBox(height: 6),
      _chips<String>([
        ('*', 'Toutes les catégories'),
        for (final g in groups) (g, prettyGroup(g)),
      ], _group, (v) => setState(() => _group = v)),
      const SizedBox(height: 8),
      Expanded(
        child: res.isEmpty
            ? Center(child: Text(pool.isEmpty ? 'Rien ici pour le moment.' : 'Aucun résultat.', style: const TextStyle(color: kMuted)))
            : GridView.builder(
                padding: EdgeInsets.fromLTRB(pad, 8, pad, 70),
                gridDelegate: SliverGridDelegateWithMaxCrossAxisExtent(
                  maxCrossAxisExtent: cardW + 14,
                  mainAxisExtent: cardH,
                  crossAxisSpacing: 10,
                  mainAxisSpacing: 14,
                ),
                itemCount: res.length,
                itemBuilder: (c, i) {
                  final it = res[i];
                  return Center(
                    child: live
                        ? ChannelCard(item: it, fav: s.isFav(it.url), onTap: () => openItem(c, it, playlist: res))
                        : PosterCard(item: it, fav: s.isFav(it.url), onTap: () => openItem(c, it)),
                  );
                },
              ),
      ),
    ]);
  }
}

class FavoritesView extends StatelessWidget {
  const FavoritesView({super.key});
  @override
  Widget build(BuildContext context) {
    final s = AppScope.of(context);
    final favs = s.items.where((i) => s.favorites.contains(i.url)).toList();
    if (favs.isEmpty) {
      return const Center(
        child: Padding(
          padding: EdgeInsets.all(30),
          child: Text('Votre liste est vide.\nAjoutez des chaînes, films ou séries avec « Ma liste ».',
              textAlign: TextAlign.center, style: TextStyle(color: kMuted, fontSize: 15)),
        ),
      );
    }
    final live = favs.where((i) => i.kind == 'live').toList();
    final movies = favs.where((i) => i.kind == 'movie').toList();
    final series = favs.where((i) => i.kind == 'series').toList();
    final pw = PosterCard.width(context), cw = ChannelCard.width(context);
    return ListView(padding: const EdgeInsets.only(bottom: 70), children: [
      if (live.isNotEmpty)
        Section(
          title: 'Chaînes TV', height: cw * .6 + 48, count: live.length,
          itemBuilder: (c, i) => ChannelCard(item: live[i], onTap: () => openItem(c, live[i], playlist: live)),
        ),
      if (movies.isNotEmpty)
        Section(
          title: 'Films', height: pw * 1.5 + 46, count: movies.length,
          itemBuilder: (c, i) => PosterCard(item: movies[i], onTap: () => openItem(c, movies[i])),
        ),
      if (series.isNotEmpty)
        Section(
          title: 'Séries', height: pw * 1.5 + 46, count: series.length,
          itemBuilder: (c, i) => PosterCard(item: series[i], onTap: () => openItem(c, series[i])),
        ),
    ]);
  }
}
