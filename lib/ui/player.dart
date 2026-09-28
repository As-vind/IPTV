// Lecteur vidéo (media_kit / mpv) : direct, films, épisodes, zapping, pistes, reprise.
import 'dart:async';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:media_kit/media_kit.dart';
import 'package:media_kit_video/media_kit_video.dart';

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
  String _epg = '';
  double? _dragValue;
  bool _endedHandled = false;

  PlayItem get _cur => widget.items[_index];
  bool get _live => _cur.kind == 'live';

  @override
  void initState() {
    super.initState();
    SystemChrome.setEnabledSystemUIMode(SystemUiMode.immersiveSticky);
    _subs.addAll([
      _player.stream.position.listen((p) => setState(() => _pos = p)),
      _player.stream.duration.listen((d) => setState(() => _dur = d)),
      _player.stream.buffer.listen((b) => _buf = b),
      _player.stream.playing.listen((p) => setState(() => _playing = p)),
      _player.stream.buffering.listen((b) => setState(() => _buffering = b)),
      _player.stream.error.listen((e) => setState(() => _error = e)),
      _player.stream.completed.listen((c) {
        if (c) _onEnded();
      }),
    ]);
    _saveT = Timer.periodic(const Duration(seconds: 5), (_) => _saveProgress());
    _open(_index, resume: widget.resume);
    _poke();
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
      _error = '';
      _epg = '';
      _pos = Duration.zero;
      _dur = Duration.zero;
      _endedHandled = false;
    });
    final it = _cur;
    _s.noteLive(it);
    final local = _s.downloads.localFile(it.url);
    _localFile = local != null;
    await _applyCache(local != null);
    await _player.open(local != null ? Media(local) : Media(it.url, httpHeaders: _headers(it)), play: true);
    final pr = _s.progressOf(it.url);
    if (resume && !_live && pr != null && pr['done'] != true && ((pr['pos'] as num?) ?? 0) > 30000) {
      final target = Duration(milliseconds: (pr['pos'] as num).toInt());
      try {
        await _player.stream.duration.firstWhere((d) => d > Duration.zero).timeout(const Duration(seconds: 25));
        await _player.seek(target);
      } catch (_) {}
    }
    if (_live && it.streamId.isNotEmpty) {
      final progs = await _s.epgById(it.streamId);
      if (mounted && progs.isNotEmpty && _cur.url == it.url) {
        String hm(dynamic ts) => ts is int ? fmtHm(DateTime.fromMillisecondsSinceEpoch(ts * 1000)) : '';
        final now = progs.first;
        var t = 'Maintenant : ${now['title']}  (${hm(now['start_ts'])}–${hm(now['stop_ts'])})';
        if (progs.length > 1) t += '   ·   Ensuite : ${progs[1]['title']} (${hm(progs[1]['start_ts'])})';
        setState(() => _epg = t);
      }
    }
  }

  /// Mémoire tampon : films / séries pré-chargés 1, 5 ou 10 min à l'avance (cache sur disque) ;
  /// chaînes TV : quelques secondes de réserve.
  Future<void> _applyCache(bool local) async {
    try {
      final p = _player.platform as dynamic;
      Future<void> set(String k, String v) async {
        try {
          await p.setProperty(k, v);
        } catch (_) {}
      }

      if (local) {
        await set('cache', 'no');
        await set('cache-pause-initial', 'no');
        return;
      }
      await set('cache', 'yes');
      if (_live) {
        final secs = _s.liveCacheSecs;
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
        await set('cache-secs', '20');
        await set('demuxer-readahead-secs', '20');
        await set('demuxer-max-bytes', '150MiB');
        await set('cache-pause-initial', 'no');
        await set('cache-pause-wait', '1');
      }
    } catch (_) {}
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
    final subtitle = _epg.isNotEmpty ? _epg : (s != null ? 'Saison ${s['season']} · Épisode ${s['num']}' : prettyGroup(it.group));
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
                          _btn(Icons.audiotrack, () => _pickTrack(true), size: 24, tip: 'Audio'),
                          _btn(Icons.subtitles, () => _pickTrack(false), size: 24, tip: 'Sous-titres'),
                        ]),
                      ),
                      const SizedBox(height: 6),
                    ]),
                  ),
                ]),
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
