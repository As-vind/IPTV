// Coque principale : en-tête (logo, onglets, recherche, avatar) + pages.
import 'package:flutter/material.dart';

import '../core/store.dart';
import 'browse.dart';
import 'categories.dart';
import 'home.dart';
import 'scope.dart';
import 'search.dart';
import 'settings.dart';
import 'theme.dart';
import 'widgets.dart';

class Shell extends StatefulWidget {
  const Shell({super.key});
  @override
  State<Shell> createState() => _ShellState();
}

class _ShellState extends State<Shell> with SingleTickerProviderStateMixin {
  static const tabs = ['Accueil', 'Films', 'Séries', 'Chaînes TV', 'Catégories', 'Ma liste'];
  late final TabController _tc = TabController(length: tabs.length, vsync: this);
  String? _lastError;

  @override
  void initState() {
    super.initState();
    _tc.addListener(() => setState(() {}));
  }

  @override
  void dispose() {
    _tc.dispose();
    super.dispose();
  }

  void _openSearch() => Navigator.of(context).push(MaterialPageRoute(builder: (_) => const SearchScreen()));
  void _openSettings() => Navigator.of(context).push(MaterialPageRoute(builder: (_) => const SettingsScreen()));

  Widget _avatarMenu(AppState s) {
    return PopupMenuButton<String>(
      tooltip: 'Profil',
      color: const Color(0xFF161A23),
      offset: const Offset(0, 46),
      onSelected: (v) {
        if (v == 'switch') {
          s.logoutProfile();
        } else if (v == 'settings') {
          _openSettings();
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
      child: Padding(padding: const EdgeInsets.all(4), child: AvatarView(s.profile!, size: 34, circle: true)),
    );
  }

  @override
  Widget build(BuildContext context) {
    final s = AppScope.of(context);
    final wide = isWide(context);
    if (s.error != null && s.error != _lastError) {
      _lastError = s.error;
      WidgetsBinding.instance.addPostFrameCallback((_) => toast(context, s.error!));
    }
    final tabBar = TabBar(
      controller: _tc,
      isScrollable: true,
      tabAlignment: TabAlignment.start,
      dividerColor: Colors.transparent,
      indicatorColor: kAccent,
      indicatorWeight: 3,
      indicatorSize: TabBarIndicatorSize.label,
      labelColor: Colors.white,
      unselectedLabelColor: const Color(0xFFAEB3C2),
      labelStyle: const TextStyle(fontWeight: FontWeight.w700, fontSize: 16),
      unselectedLabelStyle: const TextStyle(fontWeight: FontWeight.w600, fontSize: 16),
      tabs: [for (final t in tabs) Tab(text: t)],
    );
    final header = Container(
      color: kBar,
      child: SafeArea(
        bottom: false,
        child: Column(children: [
          SizedBox(
            height: 60,
            child: Row(children: [
              SizedBox(width: wide ? 26 : 14),
              InkWell(onTap: () => _tc.animateTo(0), child: const Logo(height: 34)),
              if (wide) ...[const SizedBox(width: 24), Expanded(child: tabBar)] else const Spacer(),
              IconButton(tooltip: 'Rechercher', onPressed: _openSearch, icon: const Icon(Icons.search, size: 26)),
              IconButton(tooltip: 'Paramètres', onPressed: _openSettings, icon: const Icon(Icons.settings_outlined)),
              _avatarMenu(s),
              SizedBox(width: wide ? 18 : 8),
            ]),
          ),
          if (!wide) Align(alignment: Alignment.centerLeft, child: tabBar),
          if (s.loading) const LinearProgressIndicator(minHeight: 2, color: kAccent, backgroundColor: Colors.transparent),
          const Divider(height: 1, color: Color(0xFF1C1F28)),
        ]),
      ),
    );
    Widget page;
    switch (_tc.index) {
      case 1:
        page = const BrowseView(key: ValueKey('movie'), kind: 'movie');
        break;
      case 2:
        page = const BrowseView(key: ValueKey('series'), kind: 'series');
        break;
      case 3:
        page = const BrowseView(key: ValueKey('live'), kind: 'live');
        break;
      case 4:
        page = const CategoriesView();
        break;
      case 5:
        page = const FavoritesView();
        break;
      default:
        page = HomeView(onTab: (i) => _tc.animateTo(i));
    }
    return PopScope(
      canPop: _tc.index == 0,
      onPopInvokedWithResult: (didPop, _) {
        if (!didPop) _tc.animateTo(0);
      },
      child: Scaffold(
        body: Stack(children: [
          Column(children: [header, Expanded(child: page)]),
          const Positioned(left: 12, bottom: 10, child: IgnorePointer(child: Signature(size: 17))),
        ]),
      ),
    );
  }
}
