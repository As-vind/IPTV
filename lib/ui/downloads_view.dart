// Téléchargements : progression, pause / reprise, lecture hors ligne.
import 'package:flutter/material.dart';

import '../core/downloads.dart';
import 'nav.dart';
import 'octo.dart';
import 'scope.dart';
import 'theme.dart';
import 'widgets.dart';

class DownloadsView extends StatelessWidget {
  final bool collapsed;
  const DownloadsView({super.key, this.collapsed = false});
  @override
  Widget build(BuildContext context) {
    final s = AppScope.of(context);
    final dm = s.downloads;
    return AnimatedBuilder(
      animation: dm,
      builder: (context, _) {
        final jobs = dm.jobs..sort((a, b) => ((b['added'] as num?) ?? 0).compareTo((a['added'] as num?) ?? 0));
        final done = jobs.where((j) => j['state'] == 'done').toList();
        final total = done.fold<num>(0, (a, j) => a + ((j['size'] as num?) ?? 0));
        return ListView(padding: const EdgeInsets.only(bottom: 90), children: [
          SafeArea(bottom: false, child: PageTitle('Téléchargements', top: collapsed ? 96 : (isPhone(context) ? 16 : 38))),
          Padding(
            padding: EdgeInsets.symmetric(horizontal: isPhone(context) ? 16 : 34),
            child: Text(
              '${done.length} vidéo(s) disponible(s) hors ligne · ${fmtSize(total)}\n'
              "Un téléchargement à la fois. Si votre abonnement n'autorise qu'une connexion, évitez de regarder "
              'un autre flux pendant un téléchargement.',
              style: const TextStyle(color: kMuted, fontSize: 13),
            ),
          ),
          const SizedBox(height: 12),
          if (jobs.isEmpty)
            const Padding(
              padding: EdgeInsets.all(34),
              child: Text(
                "Aucun téléchargement pour l'instant.\n\nSur la fiche d'un film, touchez « Télécharger » ; sur une série, "
                "l'icône ⬇ à côté d'un épisode ou « Télécharger la saison ». Le fichier est enregistré sur l'appareil : "
                "il se regarde ensuite sans coupure, même sans connexion — idéal avec un petit débit.",
                style: TextStyle(color: kMuted, fontSize: 15, height: 1.4),
              ),
            ),
          for (final j in jobs) _row(context, dm, j),
        ]);
      },
    );
  }

  Widget _row(BuildContext context, DownloadManager dm, Map<String, dynamic> j) {
    final st = '${j['state']}';
    final pct = dm.percent(j);
    final size = (j['size'] as num?) ?? 0, doneB = (j['done'] as num?) ?? 0;
    String txt;
    switch (st) {
      case 'done':
        txt = '✓ Téléchargé · ${fmtSize(size > 0 ? size : doneB)} · disponible sans connexion';
      case 'downloading':
        final sp = dm.speed['${j['id']}'] ?? 0;
        txt = 'Téléchargement… $pct %  ·  ${fmtSize(doneB)}${size > 0 ? ' / ${fmtSize(size)}' : ''}';
        if (sp > 0) {
          txt += '  ·  ${fmtSize(sp)}/s';
          if (size > 0) txt += '  ·  reste ${fmtSecs((size - doneB) / sp)}';
        }
      case 'queued':
        txt = 'En attente…';
      case 'paused':
        txt = 'En pause · $pct %';
      default:
        txt = '⚠ Échec : ${j['error'] ?? ''}';
    }
    return Padding(
      padding: EdgeInsets.symmetric(horizontal: isPhone(context) ? 10 : 26, vertical: 4),
      child: Container(
        padding: const EdgeInsets.all(10),
        decoration: BoxDecoration(color: const Color(0xFF10141B), borderRadius: BorderRadius.circular(14)),
        child: Row(children: [
          SizedBox(width: 64, height: 96, child: NetImg('${j['logo'] ?? ''}', fallbackText: '${j['name']}', radius: 8, cacheWidth: 200)),
          const SizedBox(width: 14),
          Expanded(
            child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Text('${j['name']}', maxLines: 2, overflow: TextOverflow.ellipsis,
                  style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 15, color: Colors.white)),
              const SizedBox(height: 4),
              Text(txt, style: const TextStyle(color: kMuted, fontSize: 12.5)),
              if (st != 'done') ...[
                const SizedBox(height: 8),
                ClipRRect(
                  borderRadius: BorderRadius.circular(2),
                  child: LinearProgressIndicator(
                      value: size > 0 ? doneB / size : null, minHeight: 4, color: kAccent, backgroundColor: Colors.white12),
                ),
              ],
            ]),
          ),
          const SizedBox(width: 8),
          if (st == 'done')
            FilledButton.icon(
              onPressed: () => playItems(context, [dm.playItem(j)], 0),
              icon: const Icon(Icons.play_arrow_rounded),
              label: const Text('Lire'),
            )
          else
            IconButton(
              tooltip: st == 'downloading' || st == 'queued' ? 'Pause' : 'Reprendre',
              onPressed: () => st == 'downloading' || st == 'queued' ? dm.pause('${j['id']}') : dm.resume('${j['id']}'),
              icon: Icon(st == 'downloading' || st == 'queued' ? Icons.pause : (st == 'error' ? Icons.refresh : Icons.play_arrow)),
            ),
          IconButton(
            tooltip: 'Supprimer',
            icon: const Icon(Icons.delete_outline),
            onPressed: () async {
              final ok = await showDialog<bool>(
                context: context,
                builder: (c) => AlertDialog(
                  title: Text('Supprimer « ${j['name']} » ?'),
                  content: const Text("Le fichier sera effacé de l'appareil."),
                  actions: [
                    TextButton(onPressed: () => Navigator.pop(c, false), child: const Text('Annuler')),
                    FilledButton(onPressed: () => Navigator.pop(c, true), child: const Text('Supprimer')),
                  ],
                ),
              );
              if (ok == true) await dm.remove('${j['id']}');
            },
          ),
        ]),
      ),
    );
  }
}
