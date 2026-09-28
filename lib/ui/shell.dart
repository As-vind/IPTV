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

const _kSidebarW = 290.0;

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

  bool _collapsed(AppState s) => s.cfg['sidebar_collapsed'] == true;

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
    final collapsed = !phone && _collapsed(s);
    final size = MediaQuery.sizeOf(context);
    final side = (!phone && !collapsed) ? _kSidebarW : 0.0;
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
    if (phone) {
      final phoneKeys = ['home', 'movie', 'series', 'live', 'favorites'];
      body = Scaffold(
        body: Stack(children: [
          stack,
          Positioned(
            top: 0, right: 4,
            child: SafeArea(
              child: Row(children: [
                _roundIcon(Icons.search, () => go('search')),
                if (s.downloadsEnabled) _roundIcon(Icons.download_outlined, () => go('downloads')),
                _avatarMenu(s, size: 30),
              ]),
            ),
          ),
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
          if (!collapsed) _sidebar(s),
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

  Widget _roundIcon(IconData ic, VoidCallback onTap) => Padding(
        padding: const EdgeInsets.all(4),
        child: Material(
          color: const Color(0x8C0A0E16),
          shape: const CircleBorder(),
          child: InkWell(
            customBorder: const CircleBorder(),
            onTap: onTap,
            child: SizedBox(width: 40, height: 40, child: Icon(ic, color: Colors.white, size: 22)),
          ),
        ),
      );

  // ---------------------------------------------------------------- menu latéral
  Widget _sidebar(AppState s) {
    return Container(
      width: _kSidebarW,
      decoration: const BoxDecoration(
        gradient: LinearGradient(colors: [kSideTop, kSideBottom], begin: Alignment.topLeft, end: Alignment.bottomRight),
        border: Border(right: BorderSide(color: Color(0x12FFFFFF))),
      ),
      child: SafeArea(
        right: false,
        child: Padding(
          padding: const EdgeInsets.fromLTRB(18, 16, 18, 12),
          child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
            Row(children: [
              _glassPill('Modifier', () => go('settings')),
              const Spacer(),
              _glassRound(Icons.view_sidebar_outlined, () => _setCollapsed(s, true), tip: 'Replier le menu'),
            ]),
            const SizedBox(height: 22),
            const Align(alignment: Alignment.centerLeft, child: Logo(height: 44)),
            const SizedBox(height: 18),
            Expanded(
              child: ListView(padding: EdgeInsets.zero, children: [
                for (final n in _nav)
                  if (n.key != 'downloads' || s.downloadsEnabled) _navItem(n),
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

  Widget _navItem(_NavDef n) {
    final sel = _root == n.key;
    return Padding(
      padding: const EdgeInsets.only(bottom: 4),
      child: Material(
        color: sel ? Colors.white.withValues(alpha: .13) : Colors.transparent,
        shape: const StadiumBorder(),
        child: InkWell(
          customBorder: const StadiumBorder(),
          focusColor: Colors.white.withValues(alpha: .18),
          onTap: () => go(n.key),
          child: Padding(
            padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 11),
            child: Row(children: [
              Icon(n.icon, color: kAccent, size: 28),
              const SizedBox(width: 16),
              Flexible(
                child: Text(n.label, maxLines: 1, overflow: TextOverflow.ellipsis,
                    style: const TextStyle(fontSize: 19, fontWeight: FontWeight.w600, color: Colors.white)),
              ),
            ]),
          ),
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

  Widget _glassPill(String text, VoidCallback onTap) => Material(
        color: Colors.white.withValues(alpha: .1),
        shape: StadiumBorder(side: BorderSide(color: Colors.white.withValues(alpha: .14))),
        child: InkWell(
          customBorder: const StadiumBorder(),
          onTap: onTap,
          child: Padding(
            padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 10),
            child: Text(text, style: const TextStyle(fontSize: 16, fontWeight: FontWeight.w600, color: Colors.white)),
          ),
        ),
      );

  Widget _glassRound(IconData ic, VoidCallback onTap, {String? tip}) => Tooltip(
        message: tip ?? '',
        child: Material(
          color: Colors.white.withValues(alpha: .1),
          shape: CircleBorder(side: BorderSide(color: Colors.white.withValues(alpha: .14))),
          child: InkWell(
            customBorder: const CircleBorder(),
            onTap: onTap,
            child: SizedBox(width: 46, height: 46, child: Icon(ic, color: Colors.white, size: 22)),
          ),
        ),
      );

  // ---------------------------------------------------------------- barre flottante (menu replié)
  Widget _pillBar(AppState s) {
    Widget tab(String key, {String? text, IconData? icon}) {
      final sel = _root == key;
      return Material(
        color: sel ? const Color(0xC00A0E16) : Colors.transparent,
        shape: const StadiumBorder(),
        child: InkWell(
          customBorder: const StadiumBorder(),
          onTap: () => go(key),
          child: Padding(
            padding: EdgeInsets.symmetric(horizontal: text != null ? 16 : 12, vertical: 9),
            child: text != null
                ? Text(text, style: TextStyle(fontSize: 16, fontWeight: FontWeight.w600, color: sel ? kAccent : Colors.white))
                : Icon(icon, size: 22, color: sel ? kAccent : Colors.white),
          ),
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
          Material(
            color: Colors.transparent,
            shape: const StadiumBorder(),
            child: InkWell(
              customBorder: const StadiumBorder(),
              onTap: () => _setCollapsed(s, false),
              child: const Padding(
                padding: EdgeInsets.symmetric(horizontal: 12, vertical: 9),
                child: Icon(Icons.view_sidebar_outlined, size: 22, color: Colors.white),
              ),
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
