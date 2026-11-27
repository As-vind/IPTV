// Import d'une liste M3U depuis un fichier : sélection sur l'appareil, ou envoi depuis un autre
// appareil du même réseau (téléphone, PC) — pratique sur une TV sans gestionnaire de fichiers.
import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';

import 'package:flutter/foundation.dart' show compute;

/// Vérifie le contenu et copie la liste dans le dossier de l'application.
/// Renvoie le chemin de la copie (la source reste lisible même si l'original est déplacé ou supprimé).
Future<String> savePlaylist(Directory dataDir, String id, List<int> bytes) async {
  if (await countEntriesAsync(bytes) == 0) {
    throw const FormatException("Ce fichier n'est pas une liste M3U (aucune ligne #EXTINF).");
  }
  final dir = Directory('${dataDir.path}/playlists');
  await dir.create(recursive: true);
  final f = File('${dir.path}/$id.m3u');
  await f.writeAsBytes(bytes, flush: true);
  return f.path;
}

/// Nombre d'entrées d'une liste (pour l'aperçu avant ajout).
/// Compte les #EXTINF directement dans les octets (sans créer de copie texte : sûr pour les très grosses listes).
int countEntries(List<int> bytes) {
  const pat = [35, 69, 88, 84, 73, 78, 70]; // "#EXTINF"
  var n = 0;
  final len = bytes.length - pat.length;
  for (var i = 0; i <= len; i++) {
    if (bytes[i] != 35) continue;
    var ok = true;
    for (var j = 1; j < pat.length; j++) {
      final c = bytes[i + j] & 0xDF; // majuscule
      if (c != pat[j]) {
        ok = false;
        break;
      }
    }
    if (ok) n++;
  }
  return n;
}

/// Même chose, hors de l'écran principal (pas de blocage « L'application ne répond pas »).
Future<int> countEntriesAsync(List<int> bytes) =>
    bytes.length < 2000000 ? Future.value(countEntries(bytes)) : compute(countEntries, bytes);

/// Petit serveur web local : affiche une page où l'on dépose le fichier depuis un navigateur.
class LanImport {
  HttpServer? _srv;
  final _files = StreamController<(String, List<int>)>.broadcast();
  final _links = StreamController<Map<String, String>>.broadcast();
  String address = '';

  /// Fichiers reçus : (nom, contenu).
  Stream<(String, List<int>)> get files => _files.stream;

  /// Liens collés depuis le téléphone : {type: 'url', url} ou {type: 'xtream', server, user, password}.
  Stream<Map<String, String>> get links => _links.stream;

  /// Analyse un texte collé : lien get.php (compte Xtream), lien M3U, ou « serveur identifiant motdepasse ».
  static Map<String, String>? parseLink(Map<String, dynamic> b) {
    final server = '${b['server'] ?? ''}'.trim(), user = '${b['user'] ?? ''}'.trim(), pwd = '${b['password'] ?? ''}'.trim();
    if (server.isNotEmpty && user.isNotEmpty && pwd.isNotEmpty) {
      return {'type': 'xtream', 'server': server, 'user': user, 'password': pwd};
    }
    final text = '${b['text'] ?? ''}'.trim();
    final m = RegExp(r'https?://\S+', caseSensitive: false).firstMatch(text);
    if (m == null) return null;
    final url = m.group(0)!;
    final u = Uri.tryParse(url);
    if (u == null || u.host.isEmpty) return null;
    final q = u.queryParameters;
    if ((q['username'] ?? '').isNotEmpty && (q['password'] ?? '').isNotEmpty) {
      return {'type': 'xtream', 'server': '${u.scheme}://${u.authority}', 'user': q['username']!, 'password': q['password']!};
    }
    return {'type': 'url', 'url': url};
  }

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
      if (req.method == 'POST' && req.uri.path == '/link') {
        final b = BytesBuilder(copy: false);
        await for (final chunk in req) {
          b.add(chunk);
          if (b.length > 64 * 1024) throw const FormatException('texte trop long');
        }
        final data = jsonDecode(utf8.decode(b.takeBytes()));
        final link = data is Map ? parseLink(Map<String, dynamic>.from(data)) : null;
        if (link == null) {
          res.statusCode = 422;
          res.write('Aucun lien reconnu. Collez un lien M3U (http://…) ou un lien Xtream (…get.php?username=…&password=…), '
              'ou remplissez serveur, identifiant et mot de passe.');
        } else {
          _links.add(link);
          res.write('ok');
        }
      } else if (req.method == 'POST' && req.uri.path == '/upload') {
        final b = BytesBuilder(copy: false);
        await for (final chunk in req) {
          b.add(chunk);
          if (b.length > 150 * 1024 * 1024) throw const FormatException('Fichier trop volumineux (150 Mo max).');
        }
        final Uint8List data = b.takeBytes();
        final name = Uri.decodeComponent(req.headers.value('x-name') ?? 'liste.m3u');
        if (await countEntriesAsync(data) == 0) {
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
label.over{background:#10233f}#f{display:none}#st,#st2{margin-top:16px;font-weight:600;min-height:1.4em}
h2{font-size:18px;margin:26px 0 6px}textarea,input:not(#f){width:100%;box-sizing:border-box;background:#0b0e14;color:#e6e8ee;
border:1px solid #262b38;border-radius:12px;padding:12px;font:inherit;margin:6px 0}details{margin:8px 0;color:#9aa0b2}
button{margin-top:10px;width:100%;padding:14px;border:0;border-radius:999px;background:#2e8bff;color:#fff;font-weight:700;font-size:16px}
.ok{color:#5ad17e}.err{color:#ff6b6b}
</style></head><body><div class="box">
<h1>Envoyer une liste à la TV</h1>
<p>Choisissez le fichier .m3u / .m3u8 sur cet appareil : il est transmis directement à IPTV Player, sans passer par Internet.</p>
<label id="drop">📄 Choisir ou déposer le fichier<input id="f" type="file" accept=".m3u,.m3u8,.txt,audio/x-mpegurl,application/vnd.apple.mpegurl"></label>
<div id="st"></div>
<h2>…ou coller un lien</h2>
<p>Lien M3U, ou lien Xtream (…/get.php?username=…&amp;password=…). Il arrive directement dans le formulaire de la TV.</p>
<textarea id="t" rows="3" placeholder="http://…"></textarea>
<details><summary>Compte Xtream en 3 champs</summary>
<input id="sv" placeholder="Serveur : http://serveur:8080" autocomplete="off">
<input id="us" placeholder="Identifiant" autocomplete="off">
<input id="pw" placeholder="Mot de passe" type="password" autocomplete="off">
</details>
<button id="go">Envoyer à la TV</button>
<div id="st2"></div></div>
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
const st2=document.getElementById('st2');
document.getElementById('go').onclick=async()=>{const v=id=>document.getElementById(id).value.trim();
st2.className='';st2.textContent='Envoi…';
try{const r=await fetch('/link',{method:'POST',headers:{'Content-Type':'application/json'},
body:JSON.stringify({text:v('t'),server:v('sv'),user:v('us'),password:document.getElementById('pw').value})});
const t=await r.text();if(r.ok){st2.className='ok';st2.textContent='✓ Envoyé — vérifiez puis validez sur la TV.';}
else{st2.className='err';st2.textContent='⚠ '+t;}}catch(e){st2.className='err';st2.textContent='⚠ Envoi impossible : '+e;}};
</script></body></html>''';
}
