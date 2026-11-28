import 'package:flutter/material.dart';

/// Couleurs fixes (identiques en thème sombre et clair).
const kRed = Color(0xFFE8252C);
const kAccent = Color(0xFF2E8BFF);
const kBlue = Color(0xFF1A5FD8);

/// Palette complète d'un thème. L'interface lit toujours les couleurs par leurs noms (kBg, kText…),
/// qui renvoient celles du thème actif : changer de thème change toute l'application.
class Pal {
  final bool light;
  final Color bg, bar, sideTop, sideBottom, card, card2, border, border2, text, ink, muted, soft;
  final Color panel, surf, hi, focus, sel, ph1, ph2, phText, heroFade, field;
  const Pal({
    required this.light, required this.bg, required this.bar, required this.sideTop, required this.sideBottom,
    required this.card, required this.card2, required this.border, required this.border2, required this.text,
    required this.ink, required this.muted, required this.soft, required this.panel, required this.surf,
    required this.hi, required this.focus, required this.sel, required this.ph1, required this.ph2,
    required this.phText, required this.heroFade, required this.field,
  });

  /// Sombre : noir bleuté, texte blanc (le thème d'origine).
  static const dark = Pal(
    light: false, bg: Color(0xFF040506), bar: Color(0xFF0A0C10), sideTop: Color(0xFF2A3440), sideBottom: Color(0xFF10151C),
    card: Color(0xFF1B1F2A), card2: Color(0xFF141821), border: Color(0xFF262B38), border2: Color(0xFF3A4254),
    text: Color(0xFFE6E8EE), ink: Color(0xFFFFFFFF), muted: Color(0xFF9AA0B2), soft: Color(0xFFC9CCD6),
    panel: Color(0xFF161A23), surf: Color(0xFF141821), hi: Color(0xFF22324A), focus: Color(0xFFFFFFFF),
    sel: Color(0xFF2E8BFF), ph1: Color(0xFF262A38), ph2: Color(0xFF1A1D27), phText: Color(0xFF5D6478),
    heroFade: Color(0xFF040506), field: Color(0xFF141821),
  );

  /// Clair : fond blanc bleuté, texte bleu nuit, menu latéral bleu.
  static const lightPal = Pal(
    light: true, bg: Color(0xFFF3F6FC), bar: Color(0xFFFFFFFF), sideTop: Color(0xFF2F6FF0), sideBottom: Color(0xFF1747B8),
    card: Color(0xFFFFFFFF), card2: Color(0xFFEAF0FB), border: Color(0xFFD4DCEC), border2: Color(0xFFAEBBD4),
    text: Color(0xFF17233F), ink: Color(0xFF0E1A36), muted: Color(0xFF56627E), soft: Color(0xFF3F4C6A),
    panel: Color(0xFFFFFFFF), surf: Color(0xFFFFFFFF), hi: Color(0xFFD6E5FF), focus: Color(0xFF0B3FB8),
    sel: Color(0xFF1A5FD8), ph1: Color(0xFFE4EAF6), ph2: Color(0xFFD2DBEE), phText: Color(0xFF8A97B3),
    heroFade: Color(0xFF0B1630), field: Color(0xFFFFFFFF),
  );
}

Pal _pal = Pal.dark;

/// Active la palette sombre ou claire (appelé avant de reconstruire l'interface).
void setPalette(bool light) => _pal = light ? Pal.lightPal : Pal.dark;

bool get kLight => _pal.light;
Color get kBg => _pal.bg;
Color get kBar => _pal.bar;
Color get kSideTop => _pal.sideTop;
Color get kSideBottom => _pal.sideBottom;
Color get kCard => _pal.card;
Color get kCard2 => _pal.card2;
Color get kBorder => _pal.border;
Color get kBorder2 => _pal.border2;
Color get kText => _pal.text;
Color get kInk => _pal.ink;
Color get kMuted => _pal.muted;
Color get kSoft => _pal.soft;
Color get kPanel => _pal.panel;
Color get kSurf => _pal.surf;
Color get kHi => _pal.hi;
Color get kFocus => _pal.focus;
Color get kSel => _pal.sel;
Color get kPhA => _pal.ph1;
Color get kPhB => _pal.ph2;
Color get kPhText => _pal.phText;
Color get kHeroFade => _pal.heroFade;
Color get kField => _pal.field;

ThemeData buildTheme({bool light = false}) {
  setPalette(light);
  final p = _pal;
  final base = ThemeData(
    brightness: light ? Brightness.light : Brightness.dark,
    useMaterial3: true,
    scaffoldBackgroundColor: p.bg,
    colorScheme: light
        ? ColorScheme.light(primary: p.sel, secondary: p.sel, surface: p.card, onSurface: p.text, onPrimary: Colors.white)
        : ColorScheme.dark(primary: kAccent, secondary: kAccent, surface: p.card2),
    splashFactory: InkRipple.splashFactory,
  );
  return base.copyWith(
    textTheme: base.textTheme.apply(bodyColor: p.text, displayColor: p.ink),
    iconTheme: IconThemeData(color: p.ink),
    dividerColor: p.border,
    appBarTheme: AppBarTheme(
        backgroundColor: p.bar, elevation: 0, surfaceTintColor: Colors.transparent,
        foregroundColor: p.ink, iconTheme: IconThemeData(color: p.ink)),
    dialogTheme: DialogThemeData(backgroundColor: p.panel, surfaceTintColor: Colors.transparent),
    popupMenuTheme: PopupMenuThemeData(color: p.panel, surfaceTintColor: Colors.transparent,
        textStyle: TextStyle(color: p.text, fontSize: 14)),
    snackBarTheme: SnackBarThemeData(
      backgroundColor: light ? const Color(0xFF17233F) : const Color(0xFF1C2029),
      contentTextStyle: const TextStyle(color: Colors.white, fontWeight: FontWeight.w600),
      behavior: SnackBarBehavior.floating,
    ),
    inputDecorationTheme: InputDecorationTheme(
      filled: true,
      fillColor: p.field,
      contentPadding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
      hintStyle: TextStyle(color: p.muted),
      labelStyle: TextStyle(color: p.muted),
      border: OutlineInputBorder(borderRadius: BorderRadius.circular(10), borderSide: BorderSide(color: p.border2)),
      enabledBorder: OutlineInputBorder(borderRadius: BorderRadius.circular(10), borderSide: BorderSide(color: p.border2)),
      focusedBorder: OutlineInputBorder(borderRadius: BorderRadius.circular(10), borderSide: BorderSide(color: p.sel, width: 2)),
    ),
    // Bouton principal : blanc sur sombre, bleu plein sur clair.
    filledButtonTheme: FilledButtonThemeData(
      style: FilledButton.styleFrom(
        backgroundColor: light ? p.sel : Colors.white,
        foregroundColor: light ? Colors.white : Colors.black,
        padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 14),
        shape: const StadiumBorder(),
        textStyle: const TextStyle(fontWeight: FontWeight.w800, fontSize: 15),
      ).copyWith(
        side: WidgetStateBorderSide.resolveWith(
            (st) => st.contains(WidgetState.focused) ? BorderSide(color: light ? p.focus : kAccent, width: 4) : BorderSide.none),
      ),
    ),
    outlinedButtonTheme: OutlinedButtonThemeData(
      style: OutlinedButton.styleFrom(
        foregroundColor: p.ink,
        backgroundColor: p.ink.withValues(alpha: 0.06),
        side: BorderSide(color: p.ink.withValues(alpha: 0.25)),
        padding: const EdgeInsets.symmetric(horizontal: 18, vertical: 14),
        shape: const StadiumBorder(),
        textStyle: const TextStyle(fontWeight: FontWeight.w600, fontSize: 15),
      ).copyWith(
        side: WidgetStateBorderSide.resolveWith((st) => st.contains(WidgetState.focused)
            ? BorderSide(color: p.focus, width: 3)
            : BorderSide(color: p.ink.withValues(alpha: 0.25))),
      ),
    ),
    // Options (choix) : forme rectangulaire arrondie, bien distincte des boutons « pilule ».
    //  choisie  = bleu plein + texte blanc gras + coche ✓ ;
    //  non choisie = fond neutre, contour fin, texte normal ;
    //  sous la télécommande = gros contour (blanc sur sombre, bleu foncé sur clair).
    chipTheme: base.chipTheme.copyWith(
      color: WidgetStateProperty.resolveWith((st) {
        if (st.contains(WidgetState.selected)) return p.sel;
        if (st.contains(WidgetState.focused)) return p.hi;
        return light ? p.card2 : p.card2;
      }),
      side: WidgetStateBorderSide.resolveWith((st) {
        if (st.contains(WidgetState.focused)) return BorderSide(color: p.focus, width: 3);
        if (st.contains(WidgetState.selected)) return BorderSide(color: light ? p.sel : Colors.white, width: 2);
        return BorderSide(color: p.border2, width: 1.2);
      }),
      labelStyle: WidgetStateTextStyle.resolveWith((st) => TextStyle(
          color: st.contains(WidgetState.selected) ? Colors.white : p.text,
          fontWeight: st.contains(WidgetState.selected) ? FontWeight.w800 : FontWeight.w500)),
      checkmarkColor: Colors.white,
      iconTheme: IconThemeData(color: p.ink),
      padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 8),
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
    ),
    textButtonTheme: TextButtonThemeData(
      style: ButtonStyle(
        foregroundColor: WidgetStatePropertyAll(light ? p.sel : Colors.white),
        side: WidgetStateBorderSide.resolveWith(
            (st) => st.contains(WidgetState.focused) ? BorderSide(color: p.focus, width: 3) : BorderSide.none),
        shape: const WidgetStatePropertyAll(StadiumBorder()),
        padding: const WidgetStatePropertyAll(EdgeInsets.symmetric(horizontal: 18, vertical: 12)),
      ),
    ),
    // Interrupteur : activé = bleu plein + coche dans le rond ; désactivé = gris avec contour.
    switchTheme: SwitchThemeData(
      thumbColor: WidgetStateProperty.resolveWith((st) => st.contains(WidgetState.selected) ? Colors.white : p.muted),
      trackColor: WidgetStateProperty.resolveWith((st) => st.contains(WidgetState.selected) ? p.sel : p.card2),
      trackOutlineColor: WidgetStateProperty.resolveWith(
          (st) => st.contains(WidgetState.selected) ? p.sel : (st.contains(WidgetState.focused) ? p.focus : p.border2)),
      thumbIcon: WidgetStateProperty.resolveWith(
          (st) => st.contains(WidgetState.selected) ? Icon(Icons.check, color: p.sel, size: 16) : null),
    ),
    sliderTheme: SliderThemeData(
      activeTrackColor: p.sel,
      inactiveTrackColor: p.border2,
      thumbColor: p.sel,
      overlayColor: p.sel.withValues(alpha: .2),
      valueIndicatorColor: p.sel,
    ),
    listTileTheme: ListTileThemeData(selectedColor: p.sel, iconColor: p.ink, textColor: p.text),
    focusColor: p.ink.withValues(alpha: 0.16),
    progressIndicatorTheme: ProgressIndicatorThemeData(color: p.sel, linearTrackColor: p.ink.withValues(alpha: .12)),
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
