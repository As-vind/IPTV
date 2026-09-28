// Page Catégories : tuiles Films / Séries / Chaînes TV.
import 'package:flutter/material.dart';

import 'nav.dart';
import 'scope.dart';
import 'theme.dart';
import 'widgets.dart';

class CategoriesView extends StatefulWidget {
  final String initialKind;
  const CategoriesView({super.key, this.initialKind = 'movie'});
  @override
  State<CategoriesView> createState() => _CategoriesViewState();
}

class _CategoriesViewState extends State<CategoriesView> {
  late String _kind = widget.initialKind;
  static const _tabs = [('movie', 'Films'), ('series', 'Séries'), ('live', 'Chaînes TV')];

  @override
  Widget build(BuildContext context) {
    final s = AppScope.of(context);
    final tiles = s.categories(_kind);
    final pad = isWide(context) ? 32.0 : 16.0;
    final size = CatTileCard.size(context);
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      Padding(
        padding: EdgeInsets.fromLTRB(pad, 16, pad, 10),
        child: Wrap(spacing: 8, runSpacing: 8, crossAxisAlignment: WrapCrossAlignment.center, children: [
          for (final (k, label) in _tabs)
            ChoiceChip(
              label: Text(label),
              selected: _kind == k,
              showCheckmark: false,
              labelStyle: TextStyle(color: _kind == k ? kBg : kText, fontWeight: FontWeight.w700),
              onSelected: (_) => setState(() => _kind = k),
            ),
        ]),
      ),
      Expanded(
        child: tiles.isEmpty
            ? const Center(child: Text('Aucune catégorie.', style: TextStyle(color: kMuted)))
            : GridView.builder(
                padding: EdgeInsets.fromLTRB(pad, 4, pad, 70),
                gridDelegate: SliverGridDelegateWithMaxCrossAxisExtent(
                  maxCrossAxisExtent: size.width + 12,
                  mainAxisExtent: size.height,
                  crossAxisSpacing: 12,
                  mainAxisSpacing: 12,
                ),
                itemCount: tiles.length,
                itemBuilder: (c, i) => CatTileCard(tile: tiles[i], onTap: () => openCategory(c, tiles[i])),
              ),
      ),
    ]);
  }
}
