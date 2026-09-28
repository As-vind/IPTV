import 'package:flutter/material.dart';

const kBg = Color(0xFF0E1016);
const kBar = Color(0xFF0A0C10);
const kCard = Color(0xFF1B1F2A);
const kCard2 = Color(0xFF141821);
const kBorder = Color(0xFF262B38);
const kAccent = Color(0xFFE8252C);
const kBlue = Color(0xFF1A5FD8);
const kMuted = Color(0xFF9AA0B2);
const kText = Color(0xFFE6E8EE);

ThemeData buildTheme() {
  final base = ThemeData(
    brightness: Brightness.dark,
    useMaterial3: true,
    scaffoldBackgroundColor: kBg,
    colorScheme: const ColorScheme.dark(primary: kAccent, secondary: kAccent, surface: kCard2),
    splashFactory: InkRipple.splashFactory,
  );
  return base.copyWith(
    textTheme: base.textTheme.apply(bodyColor: kText, displayColor: Colors.white),
    appBarTheme: const AppBarTheme(backgroundColor: kBar, elevation: 0, surfaceTintColor: Colors.transparent),
    dialogTheme: const DialogThemeData(backgroundColor: Color(0xFF161A23)),
    snackBarTheme: const SnackBarThemeData(
      backgroundColor: Color(0xFF1C2029),
      contentTextStyle: TextStyle(color: Colors.white, fontWeight: FontWeight.w600),
      behavior: SnackBarBehavior.floating,
    ),
    inputDecorationTheme: InputDecorationTheme(
      filled: true,
      fillColor: kCard2,
      contentPadding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
      border: OutlineInputBorder(borderRadius: BorderRadius.circular(10), borderSide: const BorderSide(color: kBorder)),
      enabledBorder: OutlineInputBorder(borderRadius: BorderRadius.circular(10), borderSide: const BorderSide(color: kBorder)),
      focusedBorder: OutlineInputBorder(borderRadius: BorderRadius.circular(10), borderSide: const BorderSide(color: kAccent, width: 1.5)),
    ),
    filledButtonTheme: FilledButtonThemeData(
      style: FilledButton.styleFrom(
        backgroundColor: kAccent,
        foregroundColor: Colors.white,
        padding: const EdgeInsets.symmetric(horizontal: 22, vertical: 14),
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8)),
        textStyle: const TextStyle(fontWeight: FontWeight.w700, fontSize: 15),
      ),
    ),
    outlinedButtonTheme: OutlinedButtonThemeData(
      style: OutlinedButton.styleFrom(
        foregroundColor: Colors.white,
        backgroundColor: Colors.white.withValues(alpha: 0.08),
        side: BorderSide(color: Colors.white.withValues(alpha: 0.18)),
        padding: const EdgeInsets.symmetric(horizontal: 18, vertical: 14),
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8)),
        textStyle: const TextStyle(fontWeight: FontWeight.w600, fontSize: 15),
      ),
    ),
    chipTheme: base.chipTheme.copyWith(
      backgroundColor: kCard2,
      selectedColor: Colors.white,
      side: const BorderSide(color: kBorder),
      labelStyle: const TextStyle(fontWeight: FontWeight.w600),
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(18)),
    ),
    focusColor: kAccent.withValues(alpha: 0.25),
  );
}

/// Facteur d'échelle selon la taille d'écran (téléphone / tablette / TV).
double uiScale(BuildContext context) {
  final w = MediaQuery.sizeOf(context).shortestSide;
  if (w < 500) return 0.82;
  if (w < 800) return 1.0;
  return 1.1;
}

bool isWide(BuildContext context) => MediaQuery.sizeOf(context).width >= 760;
