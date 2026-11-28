// Paramètres : sources (M3U / Xtream), clé TMDB, langue, caches, à propos.
import 'dart:async';
import 'dart:io';

import 'package:file_picker/file_picker.dart';
import 'package:flutter/material.dart';
import 'package:url_launcher/url_launcher.dart';

import '../core/meta.dart';
import '../core/jellyfin.dart';
import '../core/playlist_import.dart';
import 'advanced.dart';
import 'tv_field.dart';
import '../core/store.dart';
import 'scope.dart';
import 'theme.dart';
import 'widgets.dart';

Future<void> showSourceDialog(BuildContext context,
    {Map<String, dynamic>? replace, bool file = false, Map<String, dynamic>? edit}) async {
  final src = await showDialog<Map<String, dynamic>>(
      context: context, builder: (_) => _SourceDialog(replace: replace, file: file, edit: edit));
  if (src == null || !context.mounted) return;
  final s = AppScope.read(context);
  if (edit != null) {
    final id = '${edit['id']}';
    if (src['__delete__'] == true) {
      await s.deleteSource(id);
      if (context.mounted) toast(context, 'Source « ${edit['name']} » supprimée.');
      return;
    }
    final keep = {for (final k in ['epg', 'epg_auto', 'updated_ts']) if (edit.containsKey(k)) k: edit[k]};
    final changedLink = ['type', 'url', 'server', 'user', 'password', 'live_ext'].any((k) => '${edit[k]}' != '${src[k]}');
    edit
      ..clear()
      ..addAll(src)
      ..addAll(keep)
      ..['id'] = id;
    s.save();
    if (changedLink || s.currentSource?['id'] == id) {
      unawaited(s.setSource(id, force: changedLink));
    } else {
      s.touch();
    }
    if (context.mounted) toast(context, 'Source « ${edit['name']} » modifiée.');
    return;
  }
  if (replace != null) {
    s.setSource('${replace['id']}', force: true);
    toast(context, 'Liste « ${replace['name']} » mise à jour.');
  } else {
    s.addSource(src);
    toast(context, 'Chargement de « ${src['name']} »…');
  }
}

enum _Mode { url, file, xtream, jellyfin }

class _SourceDialog extends StatefulWidget {
  final Map<String, dynamic>? replace;
  final Map<String, dynamic>? edit;
  final bool file;
  const _SourceDialog({this.replace, this.file = false, this.edit});
  @override
  State<_SourceDialog> createState() => _SourceDialogState();
}

class _SourceDialogState extends State<_SourceDialog> {
  late _Mode _mode = widget.replace != null || widget.file ? _Mode.file : _Mode.url;

  @override
  void initState() {
    super.initState();
    final e = widget.edit;
    if (e == null) return;
    _name.text = '${e['name'] ?? ''}';
    if (e['type'] == 'jellyfin') {
      _mode = _Mode.jellyfin;
      _server.text = '${e['server'] ?? ''}';
      _user.text = '${e['user'] ?? ''}';
      _pass.text = '${e['password'] ?? ''}';
    } else if (e['type'] == 'xtream') {
      _mode = _Mode.xtream;
      _server.text = '${e['server'] ?? ''}';
      _user.text = '${e['user'] ?? ''}';
      _pass.text = '${e['password'] ?? ''}';
      _ext = '${e['live_ext'] ?? 'ts'}';
    } else if (e['file'] != null) {
      _mode = _Mode.file;
      _fileName = '${e['file']}';
    } else {
      _mode = _Mode.url;
      _url.text = '${e['url'] ?? ''}';
    }
  }
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

  @override
  void dispose() {
    _lanSub?.cancel();
    _lan?.stop();
    super.dispose();
  }

  Future<void> _gotFile(String name, List<int> bytes) async {
    setState(() => _busy = true);
    final n = await countEntriesAsync(bytes);
    if (!mounted) return;
    setState(() => _busy = false);
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
      // withData: false — le fichier est lu directement depuis le disque (pas de copie géante en mémoire)
      final r = await FilePicker.platform.pickFiles(type: FileType.any, withData: false, allowMultiple: false);
      if (r == null || r.files.isEmpty) return;
      final f = r.files.single;
      setState(() => _busy = true);
      final bytes = f.path != null ? await File(f.path!).readAsBytes() : f.bytes;
      if (bytes == null) throw Exception('fichier illisible');
      await _gotFile(f.name, bytes);
    } catch (e) {
      if (mounted) {
        setState(() => _busy = false);
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
      if (!mounted) return;
      // Panneau dédié (adresse + QR code) : rien n'est coupé en bas de l'écran, même sur une TV.
      final got = await showDialog<Object>(context: context, builder: (_) => LanReceiveDialog(lan: _lan!, address: a));
      await _lan?.stop();
      _lan = null;
      if (!mounted) return;
      if (got is (String, List<int>)) {
        setState(() => _mode = _Mode.file);
        await _gotFile(got.$1, got.$2);
      } else if (got is Map<String, String>) {
        // lien collé sur le téléphone : il arrive dans les champs, l'utilisateur vérifie puis valide
        setState(() {
          _err = null;
          if (got['type'] == 'xtream') {
            _mode = _Mode.xtream;
            _server.text = got['server'] ?? '';
            _user.text = got['user'] ?? '';
            _pass.text = got['password'] ?? '';
          } else {
            _mode = _Mode.url;
            _url.text = got['url'] ?? '';
          }
        });
        toast(context, 'Lien reçu ✓ — vérifiez puis validez.');
      }
    } catch (e) {
      await _lan?.stop();
      _lan = null;
      if (mounted) setState(() => _err = 'Envoi impossible : $e');
    }
  }

  Future<void> _ok() async {
    final s = AppScope.read(context);
    final id = '${widget.edit?['id'] ?? widget.replace?['id'] ?? AppState.newId()}';
    switch (_mode) {
      case _Mode.file:
        final e = widget.edit;
        if (_bytes == null && e != null && e['file'] != null) {
          // modification d'une source « fichier » sans nouveau fichier : on garde la liste actuelle
          Navigator.pop(context, {
            'id': id, 'type': 'm3u', 'name': _name.text.trim().isEmpty ? '${e['name']}' : _name.text.trim(),
            'url': e['url'], 'file': e['file'],
          });
          return;
        }
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
      case _Mode.jellyfin:
        final srv = _server.text.trim();
        if (srv.isEmpty || _user.text.trim().isEmpty) {
          return setState(() => _err = 'Adresse du serveur Jellyfin et identifiant requis.');
        }
        setState(() {
          _busy = true;
          _err = null;
        });
        // vérification immédiate de la connexion : l'erreur s'affiche ici plutôt qu'après l'ajout
        final probe = <String, dynamic>{'server': srv, 'user': _user.text.trim(), 'password': _pass.text, 'device': widget.edit?['device']};
        try {
          final cl = JellyfinClient.of(probe);
          await cl.login();
          if (!mounted) return;
          Navigator.pop(context, {
            'id': id, 'type': 'jellyfin',
            'name': _name.text.trim().isEmpty ? 'Jellyfin' : _name.text.trim(),
            'server': cl.base, 'user': _user.text.trim(), 'password': _pass.text,
            'token': cl.token, 'uid': cl.uid, 'device': cl.deviceId,
          });
        } catch (e) {
          if (mounted) setState(() => _err = e is JellyfinError ? e.message : 'Serveur Jellyfin injoignable : $e');
        } finally {
          if (mounted) setState(() => _busy = false);
        }
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

  Widget _modeChip(_Mode m, IconData ic, String t, {bool autofocus = false}) => OptChip(
        autofocus: autofocus,
        avatar: Icon(ic, size: 18, color: _mode == m ? Colors.white : kInk),
        label: Text(t),
        selected: _mode == m,
        showCheckmark: false,
        onSelected: (_) => setState(() {
          _mode = m;
          _err = null;
        }),
      );

  Widget _bigButton(IconData ic, String title, String sub, VoidCallback onTap) => Padding(
        padding: const EdgeInsets.only(bottom: 10),
        child: FocusCard(
          onTap: _busy ? null : onTap,
            child: Padding(
              padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
              child: Row(children: [
                Icon(ic, color: kAccent, size: 30),
                const SizedBox(width: 14),
                Expanded(
                  child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                    Text(title, style: TextStyle(fontWeight: FontWeight.w700, fontSize: 15.5, color: kInk)),
                    const SizedBox(height: 2),
                    Text(sub, style: TextStyle(color: kMuted, fontSize: 12.5)),
                  ]),
                ),
              ]),
            ),
        ),
      );

  /// Copier-coller depuis le téléphone (QR code) : remplit les champs de ce formulaire.
  Widget _phoneButton() => OutlinedButton.icon(
        onPressed: _busy ? null : _startLan,
        icon: const Icon(Icons.qr_code_2),
        label: const Text('Coller depuis mon téléphone (QR code)'),
      );

  List<Widget> _fileSection() => [
        _bigButton(Icons.folder_open_rounded, 'Choisir un fichier sur cet appareil',
            'Fichier .m3u / .m3u8 (téléchargements, carte SD, clé USB, iCloud…)', _pick),
        _bigButton(Icons.devices_rounded, 'Envoyer depuis un autre appareil',
            'Fichier, lien ou compte Xtream depuis un téléphone ou PC (même Wi-Fi) — idéal pour une TV', _startLan),
        if (_busy)
          Padding(
            padding: EdgeInsets.only(bottom: 10),
            child: LinearProgressIndicator(minHeight: 3, color: kAccent, backgroundColor: kBorder2),
          ),
        if (_bytes == null && widget.edit?['file'] != null)
          Padding(
            padding: const EdgeInsets.only(bottom: 6),
            child: Text('Fichier actuel : ${widget.edit!['file']} (choisissez-en un autre pour le remplacer)',
                style: TextStyle(color: kMuted)),
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
        Text("La liste est copiée dans l'application : elle reste disponible même si le fichier d'origine est "
            'supprimé. Pour la mettre à jour : Paramètres → Sources → « Remplacer le fichier ».',
            style: TextStyle(color: kMuted, fontSize: 12.5)),
      ];

  @override
  Widget build(BuildContext context) {
    final replacing = widget.replace != null;
    final editing = widget.edit != null;
    return AlertDialog(
      title: Text(replacing
          ? 'Remplacer le fichier de « ${widget.replace!['name']} »'
          : editing ? 'Modifier « ${widget.edit!['name']} »' : 'Ajouter une source'),
      content: SizedBox(
        width: 520,
        child: SingleChildScrollView(
          child: Column(mainAxisSize: MainAxisSize.min, crossAxisAlignment: CrossAxisAlignment.start, children: [
            if (!replacing) ...[
              Wrap(spacing: 8, runSpacing: 8, children: [
                _modeChip(_Mode.url, Icons.link_rounded, 'Lien M3U', autofocus: !widget.file),
                _modeChip(_Mode.file, Icons.insert_drive_file_outlined, 'Fichier M3U', autofocus: widget.file),
                _modeChip(_Mode.xtream, Icons.satellite_alt, 'Compte Xtream'),
                _modeChip(_Mode.jellyfin, Icons.home_work_outlined, 'Jellyfin (local)'),
              ]),
              const SizedBox(height: 14),
              TvTextField(controller: _name, label: 'Nom (facultatif)'),
              const SizedBox(height: 10),
            ],
            if (_mode == _Mode.url) ...[
              TvTextField(controller: _url, keyboardType: TextInputType.url, label: 'Lien M3U', hint: 'https://…/playlist.m3u'),
              const SizedBox(height: 8),
              Text('Un lien « get.php?username=…&password=… » est converti automatiquement en compte Xtream '
                  '(TV + films + séries + fiches).', style: TextStyle(color: kMuted, fontSize: 12.5)),
              const SizedBox(height: 8),
              _phoneButton(),
            ] else if (_mode == _Mode.file)
              ..._fileSection()
            else if (_mode == _Mode.jellyfin) ...[
              TvTextField(controller: _server, keyboardType: TextInputType.url, label: 'Adresse du serveur Jellyfin',
                  hint: 'http://192.168.1.20:8096'),
              const SizedBox(height: 10),
              TvTextField(controller: _user, label: 'Utilisateur Jellyfin'),
              const SizedBox(height: 10),
              TvTextField(controller: _pass, obscure: true, label: 'Mot de passe (vide si aucun)'),
              const SizedBox(height: 8),
              if (_busy) LinearProgressIndicator(minHeight: 3, color: kAccent, backgroundColor: kBorder2),
              const SizedBox(height: 6),
              Text('Vos films et séries personnels (disque, NAS…) servis par Jellyfin sur votre réseau. '
                  'Lecture directe du fichier d\'origine, sans conversion.', style: TextStyle(color: kMuted, fontSize: 12.5)),
            ] else ...[
              TvTextField(controller: _server, keyboardType: TextInputType.url, label: 'Serveur', hint: 'http://serveur.exemple.com:8080'),
              const SizedBox(height: 10),
              TvTextField(controller: _user, label: 'Identifiant'),
              const SizedBox(height: 10),
              TvTextField(controller: _pass, obscure: true, label: 'Mot de passe'),
              const SizedBox(height: 10),
              _phoneButton(),
              const SizedBox(height: 8),
              Row(children: [
                Text('Format des chaînes :  ', style: TextStyle(color: kMuted)),
                OptChip(label: const Text('ts'), selected: _ext == 'ts', onSelected: (_) => setState(() => _ext = 'ts')),
                const SizedBox(width: 8),
                OptChip(label: const Text('m3u8'), selected: _ext == 'm3u8', onSelected: (_) => setState(() => _ext = 'm3u8')),
              ]),
            ],
            if (_err != null)
              Padding(padding: const EdgeInsets.only(top: 10), child: Text(_err!, style: const TextStyle(color: Color(0xFFFF6B6B)))),
          ]),
        ),
      ),
      actions: [
        if (editing)
          TextButton(
            onPressed: () async {
              final ok = await showDialog<bool>(
                context: context,
                builder: (c) => AlertDialog(
                  title: Text('Supprimer « ${widget.edit!['name']} » ?'),
                  content: const Text('La source et sa liste enregistrée seront effacées de cet appareil.'),
                  actions: [
                    TextButton(autofocus: true, onPressed: () => Navigator.pop(c, false), child: const Text('Annuler')),
                    FilledButton(onPressed: () => Navigator.pop(c, true), child: const Text('Supprimer')),
                  ],
                ),
              );
              if (ok == true && context.mounted) Navigator.pop(context, {'__delete__': true});
            },
            child: const Text('Supprimer', style: TextStyle(color: Color(0xFFFF8A8A))),
          ),
        TextButton(onPressed: () => Navigator.pop(context), child: const Text('Annuler')),
        FilledButton(
          onPressed: _busy ? null : _ok,
          child: Text(replacing ? 'Remplacer' : editing ? 'Enregistrer' : 'Ajouter'),
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
      // toute la page reste construite : la télécommande peut toujours descendre vers les réglages suivants
      body: ListView(cacheExtent: 6000, padding: EdgeInsets.fromLTRB(pad, 0, pad, 50), children: [
        _h('Sources'),
        for (final src in s.sources)
          Card(
            color: kCard2,
            // La ligne et ses boutons sont côte à côte (et non les boutons DANS la ligne) :
            // à la télécommande, la flèche droite passe de la source à Modifier, Guide TV, Actualiser, Supprimer.
            child: Row(children: [
              Expanded(
                child: ListTile(
                  leading: Icon(src['type'] == 'xtream' ? Icons.satellite_alt : src['type'] == 'jellyfin' ? Icons.home_work_outlined : Icons.playlist_play,
                      color: s.currentSource?['id'] == src['id'] ? kAccent : kMuted),
                  title: Text('${src['name']}'),
                  subtitle: Text(src['type'] == 'xtream' ? 'Compte Xtream Codes' : src['type'] == 'jellyfin' ? 'Jellyfin · ${src['server']}' : (src['file'] != null ? 'Fichier M3U · ${src['file']}' : 'Lien M3U'),
                      style: TextStyle(color: kMuted)),
                  onTap: () => s.setSource('${src['id']}'),
                ),
              ),
              Wrap(children: [
                IconButton(tooltip: 'Modifier', icon: const Icon(Icons.edit_outlined),
                    onPressed: () => showSourceDialog(context, edit: src)),
                if (src['file'] != null)
                  IconButton(tooltip: 'Remplacer le fichier', icon: const Icon(Icons.upload_file),
                      onPressed: () => showSourceDialog(context, replace: src)),
                IconButton(tooltip: 'Guide TV', icon: const Icon(Icons.event_note_outlined),
                    onPressed: () => editGuide(context, src)),
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
                          TextButton(autofocus: true, onPressed: () => Navigator.pop(c, false), child: const Text('Annuler')),
                          FilledButton(onPressed: () => Navigator.pop(c, true), child: const Text('Supprimer')),
                        ],
                      ),
                    );
                    if (ok == true) await s.deleteSource('${src['id']}');
                  },
                ),
              ]),
              const SizedBox(width: 6),
            ]),
          ),
        if (s.sourceInfo.isNotEmpty)
          Padding(padding: const EdgeInsets.only(top: 6), child: Text(s.sourceInfo, style: TextStyle(color: kMuted, fontSize: 12.5))),
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
            style: TextStyle(color: kMuted, height: 1.4)),
        const SizedBox(height: 10),
        TvTextField(controller: _key, obscure: true, label: 'Clé API TMDB'),
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
          Text('Langue des fiches :  ', style: TextStyle(color: kMuted)),
          for (final (code, name) in _langs)
            OptChip(
              label: Text(name),
              selected: s.lang == code,
              showCheckmark: false,
              onSelected: (_) => s.setLang(code),
            ),
        ]),
        _h('Lecture, pré-chargement et téléchargements'),
        Text(
            "Pré-chargement : le film ou l'épisode se télécharge en avance pendant que vous regardez. Si la connexion "
            "ralentit, la lecture continue sur ce qui est déjà chargé ; si elle s'arrête, l'application attend d'avoir "
            "rempli la réserve puis repart sans à-coups. Avec un très petit débit, utilisez plutôt « Télécharger » sur la fiche.",
            style: TextStyle(color: kMuted, height: 1.4)),
        const SizedBox(height: 10),
        Wrap(spacing: 8, runSpacing: 8, crossAxisAlignment: WrapCrossAlignment.center, children: [
          Text('Films et séries :  ', style: TextStyle(color: kMuted)),
          for (final (v, t) in const [(0, 'Désactivé'), (1, "1 min d'avance"), (5, "5 min d'avance"), (10, "10 min d'avance")])
            OptChip(
              label: Text(t), selected: s.bufferMin == v, showCheckmark: false,
              onSelected: (_) => s.setBufferMin(v),
            ),
        ]),
        const SizedBox(height: 8),
        Text("Les films téléchargés sont enregistrés dans l'espace de l'application (visible dans l'app Fichiers sur iPad / iPhone).",
            style: TextStyle(color: kMuted, fontSize: 12.5)),
        const AdvancedSettings(),
        _h('Administration depuis un navigateur'),
        const AdminCard(),
        _h('Maintenance'),
        const MaintenanceCard(),
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
          Expanded(child: Text('$kAppTitle $kAppVersion — conçu par $kAppAuthor', style: TextStyle(color: kMuted))),
        ]),
        const SizedBox(height: 10),
        Text("Ce produit utilise l'API de TMDB mais n'est ni approuvé ni certifié par TMDB. "
            "IPTV Player ne fournit aucun contenu : vous ajoutez votre propre abonnement.",
            style: TextStyle(color: kMuted, fontSize: 12.5)),
        const SizedBox(height: 10),
        const Align(alignment: Alignment.centerLeft, child: Signature(size: 22)),
      ]),
    );
  }
}

/// Réception d'une liste envoyée depuis un téléphone ou un PC : adresse en grand + QR code à scanner.
class LanReceiveDialog extends StatefulWidget {
  final LanImport lan;
  final String address;
  const LanReceiveDialog({super.key, required this.lan, required this.address});
  @override
  State<LanReceiveDialog> createState() => _LanReceiveDialogState();
}

class _LanReceiveDialogState extends State<LanReceiveDialog> {
  StreamSubscription<(String, List<int>)>? _sub;
  StreamSubscription<Map<String, String>>? _sub2;

  @override
  void initState() {
    super.initState();
    _sub = widget.lan.files.listen((f) {
      if (mounted) Navigator.of(context).pop(f);
    });
    _sub2 = widget.lan.links.listen((l) {
      if (mounted) Navigator.of(context).pop(l);
    });
  }

  @override
  void dispose() {
    _sub?.cancel();
    _sub2?.cancel();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final info = Column(mainAxisSize: MainAxisSize.min, crossAxisAlignment: CrossAxisAlignment.start, children: [
      Text('Sur votre téléphone ou PC (même Wi-Fi), scannez le QR code ou ouvrez dans le navigateur :',
          style: TextStyle(color: kMuted, height: 1.35)),
      const SizedBox(height: 10),
      SelectableText(widget.address, style: TextStyle(fontSize: 28, fontWeight: FontWeight.w800, color: kInk)),
      const SizedBox(height: 10),
      Text('puis choisissez le fichier .m3u / .m3u8, ou collez un lien M3U ou un compte Xtream (copier-coller).',
          style: TextStyle(color: kMuted)),
      const SizedBox(height: 14),
      const Row(children: [
        SizedBox(width: 18, height: 18, child: CircularProgressIndicator(strokeWidth: 2, color: kAccent)),
        SizedBox(width: 10),
        Text('En attente du fichier…'),
      ]),
    ]);
    return AlertDialog(
      title: const Text('Envoyer depuis un autre appareil'),
      content: SizedBox(
        width: 640,
        child: LayoutBuilder(
          builder: (c, cons) => cons.maxWidth < 480
              ? SingleChildScrollView(child: Column(children: [info, const SizedBox(height: 14), QrView(widget.address, size: 180)]))
              : Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
                  Expanded(child: info),
                  const SizedBox(width: 18),
                  QrView(widget.address, size: 190),
                ]),
        ),
      ),
      actions: [TextButton(autofocus: true, onPressed: () => Navigator.pop(context), child: const Text('Annuler'))],
    );
  }
}

/// « Mes sources » : utiliser, modifier, actualiser ou supprimer une source (adapté à la télécommande).
Future<void> showSourcesManager(BuildContext context) => showDialog<void>(context: context, builder: (_) => const _SourcesManager());

class _SourcesManager extends StatelessWidget {
  const _SourcesManager();
  @override
  Widget build(BuildContext context) {
    final s = AppScope.of(context);
    final cur = s.currentSource?['id'];
    return AlertDialog(
      title: const Text('Mes sources'),
      content: SizedBox(
        width: 620,
        child: SingleChildScrollView(
          child: Column(mainAxisSize: MainAxisSize.min, children: [
            if (s.sources.isEmpty) Text('Aucune source pour le moment.', style: TextStyle(color: kMuted)),
            for (final src in s.sources)
              Container(
                width: double.infinity,
                margin: const EdgeInsets.only(bottom: 10),
                padding: const EdgeInsets.all(12),
                decoration: BoxDecoration(color: kInk.withValues(alpha: .06), borderRadius: BorderRadius.circular(14)),
                child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                  Text('${src['type'] == 'xtream' ? '📡' : src['type'] == 'jellyfin' ? '🏠' : '📄'}  ${src['name']}${src['id'] == cur ? '   · en cours' : ''}',
                      style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 16)),
                  Text(
                      src['type'] == 'xtream'
                          ? 'Compte Xtream · ${src['server']} · ${src['user']}'
                          : src['file'] != null ? 'Fichier M3U · ${src['file']}' : 'Lien M3U · ${src['url']}',
                      maxLines: 1, overflow: TextOverflow.ellipsis, style: TextStyle(color: kMuted, fontSize: 12.5)),
                  const SizedBox(height: 8),
                  Wrap(spacing: 8, runSpacing: 8, children: [
                    if (src['id'] != cur)
                      OutlinedButton(
                          onPressed: () {
                            s.setSource('${src['id']}');
                            Navigator.pop(context);
                          },
                          child: const Text('Utiliser')),
                    OutlinedButton.icon(
                        onPressed: () => showSourceDialog(context, edit: src),
                        icon: const Icon(Icons.edit_outlined, size: 18),
                        label: const Text('Modifier')),
                    OutlinedButton.icon(
                        onPressed: () {
                          s.setSource('${src['id']}', force: true);
                          toast(context, 'Actualisation de « ${src['name']} »…');
                        },
                        icon: const Icon(Icons.refresh, size: 18),
                        label: const Text('Actualiser')),
                    OutlinedButton.icon(
                        onPressed: () async {
                          final ok = await showDialog<bool>(
                            context: context,
                            builder: (c) => AlertDialog(
                              title: Text('Supprimer « ${src['name']} » ?'),
                              actions: [
                                TextButton(autofocus: true, onPressed: () => Navigator.pop(c, false), child: const Text('Annuler')),
                                FilledButton(onPressed: () => Navigator.pop(c, true), child: const Text('Supprimer')),
                              ],
                            ),
                          );
                          if (ok == true) await s.deleteSource('${src['id']}');
                        },
                        icon: const Icon(Icons.delete_outline, size: 18, color: Color(0xFFFF8A8A)),
                        label: const Text('Supprimer')),
                  ]),
                ]),
              ),
          ]),
        ),
      ),
      actions: [
        TextButton(onPressed: () => showSourceDialog(context), child: const Text('＋ Ajouter une source')),
        FilledButton(autofocus: true, onPressed: () => Navigator.pop(context), child: const Text('Fermer')),
      ],
    );
  }
}
