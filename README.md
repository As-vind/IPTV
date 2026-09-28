# IPTV Player — Android, Android TV, iPad

Application IPTV conçue par **Asvind** : listes **M3U** et comptes **Xtream Codes**,
chaînes classées par pays, fiches films / séries / acteurs, profils, reprise de lecture.
Même design et mêmes fonctions que la version Windows.

## Télécharger
Chaque modification publiée sur `main` est compilée automatiquement (onglet **Actions**)
et publiée dans **Releases** :

- `IPTV-Player-x.y.apk` → téléphone, tablette et box **Android TV**
- `IPTV-Player-x.y.ipa` → **iPad / iPhone**, à installer avec *Sideloadly* ou *AltStore*

## Fonctions
- Accueil : bannière, *Reprendre la lecture*, *Les chaînes du moment* (LIVE + programme en cours),
  films / séries en ce moment, catégories, nouveautés
- Chaînes TV par pays et catégories, zapping (télécommande ↑ ↓), programme en cours (EPG Xtream)
- Fiches films / séries : fond, affiche, synopsis, genres, note, âge, bande-annonce, saisons, épisodes
- Fiches acteurs : photo, biographie, filmographie, titres disponibles dans votre liste (clé TMDB)
- Profils « Qui regarde ? » avec avatar, code PIN et profil enfant
- Lecteur : pistes audio, sous-titres, reprise automatique, épisode suivant
- Navigation à la télécommande (Android TV)

## Publication sur les stores
Voir [`store/STORES.md`](store/STORES.md) (comptes, secrets GitHub, fiches, confidentialité).

## Structure
- `lib/core` : M3U, Xtream, pays, TMDB, état (profils, favoris, reprise)
- `lib/ui` : écrans
- `tool/` : génération des dossiers Android / iOS en compilation
