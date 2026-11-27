// Lecteur vidéo (media_kit / mpv) : direct, films, épisodes, zapping, pistes, reprise.
import 'dart:async';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:media_kit/media_kit.dart';
import 'package:media_kit_video/media_kit_video.dart';

import '../core/channels.dart';
import '../core/jellyfin.dart';
import '../core/models.dart';
import '../core/net.dart';
import '../core/store.dart';
import '../core/text.dart';
import 'scope.dart';
import 'theme.dart';

class PlayerScreen extends StatefulWidget {
  final List<PlayItem> items;
  final int index;
  final bool resume;
  const PlayerScreen({super.key, required this.items, required this.index, this.resume = true});
  @override
  State<PlayerScreen> createState() => _PlayerScreenState();
}

class _PlayerScreenState extends State<PlayerScreen> {
  late final Player _player = Player();
  late final VideoController _ctrl = VideoController(_player);
  late final AppState _s = AppScope.read(context);
  final FocusNode _focus = FocusNode();
  final List<StreamSubscription> _subs = [];
  late int _index = widget.index;
  bool _showUi = true;
  bool _showList = false;
  Timer? _hideT;
  Timer? _saveT;
  Duration _pos = Duration.zero;
  Duration _dur = Duration.zero;
  Duration _buf = Duration.zero;
  bool _localFile = false;
  bool _playing = false;
  bool _buffering = true;
  String _error = '';
  Duration _errAt = Duration.zero;
  Timer? _errT;
  String _epg = '';
  double? _dragValue;
  bool _endedHandled = false;
  // flux en cours (qualité, reconnexions, diagnostic)
  List<Variant> _variants = [];
  int _vidx = 0;
  String _url = '';
  final Set<String> _failed = {};
  int _retries = 0, _reconnects = 0, _stalls = 0;
  DateTime _lastProgress = DateTime.now(), _openTs = DateTime.now(), _lastRecover = DateTime(2000);
  DateTime _stableSince = DateTime.now(), _upgradeTry = DateTime(2000), _upgradeBlock = DateTime(2000);
  Duration _posPrev = Duration.zero;
  int? _zapMs;
  bool _okNoted = false, _gaveUp = false, _hadError = false, _showDiag = false;
  String _status = '';
  Timer? _dogT;
  Map<String, String> _mpv = {};
  (int, double)? _cpuPrev;
  double? _cpuPct;

  PlayItem get _cur => widget.items[_index];
  bool get _live => _cur.kind == 'live';

  @override
  void initState() {
    super.initState();
    SystemChrome.setEnabledSystemUIMode(SystemUiMode.immersiveSticky);
    _subs.addAll([
      _player.stream.position.listen((p) {
        // la vidéo avance : un message d'erreur éventuel n'était qu'un avertissement
        if (_error.isNotEmpty && p > _errAt + const Duration(milliseconds: 800)) _error = '';
        setState(() => _pos = p);
      }),
      _player.stream.duration.listen((d) => setState(() => _dur = d)),
      _player.stream.buffer.listen((b) => _buf = b),
      _player.stream.playing.listen((p) => setState(() => _playing = p)),
      _player.stream.buffering.listen((b) => setState(() => _buffering = b)),
      _player.stream.error.listen(_onError),
      _player.stream.completed.listen((c) {
        if (c) _onEnded();
      }),
    ]);
    _saveT = Timer.periodic(const Duration(seconds: 5), (_) => _saveProgress());
    _dogT = Timer.periodic(const Duration(seconds: 1), (_) => _watchdog());
    _s.playing = true;
    _s.diag = _diagData;
    _open(_index, resume: widget.resume);
    _poke();
  }

  /// mpv signale aussi de simples avertissements (ex. « force-seekable » sur une chaîne en direct) alors que
  /// la vidéo tourne : on n'affiche l'erreur que si la lecture n'avance plus 4 secondes après.
  void _onError(String e) {
    if (e.trim().isEmpty || e.contains('force-seekable') || e.toLowerCase().contains('seek')) return;
    if (_live) {
      _hadError = true; // la surveillance relance ou change de flux
      return;
    }
    final at = _pos;
    _errT?.cancel();
    _errT = Timer(const Duration(seconds: 4), () {
      if (!mounted) return;
      final stuck = _pos <= at + const Duration(milliseconds: 500);
      final v = _variants[_vidx];
      if (stuck && _jfAltFor != v.url && jellyfinIsDirect(v.url)) {
        // format non lu par l'appareil : on redemande le fichier converti par Jellyfin, au même endroit
        _s.log('Jellyfin : lecture directe impossible sur cet appareil ($e) — conversion par le serveur');
        _jfAltFor = v.url;
        _jfAlt = jellyfinTranscodeUrl(v.url);
        _resumeAt = _pos;
        unawaited(_openUrl());
        return;
      }
      if (stuck) {
        setState(() {
          _errAt = _pos;
          _error = e;
        });
      }
    });
  }

  Map<String, String> _headers(PlayItem it) {
    final h = <String, String>{'User-Agent': kUserAgent};
    for (final o in it.opts) {
      final i = o.indexOf('=');
      if (i < 0) continue;
      final k = o.substring(0, i).toLowerCase(), v = o.substring(i + 1);
      if (k == 'http-user-agent') h['User-Agent'] = v;
      if (k == 'http-referrer' || k == 'http-referer') h['Referer'] = v;
      if (k == 'http-origin') h['Origin'] = v;
    }
    return h;
  }

  Future<void> _open(int i, {bool resume = true}) async {
    _saveProgress();
    setState(() {
      _index = i;
      _errT?.cancel();
      _error = '';
      _epg = '';
      _status = '';
      _pos = Duration.zero;
      _dur = Duration.zero;
      _endedHandled = false;
    });
    final it = _cur;
    _s.noteLive(it);
    _failed.clear();
    _retries = _reconnects = _stalls = 0;
    _gaveUp = false;
    _upgradeTry = DateTime(2000);
    _variants = it.variants.isNotEmpty ? it.variants : [Variant(url: it.url, name: it.name, q: qualityOf(it.name, it.group), opts: it.opts)];
    _vidx = _live ? _choose() : 0;
    await _openUrl();
    final pr = _s.progressOf(it.url);
    if (resume && !_live && pr != null && pr['done'] != true && ((pr['pos'] as num?) ?? 0) > 30000) {
      final target = Duration(milliseconds: (pr['pos'] as num).toInt());
      try {
        await _player.stream.duration.firstWhere((d) => d > Duration.zero).timeout(const Duration(seconds: 25));
        await _player.seek(target);
      } catch (_) {}
    }
    if (_live) {
      final progs = await _s.epgFor(it);
      if (mounted && progs.isNotEmpty && _cur.url == it.url) {
        String hm(dynamic ts) => ts is int ? fmtHm(DateTime.fromMillisecondsSinceEpoch(ts * 1000)) : '';
        final now = progs.first;
        var t = 'Maintenant : ${now['title']}  (${hm(now['start_ts'])}–${hm(now['stop_ts'])})';
        if (progs.length > 1) t += '   ·   Ensuite : ${progs[1]['title']} (${hm(progs[1]['start_ts'])})';
        setState(() => _epg = t);
      }
    }
  }

  // ---------------------------------------------------------------- qualité et flux
  String get _ckey => _cur.ckey.isNotEmpty ? _cur.ckey : _cur.url;

  int _cap({bool withDegrade = true}) {
    final mr = '${_s.pset['max_res'] ?? 'auto'}';
    int cap;
    if (kQCodes.containsKey(mr)) {
      cap = kQCodes[mr]!;
    } else {
      final v = View.of(context);
      final px = v.physicalSize.shortestSide;
      cap = px >= 1800 ? 4 : 3;
    }
    if (_s.hwTier == 'low') cap = cap > 3 ? 3 : cap;
    final nc = networkCap((_s.cfg['bw_peak'] as num?) ?? 0);
    if (nc != null) cap = cap < (nc < 2 ? 2 : nc) ? cap : (nc < 2 ? 2 : nc);
    final d = withDegrade ? _s.degraded[_ckey] : null;
    if (d != null && DateTime.now().difference(d.$2).inMinutes < 15) cap = cap < d.$1 ? cap : d.$1;
    return cap;
  }

  int _choose({int? below}) {
    final pref = '${(_s.cfg['ch_quality'] as Map)[_ckey] ?? _s.pset['quality'] ?? 'auto'}';
    return pickVariant(_variants, pref: pref, cap: _cap(), stats: _s.stats, exclude: _failed, below: below);
  }

  // lien converti utilisé à la place du lien direct (pour ce lien-là seulement) et position de reprise
  String? _jfAlt, _jfAltFor;
  Duration? _resumeAt;

  Future<void> _openUrl() async {
    final it = _cur;
    final v = _variants[_vidx];
    final useAlt = _jfAlt != null && _jfAltFor == v.url;
    final playUrl = useAlt ? _jfAlt! : v.url;
    _url = v.url;
    _okNoted = false;
    _hadError = false;
    _zapMs = null;
    _openTs = _lastProgress = DateTime.now();
    _posPrev = Duration.zero;
    final local = _live ? null : _s.downloads.localFile(it.url);
    _localFile = local != null;
    await _applyProps(local != null, jellyfin: local == null && (jellyfinIsDirect(v.url) || useAlt));
    final probe = PlayItem(name: it.name, url: v.url, kind: it.kind, opts: v.opts);
    await _player.open(local != null ? Media(local) : Media(playUrl, httpHeaders: _headers(probe)), play: true);
    if (mounted) setState(() {});
  }

  /// Réglages mpv : mémoire tampon du profil, image, son, désentrelacement, HDR.
  Future<void> _applyProps(bool local, {bool jellyfin = false}) async {
    final p = _player.platform as dynamic;
    Future<void> set(String k, String v) async {
      try {
        await p.setProperty(k, v);
      } catch (_) {}
    }

    final st = _s.pset;
    final prof = _s.prof;
    await set('hwdec', st['hwdec'] == false ? 'no' : 'auto-safe');
    await set('deinterlace', {'on': 'yes', 'off': 'no'}[st['deinterlace']] ?? 'auto');
    await set('target-colorspace-hint', st['hdr'] == 'sdr' ? 'no' : 'yes');
    if (st['hdr'] == 'sdr') await set('tone-mapping', 'auto');
    await set('video-sync', st['refresh'] == 'auto' ? 'display-resample' : 'audio');
    final a = '${st['a_lang'] ?? 'fr'}';
    if (kLang3.containsKey(a)) await set('alang', kLang3[a]!);
    final sl = '${st['s_lang'] ?? 'off'}';
    if (sl == 'off') {
      await set('sid', 'no');
    } else {
      await set('slang', kLang3[sl == 'auto' ? a : sl] ?? 'fr');
      await set('sid', 'auto');
    }
    await set('af', st['normalize'] == true ? 'lavfi=[dynaudnorm=f=250:g=15]' : '');
    await set('audio-spdif', st['passthrough'] == true ? 'ac3,eac3,dts,dts-hd,truehd' : '');
    if (st['max_res'] == 'sd') await set('hls-bitrate', 'min');
    await _applyLive();
    // reprise au même endroit après un changement de lien (repli Jellyfin), sinon début normal
    final ra = _resumeAt;
    _resumeAt = null;
    await set('start', ra != null && ra.inSeconds > 2 ? '${ra.inSeconds}' : 'none');
    if (local) {
      await set('cache', 'no');
      await set('cache-pause-initial', 'no');
      return;
    }
    await set('cache', 'yes');
    // autorise l'avance / le retour dans la mémoire tampon, même sur les flux qui ne le déclarent pas
    await set('force-seekable', 'yes');
    await set('network-timeout', '${prof.stallTimeout + 5}');
    await set('stream-lavf-o', 'reconnect=1,reconnect_streamed=1,reconnect_delay_max=4');
    if (jellyfin) {
      // Jellyfin (réseau local) : grosse réserve sur disque remplie à pleine vitesse du réseau maison,
      // démarrage après 3 s seulement — plus de saccades même sur les fichiers 4K à fort débit.
      final low = _s.hwTier == 'low' || (_s.sys.totalMb > 0 && _s.sys.totalMb < 2500);
      await set('cache-on-disk', 'yes');
      await set('cache-dir', (await _cacheDir()).path);
      await set('cache-secs', '900');
      await set('demuxer-readahead-secs', '900');
      await set('demuxer-max-bytes', low ? '512MiB' : '1024MiB');
      await set('demuxer-max-back-bytes', low ? '64MiB' : '160MiB');
      await set('stream-buffer-size', '4MiB');
      await set('network-timeout', '30');
      await set('cache-pause-initial', 'yes');
      await set('cache-pause-wait', '3');
      return;
    }
    if (_live) {
      final secs = prof.liveCache;
      await set('cache-on-disk', 'no');
      await set('cache-secs', '$secs');
      await set('demuxer-readahead-secs', '$secs');
      await set('demuxer-max-bytes', '120MiB');
      await set('cache-pause-initial', secs > 3 ? 'yes' : 'no');
      await set('cache-pause-wait', '${secs > 3 ? secs : 1}');
      return;
    }
    final mins = _s.bufferMin;
    if (mins > 0) {
      await set('cache-on-disk', 'yes');
      await set('cache-dir', (await _cacheDir()).path);
      await set('cache-secs', '${mins * 60}');
      await set('demuxer-readahead-secs', '${mins * 60}');
      await set('demuxer-max-bytes', '${mins * 160}MiB');
      await set('demuxer-max-back-bytes', '60MiB');
      await set('cache-pause-initial', 'yes');
      await set('cache-pause-wait', '${mins * 60 < 60 ? mins * 60 : 60}');
    } else {
      await set('cache-on-disk', 'no');
      await set('cache-secs', '${prof.vodCache}');
      await set('demuxer-readahead-secs', '${prof.vodCache}');
      await set('demuxer-max-bytes', '150MiB');
      await set('cache-pause-initial', 'no');
      await set('cache-pause-wait', '1');
    }
  }

  /// Réglages applicables en direct (image, format, synchronisation du son).
  Future<void> _applyLive() async {
    final p = _player.platform as dynamic;
    Future<void> set(String k, String v) async {
      try {
        await p.setProperty(k, v);
      } catch (_) {}
    }

    final st = _s.pset;
    for (final k in ['brightness', 'contrast', 'saturation']) {
      await set(k, '${(st[k] as num? ?? 0).toInt()}');
    }
    final sharp = (st['sharpness'] as num? ?? 0).toInt();
    await set('vf', sharp > 0 ? 'lavfi=[unsharp=5:5:${(sharp / 50).toStringAsFixed(2)}]' : '');
    final asp = '${st['aspect'] ?? 'auto'}';
    await set('keepaspect', asp == 'stretch' ? 'no' : 'yes');
    await set('panscan', asp == 'fill' ? '1.0' : '0.0');
    await set('video-aspect-override', ['16:9', '4:3', '21:9'].contains(asp) ? asp : '-1');
    await set('audio-delay', ((st['av_delay'] as num? ?? 0) / 1000).toStringAsFixed(3));
  }

  // ---------------------------------------------------------------- anti-freeze
  void _watchdog() {
    if (!mounted || _url.isEmpty || _gaveUp) return;
    final now = DateTime.now();
    final moving = _pos != _posPrev && _pos > Duration.zero;
    _posPrev = _pos;
    if (moving) {
      if (_zapMs == null) {
        _zapMs = now.difference(_openTs).inMilliseconds;
        _stableSince = now;
      }
      _lastProgress = now;
      if (!_okNoted && now.difference(_openTs).inSeconds > 20) {
        _okNoted = true;
        _retries = 0;
        _s.stats.ok(_url);
      }
    }
    if (_showDiag || _s.admin?.running == true) _pollDiag();
    if (!_live) return;
    if (!_playing && !_buffering && !_hadError) {
      _lastProgress = now; // pause volontaire
      return;
    }
    final prof = _s.prof;
    final stuck = _hadError || now.difference(_lastProgress).inSeconds > prof.stallTimeout;
    if (stuck && now.difference(_lastRecover).inSeconds > 3) {
      _recover(_hadError ? 'erreur' : 'blocage', prof);
      return;
    }
    // retour à une meilleure qualité après 5 minutes stables
    final manual = (_s.cfg['ch_quality'] as Map)[_ckey] != null;
    if (_s.pset['upgrade'] != false && _variants.length > 1 && moving && !manual && _s.pset['quality'] == 'auto' &&
        now.isAfter(_upgradeBlock) && now.difference(_stableSince).inSeconds > 300 && now.difference(_lastRecover).inSeconds > 300) {
      final best = pickVariant(_variants, cap: _cap(withDegrade: false), stats: _s.stats, exclude: _failed);
      int eff(int i) => _variants[i].q == 0 ? 2 : _variants[i].q;
      if (eff(best) > eff(_vidx)) {
        _s.degraded.remove(_ckey);
        _upgradeTry = now;
        _stableSince = now;
        _s.log('Connexion stable : retour en ${kQLabels[_variants[best].q]} sur ${_cur.name}');
        _vidx = best;
        _openUrl();
      }
    }
  }

  void _recover(String why, Prof prof) {
    final now = DateTime.now();
    _lastRecover = now;
    _stalls++;
    if (why == 'erreur') {
      _s.stats.fail(_url);
    } else {
      _s.stats.stall(_url);
      if (prof.mode == 'auto') _s.log('Profil AUTO : mémoire tampon portée à ${autoCacheAfterStall(_s.cfg)} s');
    }
    final upgradedRecently = now.difference(_upgradeTry).inSeconds < 45;
    if (upgradedRecently) {
      _upgradeBlock = now.add(const Duration(minutes: 15));
      _upgradeTry = DateTime(2000);
    }
    if (_retries < prof.maxRetries && !upgradedRecently) {
      _retries++;
      _reconnects++;
      setState(() => _status = '⟳ Reconnexion ($_retries/${prof.maxRetries})…');
      _s.log('${why[0].toUpperCase()}${why.substring(1)} sur ${_cur.name} : reconnexion $_retries');
      _openUrl();
      return;
    }
    if (prof.fallback && _variants.length > 1) {
      _failed.add(_url);
      final curq = _variants[_vidx].q == 0 ? 2 : _variants[_vidx].q;
      final nxt = pickVariant(_variants, stats: _s.stats, exclude: _failed, below: why == 'blocage' ? curq : null);
      if (!_failed.contains(_variants[nxt].url)) {
        _s.degraded[_ckey] = (_variants[nxt].q == 0 ? 1 : _variants[nxt].q, now);
        _vidx = nxt;
        _retries = 0;
        final lab = (kQLabels[_variants[nxt].q] ?? '').isEmpty ? 'autre flux' : kQLabels[_variants[nxt].q]!;
        setState(() => _status = '⇩ Bascule vers $lab (flux ${nxt + 1}/${_variants.length})');
        _s.log('${why[0].toUpperCase()}${why.substring(1)} sur ${_cur.name} : bascule vers $lab');
        _openUrl();
        return;
      }
    }
    _gaveUp = true;
    setState(() => _status = '⚠ Chaîne indisponible pour le moment (tous les flux ont échoué).');
    _s.log('${_cur.name} : tous les flux ont échoué');
  }

  // ---------------------------------------------------------------- diagnostic
  Future<void> _pollDiag() async {
    final p = _player.platform as dynamic;
    final out = <String, String>{};
    for (final k in [
      'video-params/w', 'video-params/h', 'video-codec', 'audio-codec-name', 'estimated-vf-fps', 'container-fps',
      'video-bitrate', 'demuxer-cache-duration', 'cache-speed', 'frame-drop-count', 'decoder-frame-drop-count',
      'hwdec-current', 'video-params/gamma',
    ]) {
      try {
        out[k] = '${await p.getProperty(k)}';
      } catch (_) {}
    }
    final speed = double.tryParse(out['cache-speed'] ?? '') ?? 0;
    final peak = (_s.cfg['bw_peak'] as num?)?.toDouble() ?? 0;
    if (speed > 0 && (speed > peak * 0.98 || DateTime.now().difference(_openTs).inSeconds < 8)) {
      _s.cfg['bw_peak'] = DateTime.now().difference(_openTs).inSeconds < 8 ? (speed > peak * 0.9 ? speed : peak * 0.9).round() : speed.round();
    }
    try {
      if (Platform.isAndroid || Platform.isLinux) {
        final f = File('/proc/self/stat').readAsStringSync();
        final parts = f.substring(f.lastIndexOf(')') + 2).split(' ');
        final ticks = int.parse(parts[11]) + int.parse(parts[12]);
        final t = DateTime.now().millisecondsSinceEpoch / 1000;
        if (_cpuPrev != null) {
          _cpuPct = (ticks - _cpuPrev!.$1) / 100 / (t - _cpuPrev!.$2) / Platform.numberOfProcessors * 100;
        }
        _cpuPrev = (ticks, t);
      }
    } catch (_) {}
    _mpv = out;
    if (_showDiag && mounted) setState(() {});
  }

  Map<String, dynamic> _diagData() {
    final m = _mpv;
    final v = _variants.isEmpty ? null : _variants[_vidx];
    final prof = _s.prof;
    double n(String k) => double.tryParse(m[k] ?? '') ?? 0;
    final w = m['video-params/w'] ?? '', h = m['video-params/h'] ?? '';
    final fps = n('estimated-vf-fps') > 0 ? n('estimated-vf-fps') : n('container-fps');
    final gamma = m['video-params/gamma'] ?? '';
    final avail = _variants.map((x) => (kQLabels[x.q] ?? '').isEmpty ? 'std' : kQLabels[x.q]!).toSet().join(' / ');
    final row = _s.stats.row(_url);
    final peak = (_s.cfg['bw_peak'] as num?)?.toDouble() ?? 0;
    return {
      'état': _gaveUp ? 'indisponible' : _buffering ? 'mise en mémoire' : _playing ? 'lecture' : 'pause',
      'chaîne': _cur.name,
      'résolution': w.isNotEmpty && w != 'null' ? '$w × $h' : '—',
      'qualité': '${(kQLabels[v?.q] ?? '').isEmpty ? 'standard' : kQLabels[v?.q]}${_variants.length > 1 ? '  (disponibles : $avail)' : ''}',
      'codecs': 'vidéo ${m['video-codec'] ?? '—'} · audio ${m['audio-codec-name'] ?? '—'}',
      'images/s': fps > 0 ? fps.toStringAsFixed(2) : '—',
      'HDR': gamma == 'pq' || gamma == 'hlg' ? 'oui ($gamma)' : 'non',
      'décodage': (m['hwdec-current'] ?? '').isEmpty || m['hwdec-current'] == 'no' ? 'logiciel' : 'matériel (${m['hwdec-current']})',
      'débit': n('video-bitrate') > 0 ? '${(n('video-bitrate') / 1e6).toStringAsFixed(2)} Mbit/s' : '—',
      'connexion (pointe)': peak > 0 ? '${(peak * 8 / 1e6).toStringAsFixed(1)} Mbit/s' : '—',
      'mémoire tampon': '${n('demuxer-cache-duration').toStringAsFixed(1)} s / ${_live ? prof.liveCache : prof.vodCache} s (profil ${prof.mode})',
      'latence de zapping': _zapMs == null ? '…' : '$_zapMs ms',
      'images perdues': '${m['frame-drop-count'] ?? '0'} (décodeur ${m['decoder-frame-drop-count'] ?? '0'})',
      'processeur': _cpuPct == null ? '—' : '${_cpuPct!.toStringAsFixed(0)} %',
      'mémoire': '${(ProcessInfo.currentRss / 1048576).toStringAsFixed(0)} Mo',
      'coupures / reconnexions': '$_stalls / $_reconnects',
      'flux': '${_vidx + 1}/${_variants.length} · ${Uri.tryParse(_url)?.host ?? ''} · fiabilité ${row[0]} ok / ${row[1]} échecs / ${row[2]} coupures',
      if (_failed.isNotEmpty) 'flux en échec': '${_failed.length}',
    };
  }

  // ---------------------------------------------------------------- menus
  Future<void> _pickQuality() async {
    final cur = (_s.cfg['ch_quality'] as Map)[_ckey];
    await showModalBottomSheet(
      context: context,
      backgroundColor: const Color(0xFF161A23),
      builder: (c) => SafeArea(
        child: ListView(shrinkWrap: true, children: [
          const Padding(
            padding: EdgeInsets.all(16),
            child: Text('Qualité', style: TextStyle(fontSize: 18, fontWeight: FontWeight.w800)),
          ),
          ListTile(
            autofocus: true,
            selected: cur == null,
            selectedColor: kAccent,
            title: const Text('AUTO (meilleure qualité possible)'),
            onTap: () {
              Navigator.pop(c);
              (_s.cfg['ch_quality'] as Map).remove(_ckey);
              _s.degraded.remove(_ckey);
              _s.save();
              _vidx = _choose();
              _openUrl();
            },
          ),
          for (var i = 0; i < _variants.length; i++)
            ListTile(
              selected: i == _vidx,
              selectedColor: kAccent,
              title: Text('${(kQLabels[_variants[i].q] ?? '').isEmpty ? 'Standard' : kQLabels[_variants[i].q]}'
                  '${_s.stats.dead(_variants[i].url) ? '  · indisponible' : ''}'),
              subtitle: Text(Uri.tryParse(_variants[i].url)?.host ?? '', style: const TextStyle(color: kMuted)),
              onTap: () {
                Navigator.pop(c);
                final code = kQCodes.entries.where((e) => e.value == _variants[i].q).firstOrNull?.key;
                if (code != null) (_s.cfg['ch_quality'] as Map)[_ckey] = code;
                _failed.remove(_variants[i].url);
                _gaveUp = false;
                _s.save();
                _vidx = i;
                _openUrl();
              },
            ),
          if (_variants.length <= 1)
            const ListTile(enabled: false, title: Text('Une seule qualité disponible pour cette chaîne')),
        ]),
      ),
    );
  }

  Future<void> _tune() async {
    await showModalBottomSheet(
      context: context,
      isScrollControlled: true,
      backgroundColor: const Color(0xFF161A23),
      builder: (c) => StatefulBuilder(builder: (c, setSt) {
        void put(String k, dynamic v) {
          _s.setSetting(k, v);
          setSt(() {});
          _applyLive();
        }

        Widget slider(String k) {
          final st = kSettingByKey[k]!;
          return Row(children: [
            SizedBox(width: 110, child: Text(st.label)),
            Expanded(
              child: Slider(
                min: st.lo.toDouble(), max: st.hi.toDouble(), divisions: (st.hi - st.lo).toInt() ~/ 5,
                value: ((_s.pset[k] as num?) ?? 0).toDouble().clamp(st.lo.toDouble(), st.hi.toDouble()),
                label: '${_s.pset[k]}',
                onChanged: (v) => put(k, v.round()),
              ),
            ),
          ]);
        }

        Widget choice(String k) {
          final st = kSettingByKey[k]!;
          return Padding(
            padding: const EdgeInsets.only(top: 8),
            child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Text(st.label, style: const TextStyle(color: kMuted)),
              const SizedBox(height: 6),
              Wrap(spacing: 8, runSpacing: 8, children: [
                for (final (code, lab) in st.choices)
                  ChoiceChip(
                    label: Text(lab),
                    selected: _s.pset[k] == code,
                    showCheckmark: false,
                    onSelected: (_) => put(k, code),
                  ),
              ]),
            ]),
          );
        }

        return SafeArea(
          child: Padding(
            padding: const EdgeInsets.fromLTRB(18, 14, 18, 18),
            child: SingleChildScrollView(
              child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                const Text('Image et son', style: TextStyle(fontSize: 18, fontWeight: FontWeight.w800)),
                const SizedBox(height: 8),
                for (final k in ['brightness', 'contrast', 'saturation', 'sharpness']) slider(k),
                choice('aspect'),
                choice('deinterlace'),
                Row(children: [
                  const SizedBox(width: 110, child: Text('Décalage du son')),
                  IconButton(onPressed: () => put('av_delay', ((_s.pset['av_delay'] as num?) ?? 0) - 50), icon: const Icon(Icons.remove)),
                  Text('${_s.pset['av_delay']} ms'),
                  IconButton(onPressed: () => put('av_delay', ((_s.pset['av_delay'] as num?) ?? 0) + 50), icon: const Icon(Icons.add)),
                ]),
                SwitchListTile(
                  contentPadding: EdgeInsets.zero,
                  title: const Text('Normaliser le volume'),
                  value: _s.pset['normalize'] == true,
                  onChanged: (v) {
                    put('normalize', v);
                    _applyProps(_localFile);
                  },
                ),
                const SizedBox(height: 6),
                Row(children: [
                  TextButton(
                    onPressed: () {
                      for (final k in ['brightness', 'contrast', 'saturation', 'sharpness', 'av_delay']) {
                        _s.pset[k] = 0;
                      }
                      _s.pset['aspect'] = 'auto';
                      _s.save();
                      setSt(() {});
                      _applyLive();
                    },
                    child: const Text('Réinitialiser'),
                  ),
                  const Spacer(),
                  FilledButton(onPressed: () => Navigator.pop(c), child: const Text('Fermer')),
                ]),
              ]),
            ),
          ),
        );
      }),
    );
  }

  Future<Directory> _cacheDir() async {
    final d = Directory('${_s.dataDir.path}/tampon');
    await d.create(recursive: true);
    return d;
  }

  String get _bufText {
    if (_localFile) return '✓ Fichier téléchargé (hors ligne)';
    if (_live || _s.bufferMin == 0 || _dur <= Duration.zero) return '';
    final ahead = _buf - _pos;
    if (_buf >= _dur - const Duration(seconds: 2)) return '⬇ Entièrement chargé';
    return ahead > Duration.zero ? "⬇ ${fmtMs(ahead.inMilliseconds)} d'avance" : '';
  }

  void _saveProgress() {
    if (_live || _dur <= Duration.zero || _pos <= Duration.zero) return;
    _s.saveProgress(_cur, _pos.inMilliseconds, _dur.inMilliseconds);
  }

  void _onEnded() {
    if (_endedHandled || _live) return;
    _endedHandled = true;
    if (_dur > Duration.zero) _s.saveProgress(_cur, _dur.inMilliseconds, _dur.inMilliseconds);
    if (_index < widget.items.length - 1) {
      Future.delayed(const Duration(milliseconds: 800), () {
        if (mounted) _open(_index + 1);
      });
    }
  }

  void _poke() {
    setState(() => _showUi = true);
    _hideT?.cancel();
    _hideT = Timer(const Duration(seconds: 4), () {
      if (mounted && _playing && !_showList) setState(() => _showUi = false);
    });
  }

  void _seekRel(int secs) {
    if (_live || _dur <= Duration.zero) return;
    var t = _pos + Duration(seconds: secs);
    if (t < Duration.zero) t = Duration.zero;
    if (t > _dur) t = _dur;
    _player.seek(t);
    _poke();
  }

  void _prev() {
    if (_index > 0) _open(_index - 1);
  }

  void _next() {
    if (_index < widget.items.length - 1) _open(_index + 1);
  }

  KeyEventResult _onKey(FocusNode n, KeyEvent e) {
    if (e is! KeyDownEvent && e is! KeyRepeatEvent) return KeyEventResult.ignored;
    final k = e.logicalKey;
    if (!_showUi && k != LogicalKeyboardKey.goBack && k != LogicalKeyboardKey.escape) {
      if (_live && (k == LogicalKeyboardKey.arrowUp || k == LogicalKeyboardKey.channelUp)) {
        _prev();
        return KeyEventResult.handled;
      }
      if (_live && (k == LogicalKeyboardKey.arrowDown || k == LogicalKeyboardKey.channelDown)) {
        _next();
        return KeyEventResult.handled;
      }
      if (!_live && k == LogicalKeyboardKey.arrowLeft) {
        _seekRel(-10);
        return KeyEventResult.handled;
      }
      if (!_live && k == LogicalKeyboardKey.arrowRight) {
        _seekRel(30);
        return KeyEventResult.handled;
      }
      _poke();
      return KeyEventResult.handled;
    }
    if (k == LogicalKeyboardKey.mediaPlayPause || k == LogicalKeyboardKey.space) {
      _player.playOrPause();
      _poke();
      return KeyEventResult.handled;
    }
    if (k == LogicalKeyboardKey.channelUp) {
      _prev();
      return KeyEventResult.handled;
    }
    if (k == LogicalKeyboardKey.info || k == LogicalKeyboardKey.keyI) {
      setState(() => _showDiag = !_showDiag);
      return KeyEventResult.handled;
    }
    if (k == LogicalKeyboardKey.channelDown) {
      _next();
      return KeyEventResult.handled;
    }
    _poke();
    return KeyEventResult.ignored;
  }

  Future<void> _pickTrack(bool audio) async {
    final tracks = _player.state.tracks;
    final cur = _player.state.track;
    final list = audio ? tracks.audio : tracks.subtitle;
    await showModalBottomSheet(
      context: context,
      backgroundColor: const Color(0xFF161A23),
      builder: (c) => SafeArea(
        child: ListView(shrinkWrap: true, children: [
          Padding(
            padding: const EdgeInsets.all(16),
            child: Text(audio ? 'Langue audio' : 'Sous-titres', style: const TextStyle(fontSize: 18, fontWeight: FontWeight.w800)),
          ),
          for (final t in list)
            ListTile(
              selected: audio ? t == cur.audio : t == cur.subtitle,
              selectedColor: kAccent,
              title: Text(_trackName(t)),
              onTap: () {
                if (t is AudioTrack) _player.setAudioTrack(t);
                if (t is SubtitleTrack) _player.setSubtitleTrack(t);
                Navigator.pop(c);
              },
            ),
        ]),
      ),
    );
  }

  String _trackName(dynamic t) {
    final id = '${t.id}';
    if (id == 'auto') return 'Automatique';
    if (id == 'no') return 'Désactivés';
    final parts = ['${t.title ?? ''}', '${t.language ?? ''}'].where((e) => e.isNotEmpty && e != 'null').toList();
    return parts.isEmpty ? 'Piste $id' : parts.join(' · ');
  }

  @override
  void dispose() {
    _saveProgress();
    _hideT?.cancel();
    _saveT?.cancel();
    _errT?.cancel();
    _dogT?.cancel();
    _s.playing = false;
    _s.diag = null;
    for (final s in _subs) {
      s.cancel();
    }
    _player.dispose();
    _focus.dispose();
    SystemChrome.setEnabledSystemUIMode(SystemUiMode.edgeToEdge);
    WidgetsBinding.instance.addPostFrameCallback((_) => _s.touch());
    super.dispose();
  }

  Widget _btn(IconData icon, VoidCallback? onTap, {double size = 30, String? tip}) => IconButton(
        tooltip: tip,
        iconSize: size,
        color: Colors.white,
        disabledColor: Colors.white24,
        focusColor: kAccent.withValues(alpha: .35),
        onPressed: onTap == null
            ? null
            : () {
                onTap();
                _poke();
              },
        icon: Icon(icon),
      );

  @override
  Widget build(BuildContext context) {
    final it = _cur;
    final s = it.series;
    final title = it.name;
    final subtitle = _status.isNotEmpty
        ? _status
        : _epg.isNotEmpty ? _epg : (s != null ? 'Saison ${s['season']} · Épisode ${s['num']}' : prettyGroup(it.group));
    final durMs = _dur.inMilliseconds;
    final posMs = _pos.inMilliseconds < 0 ? 0 : (_pos.inMilliseconds > durMs && durMs > 0 ? durMs : _pos.inMilliseconds);
    return Focus(
      focusNode: _focus,
      autofocus: true,
      onKeyEvent: _onKey,
      child: Scaffold(
        backgroundColor: Colors.black,
        body: GestureDetector(
          behavior: HitTestBehavior.opaque,
          onTap: () => _showUi ? setState(() => _showUi = false) : _poke(),
          onDoubleTapDown: (d) {
            if (_live) return;
            final w = MediaQuery.sizeOf(context).width;
            _seekRel(d.localPosition.dx < w / 2 ? -10 : 10);
          },
          child: Stack(fit: StackFit.expand, children: [
            Video(controller: _ctrl, controls: NoVideoControls, fill: Colors.black),
            if (_buffering && _error.isEmpty) const Center(child: CircularProgressIndicator(color: kAccent)),
            if (_error.isNotEmpty)
              Center(
                child: Container(
                  padding: const EdgeInsets.all(16),
                  margin: const EdgeInsets.all(30),
                  decoration: BoxDecoration(color: const Color(0xCC161A23), borderRadius: BorderRadius.circular(12)),
                  child: Text('⚠  Impossible de lire ce flux.\n$_error', textAlign: TextAlign.center),
                ),
              ),
            AnimatedOpacity(
              opacity: _showUi ? 1 : 0,
              duration: const Duration(milliseconds: 220),
              child: IgnorePointer(
                ignoring: !_showUi,
                child: Stack(fit: StackFit.expand, children: [
                  const DecoratedBox(
                    decoration: BoxDecoration(
                      gradient: LinearGradient(
                        begin: Alignment.topCenter, end: Alignment.bottomCenter,
                        colors: [Color(0xCC000000), Color(0x00000000), Color(0x00000000), Color(0xDD000000)],
                        stops: [0, .25, .65, 1],
                      ),
                    ),
                  ),
                  SafeArea(
                    child: Column(children: [
                      Row(children: [
                        _btn(Icons.arrow_back, () => Navigator.of(context).maybePop(), size: 26, tip: 'Retour'),
                        const SizedBox(width: 6),
                        Expanded(
                          child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                            Text(title, maxLines: 1, overflow: TextOverflow.ellipsis,
                                style: const TextStyle(fontSize: 18, fontWeight: FontWeight.w800)),
                            Text(subtitle, maxLines: 1, overflow: TextOverflow.ellipsis, style: const TextStyle(color: kMuted, fontSize: 13)),
                          ]),
                        ),
                        if (_live) const Padding(padding: EdgeInsets.symmetric(horizontal: 8), child: Text('● EN DIRECT',
                            style: TextStyle(color: Color(0xFFFF4D5E), fontWeight: FontWeight.w900, fontSize: 12))),
                        if (widget.items.length > 1)
                          _btn(Icons.list, () => setState(() => _showList = !_showList), size: 26,
                              tip: _live ? 'Chaînes' : 'Épisodes'),
                      ]),
                      const Spacer(),
                      Row(mainAxisAlignment: MainAxisAlignment.center, children: [
                        _btn(Icons.skip_previous, _index > 0 ? _prev : null, size: 34, tip: 'Précédent'),
                        if (!_live) _btn(Icons.replay_10, () => _seekRel(-10), size: 34),
                        const SizedBox(width: 10),
                        Container(
                          decoration: const BoxDecoration(color: Colors.white, shape: BoxShape.circle),
                          child: IconButton(
                            autofocus: true,
                            iconSize: 38,
                            color: kBg,
                            onPressed: () {
                              _player.playOrPause();
                              _poke();
                            },
                            icon: Icon(_playing ? Icons.pause : Icons.play_arrow),
                          ),
                        ),
                        const SizedBox(width: 10),
                        if (!_live) _btn(Icons.forward_30, () => _seekRel(30), size: 34),
                        _btn(Icons.skip_next, _index < widget.items.length - 1 ? _next : null, size: 34, tip: 'Suivant'),
                      ]),
                      const Spacer(),
                      Padding(
                        padding: const EdgeInsets.symmetric(horizontal: 12),
                        child: Row(children: [
                          if (!_live && durMs > 0) ...[
                            Text(fmtMs(_dragValue?.toInt() ?? posMs), style: const TextStyle(fontSize: 12)),
                            Expanded(
                              child: SliderTheme(
                                data: SliderTheme.of(context).copyWith(
                                  activeTrackColor: kAccent, inactiveTrackColor: Colors.white24, thumbColor: Colors.white,
                                  trackHeight: 3, overlayShape: SliderComponentShape.noOverlay,
                                ),
                                child: Slider(
                                  min: 0,
                                  max: durMs.toDouble(),
                                  value: clampD(_dragValue ?? posMs.toDouble(), 0, durMs.toDouble()),
                                  onChanged: (v) => setState(() => _dragValue = v),
                                  onChangeEnd: (v) {
                                    _player.seek(Duration(milliseconds: v.toInt()));
                                    setState(() => _dragValue = null);
                                    _poke();
                                  },
                                ),
                              ),
                            ),
                            Text(fmtMs(durMs), style: const TextStyle(fontSize: 12)),
                          ] else
                            const Spacer(),
                          if (_bufText.isNotEmpty)
                            Padding(
                              padding: const EdgeInsets.symmetric(horizontal: 8),
                              child: Text(_bufText, style: const TextStyle(color: Color(0xFFB9C6DA), fontSize: 12, fontWeight: FontWeight.w600)),
                            ),
                          if (_live)
                            TextButton.icon(
                              onPressed: () {
                                _pickQuality();
                                _poke();
                              },
                              icon: const Icon(Icons.hd_outlined, color: Colors.white),
                              label: Text(
                                  (kQLabels[_variants.isEmpty ? 0 : _variants[_vidx].q] ?? '').isEmpty
                                      ? 'Qualité'
                                      : kQLabels[_variants[_vidx].q]!,
                                  style: const TextStyle(color: Colors.white, fontWeight: FontWeight.w700)),
                            ),
                          _btn(Icons.audiotrack, () => _pickTrack(true), size: 24, tip: 'Audio'),
                          _btn(Icons.subtitles, () => _pickTrack(false), size: 24, tip: 'Sous-titres'),
                          _btn(Icons.tune, _tune, size: 24, tip: 'Image et son'),
                          _btn(Icons.insights, () => setState(() => _showDiag = !_showDiag), size: 24, tip: 'Diagnostic'),
                        ]),
                      ),
                      const SizedBox(height: 6),
                    ]),
                  ),
                ]),
              ),
            ),
            if (_showDiag)
              Positioned(
                left: 12, top: 70,
                child: IgnorePointer(
                  child: Container(
                    width: 330,
                    padding: const EdgeInsets.all(12),
                    decoration: BoxDecoration(color: const Color(0xD90B0E14), borderRadius: BorderRadius.circular(12)),
                    child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                      const Text('Diagnostic', style: TextStyle(fontWeight: FontWeight.w800)),
                      const SizedBox(height: 6),
                      for (final e in _diagData().entries)
                        Padding(
                          padding: const EdgeInsets.symmetric(vertical: 1),
                          child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
                            SizedBox(width: 120, child: Text(e.key, style: const TextStyle(color: kMuted, fontSize: 11.5))),
                            Expanded(child: Text('${e.value}', style: const TextStyle(fontSize: 11.5))),
                          ]),
                        ),
                    ]),
                  ),
                ),
              ),
            if (_showList)
              Positioned(
                right: 0, top: 0, bottom: 0,
                width: 320,
                child: Container(
                  color: const Color(0xEE0B0C10),
                  child: SafeArea(
                    left: false,
                    child: ListView.builder(
                      itemCount: widget.items.length,
                      itemBuilder: (c, i) => ListTile(
                        autofocus: i == _index,
                        selected: i == _index,
                        selectedColor: kAccent,
                        title: Text(widget.items[i].name, maxLines: 1, overflow: TextOverflow.ellipsis),
                        onTap: () {
                          setState(() => _showList = false);
                          _open(i);
                        },
                      ),
                    ),
                  ),
                ),
              ),
          ]),
        ),
      ),
    );
  }
}
