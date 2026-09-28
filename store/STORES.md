# Publier IPTV Player sur Google Play et l'App Store

Tout se compile automatiquement sur GitHub à chaque modification (onglet **Actions**).
Il reste à créer les comptes et à coller quelques clés dans les **secrets** du dépôt :
https://github.com/As-vind/IPTV/settings/secrets/actions → *New repository secret*.

Deux versions sont compilées :

| Version | Pour | Différences |
|---|---|---|
| **Complète** (APK, IPA non signé) | installation directe (APK, Sideloadly/AltStore) | tout, comme sur Windows |
| **Stores** (`STORE=true`) | Google Play / App Store | sans logos de plateformes (Netflix…), sans tuiles studios ; sur iPhone/iPad sans téléchargement hors ligne (règle Apple 5.2.3) |

---

## 0. Clé TMDB (jaquettes, fonds, acteurs)
Secret **`TMDB_KEY`** = votre jeton TMDB (v4 « Read Access Token » ou clé v3).
Le dépôt étant public, la clé n'est jamais écrite dans le code : elle est injectée à la compilation.

---

## 1. Google Play (25 $ une seule fois)

1. Créer le compte développeur : https://play.google.com/console/signup (vérification d'identité : quelques jours).
2. Dans la Play Console : **Créer une application** → nom « IPTV Player — Asvind », langue français, Application, Gratuite.
3. Ajouter les 3 secrets de signature (fichier `Secrets-Google-Play.txt` fourni à part, **ne jamais le publier**) :
   - `ANDROID_KEYSTORE_B64`, `ANDROID_KEYSTORE_PASSWORD`, `ANDROID_KEY_ALIAS`
4. Relancer la compilation (Actions → *Compilation IPTV Player* → *Run workflow*) : le job
   **« Google Play (AAB signé) »** produit `IPTV-Player-x.y-google-play.aab` (dans la Release et les artefacts).
5. **Premier envoi à la main** : Play Console → *Tester → Tests internes* → *Créer une version* → déposer le `.aab`.
   Accepter *Play App Signing* (Google garde la clé de l'application ; la nôtre ne sert qu'à l'envoi).
6. Remplir *Présence sur le Store* (textes : `store/FICHES.md`), icône 512×512 (`assets/icon.png`),
   bannière 1024×500, captures d'écran (téléphone + tablette + TV), *Sécurité des données* (aucune donnée),
   *Classification du contenu*, *Public cible* (18+ conseillé), *Politique de confidentialité* :
   https://github.com/As-vind/IPTV/blob/main/store/PRIVACY.md
7. *(facultatif, envois automatiques ensuite)* Créer un compte de service Google Cloud avec accès à la Play Console,
   télécharger sa clé JSON et la coller dans le secret **`PLAY_SERVICE_ACCOUNT_JSON`** :
   chaque compilation déposera alors l'AAB en brouillon dans *Tests internes*.
8. Nouveaux comptes personnels : Google impose un **test fermé avec au moins 12 testeurs pendant 14 jours**
   avant de pouvoir publier en production.

Identifiant de l'application : `com.asvind.iptv_player`

---

## 2. App Store (99 $ par an)

1. S'inscrire à l'Apple Developer Program : https://developer.apple.com/programs/enroll/
2. App Store Connect → *Utilisateurs et accès* → *Intégrations* → *Clés d'API App Store Connect* →
   générer une clé avec le rôle **App Manager** (ou Admin). Télécharger le fichier `AuthKey_XXXX.p8` (une seule fois !).
3. Ajouter 4 secrets :
   - `ASC_KEY_ID` : l'identifiant de la clé (ex. `AB12CD34EF`)
   - `ASC_ISSUER_ID` : l'« Issuer ID » affiché au-dessus de la liste des clés
   - `ASC_KEY_P8_B64` : le contenu du fichier `.p8` encodé en base64
     (Mac : `base64 -i AuthKey_XXXX.p8 | pbcopy` — Windows PowerShell :
     `[Convert]::ToBase64String([IO.File]::ReadAllBytes("AuthKey_XXXX.p8")) | Set-Clipboard`)
   - `APPLE_TEAM_ID` : l'identifiant d'équipe (developer.apple.com → *Membership*)
4. App Store Connect → *Apps* → **+ Nouvelle app** : plateforme iOS, nom « IPTV Player — Asvind »,
   identifiant de lot **`com.asvind.iptvPlayer`** (s'il n'apparaît pas, le créer dans
   developer.apple.com → *Identifiers*), SKU `iptvplayer`.
5. Relancer la compilation : le job **« App Store (envoi TestFlight) »** signe l'application et l'envoie
   directement sur App Store Connect (elle apparaît dans TestFlight après ~15 min de traitement).
6. Remplir la fiche (`store/FICHES.md`), captures iPhone 6,9" et iPad 13", *Confidentialité de l'app* :
   « Aucune donnée collectée », URL de confidentialité ci-dessus, classification 17+,
   **Notes pour la revue** (texte en anglais dans `store/FICHES.md`, avec une liste de test légale).
7. Soumettre à la validation.

Identifiant de lot : `com.asvind.iptvPlayer`

---

## Risque de refus — à savoir
Les apps IPTV sont surveillées de près. Pour maximiser les chances :
- ne jamais inclure ni suggérer de liste ou de fournisseur ;
- ne pas utiliser de marques (Netflix, Canal+, Disney…) dans le nom, les captures ou la description ;
- captures d'écran réalisées avec la liste de test légale (iptv-org) et des fiches TMDB, pas avec un abonnement pirate ;
- en cas de refus Apple (règles 5.2.1 / 5.2.3), répondre en rappelant que l'app est un simple lecteur sans contenu.
