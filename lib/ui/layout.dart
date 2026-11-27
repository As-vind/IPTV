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

/// Diagonale de l'écran en pouces : choisie dans Paramètres → Affichage
/// (Android ne donne pas la vraie taille d'un téléviseur), 0 = inconnue.
int inchesOf(BuildContext context, Device d) {
  final v = int.tryParse('${AppScope.of(context).pset['ui_inches'] ?? 'auto'}');
  if (v != null) return v;
  return (d == Device.tv || d == Device.projector) ? 55 : 0;
}

/// Plus l'écran est grand, plus on peut afficher de titres sans que ce soit petit.
double _inchFactor(int inches) {
  if (inches <= 0) return 1.0;
  if (inches <= 32) return 1.2;
  if (inches <= 50) return 1.1;
  if (inches <= 58) return 1.0;
  if (inches <= 68) return .92;
  if (inches <= 78) return .85;
  return .78;
}

/// Taille du texte et des menus (« Taille de l'interface » sur Automatique).
double autoUiScale(BuildContext context) {
  final d = deviceOf(context);
  if (d != Device.tv && d != Device.projector) {
    final i = inchesOf(context, d);
    return i >= 27 ? 0.9 : 1.0; // grand moniteur d'ordinateur
  }
  return (0.8 * _inchFactor(inchesOf(context, d))).clamp(0.62, 0.96);
}

/// Rapport largeur / hauteur : 4/3 ≈ 1,33 ; 16/9 ≈ 1,78 ; 21/9 ≈ 2,33.
double aspectOf(BuildContext context) {
  final sz = MediaQuery.sizeOf(context);
  return sz.height <= 0 ? 16 / 9 : sz.width / sz.height;
}

/// Échelle finale des cases pour une zone de contenu donnée.
double layoutK(BuildContext context, double w, double h) {
  final d = deviceOf(context);
  final phone = d == Device.phone;
  final inch = d == Device.phone || d == Device.tablet ? 1.0 : _inchFactor(inchesOf(context, d));
  return clampK(scaleFor(w, h, phone) * densityOf(d) * inch, .4, 1.6);
}

/// Hauteur maximale du grand bandeau d'accueil, en part de la hauteur d'écran.
double heroMaxFraction(BuildContext context) {
  final d = deviceOf(context);
  final a = aspectOf(context);
  var f = (d == Device.tv || d == Device.projector) ? .6 : .8;
  if (a < 1.5) f = (f - .1); // 4/3, 5/4 : on garde de la place pour les rangées
  return f;
}

bool layoutPhone(BuildContext context) => deviceOf(context) == Device.phone;
