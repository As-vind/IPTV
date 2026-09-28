// Fiche acteur : photo, biographie, filmographie, titres disponibles dans la liste.
import 'package:flutter/material.dart';

import '../core/models.dart';
import '../core/text.dart';
import 'nav.dart';
import 'scope.dart';
import 'theme.dart';
import 'widgets.dart';

class PersonScreen extends StatefulWidget {
  final String name;
  final int? tmdbId;
  final String photo;
  final String role;
  const PersonScreen({super.key, required this.name, this.tmdbId, this.photo = '', this.role = ''});
  @override
  State<PersonScreen> createState() => _PersonScreenState();
}

class _PersonScreenState extends State<PersonScreen> {
  Map<String, dynamic>? _m;
  bool _loading = true;
  bool _full = false;

  @override
  void initState() {
    super.initState();
    final s = AppScope.read(context);
    if (s.tmdbKey.isEmpty) {
      _loading = false;
    } else {
      s.person(id: widget.tmdbId, name: widget.name).then((m) {
        if (!mounted) return;
        setState(() {
          _m = m;
          _loading = false;
        });
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    final s = AppScope.of(context);
    final wide = isWide(context);
    final pad = wide ? 32.0 : 16.0;
    final m = _m;
    final photo = '${m?['photo'] ?? ''}'.isNotEmpty ? '${m!['photo']}' : widget.photo;
    final bits = <String>[];
    final bd = '${m?['birthday'] ?? ''}';
    if (bd.isNotEmpty) {
      var b = '${m!['born_word']} le ${fmtDate(bd)}';
      if ('${m['place']}'.isNotEmpty) b += ' à ${m['place']}';
      final d = DateTime.tryParse(bd);
      if (d != null && '${m['deathday']}'.isEmpty) {
        final now = DateTime.now();
        var age = now.year - d.year;
        if (now.month < d.month || (now.month == d.month && now.day < d.day)) age--;
        b += '  ($age ans)';
      }
      bits.add(b);
    }
    if ('${m?['deathday'] ?? ''}'.isNotEmpty) bits.add('Décès le ${fmtDate('${m!['deathday']}')}');
    if (widget.role.isNotEmpty) bits.add('Rôle : ${widget.role}');
    final bio = '${m?['bio'] ?? ''}';

    // titres de la liste
    final local = <Item>[...s.titlesWithActor(widget.name)];
    final seen = local.map((e) => e.url).toSet();
    final films = <Map<String, dynamic>>[], series = <Map<String, dynamic>>[];
    for (final c in ((m?['credits'] as List?) ?? []).map((e) => Map<String, dynamic>.from(e as Map))) {
      if ('${c['title']}'.isEmpty) continue;
      final match = s.matchTitle('${c['kind']}', '${c['title']}', '${c['original_title']}', '${c['year']}');
      c['_lib'] = match;
      if (match != null && seen.add(match.url)) local.add(match);
      (c['kind'] == 'movie' ? films : series).add(c);
    }
    int avail(Map a) => a['_lib'] != null ? 0 : 1;
    films.sort((a, b) => avail(a).compareTo(avail(b)));
    series.sort((a, b) => avail(a).compareTo(avail(b)));
    final pw = PosterCard.width(context);

    Widget creditRow(String title, List<Map<String, dynamic>> lst) => Section(
          title: title,
          height: pw * 1.5 + 46,
          count: lst.length > 60 ? 60 : lst.length,
          itemBuilder: (c, i) {
            final cr = lst[i];
            final lib = cr['_lib'] as Item?;
            final it = Item(name: '${cr['title']}', url: 'tmdb:${cr['kind']}:${cr['title']}', logo: '${cr['poster']}', kind: '${cr['kind']}')
              ..title = '${cr['title']}'
              ..sub = ['${cr['year']}', '${cr['role']}'].where((e) => e.isNotEmpty).join(' · ');
            return Opacity(
              opacity: lib == null ? .55 : 1,
              child: Stack(children: [
                PosterCard(
                  item: it,
                  onTap: () => lib != null ? openItem(c, lib) : toast(c, '« ${cr['title']} » n\'est pas disponible dans votre liste.'),
                ),
                if (lib != null) const Positioned(left: 6, top: 6, child: Pill('✓ Disponible', color: Color(0xFF1F9D61), size: 9)),
              ]),
            );
          },
        );

    return Scaffold(
      appBar: AppBar(title: Text(widget.name)),
      body: ListView(padding: const EdgeInsets.only(bottom: 50), children: [
        Padding(
          padding: EdgeInsets.fromLTRB(pad, 20, pad, 10),
          child: Flex(
            direction: wide ? Axis.horizontal : Axis.vertical,
            crossAxisAlignment: wide ? CrossAxisAlignment.start : CrossAxisAlignment.center,
            children: [
              SizedBox(width: wide ? 200 : 150, height: wide ? 200 : 150, child: NetImg(photo, fallbackText: widget.name, circle: true, cacheWidth: 500)),
              SizedBox(width: wide ? 32 : 0, height: wide ? 0 : 16),
              Flexible(
                fit: wide ? FlexFit.tight : FlexFit.loose,
                child: Column(crossAxisAlignment: wide ? CrossAxisAlignment.start : CrossAxisAlignment.center, children: [
                  const Text('ACTEUR · ACTRICE', style: TextStyle(color: kAccent, fontWeight: FontWeight.w900, letterSpacing: 2, fontSize: 12)),
                  const SizedBox(height: 4),
                  Text('${m?['name'] ?? widget.name}', style: TextStyle(fontSize: wide ? 34 : 26, fontWeight: FontWeight.w900)),
                  if (bits.isNotEmpty) Padding(padding: const EdgeInsets.only(top: 6), child: Text(bits.join('   ·   '), style: const TextStyle(color: kMuted))),
                  const SizedBox(height: 10),
                  if (_loading) const Text('Chargement…', style: TextStyle(color: kMuted)),
                  if (!_loading && s.tmdbKey.isEmpty)
                    const Text('Ajoutez une clé TMDB (gratuite) dans Paramètres pour la photo, la biographie et la filmographie.',
                        style: TextStyle(color: kMuted)),
                  if (bio.isNotEmpty) ...[
                    Text(_full || bio.length < 600 ? bio : '${bio.substring(0, 597)}…', style: const TextStyle(fontSize: 15, height: 1.45)),
                    if (bio.length >= 600)
                      TextButton(onPressed: () => setState(() => _full = !_full), child: Text(_full ? 'Réduire' : 'Lire la suite')),
                  ],
                ]),
              ),
            ],
          ),
        ),
        if (local.isNotEmpty)
          Section(
            title: 'Dans votre liste', height: pw * 1.5 + 46, count: local.length,
            itemBuilder: (c, i) => PosterCard(item: local[i], onTap: () => openItem(c, local[i])),
          ),
        if (films.isNotEmpty) creditRow('Filmographie · Films', films),
        if (series.isNotEmpty) creditRow('Filmographie · Séries', series),
      ]),
    );
  }
}
