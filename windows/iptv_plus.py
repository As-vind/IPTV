"""IPTV Player — fonctions avancées (sans interface) :
regroupement des chaînes et qualités, profils de lecture, statistiques de stabilité,
matériel, fréquence d'affichage, maintenance, guide TV XMLTV et administration web locale.

Le module ne dépend pas de Qt : il est utilisé par iptv_player.py et testable seul.
"""
import base64
import gzip
import hashlib
import http.server
import ipaddress
import json
import os
import re
import secrets
import shutil
import socket
import socketserver
import sys
import threading
import time
import unicodedata
import urllib.parse
import urllib.request
from datetime import datetime, timezone

# Fonctions fournies par l'application (pays, nettoyage des noms) — voir setup().
_H = {"strip_lead_tags": lambda s: s, "detect_country": lambda *a, **k: "ZZ"}


def setup(**helpers):
    _H.update(helpers)


def _norm(s):
    s = unicodedata.normalize("NFKD", (s or "").lower())
    return "".join(c for c in s if not unicodedata.combining(c))


# =========================================================================== #
#  1. Qualités et regroupement des chaînes
# =========================================================================== #
Q_LABELS = {4: "4K", 3: "FHD", 2: "HD", 1: "SD", 0: ""}
Q_CODES = {"4k": 4, "fhd": 3, "hd": 2, "sd": 1}
# débit nécessaire (octets/s) pour chaque qualité — sert à la qualité automatique
Q_NEED = {4: 2_200_000, 3: 900_000, 2: 450_000, 1: 200_000, 0: 450_000}

_SUP = str.maketrans({"ᴴ": "H", "ᴰ": "D", "ᵁ": "U", "ᶠ": "F", "ˢ": "S", "ᴷ": "K", "⁴": "4"})
_QTOK = [
    (4, r"8K|4K|UHD|ULTRA\s*HD|2160[PI]?"),
    (3, r"FHD|FULL\s*HD|1080[PI]?"),
    (2, r"HD|720[PI]?|HQ"),
    (1, r"SD|576[PI]?|480[PI]?|360[PI]?|LQ|LOW"),
]
_QRE = [(r, re.compile(r"(?<![A-Za-z0-9])(?:" + p + r")(?![A-Za-z0-9])", re.I)) for r, p in _QTOK]
_DECOR_RE = re.compile(
    r"(?<![A-Za-z0-9])(?:HEVC|H\.?26[45]|X26[45]|AVC|\d{2,3}\s?FPS|HDR(?:10\+?)?|DV|DOLBY\s*VISION|"
    r"BACKUP|BK|ALT(?:ERNATIVE)?|RAW|VIP|NEW|ORIG(?:INAL)?|MULTI|DIRECT|LIVE|TEST|\(?\d\)?$)(?![A-Za-z0-9])",
    re.I)
_SYMB_RE = re.compile(r"[◉●○★☆✦✪♦◆▶►•|\[\](){}<>«»\"'`~*#_]+")


def quality_of(name, group=""):
    """Qualité d'un flux d'après son nom (puis sa catégorie) : 4 = 4K, 3 = FHD, 2 = HD, 1 = SD, 0 = inconnue."""
    for text in (name, group):
        t = (text or "").translate(_SUP)
        for rank, rx in _QRE:
            if rx.search(t):
                return rank
    return 0


def strip_quality(name):
    t = (name or "").translate(_SUP)
    for _r, rx in _QRE:
        t = rx.sub(" ", t)
    t = _DECOR_RE.sub(" ", t)
    t = re.sub(r"[\[\(]\s*[\]\)]", " ", t)
    return re.sub(r"\s{2,}", " ", t).strip(" -|:._–/")


def display_name(name):
    """Nom affiché d'une chaîne regroupée : sans préfixe pays ni mention de qualité."""
    s = _H["strip_lead_tags"](name or "") or (name or "")
    s = strip_quality(s)
    return s or (name or "").strip()


def channel_key(name, country):
    """Clé de regroupement : pays + nom sans qualité. Les variantes régionales (France 3 Alpes),
    de langue (VF, AR, EN…) et les décalages (+1) restent distinctes car leur nom diffère."""
    s = _H["strip_lead_tags"](name or "") or (name or "")
    s = strip_quality(s)
    s = _SYMB_RE.sub(" ", s)
    s = _norm(s)
    s = re.sub(r"[^a-z0-9+]+", "", s)
    if len(s) < 2:
        return None
    return f"{country or 'ZZ'}|{s}"


def _quality_only_group(group):
    g = _SYMB_RE.sub(" ", (group or "").translate(_SUP))
    g = _H["strip_lead_tags"](g) or g
    for _r, rx in _QRE:
        g = rx.sub(" ", g)
    g = _DECOR_RE.sub(" ", g)
    g = re.sub(r"(?i)\b(cha[iî]nes?|channels?|tv|live)\b", " ", g)
    return not re.sub(r"[\s\-|:._/]+", "", g)


def group_variants(items):
    """Regroupe les chaînes identiques (SD / HD / FHD / 4K, flux de secours) en une seule entrée.
    Chaque chaîne gardée reçoit « variants » : tous les flux, meilleure qualité d'abord.
    Les films et séries ne sont pas touchés. Renvoie une nouvelle liste."""
    out, by_key = [], {}
    for it in items:
        if it.get("kind") != "live":
            out.append(it)
            continue
        q = quality_of(it.get("name"), it.get("group"))
        var = {"url": it["url"], "name": it.get("name", ""), "q": q, "group": it.get("group", ""),
               "opts": it.get("opts") or []}
        key = channel_key(it.get("name"), it.get("country"))
        rep = by_key.get(key) if key else None
        if rep is None:
            rep = dict(it)
            rep["variants"] = [var]
            rep["_ckey"] = key or ("u|" + it["url"])
            if key:
                by_key[key] = rep
            out.append(rep)
            continue
        if any(v["url"] == var["url"] for v in rep["variants"]):
            continue
        rep["variants"].append(var)
        if not rep.get("logo") and it.get("logo"):
            rep["logo"] = it["logo"]
        if not rep.get("stream_id") and it.get("stream_id"):
            rep["stream_id"] = it["stream_id"]
        if not rep.get("tvg_id") and it.get("tvg_id"):
            rep["tvg_id"] = it["tvg_id"]
        if _quality_only_group(rep.get("group")) and not _quality_only_group(it.get("group")):
            rep["group"] = it["group"]
    for rep in out:
        vs = rep.get("variants")
        if not vs:
            continue
        vs.sort(key=lambda v: -v["q"])
        if len(vs) > 1:
            rep["_qlabels"] = " · ".join(dict.fromkeys(Q_LABELS[v["q"]] for v in vs if v["q"])) or ""
            rep["_title"] = display_name(rep.get("name"))
    return out


def stable_key(it):
    """Identifiant d'un élément qui survit à l'actualisation des listes (les liens changent souvent)."""
    kind = it.get("kind", "")
    if kind == "live":
        k = it.get("_ckey") or channel_key(it.get("name"), it.get("country"))
        return f"live|{k}" if k else None
    t = re.sub(r"[^a-z0-9]+", "", _norm(it.get("_title") or it.get("name") or ""))
    return f"{kind}|{t}|{it.get('_year') or ''}" if t else None


def remap_urls(urls, keymap, items):
    """Retrouve les favoris (ou l'historique) dont le lien a changé après une actualisation.
    urls : liens enregistrés ; keymap : {lien: clé stable} mémorisé ; items : nouvelle bibliothèque.
    Renvoie (nouvelle liste de liens, nouveau keymap, nombre de liens remplacés)."""
    by_url = {i["url"] for i in items}
    by_key = {}
    for i in items:
        k = stable_key(i)
        if k and k not in by_key:
            by_key[k] = i["url"]
        for v in i.get("variants") or []:
            by_url.add(v["url"])
    out, newmap, changed = [], {}, 0
    for u in urls:
        k = keymap.get(u)
        if u in by_url:
            out.append(u)
            if k:
                newmap[u] = k
        elif k and k in by_key:
            nu = by_key[k]
            out.append(nu)
            newmap[nu] = k
            changed += 1
        else:
            out.append(u)            # gardé : la chaîne peut revenir à la prochaine actualisation
            if k:
                newmap[u] = k
    return list(dict.fromkeys(out)), newmap, changed


# =========================================================================== #
#  2. Statistiques de stabilité des flux et choix de la qualité
# =========================================================================== #
def url_id(url):
    return hashlib.md5((url or "").encode("utf-8")).hexdigest()[:12]


class StreamStats:
    """Succès / échecs / coupures par flux, conservés dans la configuration (5000 flux au plus)."""

    def __init__(self, store):
        self.d = store            # dict persistant : {id: [ok, fail, stall, last_fail_ts, last_ok_ts]}

    def _row(self, url):
        r = self.d.get(url_id(url))
        if not r:
            r = self.d[url_id(url)] = [0, 0, 0, 0, 0]
        return r

    def ok(self, url):
        r = self._row(url)
        r[0] += 1
        r[4] = int(time.time())
        self._trim()

    def fail(self, url):
        r = self._row(url)
        r[1] += 1
        r[3] = int(time.time())
        self._trim()

    def stall(self, url):
        r = self._row(url)
        r[2] += 1
        self._trim()

    def dead(self, url):
        r = self.d.get(url_id(url))
        return bool(r and r[3] and r[3] > r[4] and time.time() - r[3] < 6 * 3600 and r[1] >= 2)

    def score(self, url):
        r = self.d.get(url_id(url))
        if not r:
            return 0.0
        s = r[0] * 1.0 - r[1] * 3.0 - r[2] * 1.0
        if r[3] and r[3] > r[4] and time.time() - r[3] < 600:
            s -= 50                 # échec il y a moins de 10 minutes
        return s

    def row(self, url):
        return list(self.d.get(url_id(url)) or [0, 0, 0, 0, 0])

    def _trim(self):
        if len(self.d) > 5000:
            for k in sorted(self.d, key=lambda k: max(self.d[k][3], self.d[k][4]))[:500]:
                self.d.pop(k, None)


def network_cap(bytes_per_s):
    """Meilleure qualité que le débit mesuré permet (None si inconnu)."""
    if not bytes_per_s or bytes_per_s <= 0:
        return None
    for q in (4, 3, 2):
        if bytes_per_s >= Q_NEED[q] * 1.25:
            return q
    return 1


def pick_variant(variants, pref="auto", cap=4, stats=None, exclude=(), below=None):
    """Indice du flux à lire.
    pref : 'auto' ou '4k'/'fhd'/'hd'/'sd' (choix manuel) ; cap : qualité maximale permise
    (écran, débit, repli en cours) ; exclude : liens à éviter (en échec) ; below : ne garder que les
    qualités strictement inférieures (repli après blocage)."""
    if not variants:
        return 0
    cands = [i for i, v in enumerate(variants) if v["url"] not in exclude]
    if below is not None:
        lower = [i for i in cands if (variants[i]["q"] or 2) < below]
        cands = lower or cands
    if not cands:
        cands = list(range(len(variants)))

    def sc(i):
        return stats.score(variants[i]["url"]) if stats else 0.0

    def eff(i):
        return variants[i]["q"] or 2        # qualité inconnue : considérée comme HD

    if pref in Q_CODES:
        want = Q_CODES[pref]
        exact = [i for i in cands if eff(i) == want]
        if exact:
            return max(exact, key=sc)
        lower = [i for i in cands if eff(i) < want]
        if lower:
            return max(lower, key=lambda i: (eff(i), sc(i)))
        return min(cands, key=lambda i: (eff(i), -sc(i)))
    ok = [i for i in cands if eff(i) <= cap] or [min(cands, key=eff)]
    healthy = [i for i in ok if not (stats and stats.dead(variants[i]["url"]))] or ok
    return max(healthy, key=lambda i: (eff(i), sc(i)))


# =========================================================================== #
#  3. Profils de lecture et réglages
# =========================================================================== #
PROFILES = {
    # mémoire tampon direct (s), films (s), délai avant de considérer un blocage (s), relances, repli qualité
    "performance": {"live_cache": 1.0, "vod_cache": 3, "stall_timeout": 6, "max_retries": 2, "fallback": True},
    "balanced": {"live_cache": 3.0, "vod_cache": 8, "stall_timeout": 9, "max_retries": 3, "fallback": True},
    "antifreeze": {"live_cache": 10.0, "vod_cache": 20, "stall_timeout": 15, "max_retries": 5, "fallback": True},
}
AUTO_STEPS = [2.0, 4.0, 7.0, 10.0]      # profil AUTO : la mémoire tampon grandit après chaque coupure

# Tous les réglages modifiables (interface, administration web, sauvegarde).
SETTINGS = [
    # section, clé, libellé, type, défaut, choix / bornes
    ("Lecture", "profile", "Profil de lecture", "choice", "auto",
     [("auto", "AUTO — optimisation intelligente"), ("performance", "Performance — zapping rapide"),
      ("balanced", "Équilibré"), ("antifreeze", "Anti-freeze — priorité à la continuité"),
      ("custom", "Personnalisé")]),
    ("Lecture", "c_live_cache", "Personnalisé : mémoire tampon des chaînes (s)", "float", 3.0, (0.5, 30)),
    ("Lecture", "c_vod_cache", "Personnalisé : mémoire tampon des films (s)", "int", 8, (1, 60)),
    ("Lecture", "c_stall_timeout", "Personnalisé : blocage détecté après (s)", "int", 9, (3, 60)),
    ("Lecture", "c_max_retries", "Personnalisé : reconnexions avant changement de flux", "int", 3, (0, 10)),
    ("Lecture", "reconnect", "Reconnexion automatique", "bool", True, None),
    ("Lecture", "fallback", "Basculer vers un autre flux / une qualité inférieure en cas de blocage", "bool", True, None),
    ("Chaînes", "dedupe", "Regrouper les chaînes en double (SD, HD, FHD, 4K)", "bool", True, None),
    ("Chaînes", "quality", "Qualité des chaînes", "choice", "auto",
     [("auto", "AUTO (selon le débit, l'écran et la stabilité)"), ("4k", "4K"), ("fhd", "FHD"),
      ("hd", "HD"), ("sd", "SD")]),
    ("Chaînes", "upgrade", "Revenir à une meilleure qualité quand la connexion est stable", "bool", True, None),
    ("Vidéo", "hwdec", "Accélération matérielle", "bool", True, None),
    ("Vidéo", "aspect", "Format d'image", "choice", "auto",
     [("auto", "Automatique"), ("16:9", "16:9"), ("4:3", "4:3"), ("21:9", "21:9"), ("fill", "Remplir l'écran"),
      ("stretch", "Étirer")]),
    ("Vidéo", "deinterlace", "Désentrelacement", "choice", "auto",
     [("auto", "Automatique"), ("on", "Toujours"), ("off", "Jamais")]),
    ("Vidéo", "brightness", "Luminosité", "int", 0, (-100, 100)),
    ("Vidéo", "contrast", "Contraste", "int", 0, (-100, 100)),
    ("Vidéo", "saturation", "Saturation", "int", 0, (-100, 100)),
    ("Vidéo", "sharpness", "Netteté", "int", 0, (0, 100)),
    ("Vidéo", "refresh", "Fréquence d'affichage", "choice", "off",
     [("off", "Ne pas changer"), ("auto", "Adapter au flux"), ("24", "24 Hz"), ("25", "25 Hz"),
      ("30", "30 Hz"), ("50", "50 Hz"), ("60", "60 Hz")]),
    ("Vidéo", "hdr", "HDR", "choice", "auto", [("auto", "Automatique (selon l'écran)"), ("sdr", "Convertir en SDR")]),
    ("Vidéo", "max_res", "Résolution maximale", "choice", "auto",
     [("auto", "Automatique (selon l'écran)"), ("4k", "4K"), ("fhd", "1080p"), ("hd", "720p"), ("sd", "SD")]),
    ("Audio", "a_lang", "Langue audio préférée", "choice", "fr",
     [("fr", "Français"), ("en", "Anglais"), ("es", "Espagnol"), ("de", "Allemand"), ("it", "Italien"),
      ("ar", "Arabe"), ("pt", "Portugais"), ("orig", "Version originale")]),
    ("Audio", "s_lang", "Sous-titres", "choice", "off",
     [("off", "Désactivés"), ("auto", "Si la langue audio n'est pas la mienne"), ("fr", "Français"),
      ("en", "Anglais")]),
    ("Audio", "av_delay", "Synchronisation audio / vidéo (ms)", "int", 0, (-2000, 2000)),
    ("Audio", "normalize", "Normalisation automatique du volume", "bool", False, None),
    ("Audio", "passthrough", "Son multicanal vers l'ampli (passthrough)", "bool", False, None),
    ("Maintenance", "auto_refresh_h", "Actualisation automatique des listes (heures, 0 = jamais)", "int", 24, (0, 168)),
    ("Maintenance", "cache_max_mb", "Taille maximale du cache d'images (Mo)", "int", 500, (50, 5000)),
    ("Maintenance", "auto_backup", "Sauvegarde automatique quotidienne de la configuration", "bool", True, None),
]
SETTING_KEYS = {s[1]: s for s in SETTINGS}
LANG3 = {"fr": "fr,fra,fre,french", "en": "en,eng,english", "es": "es,spa,spanish", "de": "de,deu,ger,german",
         "it": "it,ita,italian", "ar": "ar,ara,arabic", "pt": "pt,por,portuguese"}


def ensure_settings(cfg):
    """Ajoute les réglages manquants (valeurs par défaut) dans cfg['player']."""
    p = cfg.setdefault("player", {})
    for _sec, key, _lab, _typ, default, _x in SETTINGS:
        p.setdefault(key, default)
    if "live_cache" in cfg and not p.get("_migrated"):
        try:
            p["c_live_cache"] = max(0.5, float(cfg["live_cache"]) / 1000.0)
        except (TypeError, ValueError):
            pass
    p["_migrated"] = True
    cfg.setdefault("ch_quality", {})
    cfg.setdefault("stream_stats", {})
    cfg.setdefault("fav_keys", {})
    cfg.setdefault("hidden_groups", [])
    cfg.setdefault("group_order", [])
    cfg.setdefault("auto_live_cache", AUTO_STEPS[1])
    adm = cfg.setdefault("admin", {})
    adm.setdefault("enabled", False)
    adm.setdefault("port", 8080)
    if not re.fullmatch(r"\d{6}", str(adm.get("pin") or "")):
        adm["pin"] = f"{secrets.randbelow(1_000_000):06d}"
    return p


def reset_settings(cfg):
    p = cfg.setdefault("player", {})
    for _sec, key, _lab, _typ, default, _x in SETTINGS:
        p[key] = default
    cfg["ch_quality"] = {}
    cfg["auto_live_cache"] = AUTO_STEPS[1]


def coerce_setting(key, value):
    """Valide une valeur reçue (interface web) ; lève ValueError si elle est incorrecte."""
    s = SETTING_KEYS.get(key)
    if not s:
        raise ValueError(f"réglage inconnu : {key}")
    typ, extra = s[3], s[5]
    if typ == "bool":
        if isinstance(value, str):
            return value.lower() in ("1", "true", "oui", "yes", "on")
        return bool(value)
    if typ in ("int", "float"):
        v = float(value)
        lo, hi = extra
        v = max(lo, min(hi, v))
        return int(round(v)) if typ == "int" else round(v, 1)
    if typ == "choice":
        if value not in [c[0] for c in extra]:
            raise ValueError(f"valeur incorrecte pour {key}")
        return value
    return value


def effective_profile(p, cfg, hw_tier="mid"):
    """Paramètres réels de lecture selon le profil choisi."""
    mode = p.get("profile", "auto")
    if mode == "custom":
        prof = {"live_cache": float(p.get("c_live_cache", 3)), "vod_cache": int(p.get("c_vod_cache", 8)),
                "stall_timeout": int(p.get("c_stall_timeout", 9)), "max_retries": int(p.get("c_max_retries", 3)),
                "fallback": bool(p.get("fallback", True))}
    elif mode in PROFILES:
        prof = dict(PROFILES[mode])
    else:
        live = float(cfg.get("auto_live_cache") or AUTO_STEPS[1])
        prof = {"live_cache": live, "vod_cache": 10 if hw_tier != "low" else 6,
                "stall_timeout": max(7, int(live) + 5), "max_retries": 3, "fallback": True}
    if not p.get("reconnect", True):
        prof["max_retries"] = 0
    if not p.get("fallback", True):
        prof["fallback"] = False
    prof["mode"] = mode
    return prof


def auto_cache_after_stall(cfg):
    """Profil AUTO : une coupure fait passer la mémoire tampon au palier suivant (mémorisé)."""
    cur = float(cfg.get("auto_live_cache") or AUTO_STEPS[1])
    nxt = next((s for s in AUTO_STEPS if s > cur + 0.01), AUTO_STEPS[-1])
    cfg["auto_live_cache"] = nxt
    cfg["auto_stable_since"] = time.time()
    return nxt


def auto_cache_relax(cfg, stable_secs):
    """Profil AUTO : après 2 h sans coupure, on revient d'un palier (zapping plus rapide)."""
    cur = float(cfg.get("auto_live_cache") or AUTO_STEPS[1])
    if stable_secs >= 7200 and cur > AUTO_STEPS[0]:
        lower = [s for s in AUTO_STEPS if s < cur - 0.01]
        cfg["auto_live_cache"] = lower[-1]
        return True
    return False


# =========================================================================== #
#  4. Matériel et consommation
# =========================================================================== #
def hardware():
    """(cœurs, mémoire vive en Mo, niveau 'low' | 'mid' | 'high')."""
    cores = os.cpu_count() or 2
    ram = 0
    try:
        if sys.platform.startswith("win"):
            import ctypes

            class MS(ctypes.Structure):
                _fields_ = [("l", ctypes.c_ulong), ("load", ctypes.c_ulong), ("total", ctypes.c_ulonglong),
                            ("avail", ctypes.c_ulonglong), ("tp", ctypes.c_ulonglong), ("ap", ctypes.c_ulonglong),
                            ("tv", ctypes.c_ulonglong), ("av", ctypes.c_ulonglong), ("ae", ctypes.c_ulonglong)]
            m = MS()
            m.l = ctypes.sizeof(MS)
            ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m))
            ram = m.total // (1 << 20)
        else:
            with open("/proc/meminfo") as f:
                ram = int(f.readline().split()[1]) // 1024
    except Exception:
        ram = 0
    tier = "low" if (cores <= 2 or (ram and ram < 3500)) else "high" if (cores >= 8 and ram >= 12000) else "mid"
    return cores, ram, tier


class ProcUsage:
    """Processeur (%) et mémoire (Mo) utilisés par l'application."""

    def __init__(self):
        self._last = None

    def _cpu_times(self):
        if sys.platform.startswith("win"):
            import ctypes
            from ctypes import wintypes
            k = ctypes.windll.kernel32
            c, e, kt, ut = (wintypes.FILETIME() for _ in range(4))
            k.GetProcessTimes(k.GetCurrentProcess(), ctypes.byref(c), ctypes.byref(e), ctypes.byref(kt),
                              ctypes.byref(ut))
            f = lambda t: ((t.dwHighDateTime << 32) | t.dwLowDateTime) / 1e7   # noqa: E731
            return f(kt) + f(ut)
        t = os.times()
        return t.user + t.system

    def _rss(self):
        try:
            if sys.platform.startswith("win"):
                import ctypes
                from ctypes import wintypes

                class PMC(ctypes.Structure):
                    _fields_ = [("cb", wintypes.DWORD), ("pf", wintypes.DWORD), ("peak", ctypes.c_size_t),
                                ("ws", ctypes.c_size_t), ("a", ctypes.c_size_t), ("b", ctypes.c_size_t),
                                ("c", ctypes.c_size_t), ("d", ctypes.c_size_t), ("pu", ctypes.c_size_t),
                                ("ppu", ctypes.c_size_t)]
                pmc = PMC()
                pmc.cb = ctypes.sizeof(PMC)
                ctypes.windll.psapi.GetProcessMemoryInfo(ctypes.windll.kernel32.GetCurrentProcess(),
                                                         ctypes.byref(pmc), pmc.cb)
                return pmc.ws / (1 << 20)
            with open("/proc/self/statm") as f:
                return int(f.read().split()[1]) * os.sysconf("SC_PAGE_SIZE") / (1 << 20)
        except Exception:
            return 0.0

    def sample(self):
        now, cpu = time.time(), self._cpu_times()
        pct = None
        if self._last:
            dt = now - self._last[0]
            if dt > 0:
                pct = 100.0 * (cpu - self._last[1]) / dt / (os.cpu_count() or 1)
        self._last = (now, cpu)
        return pct, self._rss()


# =========================================================================== #
#  5. Fréquence d'affichage (Windows) : 24 / 25 / 30 / 50 / 60 Hz
# =========================================================================== #
class DisplayRate:
    """Change la fréquence de l'écran qui affiche la fenêtre, puis la restaure.
    Uniquement les fréquences que l'écran déclare à sa résolution actuelle."""

    def __init__(self):
        self.device = None
        self.changed = False

    @staticmethod
    def supported():
        return sys.platform.startswith("win")

    def _api(self):
        import ctypes
        from ctypes import wintypes

        class DEVMODE(ctypes.Structure):
            _fields_ = [("dmDeviceName", wintypes.WCHAR * 32), ("dmSpecVersion", wintypes.WORD),
                        ("dmDriverVersion", wintypes.WORD), ("dmSize", wintypes.WORD),
                        ("dmDriverExtra", wintypes.WORD), ("dmFields", wintypes.DWORD),
                        ("dmPositionX", ctypes.c_long), ("dmPositionY", ctypes.c_long),
                        ("dmDisplayOrientation", wintypes.DWORD), ("dmDisplayFixedOutput", wintypes.DWORD),
                        ("dmColor", ctypes.c_short), ("dmDuplex", ctypes.c_short), ("dmYResolution", ctypes.c_short),
                        ("dmTTOption", ctypes.c_short), ("dmCollate", ctypes.c_short),
                        ("dmFormName", wintypes.WCHAR * 32), ("dmLogPixels", wintypes.WORD),
                        ("dmBitsPerPel", wintypes.DWORD), ("dmPelsWidth", wintypes.DWORD),
                        ("dmPelsHeight", wintypes.DWORD), ("dmDisplayFlags", wintypes.DWORD),
                        ("dmDisplayFrequency", wintypes.DWORD), ("dmICMMethod", wintypes.DWORD),
                        ("dmICMIntent", wintypes.DWORD), ("dmMediaType", wintypes.DWORD),
                        ("dmDitherType", wintypes.DWORD), ("dmReserved1", wintypes.DWORD),
                        ("dmReserved2", wintypes.DWORD), ("dmPanningWidth", wintypes.DWORD),
                        ("dmPanningHeight", wintypes.DWORD)]

        class MONITORINFOEX(ctypes.Structure):
            _fields_ = [("cbSize", wintypes.DWORD), ("rcMonitor", wintypes.RECT), ("rcWork", wintypes.RECT),
                        ("dwFlags", wintypes.DWORD), ("szDevice", wintypes.WCHAR * 32)]
        return ctypes, DEVMODE, MONITORINFOEX

    def _device_for(self, hwnd):
        ctypes, _D, MI = self._api()
        u = ctypes.windll.user32
        mon = u.MonitorFromWindow(ctypes.c_void_p(hwnd), 2)
        mi = MI()
        mi.cbSize = ctypes.sizeof(MI)
        if not u.GetMonitorInfoW(mon, ctypes.byref(mi)):
            return None
        return mi.szDevice

    def modes(self, hwnd):
        """Fréquences disponibles à la résolution actuelle."""
        if not self.supported():
            return []
        try:
            ctypes, D, _M = self._api()
            dev = self._device_for(hwnd)
            cur = D()
            cur.dmSize = ctypes.sizeof(D)
            ctypes.windll.user32.EnumDisplaySettingsW(dev, -1, ctypes.byref(cur))
            out, i = set(), 0
            while True:
                m = D()
                m.dmSize = ctypes.sizeof(D)
                if not ctypes.windll.user32.EnumDisplaySettingsW(dev, i, ctypes.byref(m)):
                    break
                if m.dmPelsWidth == cur.dmPelsWidth and m.dmPelsHeight == cur.dmPelsHeight and \
                        m.dmBitsPerPel == cur.dmBitsPerPel:
                    out.add(int(m.dmDisplayFrequency))
                i += 1
            return sorted(out)
        except Exception:
            return []

    @staticmethod
    def best_for_fps(fps, modes):
        if not fps or not modes:
            return None
        for mult in (1, 2, 3, 4, 5):
            for m in modes:
                if abs(m - fps * mult) < 0.6 or (abs(fps - 23.976) < 0.05 and m in (24 * mult, 23 * mult)):
                    return m
        return None

    def set(self, hwnd, hz):
        """Passe l'écran à hz ; renvoie True si c'est fait."""
        if not self.supported() or not hz:
            return False
        try:
            ctypes, D, _M = self._api()
            dev = self._device_for(hwnd)
            cur = D()
            cur.dmSize = ctypes.sizeof(D)
            ctypes.windll.user32.EnumDisplaySettingsW(dev, -1, ctypes.byref(cur))
            if int(cur.dmDisplayFrequency) == int(hz):
                return True
            if int(hz) not in self.modes(hwnd):
                return False
            cur.dmDisplayFrequency = int(hz)
            cur.dmFields = 0x400000          # DM_DISPLAYFREQUENCY
            r = ctypes.windll.user32.ChangeDisplaySettingsExW(dev, ctypes.byref(cur), None, 0x4, None)  # CDS_FULLSCREEN
            if r == 0:
                self.device, self.changed = dev, True
                return True
        except Exception:
            pass
        return False

    def restore(self):
        if not self.changed:
            return
        try:
            import ctypes
            ctypes.windll.user32.ChangeDisplaySettingsExW(self.device, None, None, 0, None)
        except Exception:
            pass
        self.changed = False


# =========================================================================== #
#  6. Maintenance
# =========================================================================== #
def dir_size(path):
    total = 0
    for root, _d, files in os.walk(path):
        for f in files:
            try:
                total += os.path.getsize(os.path.join(root, f))
            except OSError:
                pass
    return total


def clean_cache(dirs, max_mb, max_age_days=60):
    """Supprime les fichiers trop vieux puis les plus anciens au-delà de max_mb. Renvoie (fichiers, octets)."""
    files = []
    now = time.time()
    removed = freed = 0
    for d in dirs:
        for root, _x, names in os.walk(d):
            for n in names:
                p = os.path.join(root, n)
                try:
                    st = os.stat(p)
                except OSError:
                    continue
                if now - st.st_atime > max_age_days * 86400 and now - st.st_mtime > max_age_days * 86400:
                    try:
                        os.remove(p)
                        removed += 1
                        freed += st.st_size
                    except OSError:
                        pass
                    continue
                files.append((max(st.st_atime, st.st_mtime), st.st_size, p))
    total = sum(f[1] for f in files)
    limit = max_mb * (1 << 20)
    for _t, size, p in sorted(files):
        if total <= limit:
            break
        try:
            os.remove(p)
            total -= size
            removed += 1
            freed += size
        except OSError:
            pass
    return removed, freed


def auto_backup(cfg_path, backup_dir, keep=7):
    """Copie quotidienne de la configuration (7 dernières gardées). Renvoie le chemin créé ou None."""
    if not os.path.isfile(cfg_path):
        return None
    os.makedirs(backup_dir, exist_ok=True)
    name = f"config-{datetime.now():%Y%m%d}.json"
    dst = os.path.join(backup_dir, name)
    if os.path.exists(dst):
        return None
    shutil.copy2(cfg_path, dst)
    olds = sorted(f for f in os.listdir(backup_dir) if f.startswith("config-") and f.endswith(".json"))
    for f in olds[:-keep]:
        try:
            os.remove(os.path.join(backup_dir, f))
        except OSError:
            pass
    return dst


def probe_stream(url, user_agent, timeout=8):
    """Vérifie qu'un flux répond et envoie des données. Renvoie (ok, détail)."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": user_agent, "Range": "bytes=0-65535"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = r.read(4096)
            ct = r.headers.get("Content-Type", "")
            if not data:
                return False, "aucune donnée"
            if "text/html" in ct and b"#EXTM3U" not in data:
                return False, "page web au lieu d'une vidéo"
            return True, f"{r.status} · {ct or '?'}"
    except Exception as e:
        return False, str(e)[:120]


def check_streams(urls, user_agent, stats=None, workers=8, timeout=8, progress=None):
    """Teste plusieurs flux en parallèle. Renvoie {url: (ok, détail)}."""
    out, lock = {}, threading.Lock()
    queue = list(urls)

    def work():
        while True:
            with lock:
                if not queue:
                    return
                u = queue.pop()
            ok, msg = probe_stream(u, user_agent, timeout)
            with lock:
                out[u] = (ok, msg)
                if stats:
                    (stats.ok if ok else stats.fail)(u)
                if progress:
                    progress(len(out), len(urls))
    th = [threading.Thread(target=work, daemon=True) for _ in range(max(1, min(workers, len(urls))))]
    for t in th:
        t.start()
    for t in th:
        t.join()
    return out


# =========================================================================== #
#  7. Guide TV (XMLTV)
# =========================================================================== #
_PROG_RE = re.compile(r"<programme\b([^>]*)>(.*?)</programme>", re.S)
_ATTR_RE = re.compile(r'(\w+)="([^"]*)"')
_TITLE_RE = re.compile(r"<title\b[^>]*>(.*?)</title>", re.S)
_DESC_RE = re.compile(r"<desc\b[^>]*>(.*?)</desc>", re.S)
_CHAN_RE = re.compile(r'<channel\b[^>]*\bid="([^"]*)"[^>]*>(.*?)</channel>', re.S)
_DNAME_RE = re.compile(r"<display-name\b[^>]*>(.*?)</display-name>", re.S)


def _xml_text(s):
    import html as _html
    s = re.sub(r"<!\[CDATA\[(.*?)\]\]>", r"\1", s or "", flags=re.S)
    return _html.unescape(re.sub(r"<[^>]+>", "", s)).strip()


def xmltv_time(s):
    """« 20261125203000 +0100 » → horodatage Unix."""
    m = re.match(r"(\d{14})\s*([+-]\d{4})?", (s or "").strip())
    if not m:
        return 0
    dt = datetime.strptime(m.group(1), "%Y%m%d%H%M%S")
    off = m.group(2) or "+0000"
    sign = 1 if off[0] == "+" else -1
    secs = sign * (int(off[1:3]) * 3600 + int(off[3:5]) * 60)
    return int(dt.replace(tzinfo=timezone.utc).timestamp()) - secs


def parse_xmltv(data, keep_ids=None, hours=30):
    """Lit un guide XMLTV (éventuellement compressé .gz). Ne garde que les programmes des
    prochaines `hours` heures. Renvoie {"progs": {channel_id: [[start, stop, titre, desc], …]},
    "names": {nom normalisé: channel_id}}."""
    if data[:2] == b"\x1f\x8b":
        data = gzip.decompress(data)
    text = data.decode("utf-8", "replace")
    now = time.time()
    lo, hi = now - 3 * 3600, now + hours * 3600
    names = {}
    for cid, body in _CHAN_RE.findall(text):
        for dn in _DNAME_RE.findall(body):
            k = re.sub(r"[^a-z0-9]+", "", _norm(strip_quality(_xml_text(dn))))
            if k:
                names.setdefault(k, cid)
    progs = {}
    for attrs, body in _PROG_RE.findall(text):
        a = dict(_ATTR_RE.findall(attrs))
        cid = a.get("channel", "")
        if keep_ids is not None and cid not in keep_ids:
            continue
        st, sp = xmltv_time(a.get("start")), xmltv_time(a.get("stop"))
        if not st or sp < lo or st > hi:
            continue
        t = _TITLE_RE.search(body)
        d = _DESC_RE.search(body)
        progs.setdefault(cid, []).append([st, sp or st + 1800, _xml_text(t.group(1)) if t else "",
                                          (_xml_text(d.group(1)) if d else "")[:400]])
    for v in progs.values():
        v.sort()
    return {"progs": progs, "names": names, "updated": int(now)}


def epg_for(guide, item):
    """Programmes en cours et à venir d'une chaîne (format des listes Xtream : title, start_ts, stop_ts, desc)."""
    if not guide:
        return []
    progs = guide.get("progs") or {}
    cid = item.get("tvg_id") or ""
    if cid not in progs:
        k = re.sub(r"[^a-z0-9]+", "", _norm(display_name(item.get("name"))))
        cid = (guide.get("names") or {}).get(k, "")
    now = time.time()
    out = []
    for st, sp, title, desc in progs.get(cid) or []:
        if sp > now:
            out.append({"title": title, "start_ts": st, "stop_ts": sp, "desc": desc})
        if len(out) >= 4:
            break
    return out


# =========================================================================== #
#  8. Administration web locale
# =========================================================================== #
def local_ips():
    """Adresses IPv4 du réseau local (la plus probable d'abord)."""
    ips = []
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("10.255.255.255", 1))      # aucun paquet envoyé : sert seulement à trouver l'interface
        ips.append(s.getsockname()[0])
        s.close()
    except OSError:
        pass
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ips.append(info[4][0])
    except OSError:
        pass
    out = []
    for ip in ips:
        if ip.startswith("127.") or ip in out:
            continue
        out.append(ip)

    def rank(a):
        return 0 if a.startswith("192.168.") else 1 if a.startswith("10.") else 2 if a.startswith("172.") else 3
    return sorted(out, key=rank)


def is_local_client(addr):
    """N'accepte que le réseau local (jamais Internet)."""
    try:
        ip = ipaddress.ip_address(addr)
        return ip.is_private or ip.is_loopback or ip.is_link_local
    except ValueError:
        return False


class AdminServer:
    """Serveur web de l'administration. `api` est un objet de l'application qui répond aux
    demandes (voir AdminApi dans iptv_player.py) ; toutes ses méthodes reçoivent des données JSON."""

    def __init__(self, api, html_path, port=8080, pin="000000"):
        self.api, self.html_path = api, html_path
        self.port, self.pin = port, str(pin)
        self.httpd = None
        self.tokens = {}
        self.fails = {}
        self.logs = []

    # -- journal technique partagé
    def log(self, msg):
        self.logs.append(f"{datetime.now():%H:%M:%S}  {msg}")
        del self.logs[:-500]

    def start(self):
        if self.httpd:
            return self.port
        handler = self._handler()
        last = None
        for port in [self.port] + list(range(8081, 8100)):
            try:
                self.httpd = _ThreadingServer(("0.0.0.0", port), handler)
                self.port = port
                break
            except OSError as e:
                last = e
        if not self.httpd:
            raise OSError(f"aucun port libre ({last})")
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()
        self.log(f"Administration web démarrée sur le port {self.port}")
        return self.port

    def stop(self):
        if self.httpd:
            try:
                self.httpd.shutdown()
                self.httpd.server_close()
            except Exception:
                pass
            self.httpd = None

    def urls(self):
        return [f"http://{ip}:{self.port}" for ip in local_ips()] or [f"http://127.0.0.1:{self.port}"]

    def _handler(self):
        srv = self

        class H(http.server.BaseHTTPRequestHandler):
            server_version = "IPTVPlayerAdmin"
            protocol_version = "HTTP/1.1"

            def log_message(self, *a):
                pass

            def _send(self, code, body, ctype="application/json; charset=utf-8", extra=None):
                if isinstance(body, (dict, list)):
                    body = json.dumps(body, ensure_ascii=False).encode("utf-8")
                elif isinstance(body, str):
                    body = body.encode("utf-8")
                self.send_response(code)
                self.send_header("Content-Type", ctype)
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-store")
                self.send_header("X-Content-Type-Options", "nosniff")
                self.send_header("Referrer-Policy", "no-referrer")
                for k, v in (extra or {}).items():
                    self.send_header(k, v)
                self.end_headers()
                self.wfile.write(body)

            def _body(self, limit=200 * 1024 * 1024):
                n = int(self.headers.get("Content-Length") or 0)
                if n > limit:
                    raise ValueError("envoi trop volumineux")
                data = b""
                while len(data) < n:
                    chunk = self.rfile.read(min(1 << 20, n - len(data)))
                    if not chunk:
                        break
                    data += chunk
                return data

            def _auth(self):
                tok = self.headers.get("X-Token") or ""
                exp = srv.tokens.get(tok)
                if exp and exp > time.time():
                    srv.tokens[tok] = time.time() + 12 * 3600
                    return True
                return False

            def _route(self, method):
                if not is_local_client(self.client_address[0]):
                    return self._send(403, {"error": "réseau local uniquement"})
                u = urllib.parse.urlparse(self.path)
                path, q = u.path, {k: v[0] for k, v in urllib.parse.parse_qs(u.query).items()}
                if method == "GET" and path in ("/", "/index.html"):
                    try:
                        with open(srv.html_path, "rb") as f:
                            return self._send(200, f.read(), "text/html; charset=utf-8",
                                              {"Content-Security-Policy":
                                               "default-src 'self'; img-src * data:; style-src 'self' 'unsafe-inline'; "
                                               "script-src 'self' 'unsafe-inline'"})
                    except OSError:
                        return self._send(500, "page d'administration introuvable", "text/plain; charset=utf-8")
                if path == "/api/login" and method == "POST":
                    ip = self.client_address[0]
                    n, until = srv.fails.get(ip, (0, 0))
                    if until > time.time():
                        return self._send(429, {"error": f"trop d'essais, réessayez dans {int(until - time.time())} s"})
                    try:
                        pin = str(json.loads(self._body(4096) or b"{}").get("pin", ""))
                    except ValueError:
                        pin = ""
                    if secrets.compare_digest(pin, srv.pin):
                        srv.fails.pop(ip, None)
                        tok = secrets.token_urlsafe(24)
                        srv.tokens[tok] = time.time() + 12 * 3600
                        srv.log(f"Connexion à l'administration depuis {ip}")
                        return self._send(200, {"token": tok})
                    n += 1
                    srv.fails[ip] = (n, time.time() + (30 if n >= 5 else 0))
                    srv.log(f"Code PIN incorrect depuis {ip}")
                    return self._send(401, {"error": "code PIN incorrect"})
                if not path.startswith("/api/"):
                    return self._send(404, {"error": "introuvable"})
                if not self._auth():
                    return self._send(401, {"error": "connexion requise"})
                try:
                    if path == "/api/logs":
                        return self._send(200, {"lines": srv.logs + srv.api.app_logs()})
                    if path == "/api/backup" and method == "GET":
                        data = srv.api.backup()
                        return self._send(200, json.dumps(data, ensure_ascii=False, indent=1),
                                          "application/json; charset=utf-8",
                                          {"Content-Disposition":
                                           f'attachment; filename="iptv-player-sauvegarde-{datetime.now():%Y%m%d}.json"'})
                    if path == "/api/upload" and method == "POST":
                        name = urllib.parse.unquote(self.headers.get("X-Name") or "liste.m3u")
                        res = srv.api.upload(name, self._body())
                        srv.log(f"Liste importée : {name}")
                        return self._send(200, res)
                    body = {}
                    if method == "POST":
                        raw = self._body(20 * 1024 * 1024)
                        body = json.loads(raw or b"{}")
                    res = srv.api.handle(method, path[5:], q, body)
                    if method == "POST":
                        srv.log(f"{path[5:]} : ok")
                    return self._send(200, res if res is not None else {"ok": True})
                except PermissionError as e:
                    return self._send(403, {"error": str(e)})
                except (ValueError, KeyError, LookupError) as e:
                    return self._send(400, {"error": str(e)})
                except Exception as e:
                    srv.log(f"Erreur {path} : {e}")
                    return self._send(500, {"error": str(e)})

            def do_GET(self):
                self._route("GET")

            def do_POST(self):
                self._route("POST")

        return H


class _ThreadingServer(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True
    allow_reuse_address = True


# =========================================================================== #
#  9. QR code (sans module externe) — mode octet, correction M, versions 1 à 10
# =========================================================================== #
_QR_EC_M = {  # version: (octets de correction par bloc, [(nb blocs, octets de données par bloc), …])
    1: (10, [(1, 16)]), 2: (16, [(1, 28)]), 3: (26, [(1, 44)]), 4: (18, [(2, 32)]), 5: (24, [(2, 43)]),
    6: (16, [(4, 27)]), 7: (18, [(4, 31)]), 8: (22, [(2, 38), (2, 39)]), 9: (22, [(3, 36), (2, 37)]),
    10: (26, [(4, 43), (1, 44)]),
}
_QR_ALIGN = {1: [], 2: [6, 18], 3: [6, 22], 4: [6, 26], 5: [6, 30], 6: [6, 34], 7: [6, 22, 38], 8: [6, 24, 42],
             9: [6, 26, 46], 10: [6, 28, 50]}


def _gf_tables():
    exp, log = [0] * 512, [0] * 256
    x = 1
    for i in range(255):
        exp[i] = x
        log[x] = i
        x <<= 1
        if x & 0x100:
            x ^= 0x11D
    for i in range(255, 512):
        exp[i] = exp[i - 255]
    return exp, log


_EXP, _LOG = _gf_tables()


def _rs_ecc(data, n):
    gen = [1]
    for i in range(n):
        ng = [0] * (len(gen) + 1)
        for j, g in enumerate(gen):
            ng[j] ^= g
            if g:
                ng[j + 1] ^= _EXP[_LOG[g] + i]
        gen = ng
    res = list(data) + [0] * n
    for i in range(len(data)):
        c = res[i]
        if c:
            for j in range(1, len(gen)):
                if gen[j]:
                    res[i + j] ^= _EXP[_LOG[gen[j]] + _LOG[c]]
    return res[len(data):]


def qr_matrix(text):
    """Matrice QR (liste de listes de booléens, vrai = noir) pour un texte court (≤ 213 octets)."""
    data = text.encode("utf-8")
    ver = None
    for v in range(1, 11):
        ecn, blocks = _QR_EC_M[v]
        cap = sum(n * k for n, k in blocks)
        if 4 + (8 if v < 10 else 16) + 8 * len(data) <= cap * 8:
            ver = v
            break
    if ver is None:
        raise ValueError("texte trop long pour le QR code")
    ecn, blocks = _QR_EC_M[ver]
    cap = sum(n * k for n, k in blocks)
    bits = [0, 1, 0, 0]
    cnt_bits = 8 if ver < 10 else 16
    bits += [(len(data) >> i) & 1 for i in range(cnt_bits - 1, -1, -1)]
    for b in data:
        bits += [(b >> i) & 1 for i in range(7, -1, -1)]
    bits += [0] * min(4, cap * 8 - len(bits))
    bits += [0] * (-len(bits) % 8)
    cw = [int("".join(map(str, bits[i:i + 8])), 2) for i in range(0, len(bits), 8)]
    pad, i = [0xEC, 0x11], 0
    while len(cw) < cap:
        cw.append(pad[i % 2])
        i += 1
    blks, eccs, pos = [], [], 0
    for n, k in blocks:
        for _ in range(n):
            b = cw[pos:pos + k]
            pos += k
            blks.append(b)
            eccs.append(_rs_ecc(b, ecn))
    final = []
    for i in range(max(len(b) for b in blks)):
        for b in blks:
            if i < len(b):
                final.append(b[i])
    for i in range(ecn):
        for e in eccs:
            final.append(e[i])
    size = 17 + 4 * ver
    m = [[None] * size for _ in range(size)]

    def finder(r, c):
        for dr in range(-1, 8):
            for dc in range(-1, 8):
                rr, cc = r + dr, c + dc
                if 0 <= rr < size and 0 <= cc < size:
                    on = (0 <= dr <= 6 and dc in (0, 6)) or (0 <= dc <= 6 and dr in (0, 6)) or \
                         (2 <= dr <= 4 and 2 <= dc <= 4)
                    m[rr][cc] = on
    finder(0, 0)
    finder(0, size - 7)
    finder(size - 7, 0)
    for i in range(8, size - 8):
        m[6][i] = m[i][6] = (i % 2 == 0)
    al = _QR_ALIGN[ver]
    last = len(al) - 1
    for i, r in enumerate(al):
        for j, c in enumerate(al):
            if (i, j) in ((0, 0), (0, last), (last, 0)):
                continue
            for dr in range(-2, 3):
                for dc in range(-2, 3):
                    m[r + dr][c + dc] = max(abs(dr), abs(dc)) != 1
    m[size - 8][8] = True
    reserved = set()
    for i in range(9):
        reserved.add((8, i))
        reserved.add((i, 8))
    for i in range(8):
        reserved.add((8, size - 1 - i))
        reserved.add((size - 1 - i, 8))
    if ver >= 7:
        for i in range(6):
            for j in range(3):
                reserved.add((i, size - 11 + j))
                reserved.add((size - 11 + j, i))
    dbits = []
    for b in final:
        dbits += [(b >> i) & 1 for i in range(7, -1, -1)]
    idx = 0
    up = True
    col = size - 1
    coords = []
    while col > 0:
        if col == 6:
            col -= 1
        rows = range(size - 1, -1, -1) if up else range(size)
        for r in rows:
            for c in (col, col - 1):
                if m[r][c] is None and (r, c) not in reserved:
                    coords.append((r, c))
        up = not up
        col -= 2
    best = None
    for mask in range(8):
        mm = [row[:] for row in m]
        idx = 0
        for r, c in coords:
            bit = dbits[idx] if idx < len(dbits) else 0
            idx += 1
            f = [(r + c) % 2, r % 2, c % 3, (r + c) % 3, (r // 2 + c // 3) % 2, (r * c) % 2 + (r * c) % 3,
                 ((r * c) % 2 + (r * c) % 3) % 2, ((r + c) % 2 + (r * c) % 3) % 2][mask] == 0
            mm[r][c] = bool(bit) ^ f
        _qr_format(mm, size, mask, ver)
        pen = _qr_penalty(mm, size)
        if best is None or pen < best[0]:
            best = (pen, mm)
    return [[bool(x) for x in row] for row in best[1]]


def _qr_format(m, size, mask, ver):
    data = (0b00 << 3) | mask          # niveau M = 00
    rem = data
    for _ in range(10):
        rem = (rem << 1) ^ ((rem >> 9) * 0x537)
    bits = ((data << 10) | rem) ^ 0x5412
    fb = [(bits >> i) & 1 for i in range(15)]
    for i in range(6):
        m[i][8] = bool(fb[i])
    m[7][8] = bool(fb[6])
    m[8][8] = bool(fb[7])
    m[8][7] = bool(fb[8])
    for i in range(9, 15):
        m[8][14 - i] = bool(fb[i])
    for i in range(8):
        m[8][size - 1 - i] = bool(fb[i])
    for i in range(8, 15):
        m[size - 15 + i][8] = bool(fb[i])
    m[size - 8][8] = True
    if ver >= 7:
        rem = ver
        for _ in range(12):
            rem = (rem << 1) ^ ((rem >> 11) * 0x1F25)
        vb = (ver << 12) | rem
        for i in range(18):
            bit = bool((vb >> i) & 1)
            a, b = size - 11 + i % 3, i // 3
            m[a][b] = bit
            m[b][a] = bit


def _qr_penalty(m, size):
    """Pénalités de la norme (règles 1 à 4) pour choisir le masque le plus lisible."""
    pen = 0
    pat1 = [True, False, True, True, True, False, True, False, False, False, False]
    pat2 = pat1[::-1]
    for rows in (m, [list(x) for x in zip(*m)]):
        for row in rows:
            run, prev = 0, None
            for x in row:
                if x == prev:
                    run += 1
                else:
                    if run >= 5:
                        pen += run - 2
                    run, prev = 1, x
            if run >= 5:
                pen += run - 2
            for i in range(size - 10):
                seg = row[i:i + 11]
                if seg == pat1 or seg == pat2:
                    pen += 40
    for r in range(size - 1):
        for c in range(size - 1):
            if m[r][c] == m[r][c + 1] == m[r + 1][c] == m[r + 1][c + 1]:
                pen += 3
    dark = sum(sum(1 for x in row if x) for row in m)
    pen += (abs(dark * 100 // (size * size) - 50) // 5) * 10
    return pen


def qr_svg(text, scale=6, border=4):
    mat = qr_matrix(text)
    n = len(mat) + 2 * border
    rects = "".join(f'<rect x="{c + border}" y="{r + border}" width="1" height="1"/>'
                    for r, row in enumerate(mat) for c, x in enumerate(row) if x)
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {n} {n}" width="{n * scale}" '
            f'height="{n * scale}" shape-rendering="crispEdges"><rect width="{n}" height="{n}" fill="#fff"/>'
            f'<g fill="#000">{rects}</g></svg>')


def b64(s):
    return base64.b64encode(s.encode()).decode()


