// Import d'une liste M3U depuis un fichier : sélection sur l'appareil, ou envoi depuis un autre
// appareil du même réseau (téléphone, PC) — pratique sur une TV sans gestionnaire de fichiers.
import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'net.dart';

/// Vérifie le contenu et copie la liste dans le dossier de l'application.
/// Renvoie le chemin de la copie (la source reste lisible même si l'original est déplacé ou supprimé).
Future<String> savePlaylist(Directory dataDir, String id, List<int> bytes) async {
  final text = decodeBody(bytes);
  if (!text.toUpperCase().contains('#EXTINF')) {
    throw const FormatException("Ce fichier n'est pas une liste M3U (aucune ligne #EXTINF).");
  }
  final dir = Directory('${dataDir.path}/playlists');
  await dir.create(recursive: true);
  final f = File('${dir.path}/$id.m3u');
  await f.writeAsBytes(bytes, flush: true);
  return f.path;
}

/// Nombre d'entrées d'une liste (pour l'aperçu avant ajout).
int countEntries(List<int> bytes) =>
    RegExp(r'^#EXTINF', multiLine: true, caseSensitive: false).allMatches(decodeBody(bytes)).length;

/// Petit serveur web local : affiche une page où l'on dépose le fichier depuis un navigateur.
class LanImport {
  HttpServer? _srv;
  final _files = StreamController<(String, List<int>)>.broadcast();
  String address = '';

  /// Fichiers reçus : (nom, contenu).
  Stream<(String, List<int>)> get files => _files.stream;

  Future<String> start() async {
    for (var port = 8686; port < 8700; port++) {
      try {
        _srv = await HttpServer.bind(InternetAddress.anyIPv4, port);
        break;
      } catch (_) {}
    }
    final srv = _srv;
    if (srv == null) throw const SocketException("Impossible d'ouvrir le serveur local.");
    final ip = await localIp();
    if (ip == null) {
      await stop();
      throw const SocketException('Aucun réseau Wi-Fi / Ethernet détecté.');
    }
    address = 'http://$ip:${srv.port}';
    srv.listen(_handle, onError: (_) {});
    return address;
  }

  Future<void> _handle(HttpRequest req) async {
    final res = req.response;
    try {
      if (req.method == 'POST' && req.uri.path == '/upload') {
        final data = <int>[];
        await for (final chunk in req) {
          data.addAll(chunk);
          if (data.length > 80 * 1024 * 1024) throw const FormatException('Fichier trop volumineux (80 Mo max).');
        }
        final name = Uri.decodeComponent(req.headers.value('x-name') ?? 'liste.m3u');
        if (!decodeBody(data).toUpperCase().contains('#EXTINF')) {
          res.statusCode = 422;
          res.write("Ce fichier n'est pas une liste M3U (aucune ligne #EXTINF).");
        } else {
          _files.add((name, data));
          res.write('ok');
        }
      } else {
        res.headers.contentType = ContentType.html;
        res.add(utf8.encode(_page));
      }
    } catch (e) {
      res.statusCode = 400;
      res.write('$e');
    }
    await res.close();
  }

  Future<void> stop() async {
    await _srv?.close(force: true);
    _srv = null;
  }

  static Future<String?> localIp() async {
    try {
      final ifs = await NetworkInterface.list(type: InternetAddressType.IPv4, includeLoopback: false);
      final all = [for (final i in ifs) ...i.addresses.map((a) => a.address)];
      int rank(String a) => a.startsWith('192.168.') ? 0 : a.startsWith('10.') ? 1 : a.startsWith('172.') ? 2 : 3;
      all.sort((a, b) => rank(a).compareTo(rank(b)));
      return all.isEmpty ? null : all.first;
    } catch (_) {
      return null;
    }
  }

  static const _page = '''<!doctype html><html lang="fr"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>IPTV Player — envoyer une liste</title>
<style>
body{margin:0;min-height:100vh;display:flex;align-items:center;justify-content:center;background:#040506;color:#e6e8ee;
font-family:system-ui,-apple-system,Segoe UI,Roboto,sans-serif;padding:16px;box-sizing:border-box}
.box{max-width:520px;width:100%;background:#141821;border:1px solid #262b38;border-radius:22px;padding:28px}
h1{font-size:22px;margin:0 0 6px}p{color:#9aa0b2;line-height:1.45;margin:0 0 18px}
label{display:block;border:2px dashed #2e8bff;border-radius:16px;padding:34px 16px;text-align:center;cursor:pointer;font-weight:700}
label.over{background:#10233f}input{display:none}#st{margin-top:16px;font-weight:600;min-height:1.4em}
.ok{color:#5ad17e}.err{color:#ff6b6b}
</style></head><body><div class="box">
<h1>Envoyer une liste M3U</h1>
<p>Choisissez le fichier .m3u / .m3u8 sur cet appareil : il est transmis directement à IPTV Player, sans passer par Internet.</p>
<label id="drop">📄 Choisir ou déposer le fichier<input id="f" type="file" accept=".m3u,.m3u8,.txt,audio/x-mpegurl,application/vnd.apple.mpegurl"></label>
<div id="st"></div></div>
<script>
const st=document.getElementById('st'),drop=document.getElementById('drop');
async function send(file){if(!file)return;st.className='';st.textContent='Envoi de « '+file.name+' »…';
try{const r=await fetch('/upload',{method:'POST',headers:{'x-name':encodeURIComponent(file.name)},body:file});
const t=await r.text();if(r.ok){st.className='ok';st.textContent='✓ Liste reçue — regardez l’écran d’IPTV Player.';}
else{st.className='err';st.textContent='⚠ '+t;}}catch(e){st.className='err';st.textContent='⚠ Envoi impossible : '+e;}}
document.getElementById('f').onchange=e=>send(e.target.files[0]);
['dragover','dragenter'].forEach(n=>drop.addEventListener(n,e=>{e.preventDefault();drop.classList.add('over')}));
['dragleave','drop'].forEach(n=>drop.addEventListener(n,e=>{e.preventDefault();drop.classList.remove('over')}));
drop.addEventListener('drop',e=>send(e.dataTransfer.files[0]));
</script></body></html>''';
}
