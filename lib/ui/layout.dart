// Disposition « intelligente » selon l'appareil : téléphone, tablette, ordinateur, TV, vidéoprojecteur.
import 'package:flutter/widgets.dart';

import 'scope.dart';
import 'theme.dart';

enum Device { phone, tablet, desktop, tv, projector }

const deviceLabels = {
  Device.phone: 'Téléphone',
  Device.tablet: 'Tablette',
  Device.desktop: 'Ordinateur',
  Device.tv: 'Télévision',
  Device.projector: 'Vidéoprojecteur',
};

/// Appareil choisi dans Paramètres → Affichage, ou détecté automatiquement.
Device deviceOf(BuildContext context) {
  final s = AppScope.of(context);
  final v = '${s.pset['ui_device'] ?? 'auto'}';
  for (final d in Device.values) {
    if (d.name == v) return d;
  }
  if (s.sys.isTv) return Device.tv;
  if (isPhone(context)) return Device.phone;
  final sz = MediaQuery.sizeOf(context);
  return sz.shortestSide < 900 ? Device.tablet : Device.desktop;
}

/// Densité des cases : sur TV / vidéoprojecteur on voit plus de titres à la fois,
/// les cases ne mangent plus la moitié de l'écran.
double densityOf(Device d) => switch (d) {
      Device.phone => 1.0,
      Device.tablet => 0.92,
      Device.desktop => 1.0,
      Device.tv => 0.74,
      Device.projector => 0.82,
    };

/// Échelle finale des cases pour une zone de contenu donnée.
double layoutK(BuildContext context, double w, double h) {
  final d = deviceOf(context);
  final phone = d == Device.phone;
  return clampK(scaleFor(w, h, phone) * densityOf(d), .45, 1.6);
}

bool layoutPhone(BuildContext context) => deviceOf(context) == Device.phone;
