import 'dart:io';

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
