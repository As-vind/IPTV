// Paramètres : sources (M3U / Xtream), clé TMDB, langue, caches, à propos.
import 'dart:async';
import 'dart:io';

import 'package:file_picker/file_picker.dart';
import 'package:flutter/material.dart';
import 'package:url_launcher/url_launcher.dart';

import '../core/meta.dart';
import '../core/playlist_import.dart';
import '../core/store.dart';
import 'scope.dart';
import 'theme.dart';
import 'widgets.dart';

Future<void> showSourceDialog(BuildContext context, {Map<String, dynamic>? replace, bool file = false}) async {
  final src = await showDialog<Map<String, dynamic>>(
      context: context, builder: (_) => _SourceDialog(replace: replace, file: file));
  if (src == null || !context.mounted) return;
  final s = AppScope.read(context);
  if (replace != null) {
    s.setSource('${replace['id']}', force: true);
    toast(context, 'Liste « ${replace['name']} » mise à jour.');
  } else {
    s.addSource(src);
    toast(context, 'Chargement de « ${src['name']} »…');
  }
}

enum _Mode { url, file, xtream }

class _SourceDialog extends StatefulWidget {
  final Map<String, dynamic>? replace;
  final bool file;
  const _SourceDialog({this.replace, this.file = false});
  @override
  State<_SourceDialog> createState() => _SourceDialogState();
}

class _SourceDialogState extends State<_SourceDialog> {
  late _Mode _mode = widget.replace != null || widget.file ? _Mode.file : _Mode.url;
  final _name = TextEditingController();
  final _url = TextEditingController();
  final _server = TextEditingController();
  final _user = TextEditingController();
  final _pass = TextEditingController();
  String _ext = 'ts';
  String? _err;
  bool _busy = false;
  // fichier choisi
  String? _fileName;
  List<int>? _bytes;
  int _entries = 0;
  // envoi depuis un autre appareil
  LanImport? _lan;
  StreamSubscription<(String, List<int>)>? _lanSub;
  String? _lanAddr;

  @override
  void dispose() {
    _lanSub?.cancel();
    _lan?.stop();
    super.dispose();
  }

  void _gotFile(String name, List<int> bytes) {
    final n = countEntries(bytes);
    if (n == 0) {
      setState(() => _err = "« $name » n'est pas une liste M3U (aucune ligne #EXTINF).");
      return;
    }
    setState(() {
      _fileName = name;
      _bytes = bytes;
      _entries = n;
      _err = null;
      if (_name.text.trim().isEmpty) _name.text = name.replaceAll(RegExp(r'\.(m3u8?|txt)$', caseSensitive: false), '');
    });
  }

  Future<void> _pick() async {
    setState(() => _err = null);
    try {
      final r = await FilePicker.platform.pickFiles(type: FileType.any, withData: true, allowMultiple: false);
      if (r == null || r.files.isEmpty) return;
      final f = r.files.single;
      final bytes = f.bytes ?? (f.path != null ? await File(f.path!).readAsBytes() : null);
      if (bytes == null) throw Exception('fichier illisible');
      _gotFile(f.name, bytes);
    } catch (e) {
      if (mounted) {
        setState(() => _err = "Impossible d'ouvrir le sélecteur de fichiers sur cet appareil ($e).\n"
            'Utilisez plutôt « Envoyer depuis un autre appareil ».');
      }
    }
  }

  Future<void> _startLan() async {
    setState(() => _err = null);
    try {
      _lan ??= LanImport();
      final a = await _lan!.start();
      _lanSub = _lan!.files.listen((f) {
        if (mounted) _gotFile(f.$1, f.$2);
      });
      if (mounted) setState(() => _lanAddr = a);
    } catch (e) {
      _lan = null;
      if (mounted) setState(() => _err = 'Envoi impossible : $e');
    }
  }

  Future<void> _ok() async {
    final s = AppScope.read(context);
    final id = '${widget.replace?['id'] ?? AppState.newId()}';
    switch (_mode) {
      case _Mode.file:
        if (_bytes == null) return setState(() => _err = 'Choisissez d\'abord un fichier M3U.');
        setState(() => _busy = true);
        try {
          final path = await savePlaylist(s.dataDir, id, _bytes!);
          if (!mounted) return;
          if (widget.replace != null) {
            widget.replace!['url'] = path;
            widget.replace!['file'] = _fileName;
            s.save();
            Navigator.pop(context, widget.replace);
          } else {
            Navigator.pop(context, {
              'id': id, 'type': 'm3u', 'name': _name.text.trim().isEmpty ? (_fileName ?? 'Ma liste') : _name.text.trim(),
              'url': path, 'file': _fileName,
            });
          }
        } catch (e) {
          if (mounted) setState(() => _err = '$e');
        } finally {
          if (mounted) setState(() => _busy = false);
        }
      case _Mode.url:
        final url = _url.text.trim();
        if (url.isEmpty) return setState(() => _err = 'Indiquez le lien de la liste M3U.');
        final u = Uri.tryParse(url);
        final q = u?.queryParameters ?? {};
        if (u != null && u.path.toLowerCase().contains('get.php') && (q['username'] ?? '').isNotEmpty && (q['password'] ?? '').isNotEmpty) {
          Navigator.pop(context, {
            'id': id, 'type': 'xtream', 'name': _name.text.trim().isEmpty ? u.host : _name.text.trim(),
            'server': '${u.scheme}://${u.authority}', 'user': q['username'], 'password': q['password'], 'live_ext': 'ts',
          });
          return;
        }
        Navigator.pop(context, {
          'id': id, 'type': 'm3u', 'name': _name.text.trim().isEmpty ? (u?.host ?? 'Liste M3U') : _name.text.trim(), 'url': url,
        });
      case _Mode.xtream:
        if (_server.text.trim().isEmpty || _user.text.trim().isEmpty || _pass.text.trim().isEmpty) {
          return setState(() => _err = 'Serveur, identifiant et mot de passe requis.');
        }
        final srv = _server.text.trim();
        Navigator.pop(context, {
          'id': id, 'type': 'xtream',
          'name': _name.text.trim().isEmpty ? (Uri.tryParse(srv.contains('://') ? srv : 'http://$srv')?.host ?? srv) : _name.text.trim(),
          'server': srv, 'user': _user.text.trim(), 'password': _pass.text.trim(), 'live_ext': _ext,
        });
    }
  }

  Widget _modeChip(_Mode m, IconData ic, String t, {bool autofocus = false}) => ChoiceChip(
        autofocus: autofocus,
        avatar: Icon(ic, size: 18, color: _mode == m ? kBg : kAccent),
        label: Text(t),
        selected: _mode == m,
        showCheckmark: false,
        labelStyle: TextStyle(color: _mode == m ? kBg : kText, fontWeight: FontWeight.w700),
        onSelected: (_) => setState(() {
          _mode = m;
          _err = null;
        }),
      );

  Widget _bigButton(IconData ic, String title, String sub, VoidCallback onTap) => Padding(
        padding: const EdgeInsets.only(bottom: 10),
        child: Material(
          color: Colors.white.withValues(alpha: .06),
          shape: RoundedRectangleBorder(
              borderRadius: BorderRadius.circular(16), side: BorderSide(color: Colors.white.withValues(alpha: .12))),
          child: InkWell(
            borderRadius: BorderRadius.circular(16),
            focusColor: kAccent.withValues(alpha: .28),
            onTap: _busy ? null : onTap,
            child: Padding(
              padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
              child: Row(children: [
                Icon(ic, color: kAccent, size: 30),
                const SizedBox(width: 14),
                Expanded(
                  child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                    Text(title, style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 15.5, color: Colors.white)),
                    const SizedBox(height: 2),
                    Text(sub, style: const TextStyle(color: kMuted, fontSize: 12.5)),
                  ]),
                ),
              ]),
            ),
          ),
        ),
      );

  List<Widget> _fileSection() => [
        _bigButton(Icons.folder_open_rounded, 'Choisir un fichier sur cet appareil',
            'Fichier .m3u / .m3u8 (téléchargements, carte SD, clé USB, iCloud…)', _pick),
        _bigButton(Icons.devices_rounded, 'Envoyer depuis un autre appareil',
            'Téléphone ou PC sur le même Wi-Fi — idéal pour une TV', _startLan),
        if (_lanAddr != null)
          Container(
            width: double.infinity,
            margin: const EdgeInsets.only(bottom: 10),
            padding: const EdgeInsets.all(14),
            decoration: BoxDecoration(color: const Color(0xFF10233F), borderRadius: BorderRadius.circular(14)),
            child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              const Text('Sur votre téléphone ou PC, ouvrez dans le navigateur :', style: TextStyle(color: kMuted, fontSize: 13)),
              const SizedBox(height: 6),
              SelectableText(_lanAddr!, style: const TextStyle(fontSize: 24, fontWeight: FontWeight.w800, color: Colors.white)),
              const SizedBox(height: 6),
              Text(_bytes == null ? 'puis choisissez le fichier. En attente…' : 'Fichier reçu ✓',
                  style: const TextStyle(color: kMuted, fontSize: 13)),
            ]),
          ),
        if (_bytes != null)
          Row(children: [
            const Icon(Icons.check_circle, color: Color(0xFF5AD17E)),
            const SizedBox(width: 8),
            Expanded(
              child: Text('$_fileName — $_entries entrée(s)',
                  maxLines: 2, overflow: TextOverflow.ellipsis, style: const TextStyle(fontWeight: FontWeight.w700)),
            ),
          ]),
        const SizedBox(height: 6),
        const Text("La liste est copiée dans l'application : elle reste disponible même si le fichier d'origine est "
            'supprimé. Pour la mettre à jour : Paramètres → Sources → « Remplacer le fichier ».',
            style: TextStyle(color: kMuted, fontSize: 12.5)),
      ];

  @override
  Widget build(BuildContext context) {
    final replacing = widget.replace != null;
    return AlertDialog(
      title: Text(replacing ? 'Remplacer le fichier de « ${widget.replace!['name']} »' : 'Ajouter une source'),
      content: SizedBox(
        width: 520,
        child: SingleChildScrollView(
          child: Column(mainAxisSize: MainAxisSize.min, crossAxisAlignment: CrossAxisAlignment.start, children: [
            if (!replacing) ...[
              Wrap(spacing: 8, runSpacing: 8, children: [
                _modeChip(_Mode.url, Icons.link_rounded, 'Lien M3U', autofocus: !widget.file),
                _modeChip(_Mode.file, Icons.insert_drive_file_outlined, 'Fichier M3U', autofocus: widget.file),
                _modeChip(_Mode.xtream, Icons.satellite_alt, 'Compte Xtream'),
              ]),
              const SizedBox(height: 14),
              TextField(controller: _name, decoration: const InputDecoration(labelText: 'Nom (facultatif)')),
              const SizedBox(height: 10),
            ],
            if (_mode == _Mode.url) ...[
              TextField(controller: _url, keyboardType: TextInputType.url,
                  decoration: const InputDecoration(labelText: 'Lien M3U', hintText: 'https://…/playlist.m3u')),
              const SizedBox(height: 8),
              const Text('Un lien « get.php?username=…&password=… » est converti automatiquement en compte Xtream '
                  '(TV + films + séries + fiches).', style: TextStyle(color: kMuted, fontSize: 12.5)),
            ] else if (_mode == _Mode.file)
              ..._fileSection()
            else ...[
              TextField(controller: _server, keyboardType: TextInputType.url,
                  decoration: const InputDecoration(labelText: 'Serveur', hintText: 'http://serveur.exemple.com:8080')),
              const SizedBox(height: 10),
              TextField(controller: _user, decoration: const InputDecoration(labelText: 'Identifiant')),
              const SizedBox(height: 10),
              TextField(controller: _pass, obscureText: true, decoration: const InputDecoration(labelText: 'Mot de passe')),
              const SizedBox(height: 10),
              Row(children: [
                const Text('Format des chaînes :  ', style: TextStyle(color: kMuted)),
                ChoiceChip(label: const Text('ts'), selected: _ext == 'ts', onSelected: (_) => setState(() => _ext = 'ts')),
                const SizedBox(width: 8),
                ChoiceChip(label: const Text('m3u8'), selected: _ext == 'm3u8', onSelected: (_) => setState(() => _ext = 'm3u8')),
              ]),
            ],
            if (_err != null)
              Padding(padding: const EdgeInsets.only(top: 10), child: Text(_err!, style: const TextStyle(color: Color(0xFFFF6B6B)))),
          ]),
        ),
      ),
      actions: [
        TextButton(onPressed: () => Navigator.pop(context), child: const Text('Annuler')),
        FilledButton(
          onPressed: _busy ? null : _ok,
          child: Text(replacing ? 'Remplacer' : 'Ajouter'),
        ),
      ],
    );
  }
}

class SettingsScreen extends StatefulWidget {
  const SettingsScreen({super.key});
  @override
  State<SettingsScreen> createState() => _SettingsScreenState();
}

class _SettingsScreenState extends State<SettingsScreen> {
  late final TextEditingController _key = TextEditingController(text: AppScope.read(context).userTmdbKey);
  bool _testing = false;
  static const _langs = [('fr-FR', 'Français'), ('en-US', 'English'), ('es-ES', 'Español'), ('de-DE', 'Deutsch'),
    ('it-IT', 'Italiano'), ('pt-PT', 'Português'), ('ar-SA', 'العربية')];

  Future<void> _saveKey(AppState s) async {
    final k = _key.text.trim();
    if (k.isEmpty) {
      s.setTmdbKey('');
      toast(context, 'Clé TMDB supprimée.');
      return;
    }
    setState(() => _testing = true);
    try {
      final r = await Tmdb(k).get('/configuration');
      if (r.isEmpty) throw Exception('réponse vide');
      s.setTmdbKey(k);
      if (mounted) toast(context, 'Clé TMDB valide et enregistrée ✓');
    } catch (e) {
      if (mounted) toast(context, 'Clé refusée par TMDB : $e');
    } finally {
      if (mounted) setState(() => _testing = false);
    }
  }

  Widget _h(String t) => Padding(
        padding: const EdgeInsets.fromLTRB(0, 26, 0, 10),
        child: Text(t, style: const TextStyle(fontSize: 18, fontWeight: FontWeight.w800)),
      );

  @override
  Widget build(BuildContext context) {
    final s = AppScope.of(context);
    final pad = isWide(context) ? 32.0 : 16.0;
    return Scaffold(
      appBar: AppBar(title: const Text('Paramètres')),
      body: ListView(padding: EdgeInsets.fromLTRB(pad, 0, pad, 50), children: [
        _h('Sources'),
        for (final src in s.sources)
          Card(
            color: kCard2,
            child: ListTile(
              leading: Icon(src['type'] == 'xtream' ? Icons.satellite_alt : Icons.playlist_play,
                  color: s.currentSource?['id'] == src['id'] ? kAccent : kMuted),
              title: Text('${src['name']}'),
              subtitle: Text(src['type'] == 'xtream' ? 'Compte Xtream Codes' : (src['file'] != null ? 'Fichier M3U · ${src['file']}' : 'Lien M3U'),
                  style: const TextStyle(color: kMuted)),
              onTap: () => s.setSource('${src['id']}'),
              trailing: Wrap(children: [
                if (src['file'] != null)
                  IconButton(tooltip: 'Remplacer le fichier', icon: const Icon(Icons.upload_file),
                      onPressed: () => showSourceDialog(context, replace: src)),
                IconButton(tooltip: 'Actualiser', icon: const Icon(Icons.refresh),
                    onPressed: () => s.setSource('${src['id']}', force: true)),
                IconButton(
                  tooltip: 'Supprimer',
                  icon: const Icon(Icons.delete_outline),
                  onPressed: () async {
                    final ok = await showDialog<bool>(
                      context: context,
                      builder: (c) => AlertDialog(
                        title: Text('Supprimer « ${src['name']} » ?'),
                        actions: [
                          TextButton(onPressed: () => Navigator.pop(c, false), child: const Text('Annuler')),
                          FilledButton(onPressed: () => Navigator.pop(c, true), child: const Text('Supprimer')),
                        ],
                      ),
                    );
                    if (ok == true) await s.deleteSource('${src['id']}');
                  },
                ),
              ]),
            ),
          ),
        if (s.sourceInfo.isNotEmpty)
          Padding(padding: const EdgeInsets.only(top: 6), child: Text(s.sourceInfo, style: const TextStyle(color: kMuted, fontSize: 12.5))),
        const SizedBox(height: 8),
        Align(
          alignment: Alignment.centerLeft,
          child: FilledButton.icon(onPressed: () => showSourceDialog(context), icon: const Icon(Icons.add), label: const Text('Ajouter une source')),
        ),
        _h('Fiches films, séries et acteurs (TMDB)'),
        Text(
            "Avec une clé TMDB gratuite, l'application affiche les photos et biographies des acteurs, leur filmographie, "
            'les fonds, bandes-annonces, âges requis et vignettes des épisodes. Créez un compte sur themoviedb.org → '
            'Paramètres → API, puis collez la clé API (v3) ou le jeton de lecture (v4).'
            '${kTmdbBuiltin.length > 0 ? "  Une clé est déjà intégrée à l'application : ce champ ne sert que si vous voulez utiliser la vôtre." : ''}',
            style: const TextStyle(color: kMuted, height: 1.4)),
        const SizedBox(height: 10),
        TextField(controller: _key, obscureText: true, decoration: const InputDecoration(labelText: 'Clé API TMDB')),
        const SizedBox(height: 10),
        Wrap(spacing: 10, runSpacing: 10, children: [
          FilledButton(onPressed: _testing ? null : () => _saveKey(s), child: Text(_testing ? 'Vérification…' : 'Tester et enregistrer')),
          OutlinedButton(
            onPressed: () => launchUrl(Uri.parse('https://www.themoviedb.org/settings/api'), mode: LaunchMode.externalApplication),
            child: const Text('Obtenir une clé'),
          ),
        ]),
        const SizedBox(height: 14),
        Wrap(spacing: 8, runSpacing: 8, crossAxisAlignment: WrapCrossAlignment.center, children: [
          const Text('Langue des fiches :  ', style: TextStyle(color: kMuted)),
          for (final (code, name) in _langs)
            ChoiceChip(
              label: Text(name),
              selected: s.lang == code,
              showCheckmark: false,
              labelStyle: TextStyle(color: s.lang == code ? kBg : kText, fontWeight: FontWeight.w700),
              onSelected: (_) => s.setLang(code),
            ),
        ]),
        _h('Lecture, pré-chargement et téléchargements'),
        const Text(
            "Pré-chargement : le film ou l'épisode se télécharge en avance pendant que vous regardez. Si la connexion "
            "ralentit, la lecture continue sur ce qui est déjà chargé ; si elle s'arrête, l'application attend d'avoir "
            "rempli la réserve puis repart sans à-coups. Avec un très petit débit, utilisez plutôt « Télécharger » sur la fiche.",
            style: TextStyle(color: kMuted, height: 1.4)),
        const SizedBox(height: 10),
        Wrap(spacing: 8, runSpacing: 8, crossAxisAlignment: WrapCrossAlignment.center, children: [
          const Text('Films et séries :  ', style: TextStyle(color: kMuted)),
          for (final (v, t) in const [(0, 'Désactivé'), (1, "1 min d'avance"), (5, "5 min d'avance"), (10, "10 min d'avance")])
            ChoiceChip(
              label: Text(t), selected: s.bufferMin == v, showCheckmark: false,
              labelStyle: TextStyle(color: s.bufferMin == v ? kBg : kText, fontWeight: FontWeight.w700),
              onSelected: (_) => s.setBufferMin(v),
            ),
        ]),
        const SizedBox(height: 10),
        Wrap(spacing: 8, runSpacing: 8, crossAxisAlignment: WrapCrossAlignment.center, children: [
          const Text('Chaînes TV (mémoire tampon) :  ', style: TextStyle(color: kMuted)),
          for (final (v, t) in const [(3, '3 s (standard)'), (5, '5 s'), (10, '10 s'), (20, '20 s'), (30, '30 s')])
            ChoiceChip(
              label: Text(t), selected: s.liveCacheSecs == v, showCheckmark: false,
              labelStyle: TextStyle(color: s.liveCacheSecs == v ? kBg : kText, fontWeight: FontWeight.w700),
              onSelected: (_) => s.setLiveCache(v),
            ),
        ]),
        const SizedBox(height: 8),
        const Text("Les films téléchargés sont enregistrés dans l'espace de l'application (visible dans l'app Fichiers sur iPad / iPhone).",
            style: TextStyle(color: kMuted, fontSize: 12.5)),
        _h('Profils et stockage'),
        Wrap(spacing: 10, runSpacing: 10, children: [
          OutlinedButton.icon(
            onPressed: () {
              Navigator.of(context).popUntil((r) => r.isFirst);
              s.logoutProfile();
            },
            icon: const Icon(Icons.people_outline),
            label: const Text('Changer / gérer les profils'),
          ),
          OutlinedButton(
            onPressed: () async {
              await s.clearMetaCache();
              if (context.mounted) toast(context, 'Cache des fiches vidé.');
            },
            child: const Text('Vider le cache des fiches'),
          ),
          OutlinedButton(
            onPressed: () {
              s.clearProgress();
              toast(context, 'Historique de lecture effacé.');
            },
            child: const Text("Effacer l'historique de lecture"),
          ),
        ]),
        _h('À propos'),
        Row(children: [
          const Logo(height: 44),
          const SizedBox(width: 16),
          Expanded(child: Text('$kAppTitle $kAppVersion — conçu par $kAppAuthor', style: const TextStyle(color: kMuted))),
        ]),
        const SizedBox(height: 10),
        const Text("Ce produit utilise l'API de TMDB mais n'est ni approuvé ni certifié par TMDB. "
            "IPTV Player ne fournit aucun contenu : vous ajoutez votre propre abonnement.",
            style: TextStyle(color: kMuted, fontSize: 12.5)),
        const SizedBox(height: 10),
        const Align(alignment: Alignment.centerLeft, child: Signature(size: 22)),
      ]),
    );
  }
}
