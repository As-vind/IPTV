// Informations système (Android) et journal des fermetures inattendues.
// - TV détectée par Android lui-même (mode « télévision ») ;
// - mémoire de l'appareil ;
// - raison exacte de la dernière fermeture de l'application (manque de mémoire, plantage, blocage…).
import 'dart:convert';
import 'dart:io';

import 'package:flutter/services.dart';

const _ch = MethodChannel('iptv/system');

class SystemInfo {
  bool isTv = false;
  int totalMb = 0, availMb = 0, memoryClass = 0;
  bool lowRam = false;

  Future<void> load() async {
    if (!Platform.isAndroid) return;
    try {
      isTv = await _ch.invokeMethod<bool>('isTv') ?? false;
    } catch (_) {}
    try {
      final m = Map<String, dynamic>.from(await _ch.invokeMethod<Map>('memory') ?? {});
      totalMb = ((m['total'] as num?) ?? 0) ~/ 1048576;
      availMb = ((m['avail'] as num?) ?? 0) ~/ 1048576;
      memoryClass = (m['memoryClass'] as num?)?.toInt() ?? 0;
      lowRam = m['lowRam'] == true;
    } catch (_) {}
  }

  static const _reasons = {
    1: 'arrêt demandé par l’application',
    2: 'arrêtée par le système (signal)',
    3: 'mémoire insuffisante : Android a fermé l’application',
    4: 'plantage (Java)',
    5: 'plantage natif (lecteur vidéo, images ou pilote)',
    6: 'application bloquée (ANR)',
    7: 'échec au démarrage',
    9: 'utilisation excessive des ressources',
    10: 'fermée par l’utilisateur',
    11: 'arrêtée par l’utilisateur',
    12: 'un service dont elle dépend s’est arrêté',
    13: 'autre raison',
    14: 'mise en veille par le système',
    16: 'application mise à jour',
  };

  /// Dernières fermetures de l'application, en clair.
  Future<List<String>> lastExits() async {
    if (!Platform.isAndroid) return [];
    try {
      final l = await _ch.invokeMethod<List>('lastExits') ?? const [];
      return [
        for (final e in l)
          () {
            final m = Map<String, dynamic>.from(e as Map);
            final t = DateTime.fromMillisecondsSinceEpoch((m['time'] as num?)?.toInt() ?? 0);
            final r = (m['reason'] as num?)?.toInt() ?? 0;
            final pss = ((m['pss'] as num?) ?? 0) ~/ 1024;
            final d = '${m['description'] ?? ''}'.trim();
            return '${_two(t.day)}/${_two(t.month)} ${_two(t.hour)}:${_two(t.minute)} — ${_reasons[r] ?? 'raison $r'}'
                '${pss > 0 ? ' · mémoire utilisée $pss Mo' : ''}${d.isNotEmpty ? ' · $d' : ''}';
          }()
      ];
    } catch (_) {
      return [];
    }
  }

  static String _two(int x) => x.toString().padLeft(2, '0');
}

/// Repère une fermeture inattendue : un fichier « session » reste présent si l'application
/// n'a pas été quittée ou mise en arrière-plan normalement.
class SessionGuard {
  final File f;
  SessionGuard(Directory dir) : f = File('${dir.path}/session.json');

  /// Renvoie la dernière page affichée si la session précédente s'est mal terminée.
  Future<String?> previousCrash() async {
    try {
      if (!await f.exists()) return null;
      final d = jsonDecode(await f.readAsString()) as Map;
      return d['open'] == true ? '${d['page'] ?? ''}' : null;
    } catch (_) {
      return null;
    }
  }

  void mark({required bool open, String page = ''}) {
    try {
      f.writeAsStringSync(jsonEncode({'open': open, 'page': page, 'time': DateTime.now().toIso8601String()}));
    } catch (_) {}
  }
}
