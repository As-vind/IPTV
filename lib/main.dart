import 'dart:io';

import 'dart:ui' show PlatformDispatcher;

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:media_kit/media_kit.dart';

import 'core/net.dart';
import 'core/store.dart';
import 'ui/layout.dart';
import 'ui/profiles.dart';
import 'ui/scope.dart';
import 'ui/shell.dart';
import 'ui/theme.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  MediaKit.ensureInitialized();
  HttpOverrides.global = LaxHttpOverrides();
  final state = AppState();
  await state.init();
  // Erreurs : notées dans le journal (Paramètres → Journal, administration web) au lieu de passer inaperçues.
  FlutterError.onError = (d) {
    state.log('Erreur : ${d.exceptionAsString()}${d.library != null ? ' (${d.library})' : ''}');
    FlutterError.presentError(d);
  };
  PlatformDispatcher.instance.onError = (e, st) {
    state.log('Erreur : $e');
    return true;
  };
  // Mémoire des images limitée selon l'appareil (les TV ont souvent peu de mémoire)
  final ic = PaintingBinding.instance.imageCache;
  final low = state.hwTier == 'low' || state.sys.lowRam || (state.sys.totalMb > 0 && state.sys.totalMb < 2600);
  ic.maximumSizeBytes = (low ? 40 : state.sys.isTv ? 70 : 120) << 20;
  ic.maximumSize = low ? 250 : 500;
  runApp(IptvApp(state: state));
}

class IptvApp extends StatefulWidget {
  final AppState state;
  const IptvApp({super.key, required this.state});

  /// Thème choisi : sombre, clair, ou automatique (suit le réglage de l'appareil).
  static bool wantsLight(AppState s) {
    final v = '${s.pset['ui_theme'] ?? 'dark'}';
    if (v == 'light') return true;
    if (v == 'auto') return PlatformDispatcher.instance.platformBrightness == Brightness.light;
    return false;
  }

  @override
  State<IptvApp> createState() => _IptvAppState();
}

/// L'application n'est reconstruite que si le thème change vraiment (et non à chaque mise à jour de l'état :
/// sinon tout l'écran se redessine sans arrêt et la navigation à la télécommande devient lourde).
class _IptvAppState extends State<IptvApp> {
  late bool _light;
  late ThemeData _theme;

  @override
  void initState() {
    super.initState();
    _apply(IptvApp.wantsLight(widget.state));
    widget.state.addListener(_onState);
  }

  @override
  void dispose() {
    widget.state.removeListener(_onState);
    super.dispose();
  }

  void _apply(bool light) {
    _light = light;
    _theme = buildTheme(light: light); // active aussi la palette (setPalette)
    SystemChrome.setSystemUIOverlayStyle(SystemUiOverlayStyle(
      statusBarColor: Colors.transparent,
      statusBarIconBrightness: light ? Brightness.dark : Brightness.light,
      systemNavigationBarColor: kBar,
      systemNavigationBarIconBrightness: light ? Brightness.dark : Brightness.light,
    ));
  }

  void _onState() {
    final l = IptvApp.wantsLight(widget.state);
    if (l != _light) setState(() => _apply(l));
  }

  @override
  Widget build(BuildContext context) {
    return AppScope(
      state: widget.state,
      child: Shortcuts(
        shortcuts: const <ShortcutActivator, Intent>{
          SingleActivator(LogicalKeyboardKey.select): ActivateIntent(),
          SingleActivator(LogicalKeyboardKey.gameButtonA): ActivateIntent(),
        },
        child: MaterialApp(
          key: ValueKey(_light),
          title: kAppTitle,
          debugShowCheckedModeBanner: false,
          theme: _theme,
          themeAnimationDuration: Duration.zero,
          builder: (context, child) => UiScale(child: child ?? const SizedBox()),
          home: const RootGate(),
        ),
      ),
    );
  }
}

class RootGate extends StatelessWidget {
  const RootGate({super.key});
  @override
  Widget build(BuildContext context) {
    final s = AppScope.of(context);
    return s.profile == null ? const ProfilesScreen() : const Shell();
  }
}

/// Taille de l'interface : réduite automatiquement sur TV (sinon tout paraît énorme sur un grand écran).
class UiScale extends StatelessWidget {
  final Widget child;
  const UiScale({super.key, required this.child});
  @override
  Widget build(BuildContext context) {
    final s = AppScope.of(context);
    final v = '${s.pset['ui_scale'] ?? 'auto'}';
    final f = v == 'auto' ? autoUiScale(context) : (int.tryParse(v) ?? 100) / 100;
    if ((f - 1).abs() < .01) return child;
    final mq = MediaQuery.of(context);
    final size = mq.size / f;
    return MediaQuery(
      data: mq.copyWith(
        size: size,
        devicePixelRatio: mq.devicePixelRatio * f,
        padding: mq.padding / f,
        viewPadding: mq.viewPadding / f,
        viewInsets: mq.viewInsets / f,
      ),
      child: FittedBox(
        fit: BoxFit.fill,
        alignment: Alignment.topLeft,
        child: SizedBox(width: size.width, height: size.height, child: child),
      ),
    );
  }
}
