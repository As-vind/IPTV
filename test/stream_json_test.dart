import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:iptv_player/core/net.dart';
import 'package:iptv_player/ui/theme.dart';
import 'package:iptv_player/ui/widgets.dart';

List<Map<String, dynamic>> scan(String json, int chunk) {
  final out = <Map<String, dynamic>>[];
  final sc = JsonObjectScanner(out.add);
  final b = utf8.encode(json);
  for (var i = 0; i < b.length; i += chunk) {
    sc.add(b.sublist(i, i + chunk > b.length ? b.length : i + chunk));
  }
  sc.close();
  return out;
}

void main() {
  test('catalogue lu objet par objet, quel que soit le découpage', () {
    const j = '[{"name":"Film {1}","stream_id":1,"x":[1,{"a":"]"}]},'
        ' {"name":"Été \\"2\\"","stream_id":2}, {"name":"Ünï","stream_id":3}]';
    for (final c in [1, 2, 3, 7, 64, 4096]) {
      final r = scan(j, c);
      expect(r.length, 3, reason: 'morceaux de $c');
      expect(r[0]['name'], 'Film {1}');
      expect(r[1]['name'], 'Été "2"');
      expect(r[2]['name'], 'Ünï');
    }
  });

  test('objet de fiches (clé → fiche) aussi accepté', () {
    final r = scan('{"10":{"name":"a"},"11":{"name":"b"}}', 5);
    expect(r.map((e) => e['name']), ['a', 'b']);
  });

  test('réponse invalide signalée', () {
    expect(() => scan('null', 2), throwsFormatException);
  });

  testWidgets('options : les flèches passent d\'un choix à l\'autre', (t) async {
    var sel = 'fr';
    await t.pumpWidget(MaterialApp(
      theme: buildTheme(),
      home: Scaffold(
        body: StatefulBuilder(
          builder: (c, set) => Wrap(children: [
            for (final l in ['fr', 'en', 'es'])
              OptChip(label: Text(l), selected: sel == l, autofocus: l == 'fr', onSelected: (_) => set(() => sel = l)),
          ]),
        ),
      ),
    ));
    await t.pumpAndSettle();
    String cur() => (FocusManager.instance.primaryFocus!.context!.findAncestorWidgetOfExactType<OptChip>()!.label as Text).data!;
    expect(cur(), 'fr');
    await t.sendKeyEvent(LogicalKeyboardKey.arrowRight);
    await t.pumpAndSettle();
    expect(cur(), 'en');
    await t.sendKeyEvent(LogicalKeyboardKey.enter);
    await t.pumpAndSettle();
    expect(sel, 'en');
    await t.sendKeyEvent(LogicalKeyboardKey.arrowRight);
    await t.pumpAndSettle();
    expect(cur(), 'es');
  });
}
