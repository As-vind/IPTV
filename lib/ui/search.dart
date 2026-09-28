// Recherche globale : chaînes, films, séries et acteurs (TMDB).
import 'dart:async';

import 'package:flutter/material.dart';

import '../core/meta.dart';
import '../core/models.dart';
import 'nav.dart';
import 'scope.dart';
import 'theme.dart';
import 'widgets.dart';

class SearchScreen extends StatefulWidget {
  const SearchScreen({super.key});
  @override
  State<SearchScreen> createState() => _SearchScreenState();
}

class _SearchScreenState extends State<SearchScreen> {
  String _q = '';
  Timer? _deb;
  List<Map<String, dynamic>> _people = [];
  int _token = 0;

  void _changed(String v) {
    _deb?.cancel();
    _deb = Timer(const Duration(milliseconds: 350), () async {
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

  @override
  Widget build(BuildContext context) {
    final s = AppScope.of(context);
    final live = _q.length >= 2 ? s.search(_q, 'live') : <Item>[];
    final movies = _q.length >= 2 ? s.search(_q, 'movie') : <Item>[];
    final series = _q.length >= 2 ? s.search(_q, 'series') : <Item>[];
    final pw = PosterCard.width(context), cw = ChannelCard.width(context), aw = ActorCard.width(context);
    final pad = isWide(context) ? 32.0 : 16.0;
    return Scaffold(
      appBar: AppBar(
        titleSpacing: 0,
        title: Padding(
          padding: EdgeInsets.only(right: pad),
          child: TextField(
            autofocus: true,
            style: const TextStyle(fontSize: 17),
            decoration: const InputDecoration(hintText: 'Chaîne, film, série, acteur…', prefixIcon: Icon(Icons.search)),
            onChanged: _changed,
          ),
        ),
      ),
      body: _q.length < 2
          ? const Center(child: Text('Tapez au moins 2 caractères.', style: TextStyle(color: kMuted)))
          : ListView(padding: const EdgeInsets.only(bottom: 40), children: [
              if (live.isNotEmpty)
                Section(
                  title: 'Chaînes TV  (${live.length})', height: cw * .6 + 48, count: live.length,
                  itemBuilder: (c, i) => ChannelCard(item: live[i], onTap: () => openItem(c, live[i], playlist: live)),
                ),
              if (movies.isNotEmpty)
                Section(
                  title: 'Films  (${movies.length})', height: pw * 1.5 + 46, count: movies.length,
                  itemBuilder: (c, i) => PosterCard(item: movies[i], onTap: () => openItem(c, movies[i])),
                ),
              if (series.isNotEmpty)
                Section(
                  title: 'Séries  (${series.length})', height: pw * 1.5 + 46, count: series.length,
                  itemBuilder: (c, i) => PosterCard(item: series[i], onTap: () => openItem(c, series[i])),
                ),
              if (_people.isNotEmpty)
                Section(
                  title: 'Acteurs', height: aw * .9 + 56, count: _people.length,
                  itemBuilder: (c, i) {
                    final p = _people[i];
                    final known = ((p['known_for'] as List?) ?? [])
                        .whereType<Map>().take(2).map((k) => '${k['title'] ?? k['name'] ?? ''}').join(', ');
                    return ActorCard(
                      name: '${p['name']}', role: known, photo: tmdbImg(p['profile_path'], 'w185'),
                      onTap: () => openPerson(c, name: '${p['name']}', id: (p['id'] as num?)?.toInt(),
                          photo: tmdbImg(p['profile_path'], 'w185')),
                    );
                  },
                ),
              if (live.isEmpty && movies.isEmpty && series.isEmpty && _people.isEmpty)
                const Padding(
                  padding: EdgeInsets.all(40),
                  child: Center(child: Text('Aucun résultat dans votre liste.', style: TextStyle(color: kMuted))),
                ),
            ]),
    );
  }
}
