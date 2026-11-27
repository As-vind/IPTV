import 'dart:io';

import 'dart:ui' show PlatformDispatcher;

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:media_kit/media_kit.dart';

import 'core/net.dart';
import 'core/store.dart';
import 'ui/profiles.dart';
import 'ui/scope.dart';
import 'ui/shell.dart';
import 'ui/theme.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  MediaKit.ensureInitialized();
  HttpOverrides.global = LaxHttpOverrides();
  SystemChrome.setSystemUIOverlayStyle(const SystemUiOverlayStyle(
    statusBarColor: Colors.transparent,
    statusBarIconBrightness: Brightness.light,
    systemNavigationBarColor: kBar,
  ));
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

class IptvApp extends StatelessWidget {
  final AppState state;
  const IptvApp({super.key, required this.state});
  @override
  Widget build(BuildContext context) {
    return AppScope(
      state: state,
      child: Shortcuts(
        shortcuts: const <ShortcutActivator, Intent>{
          SingleActivator(LogicalKeyboardKey.select): ActivateIntent(),
          SingleActivator(LogicalKeyboardKey.gameButtonA): ActivateIntent(),
        },
        child: MaterialApp(
          title: kAppTitle,
          debugShowCheckedModeBanner: false,
          theme: buildTheme(),
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
    final f = v == 'auto' ? (s.sys.isTv ? 0.8 : 1.0) : (int.tryParse(v) ?? 100) / 100;
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
