import 'package:flutter/material.dart';

const kBg = Color(0xFF040506);
const kBar = Color(0xFF0A0C10);
const kSideTop = Color(0xFF2A3440);
const kSideBottom = Color(0xFF10151C);
const kRed = Color(0xFFE8252C);
const kCard = Color(0xFF1B1F2A);
const kCard2 = Color(0xFF141821);
const kBorder = Color(0xFF262B38);
const kAccent = Color(0xFF2E8BFF);
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
        backgroundColor: Colors.white,
        foregroundColor: Colors.black,
        padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 14),
        shape: const StadiumBorder(),
        textStyle: const TextStyle(fontWeight: FontWeight.w800, fontSize: 15),
      ).copyWith(
        side: WidgetStateBorderSide.resolveWith(
            (st) => st.contains(WidgetState.focused) ? const BorderSide(color: kAccent, width: 4) : BorderSide.none),
      ),
    ),
    outlinedButtonTheme: OutlinedButtonThemeData(
      style: OutlinedButton.styleFrom(
        foregroundColor: Colors.white,
        backgroundColor: Colors.white.withValues(alpha: 0.08),
        side: BorderSide(color: Colors.white.withValues(alpha: 0.18)),
        padding: const EdgeInsets.symmetric(horizontal: 18, vertical: 14),
        shape: const StadiumBorder(),
        textStyle: const TextStyle(fontWeight: FontWeight.w600, fontSize: 15),
      ).copyWith(
        side: WidgetStateBorderSide.resolveWith((st) => st.contains(WidgetState.focused)
            ? const BorderSide(color: Colors.white, width: 3)
            : BorderSide(color: Colors.white.withValues(alpha: 0.18))),
      ),
    ),
    // Options : choisie = bleu plein + texte blanc ; sous la télécommande = gros contour blanc.
    chipTheme: base.chipTheme.copyWith(
      color: WidgetStateProperty.resolveWith((st) {
        if (st.contains(WidgetState.selected)) return kAccent;
        if (st.contains(WidgetState.focused)) return const Color(0xFF2A3A55);
        return kCard2;
      }),
      side: WidgetStateBorderSide.resolveWith((st) {
        if (st.contains(WidgetState.focused)) return const BorderSide(color: Colors.white, width: 3);
        if (st.contains(WidgetState.selected)) return const BorderSide(color: kAccent, width: 1.5);
        return const BorderSide(color: Color(0xFF3A4254));
      }),
      labelStyle: WidgetStateTextStyle.resolveWith((st) => TextStyle(
          color: Colors.white,
          fontWeight: st.contains(WidgetState.selected) ? FontWeight.w800 : FontWeight.w600)),
      checkmarkColor: Colors.white,
      iconTheme: const IconThemeData(color: Colors.white),
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(18)),
    ),
    textButtonTheme: TextButtonThemeData(
      style: ButtonStyle(
        foregroundColor: const WidgetStatePropertyAll(Colors.white),
        side: WidgetStateBorderSide.resolveWith(
            (st) => st.contains(WidgetState.focused) ? const BorderSide(color: Colors.white, width: 3) : BorderSide.none),
        shape: const WidgetStatePropertyAll(StadiumBorder()),
        padding: const WidgetStatePropertyAll(EdgeInsets.symmetric(horizontal: 18, vertical: 12)),
      ),
    ),
    switchTheme: SwitchThemeData(
      thumbColor: WidgetStateProperty.resolveWith((st) => st.contains(WidgetState.selected) ? Colors.white : kMuted),
      trackColor: WidgetStateProperty.resolveWith((st) => st.contains(WidgetState.selected) ? kAccent : kCard2),
    ),
    listTileTheme: const ListTileThemeData(selectedColor: kAccent),
    focusColor: Colors.white.withValues(alpha: 0.16),
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

/// Échelle des cases (même logique que la version Windows) : 1 pour une zone de contenu
/// d'environ 1100 × 760 ; plus petit sur téléphone, plus grand sur grand écran / TV.
double scaleFor(double w, double h, bool phone) {
  if (phone) return clampK(w / 700, .5, .9);
  final k = w / 1100 < h / 760 ? w / 1100 : h / 760;
  return clampK(k, .55, 1.6);
}

double clampK(double v, double lo, double hi) => v < lo ? lo : (v > hi ? hi : v);

/// Téléphone (en portrait ou en paysage) — une TV Android fait souvent 960 × 540 : ce n'est pas un téléphone.
/// Les téléphones allongés (412 × 915…) restent des téléphones.
bool isPhone(BuildContext context) {
  final s = MediaQuery.sizeOf(context);
  return s.shortestSide < 480 || (s.shortestSide < 600 && s.longestSide < 900);
}

/// Mise à l'échelle transmise aux pages (calculée d'après la zone de contenu réelle).
class UiK extends InheritedWidget {
  final double k;
  final bool phone;
  const UiK({super.key, required this.k, required this.phone, required super.child});
  static UiK of(BuildContext c) => c.dependOnInheritedWidgetOfExactType<UiK>() ?? const UiK(k: 1, phone: false, child: SizedBox());
  @override
  bool updateShouldNotify(UiK old) => old.k != k || old.phone != phone;
}
