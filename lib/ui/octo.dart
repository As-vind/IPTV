// Cases et rangées façon OCTO+ (mêmes formats que la version Windows 2.6).
import 'package:flutter/material.dart';

import '../core/meta.dart';
import '../core/models.dart';
import '../core/text.dart';
import 'scope.dart';
import 'theme.dart';
import 'widgets.dart';

enum CardStyle { resume, land, wide, tile, tileBig, big, provider, posterBig, posterSm, coeur, studio, actor }

/// Taille de l'image de chaque case (à l'échelle 1).
Size _base(CardStyle s) => switch (s) {
      CardStyle.resume => const Size(270, 152),
      CardStyle.land => const Size(270, 152),
      CardStyle.wide => const Size(222, 125),
      CardStyle.tile => const Size(143, 80),
      CardStyle.tileBig => const Size(262, 148),
      CardStyle.big => const Size(466, 316),
      CardStyle.provider => const Size(135, 135),
      CardStyle.posterBig => const Size(216, 324),
      CardStyle.posterSm => const Size(134, 201),
      CardStyle.coeur => const Size(400, 475),
      CardStyle.studio => const Size(185, 103),
      CardStyle.actor => const Size(136, 136),
    };

Size cardImageSize(CardStyle s, double k) {
  final b = _base(s);
  return Size(b.width * k, b.height * k);
}

/// Hauteur de la case avec le texte éventuel en dessous.
double cardHeight(CardStyle s, double k) {
  final h = cardImageSize(s, k).height;
  if (s == CardStyle.wide) return h + 8 + 40 * clampK(k, .8, 1.2);
  if (s == CardStyle.actor) return h + 8 + 38 * clampK(k, .8, 1.2);
  return h;
}

const _tileColors = [0xFF3B5BDB, 0xFF0B7285, 0xFF5F3DC4, 0xFFC2255C, 0xFFE67700, 0xFF2B8A3E, 0xFF862E9C, 0xFF1864AB,
  0xFFA61E4D, 0xFF5C940D, 0xFF364FC7, 0xFFD9480F];

Color tileColor(String name) => Color(_tileColors[name.codeUnits.fold<int>(0, (a, b) => a + b) % _tileColors.length]);

const _catEmoji = [('sport', '⚽'), ('foot', '⚽'), ('info', '📰'), ('news', '📰'), ('cin', '🎬'), ('film', '🎬'),
  ('movie', '🎬'), ('music', '🎵'), ('musique', '🎵'), ('enfant', '🧸'), ('jeunesse', '🧸'), ('kid', '🧸'),
  ('dessin', '🧸'), ('docu', '🌍'), ('decouverte', '🌍'), ('religi', '🕊'), ('seri', '📺'), ('divert', '🎭'),
  ('general', '📺'), ('regional', '🏘'), ('local', '🏘'), ('premium', '💎'), ('canal', '💎'), ('adult', '🔞'),
  ('cuisine', '🍳'), ('4k', '✨'), ('uhd', '✨'), ('radio', '📻'), ('anim', '🧸'), ('action', '💥'), ('comedie', '😄'),
  ('horreur', '👻'), ('drame', '🎭'), ('crime', '🕵'), ('aventure', '🧭'), ('science', '🚀'), ('romance', '💕')];

String catEmoji(String name) {
  final n = norm(name);
  for (final (k, e) in _catEmoji) {
    if (n.contains(k)) return e;
  }
  return '📺';
}

/// Données d'une case.
class CardData {
  final String title;
  final String image;
  final String sub;
  final String badge;
  final String remain;
  final String overlay;
  final String time;
  final double progress;
  final bool unavailable;
  final bool logoMode;
  final Item? lib;
  final bool fetchMeta;
  final int c1, c2;
  final VoidCallback onTap;
  const CardData({required this.title, this.image = '', this.sub = '', this.badge = '', this.remain = '',
      this.overlay = '', this.time = '', this.progress = 0, this.unavailable = false, this.logoMode = false,
      this.lib, this.fetchMeta = true, this.c1 = 0, this.c2 = 0, required this.onTap});
}

/// Recharge une case quand la fiche (fond, logo-titre, genre) arrive.
class MetaBuilder extends StatefulWidget {
  final Item? item;
  final Widget Function(Map<String, dynamic>? m) builder;
  const MetaBuilder({super.key, required this.item, required this.builder});
  @override
  State<MetaBuilder> createState() => _MetaBuilderState();
}

class _MetaBuilderState extends State<MetaBuilder> {
  Map<String, dynamic>? _m;
  @override
  void initState() {
    super.initState();
    _load();
  }

  @override
  void didUpdateWidget(MetaBuilder old) {
    super.didUpdateWidget(old);
    if (old.item?.url != widget.item?.url) _load();
  }

  void _load() {
    final it = widget.item;
    if (it == null || (it.kind != 'movie' && it.kind != 'series')) {
      _m = null;
      return;
    }
    final s = AppScope.read(context);
    _m = s.metaNow(it);
    if (_m == null) {
      s.meta(it).then((m) {
        if (mounted && m != null) setState(() => _m = m);
      });
    }
  }

  @override
  Widget build(BuildContext context) => widget.builder(_m);
}

/// Logo-titre TMDB si disponible, sinon le titre en texte.
Widget titleOrLogo(String logo, String title, {required double maxW, required double maxH, double font = 18,
    Alignment align = Alignment.bottomLeft, TextAlign textAlign = TextAlign.left}) {
  final text = Text(title, maxLines: 2, overflow: TextOverflow.ellipsis, textAlign: textAlign,
      style: TextStyle(fontSize: font, fontWeight: FontWeight.w900, color: Colors.white, height: 1.1,
          shadows: const [Shadow(blurRadius: 8, color: Colors.black54)]));
  if (logo.isEmpty) return text;
  return ConstrainedBox(
    constraints: BoxConstraints(maxWidth: maxW, maxHeight: maxH),
    child: Image.network(logo, fit: BoxFit.contain, alignment: align, filterQuality: FilterQuality.medium,
        errorBuilder: (_, __, ___) => text,
        loadingBuilder: (c, child, p) => p == null ? child : const SizedBox()),
  );
}

Widget _redPill(String t) => Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
      decoration: BoxDecoration(color: kRed, borderRadius: BorderRadius.circular(8)),
      child: Text(t, style: const TextStyle(color: Colors.white, fontWeight: FontWeight.w700, fontSize: 11.5)),
    );

Widget _outlinePill(String t, double k) => Container(
      padding: EdgeInsets.symmetric(horizontal: 12 * clampK(k, .8, 1.3), vertical: 4),
      decoration: BoxDecoration(
          color: Colors.black38, borderRadius: BorderRadius.circular(20),
          border: Border.all(color: Colors.white.withValues(alpha: .8), width: 1.3)),
      child: Text(t, style: TextStyle(color: Colors.white, fontWeight: FontWeight.w700, fontSize: 11 * clampK(k, .85, 1.3))),
    );

Widget _bottomShade([double from = .45, int alpha = 0xCC]) => DecoratedBox(
      decoration: BoxDecoration(
        gradient: LinearGradient(begin: Alignment.topCenter, end: Alignment.bottomCenter,
            stops: [from, 1], colors: [Colors.transparent, Color.fromARGB(alpha, 0, 0, 0)]),
      ),
    );

/// Une case.
class OctoCard extends StatelessWidget {
  final CardStyle style;
  final CardData d;
  final double k;
  final bool autofocus;
  const OctoCard({super.key, required this.style, required this.d, required this.k, this.autofocus = false});

  double get _radius => switch (style) {
        CardStyle.big => 20,
        CardStyle.coeur => 22,
        CardStyle.provider => 14,
        _ => 12,
      };

  @override
  Widget build(BuildContext context) {
    final sz = cardImageSize(style, k);
    final needsMeta = d.lib != null && d.fetchMeta &&
        const {CardStyle.resume, CardStyle.land, CardStyle.big, CardStyle.coeur, CardStyle.posterBig, CardStyle.posterSm}
            .contains(style);
    Widget body(Map<String, dynamic>? m) => _body(context, sz, m);
    return SizedBox(
      width: sz.width,
      height: cardHeight(style, k),
      child: FocusTile(
        autofocus: autofocus,
        radius: style == CardStyle.actor ? sz.width : _radius,
        onTap: d.onTap,
        builder: (on) => Stack(clipBehavior: Clip.none, children: [
          needsMeta ? MetaBuilder(item: d.lib, builder: body) : body(null),
          if (on)
            Positioned(
              left: 0, top: 0, width: sz.width, height: sz.height,
              child: IgnorePointer(
                child: DecoratedBox(
                  decoration: BoxDecoration(
                    shape: style == CardStyle.actor ? BoxShape.circle : BoxShape.rectangle,
                    borderRadius: style == CardStyle.actor ? null : BorderRadius.circular(_radius),
                    border: Border.all(color: Colors.white, width: 3),
                  ),
                ),
              ),
            ),
        ]),
      ),
    );
  }

  Widget _img(String url, Size sz, {BoxFit fit = BoxFit.cover, String fallback = ''}) => SizedBox(
        width: sz.width,
        height: sz.height,
        child: NetImg(url, fallbackText: fallback, fit: fit, radius: _radius,
            cacheWidth: (sz.width * 2.5).clamp(120, 1400).toInt()),
      );

  Widget _body(BuildContext context, Size sz, Map<String, dynamic>? m) {
    final logo = '${m?['title_logo'] ?? ''}';
    final backdrop = '${m?['backdrop'] ?? ''}';
    final poster = '${m?['poster'] ?? ''}';
    final genre = ((m?['genres'] as List?) ?? []).isNotEmpty ? '${(m!['genres'] as List).first}' : '';
    final title = '${m?['title'] ?? ''}'.isNotEmpty ? '${m!['title']}' : d.title;
    final f = clampK(k, .75, 1.4);
    switch (style) {
      case CardStyle.resume:
      case CardStyle.land:
        final img = backdrop.isNotEmpty ? hires(backdrop, 'w780') : d.image;
        return ClipRRect(
          borderRadius: BorderRadius.circular(_radius),
          child: SizedBox(
            width: sz.width, height: sz.height,
            child: Stack(fit: StackFit.expand, children: [
              _img(img, sz, fallback: title),
              _bottomShade(.45),
              if (style == CardStyle.land)
                Positioned(
                  left: 14 * f, bottom: 12 * f,
                  child: titleOrLogo(logo, title, maxW: sz.width * .62, maxH: sz.height * .42, font: 15 * f),
                ),
              if (style == CardStyle.resume)
                Positioned(
                  left: 12 * f, right: 12 * f, bottom: 11 * f,
                  child: Row(children: [
                    Icon(Icons.play_arrow_rounded, color: Colors.white, size: 20 * f),
                    const SizedBox(width: 6),
                    SizedBox(
                      width: 64 * f,
                      child: ClipRRect(
                        borderRadius: BorderRadius.circular(3),
                        child: LinearProgressIndicator(
                            value: clampK(d.progress, 0, 1), minHeight: 5, color: Colors.white, backgroundColor: Colors.white24),
                      ),
                    ),
                    const SizedBox(width: 10),
                    Flexible(
                      child: Text(d.remain, maxLines: 1, overflow: TextOverflow.ellipsis,
                          style: TextStyle(fontWeight: FontWeight.w700, fontSize: 12 * f, color: Colors.white)),
                    ),
                  ]),
                ),
              if (d.unavailable) Positioned(top: 8, left: 0, right: 0, child: Center(child: _redPill('Indisponible'))),
            ]),
          ),
        );
      case CardStyle.big:
        final img = backdrop.isNotEmpty ? hires(backdrop, 'w1280') : d.image;
        final sub = genre.isNotEmpty ? '${d.lib?.kind == 'series' ? 'Séries' : 'Films'} · $genre' : d.sub;
        return ClipRRect(
          borderRadius: BorderRadius.circular(_radius),
          child: SizedBox(
            width: sz.width, height: sz.height,
            child: Stack(fit: StackFit.expand, children: [
              _img(img, sz, fallback: title),
              _bottomShade(.35, 0xEB),
              Positioned(
                left: 24 * f, right: 24 * f, bottom: 20 * f,
                child: Column(crossAxisAlignment: CrossAxisAlignment.start, mainAxisSize: MainAxisSize.min, children: [
                  if (d.badge.isNotEmpty) ...[_outlinePill(d.badge, k), SizedBox(height: 10 * f)],
                  titleOrLogo(logo, title, maxW: sz.width * .55, maxH: 84 * f, font: 22 * f),
                  if (sub.isNotEmpty) ...[
                    SizedBox(height: 8 * f),
                    Text(sub, style: TextStyle(fontWeight: FontWeight.w600, fontSize: 12.5 * f, color: const Color(0xFFD9DCE4))),
                  ],
                ]),
              ),
            ]),
          ),
        );
      case CardStyle.coeur:
        final img = d.image.isNotEmpty ? d.image : (poster.isNotEmpty ? hires(poster, 'w780') : (d.lib?.logo ?? ''));
        final sub = genre.isNotEmpty ? '${d.lib?.kind == 'series' ? 'Séries' : 'Films'} · $genre' : d.sub;
        return ClipRRect(
          borderRadius: BorderRadius.circular(_radius),
          child: SizedBox(
            width: sz.width, height: sz.height,
            child: Stack(fit: StackFit.expand, children: [
              _img(img, sz, fallback: title),
              _bottomShade(.5, 0xE0),
              Positioned(
                left: 24 * f, right: 24 * f, bottom: 22 * f,
                child: Column(crossAxisAlignment: CrossAxisAlignment.start, mainAxisSize: MainAxisSize.min, children: [
                  titleOrLogo(logo, title, maxW: sz.width * .62, maxH: 96 * f, font: 22 * f),
                  if (sub.isNotEmpty) ...[
                    SizedBox(height: 10 * f),
                    Text(sub, style: TextStyle(fontWeight: FontWeight.w600, fontSize: 12.5 * f, color: const Color(0xFFD9DCE4))),
                  ],
                ]),
              ),
            ]),
          ),
        );
      case CardStyle.posterBig:
      case CardStyle.posterSm:
        final img = d.image.isNotEmpty ? d.image : (poster.isNotEmpty ? hires(poster, 'w500') : (d.lib?.logo ?? ''));
        return SizedBox(
          width: sz.width, height: sz.height,
          child: Stack(fit: StackFit.expand, children: [
            _img(img, sz, fallback: title),
            if (img.isEmpty)
              Center(
                child: Padding(
                  padding: const EdgeInsets.all(10),
                  child: Text(title, textAlign: TextAlign.center, maxLines: 4,
                      style: TextStyle(color: kMuted, fontWeight: FontWeight.w700, fontSize: 13 * f)),
                ),
              ),
            if (d.unavailable) Positioned(bottom: 10, left: 0, right: 0, child: Center(child: _redPill('Indisponible'))),
          ]),
        );
      case CardStyle.provider:
        return Container(
          width: sz.width, height: sz.height,
          decoration: BoxDecoration(
            color: const Color(0xFF15181F),
            borderRadius: BorderRadius.circular(_radius),
            border: Border.all(color: Colors.white.withValues(alpha: .2)),
          ),
          clipBehavior: Clip.antiAlias,
          child: d.image.isNotEmpty
              ? NetImg(d.image, radius: 0, fallbackText: d.title)
              : Center(
                  child: Text(d.title, textAlign: TextAlign.center,
                      style: TextStyle(fontWeight: FontWeight.w900, fontSize: 15 * f, color: Colors.white))),
        );
      case CardStyle.studio:
        final dark = Color(d.c1).computeLuminance() > .6;
        return Container(
          width: sz.width, height: sz.height,
          decoration: BoxDecoration(
            borderRadius: BorderRadius.circular(_radius),
            gradient: LinearGradient(colors: [Color(d.c1), Color(d.c2)], begin: Alignment.topLeft, end: Alignment.bottomRight),
            border: Border.all(color: Colors.white.withValues(alpha: .22)),
          ),
          alignment: Alignment.center,
          padding: const EdgeInsets.symmetric(horizontal: 8),
          child: FittedBox(
            fit: BoxFit.scaleDown,
            child: Text(d.title,
                style: TextStyle(fontWeight: FontWeight.w900, fontSize: 21 * f, letterSpacing: 1,
                    color: dark ? const Color(0xFF11151C) : Colors.white)),
          ),
        );
      case CardStyle.tile:
      case CardStyle.tileBig:
        final base = d.c1 != 0 ? Color(d.c1) : tileColor(d.title);
        final hsl = HSLColor.fromColor(base);
        return Container(
          width: sz.width, height: sz.height,
          decoration: BoxDecoration(
            borderRadius: BorderRadius.circular(_radius),
            gradient: LinearGradient(
              colors: [hsl.withLightness(clampK(hsl.lightness + .1, 0, 1)).toColor(), hsl.withLightness(clampK(hsl.lightness - .25, 0, 1)).toColor()],
              begin: Alignment.topLeft, end: Alignment.bottomRight,
            ),
            border: Border.all(color: Colors.white.withValues(alpha: .24), width: 1.2),
          ),
          padding: EdgeInsets.fromLTRB(14 * f, 10 * f, 12 * f, 10 * f),
          child: Stack(children: [
            if (style == CardStyle.tileBig)
              Positioned(right: 0, top: 0, child: Text(catEmoji(d.title), style: TextStyle(fontSize: 40 * f))),
            if (d.sub.isNotEmpty && style == CardStyle.tileBig)
              Positioned(left: 0, top: 0, right: 60 * f,
                  child: Text(d.sub, maxLines: 1, overflow: TextOverflow.ellipsis,
                      style: TextStyle(fontSize: 11 * f, color: const Color(0xFFE6E8EE)))),
            Align(
              alignment: Alignment.bottomLeft,
              child: Text(d.title, maxLines: 2, overflow: TextOverflow.ellipsis,
                  style: TextStyle(fontWeight: FontWeight.w800, fontSize: (style == CardStyle.tileBig ? 17 : 13) * f,
                      color: Colors.white, height: 1.15)),
            ),
          ]),
        );
      case CardStyle.actor:
        return Column(children: [
          SizedBox(width: sz.width, height: sz.height, child: NetImg(d.image, fallbackText: d.title, circle: true, cacheWidth: 300)),
          const SizedBox(height: 8),
          Text(d.title, textAlign: TextAlign.center, maxLines: 2, overflow: TextOverflow.ellipsis,
              style: TextStyle(fontWeight: FontWeight.w700, fontSize: 13 * f, color: Colors.white)),
        ]);
      case CardStyle.wide:
        return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          ClipRRect(
            borderRadius: BorderRadius.circular(_radius),
            child: SizedBox(
              width: sz.width, height: sz.height,
              child: Stack(fit: StackFit.expand, children: [
                if (d.logoMode)
                  Container(
                    decoration: const BoxDecoration(
                        gradient: LinearGradient(colors: [Color(0xFF2A2F3A), Color(0xFF121418)],
                            begin: Alignment.topLeft, end: Alignment.bottomRight)),
                    padding: EdgeInsets.fromLTRB(sz.width * .24, sz.height * .12, sz.width * .24, sz.height * .34),
                    child: NetImg(d.image, fallbackText: d.overlay, fit: BoxFit.contain, radius: 0, cacheWidth: 320),
                  )
                else
                  _img(d.image, sz, fallback: d.title),
                _bottomShade(.5),
                if (d.overlay.isNotEmpty)
                  Positioned(
                    left: 10, right: 10, bottom: 16 * f,
                    child: Text(d.overlay.toUpperCase(), maxLines: 1, overflow: TextOverflow.ellipsis,
                        style: TextStyle(fontWeight: FontWeight.w800, fontSize: 10.5 * f, color: Colors.white)),
                  ),
                if (d.progress > 0)
                  Positioned(
                    left: 10, right: 10, bottom: 7 * f,
                    child: ClipRRect(
                      borderRadius: BorderRadius.circular(2),
                      child: LinearProgressIndicator(
                          value: clampK(d.progress, 0, 1), minHeight: 3.5, color: Colors.white, backgroundColor: Colors.white24),
                    ),
                  ),
                if (d.time.isNotEmpty)
                  Positioned(
                    left: 8, top: 8,
                    child: Container(
                      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
                      decoration: BoxDecoration(color: kAccent, borderRadius: BorderRadius.circular(8)),
                      child: Row(mainAxisSize: MainAxisSize.min, children: [
                        const Icon(Icons.schedule, size: 14, color: Colors.white),
                        const SizedBox(width: 4),
                        Text(d.time, style: const TextStyle(fontWeight: FontWeight.w800, fontSize: 11.5, color: Colors.white)),
                      ]),
                    ),
                  ),
              ]),
            ),
          ),
          const SizedBox(height: 7),
          Text(d.title, maxLines: 2, overflow: TextOverflow.ellipsis,
              style: TextStyle(fontSize: 13 * f, color: Colors.white, height: 1.2)),
        ]);
    }
  }
}

/// Rangée titrée « Titre › » avec défilement horizontal.
class OctoRow extends StatelessWidget {
  final String title;
  final CardStyle style;
  final List<CardData> items;
  final VoidCallback? onMore;
  const OctoRow({super.key, required this.title, required this.style, required this.items, this.onMore});
  @override
  Widget build(BuildContext context) {
    if (items.isEmpty) return const SizedBox.shrink();
    final u = UiK.of(context);
    final k = u.k;
    final pad = u.phone ? 14.0 : 26.0;
    return Padding(
      padding: EdgeInsets.only(top: title.isEmpty ? 18 * clampK(k, .7, 1.2) : 26 * clampK(k, .7, 1.2)),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        if (title.isNotEmpty)
          Padding(
            padding: EdgeInsets.fromLTRB(pad, 0, pad, 10),
            child: InkWell(
              onTap: onMore,
              canRequestFocus: false,
              child: Row(mainAxisSize: MainAxisSize.min, children: [
                Flexible(
                  child: Text(title, maxLines: 1, overflow: TextOverflow.ellipsis,
                      style: TextStyle(fontSize: (u.phone ? 19 : 23) * clampK(k, .85, 1.3), fontWeight: FontWeight.w800, color: Colors.white)),
                ),
                if (onMore != null) const Padding(padding: EdgeInsets.only(left: 4, top: 2), child: Icon(Icons.chevron_right, color: kMuted)),
              ]),
            ),
          ),
        SizedBox(
          height: cardHeight(style, k) + 6,
          child: ListView.separated(
            scrollDirection: Axis.horizontal,
            padding: EdgeInsets.symmetric(horizontal: pad),
            itemCount: items.length,
            clipBehavior: Clip.none,
            separatorBuilder: (_, __) => SizedBox(width: 14 * clampK(k, .6, 1.3)),
            itemBuilder: (c, i) => OctoCard(style: style, d: items[i], k: k),
          ),
        ),
      ]),
    );
  }
}

/// Titre de page (pages sans bannière).
class PageTitle extends StatelessWidget {
  final String text;
  final Widget? right;
  final double top;
  const PageTitle(this.text, {super.key, this.right, this.top = 38});
  @override
  Widget build(BuildContext context) {
    final u = UiK.of(context);
    return Padding(
      padding: EdgeInsets.fromLTRB(u.phone ? 16 : 34, top, u.phone ? 12 : 30, 14),
      child: Row(children: [
        Expanded(
          child: Text(text, maxLines: 1, overflow: TextOverflow.ellipsis,
              style: TextStyle(fontSize: u.phone ? 28 : 38, fontWeight: FontWeight.w900, color: Colors.white)),
        ),
        if (right != null) right!,
      ]),
    );
  }
}
