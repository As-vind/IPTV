import 'package:flutter/material.dart';

import '../core/models.dart';
import '../core/net.dart';
import '../core/store.dart';
import '../core/text.dart';
import 'theme.dart';

/// Image réseau avec emplacement de secours (initiales).
class NetImg extends StatelessWidget {
  final String url;
  final String fallbackText;
  final BoxFit fit;
  final double radius;
  final bool circle;
  final int? cacheWidth;
  final Alignment alignment;
  const NetImg(this.url,
      {super.key, this.fallbackText = '', this.fit = BoxFit.cover, this.radius = 10, this.circle = false,
      this.cacheWidth, this.alignment = Alignment.center});

  Widget _ph() => Container(
        decoration: const BoxDecoration(
          gradient: LinearGradient(colors: [Color(0xFF262A38), Color(0xFF1A1D27)], begin: Alignment.topLeft, end: Alignment.bottomRight),
        ),
        alignment: Alignment.center,
        child: Text(fallbackText.isEmpty ? '' : initials(fallbackText),
            style: const TextStyle(color: Color(0xFF5D6478), fontWeight: FontWeight.w800, fontSize: 20)),
      );

  @override
  Widget build(BuildContext context) {
    Widget img = url.isEmpty || !url.startsWith('http')
        ? _ph()
        : Image.network(url,
            fit: fit,
            alignment: alignment,
            cacheWidth: cacheWidth,
            headers: const {'User-Agent': 'Mozilla/5.0'},
            gaplessPlayback: true,
            errorBuilder: (_, __, ___) => _ph(),
            loadingBuilder: (c, child, p) => p == null ? child : _ph());
    if (circle) return ClipOval(child: img);
    return ClipRRect(borderRadius: BorderRadius.circular(radius), child: img);
  }
}

/// Carte cliquable, compatible télécommande (bordure rouge au focus).
class FocusTile extends StatefulWidget {
  final Widget Function(bool focused) builder;
  final VoidCallback? onTap;
  final VoidCallback? onLongPress;
  final bool autofocus;
  final double radius;
  const FocusTile({super.key, required this.builder, this.onTap, this.onLongPress, this.autofocus = false, this.radius = 12});
  @override
  State<FocusTile> createState() => _FocusTileState();
}

class _FocusTileState extends State<FocusTile> {
  bool _focus = false;
  bool _hover = false;
  @override
  Widget build(BuildContext context) {
    final on = _focus || _hover;
    return InkWell(
      autofocus: widget.autofocus,
      borderRadius: BorderRadius.circular(widget.radius),
      focusColor: Colors.transparent,
      hoverColor: Colors.transparent,
      onTap: widget.onTap,
      onLongPress: widget.onLongPress,
      onFocusChange: (f) => setState(() => _focus = f),
      onHover: (h) => setState(() => _hover = h),
      child: AnimatedScale(
        scale: _focus ? 1.05 : 1.0,
        duration: const Duration(milliseconds: 140),
        child: widget.builder(on),
      ),
    );
  }
}

class Pill extends StatelessWidget {
  final String text;
  final Color color;
  final double size;
  const Pill(this.text, {super.key, this.color = kAccent, this.size = 10});
  @override
  Widget build(BuildContext context) => Container(
        padding: const EdgeInsets.symmetric(horizontal: 7, vertical: 3),
        decoration: BoxDecoration(color: color, borderRadius: BorderRadius.circular(6)),
        child: Text(text, style: TextStyle(color: Colors.white, fontWeight: FontWeight.w800, fontSize: size, letterSpacing: .3)),
      );
}

class ProgressLine extends StatelessWidget {
  final double value;
  const ProgressLine(this.value, {super.key});
  @override
  Widget build(BuildContext context) => ClipRRect(
        borderRadius: BorderRadius.circular(2),
        child: LinearProgressIndicator(
            value: clampD(value, 0, 1), minHeight: 4, color: kAccent, backgroundColor: Colors.white24),
      );
}

// ----------------------------------------------------------------- cartes
class PosterCard extends StatelessWidget {
  final Item item;
  final VoidCallback onTap;
  final bool fav;
  const PosterCard({super.key, required this.item, required this.onTap, this.fav = false});
  static double width(BuildContext c) => 132 * uiScale(c);
  @override
  Widget build(BuildContext context) {
    final w = width(context);
    return SizedBox(
      width: w,
      child: FocusTile(
        onTap: onTap,
        builder: (on) => Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Container(
            width: w,
            height: w * 1.5,
            decoration: BoxDecoration(
              borderRadius: BorderRadius.circular(10),
              border: Border.all(color: on ? kAccent : Colors.transparent, width: 2.5),
            ),
            child: Stack(fit: StackFit.expand, children: [
              NetImg(item.logo, fallbackText: item.title.isEmpty ? item.name : item.title, radius: 8, cacheWidth: 360),
              if (item.logo.isEmpty)
                Positioned(
                  left: 8, right: 8, bottom: 10,
                  child: Text(item.title.isEmpty ? item.name : item.title,
                      textAlign: TextAlign.center, maxLines: 3, overflow: TextOverflow.ellipsis,
                      style: const TextStyle(color: kMuted, fontSize: 12)),
                ),
              if (item.ratingStr.isNotEmpty)
                Positioned(left: 6, top: 6, child: Pill('★ ${item.ratingStr}', color: Colors.black.withValues(alpha: .7))),
              if (fav) const Positioned(right: 6, top: 4, child: Text('★', style: TextStyle(color: Color(0xFFFFC940), fontSize: 18))),
            ]),
          ),
          const SizedBox(height: 6),
          Text(item.title.isEmpty ? item.name : item.title,
              maxLines: 1, overflow: TextOverflow.ellipsis,
              style: TextStyle(fontWeight: FontWeight.w700, fontSize: 13, color: on ? Colors.white : kText)),
          if (item.sub.isNotEmpty)
            Text(item.sub, maxLines: 1, overflow: TextOverflow.ellipsis, style: const TextStyle(color: kMuted, fontSize: 11)),
        ]),
      ),
    );
  }
}

/// Carte large 16:9 (chaînes du moment, nouveautés, reprise).
class WideCard extends StatelessWidget {
  final String image;
  final String title;
  final String sub;
  final String overlay;
  final String badge; // LIVE / NOUVEAU
  final String time;
  final double progress;
  final bool logoMode; // logo de chaîne centré
  final VoidCallback onTap;
  const WideCard({super.key, required this.image, required this.title, this.sub = '', this.overlay = '', this.badge = '',
      this.time = '', this.progress = 0, this.logoMode = false, required this.onTap});
  static double width(BuildContext c) => 270 * uiScale(c);
  @override
  Widget build(BuildContext context) {
    final w = width(context);
    final h = w * 9 / 16;
    return SizedBox(
      width: w,
      child: FocusTile(
        onTap: onTap,
        builder: (on) => Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Container(
            width: w,
            height: h,
            decoration: BoxDecoration(
              borderRadius: BorderRadius.circular(10),
              border: Border.all(color: on ? kAccent : Colors.transparent, width: 2.5),
            ),
            child: ClipRRect(
              borderRadius: BorderRadius.circular(8),
              child: Stack(fit: StackFit.expand, children: [
                if (logoMode)
                  Container(
                    decoration: const BoxDecoration(
                        gradient: LinearGradient(colors: [Color(0xFF232A3D), Color(0xFF10131B)],
                            begin: Alignment.topLeft, end: Alignment.bottomRight)),
                    padding: EdgeInsets.fromLTRB(w * .2, h * .14, w * .2, h * .3),
                    child: NetImg(image, fallbackText: overlay.isEmpty ? title : overlay, fit: BoxFit.contain, radius: 0, cacheWidth: 400),
                  )
                else
                  NetImg(image, fallbackText: title, radius: 0, cacheWidth: 640),
                if (overlay.isNotEmpty)
                  const DecoratedBox(
                    decoration: BoxDecoration(
                      gradient: LinearGradient(
                          begin: Alignment.topCenter, end: Alignment.bottomCenter,
                          stops: [0.5, 1], colors: [Colors.transparent, Color(0xC0000000)]),
                    ),
                  ),
                if (overlay.isNotEmpty)
                  Positioned(
                    left: 10, right: 10, bottom: 8,
                    child: Text(overlay, maxLines: 1, overflow: TextOverflow.ellipsis,
                        style: const TextStyle(fontWeight: FontWeight.w800, fontSize: 13, color: Colors.white)),
                  ),
                if (badge == 'LIVE') const Positioned(right: 8, top: 8, child: Pill('LIVE')),
                if (badge.isNotEmpty && badge != 'LIVE') Positioned(left: 8, top: 8, child: Pill(badge, size: 9)),
                if (time.isNotEmpty) Positioned(left: 8, top: 8, child: Pill(time, color: kBlue, size: 11)),
                if (progress > 0) Positioned(left: 0, right: 0, bottom: 0, child: ProgressLine(progress)),
              ]),
            ),
          ),
          const SizedBox(height: 6),
          Text(title, maxLines: 1, overflow: TextOverflow.ellipsis,
              style: TextStyle(fontWeight: FontWeight.w600, fontSize: 14, color: on ? Colors.white : kText)),
          if (sub.isNotEmpty) Text(sub, maxLines: 1, overflow: TextOverflow.ellipsis, style: const TextStyle(color: kMuted, fontSize: 11.5)),
        ]),
      ),
    );
  }
}

class ChannelCard extends StatelessWidget {
  final Item item;
  final VoidCallback onTap;
  final bool fav;
  const ChannelCard({super.key, required this.item, required this.onTap, this.fav = false});
  static double width(BuildContext c) => 150 * uiScale(c);
  @override
  Widget build(BuildContext context) {
    final w = width(context);
    return SizedBox(
      width: w,
      child: FocusTile(
        onTap: onTap,
        builder: (on) => Column(children: [
          Container(
            width: w,
            height: w * .6,
            padding: const EdgeInsets.all(12),
            decoration: BoxDecoration(
              color: on ? const Color(0xFF232734) : const Color(0xFF191C25),
              borderRadius: BorderRadius.circular(10),
              border: Border.all(color: on ? kAccent : Colors.transparent, width: 2.5),
            ),
            child: Stack(fit: StackFit.expand, children: [
              NetImg(item.logo, fallbackText: item.title, fit: BoxFit.contain, radius: 4, cacheWidth: 300),
              if (fav) const Positioned(right: -4, top: -8, child: Text('★', style: TextStyle(color: Color(0xFFFFC940), fontSize: 16))),
            ]),
          ),
          const SizedBox(height: 6),
          Text(item.title.isEmpty ? item.name : item.title,
              textAlign: TextAlign.center, maxLines: 2, overflow: TextOverflow.ellipsis,
              style: TextStyle(fontWeight: FontWeight.w700, fontSize: 12.5, color: on ? Colors.white : kText)),
        ]),
      ),
    );
  }
}

class ActorCard extends StatelessWidget {
  final String name;
  final String role;
  final String photo;
  final VoidCallback onTap;
  const ActorCard({super.key, required this.name, this.role = '', this.photo = '', required this.onTap});
  static double width(BuildContext c) => 110 * uiScale(c);
  @override
  Widget build(BuildContext context) {
    final w = width(context);
    return SizedBox(
      width: w,
      child: FocusTile(
        onTap: onTap,
        radius: w,
        builder: (on) => Column(children: [
          Container(
            width: w * .9,
            height: w * .9,
            decoration: BoxDecoration(shape: BoxShape.circle, border: Border.all(color: on ? kAccent : Colors.transparent, width: 3)),
            child: NetImg(photo, fallbackText: name, circle: true, cacheWidth: 240),
          ),
          const SizedBox(height: 6),
          Text(name, textAlign: TextAlign.center, maxLines: 2, overflow: TextOverflow.ellipsis,
              style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 12.5)),
          if (role.isNotEmpty)
            Text(role, textAlign: TextAlign.center, maxLines: 1, overflow: TextOverflow.ellipsis,
                style: const TextStyle(color: kMuted, fontSize: 11)),
        ]),
      ),
    );
  }
}

class CatTileCard extends StatelessWidget {
  final CatTile tile;
  final VoidCallback onTap;
  const CatTileCard({super.key, required this.tile, required this.onTap});
  static Size size(BuildContext c) => Size(200 * uiScale(c), 84 * uiScale(c));
  @override
  Widget build(BuildContext context) {
    final s = size(context);
    final live = tile.kind == 'live';
    return SizedBox(
      width: s.width,
      height: s.height,
      child: FocusTile(
        onTap: onTap,
        builder: (on) => Container(
          decoration: BoxDecoration(
            color: kCard,
            borderRadius: BorderRadius.circular(12),
            border: Border.all(color: on ? kAccent : const Color(0xFF2C3140), width: on ? 2 : 1),
          ),
          child: ClipRRect(
            borderRadius: BorderRadius.circular(11),
            child: Stack(fit: StackFit.expand, children: [
              if (!tile.special && tile.logo.isNotEmpty && !live) ...[
                NetImg(tile.logo, radius: 0, cacheWidth: 400),
                const DecoratedBox(
                  decoration: BoxDecoration(
                      gradient: LinearGradient(colors: [Color(0xEB0A0C12), Color(0x960A0C12), Color(0x3C0A0C12)], stops: [0, .6, 1])),
                ),
              ],
              if (live && tile.logo.isNotEmpty)
                Positioned(right: 10, top: 0, bottom: 0, width: 56,
                    child: Center(child: SizedBox(height: 40, child: NetImg(tile.logo, fit: BoxFit.contain, radius: 0, cacheWidth: 160)))),
              Padding(
                padding: EdgeInsets.fromLTRB(14, 8, live ? 74 : 12, 8),
                child: Row(children: [
                  if (tile.special)
                    Padding(
                      padding: const EdgeInsets.only(right: 10),
                      child: Icon(
                          tile.kind == 'live' ? Icons.live_tv : (tile.kind == 'series' ? Icons.video_library : Icons.movie_outlined),
                          color: kText, size: 26),
                    ),
                  Expanded(
                    child: Column(mainAxisAlignment: MainAxisAlignment.center, crossAxisAlignment: CrossAxisAlignment.start, children: [
                      Text(tile.name, maxLines: 2, overflow: TextOverflow.ellipsis,
                          style: const TextStyle(fontWeight: FontWeight.w800, fontSize: 14, color: Colors.white)),
                      if (tile.sub.isNotEmpty)
                        Text(tile.sub, maxLines: 1, overflow: TextOverflow.ellipsis, style: const TextStyle(color: kMuted, fontSize: 11)),
                    ]),
                  ),
                ]),
              ),
            ]),
          ),
        ),
      ),
    );
  }
}

/// Rangée horizontale titrée : « Titre › » + sous-titre + badge.
class Section extends StatelessWidget {
  final String title;
  final String subtitle;
  final String badge;
  final VoidCallback? onMore;
  final double height;
  final int count;
  final IndexedWidgetBuilder itemBuilder;
  final double spacing;
  const Section({super.key, required this.title, this.subtitle = '', this.badge = '', this.onMore, required this.height,
      required this.count, required this.itemBuilder, this.spacing = 12});
  @override
  Widget build(BuildContext context) {
    final pad = isWide(context) ? 32.0 : 16.0;
    return Padding(
      padding: const EdgeInsets.only(top: 22),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        if (title.isNotEmpty)
          Padding(
            padding: EdgeInsets.symmetric(horizontal: pad),
            child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Expanded(
                child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                  InkWell(
                    onTap: onMore,
                    child: Row(mainAxisSize: MainAxisSize.min, children: [
                      Flexible(
                        child: Text(title, maxLines: 1, overflow: TextOverflow.ellipsis,
                            style: TextStyle(fontSize: 19 * uiScale(context), fontWeight: FontWeight.w700, color: Colors.white)),
                      ),
                      if (onMore != null) const Padding(padding: EdgeInsets.only(left: 4), child: Icon(Icons.chevron_right, color: kAccent)),
                    ]),
                  ),
                  if (subtitle.isNotEmpty) Text(subtitle, style: const TextStyle(color: kMuted, fontSize: 12.5)),
                ]),
              ),
              if (badge.isNotEmpty) Pill(badge, size: 11),
            ]),
          ),
        const SizedBox(height: 10),
        SizedBox(
          height: height,
          child: ListView.separated(
            scrollDirection: Axis.horizontal,
            padding: EdgeInsets.symmetric(horizontal: pad),
            itemCount: count,
            separatorBuilder: (_, __) => SizedBox(width: spacing),
            itemBuilder: itemBuilder,
          ),
        ),
      ]),
    );
  }
}

// ----------------------------------------------------------------- profils / logo
class AvatarView extends StatelessWidget {
  final Map<String, dynamic> profile;
  final double size;
  final bool circle;
  const AvatarView(this.profile, {super.key, this.size = 120, this.circle = false});
  @override
  Widget build(BuildContext context) {
    final c = Color((profile['color'] as num?)?.toInt() ?? kAvatarColors.first);
    final emoji = '${profile['emoji'] ?? ''}';
    final name = '${profile['name'] ?? '?'}';
    final hsl = HSLColor.fromColor(c);
    return Container(
      width: size,
      height: size,
      decoration: BoxDecoration(
        shape: circle ? BoxShape.circle : BoxShape.rectangle,
        borderRadius: circle ? null : BorderRadius.circular(size * .16),
        gradient: LinearGradient(
          colors: [hsl.withLightness(clampD(hsl.lightness + .12, 0, 1)).toColor(),
            hsl.withLightness(clampD(hsl.lightness - .15, 0, 1)).toColor()],
          begin: Alignment.topLeft, end: Alignment.bottomRight,
        ),
      ),
      alignment: Alignment.center,
      child: Text(emoji.isNotEmpty ? emoji : (name.isEmpty ? '?' : name[0].toUpperCase()),
          style: TextStyle(fontSize: size * (emoji.isNotEmpty ? .5 : .46), fontWeight: FontWeight.w800, color: Colors.white)),
    );
  }
}

class Logo extends StatelessWidget {
  final double height;
  final bool darkBackground;
  const Logo({super.key, this.height = 36, this.darkBackground = true});
  @override
  Widget build(BuildContext context) => Image.asset(
        darkBackground ? 'assets/logo_dark.png' : 'assets/logo_light.png',
        height: height,
        filterQuality: FilterQuality.high,
        errorBuilder: (_, __, ___) => Text(kAppTitle, style: TextStyle(fontSize: height * .6, fontWeight: FontWeight.w900)),
      );
}

/// Signature manuscrite « Asvind ».
class Signature extends StatelessWidget {
  final double size;
  const Signature({super.key, this.size = 18});
  @override
  Widget build(BuildContext context) => Container(
        padding: const EdgeInsets.fromLTRB(10, 0, 12, 2),
        decoration: BoxDecoration(color: const Color(0xD20A0C10), borderRadius: BorderRadius.circular(10)),
        child: Text(kAppAuthor,
            style: TextStyle(
              fontFamily: 'cursive',
              fontFamilyFallback: const ['Snell Roundhand', 'Savoye LET', 'Noteworthy'],
              fontStyle: FontStyle.italic,
              fontSize: size,
              color: Colors.white.withValues(alpha: .85),
            )),
      );
}

void toast(BuildContext context, String msg) {
  ScaffoldMessenger.of(context)
    ..hideCurrentSnackBar()
    ..showSnackBar(SnackBar(content: Text(msg), duration: const Duration(seconds: 3)));
}

String hostOf(String url) => Uri.tryParse(url)?.host ?? url;

// gardé pour les usages futurs (en-têtes vidéo)
const kVideoHeaders = {'User-Agent': kUserAgent};
