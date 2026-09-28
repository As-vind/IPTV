// Navigation commune : ouvrir une fiche, un acteur, lancer la lecture.
import 'package:flutter/material.dart';

import '../core/models.dart';
import '../core/store.dart';
import 'browse.dart';
import 'categories.dart';
import 'detail.dart';
import 'person.dart';
import 'player.dart';

void openItem(BuildContext context, Item it, {List<Item>? playlist}) {
  if (it.kind == 'live') {
    final list = playlist ?? [it];
    final idx = list.indexOf(it);
    playItems(context, list.map(PlayItem.of).toList(), idx < 0 ? 0 : idx);
  } else {
    Navigator.of(context).push(MaterialPageRoute(builder: (_) => DetailScreen(item: it)));
  }
}

void playItems(BuildContext context, List<PlayItem> items, int index, {bool resume = true}) {
  Navigator.of(context).push(MaterialPageRoute(
      builder: (_) => PlayerScreen(items: items, index: index, resume: resume)));
}

void openPerson(BuildContext context, {required String name, int? id, String photo = '', String role = ''}) {
  Navigator.of(context).push(MaterialPageRoute(
      builder: (_) => PersonScreen(name: name, tmdbId: id, photo: photo, role: role)));
}

void openCategory(BuildContext context, CatTile t) {
  if (t.special) {
    Navigator.of(context).push(MaterialPageRoute(builder: (_) => Scaffold(
          appBar: AppBar(title: const Text('Catégories')),
          body: CategoriesView(initialKind: t.kind),
        )));
  } else {
    Navigator.of(context).push(MaterialPageRoute(builder: (_) => Scaffold(
          appBar: AppBar(title: Text(t.name)),
          body: BrowseView(kind: t.kind, initialGroup: t.group, compact: true),
        )));
  }
}
