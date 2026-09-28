// Recherche : champ en haut, « Les plus recherchés » (TMDB) puis résultats (chaînes, films, séries, acteurs).
import 'dart:async';

import 'package:flutter/material.dart';

import '../core/meta.dart';
import '../core/models.dart';
import 'nav.dart';
import 'octo.dart';
import 'pages.dart';
import 'scope.dart';
import 'theme.dart';

class SearchView extends StatefulWidget {
  final bool collapsed;
  const SearchView({super.key, this.collapsed = false});
  @override
  State<SearchView> createState() => _SearchViewState();
}

class _SearchViewState extends State<SearchView> {
  String _q = '';
  Timer? _deb;
  List<Map<String, dynamic>> _people = [];
  int _token = 0;

  void _changed(String v) {
    _deb?.cancel();
    _deb = Timer(const Duration(milliseconds: 350), () async {
      if (!mounted) return;
      setState(() => _q = v.trim());
      final s = AppScope.read(context);
      final t = ++_token;
      if (s.tmdbKey.isNotEmpty && _q.length >= 3) {
        try {
          final res = await Tmdb(s.tmdbKey, s.lang).searchPerson(_q);
          if (!mounted || t != _token) return;
          setState(() => _people = res
              .where((p) => p['known_for_department'] == 'Acting' && p['profile_path'] != null)
              .take(30)
              .toList());
        } catch (_) {}
      } else {
        setState(() => _people = []);
      }
    });
  }

  @override
  void dispose() {
    _deb?.cancel();
    super.dispose();
  }

  List<CardData> _items(BuildContext c, List<Item> l) =>
      [for (final it in l) CardData(title: it.title, image: it.logo, lib: it, fetchMeta: false, onTap: () => openItem(c, it))];

  @override
  Widget build(BuildContext context) {
    final s = AppScope.of(context);
    final u = UiK.of(context);
    final field = SizedBox(
      width: u.phone ? double.infinity : 440,
      child: TextField(
        style: const TextStyle(fontSize: 17),
        textInputAction: TextInputAction.search,
        decoration: InputDecoration(
          hintText: 'Films, Séries, TV, Acteurs…',
          prefixIcon: const Icon(Icons.search),
          filled: true,
          fillColor: Colors.white.withValues(alpha: .1),
          border: OutlineInputBorder(borderRadius: BorderRadius.circular(26), borderSide: BorderSide.none),
          enabledBorder: OutlineInputBorder(borderRadius: BorderRadius.circular(26),
              borderSide: BorderSide(color: Colors.white.withValues(alpha: .14))),
          focusedBorder: OutlineInputBorder(borderRadius: BorderRadius.circular(26), borderSide: const BorderSide(color: kAccent)),
        ),
        onChanged: _changed,
      ),
    );
    final header = u.phone
        ? Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
            const PageTitle('Recherche', top: 16),
            Padding(padding: const EdgeInsets.symmetric(horizontal: 14), child: field),
          ])
        : PageTitle('Recherche', top: widget.collapsed ? 96 : 38, right: field);

    final children = <Widget>[SafeArea(bottom: false, child: header)];
    if (_q.length < 2) {
      children.addAll([
        AsyncRow(
          title: 'Films', style: CardStyle.posterBig, listName: 'trend3-movie',
          compute: (k, l) => tmdbTrending(k, l, 'movie'),
          toCards: (c, res) => matchCards(c, s, res, CardStyle.posterBig, onlyAvailable: false),
        ),
        AsyncRow(
          title: 'Séries', style: CardStyle.posterBig, listName: 'trend3-tv',
          compute: (k, l) => tmdbTrending(k, l, 'tv'),
          toCards: (c, res) => matchCards(c, s, res, CardStyle.posterBig, onlyAvailable: false),
        ),
        actorsRow(s),
      ]);
    } else {
      final live = s.search(_q, 'live');
      final movies = s.search(_q, 'movie');
      final series = s.search(_q, 'series');
      children.addAll([
        OctoRow(title: 'Chaînes TV  (${live.length})', style: CardStyle.wide, items: [
          for (final ch in live)
            CardData(title: ch.title, overlay: ch.title, image: ch.logo, logoMode: true,
                onTap: () => openItem(context, ch, playlist: live)),
        ]),
        OctoRow(title: 'Films  (${movies.length})', style: CardStyle.posterSm, items: _items(context, movies)),
        OctoRow(title: 'Séries  (${series.length})', style: CardStyle.posterSm, items: _items(context, series)),
        OctoRow(title: 'Acteurs', style: CardStyle.actor, items: [
          for (final p in _people)
            CardData(
              title: '${p['name']}', image: tmdbImg(p['profile_path'], 'w185'),
              onTap: () => openPerson(context, name: '${p['name']}', id: (p['id'] as num?)?.toInt(),
                  photo: tmdbImg(p['profile_path'], 'w185')),
            ),
        ]),
        if (live.isEmpty && movies.isEmpty && series.isEmpty && _people.isEmpty)
          const Padding(
            padding: EdgeInsets.all(40),
            child: Center(child: Text('Aucun résultat dans votre liste.', style: TextStyle(color: kMuted))),
          ),
      ]);
    }
    return ListView(padding: const EdgeInsets.only(bottom: 90), children: children);
  }
}
