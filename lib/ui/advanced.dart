// Paramètres avancés : lecture et anti-coupure, chaînes et qualité, vidéo, audio, entretien,
// administration depuis un navigateur (adresse, code PIN, QR code) et maintenance.
import 'dart:convert';
import 'dart:io';

import 'package:file_picker/file_picker.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:qr/qr.dart';

import '../core/channels.dart';
import '../core/models.dart';
import '../core/store.dart';
import 'scope.dart';
import 'theme.dart';
import 'widgets.dart';
import 'tv_field.dart';

const Map<String, String> _sectionTitles = {
  'Lecture': 'Lecture et anti-coupure',
  'Chaînes': 'Chaînes et qualité',
  'Vidéo': 'Vidéo',
  'Audio': 'Audio et sous-titres',
  'Maintenance': 'Entretien automatique',
};

/// Réglages générés depuis kSettings (identiques à la version Windows et à l'administration web).
class AdvancedSettings extends StatelessWidget {
  const AdvancedSettings({super.key});

  Widget _h(String t) => Padding(
        padding: const EdgeInsets.fromLTRB(0, 26, 0, 8),
        child: Text(t, style: const TextStyle(fontSize: 18, fontWeight: FontWeight.w800)),
      );

  @override
  Widget build(BuildContext context) {
    final s = AppScope.of(context);
    final out = <Widget>[];
    String? sec;
    for (final st in kSettings) {
      if (st.section != sec) {
        sec = st.section;
        out.add(_h(_sectionTitles[sec] ?? sec));
        if (sec == 'Lecture') {
          out.add(const Text(
              'AUTO adapte la mémoire tampon après chaque coupure et la réduit quand tout est stable. '
              'Performance : zapping le plus rapide. Anti-freeze : continuité avant tout. Personnalisé : les valeurs ci-dessous.',
              style: TextStyle(color: kMuted, height: 1.4)));
        }
      }
      final custom = s.pset['profile'] == 'custom';
      if (st.key.startsWith('c_') && !custom) continue;
      if (st.key == 'refresh') {
        out.add(_choice(s, st, extraHint: 'Sur téléphone et TV : « Adapter au flux » lisse le mouvement selon la fréquence de l’écran.'));
        continue;
      }
      if (st.key == 'passthrough' && !Platform.isAndroid) continue;
      switch (st.type) {
        case 'bool':
          out.add(SwitchListTile(
            contentPadding: EdgeInsets.zero,
            title: Text(st.label),
            value: s.pset[st.key] == true,
            onChanged: (v) => s.setSetting(st.key, v),
          ));
        case 'choice':
          out.add(_choice(s, st));
        default:
          final v = ((s.pset[st.key] as num?) ?? (st.def as num)).toDouble();
          out.add(Padding(
            padding: const EdgeInsets.only(top: 6),
            child: Row(children: [
              Expanded(flex: 5, child: Text(st.label)),
              Expanded(
                flex: 6,
                child: Slider(
                  min: st.lo.toDouble(),
                  max: st.hi.toDouble(),
                  divisions: st.type == 'float' ? ((st.hi - st.lo) * 2).toInt() : ((st.hi - st.lo).toInt() > 200 ? 100 : (st.hi - st.lo).toInt()),
                  value: v.clamp(st.lo.toDouble(), st.hi.toDouble()),
                  label: st.type == 'float' ? v.toStringAsFixed(1) : '${v.round()}',
                  onChanged: (x) => s.setSetting(st.key, st.type == 'float' ? (x * 2).round() / 2 : x.round()),
                ),
              ),
              SizedBox(width: 56, child: Text(st.type == 'float' ? v.toStringAsFixed(1) : '${v.round()}', textAlign: TextAlign.end)),
            ]),
          ));
      }
    }
    out.add(Padding(
      padding: const EdgeInsets.only(top: 10),
      child: Text(
          'Appareil : ${s.cores} cœurs${s.ramMb > 0 ? ', ${(s.ramMb / 1024).toStringAsFixed(1)} Go de mémoire' : ''} — niveau '
          '${{'low': 'économique', 'mid': 'standard', 'high': 'puissant'}[s.hwTier]} (qualité et mémoire tampon adaptées automatiquement)',
          style: const TextStyle(color: kMuted, fontSize: 12.5)),
    ));
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: out);
  }

  Widget _choice(AppState s, Setting st, {String? extraHint}) => Padding(
        padding: const EdgeInsets.only(top: 10),
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Text(st.label, style: const TextStyle(color: kMuted)),
          const SizedBox(height: 6),
          Wrap(spacing: 8, runSpacing: 8, children: [
            for (final (code, lab) in st.choices)
              ChoiceChip(
                label: Text(lab),
                selected: s.pset[st.key] == code,
                showCheckmark: false,
                onSelected: (_) => s.setSetting(st.key, code),
              ),
          ]),
          if (extraHint != null) Padding(padding: const EdgeInsets.only(top: 4), child: Text(extraHint, style: const TextStyle(color: kMuted, fontSize: 12))),
        ]),
      );
}

/// QR code dessiné (paquet qr, correction M).
class QrView extends StatelessWidget {
  final String data;
  final double size;
  const QrView(this.data, {super.key, this.size = 170});
  @override
  Widget build(BuildContext context) {
    final img = QrImage(QrCode.fromData(data: data, errorCorrectLevel: QrErrorCorrectLevel.M));
    return Container(
      width: size,
      height: size,
      color: Colors.white,
      padding: EdgeInsets.all(size / 14),
      child: CustomPaint(painter: _QrPainter(img)),
    );
  }
}

class _QrPainter extends CustomPainter {
  final QrImage img;
  _QrPainter(this.img);
  @override
  void paint(Canvas c, Size sz) {
    final n = img.moduleCount;
    final cell = sz.width / n;
    final p = Paint()..color = Colors.black;
    for (var r = 0; r < n; r++) {
      for (var col = 0; col < n; col++) {
        if (img.isDark(r, col)) c.drawRect(Rect.fromLTWH(col * cell, r * cell, cell + .5, cell + .5), p);
      }
    }
  }

  @override
  bool shouldRepaint(covariant _QrPainter old) => old.img != img;
}

/// Administration depuis un navigateur.
class AdminCard extends StatefulWidget {
  const AdminCard({super.key});
  @override
  State<AdminCard> createState() => _AdminCardState();
}

class _AdminCardState extends State<AdminCard> {
  bool _busy = false;

  @override
  Widget build(BuildContext context) {
    final s = AppScope.of(context);
    final adm = s.cfg['admin'] as Map;
    final on = s.admin?.running == true;
    final url = on && s.admin!.urls.isNotEmpty ? s.admin!.urls.first : '';
    final info = Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      const Text(
          "Gérez l'application depuis un ordinateur, un téléphone ou une tablette du même réseau : ajout de listes "
          '(glisser-déposer de fichiers M3U), catégories, doublons, favoris, guide TV, réglages, journaux, sauvegarde. '
          'Accès protégé par un code PIN et limité au réseau local (jamais exposé sur Internet).',
          style: TextStyle(color: kMuted, height: 1.4)),
      SwitchListTile(
        contentPadding: EdgeInsets.zero,
        title: const Text("Activer l'administration web"),
        value: on,
        onChanged: _busy
            ? null
            : (v) async {
                setState(() => _busy = true);
                final err = await s.setAdmin(v);
                if (mounted) setState(() => _busy = false);
                if (err != null && context.mounted) toast(context, 'Impossible de démarrer : $err');
              },
      ),
      if (on) ...[
        SelectableText(url, style: const TextStyle(fontSize: 22, fontWeight: FontWeight.w800)),
        const SizedBox(height: 4),
        Text('Adresse IP : ${Uri.tryParse(url)?.host ?? ''}  ·  Port : ${s.admin!.port}  ·  Code PIN : ${adm['pin']}',
            style: const TextStyle(color: kMuted)),
      ] else
        Text('Désactivée.  Code PIN : ${adm['pin']}', style: const TextStyle(color: kMuted)),
      const SizedBox(height: 8),
      OutlinedButton(onPressed: s.newAdminPin, child: const Text('Nouveau code PIN')),
    ]);
    if (!on || url.isEmpty) return info;
    return LayoutBuilder(builder: (c, cons) {
      if (cons.maxWidth < 560) {
        return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [info, const SizedBox(height: 12), QrView(url)]);
      }
      return Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Expanded(child: info),
        const SizedBox(width: 18),
        QrView(url),
      ]);
    });
  }
}

/// Maintenance : actualisation, vérification, nettoyage, sauvegarde et restauration.
class MaintenanceCard extends StatelessWidget {
  const MaintenanceCard({super.key});

  @override
  Widget build(BuildContext context) {
    final s = AppScope.of(context);
    return Wrap(spacing: 10, runSpacing: 10, children: [
      OutlinedButton.icon(
        onPressed: () {
          final cur = s.currentSource?['id'];
          if (cur != null) s.setSource('$cur', force: true);
          toast(context, 'Actualisation de la liste…');
        },
        icon: const Icon(Icons.refresh),
        label: const Text('Actualiser la liste'),
      ),
      OutlinedButton.icon(
        onPressed: () async {
          final favs = (s.byKind['live'] ?? const <Item>[]).where((i) => s.isFav(i.url)).toList();
          final list = favs.isNotEmpty ? favs : s.trendingChannels(30);
          toast(context, 'Vérification de ${list.length} chaîne(s)…');
          final (ok, bad) = await s.checkItems(list);
          if (context.mounted) toast(context, 'Vérification : $ok flux OK, $bad indisponible(s).');
        },
        icon: const Icon(Icons.health_and_safety_outlined),
        label: const Text('Vérifier mes chaînes favorites'),
      ),
      OutlinedButton.icon(
        onPressed: () async {
          final b = await s.cleanNow();
          if (context.mounted) toast(context, 'Cache nettoyé : ${(b / 1048576).toStringAsFixed(1)} Mo libérés.');
        },
        icon: const Icon(Icons.cleaning_services_outlined),
        label: const Text('Nettoyer le cache'),
      ),
      OutlinedButton.icon(
        onPressed: () async {
          final txt = const JsonEncoder.withIndent(' ').convert(s.backupData());
          final n = DateTime.now();
          final name = 'iptv-player-sauvegarde-${n.year}${n.month.toString().padLeft(2, '0')}${n.day.toString().padLeft(2, '0')}.json';
          String? path;
          try {
            path = await FilePicker.platform.saveFile(fileName: name, bytes: utf8.encode(txt));
          } catch (_) {}
          if (path == null) {
            final f = File('${s.dataDir.path}/sauvegardes/$name');
            await f.parent.create(recursive: true);
            await f.writeAsString(txt);
            await Clipboard.setData(ClipboardData(text: f.path));
            path = f.path;
          }
          if (context.mounted) toast(context, 'Configuration sauvegardée : $path');
        },
        icon: const Icon(Icons.save_outlined),
        label: const Text('Sauvegarder la configuration'),
      ),
      OutlinedButton.icon(
        onPressed: () async {
          try {
            final r = await FilePicker.platform.pickFiles(type: FileType.any, withData: true);
            final f = r?.files.single;
            if (f == null) return;
            final bytes = f.bytes ?? await File(f.path!).readAsBytes();
            await s.restore(Map<String, dynamic>.from(jsonDecode(utf8.decode(bytes)) as Map));
            if (context.mounted) toast(context, 'Configuration restaurée ✓');
          } catch (e) {
            if (context.mounted) toast(context, 'Restauration impossible : $e');
          }
        },
        icon: const Icon(Icons.restore),
        label: const Text('Restaurer…'),
      ),
      OutlinedButton.icon(
        onPressed: () async {
          final ok = await showDialog<bool>(
            context: context,
            builder: (c) => AlertDialog(
              title: const Text('Réglages par défaut ?'),
              content: const Text('Lecture, image, son et qualité reviennent aux valeurs par défaut. '
                  'Vos listes, profils et favoris sont conservés.'),
              actions: [
                TextButton(onPressed: () => Navigator.pop(c, false), child: const Text('Annuler')),
                FilledButton(onPressed: () => Navigator.pop(c, true), child: const Text('Rétablir')),
              ],
            ),
          );
          if (ok == true) {
            s.resetSettings();
            if (context.mounted) toast(context, 'Réglages par défaut rétablis.');
          }
        },
        icon: const Icon(Icons.settings_backup_restore),
        label: const Text('Réglages par défaut'),
      ),
    ]);
  }
}

/// Guide TV (XMLTV) d'une source.
Future<void> editGuide(BuildContext context, Map<String, dynamic> src) async {
  final s = AppScope.read(context);
  final c = TextEditingController(text: '${src['epg'] ?? ''}');
  final url = await showDialog<String>(
    context: context,
    builder: (d) => AlertDialog(
      title: Text('Guide TV de « ${src['name']} »'),
      content: Column(mainAxisSize: MainAxisSize.min, crossAxisAlignment: CrossAxisAlignment.start, children: [
        Text(
            'Adresse d’un guide XMLTV (.xml ou .xml.gz). Laissez vide pour utiliser celui de la liste'
            '${(src['epg_auto'] ?? '') != '' ? ' (${src['epg_auto']})' : ''} ou du compte Xtream.',
            style: const TextStyle(color: kMuted)),
        const SizedBox(height: 10),
        TvTextField(controller: c, keyboardType: TextInputType.url, label: 'Guide TV (XMLTV)', hint: 'https://…/epg.xml.gz'),
      ]),
      actions: [
        TextButton(onPressed: () => Navigator.pop(d), child: const Text('Annuler')),
        FilledButton(onPressed: () => Navigator.pop(d, c.text.trim()), child: const Text('Enregistrer')),
      ],
    ),
  );
  if (url == null) return;
  if (url.isNotEmpty && !RegExp(r'^https?://', caseSensitive: false).hasMatch(url)) {
    if (context.mounted) toast(context, "L'adresse doit commencer par http:// ou https://");
    return;
  }
  if (url.isEmpty) {
    src.remove('epg');
  } else {
    src['epg'] = url;
  }
  s.guides.remove(src['id']);
  s.save();
  if (s.epgUrl(src).isNotEmpty) {
    await s.loadGuide(src, force: true);
    if (context.mounted) toast(context, 'Guide TV chargé ✓');
  }
}
