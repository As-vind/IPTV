// Grande bannière façon OCTO+ : les affiches défilent en glissant, titre (logo officiel) au milieu.
import 'dart:async';
import 'dart:ui' as ui;

import 'package:flutter/material.dart';

import '../core/meta.dart';
import '../core/models.dart';
import '../core/text.dart';
import 'nav.dart';
import 'octo.dart';
import 'scope.dart';
import 'theme.dart';
import 'widgets.dart';

class HeroBanner extends StatefulWidget {
  final String pageTitle;
  final List<Item> items;
  final Set<String> newUrls;
  final bool collapsed;
  const HeroBanner({super.key, required this.pageTitle, required this.items, this.newUrls = const {}, this.collapsed = false});
  @override
  State<HeroBanner> createState() => _HeroBannerState();
}

class _HeroBannerState extends State<HeroBanner> {
  late final PageController _pc = PageController(initialPage: widget.items.length * 500);
  late int _i = widget.items.length * 500;
  Timer? _t;
  final Map<String, Map<String, dynamic>> _meta = {};

  int get _n => widget.items.length;
  Item get _cur => widget.items[_i % _n];

  @override
  void initState() {
    super.initState();
    final s = AppScope.read(context);
    for (final it in widget.items) {
      final now = s.metaNow(it);
      if (now != null) _meta[it.url] = now;
      s.meta(it).then((m) {
        if (m != null && mounted) setState(() => _meta[it.url] = m);
      });
    }
    _t = Timer.periodic(const Duration(seconds: 8), (_) {
      if (!mounted || !TickerMode.of(context) || !_pc.hasClients) return;
      _pc.nextPage(duration: const Duration(milliseconds: 750), curve: Curves.easeOutCubic);
    });
  }

  @override
  void dispose() {
    _t?.cancel();
    _pc.dispose();
    super.dispose();
  }

  void _go(int d) {
    _pc.animateToPage(_i + d, duration: const Duration(milliseconds: 650), curve: Curves.easeOutCubic);
  }

  String _backdrop(Item it, double w) {
    final b = '${_meta[it.url]?['backdrop'] ?? ''}';
    return b.isEmpty ? '' : hires(b, w > 1400 ? 'original' : 'w1280');
  }

  String _poster(Item it) {
    final p = '${_meta[it.url]?['poster'] ?? ''}';
    return p.isNotEmpty ? hires(p, 'w780') : it.logo;
  }

  /// Affiche verticale + bloc de texte centrés ensemble (quand il n'y a pas d'image de fond).
  (Rect, double, double, double)? _pairGeom(double w, double h, double band) {
    final area = h - band - 16;
    final ph = area * .84, pw = ph * 2 / 3;
    final gap = w * .05 < 40 ? 40.0 : w * .05;
    var bw = w * .46;
    if (bw > 1000) bw = 1000;
    if (bw > w - pw - gap - 120) bw = w - pw - gap - 120;
    if (bw < 300) return null;
    final x0 = (w - (pw + gap + bw)) / 2;
    final cy = band + area / 2 + 8;
    return (Rect.fromLTWH(x0, cy - ph / 2, pw, ph), x0 + pw + gap, bw, cy);
  }

  Widget _slide(Item it, double w, double h, double band, bool phone) {
    final bd = _backdrop(it, w);
    final poster = _poster(it);
    if (bd.isNotEmpty) {
      return NetImg(bd, radius: 0, alignment: const Alignment(0, -.5), cacheWidth: (w * 2).clamp(600, 2600).toInt());
    }
    final pair = phone ? null : _pairGeom(w, h, band);
    return Stack(fit: StackFit.expand, children: [
      ImageFiltered(
        imageFilter: ui.ImageFilter.blur(sigmaX: 28, sigmaY: 28),
        child: NetImg(poster, radius: 0, cacheWidth: 400),
      ),
      Container(color: Colors.black.withValues(alpha: .35)),
      if (pair != null)
        Positioned.fromRect(
          rect: pair.$1,
          child: DecoratedBox(
            decoration: BoxDecoration(borderRadius: BorderRadius.circular(16), boxShadow: const [
              BoxShadow(color: Colors.black54, blurRadius: 30, offset: Offset(0, 10)),
            ]),
            child: NetImg(poster, radius: 16, fallbackText: it.title, cacheWidth: 700),
          ),
        )
      else
        Positioned(
          top: band + 10, left: 0, right: 0, height: h * .5,
          child: Center(child: AspectRatio(aspectRatio: 2 / 3, child: NetImg(poster, radius: 14, cacheWidth: 600))),
        ),
    ]);
  }

  @override
  Widget build(BuildContext context) {
    if (_n == 0) return const SizedBox.shrink();
    final u = UiK.of(context);
    final phone = u.phone;
    return LayoutBuilder(builder: (context, c) {
      final w = c.maxWidth;
      final screenH = MediaQuery.sizeOf(context).height;
      final phoneMax = screenH * .82 < 360 ? 360.0 : screenH * .82;
      final h = (phone ? (w * 1.25).clamp(360.0, phoneMax) : (w * .43).clamp(380.0, (screenH * .8).clamp(380.0, 1100.0))).toDouble();
      final band = phone ? 96.0 : (widget.collapsed ? 150.0 : 124.0);
      final k = u.k;
      final it = _cur;
      final m = _meta[it.url];
      final title = '${m?['title'] ?? ''}'.isNotEmpty ? '${m!['title']}' : (it.title.isEmpty ? it.name : it.title);
      final genre = ((m?['genres'] as List?) ?? []).isNotEmpty ? '${(m!['genres'] as List).first}' : prettyGroup(it.group);
      final sub = '${it.kind == 'series' ? 'Séries' : 'Films'} · $genre';
      final logo = '${m?['title_logo'] ?? ''}'.isEmpty ? '' : hires('${m!['title_logo']}', 'w780');
      final isNew = widget.newUrls.contains(it.url);
      final pairMode = !phone && _backdrop(it, w).isEmpty && m != null;
      final pair = pairMode ? _pairGeom(w, h, band) : null;
      final bw = pair?.$3 ?? (w * .6).clamp(260.0, 1100.0).toDouble();
      final f = clampK(k, .8, 1.7);

      final content = Column(mainAxisSize: MainAxisSize.min, children: [
        if (isNew)
          Container(
            margin: EdgeInsets.only(bottom: 10 * f),
            padding: EdgeInsets.symmetric(horizontal: 14 * f, vertical: 4 * f),
            decoration: BoxDecoration(
              color: Colors.black38,
              borderRadius: BorderRadius.circular(20),
              border: Border.all(color: Colors.white.withValues(alpha: .85), width: 1.4),
            ),
            child: Text('Nouveauté', style: TextStyle(fontWeight: FontWeight.w800, fontSize: 12.5 * f, color: Colors.white)),
          ),
        titleOrLogo(logo, title, maxW: bw * .72, maxH: (h * .2).clamp(60.0, 220.0).toDouble(), font: (phone ? 30 : 38) * f,
            align: Alignment.center, textAlign: TextAlign.center),
        SizedBox(height: 10 * f),
        Text(sub, textAlign: TextAlign.center, maxLines: 1, overflow: TextOverflow.ellipsis,
            style: TextStyle(fontWeight: FontWeight.w600, fontSize: 14 * f, color: const Color(0xFFE6E8EE))),
        SizedBox(height: 16 * f),
        FilledButton.icon(
          onPressed: () => it.kind == 'movie' ? playItems(context, [PlayItem.of(it)], 0) : openItem(context, it),
          style: FilledButton.styleFrom(
            padding: EdgeInsets.symmetric(horizontal: 34 * clampK(f, .8, 1.3), vertical: 15 * clampK(f, .8, 1.3)),
            textStyle: TextStyle(fontSize: 17 * clampK(f, .8, 1.3), fontWeight: FontWeight.w800),
          ),
          icon: Icon(Icons.play_arrow_rounded, size: 26 * clampK(f, .8, 1.3)),
          label: const Text('Regarder'),
        ),
        SizedBox(height: 14 * f),
        Container(
          padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 7),
          decoration: BoxDecoration(color: Colors.black45, borderRadius: BorderRadius.circular(12)),
          child: Row(mainAxisSize: MainAxisSize.min, children: [
            for (var j = 0; j < _n; j++)
              GestureDetector(
                onTap: () => _pc.animateToPage(_i - (_i % _n) + j,
                    duration: const Duration(milliseconds: 650), curve: Curves.easeOutCubic),
                child: AnimatedContainer(
                  duration: const Duration(milliseconds: 250),
                  margin: const EdgeInsets.symmetric(horizontal: 4),
                  width: j == _i % _n ? 32 : 8,
                  height: 8,
                  decoration: BoxDecoration(
                      color: j == _i % _n ? Colors.white : Colors.white54, borderRadius: BorderRadius.circular(4)),
                ),
              ),
          ]),
        ),
      ]);

      return SizedBox(
        height: h,
        child: Stack(children: [
          Positioned.fill(
            child: PageView.builder(
              controller: _pc,
              onPageChanged: (i) => setState(() => _i = i),
              itemBuilder: (c, i) {
                final x = widget.items[i % _n];
                return GestureDetector(onTap: () => openItem(context, x), child: _slide(x, w, h, band, phone));
              },
            ),
          ),
          const Positioned.fill(
            child: IgnorePointer(
              child: DecoratedBox(
                decoration: BoxDecoration(
                  gradient: LinearGradient(colors: [Color(0x70000000), Color(0x0A000000), Color(0x5A000000)], stops: [0, .45, 1]),
                ),
              ),
            ),
          ),
          const Positioned.fill(
            child: IgnorePointer(
              child: DecoratedBox(
                decoration: BoxDecoration(
                  gradient: LinearGradient(begin: Alignment.topCenter, end: Alignment.bottomCenter,
                      colors: [Color(0x00040506), Color(0xAF040506), kBg], stops: [.5, .84, 1]),
                ),
              ),
            ),
          ),
          // bandeau supérieur dépoli + titre de la page
          Positioned(
            left: 0, right: 0, top: 0, height: band,
            child: ClipRect(
              child: BackdropFilter(
                filter: ui.ImageFilter.blur(sigmaX: 22, sigmaY: 22),
                child: Container(
                  decoration: BoxDecoration(
                    color: const Color(0x6E141A22),
                    border: Border(bottom: BorderSide(color: Colors.white.withValues(alpha: .1))),
                  ),
                  alignment: Alignment.bottomLeft,
                  padding: EdgeInsets.fromLTRB(phone ? 16 : 34, 0, 16, phone ? 14 : 22),
                  child: SafeArea(
                    bottom: false,
                    child: Text(widget.pageTitle,
                        style: TextStyle(fontSize: phone ? 30 : 40, fontWeight: FontWeight.w900, color: Colors.white)),
                  ),
                ),
              ),
            ),
          ),
          // titre, genre, Regarder, points
          if (pair != null)
            Positioned(
              left: pair.$2, width: pair.$3, top: 0, bottom: 0,
              child: Align(
                alignment: Alignment((0), ((pair.$4 / h) * 2 - 1)),
                child: AnimatedSwitcher(duration: const Duration(milliseconds: 450), child: KeyedSubtree(key: ValueKey(_i), child: content)),
              ),
            )
          else
            Positioned(
              left: 0, right: 0, bottom: 20 * f,
              child: Center(
                child: SizedBox(
                  width: bw,
                  child: AnimatedSwitcher(duration: const Duration(milliseconds: 450), child: KeyedSubtree(key: ValueKey(_i), child: content)),
                ),
              ),
            ),
          if (!phone && _n > 1) ...[
            Positioned(left: 16, top: band + (h - band) / 2 - 26, child: _arrow(Icons.chevron_left, () => _go(-1))),
            Positioned(right: 16, top: band + (h - band) / 2 - 26, child: _arrow(Icons.chevron_right, () => _go(1))),
          ],
        ]),
      );
    });
  }

  Widget _arrow(IconData ic, VoidCallback onTap) => Material(
        color: const Color(0x8C0A0E16),
        shape: const CircleBorder(side: BorderSide(color: Color(0x2EFFFFFF))),
        child: InkWell(
          customBorder: const CircleBorder(),
          onTap: onTap,
          child: SizedBox(width: 52, height: 52, child: Icon(ic, color: Colors.white, size: 32)),
        ),
      );
}
