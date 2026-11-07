// Coque principale façon OCTO+ : menu latéral (tablette, TV) repliable en barre flottante, barre du bas (téléphone).
import 'package:flutter/material.dart';

import '../core/store.dart';
import 'browse.dart';
import 'downloads_view.dart';
import 'octo.dart';
import 'pages.dart';
import 'scope.dart';
import 'search.dart';
import 'settings.dart';
import 'theme.dart';
import 'widgets.dart';

/// Largeur du menu latéral : 290 sur grand écran, plus étroit sur tablette.
double _sidebarW(double w) => clampK(w * .23, 220, 290);

class _NavDef {
  final String key;
  final IconData icon;
  final String label;
  const _NavDef(this.key, this.icon, this.label);
}

const _nav = [
  _NavDef('home', Icons.home_outlined, 'Accueil'),
  _NavDef('movie', Icons.movie_outlined, 'Films'),
  _NavDef('series', Icons.theaters_outlined, 'Séries'),
  _NavDef('live', Icons.tv_outlined, 'Chaînes TV'),
  _NavDef('favorites', Icons.favorite_border, 'Ma liste'),
  _NavDef('downloads', Icons.download_outlined, 'Téléchargés'),
  _NavDef('search', Icons.search, 'Recherche'),
];

class Shell extends StatefulWidget {
  const Shell({super.key});
  @override
  State<Shell> createState() => _ShellState();
}

class _ShellState extends State<Shell> implements RootNavigator {
  String _root = 'home';
  final Set<String> _visited = {'home'};
  String? _lastError;
  bool _hookedDownloads = false;

  @override
  void go(String key) {
    if (key == 'settings') {
      Navigator.of(context).push(MaterialPageRoute(builder: (_) => const SettingsScreen()));
      return;
    }
    setState(() {
      _root = key;
      _visited.add(key);
    });
  }

  /// Menu replié : choix de l'utilisateur, sinon replié d'office sur les écrans étroits (tablette en portrait).
  bool _collapsed(AppState s, double w) {
    final v = s.cfg['sidebar_collapsed'];
    return v is bool ? v : w < 900;
  }

  void _setCollapsed(AppState s, bool v) {
    s.cfg['sidebar_collapsed'] = v;
    s.save();
    setState(() {});
  }

  Widget _page(String key, bool collapsed) => switch (key) {
        'home' => HomePage(collapsed: collapsed),
        'movie' => MediaPage(kind: 'movie', collapsed: collapsed),
        'series' => MediaPage(kind: 'series', collapsed: collapsed),
        'live' => LivePage(collapsed: collapsed),
        'favorites' => _Titled(title: 'Ma liste', collapsed: collapsed, child: const FavoritesView()),
        'downloads' => DownloadsView(collapsed: collapsed),
        'search' => SearchView(collapsed: collapsed),
        _ => const SizedBox.shrink(),
      };

  Widget _avatarMenu(AppState s, {double size = 34, bool withName = false}) {
    return PopupMenuButton<String>(
      tooltip: 'Profil',
      color: const Color(0xFF161A23),
      offset: const Offset(0, 46),
      onSelected: (v) {
        if (v == 'switch') {
          s.logoutProfile();
        } else if (v == 'settings') {
          go('settings');
        } else if (v.startsWith('p:')) {
          final id = v.substring(2);
          final p = s.profiles.firstWhere((e) => e['id'] == id);
          if ('${p['pin'] ?? ''}'.isNotEmpty) {
            s.logoutProfile();
          } else {
            s.selectProfile(id);
          }
        }
      },
      itemBuilder: (_) => [
        for (final p in s.profiles)
          PopupMenuItem(
            value: 'p:${p['id']}',
            child: Row(children: [
              AvatarView(p, size: 26, circle: true),
              const SizedBox(width: 10),
              Text('${p['name']}'),
              if (p['id'] == s.profile?['id']) const Padding(padding: EdgeInsets.only(left: 8), child: Icon(Icons.check, size: 16)),
            ]),
          ),
        const PopupMenuDivider(),
        const PopupMenuItem(value: 'switch', child: Text('⇄  Changer / gérer les profils')),
        const PopupMenuItem(value: 'settings', child: Text('⚙  Paramètres')),
      ],
      child: Padding(
        padding: EdgeInsets.symmetric(horizontal: withName ? 14 : 4, vertical: withName ? 9 : 4),
        child: Row(mainAxisSize: MainAxisSize.min, children: [
          AvatarView(s.profile!, size: size, circle: true),
          if (withName) ...[
            const SizedBox(width: 14),
            Text('${s.profile!['name']}', style: const TextStyle(fontSize: 18, fontWeight: FontWeight.w600, color: Colors.white)),
          ],
        ]),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final s = AppScope.of(context);
    if (!_hookedDownloads) {
      _hookedDownloads = true;
      s.downloads.onFinished = (msg) {
        if (mounted) toast(context, msg);
      };
    }
    if (s.error != null && s.error != _lastError) {
      _lastError = s.error;
      WidgetsBinding.instance.addPostFrameCallback((_) => toast(context, s.error!));
    }
    final phone = isPhone(context);
    final size = MediaQuery.sizeOf(context);
    final collapsed = !phone && _collapsed(s, size.width);
    final landscapePhone = phone && size.width > size.height;
    final side = (!phone && !collapsed) ? _sidebarW(size.width) : (landscapePhone ? 76.0 : 0.0);
    final k = scaleFor(size.width - side, size.height, phone);
    final keys = _nav.map((e) => e.key).toList();
    final stack = IndexedStack(
      index: keys.indexOf(_root),
      children: [
        for (final key in keys)
          TickerMode(
            enabled: key == _root,
            child: _visited.contains(key) ? _page(key, collapsed) : const SizedBox.shrink(),
          ),
      ],
    );

    Widget body;
    final phoneKeys = ['home', 'movie', 'series', 'live', 'favorites'];
    final topIcons = Positioned(
      top: 0, right: 4,
      child: SafeArea(
        child: Row(children: [
          _roundIcon(Icons.search, () => go('search'), tip: 'Recherche'),
          if (s.downloadsEnabled) _roundIcon(Icons.download_outlined, () => go('downloads'), tip: 'Téléchargements'),
          _avatarMenu(s, size: 30),
        ]),
      ),
    );
    if (landscapePhone) {
      // Téléphone couché : barre de navigation à gauche pour garder toute la hauteur aux images.
      body = Scaffold(
        body: Row(children: [
          Container(
            width: side,
            color: const Color(0xFF0B0F15),
            child: SafeArea(
              right: false,
              child: Column(children: [
                const SizedBox(height: 8),
                for (final key in phoneKeys)
                  Padding(
                    padding: const EdgeInsets.symmetric(vertical: 3),
                    child: NavButton(
                      circle: true,
                      selected: _root == key,
                      tooltip: _nav.firstWhere((e) => e.key == key).label,
                      onTap: () => go(key),
                      child: SizedBox(
                          width: 50, height: 50,
                          child: Icon(_nav.firstWhere((e) => e.key == key).icon, color: kAccent, size: 25)),
                    ),
                  ),
              ]),
            ),
          ),
          Expanded(
            child: Stack(children: [
              Positioned.fill(child: stack),
              topIcons,
              if (s.loading)
                const Positioned(top: 0, left: 0, right: 0,
                    child: LinearProgressIndicator(minHeight: 2, color: kAccent, backgroundColor: Colors.transparent)),
            ]),
          ),
        ]),
      );
    } else if (phone) {
      body = Scaffold(
        body: Stack(children: [
          stack,
          topIcons,
          if (s.loading)
            const Positioned(top: 0, left: 0, right: 0, child: LinearProgressIndicator(minHeight: 2, color: kAccent, backgroundColor: Colors.transparent)),
        ]),
        bottomNavigationBar: NavigationBar(
          backgroundColor: const Color(0xFF0B0F15),
          indicatorColor: Colors.white.withValues(alpha: .12),
          height: 64,
          labelBehavior: NavigationDestinationLabelBehavior.alwaysShow,
          selectedIndex: phoneKeys.contains(_root) ? phoneKeys.indexOf(_root) : 0,
          onDestinationSelected: (i) => go(phoneKeys[i]),
          destinations: [
            for (final key in phoneKeys)
              NavigationDestination(
                icon: Icon(_nav.firstWhere((e) => e.key == key).icon, color: kAccent),
                label: _nav.firstWhere((e) => e.key == key).label,
              ),
          ],
        ),
      );
    } else {
      body = Scaffold(
        body: Row(children: [
          if (!collapsed) _sidebar(s, side),
          Expanded(
            child: Stack(children: [
              Positioned.fill(child: stack),
              if (collapsed)
                Positioned(top: 0, left: 0, right: 0, child: SafeArea(child: Center(child: _pillBar(s)))),
              if (collapsed)
                const Positioned(left: 14, bottom: 10, child: IgnorePointer(child: Signature(size: 17))),
              if (s.loading && collapsed)
                const Positioned(top: 0, left: 0, right: 0,
                    child: LinearProgressIndicator(minHeight: 2, color: kAccent, backgroundColor: Colors.transparent)),
            ]),
          ),
        ]),
      );
    }
    return PopScope(
      canPop: _root == 'home',
      onPopInvokedWithResult: (didPop, _) {
        if (!didPop) go('home');
      },
      child: RootNav(nav: this, child: UiK(k: k, phone: phone, child: body)),
    );
  }

  Widget _roundIcon(IconData ic, VoidCallback onTap, {String? tip}) => Padding(
        padding: const EdgeInsets.all(4),
        child: NavButton(
          circle: true,
          color: const Color(0x8C0A0E16),
          tooltip: tip,
          onTap: onTap,
          child: SizedBox(width: 44, height: 44, child: Icon(ic, color: Colors.white, size: 22)),
        ),
      );

  // ---------------------------------------------------------------- menu latéral
  Widget _sidebar(AppState s, double w) {
    final f = w / 290;
    return Container(
      width: w,
      decoration: const BoxDecoration(
        gradient: LinearGradient(colors: [kSideTop, kSideBottom], begin: Alignment.topLeft, end: Alignment.bottomRight),
        border: Border(right: BorderSide(color: Color(0x12FFFFFF))),
      ),
      child: SafeArea(
        right: false,
        child: Padding(
          padding: EdgeInsets.fromLTRB(18 * f, 16, 18 * f, 12),
          child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
            Row(children: [
              _glassPill('Modifier', () => go('settings')),
              const Spacer(),
              _glassRound(Icons.view_sidebar_outlined, () => _setCollapsed(s, true), tip: 'Replier le menu'),
            ]),
            const SizedBox(height: 22),
            Align(alignment: Alignment.centerLeft, child: Logo(height: 44 * f)),
            const SizedBox(height: 18),
            Expanded(
              child: ListView(padding: EdgeInsets.zero, children: [
                for (final n in _nav)
                  if (n.key != 'downloads' || s.downloadsEnabled) _navItem(n, f),
                _profileItem(s),
              ]),
            ),
            const Text('SOURCE', style: TextStyle(color: Color(0xFF6B7183), fontSize: 11, fontWeight: FontWeight.w700, letterSpacing: 1)),
            const SizedBox(height: 6),
            _sourcePicker(s),
            if (s.loading) const Padding(padding: EdgeInsets.only(top: 8), child: LinearProgressIndicator(minHeight: 2, color: kAccent)),
            const SizedBox(height: 10),
            const Align(alignment: Alignment.centerLeft, child: Signature(size: 19)),
          ]),
        ),
      ),
    );
  }

  Widget _navItem(_NavDef n, double f) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 4),
      child: NavButton(
        selected: _root == n.key,
        onTap: () => go(n.key),
        child: Padding(
          padding: EdgeInsets.symmetric(horizontal: 16 * f, vertical: 11),
          child: Row(children: [
            Icon(n.icon, color: kAccent, size: 28 * clampK(f, .85, 1.0)),
            SizedBox(width: 16 * f),
            Flexible(
              child: Text(n.label, maxLines: 1, overflow: TextOverflow.ellipsis,
                  style: TextStyle(fontSize: 19 * clampK(f, .86, 1.0), fontWeight: FontWeight.w600, color: Colors.white)),
            ),
          ]),
        ),
      ),
    );
  }

  Widget _profileItem(AppState s) => Align(alignment: Alignment.centerLeft, child: _avatarMenu(s, size: 34, withName: true));

  Widget _sourcePicker(AppState s) {
    final srcs = s.sources;
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 12),
      decoration: BoxDecoration(
        color: Colors.white.withValues(alpha: .08),
        borderRadius: BorderRadius.circular(18),
        border: Border.all(color: Colors.white.withValues(alpha: .12)),
      ),
      child: DropdownButtonHideUnderline(
        child: DropdownButton<String>(
          isExpanded: true,
          dropdownColor: const Color(0xFF161A23),
          value: srcs.any((x) => x['id'] == s.currentSource?['id']) ? '${s.currentSource!['id']}' : null,
          hint: const Text('Aucune source'),
          items: [
            for (final x in srcs)
              DropdownMenuItem(value: '${x['id']}', child: Text('${x['type'] == 'xtream' ? '📡' : '📄'} ${x['name']}', overflow: TextOverflow.ellipsis)),
            const DropdownMenuItem(value: '__add__', child: Text('＋ Ajouter une source…')),
          ],
          onChanged: (v) {
            if (v == '__add__') {
              showSourceDialog(context);
            } else if (v != null) {
              s.setSource(v);
            }
          },
        ),
      ),
    );
  }

  Widget _glassPill(String text, VoidCallback onTap) => NavButton(
        color: Colors.white.withValues(alpha: .1),
        side: BorderSide(color: Colors.white.withValues(alpha: .14)),
        onTap: onTap,
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 10),
          child: Text(text, style: const TextStyle(fontSize: 16, fontWeight: FontWeight.w600, color: Colors.white)),
        ),
      );

  Widget _glassRound(IconData ic, VoidCallback onTap, {String? tip}) => NavButton(
        circle: true,
        color: Colors.white.withValues(alpha: .1),
        side: BorderSide(color: Colors.white.withValues(alpha: .14)),
        tooltip: tip,
        onTap: onTap,
        child: SizedBox(width: 46, height: 46, child: Icon(ic, color: Colors.white, size: 22)),
      );

  // ---------------------------------------------------------------- barre flottante (menu replié)
  Widget _pillBar(AppState s) {
    Widget tab(String key, {String? text, IconData? icon}) {
      final sel = _root == key;
      return NavButton(
        selected: sel,
        selectedColor: const Color(0xC00A0E16),
        onTap: () => go(key),
        child: Padding(
          padding: EdgeInsets.symmetric(horizontal: text != null ? 16 : 12, vertical: 9),
          child: text != null
              ? Text(text, style: TextStyle(fontSize: 16, fontWeight: FontWeight.w600, color: sel ? kAccent : Colors.white))
              : Icon(icon, size: 22, color: sel ? kAccent : Colors.white),
        ),
      );
    }

    return Container(
      margin: const EdgeInsets.only(top: 14),
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 5),
      decoration: BoxDecoration(
        color: const Color(0xE128303E),
        borderRadius: BorderRadius.circular(30),
        border: Border.all(color: Colors.white.withValues(alpha: .16)),
      ),
      child: SingleChildScrollView(
        scrollDirection: Axis.horizontal,
        child: Row(mainAxisSize: MainAxisSize.min, children: [
          NavButton(
            tooltip: 'Afficher le menu',
            onTap: () => _setCollapsed(s, false),
            child: const Padding(
              padding: EdgeInsets.symmetric(horizontal: 12, vertical: 9),
              child: Icon(Icons.view_sidebar_outlined, size: 22, color: Colors.white),
            ),
          ),
          tab('home', text: 'Accueil'),
          tab('movie', text: 'Films'),
          tab('series', text: 'Séries'),
          tab('live', text: 'Chaînes TV'),
          tab('favorites', icon: Icons.favorite_border),
          if (s.downloadsEnabled) tab('downloads', icon: Icons.download_outlined),
          tab('search', icon: Icons.search),
        ]),
      ),
    );
  }
}

/// Page simple avec un grand titre.
class _Titled extends StatelessWidget {
  final String title;
  final bool collapsed;
  final Widget child;
  const _Titled({required this.title, required this.collapsed, required this.child});
  @override
  Widget build(BuildContext context) => SafeArea(
        bottom: false,
        child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
          PageTitle(title, top: collapsed ? 96 : (isPhone(context) ? 16 : 38)),
          Expanded(child: child),
        ]),
      );
}
