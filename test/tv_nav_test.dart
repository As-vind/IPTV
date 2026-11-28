// Navigation à la télécommande (écran TV 960 × 540) : le clavier ne s'ouvre jamais tout seul,
// les flèches parcourent tous les champs sans blocage, OK ouvre la saisie, OK / Retour la ferment.
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:iptv_player/core/playlist_import.dart';
import 'package:iptv_player/ui/settings.dart';
import 'package:iptv_player/ui/theme.dart';
import 'package:iptv_player/ui/tv_field.dart';
import 'package:iptv_player/ui/widgets.dart';

String focusName() {
  final ctx = FocusManager.instance.primaryFocus?.context;
  if (ctx == null) return 'aucun';
  final tv = ctx.findAncestorWidgetOfExactType<TvTextField>();
  if (tv != null) return 'champ:${tv.label}';
  if (ctx.findAncestorWidgetOfExactType<FocusCard>() != null) return 'carte';
  final chip = ctx.findAncestorWidgetOfExactType<OptChip>();
  if (chip != null) return 'puce:${(chip.label as Text).data}';
  final btn = ctx.findAncestorWidgetOfExactType<TextButton>() ?? ctx.findAncestorWidgetOfExactType<FilledButton>();
  if (btn != null && btn.child is Text) return 'bouton:${(btn.child as Text).data}';
  if (ctx.findAncestorWidgetOfExactType<EditableText>() != null || ctx.widget is EditableText) return 'saisie';
  return ctx.widget.runtimeType.toString();
}

bool editing() => FocusManager.instance.primaryFocus?.context?.findAncestorWidgetOfExactType<EditableText>() != null;

Future<void> key(WidgetTester t, LogicalKeyboardKey k) async {
  await t.sendKeyEvent(k);
  await t.pumpAndSettle();
}

void main() {
  Future<void> openDialog(WidgetTester t) async {
    t.view.physicalSize = const Size(1920, 1080);
    t.view.devicePixelRatio = 2; // 960 × 540 : une TV Android
    addTearDown(t.view.reset);
    await t.pumpWidget(MaterialApp(
      theme: buildTheme(),
      home: Scaffold(
        body: Builder(builder: (c) => Center(child: TextButton(onPressed: () => showSourceDialog(c), child: const Text('ouvrir')))),
      ),
    ));
    await t.tap(find.text('ouvrir'));
    await t.pumpAndSettle();
  }

  testWidgets('les flèches parcourent tous les champs sans ouvrir le clavier', (t) async {
    await openDialog(t);
    await t.tap(find.text('Compte Xtream'));
    await t.pumpAndSettle();
    final seen = <String>[];
    for (var i = 0; i < 9; i++) {
      await key(t, LogicalKeyboardKey.arrowDown);
      seen.add(focusName());
      expect(t.testTextInput.isVisible, false, reason: 'clavier ouvert sur ${seen.last}');
      expect(editing(), false, reason: 'saisie activée sur ${seen.last}');
    }
    // tous les champs, y compris ceux du milieu et du bas, puis les puces et les boutons
    for (final f in ['champ:Nom (facultatif)', 'champ:Serveur', 'champ:Identifiant', 'champ:Mot de passe']) {
      expect(seen, contains(f));
    }
    expect(seen.any((e) => e.startsWith('puce:ts') || e.startsWith('puce:m3u8')), true, reason: '$seen');
    expect(seen.any((e) => e == 'bouton:Ajouter' || e == 'bouton:Annuler'), true, reason: '$seen');
    // et on remonte jusqu'en haut sans blocage
    for (var i = 0; i < 9; i++) {
      await key(t, LogicalKeyboardKey.arrowUp);
      expect(t.testTextInput.isVisible, false);
      expect(editing(), false);
    }
    expect(focusName(), startsWith('puce:'));
  });

  testWidgets('OK ouvre la saisie au-dessus du clavier, OK valide, Retour annule', (t) async {
    await openDialog(t);
    await t.tap(find.text('Compte Xtream'));
    await t.pumpAndSettle();
    while (focusName() != 'champ:Identifiant') {
      await key(t, LogicalKeyboardKey.arrowDown);
    }
    // OK : la saisie s'ouvre dans le panneau du haut (jamais caché par le clavier)
    await key(t, LogicalKeyboardKey.select);
    expect(editing(), true);
    expect(t.testTextInput.isVisible, true);
    final box = t.getRect(find.byType(EditableText).last);
    expect(box.bottom < 540 / 2, true, reason: 'la zone de saisie doit être en haut de l’écran ($box)');
    t.testTextInput.enterText('bob');
    await t.testTextInput.receiveAction(TextInputAction.done);
    await t.pumpAndSettle();
    // validé : clavier fermé, valeur enregistrée, focus conservé sur le champ
    expect(editing(), false);
    expect(t.testTextInput.isVisible, false);
    expect(focusName(), 'champ:Identifiant');
    expect(find.text('bob'), findsOneWidget);
    // flèche bas : champ suivant, toujours sans clavier
    await key(t, LogicalKeyboardKey.arrowDown);
    expect(focusName(), 'champ:Mot de passe');
    expect(t.testTextInput.isVisible, false);
    // OK puis Retour : annulé, valeur inchangée, focus sur le champ
    await key(t, LogicalKeyboardKey.select);
    expect(editing(), true);
    t.testTextInput.enterText('secret');
    await t.binding.handlePopRoute();
    await t.pumpAndSettle();
    expect(editing(), false);
    expect(focusName(), 'champ:Mot de passe');
    expect(find.text('••••••'), findsNothing);
    // OK puis valider avec le bouton « Valider »
    await key(t, LogicalKeyboardKey.select);
    t.testTextInput.enterText('1234');
    await t.tap(find.text('Valider'));
    await t.pumpAndSettle();
    expect(find.text('••••'), findsOneWidget);
    expect(focusName(), 'champ:Mot de passe');
    expect(t.testTextInput.isVisible, false);
  });

  testWidgets('les autres modes : lien et fichier', (t) async {
    await openDialog(t);
    // Lien M3U (mode par défaut)
    for (var i = 0; i < 4 && focusName() != 'champ:Lien M3U'; i++) {
      await key(t, LogicalKeyboardKey.arrowDown);
      expect(t.testTextInput.isVisible, false);
    }
    expect(focusName(), 'champ:Lien M3U');
    expect(t.testTextInput.isVisible, false);
    // Fichier M3U : les deux grandes cartes et les boutons sont atteignables
    await t.tap(find.text('Fichier M3U'));
    await t.pumpAndSettle();
    final seen = <String>[];
    for (var i = 0; i < 6; i++) {
      await key(t, LogicalKeyboardKey.arrowDown);
      seen.add(focusName());
      expect(t.testTextInput.isVisible, false);
    }
    expect(seen.where((e) => e == 'carte').length, 2, reason: '$seen');
    expect(seen.any((e) => e.startsWith('bouton:')), true, reason: '$seen');
  });

  testWidgets('panneau « envoyer depuis un autre appareil » entièrement visible sur TV', (t) async {
    t.view.physicalSize = const Size(1920, 1080);
    t.view.devicePixelRatio = 2;
    addTearDown(t.view.reset);
    await t.pumpWidget(MaterialApp(
      theme: buildTheme(),
      home: Scaffold(
        body: Builder(
          builder: (c) => TextButton(
            onPressed: () => showDialog(context: c, builder: (_) => LanReceiveDialog(lan: LanImport(), address: 'http://192.168.1.50:8686')),
            child: const Text('ouvrir'),
          ),
        ),
      ),
    ));
    await t.tap(find.text('ouvrir'));
    await t.pump(const Duration(milliseconds: 400));
    await t.pump(const Duration(milliseconds: 400));
    final addr = t.getRect(find.text('http://192.168.1.50:8686'));
    expect(addr.bottom <= 540, true, reason: 'adresse hors écran : $addr');
    expect(find.text('Annuler'), findsOneWidget);
    expect(t.getRect(find.text('Annuler')).bottom <= 540, true);
    expect(focusName(), 'bouton:Annuler');
    expect(t.takeException(), isNull);
  });
}
