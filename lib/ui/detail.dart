// Fiche film / série : fond, affiche, infos, bande-annonce, saisons, épisodes, distribution.
import 'package:flutter/material.dart';
import 'package:url_launcher/url_launcher.dart';

import '../core/models.dart';
import '../core/store.dart';
import '../core/text.dart';
import 'nav.dart';
import 'scope.dart';
import 'theme.dart';
import 'widgets.dart';

class DetailScreen extends StatefulWidget {
  final Item item;
  const DetailScreen({super.key, required this.item});
  @override
  State<DetailScreen> createState() => _DetailScreenState();
}

class _DetailScreenState extends State<DetailScreen> {
  Map<String, dynamic>? _m;
  bool _loading = true;
  int _season = 0;
  bool get _series => widget.item.kind == 'series';

  @override
  void initState() {
    super.initState();
    AppScope.read(context).meta(widget.item).then((m) {
      if (!mounted) return;
      setState(() {
        _m = m;
        _loading = false;
        _season = _resumeSeasonIndex();
      });
    });
  }

  List<Map<String, dynamic>> get _seasons =>
      ((_m?['seasons'] as List?) ?? []).map((e) => Map<String, dynamic>.from(e as Map)).toList();

  String get _title => '${_m?['title'] ?? ''}'.isNotEmpty ? '${_m!['title']}' : widget.item.title;

  List<PlayItem> _episodeItems(int si) {
    final season = _seasons[si];
    return [
      for (final e in (season['episodes'] as List).map((x) => Map<String, dynamic>.from(x as Map)))
        PlayItem(
          name: '$_title — S${'${season['number']}'.padLeft(2, '0')}E${'${e['num']}'.padLeft(2, '0')}  ${e['name']}',
          url: '${e['url']}', kind: 'episode', logo: widget.item.logo,
          opts: ((e['opts'] as List?) ?? []).map((x) => '$x').toList(),
          series: {
            'url': widget.item.url, 'name': _title, 'logo': widget.item.logo,
            'season': season['number'], 'num': e['num'], 'ep_name': '${e['name']}',
          },
        ),
    ];
  }

  MapEntry<String, Map<String, dynamic>>? _seriesLast(AppState s) {
    MapEntry<String, Map<String, dynamic>>? best;
    s.progress.forEach((url, v) {
      final e = Map<String, dynamic>.from(v as Map);
      final ser = e['series'];
      if (ser is Map && ser['url'] == widget.item.url) {
        if (best == null || (e['t'] as num) > (best!.value['t'] as num)) best = MapEntry(url, e);
      }
    });
    return best;
  }

  int _resumeSeasonIndex() {
    final last = _seriesLast(AppScope.read(context));
    if (last == null) return 0;
    final sn = (last.value['series'] as Map)['season'];
    final i = _seasons.indexWhere((s) => s['number'] == sn);
    return i < 0 ? 0 : i;
  }

  /// (saison, épisode, reprendre ?)
  (int, int, bool)? _resumeTarget(AppState s) {
    final seasons = _seasons;
    if (seasons.isEmpty) return null;
    final last = _seriesLast(s);
    if (last != null) {
      for (var si = 0; si < seasons.length; si++) {
        final eps = seasons[si]['episodes'] as List;
        for (var ei = 0; ei < eps.length; ei++) {
          if ((eps[ei] as Map)['url'] == last.key) {
            if (last.value['done'] == true) {
              if (ei + 1 < eps.length) return (si, ei + 1, false);
              if (si + 1 < seasons.length && (seasons[si + 1]['episodes'] as List).isNotEmpty) return (si + 1, 0, false);
              return (si, ei, false);
            }
            return (si, ei, ((last.value['pos'] as num?) ?? 0) > 30000);
          }
        }
      }
    }
    return (0, 0, false);
  }

  void _play(AppState s, {bool restart = false}) async {
    if (_series) {
      final t = _resumeTarget(s);
      if (t == null) return;
      playItems(context, _episodeItems(t.$1), t.$2, resume: !restart);
    } else {
      playItems(context, [PlayItem.of(widget.item)], 0, resume: !restart);
    }
  }

  @override
  Widget build(BuildContext context) {
    final s = AppScope.of(context);
    final wide = isWide(context);
    final pad = wide ? 32.0 : 16.0;
    final m = _m;
    final backdrop = '${m?['backdrop'] ?? ''}';
    final poster = '${m?['poster'] ?? ''}'.isNotEmpty ? '${m!['poster']}' : widget.item.logo;
    final genres = ((m?['genres'] as List?) ?? []).map((e) => '$e').take(5).toList();
    final age = '${m?['age'] ?? ''}';
    final rating = '${m?['rating'] ?? ''}';
    final nSeasons = _seasons.length;
    final metaLine = [
      '${m?['year'] ?? widget.item.year}',
      _series ? (nSeasons > 0 ? '$nSeasons saison${nSeasons > 1 ? 's' : ''}' : '') : fmtRuntime(m?['runtime']),
      rating.isNotEmpty && rating != '0' && rating != '0.0' ? '★ $rating' : '',
      prettyGroup(widget.item.group),
    ].where((e) => e.isNotEmpty && e != 'null').join('   ·   ');
    final cast = ((m?['cast'] as List?) ?? []).map((e) => Map<String, dynamic>.from(e as Map)).where((c) => '${c['name']}'.isNotEmpty).toList();
    final similar = (s.byKind[widget.item.kind] ?? [])
        .where((i) => i.group == widget.item.group && i.url != widget.item.url)
        .take(30)
        .toList();
    final fav = s.isFav(widget.item.url);

    // bouton principal
    String playLabel = 'Lecture';
    bool showRestart = false;
    if (_series) {
      final t = _resumeTarget(s);
      if (t != null && nSeasons > 0) {
        final season = _seasons[t.$1];
        final ep = (season['episodes'] as List)[t.$2] as Map;
        playLabel = '${t.$3 ? 'Reprendre' : 'Lecture'}  S${season['number']} E${ep['num']}';
      }
    } else {
      final pr = s.progressOf(widget.item.url);
      if (pr != null && pr['done'] != true && ((pr['pos'] as num?) ?? 0) > 30000) {
        playLabel = 'Reprendre · ${fmtMs((pr['pos'] as num).toInt())}';
        showRestart = true;
      }
    }

    final info = Column(crossAxisAlignment: CrossAxisAlignment.start, mainAxisSize: MainAxisSize.min, children: [
      Text(_series ? 'SÉRIE' : 'FILM', style: const TextStyle(color: kAccent, fontWeight: FontWeight.w900, letterSpacing: 2, fontSize: 12)),
      const SizedBox(height: 4),
      Text(_title, style: TextStyle(fontSize: wide ? 36 : 26, fontWeight: FontWeight.w900, color: Colors.white, height: 1.1)),
      if ('${m?['tagline'] ?? ''}'.isNotEmpty)
        Padding(padding: const EdgeInsets.only(top: 6),
            child: Text('« ${m!['tagline']} »', style: const TextStyle(fontStyle: FontStyle.italic, color: Color(0xFFC9CBD6)))),
      const SizedBox(height: 8),
      Text(metaLine, style: const TextStyle(color: kMuted)),
      const SizedBox(height: 8),
      Wrap(spacing: 6, runSpacing: 6, children: [
        if (age.isNotEmpty)
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 7, vertical: 2),
            decoration: BoxDecoration(border: Border.all(color: const Color(0xFFC9CCD6), width: 1.5), borderRadius: BorderRadius.circular(5)),
            child: Text(int.tryParse(age) != null ? '$age+' : age, style: const TextStyle(fontWeight: FontWeight.w800, fontSize: 12)),
          ),
        for (final g in genres)
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 3),
            decoration: BoxDecoration(color: Colors.white.withValues(alpha: .08), borderRadius: BorderRadius.circular(9),
                border: Border.all(color: Colors.white.withValues(alpha: .12))),
            child: Text(g, style: const TextStyle(fontSize: 12)),
          ),
      ]),
      const SizedBox(height: 12),
      ConstrainedBox(
        constraints: const BoxConstraints(maxWidth: 820),
        child: Text(_loading ? 'Chargement des informations…' : ('${m?['overview'] ?? ''}'.isEmpty ? 'Pas de résumé disponible.' : '${m!['overview']}'),
            style: const TextStyle(fontSize: 15, height: 1.45)),
      ),
      if ('${m?['director'] ?? ''}'.isNotEmpty)
        Padding(
          padding: const EdgeInsets.only(top: 8),
          child: Text.rich(TextSpan(children: [
            TextSpan(text: _series ? 'Création : ' : 'Réalisation : ', style: const TextStyle(color: kMuted)),
            TextSpan(text: '${m!['director']}'),
          ])),
        ),
      const SizedBox(height: 16),
      Wrap(spacing: 10, runSpacing: 10, children: [
        FilledButton.icon(
          autofocus: true,
          onPressed: (_series && nSeasons == 0) ? null : () => _play(s),
          icon: const Icon(Icons.play_arrow),
          label: Text(playLabel),
        ),
        if (showRestart)
          OutlinedButton.icon(onPressed: () => _play(s, restart: true), icon: const Icon(Icons.replay), label: const Text('Depuis le début')),
        if ('${m?['trailer'] ?? ''}'.isNotEmpty)
          OutlinedButton.icon(
            onPressed: () => launchUrl(Uri.parse('${m!['trailer']}'), mode: LaunchMode.externalApplication),
            icon: const Icon(Icons.movie_creation_outlined),
            label: const Text('Bande-annonce'),
          ),
        OutlinedButton.icon(
          onPressed: () => s.toggleFavorite(widget.item.url),
          icon: Icon(fav ? Icons.favorite : Icons.favorite_border, color: fav ? kAccent : null),
          label: Text(fav ? 'Dans Ma liste' : 'Ma liste'),
        ),
        AnimatedBuilder(
          animation: s.downloads,
          builder: (c, _) => OutlinedButton.icon(
            onPressed: (_series && nSeasons == 0) ? null : () => _download(s),
            icon: Icon(_series ? Icons.download_outlined : _dlIcon(s, widget.item.url)),
            label: Text(_series ? 'Télécharger la saison' : _dlLabel(s, widget.item.url)),
          ),
        ),
      ]),
    ]);

    final header = Stack(children: [
      Positioned.fill(
        child: backdrop.isNotEmpty
            ? NetImg(backdrop, radius: 0, alignment: Alignment.topCenter, cacheWidth: 1280)
            : ColorFiltered(
                colorFilter: ColorFilter.mode(Colors.black.withValues(alpha: .55), BlendMode.darken),
                child: NetImg(poster, radius: 0, cacheWidth: 500)),
      ),
      const Positioned.fill(
        child: DecoratedBox(
          decoration: BoxDecoration(
            gradient: LinearGradient(colors: [kBg, Color(0xCC0E1016), Color(0x220E1016)], stops: [0, .5, 1]),
          ),
        ),
      ),
      const Positioned.fill(
        child: DecoratedBox(
          decoration: BoxDecoration(
            gradient: LinearGradient(begin: Alignment.topCenter, end: Alignment.bottomCenter,
                colors: [Color(0x880E1016), Color(0x000E1016), kBg], stops: [0, .35, 1]),
          ),
        ),
      ),
      Padding(
        padding: EdgeInsets.fromLTRB(pad, wide ? 90 : 80, pad, 12),
        child: wide
            ? Row(crossAxisAlignment: CrossAxisAlignment.end, children: [
                SizedBox(width: 220, height: 330, child: NetImg(poster, fallbackText: _title, radius: 14, cacheWidth: 500)),
                const SizedBox(width: 30),
                Expanded(child: info),
              ])
            : info,
      ),
    ]);

    final seasons = _seasons;
    return Scaffold(
      extendBodyBehindAppBar: true,
      appBar: AppBar(backgroundColor: Colors.transparent),
      body: ListView(padding: const EdgeInsets.only(bottom: 50), children: [
        header,
        if (_series && seasons.isNotEmpty) ...[
          Padding(
            padding: EdgeInsets.fromLTRB(pad, 22, pad, 10),
            child: const Text('Épisodes', style: TextStyle(fontSize: 20, fontWeight: FontWeight.w800)),
          ),
          SizedBox(
            height: 44,
            child: ListView.separated(
              scrollDirection: Axis.horizontal,
              padding: EdgeInsets.symmetric(horizontal: pad),
              itemCount: seasons.length,
              separatorBuilder: (_, __) => const SizedBox(width: 8),
              itemBuilder: (c, i) {
                final sn = seasons[i];
                var name = '${sn['name']}'.isEmpty ? 'Saison ${sn['number']}' : '${sn['name']}';
                if (!RegExp(r'\d').hasMatch(name)) name = '$name ${sn['number']}';
                return ChoiceChip(
                  label: Text('$name · ${(sn['episodes'] as List).length}'),
                  selected: _season == i,
                  showCheckmark: false,
                  labelStyle: TextStyle(color: _season == i ? kBg : kText, fontWeight: FontWeight.w700),
                  onSelected: (_) => setState(() => _season = i),
                );
              },
            ),
          ),
          const SizedBox(height: 8),
          ..._episodeRows(s, pad),
        ],
        if (_series && seasons.isEmpty && !_loading)
          Padding(padding: EdgeInsets.all(pad), child: const Text('Aucun épisode disponible.', style: TextStyle(color: kMuted))),
        if (cast.isNotEmpty)
          Section(
            title: 'Distribution',
            height: ActorCard.width(context) * .9 + 60,
            count: cast.length,
            itemBuilder: (c, i) => ActorCard(
              name: '${cast[i]['name']}', role: '${cast[i]['role'] ?? ''}', photo: '${cast[i]['photo'] ?? ''}',
              onTap: () => openPerson(c, name: '${cast[i]['name']}', id: (cast[i]['tmdb_id'] as num?)?.toInt(),
                  photo: '${cast[i]['photo'] ?? ''}', role: '${cast[i]['role'] ?? ''}'),
            ),
          ),
        if (similar.isNotEmpty)
          Section(
            title: 'Vous aimerez aussi',
            height: PosterCard.width(context) * 1.5 + 46,
            count: similar.length,
            itemBuilder: (c, i) => PosterCard(item: similar[i], onTap: () => openItem(c, similar[i])),
          ),
      ]),
    );
  }

  // -- téléchargements
  String _dlLabel(AppState s, String url) {
    final j = s.downloads.jobFor(url);
    return switch (j?['state']) {
      'done' => 'Téléchargé',
      'downloading' => 'Téléchargement ${s.downloads.percent(j!)} %',
      'queued' => 'En attente',
      'paused' => 'En pause ${s.downloads.percent(j!)} %',
      'error' => 'Réessayer',
      _ => 'Télécharger',
    };
  }

  IconData _dlIcon(AppState s, String url) => switch (s.downloads.jobFor(url)?['state']) {
        'done' => Icons.download_done,
        'downloading' || 'queued' => Icons.downloading,
        'paused' => Icons.pause_circle_outline,
        'error' => Icons.refresh,
        _ => Icons.download_outlined,
      };

  Future<void> _download(AppState s) async {
    final dm = s.downloads;
    if (_series) {
      var n = 0;
      for (final it in _episodeItems(_season)) {
        if (dm.jobFor(it.url) == null) {
          await dm.add(it, quiet: true);
          n++;
        }
      }
      if (mounted) toast(context, n > 0 ? '$n épisode(s) ajouté(s) aux téléchargements.' : 'Saison déjà téléchargée ou en cours.');
      return;
    }
    final j = dm.jobFor(widget.item.url);
    if (j == null || j['state'] == 'error' || j['state'] == 'paused') {
      await dm.add(PlayItem.of(widget.item), title: _title);
      if (mounted) toast(context, 'Ajouté aux téléchargements : $_title');
    } else if (j['state'] == 'done') {
      if (mounted) toast(context, 'Déjà téléchargé : il se lit hors ligne.');
    } else {
      if (mounted) toast(context, 'Téléchargement en cours (${dm.percent(j)} %).');
    }
  }

  Future<void> _downloadEpisode(AppState s, int j) async {
    final it = _episodeItems(_season)[j];
    final job = s.downloads.jobFor(it.url);
    if (job == null || job['state'] == 'error' || job['state'] == 'paused') {
      await s.downloads.add(it);
      if (mounted) toast(context, 'Épisode ajouté aux téléchargements.');
    } else if (job['state'] == 'done') {
      if (mounted) toast(context, 'Épisode déjà téléchargé : il se lit hors ligne.');
    }
  }

  List<Widget> _episodeRows(AppState s, double pad) {
    final seasons = _seasons;
    if (_season >= seasons.length) return [];
    final eps = (seasons[_season]['episodes'] as List).map((e) => Map<String, dynamic>.from(e as Map)).toList();
    final wide = isWide(context);
    final tw = wide ? 240.0 : 150.0;
    final fallback = '${_m?['backdrop'] ?? ''}'.isNotEmpty ? '${_m!['backdrop']}' : widget.item.logo;
    return [
      for (var j = 0; j < eps.length; j++)
        Padding(
          padding: EdgeInsets.symmetric(horizontal: pad - 8, vertical: 2),
          child: FocusTile(
            onTap: () => playItems(context, _episodeItems(_season), j),
            builder: (on) {
              final e = eps[j];
              final pr = s.progressOf('${e['url']}');
              var frac = pr == null || ((pr['len'] as num?) ?? 0) == 0 ? 0.0 : (pr['pos'] as num) / (pr['len'] as num);
              if (pr?['done'] == true) frac = 1;
              final still = '${e['still'] ?? ''}';
              final bits = [
                fmtRuntime(e['runtime']), fmtDate('${e['air_date'] ?? ''}'),
                '${e['rating'] ?? ''}'.isNotEmpty && '${e['rating']}' != '0' ? '★ ${e['rating']}' : '',
              ].where((x) => x.isNotEmpty).join(' · ');
              return Container(
                padding: const EdgeInsets.all(8),
                decoration: BoxDecoration(
                  color: on ? const Color(0xFF161A23) : Colors.transparent,
                  borderRadius: BorderRadius.circular(12),
                  border: Border.all(color: on ? kAccent : Colors.transparent, width: 2),
                ),
                child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
                  SizedBox(
                    width: tw,
                    height: tw * 9 / 16,
                    child: Stack(fit: StackFit.expand, children: [
                      NetImg(still.isNotEmpty ? still : fallback, fallbackText: 'E${e['num']}', radius: 8, cacheWidth: 480),
                      Center(
                        child: Container(
                          width: 38, height: 38,
                          decoration: const BoxDecoration(color: Color(0x8C000000), shape: BoxShape.circle),
                          child: const Icon(Icons.play_arrow, color: Colors.white),
                        ),
                      ),
                      if (frac > 0) Positioned(left: 6, right: 6, bottom: 6, child: ProgressLine(frac.toDouble())),
                    ]),
                  ),
                  const SizedBox(width: 14),
                  Expanded(
                    child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                      Row(children: [
                        Expanded(
                          child: Text('${e['num']}.  ${e['name']}', maxLines: 2, overflow: TextOverflow.ellipsis,
                              style: const TextStyle(fontWeight: FontWeight.w800, fontSize: 15)),
                        ),
                        if (frac >= .95) const Text('✓ Vu', style: TextStyle(color: Color(0xFF3ECF8E), fontWeight: FontWeight.w700)),
                        AnimatedBuilder(
                          animation: s.downloads,
                          builder: (c, _) => IconButton(
                            tooltip: 'Télécharger cet épisode',
                            onPressed: () => _downloadEpisode(s, j),
                            icon: Icon(_dlIcon(s, '${e['url']}'), size: 22),
                          ),
                        ),
                      ]),
                      if (bits.isNotEmpty) Text(bits, style: const TextStyle(color: kMuted, fontSize: 12)),
                      if ('${e['plot'] ?? ''}'.isNotEmpty)
                        Padding(
                          padding: const EdgeInsets.only(top: 4),
                          child: Text('${e['plot']}', maxLines: wide ? 3 : 2, overflow: TextOverflow.ellipsis,
                              style: const TextStyle(color: kMuted, fontSize: 13)),
                        ),
                    ]),
                  ),
                ]),
              );
            },
          ),
        ),
    ];
  }
}
