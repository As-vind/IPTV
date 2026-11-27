// Cache disque des pochettes / affiches : au redémarrage elles s'affichent tout de suite,
// sans tout retélécharger. Nettoyé avec le reste du cache (Paramètres → Maintenance).
import 'dart:async';
import 'dart:io';
import 'dart:ui' as ui;

import 'package:flutter/foundation.dart';
import 'package:flutter/painting.dart';

import 'net.dart';
import 'text.dart';

class DiskImage extends ImageProvider<DiskImage> {
  /// Dossier du cache (fixé au démarrage) ; vide = pas de cache disque.
  static String dir = '';
  static const _maxBytes = 8 * 1024 * 1024;

  final String url;
  const DiskImage(this.url);

  @override
  Future<DiskImage> obtainKey(ImageConfiguration configuration) => SynchronousFuture(this);

  @override
  ImageStreamCompleter loadImage(DiskImage key, ImageDecoderCallback decode) =>
      MultiFrameImageStreamCompleter(codec: _load(decode), scale: 1.0, debugLabel: url);

  Future<ui.Codec> _load(ImageDecoderCallback decode) async {
    Uint8List? bytes;
    final f = dir.isEmpty ? null : File('$dir/${fnv(url)}.img');
    if (f != null && await f.exists()) {
      try {
        bytes = await f.readAsBytes();
        if (bytes.isEmpty) bytes = null;
      } catch (_) {
        bytes = null;
      }
    }
    if (bytes == null) {
      final b = Uint8List.fromList(await getBytes(url, headers: const {'User-Agent': 'Mozilla/5.0'}, timeout: const Duration(seconds: 30)));
      if (b.isEmpty || b.length > _maxBytes) throw Exception('image invalide');
      bytes = b;
      if (f != null) {
        unawaited(() async {
          try {
            await f.parent.create(recursive: true);
            await f.writeAsBytes(b, flush: false);
          } catch (_) {}
        }());
      }
    }
    try {
      return await decode(await ui.ImmutableBuffer.fromUint8List(bytes));
    } catch (e) {
      // fichier abîmé : on l'efface pour qu'il soit retéléchargé
      if (f != null) unawaited(f.delete().then((_) {}, onError: (_) {}));
      rethrow;
    }
  }

  /// Télécharge à l'avance des pochettes dans le cache disque (en arrière-plan, quelques-unes à la fois),
  /// pour que la navigation soit fluide dès l'ouverture d'une page.
  static Future<int> prefetch(Iterable<String> urls, {int parallel = 4, int max = 1500}) async {
    if (dir.isEmpty) return 0;
    final todo = <String>[];
    for (final u in urls) {
      if (todo.length >= max) break;
      if (u.startsWith('http') && !await File('$dir/${fnv(u)}.img').exists()) todo.add(u);
    }
    if (todo.isEmpty) return 0;
    await Directory(dir).create(recursive: true);
    var i = 0, done = 0;
    Future<void> worker() async {
      while (i < todo.length) {
        final u = todo[i++];
        try {
          final b = await getBytes(u, headers: const {'User-Agent': 'Mozilla/5.0'}, timeout: const Duration(seconds: 20));
          if (b.isNotEmpty && b.length <= _maxBytes) {
            await File('$dir/${fnv(u)}.img').writeAsBytes(b, flush: false);
            done++;
          }
        } catch (_) {}
      }
    }
    await Future.wait([for (var k = 0; k < parallel; k++) worker()]);
    return done;
  }

  @override
  bool operator ==(Object other) => other is DiskImage && other.url == url;
  @override
  int get hashCode => url.hashCode;
}
