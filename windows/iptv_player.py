#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
IPTV Player — lecteur IPTV pour Windows (interface façon « médiathèque »)

  • Sources : listes M3U / M3U8 (lien ou fichier) et comptes Xtream Codes
  • Accueil : grande bannière, « Continuer à regarder », nouveautés, rangées par catégorie
  • Chaînes TV classées par pays et catégories, zapping, programme en cours (EPG Xtream)
  • Fiches films / séries : fond, affiche, synopsis, genres, note, âge, durée, bande-annonce
  • Séries : saisons, épisodes avec vignettes et résumé, épisode suivant automatique
  • Fiches acteurs : photo, biographie, filmographie, titres disponibles dans votre liste
  • Reprise de lecture, favoris (« Ma liste »), recherche globale
  • Lecture intégrée VLC : pistes audio, sous-titres, plein écran

Métadonnées : celles du fournisseur Xtream, enrichies par TMDB si une clé (gratuite)
est renseignée dans Paramètres (photos d'acteurs, biographies, filmographies…).

Dépendances : PySide6, python-vlc (+ VLC 64 bits installé, ou dossier « vlc » à côté).
"""

import os
import re
import sys
import ssl
import json
import math
import time
import uuid
import shutil
import threading
import http.server
import base64
import random
import hashlib
import html
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter, OrderedDict
from datetime import datetime

from PySide6 import QtCore, QtGui, QtWidgets, QtNetwork

Qt = QtCore.Qt

# --------------------------------------------------------------------------- #
#  Chemins & constantes
# --------------------------------------------------------------------------- #
APP_TITLE = "IPTV Player"
APP_VERSION = "2.7"
APP_AUTHOR = "Asvind"
FROZEN = getattr(sys, "frozen", False)
APP_DIR = os.path.dirname(os.path.abspath(sys.executable if FROZEN else __file__))
DATA_DIR = os.path.join(os.environ.get("APPDATA") or os.path.expanduser("~"), "IPTVPlayer")
IMG_DIR = os.path.join(DATA_DIR, "images")
CACHE_DIR = os.path.join(DATA_DIR, "cache")
META_DIR = os.path.join(DATA_DIR, "meta")
CONFIG_PATH = os.path.join(DATA_DIR, "config.json")
for _d in (DATA_DIR, IMG_DIR, CACHE_DIR, META_DIR):
    os.makedirs(_d, exist_ok=True)

USER_AGENT = "VLC/3.0.21 LibVLC/3.0.21"
TMDB_API = os.environ.get("IPTV_TMDB_API", "https://api.themoviedb.org/3")
TMDB_IMG = os.environ.get("IPTV_TMDB_IMG", "https://image.tmdb.org/t/p/")
# Clé TMDB intégrée (jaquettes, fonds, acteurs) : utilisée si aucune clé n'est saisie dans Paramètres.
TMDB_BUILTIN_KEY = (
    "eyJhbGciOiJIUzI1NiJ9.eyJhdWQiOiIyOWY2NWExMTI1MjcyNzVmYTU2OGMyODcyYmRhZmMzYSIsIm5iZiI6MTc0MzI3NDQ5OC43NjE5OTk4LCJzdWIiOiI2N2U4NDIwMjhmMzAzZDJmOTVkZGIyZDciLCJzY29wZXMiOlsiYXBpX3JlYWQiXSwidmVyc2lvbiI6MX0.3SJ9Hu2wA19lIcXGCFlknP_K68OSZztLZFC7zrDBrNY")
_TMDB_SIZE_RE = re.compile(r"(/t/p/)(w\d+|original|h\d+)(/)")


def tmdb_key_of(cfg):
    return (cfg.get("tmdb_key") or "").strip() or TMDB_BUILTIN_KEY


def hires(url, size="w1280"):
    """Remplace la taille d'une image TMDB (w300…) par une plus grande."""
    if not url or "/t/p/" not in url:
        return url or ""
    return _TMDB_SIZE_RE.sub(lambda m: m.group(1) + size + m.group(3), url, count=1)
META_TTL = 7 * 86400
META_REFRESH = 86400          # fiches actualisées en arrière-plan une fois par jour
ITEM_ROLE = Qt.ItemDataRole.UserRole + 1

BG = "#040506"
ACCENT = "#2E8BFF"      # bleu OCTO (icônes, sélection)
RED = "#E8252C"         # badges (LIVE, Indisponible)
SIDEBAR_TOP = "#2a3440"
SIDEBAR_BOTTOM = "#10151c"
FLAG = ["#e8252c", "#1a5fd8", "#f6c400", "#0e9a48"]   # rouge, bleu, jaune, vert
AVATAR_COLORS = ["#e8252c", "#1a5fd8", "#f6a600", "#0e9a48", "#8b3fd9", "#e0457b", "#11a3b5", "#5b6478"]
AVATAR_EMOJIS = ["", "🦤", "🦁", "🐯", "🦊", "🐼", "🐸", "🐙", "🦄", "🐬", "🚀", "⚽", "🎮", "🎬", "🎧", "⭐"]
ADULT_RE = re.compile(r"(?i)(\badult[e]?s?\b|xxx|porn|\b18\s*\+|\+\s*18\b|erotic|érotique|\bsexy\b)")


def asset(name):
    return os.path.join(APP_DIR, name)


def logo_pixmap(height, bg=None):
    """Logo adapté au fond : version claire (bleu marine) ou sombre (inversée, couleurs du drapeau conservées)."""
    dark_bg = True if bg is None else QtGui.QColor(bg).lightnessF() < 0.5
    path = asset("logo_dark.png" if dark_bg else "logo_light.png")
    pm = QtGui.QPixmap(path) if os.path.exists(path) else QtGui.QPixmap()
    if pm.isNull():
        return None
    dpr = _dpr()
    pm = pm.scaledToHeight(int(height * dpr), Qt.TransformationMode.SmoothTransformation)
    pm.setDevicePixelRatio(dpr)
    return pm

_vlc_dir = os.path.join(APP_DIR, "vlc")
if os.path.isfile(os.path.join(_vlc_dir, "libvlc.dll")):
    os.environ["PYTHON_VLC_LIB_PATH"] = os.path.join(_vlc_dir, "libvlc.dll")
    os.environ["PYTHON_VLC_MODULE_PATH"] = os.path.join(_vlc_dir, "plugins")
    if hasattr(os, "add_dll_directory"):
        os.add_dll_directory(_vlc_dir)
try:
    import vlc  # python-vlc
    VLC_ERROR = None
except Exception as _e:
    vlc = None
    VLC_ERROR = str(_e)

# --------------------------------------------------------------------------- #
#  Pays
# --------------------------------------------------------------------------- #
COUNTRIES = {
    "FR": "France", "BE": "Belgique", "CH": "Suisse", "LU": "Luxembourg", "CA": "Canada",
    "US": "États-Unis", "GB": "Royaume-Uni", "IE": "Irlande", "DE": "Allemagne", "AT": "Autriche",
    "IT": "Italie", "ES": "Espagne", "PT": "Portugal", "NL": "Pays-Bas", "PL": "Pologne",
    "RO": "Roumanie", "BG": "Bulgarie", "GR": "Grèce", "TR": "Turquie", "RU": "Russie",
    "UA": "Ukraine", "SE": "Suède", "NO": "Norvège", "DK": "Danemark", "FI": "Finlande",
    "CZ": "Tchéquie", "SK": "Slovaquie", "HU": "Hongrie", "HR": "Croatie", "RS": "Serbie",
    "BA": "Bosnie", "SI": "Slovénie", "AL": "Albanie", "MK": "Macédoine du Nord",
    "MA": "Maroc", "DZ": "Algérie", "TN": "Tunisie", "EG": "Égypte", "SA": "Arabie saoudite",
    "AE": "Émirats arabes unis", "QA": "Qatar", "LB": "Liban", "IQ": "Irak", "IR": "Iran",
    "IL": "Israël", "IN": "Inde", "PK": "Pakistan", "BD": "Bangladesh", "CN": "Chine",
    "JP": "Japon", "KR": "Corée du Sud", "TH": "Thaïlande", "VN": "Vietnam", "PH": "Philippines",
    "ID": "Indonésie", "MY": "Malaisie", "AU": "Australie", "NZ": "Nouvelle-Zélande",
    "MX": "Mexique", "BR": "Brésil", "AR": "Argentine", "CL": "Chili", "CO": "Colombie",
    "PE": "Pérou", "VE": "Venezuela", "SN": "Sénégal", "CI": "Côte d'Ivoire", "CM": "Cameroun",
    "CD": "RD Congo", "ML": "Mali", "NG": "Nigeria", "GH": "Ghana", "ZA": "Afrique du Sud",
    "HT": "Haïti", "ARAB": "Monde arabe", "AFR": "Afrique", "LAT": "Amérique latine",
    "EXYU": "Ex-Yougoslavie", "INT": "International", "ZZ": "Autres",
}
ALIASES = {
    "UK": "GB", "ENG": "GB", "USA": "US", "FRA": "FR", "BEL": "BE", "SUI": "CH", "CHE": "CH",
    "CAN": "CA", "QC": "CA", "GER": "DE", "DEU": "DE", "ITA": "IT", "ESP": "ES", "SPA": "ES",
    "POR": "PT", "PRT": "PT", "BRA": "BR", "NLD": "NL", "HOL": "NL", "POL": "PL", "ROU": "RO",
    "ROM": "RO", "TUR": "TR", "RUS": "RU", "UKR": "UA", "GRE": "GR", "SWE": "SE", "NOR": "NO",
    "DEN": "DK", "FIN": "FI", "ALB": "AL", "MAR": "MA", "ALG": "DZ", "TUN": "TN", "EGY": "EG",
    "KSA": "SA", "UAE": "AE", "IND": "IN", "PAK": "PK", "CHN": "CN", "JPN": "JP", "KOR": "KR",
    "MEX": "MX", "ARG": "AR",
    "AR": "ARAB", "ARB": "ARAB", "ARA": "ARAB", "ARABIC": "ARAB",
    "EXYU": "EXYU", "YU": "EXYU", "LATINO": "LAT", "AFRICA": "AFR", "AFRIQUE": "AFR",
}
_NAME_TO_CODE = {unicodedata.normalize("NFC", n.upper()): c
                 for c, n in COUNTRIES.items() if c not in ("INT", "ZZ")}
_NAME_TO_CODE.update({
    "FRANCE": "FR", "FRENCH": "FR", "BELGIUM": "BE", "SWITZERLAND": "CH", "GERMANY": "DE",
    "GERMAN": "DE", "ITALY": "IT", "ITALIAN": "IT", "SPAIN": "ES", "SPANISH": "ES",
    "PORTUGAL": "PT", "PORTUGUESE": "PT", "NETHERLANDS": "NL", "DUTCH": "NL", "POLAND": "PL",
    "ROMANIA": "RO", "TURKEY": "TR", "TURKISH": "TR", "RUSSIA": "RU", "GREECE": "GR",
    "SWEDEN": "SE", "NORWAY": "NO", "DENMARK": "DK", "FINLAND": "FI", "UNITED STATES": "US",
    "UNITED KINGDOM": "GB", "ENGLAND": "GB", "BRAZIL": "BR", "MEXICO": "MX", "ARGENTINA": "AR",
    "MOROCCO": "MA", "ALGERIA": "DZ", "TUNISIA": "TN", "EGYPT": "EG", "INDIA": "IN",
    "CHINA": "CN", "JAPAN": "JP", "KOREA": "KR", "QUEBEC": "CA", "QUÉBEC": "CA",
    "ARABIC": "ARAB", "ARAB": "ARAB", "LATINO": "LAT", "AFRICA": "AFR", "AFRIQUE": "AFR",
    "EX-YU": "EXYU", "ITALIA": "IT", "DEUTSCHLAND": "DE", "ESPAÑA": "ES", "ESPANA": "ES",
    "NEDERLAND": "NL", "POLSKA": "PL", "TÜRKIYE": "TR", "TURKIYE": "TR", "BRASIL": "BR",
    "SVERIGE": "SE", "NORGE": "NO", "DANMARK": "DK", "SUOMI": "FI", "SCHWEIZ": "CH",
    "MAGHREB": "MA", "USA": "US", "UK": "GB", "CANADA": "CA",
})
_NAME_RE = re.compile(r"\b(" + "|".join(sorted(map(re.escape, _NAME_TO_CODE), key=len, reverse=True)) + r")\b")
_PREFIX_RE = re.compile(
    r"^[\s|\[\(\{#★•▶\-]*(EX-?YU|LATINO|ARABIC|AFRICA|AFRIQUE|[A-Z]{2,3})(?=\s*[|\]\)\}:\-–»/]|\s|$)")
_SUFFIX_RE = re.compile(r"(?:^|[\s\(\[|])([A-Z]{2,3})[\)\]|]?\s*$")
_TVGID_RE = re.compile(r"\.([a-z]{2})(?:@|$)")


def _resolve(tok):
    t = tok.upper().replace("-", "").replace(" ", "")
    t = ALIASES.get(t, t)
    return t if t in COUNTRIES and t != "ZZ" else None


def detect_country(group="", name="", tvg_country="", tvg_id=""):
    for tok in re.split(r"[;,|/ ]+", tvg_country or ""):
        t = {"UK": "GB"}.get(tok.strip().upper(), tok.strip().upper())
        if t in COUNTRIES and t != "ZZ":
            return t
    for text in (group, name):
        m = _PREFIX_RE.match(text or "")
        if m and _resolve(m.group(1)):
            return _resolve(m.group(1))
    if tvg_id:
        m = _TVGID_RE.search(tvg_id.lower())
        if m:
            t = {"UK": "GB"}.get(m.group(1).upper(), m.group(1).upper())
            if t in COUNTRIES:
                return t
    if group:
        m = _NAME_RE.search(unicodedata.normalize("NFC", group.upper()))
        if m:
            return _NAME_TO_CODE[m.group(1)]
    for text in (group, name):
        m = _SUFFIX_RE.search(text or "")
        if m and _resolve(m.group(1)):
            return _resolve(m.group(1))
    return "ZZ"


def country_name(code):
    return COUNTRIES.get(code, code)


# --------------------------------------------------------------------------- #
#  Texte
# --------------------------------------------------------------------------- #
def norm(s):
    s = unicodedata.normalize("NFKD", (s or "").lower())
    return "".join(c for c in s if not unicodedata.combining(c))


def title_key(s):
    return re.sub(r"[^a-z0-9]+", "", norm(s))


def initials(name):
    words = re.findall(r"[A-Za-zÀ-ÿ0-9]+", name or "")
    if not words:
        return "TV"
    if len(words) == 1:
        return words[0][:3].upper()
    return (words[0][0] + words[1][0]).upper()


_QUALITY_RE = re.compile(
    r"(?<![A-Za-z0-9])(4K|UHD|FHD|HD|SD|HEVC|H\.?265|H\.?264|x265|x264|2160p|1080p|720p|MULTI|"
    r"VOSTFR|VOST|VFF|VFQ|VFi|VF|TRUEFRENCH|FRENCH|HDR10?|DV|3D|REMUX|WEB-?DL|BLURAY)(?![A-Za-z0-9])",
    re.I)
_LEAD_TAG_RE = re.compile(r"^\s*(?:[\[\(|]\s*([A-Za-z\-]{2,7})\s*[\]\)|]|([A-Z\-]{2,7})\s*(?:[:|»–]|\s-\s))\s*")
_LEAD_OK = {"VF", "VFF", "VFQ", "VOST", "VOSTFR", "MULTI", "4K", "UHD", "FHD", "HD", "NEW", "VIP", "TOP"}


def strip_lead_tags(s):
    for _ in range(3):
        m = _LEAD_TAG_RE.match(s)
        if not m:
            break
        tok = (m.group(1) or m.group(2) or "").upper()
        if _resolve(tok) or tok in _LEAD_OK:
            s = s[m.end():]
        else:
            break
    return s.strip() or s


_GRP_PREFIX = re.compile(r"^\s*[|\[(]?\s*(?:VOD|FILMS?|MOVIES?|S[ÉE]RIES?|TV|LIVE|CHA[IÎ]NES?)\s*"
                         r"(?:[|\])]\s*[|:\-–»]*|[|:\-–»]+)\s*", re.I)


def pretty_group(g):
    """« VOD| ACTION » → « Action », « FR| GÉNÉRALISTES » → « Généralistes »."""
    s = strip_lead_tags(_GRP_PREFIX.sub("", g or "")).strip(" |-:")
    s = strip_lead_tags(s).strip(" |-:") or (g or "")
    if s.isupper() and len(s) > 3:
        s = s[:1] + s[1:].lower()
    return s


def clean_title(name):
    """« FR - Inception (2010) [4K] » → ('Inception', '2010')"""
    s = name or ""
    for _ in range(3):
        m = _LEAD_TAG_RE.match(s)
        if not m:
            break
        tok = (m.group(1) or m.group(2) or "").upper()
        if _resolve(tok) or tok in _LEAD_OK:
            s = s[m.end():]
        else:
            break
    year = None
    m = re.search(r"[\(\[]\s*((?:19|20)\d{2})\s*[\)\]]", s)
    if m:
        year, s = m.group(1), s[:m.start()] + s[m.end():]
    else:
        m = re.search(r"(?:\s[-–]\s*|\s)((?:19|20)\d{2})\s*$", s)
        if m:
            year, s = m.group(1), s[:m.start()]
    s = _QUALITY_RE.sub("", s)
    s = re.sub(r"[\[\(]\s*[\]\)]", "", s)
    s = re.sub(r"\s{2,}", " ", s).strip(" -|:._–")
    return (s or (name or "").strip()), year


def fmt_ms(ms):
    s = max(0, int(ms // 1000))
    h, m, s = s // 3600, (s % 3600) // 60, s % 60
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


def fmt_runtime(minutes):
    try:
        minutes = int(minutes)
    except (TypeError, ValueError):
        return ""
    if minutes <= 0:
        return ""
    return f"{minutes // 60} h {minutes % 60:02d}" if minutes >= 60 else f"{minutes} min"


def fmt_date(s):
    try:
        return datetime.strptime(s[:10], "%Y-%m-%d").strftime("%d/%m/%Y")
    except Exception:
        return s or ""


# --------------------------------------------------------------------------- #
#  Réseau
# --------------------------------------------------------------------------- #
_SSL_CTX = ssl.create_default_context()
_SSL_CTX.check_hostname = False
_SSL_CTX.verify_mode = ssl.CERT_NONE


def http_get(url, timeout=60, headers=None):
    h = {"User-Agent": USER_AGENT, "Accept": "*/*"}
    h.update(headers or {})
    req = urllib.request.Request(url, headers=h)
    with urllib.request.urlopen(req, timeout=timeout, context=_SSL_CTX) as r:
        return r.read()


def decode_text(data):
    if data.startswith(b"\xef\xbb\xbf"):
        data = data[3:]
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return data.decode("latin-1", "replace")


# --------------------------------------------------------------------------- #
#  M3U
# --------------------------------------------------------------------------- #
_ATTR_RE = re.compile(r'([A-Za-z0-9_\-]+)\s*=\s*"([^"]*)"')
_EP_RE = re.compile(r"^(.*?)[\s._\-|:]*\bS(\d{1,2})[\s._\-]*E(\d{1,4})\b(.*)$", re.I)


def guess_kind(url):
    u = url.lower()
    if "/series/" in u:
        return "series"
    if "/movie/" in u or "/vod/" in u or re.search(r"\.(mkv|mp4|avi|mov|wmv)(\?|$)", u):
        return "movie"
    return "live"


def make_item(name, url, logo="", group="", kind="live", country=None, **extra):
    group = (group or "").strip() or "Sans catégorie"
    name = (name or "").strip() or "Sans nom"
    it = {"name": name, "url": url, "logo": (logo or "").strip(), "group": group,
          "kind": kind, "country": country or detect_country(group, name)}
    it.update({k: v for k, v in extra.items() if v not in (None, "", [], {})})
    return it


def parse_m3u(text):
    items, cur, opts = [], None, []
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        up = line[:12].upper()
        if up.startswith("#EXTINF"):
            body = line.split(":", 1)[1] if ":" in line else ""
            attrs = {k.lower(): v for k, v in _ATTR_RE.findall(body)}
            rest = _ATTR_RE.sub("", body)
            name = rest.split(",", 1)[1].strip() if "," in rest else ""
            cur = {"name": name or attrs.get("tvg-name", ""),
                   "logo": attrs.get("tvg-logo") or attrs.get("logo", ""),
                   "group": attrs.get("group-title", ""),
                   "tvg_country": attrs.get("tvg-country", ""),
                   "tvg_id": attrs.get("tvg-id", "")}
        elif up.startswith("#EXTGRP:"):
            if cur is not None and not cur["group"]:
                cur["group"] = line[8:].strip()
        elif up.startswith("#EXTVLCOPT:"):
            opts.append(line[11:].strip())
        elif line.startswith("#"):
            continue
        else:
            c = cur or {"name": line.rsplit("/", 1)[-1], "logo": "", "group": "",
                        "tvg_country": "", "tvg_id": ""}
            country = detect_country(c["group"], c["name"], c["tvg_country"], c["tvg_id"])
            items.append(make_item(c["name"], line, c["logo"], c["group"], guess_kind(line),
                                   country, opts=list(opts), tvg_id=c["tvg_id"]))
            cur, opts = None, []
    return group_m3u_series(items)


def group_m3u_series(items):
    """Regroupe les épisodes « Série S01E02 » d'une liste M3U en fiches séries."""
    out, series = [], {}
    for it in items:
        if it["kind"] in ("series", "movie"):
            m = _EP_RE.match(it["name"])
            if m and m.group(1).strip(" -|:._"):
                show = m.group(1).strip(" -|:._")
                key = (title_key(clean_title(show)[0]), it["group"])
                s = series.get(key)
                if s is None:
                    sid = hashlib.md5(repr(key).encode()).hexdigest()[:16]
                    s = make_item(show, f"m3u-series:{sid}", it.get("logo"), it["group"],
                                  "series", it["country"])
                    s["episodes"] = {}
                    series[key] = s
                    out.append(s)
                num = int(m.group(3))
                s["episodes"].setdefault(str(int(m.group(2))), []).append({
                    "name": m.group(4).strip(" -|:._") or f"Épisode {num}",
                    "num": num, "url": it["url"], "opts": it.get("opts") or []})
                if not s.get("logo") and it.get("logo"):
                    s["logo"] = it["logo"]
                continue
        out.append(it)
    for s in series.values():
        for eps in s["episodes"].values():
            eps.sort(key=lambda e: e["num"])
    return out


# --------------------------------------------------------------------------- #
#  Xtream Codes
# --------------------------------------------------------------------------- #
class XtreamClient:
    def __init__(self, server, username, password, live_ext="ts"):
        s = server.strip().rstrip("/")
        if not re.match(r"^https?://", s, re.I):
            s = "http://" + s
        s = re.sub(r"/(player_api|get)\.php.*$", "", s, flags=re.I)
        self.base = s
        self.user, self.pwd = username.strip(), password.strip()
        self.live_ext = live_ext or "ts"
        self.qu = urllib.parse.quote(self.user, safe="")
        self.qp = urllib.parse.quote(self.pwd, safe="")

    def api(self, action=None, **params):
        q = {"username": self.user, "password": self.pwd}
        if action:
            q["action"] = action
        q.update(params)
        data = http_get(f"{self.base}/player_api.php?{urllib.parse.urlencode(q)}", timeout=90)
        txt = decode_text(data).strip()
        return json.loads(txt) if txt else None

    @staticmethod
    def _list(v):
        if isinstance(v, dict):
            return list(v.values())
        return v if isinstance(v, list) else []

    def load_all(self):
        info = self.api()
        ui = info.get("user_info") if isinstance(info, dict) else None
        if not ui or str(ui.get("auth")) != "1":
            raise RuntimeError("Identifiants refusés par le serveur (ou serveur injoignable).")
        meta = []
        if ui.get("status"):
            meta.append(f"Statut : {ui['status']}")
        exp = ui.get("exp_date")
        if exp and str(exp).isdigit():
            meta.append("Expire le " + datetime.fromtimestamp(int(exp)).strftime("%d/%m/%Y"))
        if ui.get("max_connections"):
            meta.append(f"Connexions max : {ui['max_connections']}")

        b, u, p = self.base, self.qu, self.qp
        items = []
        plan = (("live", "get_live_categories", "get_live_streams"),
                ("movie", "get_vod_categories", "get_vod_streams"),
                ("series", "get_series_categories", "get_series"))
        for kind, cat_action, list_action in plan:
            try:
                cats = {str(c.get("category_id")): c.get("category_name") or ""
                        for c in self._list(self.api(cat_action))}
            except Exception:
                cats = {}
            try:
                streams = self._list(self.api(list_action))
            except Exception:
                continue
            for s in streams:
                if not isinstance(s, dict):
                    continue
                group = cats.get(str(s.get("category_id")), "Sans catégorie")
                name = s.get("name") or ""
                if kind == "live":
                    sid = s.get("stream_id")
                    items.append(make_item(name, f"{b}/live/{u}/{p}/{sid}.{self.live_ext}",
                                           s.get("stream_icon"), group, kind,
                                           stream_id=str(sid), tvg_id=s.get("epg_channel_id") or ""))
                elif kind == "movie":
                    sid = s.get("stream_id")
                    ext = s.get("container_extension") or "mp4"
                    items.append(make_item(name, f"{b}/movie/{u}/{p}/{sid}.{ext}",
                                           s.get("stream_icon"), group, kind, stream_id=str(sid),
                                           rating=str(s.get("rating") or ""),
                                           added=str(s.get("added") or "")))
                else:
                    sid = s.get("series_id")
                    items.append(make_item(name, f"xtream-series:{sid}", s.get("cover"), group,
                                           kind, series_id=str(sid),
                                           rating=str(s.get("rating") or ""),
                                           added=str(s.get("last_modified") or "")))
        return items, "  ·  ".join(meta)

    def vod_info(self, stream_id):
        return self.api("get_vod_info", vod_id=stream_id) or {}

    def series_info(self, series_id):
        return self.api("get_series_info", series_id=series_id) or {}

    def episode_url(self, ep_id, ext):
        return f"{self.base}/series/{self.qu}/{self.qp}/{ep_id}.{ext or 'mp4'}"

    def short_epg(self, stream_id, limit=3):
        data = self.api("get_short_epg", stream_id=stream_id, limit=limit) or {}
        out = []
        for e in data.get("epg_listings") or []:
            def dec(v):
                try:
                    return base64.b64decode(v).decode("utf-8", "replace")
                except Exception:
                    return v or ""
            out.append({"title": dec(e.get("title")), "desc": dec(e.get("description")),
                        "start": e.get("start") or "", "end": e.get("end") or "",
                        "start_ts": e.get("start_timestamp"), "stop_ts": e.get("stop_timestamp")})
        return out


def xtream_client(src):
    return XtreamClient(src["server"], src["user"], src["password"], src.get("live_ext", "ts"))


PLAYLIST_DIR = os.path.join(DATA_DIR, "playlists")
M3U_EXTS = (".m3u", ".m3u8", ".txt")


def read_playlist_file(path):
    """Lit un fichier M3U et vérifie son contenu. Renvoie (octets, nombre d'entrées)."""
    with open(path, "rb") as f:
        data = f.read()
    n = len(re.findall(r"^#EXTINF", decode_text(data), re.I | re.M))
    if not n:
        raise RuntimeError(f"« {os.path.basename(path)} » n'est pas une liste M3U (aucune ligne #EXTINF).")
    return data, n


def import_playlist(sid, path):
    """Copie la liste dans le dossier de l'application : elle reste lisible si l'original est déplacé."""
    data, _n = read_playlist_file(path)
    os.makedirs(PLAYLIST_DIR, exist_ok=True)
    dst = os.path.join(PLAYLIST_DIR, sid + ".m3u")
    with open(dst + ".tmp", "wb") as f:
        f.write(data)
    os.replace(dst + ".tmp", dst)
    return dst


def file_source(path, name=""):
    sid = uuid.uuid4().hex[:12]
    return {"id": sid, "type": "m3u", "name": name or os.path.splitext(os.path.basename(path))[0] or "Ma liste",
            "url": import_playlist(sid, path), "file": os.path.basename(path), "file_orig": os.path.abspath(path)}


def fetch_source(src):
    if src.get("file_orig"):
        # le fichier d'origine a été modifié depuis l'import : on reprend la nouvelle version
        try:
            orig, cur = src["file_orig"], src["url"]
            if os.path.isfile(orig) and (not os.path.isfile(cur) or os.path.getmtime(orig) > os.path.getmtime(cur)):
                import_playlist(src["id"], orig)
        except Exception:
            pass
    if src["type"] == "xtream":
        items, info = xtream_client(src).load_all()
    else:
        loc = src["url"].strip()
        if re.match(r"^https?://", loc, re.I):
            data = http_get(loc, timeout=120)
        else:
            path = loc[7:] if loc.lower().startswith("file://") else loc
            with open(path, "rb") as f:
                data = f.read()
        text = decode_text(data)
        if "#EXTINF" not in text.upper():
            raise RuntimeError("Le contenu reçu n'est pas une liste M3U valide.")
        items, info = parse_m3u(text), ""
    return {"items": items, "info": info, "updated": time.strftime("%d/%m/%Y %H:%M")}


# --------------------------------------------------------------------------- #
#  TMDB
# --------------------------------------------------------------------------- #
_TMDB_SEM = threading.BoundedSemaphore(6)


class TMDB:
    def __init__(self, key, lang="fr-FR"):
        self.key, self.lang = key.strip(), lang or "fr-FR"

    def get(self, path, **params):
        params.setdefault("language", self.lang)
        headers = {"Accept": "application/json", "User-Agent": "IPTVPlayer/2.0"}
        if len(self.key) > 40:
            headers["Authorization"] = f"Bearer {self.key}"
        else:
            params["api_key"] = self.key
        url = f"{TMDB_API}{path}?{urllib.parse.urlencode(params)}"
        last = None
        for attempt in range(4):
            try:
                with _TMDB_SEM:
                    return json.loads(decode_text(http_get(url, timeout=15, headers=headers)))
            except urllib.error.HTTPError as e:
                last = e
                if e.code == 404 or e.code == 401:
                    raise
                wait = 1.5 * (attempt + 1)
                try:
                    wait = max(wait, float(e.headers.get("Retry-After") or 0))
                except (TypeError, ValueError):
                    pass
                time.sleep(min(wait, 8))
            except (urllib.error.URLError, TimeoutError, OSError, ValueError) as e:
                last = e
                time.sleep(1.0 * (attempt + 1))
        raise last

    @staticmethod
    def img(path, size="w500"):
        return f"{TMDB_IMG}{size}{path}" if path else ""

    def search(self, kind, title, year=None):
        params = {"query": title, "include_adult": "false"}
        if year:
            params["year" if kind == "movie" else "first_air_date_year"] = year
        res = (self.get(f"/search/{kind}", **params) or {}).get("results") or []
        if not res and year:
            res = (self.get(f"/search/{kind}", query=title) or {}).get("results") or []
        return res[0]["id"] if res else None

    def movie(self, mid):
        return self.get(f"/movie/{mid}", append_to_response="credits,videos,release_dates,images",
                        include_video_language=f"{self.lang[:2]},en,null",
                        include_image_language=f"{self.lang[:2]},en,null")

    def tv(self, tid):
        return self.get(f"/tv/{tid}", append_to_response="credits,videos,content_ratings,images",
                        include_video_language=f"{self.lang[:2]},en,null",
                        include_image_language=f"{self.lang[:2]},en,null")

    def season(self, tid, n):
        return self.get(f"/tv/{tid}/season/{n}")

    def person(self, pid):
        d = self.get(f"/person/{pid}", append_to_response="combined_credits")
        if not (d.get("biography") or "").strip() and not self.lang.startswith("en"):
            try:
                d["biography"] = self.get(f"/person/{pid}", language="en-US").get("biography") or ""
            except Exception:
                pass
        return d

    def search_person(self, name):
        return (self.get("/search/person", query=name) or {}).get("results") or []


def _yt(key):
    if not key:
        return ""
    return key if key.startswith("http") else f"https://www.youtube.com/watch?v={key}"


def _split_list(s):
    if isinstance(s, list):
        return [str(x).strip() for x in s if str(x).strip()]
    return [x.strip() for x in re.split(r"\s*[,/]\s*", s or "") if x.strip()]


def _first(v):
    if isinstance(v, list):
        return v[0] if v else ""
    return v or ""


def _to_minutes(info):
    try:
        secs = int(info.get("duration_secs") or 0)
        if secs:
            return secs // 60
    except (TypeError, ValueError):
        pass
    d = str(info.get("duration") or info.get("episode_run_time") or "")
    m = re.match(r"^(\d+):(\d+)(?::(\d+))?$", d)
    if m:
        return int(m.group(1)) * 60 + int(m.group(2)) if m.group(3) is not None else int(m.group(1))
    m = re.match(r"^(\d+)", d)
    return int(m.group(1)) if m else 0


def _pick_logo(d, lang2):
    """Logo-titre du film/de la série (image PNG transparente), en français sinon en anglais."""
    logos = (d.get("images") or {}).get("logos") or []
    for pref in (lang2, "en", None):
        c = [x for x in logos if x.get("iso_639_1") == pref and str(x.get("file_path") or "").endswith(".png")]
        if c:
            best = max(c, key=lambda x: (x.get("vote_average") or 0, x.get("width") or 0))
            return TMDB.img(best["file_path"], "w500")
    return ""


def _merge_tmdb_common(meta, d, kind):
    if not d:
        return
    meta["tmdb_id"] = d.get("id")
    logo = _pick_logo(d, meta.get("_lang2") or "fr")
    if logo:
        meta["title_logo"] = logo
    meta["title"] = d.get("title") or d.get("name") or meta["title"]
    meta["original_title"] = d.get("original_title") or d.get("original_name") or ""
    if (d.get("overview") or "").strip():
        meta["overview"] = d["overview"].strip()
    if d.get("genres"):
        meta["genres"] = [g["name"] for g in d["genres"] if g.get("name")]
    if d.get("vote_average"):
        meta["rating"] = round(float(d["vote_average"]), 1)
    date = d.get("release_date") or d.get("first_air_date") or ""
    if date[:4].isdigit():
        meta["year"] = date[:4]
    if d.get("backdrop_path"):
        meta["backdrop"] = TMDB.img(d["backdrop_path"], "w1280")
    if d.get("poster_path"):
        meta["poster"] = TMDB.img(d["poster_path"], "w500")
    if d.get("tagline"):
        meta["tagline"] = d["tagline"]
    credits = d.get("credits") or {}
    cast = []
    for c in (credits.get("cast") or [])[:24]:
        cast.append({"name": c.get("name") or "", "role": c.get("character") or "",
                     "photo": TMDB.img(c.get("profile_path"), "w185"), "tmdb_id": c.get("id")})
    if cast:
        meta["cast"] = cast
    directors = [c["name"] for c in credits.get("crew") or [] if c.get("job") == "Director"]
    if kind == "tv" and d.get("created_by"):
        directors = [c["name"] for c in d["created_by"] if c.get("name")]
    if directors:
        meta["director"] = ", ".join(directors[:3])
    vids = [v for v in (d.get("videos") or {}).get("results") or []
            if v.get("site") == "YouTube" and v.get("type") in ("Trailer", "Teaser")]
    vids.sort(key=lambda v: (v.get("type") != "Trailer", v.get("iso_639_1") != meta.get("_lang2")))
    if vids:
        meta["trailer"] = _yt(vids[0]["key"])


def _pick_cert(entries, lang_country, getter):
    for cc in (lang_country, "FR", "US"):
        for e in entries:
            if e.get("iso_3166_1") == cc:
                v = getter(e)
                if v:
                    return v
    return ""


def movie_meta(src, item, tmdb_key, lang):
    title, year = clean_title(item["name"])
    meta = {"kind": "movie", "title": title, "year": year or "", "overview": "", "genres": [],
            "rating": item.get("rating") or "", "runtime": 0, "age": "", "backdrop": "",
            "poster": item.get("logo") or "", "trailer": "", "director": "", "cast": [],
            "_lang2": (lang or "fr")[:2]}
    tmdb_id = None
    if src and src.get("type") == "xtream" and item.get("stream_id"):
        try:
            info = xtream_client(src).vod_info(item["stream_id"]).get("info") or {}
            if isinstance(info, dict):
                meta["overview"] = (info.get("plot") or info.get("description") or "").strip()
                meta["genres"] = _split_list(info.get("genre"))
                meta["rating"] = info.get("rating") or meta["rating"]
                meta["runtime"] = _to_minutes(info)
                meta["director"] = info.get("director") or ""
                meta["cast"] = [{"name": n, "role": "", "photo": ""}
                                for n in _split_list(info.get("cast") or info.get("actors"))][:24]
                meta["backdrop"] = hires(_first(info.get("backdrop_path")))
                meta["poster"] = info.get("movie_image") or info.get("cover_big") or meta["poster"]
                meta["trailer"] = _yt(info.get("youtube_trailer"))
                meta["age"] = str(info.get("age") or info.get("mpaa_rating") or "")
                rd = str(info.get("releasedate") or info.get("release_date") or "")
                if rd[:4].isdigit():
                    meta["year"] = rd[:4]
                tmdb_id = info.get("tmdb_id") or info.get("tmdb") or None
        except Exception:
            pass
    if tmdb_key:
        tm = TMDB(tmdb_key, lang)
        try:
            if not tmdb_id or not str(tmdb_id).isdigit():
                tmdb_id = tm.search("movie", title, year)
            if tmdb_id:
                d = tm.movie(tmdb_id)
                _merge_tmdb_common(meta, d, "movie")
                if d.get("runtime"):
                    meta["runtime"] = d["runtime"]
                cc = lang[-2:].upper() if lang and "-" in lang else "FR"
                cert = _pick_cert((d.get("release_dates") or {}).get("results") or [], cc,
                                  lambda e: next((r.get("certification") for r in e.get("release_dates") or []
                                                  if r.get("certification")), ""))
                if cert:
                    meta["age"] = cert
                meta["_tmdb"] = "ok"
            else:
                meta["_tmdb"] = "none"
        except Exception:
            meta["_tmdb"] = "fail"
    return meta


def _ep_clean_name(name, show):
    s = name or ""
    if show and norm(s).startswith(norm(show)):
        s = s[len(show):]
    s = re.sub(r"^[\s\-|:._]*S\d{1,2}[\s._\-]*E\d{1,4}[\s\-|:._]*", "", s, flags=re.I)
    return s.strip(" -|:._")


def series_meta(src, item, tmdb_key, lang):
    title, year = clean_title(item["name"])
    meta = {"kind": "series", "title": title, "year": year or "", "overview": "", "genres": [],
            "rating": item.get("rating") or "", "runtime": 0, "age": "", "backdrop": "",
            "poster": item.get("logo") or "", "trailer": "", "director": "", "cast": [],
            "seasons": [], "_lang2": (lang or "fr")[:2]}
    tmdb_id = None
    seasons = []
    if item.get("series_id") and src and src.get("type") == "xtream":
        cl = xtream_client(src)
        data = cl.series_info(item["series_id"])
        info = data.get("info") if isinstance(data.get("info"), dict) else {}
        meta["overview"] = (info.get("plot") or "").strip()
        meta["genres"] = _split_list(info.get("genre"))
        meta["rating"] = info.get("rating") or meta["rating"]
        meta["director"] = info.get("director") or ""
        meta["cast"] = [{"name": n, "role": "", "photo": ""} for n in _split_list(info.get("cast"))][:24]
        meta["backdrop"] = hires(_first(info.get("backdrop_path")))
        meta["poster"] = info.get("cover") or meta["poster"]
        meta["trailer"] = _yt(info.get("youtube_trailer"))
        meta["runtime"] = _to_minutes(info)
        rd = str(info.get("releaseDate") or info.get("release_date") or "")
        if rd[:4].isdigit():
            meta["year"] = rd[:4]
        tmdb_id = info.get("tmdb") or info.get("tmdb_id")
        eps = data.get("episodes") or {}
        pairs = list(eps.items()) if isinstance(eps, dict) else [(str(i + 1), l) for i, l in enumerate(eps)]
        season_names = {str(s.get("season_number")): s for s in XtreamClient._list(data.get("seasons"))
                        if isinstance(s, dict)}
        for sn, lst in pairs:
            out = []
            for e in XtreamClient._list(lst):
                if not isinstance(e, dict):
                    continue
                ei = e.get("info") if isinstance(e.get("info"), dict) else {}
                try:
                    num = int(e.get("episode_num") or 0)
                except (TypeError, ValueError):
                    num = 0
                out.append({"name": _ep_clean_name(e.get("title"), item["name"]) or f"Épisode {num}",
                            "num": num, "url": cl.episode_url(e.get("id"), e.get("container_extension")),
                            "plot": (ei.get("plot") or "").strip(), "runtime": _to_minutes(ei),
                            "still": ei.get("movie_image") or "", "rating": ei.get("rating") or ""})
            out.sort(key=lambda x: x["num"])
            sinfo = season_names.get(str(sn), {})
            seasons.append({"number": int(sn) if str(sn).isdigit() else 0,
                            "name": sinfo.get("name") or "", "episodes": out,
                            "poster": sinfo.get("cover") or ""})
    elif item.get("episodes"):
        for sn, lst in item["episodes"].items():
            seasons.append({"number": int(sn), "name": "", "poster": "",
                            "episodes": [dict(e, plot="", runtime=0, still="", rating="") for e in lst]})
    seasons.sort(key=lambda s: s["number"])
    if tmdb_key:
        tm = TMDB(tmdb_key, lang)
        try:
            if not tmdb_id or not str(tmdb_id).isdigit():
                tmdb_id = tm.search("tv", title, year)
            if tmdb_id:
                d = tm.tv(tmdb_id)
                _merge_tmdb_common(meta, d, "tv")
                if d.get("episode_run_time"):
                    meta["runtime"] = d["episode_run_time"][0]
                cc = lang[-2:].upper() if lang and "-" in lang else "FR"
                cert = _pick_cert((d.get("content_ratings") or {}).get("results") or [], cc,
                                  lambda e: e.get("rating") or "")
                if cert:
                    meta["age"] = cert
                meta["_tmdb"] = "ok"
                for s in seasons[:25]:
                    try:
                        sd = tm.season(tmdb_id, s["number"])
                    except Exception:
                        meta["_tmdb"] = "fail"
                        continue
                    if not s["name"]:
                        s["name"] = sd.get("name") or ""
                    if sd.get("poster_path"):
                        s["poster"] = TMDB.img(sd["poster_path"], "w342")
                    by_num = {e.get("episode_number"): e for e in sd.get("episodes") or []}
                    for e in s["episodes"]:
                        t = by_num.get(e["num"])
                        if not t:
                            continue
                        if t.get("still_path"):
                            e["still"] = TMDB.img(t["still_path"], "w300")
                        if (t.get("overview") or "").strip():
                            e["plot"] = t["overview"].strip()
                        if t.get("name") and (not e["name"] or re.match(r"^(Épisode|Episode)\s*\d+$", e["name"])):
                            e["name"] = t["name"]
                        if t.get("runtime") and not e["runtime"]:
                            e["runtime"] = t["runtime"]
                        if t.get("air_date"):
                            e["air_date"] = t["air_date"]
            else:
                meta["_tmdb"] = "none"
        except Exception:
            meta["_tmdb"] = "fail"
    meta["seasons"] = seasons
    return meta


def person_meta(tmdb_key, lang, pid=None, name=""):
    tm = TMDB(tmdb_key, lang)
    if not pid:
        res = tm.search_person(name)
        if not res:
            return None
        pid = res[0]["id"]
    d = tm.person(pid)
    credits, seen = [], set()
    for c in (d.get("combined_credits") or {}).get("cast") or []:
        key = (c.get("media_type"), c.get("id"))
        if key in seen:
            continue
        seen.add(key)
        date = c.get("release_date") or c.get("first_air_date") or ""
        credits.append({"title": c.get("title") or c.get("name") or "",
                        "original_title": c.get("original_title") or c.get("original_name") or "",
                        "year": date[:4], "poster": TMDB.img(c.get("poster_path"), "w342"),
                        "kind": "movie" if c.get("media_type") == "movie" else "series",
                        "role": c.get("character") or "", "popularity": c.get("popularity") or 0,
                        "votes": c.get("vote_count") or 0})
    credits.sort(key=lambda c: (-(c["votes"] or 0)))
    genders = {1: "Née", 2: "Né"}
    return {"tmdb_id": pid, "name": d.get("name") or name, "bio": (d.get("biography") or "").strip(),
            "photo": TMDB.img(d.get("profile_path"), "h632"), "birthday": d.get("birthday") or "",
            "deathday": d.get("deathday") or "", "place": d.get("place_of_birth") or "",
            "department": d.get("known_for_department") or "", "born_word": genders.get(d.get("gender"), "Né(e)"),
            "credits": credits}


# --------------------------------------------------------------------------- #
#  Configuration
# --------------------------------------------------------------------------- #
def tmdb_trending(tmdb_key, lang, kind):
    """Titres les plus recherchés de la semaine (kind : movie | tv)."""
    d = TMDB(tmdb_key, lang).get(f"/trending/{kind}/week")
    out = []
    for r in d.get("results") or []:
        date = r.get("release_date") or r.get("first_air_date") or ""
        out.append({"title": r.get("title") or r.get("name") or "",
                    "original_title": r.get("original_title") or r.get("original_name") or "",
                    "year": date[:4], "poster": TMDB.img(r.get("poster_path"), "w342"),
                    "backdrop": TMDB.img(r.get("backdrop_path"), "w780"),
                    "kind": "movie" if kind == "movie" else "series", "tmdb_id": r.get("id"),
                    "genre_ids": r.get("genre_ids") or []})
    return out


def _tmdb_rows(results, kind):
    out = []
    for r in results or []:
        date = r.get("release_date") or r.get("first_air_date") or ""
        out.append({"title": r.get("title") or r.get("name") or "",
                    "original_title": r.get("original_title") or r.get("original_name") or "",
                    "year": date[:4], "poster": TMDB.img(r.get("poster_path"), "w342"),
                    "backdrop": TMDB.img(r.get("backdrop_path"), "w780"),
                    "kind": "movie" if kind == "movie" else "series", "tmdb_id": r.get("id"),
                    "genre_ids": r.get("genre_ids") or []})
    return out


def tmdb_discover(tmdb_key, lang, kind, pages=3, **params):
    """/discover (kind : movie | tv) sur plusieurs pages."""
    tm = TMDB(tmdb_key, lang)
    out, seen = [], set()
    for page in range(1, pages + 1):
        try:
            d = tm.get(f"/discover/{kind}", page=page, **params)
        except Exception:
            if page == 1:
                raise
            break
        for r in _tmdb_rows(d.get("results"), kind):
            if r["tmdb_id"] not in seen:
                seen.add(r["tmdb_id"])
                out.append(r)
        if page >= (d.get("total_pages") or 1):
            break
    return out


def tmdb_trending_all(tmdb_key, lang, kind, pages=3, window="week"):
    tm = TMDB(tmdb_key, lang)
    out = []
    for page in range(1, pages + 1):
        try:
            out += _tmdb_rows(tm.get(f"/trending/{kind}/{window}", page=page).get("results"), kind)
        except Exception:
            if page == 1:
                raise
            break
    return out


# Plateformes (identifiants TMDB / JustWatch, région France)
PROVIDERS = [(8, "Netflix"), (119, "Prime Video"), (337, "Disney+"), (350, "Apple TV+"), (1899, "Max"),
             (283, "Crunchyroll"), (381, "Canal+"), (531, "Paramount+")]
# Studios (sociétés de production TMDB) : nom affiché, identifiants, couleurs de la tuile
STUDIOS = [("Disney", "2", "#0d2a6b", "#3d7fe0"), ("DreamWorks", "521", "#0b3a7a", "#6ab0ff"),
           ("DC", "9993|128064|429", "#0a1a3a", "#1f6fe5"), ("Pixar", "3", "#e9edf3", "#aeb8c8"),
           ("MARVEL", "420|7505", "#8d0b10", "#ec1d24"), ("STAR WARS", "1", "#050505", "#3a3a3a")]


def tmdb_provider_logos(tmdb_key, lang, kind):
    d = TMDB(tmdb_key, lang).get(f"/watch/providers/{kind}", watch_region="FR")
    return {r.get("provider_id"): TMDB.img(r.get("logo_path"), "w300") for r in d.get("results") or []}


def tmdb_popular_people(tmdb_key, lang):
    d = TMDB(tmdb_key, lang).get("/person/popular")
    return [{"name": r.get("name") or "", "photo": TMDB.img(r.get("profile_path"), "w185"), "tmdb_id": r.get("id")}
            for r in d.get("results") or []
            if r.get("profile_path") and (r.get("known_for_department") or "Acting") == "Acting"]


def load_config():
    try:
        with open(CONFIG_PATH, encoding="utf-8") as f:
            cfg = json.load(f)
    except Exception:
        cfg = {}
    cfg.setdefault("sources", [])
    cfg.setdefault("favorites", [])
    cfg.setdefault("progress", {})
    cfg.setdefault("volume", 80)
    cfg.setdefault("tmdb_key", "")
    cfg.setdefault("lang", "fr-FR")
    cfg.setdefault("pdata", {})
    if not cfg.get("profiles"):
        cfg["profiles"] = [{"id": "p1", "name": "Principal", "color": AVATAR_COLORS[0], "emoji": "🦤",
                            "kids": False, "pin": ""}]
        cfg["pdata"]["p1"] = {"favorites": cfg.get("favorites", []), "progress": cfg.get("progress", {})}
    cfg.pop("favorites", None)
    cfg.pop("progress", None)
    for pr in cfg["profiles"]:
        d = cfg["pdata"].setdefault(pr["id"], {})
        d.setdefault("favorites", [])
        d.setdefault("progress", {})
        d.setdefault("live_hist", {})
    return cfg


def save_config(cfg):
    tmp = CONFIG_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=1)
    os.replace(tmp, CONFIG_PATH)


def cache_path(source_id):
    return os.path.join(CACHE_DIR, f"{source_id}.json")


# --------------------------------------------------------------------------- #
#  Tâches en arrière-plan
# --------------------------------------------------------------------------- #
class _TaskSignals(QtCore.QObject):
    done = QtCore.Signal(object)
    failed = QtCore.Signal(object)


class Task(QtCore.QRunnable):
    def __init__(self, tid, fn):
        super().__init__()
        self.tid, self.fn = tid, fn
        self.signals = _TaskSignals()

    def run(self):
        try:
            res = self.fn()
        except Exception as e:
            self.signals.failed.emit((self.tid, f"{e}"))
        else:
            self.signals.done.emit((self.tid, res))


def safe_call(cb, *args):
    try:
        cb(*args)
    except RuntimeError:  # widget détruit entre-temps
        pass


# --------------------------------------------------------------------------- #
#  Images (logos, affiches, fonds, photos)
# --------------------------------------------------------------------------- #
class ImageCache(QtCore.QObject):
    loaded = QtCore.Signal(str)
    MAX_MEM = 500

    def __init__(self, parent=None):
        super().__init__(parent)
        self.nam = QtNetwork.QNetworkAccessManager(self)
        self.nam.setTransferTimeout(20000)
        self.mem = OrderedDict()
        self.failed, self.pending = set(), set()

    @staticmethod
    def _path(url):
        return os.path.join(IMG_DIR, hashlib.md5(url.encode("utf-8", "replace")).hexdigest())

    def _store(self, url, pm):
        if pm.width() > 2600 or pm.height() > 2600:
            pm = pm.scaled(QtCore.QSize(2600, 2600), Qt.AspectRatioMode.KeepAspectRatio,
                           Qt.TransformationMode.SmoothTransformation)
        self.mem[url] = pm
        self.mem.move_to_end(url)
        while len(self.mem) > self.MAX_MEM:
            self.mem.popitem(last=False)
        return pm

    def get(self, url):
        if not url or url in self.failed:
            return None
        pm = self.mem.get(url)
        if pm is not None:
            self.mem.move_to_end(url)
            return pm
        if url in self.pending:
            return None
        path = self._path(url)
        if os.path.exists(path):
            pm = QtGui.QPixmap(path)
            if not pm.isNull():
                return self._store(url, pm)
        if not url.lower().startswith(("http://", "https://")):
            if os.path.exists(url):
                pm = QtGui.QPixmap(url)
                if not pm.isNull():
                    return self._store(url, pm)
            self.failed.add(url)
            return None
        self.pending.add(url)
        req = QtNetwork.QNetworkRequest(QtCore.QUrl(url))
        req.setHeader(QtNetwork.QNetworkRequest.KnownHeaders.UserAgentHeader, "Mozilla/5.0")
        req.setAttribute(QtNetwork.QNetworkRequest.Attribute.RedirectPolicyAttribute,
                         QtNetwork.QNetworkRequest.RedirectPolicy.NoLessSafeRedirectPolicy)
        reply = self.nam.get(req)
        reply.sslErrors.connect(lambda _errs, r=reply: r.ignoreSslErrors())
        reply.finished.connect(lambda r=reply, u=url: self._finished(r, u))
        return None

    def _finished(self, reply, url):
        self.pending.discard(url)
        ok = reply.error() == QtNetwork.QNetworkReply.NetworkError.NoError
        data = reply.readAll().data() if ok else b""
        reply.deleteLater()
        pm = QtGui.QPixmap()
        if data and pm.loadFromData(data):
            try:
                with open(self._path(url), "wb") as f:
                    f.write(data)
            except OSError:
                pass
            self._store(url, pm)
        else:
            self.failed.add(url)
        self.loaded.emit(url)

    def clear_disk(self):
        n = 0
        for f in os.listdir(IMG_DIR):
            try:
                os.remove(os.path.join(IMG_DIR, f))
                n += 1
            except OSError:
                pass
        self.mem.clear()
        self.failed.clear()
        return n


def _flags(*fl):
    v = 0
    for f in fl:
        v |= f.value
    return v


def _dpr():
    s = QtGui.QGuiApplication.primaryScreen()
    return s.devicePixelRatio() if s else 1.0


def draw_image(p, rect, pm, mode="cover"):
    """Dessine pm dans rect (QRectF) en mode cover ou contain."""
    if mode == "cover":
        s = pm.size().scaled(rect.size().toSize(), Qt.AspectRatioMode.KeepAspectRatioByExpanding)
        sw = pm.width() * rect.width() / max(1, s.width())
        sh = pm.height() * rect.height() / max(1, s.height())
        src = QtCore.QRectF((pm.width() - sw) / 2, (pm.height() - sh) / 4, sw, sh)
        p.drawPixmap(rect, pm, src)
    else:
        s = pm.size().scaled(rect.size().toSize(), Qt.AspectRatioMode.KeepAspectRatio)
        t = QtCore.QRectF(rect.center().x() - s.width() / 2, rect.center().y() - s.height() / 2,
                          s.width(), s.height())
        p.drawPixmap(t, pm, QtCore.QRectF(pm.rect()))


def draw_placeholder(p, rect, text, font, radius=10, big=False):
    g = QtGui.QLinearGradient(rect.topLeft(), rect.bottomRight())
    g.setColorAt(0, QtGui.QColor("#262a38"))
    g.setColorAt(1, QtGui.QColor("#1a1d27"))
    path = QtGui.QPainterPath()
    path.addRoundedRect(rect, radius, radius)
    p.fillPath(path, g)
    f = QtGui.QFont(font)
    f.setPointSize(22 if big else 15)
    f.setBold(True)
    p.setFont(f)
    p.setPen(QtGui.QColor("#5d6478"))
    p.drawText(rect, _flags(Qt.AlignmentFlag.AlignCenter), text)


def nav_icon(name, color=ACCENT, size=28):
    """Icônes du menu dessinées à la main (nettes à toutes les tailles)."""
    dpr = _dpr()
    pm = QtGui.QPixmap(int(size * dpr), int(size * dpr))
    pm.setDevicePixelRatio(dpr)
    pm.fill(Qt.GlobalColor.transparent)
    p = QtGui.QPainter(pm)
    p.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
    pen = QtGui.QPen(QtGui.QColor(color), max(1.6, size * 0.075))
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    p.setPen(pen)
    p.setBrush(Qt.BrushStyle.NoBrush)
    S = float(size)

    def P(x, y):
        return QtCore.QPointF(x * S, y * S)

    def R(x, y, w, h):
        return QtCore.QRectF(x * S, y * S, w * S, h * S)

    if name == "home":
        p.drawPolyline(QtGui.QPolygonF([P(.1, .5), P(.5, .13), P(.9, .5)]))
        p.drawRoundedRect(R(.22, .42, .56, .46), S * .06, S * .06)
        p.drawRoundedRect(R(.42, .62, .16, .26), S * .03, S * .03)
    elif name == "film":
        p.drawRoundedRect(R(.12, .38, .76, .5), S * .06, S * .06)
        path = QtGui.QPainterPath(P(.12, .38))
        path.lineTo(P(.12, .24))
        path.lineTo(P(.84, .1))
        path.lineTo(P(.87, .24))
        path.closeSubpath()
        p.drawPath(path)
        for x in (.32, .52, .72):
            p.drawLine(P(x - .06, .21), P(x + .02, .33))
        p.drawLine(P(.12, .55), P(.88, .55))
    elif name == "series":
        path = QtGui.QPainterPath(P(.2, .36))
        path.lineTo(P(.8, .36))
        path.lineTo(P(.7, .9))
        path.lineTo(P(.3, .9))
        path.closeSubpath()
        p.drawPath(path)
        for x in (.4, .6):
            p.drawLine(P(x, .38), P(x - .02 if x < .5 else x + .02, .88))
        for cx, cy in ((.32, .26), (.5, .18), (.68, .26)):
            p.drawArc(R(cx - .11, cy - .1, .22, .2), 0, 180 * 16)
    elif name == "tv":
        p.drawRoundedRect(R(.08, .18, .84, .56), S * .07, S * .07)
        p.drawLine(P(.34, .88), P(.66, .88))
        p.drawLine(P(.5, .74), P(.5, .88))
    elif name == "download":
        p.drawLine(P(.5, .14), P(.5, .64))
        p.drawPolyline(QtGui.QPolygonF([P(.3, .45), P(.5, .65), P(.7, .45)]))
        p.drawPolyline(QtGui.QPolygonF([P(.16, .66), P(.16, .84), P(.84, .84), P(.84, .66)]))
    elif name == "search":
        p.drawEllipse(R(.16, .16, .52, .52))
        p.drawLine(P(.6, .6), P(.86, .86))
    elif name == "heart":
        path = QtGui.QPainterPath(P(.5, .86))
        path.cubicTo(P(.1, .58), P(.06, .3), P(.28, .2))
        path.cubicTo(P(.4, .15), P(.48, .22), P(.5, .32))
        path.cubicTo(P(.52, .22), P(.6, .15), P(.72, .2))
        path.cubicTo(P(.94, .3), P(.9, .58), P(.5, .86))
        p.drawPath(path)
    elif name == "gear":
        p.drawEllipse(R(.34, .34, .32, .32))
        for i in range(8):
            a = i * math.pi / 4
            p.drawLine(P(.5 + .28 * math.cos(a), .5 + .28 * math.sin(a)), P(.5 + .4 * math.cos(a), .5 + .4 * math.sin(a)))
        p.drawEllipse(R(.22, .22, .56, .56))
    elif name == "sidebar":
        p.drawRoundedRect(R(.1, .18, .8, .64), S * .1, S * .1)
        p.drawLine(P(.38, .2), P(.38, .8))
    elif name == "grid":
        for x, y in ((.14, .14), (.54, .14), (.14, .54), (.54, .54)):
            p.drawRoundedRect(R(x, y, .32, .32), S * .06, S * .06)
    elif name == "play":
        p.setBrush(QtGui.QColor(color))
        p.drawPolygon(QtGui.QPolygonF([P(.26, .14), P(.26, .86), P(.86, .5)]))
    elif name == "clock":
        p.drawEllipse(R(.12, .12, .76, .76))
        p.drawPolyline(QtGui.QPolygonF([P(.5, .28), P(.5, .5), P(.66, .6)]))
    p.end()
    return pm


def blurred_pixmap(pm, strength=18):
    """Flou rapide (réduction puis agrandissement lissé)."""
    if pm is None or pm.isNull():
        return pm
    w = max(8, pm.width() // strength)
    small = pm.scaledToWidth(w, Qt.TransformationMode.SmoothTransformation)
    return small.scaled(pm.size(), Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.SmoothTransformation)


_TILE_COLORS = ["#3b5bdb", "#0b7285", "#5f3dc4", "#c2255c", "#e67700", "#2b8a3e", "#862e9c", "#1864ab",
                "#a61e4d", "#5c940d", "#364fc7", "#d9480f"]
_CAT_EMOJI = [("sport", "⚽"), ("foot", "⚽"), ("info", "📰"), ("news", "📰"), ("cin", "🎬"), ("film", "🎬"),
              ("movie", "🎬"), ("music", "🎵"), ("musique", "🎵"), ("enfant", "🧸"), ("jeunesse", "🧸"), ("kid", "🧸"),
              ("dessin", "🧸"), ("docu", "🌍"), ("découverte", "🌍"), ("religi", "🕊"), ("séri", "📺"), ("serie", "📺"),
              ("divert", "🎭"), ("général", "📺"), ("generaliste", "📺"), ("régional", "🏘"), ("local", "🏘"),
              ("premium", "💎"), ("canal", "💎"), ("adult", "🔞"), ("cuisine", "🍳"), ("vie", "🌿"), ("4k", "✨"),
              ("uhd", "✨"), ("radio", "📻"), ("anim", "🧸"), ("action", "💥"), ("comédie", "😄"), ("comedie", "😄"),
              ("horreur", "👻"), ("drame", "🎭"), ("crime", "🕵"), ("aventure", "🧭"), ("science", "🚀"), ("romance", "💕")]


def tile_color(name):
    return QtGui.QColor(_TILE_COLORS[sum(map(ord, name or "?")) % len(_TILE_COLORS)])


def cat_emoji(name):
    n = norm(name)
    for k, e in _CAT_EMOJI:
        if norm(k) in n:
            return e
    return "📺"


class ImageLabel(QtWidgets.QLabel):
    """Image arrondie / circulaire chargée de façon asynchrone."""

    def __init__(self, cache, w, h, radius=10, circle=False, mode="cover", parent=None):
        super().__init__(parent)
        self.cache, self.w, self.h = cache, w, h
        self.radius, self.circle, self.mode = radius, circle, mode
        self.url, self.fallback, self.text = "", "", ""
        self.setFixedSize(w, h)
        cache.loaded.connect(self._loaded)

    def set_image(self, url, text="", fallback=""):
        self.url, self.text, self.fallback = url or "", text, fallback or ""
        self._render()

    def _loaded(self, u):
        if u and u in (self.url, self.fallback):
            self._render()

    def _render(self):
        pm = self.cache.get(self.url) if self.url else None
        if pm is None and self.fallback:
            pm = self.cache.get(self.fallback)
        dpr = _dpr()
        out = QtGui.QPixmap(int(self.w * dpr), int(self.h * dpr))
        out.setDevicePixelRatio(dpr)
        out.fill(Qt.GlobalColor.transparent)
        p = QtGui.QPainter(out)
        p.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QtGui.QPainter.RenderHint.SmoothPixmapTransform)
        rect = QtCore.QRectF(0, 0, self.w, self.h)
        path = QtGui.QPainterPath()
        if self.circle:
            path.addEllipse(rect)
        else:
            path.addRoundedRect(rect, self.radius, self.radius)
        if pm is not None and not pm.isNull():
            p.setClipPath(path)
            if self.mode == "contain":
                p.fillPath(path, QtGui.QColor("#1b1e27"))
            draw_image(p, rect, pm, self.mode)
        else:
            p.setClipPath(path)
            draw_placeholder(p, rect, self.text or "", self.font(), 0 if self.circle else self.radius,
                             big=self.w > 150)
        p.end()
        self.setPixmap(out)


# --------------------------------------------------------------------------- #
#  Cartes (affiches / chaînes / acteurs)
# --------------------------------------------------------------------------- #
CARD_SIZES = {
    "poster": QtCore.QSize(160, 292),
    "channel": QtCore.QSize(178, 146),
    "actor": QtCore.QSize(138, 204),
    "wide": QtCore.QSize(236, 196),      # chaînes du moment : image + programme dessous
    "resume": QtCore.QSize(284, 166),    # Reprendre : image seule, avancement dedans
    "cat": QtCore.QSize(214, 98),
    "cover": QtCore.QSize(206, 312),
    "coverc": QtCore.QSize(206, 346),
    "land": QtCore.QSize(284, 166),      # Top de la semaine : image + logo-titre
    "big": QtCore.QSize(480, 330),       # Nouveautés
    "tile": QtCore.QSize(157, 94),       # catégories
    "tilebig": QtCore.QSize(276, 162),
    "actor2": QtCore.QSize(150, 198),    # acteurs populaires
    "provider": QtCore.QSize(149, 149),  # En streaming sur
    "posterbig": QtCore.QSize(230, 338), # Les plus gros succès de l'année
    "postersm": QtCore.QSize(148, 216),  # Top du mois
    "coeur": QtCore.QSize(414, 489),     # Coups de cœur
    "studio": QtCore.QSize(199, 117),    # Disney, Marvel…
}


class _UiScale(QtCore.QObject):
    """Échelle de l'interface selon la taille de la fenêtre (vignettes et textes des cartes)."""
    changed = QtCore.Signal()

    def __init__(self):
        super().__init__()
        self.k = 1.0

    def set(self, k):
        k = round(max(0.8, min(1.9, k)), 2)
        if abs(k - self.k) >= 0.04:
            self.k = k
            self.changed.emit()


UI = _UiScale()


def card_size(style):
    s = CARD_SIZES[style]
    return QtCore.QSize(int(s.width() * UI.k), int(s.height() * UI.k))


class CardModel(QtCore.QAbstractListModel):
    def __init__(self, images, parent=None):
        super().__init__(parent)
        self.images = images
        self.items = []
        self.rows_by_img = {}
        images.loaded.connect(self._img_loaded)

    def set_items(self, items):
        self.beginResetModel()
        self.items = list(items)
        self.rows_by_img = {}
        for i, it in enumerate(self.items):
            for u in (it.get("_img") or it.get("logo"), it.get("_tlogo")):
                if u:
                    self.rows_by_img.setdefault(u, []).append(i)
        self.endResetModel()

    def refresh(self, it):
        for i, x in enumerate(self.items):
            if x is it:
                for u in (it.get("_img") or it.get("logo"), it.get("_tlogo")):
                    if u and i not in self.rows_by_img.get(u, []):
                        self.rows_by_img.setdefault(u, []).append(i)
                idx = self.index(i)
                self.dataChanged.emit(idx, idx)
                return

    def rowCount(self, parent=QtCore.QModelIndex()):
        return 0 if parent.isValid() else len(self.items)

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or index.row() >= len(self.items):
            return None
        it = self.items[index.row()]
        if role == Qt.ItemDataRole.DisplayRole:
            return it.get("_title") or it["name"]
        if role == Qt.ItemDataRole.DecorationRole:
            return self.images.get(it.get("_img") or it.get("logo"))
        if role == Qt.ItemDataRole.ToolTipRole:
            if it.get("kind") in ("person", "category"):
                return it["name"] + (f"\n{it['sub']}" if it.get("sub") else "")
            return it["name"] + (f"\n{it['group']}" if it.get("group") else "")
        if role == ITEM_ROLE:
            return it
        return None

    def _img_loaded(self, url):
        for r in self.rows_by_img.get(url, ()):
            idx = self.index(r)
            self.dataChanged.emit(idx, idx, [Qt.ItemDataRole.DecorationRole])


class CardDelegate(QtWidgets.QStyledItemDelegate):
    def __init__(self, win, style):
        super().__init__(win)
        self.win, self.style = win, style
        self._blur_cache = {}

    def sizeHint(self, option, index):
        return card_size(self.style)

    def paint(self, p, option, index):
        it = index.data(ITEM_ROLE)
        if not it:
            return
        hov = bool(option.state & QtWidgets.QStyle.StateFlag.State_MouseOver)
        sel = bool(option.state & QtWidgets.QStyle.StateFlag.State_HasFocus) and \
            bool(option.state & QtWidgets.QStyle.StateFlag.State_Selected)
        if sel and KEYBOARD["on"]:
            hov = True      # case choisie au clavier / à la télécommande : même rendu qu'au survol
        r = QtCore.QRectF(option.rect).adjusted(7, 7, -7, -7)
        p.save()
        p.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QtGui.QPainter.RenderHint.SmoothPixmapTransform)
        pm = index.data(Qt.ItemDataRole.DecorationRole)
        title = index.data(Qt.ItemDataRole.DisplayRole) or ""
        f_title = QtGui.QFont(option.font)
        f_title.setPointSizeF(9.5)
        f_title.setBold(True)
        f_sub = QtGui.QFont(option.font)
        f_sub.setPointSizeF(8.5)

        if self.style in ("wide", "resume"):
            self._paint_wide(p, option, it, r, pm, title, hov, f_title, f_sub)
            p.restore()
            return
        if self.style in ("cover", "coverc", "land", "big", "tile", "tilebig", "actor2", "provider", "posterbig",
                          "postersm", "coeur", "studio"):
            getattr(self, "_paint_" + self.style)(p, option, it, r, pm, title, hov)
            p.restore()
            return
        if self.style == "cat":
            self._paint_cat(p, option, it, r, pm, hov)
            p.restore()
            return

        if self.style == "actor":
            d = min(r.width(), 118)
            img = QtCore.QRectF(r.center().x() - d / 2, r.top() + 2, d, d)
            path = QtGui.QPainterPath()
            path.addEllipse(img)
            p.setClipPath(path)
            if pm is not None and not pm.isNull():
                draw_image(p, img, pm, "cover")
            else:
                draw_placeholder(p, img, initials(it["name"]), option.font, 0)
            p.setClipping(False)
            if hov:
                p.setPen(QtGui.QPen(QtGui.QColor(ACCENT), 3))
                p.drawEllipse(img.adjusted(1, 1, -1, -1))
            tr = QtCore.QRectF(r.left(), img.bottom() + 8, r.width(), 36)
            p.setFont(f_title)
            p.setPen(QtGui.QColor("#ffffff"))
            fm = QtGui.QFontMetrics(f_title)
            p.drawText(tr, _flags(Qt.AlignmentFlag.AlignHCenter, Qt.AlignmentFlag.AlignTop, Qt.TextFlag.TextWordWrap),
                       fm.elidedText(it["name"], Qt.TextElideMode.ElideRight, int(tr.width() * 2 - 10)))
            if it.get("sub"):
                p.setFont(f_sub)
                p.setPen(QtGui.QColor("#8b91a3"))
                sr = QtCore.QRectF(r.left(), tr.bottom() - 2, r.width(), 18)
                p.drawText(sr, _flags(Qt.AlignmentFlag.AlignHCenter),
                           QtGui.QFontMetrics(f_sub).elidedText(it["sub"], Qt.TextElideMode.ElideRight, int(sr.width())))
            p.restore()
            return

        if self.style == "poster":
            img = QtCore.QRectF(r.left(), r.top(), r.width(), r.width() * 1.5)
            mode = "cover"
        else:
            img = QtCore.QRectF(r.left(), r.top(), r.width(), r.height() - 42)
            mode = "contain"
        if hov:
            img.adjust(-2, -2, 2, 2)
        path = QtGui.QPainterPath()
        path.addRoundedRect(img, 10, 10)
        if self.style == "channel":
            p.fillPath(path, QtGui.QColor("#232734" if hov else "#191c25"))
        if pm is not None and not pm.isNull():
            p.setClipPath(path)
            draw_image(p, img.adjusted(12, 10, -12, -10) if mode == "contain" else img, pm, mode)
            p.setClipping(False)
        else:
            draw_placeholder(p, img, initials(title), option.font, 10, big=self.style == "poster")
            if self.style == "poster":
                f = QtGui.QFont(option.font)
                f.setPointSizeF(8.5)
                p.setFont(f)
                p.setPen(QtGui.QColor("#9aa0b2"))
                p.drawText(img.adjusted(10, 0, -10, -14),
                           _flags(Qt.AlignmentFlag.AlignHCenter, Qt.AlignmentFlag.AlignBottom, Qt.TextFlag.TextWordWrap),
                           title)
        if hov or sel:
            p.setPen(QtGui.QPen(QtGui.QColor(ACCENT), 2.5))
            p.drawPath(path)

        # barre de progression
        prog = it.get("progress")
        if prog:
            bar = QtCore.QRectF(img.left() + 10, img.bottom() - 12, img.width() - 20, 4)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QtGui.QColor(255, 255, 255, 70))
            p.drawRoundedRect(bar, 2, 2)
            p.setBrush(QtGui.QColor(ACCENT))
            p.drawRoundedRect(QtCore.QRectF(bar.left(), bar.top(), bar.width() * min(1, prog), 4), 2, 2)
        # badges
        if it.get("available"):
            self._badge(p, img, "✓ Disponible", "#1f9d61", option.font)
        elif it.get("unavailable"):
            p.fillPath(path, QtGui.QColor(13, 14, 18, 120))
        if it.get("url") in self.win.favorites:
            f = QtGui.QFont(option.font)
            f.setPointSize(12)
            p.setFont(f)
            p.setPen(QtGui.QColor("#ffc940"))
            p.drawText(QtCore.QRectF(img.right() - 28, img.top() + 4, 24, 24),
                       _flags(Qt.AlignmentFlag.AlignCenter), "★")
        rating = it.get("_rating")
        if self.style == "poster" and rating:
            f = QtGui.QFont(option.font)
            f.setPointSizeF(8)
            f.setBold(True)
            p.setFont(f)
            txt = f"★ {rating}"
            w = QtGui.QFontMetrics(f).horizontalAdvance(txt) + 12
            br = QtCore.QRectF(img.left() + 8, img.top() + 8, w, 20)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QtGui.QColor(0, 0, 0, 170))
            p.drawRoundedRect(br, 6, 6)
            p.setPen(QtGui.QColor("#ffd24a"))
            p.drawText(br, _flags(Qt.AlignmentFlag.AlignCenter), txt)

        # texte
        tr = QtCore.QRectF(r.left() + 2, img.bottom() + 7, r.width() - 4, 18)
        p.setFont(f_title)
        p.setPen(QtGui.QColor("#ffffff" if hov else "#e3e5ec"))
        fm = QtGui.QFontMetrics(f_title)
        align = Qt.AlignmentFlag.AlignHCenter if self.style == "channel" else Qt.AlignmentFlag.AlignLeft
        p.drawText(tr, _flags(align), fm.elidedText(title, Qt.TextElideMode.ElideRight, int(tr.width())))
        sub = it.get("sub")
        if sub:
            p.setFont(f_sub)
            p.setPen(QtGui.QColor("#8b91a3"))
            sr = QtCore.QRectF(tr.left(), tr.bottom() + 1, tr.width(), 16)
            p.drawText(sr, _flags(align), QtGui.QFontMetrics(f_sub).elidedText(sub, Qt.TextElideMode.ElideRight, int(sr.width())))
        p.restore()

    @staticmethod
    def _pill(p, rect_pos, text, color, font, size=8.0, right=False):
        f = QtGui.QFont(font)
        f.setPointSizeF(size)
        f.setBold(True)
        p.setFont(f)
        w = QtGui.QFontMetrics(f).horizontalAdvance(text) + 14
        x, y = rect_pos
        br = QtCore.QRectF(x - w if right else x, y, w, 22)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QtGui.QColor(color))
        p.drawRoundedRect(br, 6, 6)
        p.setPen(QtGui.QColor("white"))
        p.drawText(br, _flags(Qt.AlignmentFlag.AlignCenter), text)

    def _paint_wide(self, p, option, it, r, pm, title, hov, f_title, f_sub):
        img = QtCore.QRectF(r.left(), r.top(), r.width(), r.width() * 9 / 16)
        path = QtGui.QPainterPath()
        path.addRoundedRect(img, 12, 12)
        live_logo = it.get("kind") == "live" and not it.get("_img")
        p.save()
        p.setClipPath(path)
        if live_logo:
            g = QtGui.QLinearGradient(img.topLeft(), img.bottomRight())
            g.setColorAt(0, QtGui.QColor("#2a2f3a"))
            g.setColorAt(1, QtGui.QColor("#121418"))
            p.fillPath(path, g)
            if pm is not None and not pm.isNull():
                draw_image(p, img.adjusted(img.width() * .24, img.height() * .14,
                                           -img.width() * .24, -img.height() * .34), pm, "contain")
            else:
                self._text(p, img.adjusted(0, 0, 0, -30), initials(it.get("overlay") or title),
                           self._font(option.font, 22, QtGui.QFont.Weight.Black), "#5d6478",
                           _flags(Qt.AlignmentFlag.AlignCenter))
        elif pm is not None and not pm.isNull():
            draw_image(p, img, pm, "cover")
        else:
            draw_placeholder(p, img, initials(title), option.font, 12, big=True)
        g = QtGui.QLinearGradient(0, img.bottom() - img.height() * .5, 0, img.bottom())
        g.setColorAt(0, QtGui.QColor(0, 0, 0, 0))
        g.setColorAt(1, QtGui.QColor(0, 0, 0, 200))
        if it.get("overlay") or it.get("resume") or it.get("progress"):
            p.fillRect(img, g)
        if it.get("overlay"):
            self._text(p, QtCore.QRectF(img.left() + 10, img.bottom() - 34, img.width() - 20, 20), it["overlay"].upper(),
                       self._font(option.font, 9.5, QtGui.QFont.Weight.DemiBold), "#ffffff",
                       _flags(Qt.AlignmentFlag.AlignLeft, Qt.AlignmentFlag.AlignVCenter))
        if it.get("resume"):
            y = img.bottom() - 24
            p.drawPixmap(QtCore.QPointF(img.left() + 12, y - 8), nav_icon("play", "#ffffff", 16))
            self._progress_bar(p, QtCore.QRectF(img.left() + 36, y - 2, 64, 5), it.get("progress") or 0)
            self._text(p, QtCore.QRectF(img.left() + 110, y - 11, img.width() - 120, 22), it.get("remain", ""),
                       self._font(option.font, 10.5, QtGui.QFont.Weight.DemiBold), "#ffffff",
                       _flags(Qt.AlignmentFlag.AlignLeft, Qt.AlignmentFlag.AlignVCenter))
        elif it.get("progress"):
            self._progress_bar(p, QtCore.QRectF(img.left() + 10, img.bottom() - 10, img.width() - 20, 4), it["progress"])
        p.restore()
        self._hover_ring(p, path, hov)
        if it.get("time"):
            f = self._font(option.font, 10, QtGui.QFont.Weight.Bold)
            p.setFont(f)
            w = QtGui.QFontMetrics(f).horizontalAdvance(it["time"]) + 38
            br = QtCore.QRectF(img.left() + 8, img.top() + 8, w, 26)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QtGui.QColor(ACCENT))
            p.drawRoundedRect(br, 8, 8)
            p.drawPixmap(QtCore.QPointF(br.left() + 7, br.top() + 5), nav_icon("clock", "#ffffff", 16))
            p.setPen(QtGui.QColor("white"))
            p.drawText(br.adjusted(22, 0, 0, 0), _flags(Qt.AlignmentFlag.AlignCenter), it["time"])
        elif it.get("badge") and it.get("badge") != "LIVE":
            self._pill(p, (img.left() + 10, img.top() + 10), it["badge"], RED, option.font, 7.5)
        if self.style == "resume":
            return
        tr = QtCore.QRectF(r.left() + 2, img.bottom() + 8, r.width() - 4, 44)
        self._text(p, tr, title, self._font(option.font, 11.5, QtGui.QFont.Weight.Normal), "#ffffff", lines=2)
        if it.get("sub") and not it.get("resume_sub_hidden"):
            fm = QtGui.QFontMetrics(self._font(option.font, 11.5))
            lines = 2 if fm.horizontalAdvance(title) > tr.width() else 1
            self._text(p, QtCore.QRectF(tr.left(), tr.top() + 22 * lines, tr.width(), 18), it["sub"],
                       self._font(option.font, 9.5), "#8b91a3")

    def _paint_cat(self, p, option, it, r, pm, hov):
        tile = QtCore.QRectF(r)
        path = QtGui.QPainterPath()
        path.addRoundedRect(tile, 12, 12)
        p.save()
        p.setClipPath(path)
        p.fillPath(path, QtGui.QColor("#1b1f2a"))
        logo_mode = it.get("_ckind") == "live"
        if pm is not None and not pm.isNull() and not it.get("special"):
            if logo_mode:
                draw_image(p, QtCore.QRectF(tile.right() - 70, tile.center().y() - 22, 58, 44), pm, "contain")
            else:
                draw_image(p, tile, pm, "cover")
                g = QtGui.QLinearGradient(tile.left(), 0, tile.right(), 0)
                g.setColorAt(0, QtGui.QColor(10, 12, 18, 235))
                g.setColorAt(0.6, QtGui.QColor(10, 12, 18, 150))
                g.setColorAt(1, QtGui.QColor(10, 12, 18, 60))
                p.fillRect(tile, g)
        p.restore()
        p.setPen(QtGui.QPen(QtGui.QColor(ACCENT if hov else "#2c3140"), 2 if hov else 1))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawPath(path)
        x = tile.left() + 16
        if it.get("special"):
            f = QtGui.QFont(option.font)
            f.setPointSize(20)
            p.setFont(f)
            p.setPen(QtGui.QColor("#e6e8ee"))
            p.drawText(QtCore.QRectF(x, tile.top(), 40, tile.height()), _flags(Qt.AlignmentFlag.AlignVCenter), it.get("icon", "🎬"))
            x += 44
        f = QtGui.QFont(option.font)
        f.setPointSizeF(10.5)
        f.setBold(True)
        p.setFont(f)
        p.setPen(QtGui.QColor("white"))
        tw = tile.right() - x - (78 if logo_mode else 12)
        name_r = QtCore.QRectF(x, tile.top() + 10, tw, tile.height() - (38 if it.get("sub") else 20))
        fm = QtGui.QFontMetrics(f)
        words_fit = all(fm.horizontalAdvance(w) <= tw for w in it["name"].split())
        txt = fm.elidedText(it["name"], Qt.TextElideMode.ElideRight, int(tw * 2 - 10) if words_fit else int(tw))
        p.save()
        p.setClipRect(QtCore.QRectF(x, tile.top(), tw, tile.height()))
        p.drawText(name_r, _flags(Qt.AlignmentFlag.AlignLeft, Qt.AlignmentFlag.AlignVCenter, Qt.TextFlag.TextWordWrap), txt)
        p.restore()
        if it.get("sub"):
            fs = QtGui.QFont(option.font)
            fs.setPointSizeF(8.5)
            p.setFont(fs)
            p.setPen(QtGui.QColor("#9aa0b2"))
            p.drawText(QtCore.QRectF(x, tile.bottom() - 28, tw, 18), _flags(Qt.AlignmentFlag.AlignLeft),
                       QtGui.QFontMetrics(fs).elidedText(it["sub"], Qt.TextElideMode.ElideRight, int(tw)))

    # ---- utilitaires de dessin
    @staticmethod
    def _font(base, size, weight=QtGui.QFont.Weight.Normal):
        f = QtGui.QFont(base)
        f.setPointSizeF(size * (1 + (UI.k - 1) * 0.6))
        f.setWeight(weight)
        return f

    def _text(self, p, rect, text, font, color="#ffffff", flags=None, lines=1):
        p.setFont(font)
        p.setPen(QtGui.QColor(color))
        fm = QtGui.QFontMetrics(font)
        fl = flags if flags is not None else _flags(Qt.AlignmentFlag.AlignLeft, Qt.AlignmentFlag.AlignTop)
        if lines > 1:
            txt = fm.elidedText(text, Qt.TextElideMode.ElideRight, int(rect.width() * lines - 12))
            p.drawText(rect, fl | Qt.TextFlag.TextWordWrap.value, txt)
        else:
            p.drawText(rect, fl, fm.elidedText(text, Qt.TextElideMode.ElideRight, int(rect.width())))

    def _hover_ring(self, p, path, hov):
        if hov:
            p.setPen(QtGui.QPen(QtGui.QColor(255, 255, 255, 230), 3))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawPath(path)

    def _red_pill(self, p, center_x, y, text, font):
        f = self._font(font, 9.5, QtGui.QFont.Weight.DemiBold)
        p.setFont(f)
        w = QtGui.QFontMetrics(f).horizontalAdvance(text) + 22
        br = QtCore.QRectF(center_x - w / 2, y, w, 26)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QtGui.QColor(RED))
        p.drawRoundedRect(br, 8, 8)
        p.setPen(QtGui.QColor("white"))
        p.drawText(br, _flags(Qt.AlignmentFlag.AlignCenter), text)

    def _outline_pill(self, p, x, y, text, font, size=10.5):
        f = self._font(font, size, QtGui.QFont.Weight.DemiBold)
        p.setFont(f)
        w = QtGui.QFontMetrics(f).horizontalAdvance(text) + 26
        br = QtCore.QRectF(x, y, w, 30)
        p.setBrush(QtGui.QColor(0, 0, 0, 120))
        p.setPen(QtGui.QPen(QtGui.QColor(255, 255, 255, 200), 1.4))
        p.drawRoundedRect(br, 15, 15)
        p.setPen(QtGui.QColor("white"))
        p.drawText(br, _flags(Qt.AlignmentFlag.AlignCenter), text)
        return br

    def _progress_bar(self, p, rect, frac, color="#ffffff"):
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QtGui.QColor(255, 255, 255, 70))
        p.drawRoundedRect(rect, rect.height() / 2, rect.height() / 2)
        p.setBrush(QtGui.QColor(color))
        p.drawRoundedRect(QtCore.QRectF(rect.left(), rect.top(), max(rect.height(), rect.width() * min(1, frac)), rect.height()),
                          rect.height() / 2, rect.height() / 2)

    # ---- affiche sans texte (rangées)
    def _paint_cover(self, p, option, it, r, pm, title, hov):
        img = QtCore.QRectF(r.left(), r.top(), r.width(), r.width() * 1.5)
        path = QtGui.QPainterPath()
        path.addRoundedRect(img, 12, 12)
        p.save()
        p.setClipPath(path)
        if pm is not None and not pm.isNull():
            draw_image(p, img, pm, "cover")
        else:
            draw_placeholder(p, img, "", option.font, 12)
            self._text(p, img.adjusted(14, 0, -14, 0), title, self._font(option.font, 12, QtGui.QFont.Weight.Bold),
                       "#c9ccd6", _flags(Qt.AlignmentFlag.AlignCenter), lines=4)
        if it.get("progress"):
            self._progress_bar(p, QtCore.QRectF(img.left() + 10, img.bottom() - 12, img.width() - 20, 4), it["progress"])
        p.restore()
        if it.get("unavailable"):
            self._red_pill(p, img.center().x(), img.bottom() - 40, "Indisponible", option.font)
        elif it.get("available"):
            self._red_pill(p, img.center().x(), img.bottom() - 40, "Disponible", option.font) if False else None
        if it.get("url") in self.win.favorites:
            self._text(p, QtCore.QRectF(img.right() - 30, img.top() + 6, 24, 24), "★",
                       self._font(option.font, 13), "#ffc940", _flags(Qt.AlignmentFlag.AlignCenter))
        self._hover_ring(p, path, hov)
        if it.get("caption"):
            self._text(p, QtCore.QRectF(r.left() + 4, img.bottom() + 8, r.width() - 8, 26), it["caption"],
                       self._font(option.font, 11.5, QtGui.QFont.Weight.DemiBold), "#ffffff",
                       _flags(Qt.AlignmentFlag.AlignHCenter, Qt.AlignmentFlag.AlignVCenter), lines=1)

    _paint_coverc = _paint_cover

    # ---- paysage (Top de la semaine)
    def _tlogo(self, it):
        u = it.get("_tlogo")
        pm = self.win.images.get(u) if u else None
        return pm if pm is not None and not pm.isNull() else None

    def _draw_title(self, p, option, it, area, title, size, align=Qt.AlignmentFlag.AlignLeft):
        """Logo-titre TMDB si disponible, sinon le titre en texte."""
        lg = self._tlogo(it)
        if lg is not None:
            s = lg.size().scaled(area.size().toSize(), Qt.AspectRatioMode.KeepAspectRatio)
            x = area.left() if align == Qt.AlignmentFlag.AlignLeft else area.center().x() - s.width() / 2
            p.drawPixmap(QtCore.QRectF(x, area.bottom() - s.height(), s.width(), s.height()), lg,
                         QtCore.QRectF(lg.rect()))
            return
        self._text(p, area, title, self._font(option.font, size, QtGui.QFont.Weight.Black), "#ffffff",
                   _flags(align, Qt.AlignmentFlag.AlignBottom), lines=2)

    def _paint_land(self, p, option, it, r, pm, title, hov):
        img = QtCore.QRectF(r)
        path = QtGui.QPainterPath()
        path.addRoundedRect(img, 12, 12)
        p.save()
        p.setClipPath(path)
        if pm is not None and not pm.isNull():
            draw_image(p, img, pm, "cover")
        else:
            draw_placeholder(p, img, "", option.font, 12)
        g = QtGui.QLinearGradient(0, img.top() + img.height() * .45, 0, img.bottom())
        g.setColorAt(0, QtGui.QColor(0, 0, 0, 0))
        g.setColorAt(1, QtGui.QColor(0, 0, 0, 190))
        p.fillRect(img, g)
        self._draw_title(p, option, it, QtCore.QRectF(img.left() + 14, img.top() + img.height() * .45,
                                                      img.width() * .62, img.height() * .45), title, 13)
        p.restore()
        if it.get("unavailable"):
            self._red_pill(p, img.center().x(), img.top() + 10, "Indisponible", option.font)
        self._hover_ring(p, path, hov)

    # ---- affiches sans texte (Les plus gros succès, Top du mois)
    def _paint_posterbig(self, p, option, it, r, pm, title, hov):
        img = QtCore.QRectF(r)
        path = QtGui.QPainterPath()
        path.addRoundedRect(img, 12, 12)
        p.save()
        p.setClipPath(path)
        if pm is not None and not pm.isNull():
            draw_image(p, img, pm, "cover")
        else:
            draw_placeholder(p, img, "", option.font, 12)
            self._text(p, img.adjusted(10, 0, -10, 0), title, self._font(option.font, 12, QtGui.QFont.Weight.Bold),
                       "#c9ccd6", _flags(Qt.AlignmentFlag.AlignCenter), lines=4)
        p.restore()
        if it.get("unavailable"):
            self._red_pill(p, img.center().x(), img.bottom() - 36, "Indisponible", option.font)
        if it.get("url") in self.win.favorites:
            self._text(p, QtCore.QRectF(img.right() - 30, img.top() + 6, 24, 24), "★",
                       self._font(option.font, 13), "#ffc940", _flags(Qt.AlignmentFlag.AlignCenter))
        self._hover_ring(p, path, hov)

    _paint_postersm = _paint_posterbig

    # ---- plateformes (En streaming sur)
    def _paint_provider(self, p, option, it, r, pm, title, hov):
        img = QtCore.QRectF(r)
        path = QtGui.QPainterPath()
        path.addRoundedRect(img, 14, 14)
        p.save()
        p.setClipPath(path)
        p.fillPath(path, QtGui.QColor("#15181f"))
        if pm is not None and not pm.isNull():
            draw_image(p, img, pm, "cover")
        else:
            self._text(p, img.adjusted(8, 0, -8, 0), it["name"], self._font(option.font, 14, QtGui.QFont.Weight.Black),
                       "#ffffff", _flags(Qt.AlignmentFlag.AlignCenter), lines=2)
        p.restore()
        p.setPen(QtGui.QPen(QtGui.QColor(255, 255, 255, 55), 1.2))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawPath(path)
        self._hover_ring(p, path, hov)

    # ---- studios (Disney, Marvel…)
    def _paint_studio(self, p, option, it, r, pm, title, hov):
        img = QtCore.QRectF(r)
        path = QtGui.QPainterPath()
        path.addRoundedRect(img, 12, 12)
        g = QtGui.QLinearGradient(img.topLeft(), img.bottomRight())
        g.setColorAt(0, QtGui.QColor(it.get("c1") or "#1b2230"))
        g.setColorAt(1, QtGui.QColor(it.get("c2") or "#0b0e14"))
        p.fillPath(path, g)
        dark_text = QtGui.QColor(it.get("c1") or "#000").lightness() > 170
        n = len(it["name"])
        f = self._font(option.font, 13 if n > 8 else 16 if n > 5 else 20, QtGui.QFont.Weight.Black)
        f.setLetterSpacing(QtGui.QFont.SpacingType.PercentageSpacing, 104)
        self._text(p, img.adjusted(8, 0, -8, 0), it["name"], f, "#11151c" if dark_text else "#ffffff",
                   _flags(Qt.AlignmentFlag.AlignCenter))
        p.setPen(QtGui.QPen(QtGui.QColor(255, 255, 255, 60), 1.2))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawPath(path)
        self._hover_ring(p, path, hov)

    # ---- Coups de cœur : grande affiche + logo-titre + genre
    def _paint_coeur(self, p, option, it, r, pm, title, hov):
        img = QtCore.QRectF(r)
        path = QtGui.QPainterPath()
        path.addRoundedRect(img, 22, 22)
        p.save()
        p.setClipPath(path)
        if pm is not None and not pm.isNull():
            draw_image(p, img, pm, "cover")
        else:
            draw_placeholder(p, img, "", option.font, 22)
        g = QtGui.QLinearGradient(0, img.top() + img.height() * .5, 0, img.bottom())
        g.setColorAt(0, QtGui.QColor(0, 0, 0, 0))
        g.setColorAt(1, QtGui.QColor(0, 0, 0, 225))
        p.fillRect(img, g)
        self._draw_title(p, option, it, QtCore.QRectF(img.left() + 26, img.bottom() - 150, img.width() * .62, 96),
                         title, 20)
        if it.get("sub"):
            self._text(p, QtCore.QRectF(img.left() + 26, img.bottom() - 44, img.width() - 52, 24), it["sub"],
                       self._font(option.font, 11.5, QtGui.QFont.Weight.DemiBold), "#d9dce4")
        p.restore()
        self._hover_ring(p, path, hov)

    # ---- grand format (Nouveautés, Coups de cœur)
    def _paint_big(self, p, option, it, r, pm, title, hov):
        img = QtCore.QRectF(r)
        path = QtGui.QPainterPath()
        path.addRoundedRect(img, 20, 20)
        p.save()
        p.setClipPath(path)
        if pm is not None and not pm.isNull():
            draw_image(p, img, pm, "cover")
        else:
            draw_placeholder(p, img, "", option.font, 20)
        g = QtGui.QLinearGradient(0, img.top() + img.height() * .35, 0, img.bottom())
        g.setColorAt(0, QtGui.QColor(0, 0, 0, 0))
        g.setColorAt(.7, QtGui.QColor(0, 0, 0, 170))
        g.setColorAt(1, QtGui.QColor(0, 0, 0, 235))
        p.fillRect(img, g)
        y = img.bottom() - 34
        if it.get("sub"):
            self._text(p, QtCore.QRectF(img.left() + 26, y, img.width() - 52, 24), it["sub"],
                       self._font(option.font, 12, QtGui.QFont.Weight.DemiBold), "#d9dce4")
        y -= 46
        area = QtCore.QRectF(img.left() + 26, y - 40, img.width() * .55, 84)
        self._draw_title(p, option, it, area, title, 20)
        if it.get("badge"):
            top = area.top() if self._tlogo(it) is None else area.bottom() - min(
                area.height(), self._tlogo(it).height() * area.width() / max(1, self._tlogo(it).width()))
            self._outline_pill(p, img.left() + 26, min(y - 62, top - 40), it["badge"], option.font)
        p.restore()
        self._hover_ring(p, path, hov)

    # ---- tuile de catégorie
    def _tile_bg(self, p, img, it, pm, radius):
        path = QtGui.QPainterPath()
        path.addRoundedRect(img, radius, radius)
        base = QtGui.QColor("#2a3140") if it.get("special") else tile_color(it.get("name", ""))
        p.save()
        p.setClipPath(path)
        g = QtGui.QLinearGradient(img.topLeft(), img.bottomRight())
        g.setColorAt(0, base.lighter(125))
        g.setColorAt(1, base.darker(210))
        p.fillPath(path, g)
        if pm is not None and not pm.isNull() and not it.get("special") and it.get("_ckind") != "live":
            key = it.get("logo")
            bl = self._blur_cache.get(key)
            if bl is None:
                bl = blurred_pixmap(pm, 10)
                self._blur_cache[key] = bl
            p.setOpacity(.45)
            draw_image(p, img, bl, "cover")
            p.setOpacity(1)
        g2 = QtGui.QLinearGradient(0, img.top(), 0, img.bottom())
        g2.setColorAt(0, QtGui.QColor(0, 0, 0, 0))
        g2.setColorAt(1, QtGui.QColor(0, 0, 0, 150))
        p.fillRect(img, g2)
        p.restore()
        p.setPen(QtGui.QPen(QtGui.QColor(255, 255, 255, 60), 1.2))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawPath(path)
        return path

    def _paint_tile(self, p, option, it, r, pm, title, hov):
        img = QtCore.QRectF(r)
        path = self._tile_bg(p, img, it, pm, 12)
        self._text(p, QtCore.QRectF(img.left() + 14, img.top() + 10, img.width() - 28, img.height() - 22), it["name"],
                   self._font(option.font, 12, QtGui.QFont.Weight.Bold), "#ffffff",
                   _flags(Qt.AlignmentFlag.AlignLeft, Qt.AlignmentFlag.AlignBottom), lines=2)
        self._hover_ring(p, path, hov)

    def _paint_tilebig(self, p, option, it, r, pm, title, hov):
        img = QtCore.QRectF(r)
        path = self._tile_bg(p, img, it, None, 14)
        self._text(p, QtCore.QRectF(img.right() - 96, img.top() + 8, 86, 86), it.get("icon") or cat_emoji(it["name"]),
                   self._font("Segoe UI Emoji", 40), "#ffffff", _flags(Qt.AlignmentFlag.AlignCenter))
        self._text(p, QtCore.QRectF(img.left() + 16, img.top() + 10, img.width() - 32, img.height() - 22), it["name"],
                   self._font(option.font, 15, QtGui.QFont.Weight.Black), "#ffffff",
                   _flags(Qt.AlignmentFlag.AlignLeft, Qt.AlignmentFlag.AlignBottom), lines=2)
        if it.get("sub"):
            self._text(p, QtCore.QRectF(img.left() + 16, img.top() + 12, img.width() - 120, 20), it["sub"],
                       self._font(option.font, 9.5), "#e6e8ee")
        self._hover_ring(p, path, hov)

    # ---- acteur (grand cercle)
    def _paint_actor2(self, p, option, it, r, pm, title, hov):
        d = min(r.width(), r.height() - 44)
        img = QtCore.QRectF(r.center().x() - d / 2, r.top() + 2, d, d)
        path = QtGui.QPainterPath()
        path.addEllipse(img)
        p.save()
        p.setClipPath(path)
        if pm is not None and not pm.isNull():
            draw_image(p, img, pm, "cover")
        else:
            draw_placeholder(p, img, initials(it["name"]), option.font, 0, big=True)
        p.restore()
        self._hover_ring(p, path, hov)
        self._text(p, QtCore.QRectF(r.left(), img.bottom() + 8, r.width(), 50), it["name"],
                   self._font(option.font, 12.5, QtGui.QFont.Weight.DemiBold), "#ffffff",
                   _flags(Qt.AlignmentFlag.AlignHCenter, Qt.AlignmentFlag.AlignTop), lines=2)

    @staticmethod
    def _badge(p, img, text, color, font):
        f = QtGui.QFont(font)
        f.setPointSizeF(7.5)
        f.setBold(True)
        p.setFont(f)
        w = QtGui.QFontMetrics(f).horizontalAdvance(text) + 12
        br = QtCore.QRectF(img.left() + 8, img.bottom() - 28, w, 19)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QtGui.QColor(color))
        p.drawRoundedRect(br, 6, 6)
        p.setPen(QtGui.QColor("white"))
        p.drawText(br, _flags(Qt.AlignmentFlag.AlignCenter), text)


class CardView(QtWidgets.QListView):
    item_clicked = QtCore.Signal(dict)

    def __init__(self, win, style, horizontal=False, parent=None):
        super().__init__(parent)
        self.win, self.style, self.horizontal = win, style, horizontal
        self.model_ = CardModel(win.images, self)
        self.setModel(self.model_)
        self.setItemDelegate(CardDelegate(win, style))
        self.setMouseTracking(True)
        self.setUniformItemSizes(True)
        self.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
        self.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.SingleSelection)
        self.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
        self.setVerticalScrollMode(QtWidgets.QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.setHorizontalScrollMode(QtWidgets.QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.setMovement(QtWidgets.QListView.Movement.Static)
        self.viewport().setCursor(Qt.CursorShape.PointingHandCursor)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._menu)
        self._style, self._horizontal = style, horizontal
        self.setGridSize(card_size(style))
        UI.changed.connect(self._rescale)
        if horizontal:
            self.setFlow(QtWidgets.QListView.Flow.LeftToRight)
            self.setWrapping(False)
            self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            self.setFixedHeight(card_size(style).height() + 6)
        else:
            self.setViewMode(QtWidgets.QListView.ViewMode.IconMode)
            self.setResizeMode(QtWidgets.QListView.ResizeMode.Adjust)
            self.setLayoutMode(QtWidgets.QListView.LayoutMode.Batched)
            self.setBatchSize(400)
            self.verticalScrollBar().setSingleStep(40)
        self.clicked.connect(lambda idx: self.item_clicked.emit(idx.data(ITEM_ROLE)))
        self.activated.connect(lambda idx: None)

    def _rescale(self):
        try:
            self.setGridSize(card_size(self._style))
            if self._horizontal:
                self.setFixedHeight(card_size(self._style).height() + 6)
            self.doItemsLayout()
            self.viewport().update()
        except RuntimeError:
            pass

    def set_items(self, items):
        self.model_.set_items(items)

    def wheelEvent(self, e):
        if self.horizontal:
            d = e.angleDelta()
            if (e.modifiers() & Qt.KeyboardModifier.ShiftModifier) or abs(d.x()) > abs(d.y()):
                sb = self.horizontalScrollBar()
                sb.setValue(sb.value() - (d.x() or d.y()))
                e.accept()
            else:
                e.ignore()
            return
        super().wheelEvent(e)

    def _menu(self, pos):
        idx = self.indexAt(pos)
        if not idx.isValid():
            return
        it = idx.data(ITEM_ROLE)
        if not it or it.get("kind") not in ("live", "movie", "series"):
            return
        m = QtWidgets.QMenu(self)
        a_open = m.addAction("▶  Lire" if it["kind"] == "live" else "Ouvrir la fiche")
        a_fav = m.addAction("Retirer de Ma liste" if it["url"] in self.win.favorites else "★  Ajouter à Ma liste")
        a_copy = m.addAction("Copier le lien du flux") if it["kind"] != "series" else None
        act = m.exec(self.viewport().mapToGlobal(pos))
        if act is a_open:
            self.item_clicked.emit(it)
        elif act is a_fav:
            self.win.toggle_favorite(it)
            self.viewport().update()
        elif a_copy is not None and act is a_copy:
            QtWidgets.QApplication.clipboard().setText(it["url"])


class ClickLabel(QtWidgets.QLabel):
    clicked = QtCore.Signal()

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mouseReleaseEvent(e)


class HRow(QtWidgets.QWidget):
    """Rangée horizontale titrée (façon plateformes de streaming)."""

    def __init__(self, win, title, items, style="poster", on_click=None, see_all=None, parent=None,
                 subtitle="", badge=""):
        super().__init__(parent)
        self.win = win
        v = QtWidgets.QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(2)
        h = QtWidgets.QHBoxLayout()
        h.setContentsMargins(0, 0, 8, 0)
        tv = QtWidgets.QVBoxLayout()
        tv.setSpacing(0)
        lab = ClickLabel(title + ("  <span style='color:#8b91a3; font-weight:600'>›</span>" if see_all and title else ""))
        lab.setVisible(bool(title))
        lab.setObjectName("rowtitle")
        lab.setTextFormat(Qt.TextFormat.RichText)
        if see_all:
            lab.setCursor(Qt.CursorShape.PointingHandCursor)
            lab.clicked.connect(see_all)
        tv.addWidget(lab)
        if subtitle:
            tv.addWidget(label(subtitle, "rowsub"))
        h.addLayout(tv)
        h.addStretch(1)
        if badge:
            h.addWidget(label(badge, "livepill"), 0, Qt.AlignmentFlag.AlignTop)
            h.addSpacing(8)
        self.view = CardView(win, style, horizontal=True)
        self.view.set_items(items)
        for txt, sign in (("‹", -1), ("›", 1)):
            b = QtWidgets.QPushButton(txt)
            b.setObjectName("arrow")
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setFixedSize(34, 30)
            b.clicked.connect(lambda _c=False, s=sign: self._scroll(s))
            h.addWidget(b, 0, Qt.AlignmentFlag.AlignTop)
        if title:
            v.addLayout(h)
            v.addSpacing(6)
        else:
            hw = QtWidgets.QWidget()
            hw.setLayout(h)
            hw.hide()
        v.addWidget(self.view)
        self.view.item_clicked.connect(on_click or win.open_item)
        self._anim = None

    def refresh(self, it):
        self.view.model_.refresh(it)

    def _scroll(self, sign):
        sb = self.view.horizontalScrollBar()
        target = max(0, min(sb.maximum(), sb.value() + sign * int(self.view.viewport().width() * 0.85)))
        self._anim = QtCore.QPropertyAnimation(sb, b"value", self)
        self._anim.setDuration(380)
        self._anim.setEasingCurve(QtCore.QEasingCurve.Type.OutCubic)
        self._anim.setStartValue(sb.value())
        self._anim.setEndValue(target)
        self._anim.start()


# --------------------------------------------------------------------------- #
#  Fond d'écran (backdrop) avec dégradés
# --------------------------------------------------------------------------- #
class Backdrop(QtWidgets.QWidget):
    def __init__(self, images, parent=None):
        super().__init__(parent)
        self.images = images
        self.backdrop = self.poster = ""
        self._blur = {}
        self._scaled = (None, None, None)
        images.loaded.connect(self._loaded)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, False)

    def set_images(self, backdrop, poster=""):
        self.backdrop, self.poster = backdrop or "", poster or ""
        self.update()

    def _loaded(self, url):
        if url and url in (self.backdrop, self.poster):
            self.update()

    def _blurred(self, url, pm):
        b = self._blur.get(url)
        if b is None:
            small = pm.scaled(24, 36, Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                              Qt.TransformationMode.SmoothTransformation)
            b = small.scaled(small.width() * 30, small.height() * 30, Qt.AspectRatioMode.KeepAspectRatio,
                             Qt.TransformationMode.SmoothTransformation)
            self._blur[url] = b
        return b

    def paintEvent(self, e):
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.RenderHint.SmoothPixmapTransform)
        rect = QtCore.QRectF(self.rect())
        bg = QtGui.QColor(BG)
        p.fillRect(rect, bg)
        pm = self.images.get(self.backdrop) if self.backdrop else None
        blurred = False
        if pm is None and self.poster:
            pm = self.images.get(self.poster)
            if pm is not None:
                pm, blurred = self._blurred(self.poster, pm), True
        if pm is not None and not pm.isNull():
            w = rect.width() * (1.0 if blurred else 0.78)
            s = pm.size().scaled(QtCore.QSize(int(w), int(rect.height())),
                                 Qt.AspectRatioMode.KeepAspectRatioByExpanding)
            key = (id(pm), s.width(), s.height())
            if self._scaled[0] != key:
                self._scaled = (key, pm.scaled(s, Qt.AspectRatioMode.IgnoreAspectRatio,
                                               Qt.TransformationMode.SmoothTransformation), None)
            spm = self._scaled[1]
            x = rect.width() - spm.width()
            y = min(0, (rect.height() - spm.height()) / 3)
            p.drawPixmap(QtCore.QPointF(x, y), spm)
            if blurred:
                p.fillRect(rect, QtGui.QColor(13, 14, 18, 150))
            x0 = max(0.0, x / max(1, rect.width()))
            g = QtGui.QLinearGradient(0, 0, rect.width(), 0)
            c = QtGui.QColor(bg)
            g.setColorAt(0, c)
            g.setColorAt(min(0.99, x0 + 0.02), c)
            c2 = QtGui.QColor(bg)
            c2.setAlpha(150)
            g.setColorAt(min(0.995, x0 + 0.25), c2)
            c3 = QtGui.QColor(bg)
            c3.setAlpha(0)
            g.setColorAt(1, c3)
            p.fillRect(rect, g)
        gv = QtGui.QLinearGradient(0, 0, 0, rect.height())
        t = QtGui.QColor(bg)
        t.setAlpha(0)
        gv.setColorAt(0.5, t)
        gv.setColorAt(1, bg)
        p.fillRect(rect, gv)
        gt = QtGui.QLinearGradient(0, 0, 0, 90)
        t2 = QtGui.QColor(bg)
        t2.setAlpha(170)
        gt.setColorAt(0, t2)
        gt.setColorAt(1, t)
        p.fillRect(QtCore.QRectF(0, 0, rect.width(), 90), gt)


# --------------------------------------------------------------------------- #
#  Petits widgets
# --------------------------------------------------------------------------- #
def button(text, kind="secondary", cb=None):
    b = QtWidgets.QPushButton(text)
    b.setObjectName(kind)
    b.setCursor(Qt.CursorShape.PointingHandCursor)
    if cb:
        b.clicked.connect(cb)
    return b


def label(text="", obj=None, wrap=False):
    l = QtWidgets.QLabel(text)
    if obj:
        l.setObjectName(obj)
    l.setWordWrap(wrap)
    return l


class ClickFrame(QtWidgets.QFrame):
    clicked = QtCore.Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def keyPressEvent(self, e):
        if e.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space):
            self.clicked.emit()
            return
        super().keyPressEvent(e)

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton and self.rect().contains(e.position().toPoint()):
            self.clicked.emit()
        super().mouseReleaseEvent(e)


class ScrollPage(QtWidgets.QScrollArea):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.verticalScrollBar().setSingleStep(30)
        self.content = QtWidgets.QWidget()
        self.content.setObjectName("page")
        self.v = QtWidgets.QVBoxLayout(self.content)
        self.v.setContentsMargins(0, 0, 0, 0)
        self.v.setSpacing(0)
        self.setWidget(self.content)

    def reset(self):
        old = self.takeWidget()
        if old:
            old.deleteLater()
        self.content = QtWidgets.QWidget()
        self.content.setObjectName("page")
        self.v = QtWidgets.QVBoxLayout(self.content)
        self.v.setContentsMargins(0, 0, 0, 0)
        self.v.setSpacing(0)
        self.setWidget(self.content)


def body_box(parent_layout, margins=(44, 10, 36, 40), spacing=26):
    w = QtWidgets.QWidget()
    lay = QtWidgets.QVBoxLayout(w)
    lay.setContentsMargins(*margins)
    lay.setSpacing(spacing)
    parent_layout.addWidget(w)
    return lay


# --------------------------------------------------------------------------- #
#  Accueil
# --------------------------------------------------------------------------- #
class HeroCarousel(QtWidgets.QWidget):
    """Grande bannière façon OCTO+ : les affiches défilent (glissement), images nettes, s'adapte à la fenêtre."""

    def __init__(self, win, page_title, items, new_urls=()):
        super().__init__()
        self.win, self.items = win, list(items)
        self.new_urls = set(new_urls)
        self.idx = 0
        self.meta = {}
        self._from = None
        self._dir = 1
        self._t = 1.0
        self._frames = {}
        self._ratio = {}
        self._size = None
        self._press = None
        self._drag = 0.0
        self._dots = []
        self.setMouseTracking(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMinimumHeight(460)
        self.page_title = QtWidgets.QLabel(page_title, self)
        self.page_title.setObjectName("pagetitle2")
        self.page_title.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.box = QtWidgets.QWidget(self)
        self.box.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self._fx = QtWidgets.QGraphicsOpacityEffect(self.box)
        self._fx.setOpacity(1.0)
        self.box.setGraphicsEffect(self._fx)
        v = QtWidgets.QVBoxLayout(self.box)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(10)
        self.badge = label("", "outlinepill")
        self.name = label("", "herotitle2", wrap=True)
        self.name.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.logo_l = QtWidgets.QLabel()
        self.logo_l.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.logo_l.hide()
        self.sub = label("", "herometa", wrap=True)
        self.sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.b_play = QtWidgets.QPushButton("  Regarder")
        self.b_play.setObjectName("whitepill")
        self.b_play.setIcon(QtGui.QIcon(nav_icon("play", "#000000", 22)))
        self.b_play.setIconSize(QtCore.QSize(20, 20))
        self.b_play.setCursor(Qt.CursorShape.PointingHandCursor)
        self.b_play.clicked.connect(self._play)
        v.addWidget(self.badge, 0, Qt.AlignmentFlag.AlignHCenter)
        v.addWidget(self.name)
        v.addWidget(self.logo_l)
        v.addWidget(self.sub)
        v.addSpacing(8)
        v.addWidget(self.b_play, 0, Qt.AlignmentFlag.AlignHCenter)
        v.addSpacing(40)
        self.b_prev = QtWidgets.QPushButton("‹", self)
        self.b_next = QtWidgets.QPushButton("›", self)
        for bt, d in ((self.b_prev, -1), (self.b_next, 1)):
            bt.setObjectName("heroarrow")
            bt.setFixedSize(52, 52)
            bt.setCursor(Qt.CursorShape.PointingHandCursor)
            bt.clicked.connect(lambda _c=False, d=d: self.step(d))
            bt.hide()
        self._anim = QtCore.QVariantAnimation(self, startValue=0.0, endValue=1.0, duration=750)
        self._anim.setEasingCurve(QtCore.QEasingCurve.Type.OutCubic)
        self._anim.valueChanged.connect(self._on_anim)
        self._anim.finished.connect(self._anim_done)
        self._slide = QtCore.QTimer(self, interval=8000)
        self._slide.timeout.connect(lambda: self.step(1))
        win.images.loaded.connect(self._img_loaded)
        self.setVisible(bool(self.items))
        if self.items:
            for it in self.items:
                win.meta.request(it, lambda m, it=it: self._got_meta(it, m))
            self._fill(self.items[0])
            self._prefetch(0)

    # -- données
    def _urls(self, it):
        m = self.meta.get(it["url"]) or {}
        big = self.width() * _dpr() > 1400
        bd = hires(m.get("backdrop") or "", "original" if big else "w1280")
        poster = hires(m.get("poster") or it.get("logo") or "", "w780")
        return bd, poster

    def _prefetch(self, i):
        if not self.items:
            return
        for k in (i, i + 1, i - 1):
            it = self.items[k % len(self.items)]
            m = self.meta.get(it["url"]) or {}
            for u in self._urls(it) + ((hires(m["title_logo"], "w780"),) if m.get("title_logo") else ()):
                if u:
                    self.win.images.get(u)

    def _got_meta(self, it, m):
        if not m:
            return
        self.meta[it["url"]] = m
        try:
            i = self.items.index(it)
        except ValueError:
            return
        self._frames.pop(i, None)
        if i == self.idx:
            self._fill(it)
        self._prefetch(self.idx)
        self.update()

    def _img_loaded(self, url):
        if not url:
            return
        if self.items:
            m = self.meta.get(self.items[self.idx]["url"]) or {}
            if m.get("title_logo") and url == hires(m["title_logo"], "w780"):
                self._layout()
        for i, it in enumerate(self.items):
            if url in self._urls(it):
                self._frames.pop(i, None)
                if i in (self.idx, self._from):
                    self.update()

    def _apply_logo(self, bw):
        """Affiche le logo-titre TMDB (comme OCTO+) ; le titre en texte sinon."""
        it = self.items[self.idx] if self.items else None
        m = (self.meta.get(it["url"]) or {}) if it else {}
        url = hires(m.get("title_logo") or "", "w780") if it else ""
        pm = self.win.images.get(url) if url else None
        if pm is not None and not pm.isNull():
            dpr = _dpr()
            mh = max(70, int(self.height() * 0.20))
            sc = pm.scaled(int(bw * 0.72 * dpr), int(mh * dpr), Qt.AspectRatioMode.KeepAspectRatio,
                           Qt.TransformationMode.SmoothTransformation)
            sc.setDevicePixelRatio(dpr)
            self.logo_l.setPixmap(sc)
            self.logo_l.setFixedHeight(int(sc.height() / dpr) + 6)
            self.logo_l.show()
            self.name.hide()
        else:
            self.logo_l.hide()
            self.name.show()
            self.name.setText(m.get("title") or (it.get("_title") or it["name"] if it else ""))

    def _fill(self, it):
        m = self.meta.get(it["url"]) or {}
        self.name.setText(m.get("title") or it.get("_title") or it["name"])
        kind = "Séries" if it["kind"] == "series" else "Films"
        genre = (m.get("genres") or [None])[0] or pretty_group(it["group"])
        self.sub.setText(f"{kind} · {genre}")
        is_new = it["url"] in self.new_urls
        self.badge.setText("Nouveauté" if is_new else "")
        self.badge.setVisible(is_new)
        self._layout()

    # -- défilement
    def step(self, d):
        if len(self.items) > 1:
            self.show_index(self.idx + d, direction=1 if d > 0 else -1)

    def show_index(self, i, animate=True, direction=None):
        if not self.items:
            return
        i %= len(self.items)
        if i == self.idx and animate:
            return
        if direction is None:
            direction = 1 if i > self.idx else -1
        self._from = self.idx if animate and self.isVisible() else None
        self._dir = direction
        self.idx = i
        self._prefetch(i)
        self._frame(i)
        self._fill(self.items[i])
        if self._from is not None:
            self._t = 0.0
            self._anim.stop()
            self._anim.start()
        else:
            self._t = 1.0
            self._fx.setOpacity(1.0)
        if self._slide.isActive():
            self._slide.start()
        self.update()

    def _on_anim(self, v):
        self._t = float(v)
        self._fx.setOpacity(max(0.0, min(1.0, (self._t - 0.35) / 0.65)))
        self.update()

    def _anim_done(self):
        self._t = 1.0
        self._from = None
        self._fx.setOpacity(1.0)
        self.update()

    def showEvent(self, e):
        super().showEvent(e)
        if len(self.items) > 1:
            self._slide.start()

    def hideEvent(self, e):
        self._slide.stop()
        self._anim.stop()
        self._anim_done()
        super().hideEvent(e)

    # -- mise en page (s'adapte à la taille de la fenêtre)
    def _scale(self):
        return max(0.85, min(1.9, self.width() / 1500.0))

    def resizeEvent(self, e):
        top = self.window().height() if self.window() else 900
        h = int(max(460, min(self.width() * 0.43, top * 0.80, 1100)))
        if self.height() != h:
            self.setFixedHeight(h)
        self._frames.clear()
        self._layout()
        super().resizeEvent(e)

    def _band_h(self):
        """Bandeau du titre : plus haut quand le menu est replié (la barre flottante passe au-dessus du titre)."""
        return 150 if getattr(self.win, "_collapsed", False) else 124

    def _poster_geom(self, ratio):
        """Affiche verticale + bloc de texte : l'ensemble est centré dans la bannière (horizontalement et verticalement)."""
        if not ratio:
            return None
        w, h = self.width(), self.height()
        top = self._band_h()
        area = h - top - 16
        ph = area * 0.84
        pw = ph * ratio
        gap = max(40.0, w * 0.05)
        bw = min(w * 0.46, 1000.0, w - pw - gap - 120)
        if bw < 300:
            return None
        x0 = (w - (pw + gap + bw)) / 2
        cy = top + area / 2 + 8
        return QtCore.QRectF(x0, cy - ph / 2, pw, ph), x0 + pw + gap, bw, cy

    def _layout(self):
        w, h = self.width(), self.height()
        k = self._scale()
        self.page_title.adjustSize()
        self.page_title.move(34, 86 if getattr(self.win, "_collapsed", False) else 38)
        self.name.setStyleSheet(f"font-size:{int(34 * k)}pt;")
        self.sub.setStyleSheet(f"font-size:{12.5 * k:.1f}pt;")
        base = f"font-size:{15 * min(k, 1.4):.1f}pt; padding:{int(14 * min(k, 1.4))}px {int(36 * min(k, 1.4))}px;"
        if self.b_play.property("_basess") != base:
            self.b_play.setProperty("_basess", base)
            self.b_play.setProperty("_pillr", None)
            self.b_play.setStyleSheet(base)
            QtCore.QTimer.singleShot(0, lambda b=self.b_play: round_pill(b))
        g = self._poster_geom(self._ratio.get(self.idx)) if self.items else None
        if g:
            _r, bx, bw, cy = g
            self.box.setFixedWidth(int(bw))
            self._apply_logo(int(bw))
            self.box.adjustSize()
            self.box.move(int(bx), int(cy - (self.box.height() - 40) / 2))
        else:
            bw = int(min(w * 0.60, 1100))
            self.box.setFixedWidth(bw)
            self._apply_logo(bw)
            self.box.adjustSize()
            self.box.move(w // 2 - bw // 2, h - self.box.height() - int(22 * k))
        ay = self._band_h() + (h - self._band_h()) // 2 - 26
        self.b_prev.move(18, ay)
        self.b_next.move(w - 70, ay)

    # -- composition d'une diapositive (mise en cache à la taille exacte, pixels réels)
    def _frame(self, i):
        key = (i, self.width(), self.height(), self._band_h())
        f = self._frames.get(i)
        if f is not None and f[0] == key:
            return f[1]
        it = self.items[i]
        bd_url, poster_url = self._urls(it)
        bd = self.win.images.get(bd_url) if bd_url else None
        poster = self.win.images.get(poster_url) if poster_url else None
        if poster is None and it.get("logo") and it.get("logo") != poster_url:
            poster = self.win.images.get(it["logo"])
        dpr = _dpr()
        w, h = max(1, self.width()), max(1, self.height())
        pm = QtGui.QPixmap(int(w * dpr), int(h * dpr))
        pm.setDevicePixelRatio(dpr)
        pm.fill(QtGui.QColor(BG))
        p = QtGui.QPainter(pm)
        p.setRenderHint(QtGui.QPainter.RenderHint.SmoothPixmapTransform)
        p.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        rect = QtCore.QRectF(0, 0, w, h)
        overlay = None
        src = None
        if bd is not None and not bd.isNull() and bd.width() >= bd.height() * 1.2:
            src = bd
        elif poster is not None and not poster.isNull() and poster.width() >= poster.height() * 1.2:
            src = poster
        if src is not None:
            if self._ratio.pop(i, None) and i == self.idx:
                QtCore.QTimer.singleShot(0, self._layout)
            self._cover(p, rect, src)
        elif poster is not None and not poster.isNull():
            # affiche verticale : fond d'ambiance flouté + affiche nette
            self._cover(p, rect, blurred_pixmap(poster, 10))
            p.fillRect(rect, QtGui.QColor(0, 0, 0, 90))
            ratio = poster.width() / max(1, poster.height())
            if self._ratio.get(i) != ratio:
                self._ratio[i] = ratio
                if i == self.idx:
                    QtCore.QTimer.singleShot(0, self._layout)
            geo = self._poster_geom(ratio)
            if geo is None:
                ph = (h - self._band_h()) * 0.8
                r = QtCore.QRectF(w / 2 - ph * ratio / 2, self._band_h() + ((h - self._band_h()) - ph) / 2, ph * ratio, ph)
            else:
                r = geo[0]
            overlay = (r, poster)
        else:
            g = QtGui.QLinearGradient(0, 0, w, h)
            c = QtGui.QColor(tile_color(it.get("name", "")))
            g.setColorAt(0, c.darker(160))
            g.setColorAt(1, QtGui.QColor(BG))
            p.fillRect(rect, g)
        p.end()
        band = pm.copy(0, 0, pm.width(), int(self._band_h() * dpr))
        band = blurred_pixmap(band, 26)
        band.setDevicePixelRatio(dpr)
        self._frames[i] = (key, pm, band, overlay)
        return pm

    @staticmethod
    def _cover(p, rect, pm):
        s = pm.size().scaled(rect.size().toSize(), Qt.AspectRatioMode.KeepAspectRatioByExpanding)
        target = QtCore.QRectF(rect.center().x() - s.width() / 2, rect.top() - (s.height() - rect.height()) * 0.25,
                               s.width(), s.height())
        p.drawPixmap(target, pm, QtCore.QRectF(pm.rect()))

    def _band(self, i):
        self._frame(i)
        return self._frames[i][2]

    # -- dessin
    def paintEvent(self, e):
        p = QtGui.QPainter(self)
        rect = QtCore.QRectF(self.rect())
        w = rect.width()
        bg = QtGui.QColor(BG)
        p.fillRect(rect, bg)
        if not self.items:
            return
        slides = []
        if self._from is not None and self._t < 1.0:
            off = w * self._t
            slides.append((self._from, -self._dir * off))
            slides.append((self.idx, self._dir * (w - off)))
        else:
            slides.append((self.idx, self._drag))
            if self._drag:
                n = len(self.items)
                slides.append(((self.idx - 1) % n if self._drag > 0 else (self.idx + 1) % n,
                               self._drag - w if self._drag > 0 else self._drag + w))
        for i, x in slides:
            p.drawPixmap(QtCore.QPointF(x, 0), self._frame(i))
        gl = QtGui.QLinearGradient(0, 0, w, 0)
        gl.setColorAt(0, QtGui.QColor(0, 0, 0, 110))
        gl.setColorAt(.45, QtGui.QColor(0, 0, 0, 10))
        gl.setColorAt(1, QtGui.QColor(0, 0, 0, 90))
        p.fillRect(rect, gl)
        gb = QtGui.QLinearGradient(0, 0, 0, rect.height())
        t = QtGui.QColor(bg)
        t.setAlpha(0)
        gb.setColorAt(.50, t)
        gb.setColorAt(.84, QtGui.QColor(bg.red(), bg.green(), bg.blue(), 175))
        gb.setColorAt(1, bg)
        p.fillRect(rect, gb)
        # affiche verticale nette, par-dessus les dégradés
        p.setRenderHint(QtGui.QPainter.RenderHint.SmoothPixmapTransform)
        p.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        for i, x in slides:
            ov = self._frames.get(i, (None,) * 4)[3]
            if ov:
                r = ov[0].translated(x, 0)
                path = QtGui.QPainterPath()
                path.addRoundedRect(r, 16, 16)
                p.save()
                p.setClipPath(path)
                p.drawPixmap(r, ov[1], QtCore.QRectF(ov[1].rect()))
                p.restore()
                p.setPen(QtGui.QPen(QtGui.QColor(255, 255, 255, 45), 1))
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.drawPath(path)
        band = self._band_h()
        p.save()
        p.setClipRect(QtCore.QRectF(0, 0, w, band))
        for i, x in slides:
            p.drawPixmap(QtCore.QPointF(x, 0), self._band(i))
        p.restore()
        p.fillRect(QtCore.QRectF(0, 0, w, band), QtGui.QColor(20, 26, 34, 110))
        p.fillRect(QtCore.QRectF(0, band - 1, w, 1), QtGui.QColor(255, 255, 255, 25))
        n = len(self.items)
        self._dots = []
        if n > 1:
            cx = self.box.x() + self.box.width() / 2
            y = self.box.y() + self.box.height() - 20
            widths = [34 if i == self.idx else 9 for i in range(n)]
            total = sum(widths) + 9 * (n - 1) + 20
            pill = QtCore.QRectF(cx - total / 2, y - 7, total, 22)
            p.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QtGui.QColor(0, 0, 0, 110))
            p.drawRoundedRect(pill, 11, 11)
            x = pill.left() + 10
            for i, dw in enumerate(widths):
                r = QtCore.QRectF(x, y, dw, 8)
                p.setBrush(QtGui.QColor(255, 255, 255, 240 if i == self.idx else 110))
                p.drawRoundedRect(r, 4, 4)
                self._dots.append((r.adjusted(-4, -8, 4, 8), i))
                x += dw + 9

    # -- souris : clic, glisser, molette, flèches
    def enterEvent(self, e):
        if len(self.items) > 1:
            self.b_prev.show()
            self.b_next.show()
            self.b_prev.raise_()
            self.b_next.raise_()
        super().enterEvent(e)

    def leaveEvent(self, e):
        self.b_prev.hide()
        self.b_next.hide()
        super().leaveEvent(e)

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self._press = e.position().x()
        super().mousePressEvent(e)

    def mouseMoveEvent(self, e):
        if self._press is not None and self._from is None and len(self.items) > 1:
            d = e.position().x() - self._press
            if abs(d) > 8 or self._drag:
                self._drag = d
                self.update()
        super().mouseMoveEvent(e)

    def mouseReleaseEvent(self, e):
        drag, self._press, self._drag = self._drag, None, 0.0
        if abs(drag) > 70:
            self.step(-1 if drag > 0 else 1)
            return
        if drag:
            self.update()
            return
        pos = e.position()
        for r, i in self._dots:
            if r.contains(pos):
                self.show_index(i)
                return
        if self.items and pos.y() > 130:
            self.win.open_item(self.items[self.idx])

    def wheelEvent(self, e):
        dx = e.angleDelta().x()
        if abs(dx) > abs(e.angleDelta().y()) and abs(dx) >= 40:
            self.step(1 if dx < 0 else -1)
            e.accept()
            return
        super().wheelEvent(e)

    def _play(self):
        if self.items:
            it = self.items[self.idx]
            if it["kind"] == "movie":
                self.win.play_items([it], 0)
            else:
                self.win.open_item(it)

    def stop(self):
        self._slide.stop()
        self._anim.stop()


def epg_hm(p, k):
    ts = p.get(k + "_ts")
    try:
        return datetime.fromtimestamp(int(ts)).strftime("%H:%M")
    except (TypeError, ValueError):
        return (p.get("start" if k == "start" else "end") or "")[11:16]


def epg_progress(prog):
    try:
        st, en = int(prog.get("start_ts")), int(prog.get("stop_ts"))
        now = time.time()
        return max(0.0, min(1.0, (now - st) / max(1, en - st)))
    except (TypeError, ValueError):
        return 0.0


class PageHeader(QtWidgets.QWidget):
    """Grand titre de page (pages sans bannière)."""

    def __init__(self, win, text, right=None, pushed=False):
        super().__init__()
        self.win = win
        self.pushed = pushed
        h = QtWidgets.QHBoxLayout(self)
        h.setContentsMargins(34, 38, 34, 22)
        h.addWidget(label(text, "pagetitle2"))
        h.addStretch(1)
        if right is not None:
            h.addWidget(right, 0, Qt.AlignmentFlag.AlignVCenter)


    def fit(self):
        """Menu replié : on laisse la place à la barre flottante au-dessus du titre."""
        top = 96 if (getattr(self.win, "_collapsed", False) or self.pushed) else 38
        m = self.layout().contentsMargins()
        if m.top() != top:
            self.layout().setContentsMargins(34, top, 34, 22)

    def showEvent(self, e):
        self.fit()
        super().showEvent(e)

class RichPage(ScrollPage):
    """Base des pages « OCTO+ » : bannière + rangées + acteurs en bas."""

    def __init__(self, win):
        super().__init__()
        self.win = win
        self.hero = None
        self._built = -1
        self._resume_holder = None
        self._resume_kinds = None

    def reset(self):
        self._resume_holder = None
        if self.hero is not None:
            try:
                self.hero.stop()
            except RuntimeError:
                pass
            self.hero = None
        super().reset()

    def body(self, top=18):
        return body_box(self.v, (26, top, 0, 70), 34)

    def cards(self, items, **extra):
        out = []
        for i in items:
            d = {**{k: v for k, v in i.items() if not k.startswith("_")}, "_lib": i,
                 "_title": i.get("_title") or i["name"]}
            d.update(extra)
            out.append(d)
        return out

    def add_row(self, box, title, items, style, subtitle="", see_all=None, on_click=None):
        if not items:
            return None
        row = HRow(self.win, title, items, style, on_click=on_click or self._open_card, see_all=see_all, subtitle=subtitle)
        box.addWidget(row)
        return row

    def _open_card(self, it):
        lib = it.get("_lib")
        if it.get("unavailable") and lib is None:
            self.win.toast(f"« {it.get('_title') or it['name']} » n'est pas disponible dans votre liste.")
            return
        self.win.open_item(lib or it)

    def with_backdrops(self, row, cards):
        for d in cards:
            lib = d.get("_lib")
            if lib is None or lib.get("kind") not in ("movie", "series"):
                continue
            self.win.meta.request(lib, lambda m, d=d, row=row: self._set_backdrop(row, d, m))

    @staticmethod
    def _set_backdrop(row, d, m):
        if not m:
            return
        if m.get("title_logo"):
            d["_tlogo"] = m["title_logo"]
        if d.get("_keep_img"):
            if m.get("poster") and not d.get("_img"):
                d["_img"] = hires(m["poster"], "w780")
            if m.get("genres") and d.get("_subkind"):
                d["sub"] = f"{d['_subkind']} · {m['genres'][0]}"
        elif m.get("backdrop"):
            d["_img"] = m["backdrop"]
        if m.get("title"):
            d["_title"] = m["title"]
        if m.get("genres") and d.get("_subkind"):
            d["sub"] = f"{d['_subkind']} · {m['genres'][0]}"
        try:
            row.refresh(d)
        except RuntimeError:
            pass

    # -- rangées communes
    def refresh_resume(self):
        holder = getattr(self, "_resume_holder", None)
        if holder is None:
            return
        try:
            while holder.count():
                w = holder.takeAt(0).widget()
                if w:
                    w.deleteLater()
        except RuntimeError:
            return
        self._resume_fill(holder, self._resume_kinds)

    def resume_row(self, box, kinds=None):
        holder = QtWidgets.QVBoxLayout()
        holder.setContentsMargins(0, 0, 0, 0)
        box.addLayout(holder)
        self._resume_holder, self._resume_kinds = holder, kinds
        return self._resume_fill(holder, kinds)

    def _resume_fill(self, box, kinds=None):
        items = self.win.continue_items()
        if kinds:
            items = [i for i in items if (i.get("kind") in kinds) or (i.get("_series") and "series" in kinds)]
        for d in items:
            d["resume"] = True
            d["remain"] = d.get("_remain", "")
        row = self.add_row(box, "Reprendre", items, "resume", on_click=self.win.resume_entry)
        if row:
            for d in items:
                if d.get("_lib"):
                    self.win.meta.request(d["_lib"], lambda m, d=d, row=row: self._set_backdrop(row, d, m))
        return row

    def channels_row(self, box, title, chans, subtitle="", see_all=None):
        cards = []
        for c in chans:
            name = c.get("_title") or c["name"]
            cards.append({**{k: v for k, v in c.items() if not k.startswith("_")}, "_lib": c, "overlay": name,
                          "_title": name, "sub": ""})
        if not cards:
            return None
        row = HRow(self.win, title, cards, "wide", subtitle=subtitle, see_all=see_all,
                   on_click=lambda it, l=cards: self.win.play_items([x["_lib"] for x in l], l.index(it)))
        box.addWidget(row)
        for d in cards[:14]:
            if d["_lib"].get("stream_id"):
                self.win.fetch_epg(d["_lib"], lambda _it, progs, d=d, row=row: self._epg(row, d, progs))
        return row

    @staticmethod
    def _epg(row, d, progs):
        if not progs:
            return
        now = progs[0]
        d["_title"] = now["title"] or d["_title"]
        d["progress"] = epg_progress(now) or 0.02
        try:
            row.refresh(d)
        except RuntimeError:
            pass

    # -- rangées TMDB rapprochées de votre liste (mises en cache pour la journée)
    def tmdb_row(self, box, title, list_name, compute, style, kind, see_all_title=None, min_items=3,
                 only_available=True, extra=None):
        key = tmdb_key_of(self.win.cfg)
        if not key:
            return False
        holder = QtWidgets.QVBoxLayout()
        holder.setContentsMargins(0, 0, 0, 0)
        box.addLayout(holder)

        def done(res):
            cards = self._match_cards(res or [], style, only_available)
            if len(cards) < min_items:
                return
            see = (lambda c=cards: self.win.open_collection(see_all_title or title, c)) if see_all_title is not False else None
            try:
                row = HRow(self.win, title, cards[:40], style, on_click=self._open_card, see_all=see)
                holder.addWidget(row)
                self.with_backdrops(row, [d for d in cards[:40] if d.get("_lib")])
            except RuntimeError:
                pass
        self.win.meta.request_list(list_name, lambda: compute(key, self.win.cfg.get("lang", "fr-FR")), done)
        return True

    def _match_cards(self, res, style, only_available=True):
        cards, seen = [], set()
        for r in res:
            lib = self.win.lib.match_title(r["kind"], r["title"], r["original_title"], r["year"])
            if only_available and lib is None:
                continue
            if lib is not None and lib["url"] in seen:
                continue
            if lib is not None:
                seen.add(lib["url"])
            d = {"name": r["title"], "_title": r["title"], "logo": r["poster"], "kind": r["kind"],
                 "url": lib["url"] if lib else f"tmdb:{r['kind']}:{r['tmdb_id']}", "_lib": lib,
                 "unavailable": lib is None, "group": (lib or {}).get("group", "")}
            if style in ("land", "big"):
                d["_img"] = r["backdrop"] or r["poster"]
            if style in ("posterbig", "postersm", "coeur"):
                d["_keep_img"] = True
                d["_img"] = hires(r["poster"], "w500") if r["poster"] else ""
            cards.append(d)
        return cards

    def providers_row(self, box, kind):
        key = tmdb_key_of(self.win.cfg)
        if not key:
            return
        tk = "movie" if kind == "movie" else "tv"
        holder = QtWidgets.QVBoxLayout()
        holder.setContentsMargins(0, 0, 0, 0)
        box.addLayout(holder)

        def done(logos):
            logos = logos or {}
            cards = [{"name": n, "logo": logos.get(pid) or logos.get(str(pid)) or "", "kind": "provider",
                      "url": f"provider:{pid}", "pid": pid} for pid, n in PROVIDERS]
            try:
                holder.addWidget(HRow(self.win, "En streaming sur", cards, "provider",
                                      on_click=lambda it: self._open_provider(it, tk)))
            except RuntimeError:
                pass
        self.win.meta.request_list(f"providers-{tk}", lambda: {k: v for k, v in tmdb_provider_logos(
            key, self.win.cfg.get("lang", "fr-FR"), tk).items()}, done)

    def _open_provider(self, it, tk):
        key = tmdb_key_of(self.win.cfg)
        lang = self.win.cfg.get("lang", "fr-FR")
        self.win.open_collection(it["name"], None, loader=(
            f"prov-{tk}-{it['pid']}",
            lambda: tmdb_discover(key, lang, tk, pages=6, with_watch_providers=it["pid"], watch_region="FR",
                                  sort_by="popularity.desc")))

    def studios_row(self, box):
        key = tmdb_key_of(self.win.cfg)
        if not key:
            return
        cards = [{"name": n, "kind": "studio", "url": f"studio:{ids}", "ids": ids, "c1": c1, "c2": c2, "logo": ""}
                 for n, ids, c1, c2 in STUDIOS]
        lang = self.win.cfg.get("lang", "fr-FR")

        def open_studio(it):
            self.win.open_collection(it["name"], None, loader=(
                f"studio-{it['ids']}", lambda: tmdb_discover(key, lang, "movie", pages=6, with_companies=it["ids"],
                                                             sort_by="popularity.desc")))
        self.add_row(box, "", cards, "studio", on_click=open_studio)

    def tiles_row(self, box, kind):
        cats = self.win.category_items(kind, 24, special=True)
        if len(cats) > 1:
            self.add_row(box, "", cats, "tile", on_click=self.win.open_category)

    def actors_row(self, box, title="Les acteurs populaires", subtitle=""):
        key = tmdb_key_of(self.win.cfg)
        if not key:
            return
        holder = QtWidgets.QVBoxLayout()
        box.addLayout(holder)

        def done(people):
            if not people:
                return
            cards = [{"name": x["name"], "logo": x["photo"], "kind": "person", "tmdb_id": x["tmdb_id"], "sub": ""}
                     for x in people[:30]]
            try:
                holder.addWidget(HRow(self.win, title, cards, "actor2", on_click=self.win.open_person,
                                      subtitle=subtitle, see_all=lambda: self.win.go_root("search")))
            except RuntimeError:
                pass
        self.win.meta.request_list("people", lambda: tmdb_popular_people(key, self.win.cfg.get("lang", "fr-FR")), done)

    def trending_rows(self, box, kind, title, style, only_available=False, subtitle=""):
        """Tendances TMDB de la semaine, rapprochées de votre liste."""
        key = tmdb_key_of(self.win.cfg)
        if not key:
            return False
        holder = QtWidgets.QVBoxLayout()
        box.addLayout(holder)
        tk = "movie" if kind == "movie" else "tv"

        def done(res):
            if not res:
                return
            cards = []
            for r in res:
                lib = self.win.lib.match_title(r["kind"], r["title"], r["original_title"], r["year"])
                if only_available and lib is None:
                    continue
                d = {"name": r["title"], "_title": r["title"], "logo": r["poster"], "kind": r["kind"],
                     "url": lib["url"] if lib else f"tmdb:{r['kind']}:{r['tmdb_id']}", "_lib": lib,
                     "unavailable": lib is None, "caption": r["title"] if style == "cover" else ""}
                if style == "land":
                    d["_img"] = r["backdrop"] or r["poster"]
                cards.append(d)
            if not cards:
                return
            try:
                holder.addWidget(HRow(self.win, title, cards, "coverc" if style == "cover" else style,
                                      subtitle=subtitle, on_click=self._open_card))
            except RuntimeError:
                pass
        self.win.meta.request_list(f"trend-{tk}", lambda: tmdb_trending(key, self.win.cfg.get("lang", "fr-FR"), tk), done)
        return True


class CollectionPage(ScrollPage):
    """Grille d'affiches (plateforme, studio, « voir tout »)."""

    def __init__(self, win, title, cards=None, loader=None):
        super().__init__()
        self.win = win
        self.content.setObjectName("page")
        self.v.addWidget(PageHeader(win, title, pushed=True))
        box = body_box(self.v, (26, 0, 26, 40), 12)
        self.info = label("Chargement…", "rowsub")
        box.addWidget(self.info)
        self.grid = CardView(win, "posterbig", horizontal=False)
        self.grid.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.grid.item_clicked.connect(self._click)
        box.addWidget(self.grid, 1)
        if cards is not None:
            self._show(cards)
        elif loader:
            name, fn = loader
            win.meta.request_list(name, fn, self._loaded)

    def _loaded(self, res):
        try:
            cards = RichPage._match_cards(self, res or [], "posterbig", True)
            self._show(cards)
        except RuntimeError:
            pass

    def _show(self, cards):
        for d in cards:
            d["_keep_img"] = True
            if d.get("_lib") and not d.get("_img"):
                d["_img"] = d.get("logo") or ""
        self.grid.set_items(cards)
        n = len(cards)
        self.info.setText(f"{n} titre(s) disponible(s) dans votre liste" if n else
                          "Aucun titre de cette sélection n'est disponible dans votre liste pour le moment.")
        QtCore.QTimer.singleShot(0, self._fit)

    def _fit(self):
        g = self.grid
        cols = max(1, g.viewport().width() // max(1, g.gridSize().width()))
        rows = (g.model_.rowCount() + cols - 1) // cols
        g.setFixedHeight(rows * g.gridSize().height() + 12)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        QtCore.QTimer.singleShot(0, self._fit)

    def _click(self, it):
        if it.get("_lib"):
            self.win.open_item(it["_lib"])
        else:
            self.win.toast(f"« {it.get('_title') or it['name']} » n'est pas disponible dans votre liste.")


class HomePage(RichPage):
    TITLE = "Accueil"

    def refresh_continue(self):
        pass

    def rebuild(self):
        self.reset()
        win, lib = self.win, self.win.lib
        if not lib.items:
            self.v.addWidget(PageHeader(win, self.TITLE))
            box = body_box(self.v, (48, 60, 48, 40))
            box.addWidget(label("Bienvenue 👋", "herotitle"))
            box.addWidget(label("Ajoutez une liste M3U (lien ou fichier) ou un compte Xtream Codes pour commencer.\n"
                                "Vous pouvez aussi glisser un fichier .m3u directement sur cette fenêtre.", "overview"))
            brow = QtWidgets.QHBoxLayout()
            brow.setSpacing(12)
            b = button("＋  Lien M3U ou compte Xtream", "whitepill", win.add_source)
            brow.addWidget(b)
            fb = button("📄  Ouvrir un fichier M3U", "glasspill", win.add_file_source)
            fb.setMinimumHeight(b.sizeHint().height())
            brow.addWidget(fb)
            brow.addStretch(1)
            box.addLayout(brow)
            box.addStretch(1)
            return
        news = lib.recent("movie", 10) + lib.recent("series", 8)
        pool = [i for i in news if i.get("logo")]
        random.shuffle(pool)
        self.hero = HeroCarousel(win, self.TITLE, pool[:7], [i["url"] for i in news])
        self.v.addWidget(self.hero)
        if not pool:
            self.v.addWidget(PageHeader(win, self.TITLE))
        box = self.body()
        self.resume_row(box)
        chans = win.trending_channels(24)
        self.channels_row(box, "Les chaînes du moment", chans, "Les chaînes les plus regardées actuellement",
                          see_all=lambda: win.go_root("live"))
        self.tmdb_row(box, "Top de la semaine", "trend3-movie", lambda k, l: tmdb_trending_all(k, l, "movie"),
                      "land", "movie")
        self.add_row(box, "Films en ce moment", self.cards(lib.recent("movie", 40)), "postersm",
                     see_all=lambda: win.browse("movie"))
        self.add_row(box, "Séries en ce moment", self.cards(lib.recent("series", 40)), "postersm",
                     see_all=lambda: win.browse("series"))
        self.tiles_row(box, "movie")
        big = self.cards(sorted(news, key=lambda i: -int(i.get("added") or 0) if str(i.get("added") or "0").isdigit() else 0)[:14],
                         badge="Nouveauté")
        for d in big:
            d["_subkind"] = "Séries" if d["kind"] == "series" else "Films"
            d["sub"] = f"{d['_subkind']} · {pretty_group(d['group'])}"
        row = self.add_row(box, f"Nouveautés sur {APP_TITLE}", big, "big")
        if row:
            self.with_backdrops(row, big)
        self.tiles_row(box, "series")
        self.actors_row(box)
        box.addStretch(1)


class MediaPage(RichPage):
    """Page Films ou Séries."""

    def __init__(self, win, kind):
        super().__init__(win)
        self.kind = kind
        self.TITLE = "Films" if kind == "movie" else "Séries"

    def rebuild(self, **_kw):
        self.reset()
        win, lib, kind = self.win, self.win.lib, self.kind
        pool_all = lib.by_kind.get(kind) or []
        if not pool_all:
            self.v.addWidget(PageHeader(win, self.TITLE))
            box = body_box(self.v, (48, 30, 48, 40))
            box.addWidget(label("Rien ici pour le moment.", "empty"))
            box.addStretch(1)
            return
        recent = lib.recent(kind, 40)
        pool = [i for i in recent[:20] if i.get("logo")]
        random.shuffle(pool)
        self.hero = HeroCarousel(win, self.TITLE, pool[:7], [i["url"] for i in recent[:12]])
        self.v.addWidget(self.hero)
        box = self.body()
        self.resume_row(box, kinds=(kind,))
        sub_kind = "Séries" if kind == "series" else "Films"
        tk = "movie" if kind == "movie" else "tv"
        year = datetime.now().year
        # Top de la semaine (tendances TMDB présentes dans votre liste)
        if not self.tmdb_row(box, "Top de la semaine", f"trend3-{tk}", lambda k, l: tmdb_trending_all(k, l, tk),
                             "land", kind):
            top = sorted(pool_all, key=lambda i: -float(i.get("_rating") or 0))[:14]
            cards = self.cards(top)
            row = self.add_row(box, "Top de la semaine", cards, "land")
            if row:
                self.with_backdrops(row, cards)
        self.tiles_row(box, kind)
        news = self.cards(recent[:14], badge="Nouveauté", _subkind=sub_kind)
        for d in news:
            d["sub"] = f"{sub_kind} · {pretty_group(d['group'])}"
        row = self.add_row(box, f"Nouveautés sur {APP_TITLE}", news, "big", see_all=lambda: win.browse(kind))
        if row:
            self.with_backdrops(row, news)
        self.providers_row(box, kind)
        date_key = "primary_release_year" if tk == "movie" else "first_air_date_year"
        sort_hit = "revenue.desc" if tk == "movie" else "popularity.desc"
        self.tmdb_row(box, "Les plus gros succès de l'année", f"hits-{tk}-{year}",
                      lambda k, l: tmdb_discover(k, l, tk, pages=4, sort_by=sort_hit, **{date_key: year})
                      + tmdb_discover(k, l, tk, pages=3, sort_by=sort_hit, **{date_key: year - 1}),
                      "posterbig", kind)
        self.tmdb_row(box, "Top du mois", f"month-{tk}",
                      lambda k, l: tmdb_trending_all(k, l, tk, pages=2, window="day")
                      + tmdb_discover(k, l, tk, pages=4, sort_by="popularity.desc"),
                      "postersm", kind)
        rated = [i for i in pool_all if float(i.get("_rating") or 0) >= 7.0]
        random.shuffle(rated)
        fav = self.cards((rated or random.sample(pool_all, min(12, len(pool_all))))[:12], _subkind=sub_kind,
                         _keep_img=True)
        for d in fav:
            d["sub"] = f"{sub_kind} · {pretty_group(d['group'])}"
            d["_img"] = ""
        row = self.add_row(box, f"Coups de cœur {APP_TITLE}", fav, "coeur")
        if row:
            self.with_backdrops(row, fav)
        if kind == "movie":
            self.studios_row(box)
        for g, _n in Counter(i["group"] for i in pool_all).most_common(3):
            items = self.cards([i for i in pool_all if i["group"] == g][:40])
            self.add_row(box, pretty_group(g), items, "postersm", see_all=lambda gg=g: win.browse(kind, group=gg))
        self.actors_row(box)
        box.addStretch(1)


class LivePage(RichPage):
    TITLE = "Chaînes TV"

    def rebuild(self, **_kw):
        self.reset()
        win, lib = self.win, self.win.lib
        self.v.addWidget(PageHeader(win, self.TITLE, button("Toutes les chaînes", "glasspill", lambda: win.browse("live"))))
        live = lib.by_kind.get("live") or []
        if not live:
            box = body_box(self.v, (48, 30, 48, 40))
            box.addWidget(label("Aucune chaîne pour le moment.", "empty"))
            box.addStretch(1)
            return
        box = self.body(6)
        chans = win.trending_channels(24)
        self.channels_row(box, "Les chaînes du moment", chans, "Les chaînes les plus regardées actuellement",
                          see_all=lambda: win.browse("live"))
        self.upcoming_holder = QtWidgets.QVBoxLayout()
        box.addLayout(self.upcoming_holder)
        self._upcoming = []
        self._pending = 0
        for c in chans[:18]:
            if c.get("stream_id"):
                self._pending += 1
                win.fetch_epg(c, self._got_upcoming)
        shortcuts = [
            {"kind": "category", "special": True, "name": "Chaînes par catégories", "_act": "cats"},
            {"kind": "category", "name": "Par pays", "_act": "countries"},
            {"kind": "category", "name": "Mes chaînes favorites", "_act": "favs"},
            {"kind": "category", "name": "Toutes les chaînes", "_act": "all"},
        ]
        self.add_row(box, "", shortcuts, "tile", on_click=self._shortcut)
        cats = win.category_items("live", 40)
        tiles = [dict(c, icon=cat_emoji(c["name"])) for c in cats]
        self.add_row(box, "Catégories", tiles, "tilebig", on_click=win.open_category)
        for g, _n in Counter(i["group"] for i in live).most_common(6):
            items = [i for i in live if i["group"] == g][:30]
            self.channels_row(box, pretty_group(g), items, see_all=lambda gg=g: win.browse("live", group=gg))
        box.addStretch(1)

    def _shortcut(self, it):
        act = it.get("_act")
        if act == "cats":
            self.win.go_root("categories")
            self.win.pages["categories"].show_kind("live")
        elif act == "favs":
            self.win.go_root("favorites")
        else:
            self.win.browse("live")

    def _got_upcoming(self, item, progs):
        now = time.time()
        for pr in progs[1:]:
            try:
                st = int(pr.get("start_ts"))
            except (TypeError, ValueError):
                continue
            if st > now and datetime.fromtimestamp(st).date() == datetime.now().date():
                self._upcoming.append((st, item, pr))
                break
        self._pending -= 1
        if self._pending <= 0 and self._upcoming:
            self._upcoming.sort(key=lambda x: x[0])
            cards = []
            for st, c, pr in self._upcoming[:16]:
                cards.append({**{k: v for k, v in c.items() if not k.startswith("_")}, "_lib": c,
                              "_title": pr["title"], "time": datetime.fromtimestamp(st).strftime("%H:%M"),
                              "sub": c.get("_title") or c["name"]})
            try:
                self.upcoming_holder.addWidget(HRow(self.win, "À ne pas manquer aujourd'hui", cards, "wide",
                                                    on_click=lambda it: self.win.play_items([it["_lib"]], 0)))
            except RuntimeError:
                pass


# --------------------------------------------------------------------------- #
#  Parcourir (TV / Films / Séries)
# --------------------------------------------------------------------------- #
class BrowsePage(QtWidgets.QWidget):
    has_own_back = True

    KIND_TITLES = {"live": "Chaînes TV", "movie": "Films", "series": "Séries"}

    def __init__(self, win, kind):
        super().__init__()
        self.win, self.kind = win, kind
        self.pool, self.subset, self.shown = [], [], []

        left = QtWidgets.QWidget()
        left.setObjectName("filters")
        left.setFixedWidth(250)
        ll = QtWidgets.QVBoxLayout(left)
        ll.setContentsMargins(12, 22, 8, 12)
        ll.setSpacing(4)
        ll.addWidget(label("PAYS", "h"))
        self.countries = QtWidgets.QListWidget()
        self.countries.currentRowChanged.connect(lambda _r: self._refresh_groups())
        ll.addWidget(self.countries, 2)
        ll.addWidget(label("CATÉGORIES", "h"))
        self.groups = QtWidgets.QListWidget()
        self.groups.currentRowChanged.connect(lambda _r: self._apply())
        ll.addWidget(self.groups, 3)

        right = QtWidgets.QWidget()
        rl = QtWidgets.QVBoxLayout(right)
        rl.setContentsMargins(24, 22, 16, 0)
        rl.setSpacing(10)
        top = QtWidgets.QHBoxLayout()
        top.addWidget(button("‹  Retour", "glasspill", win.back))
        top.addSpacing(14)
        self.title = label(self.KIND_TITLES[kind], "pagetitle")
        self.count = label("", "meta")
        top.addWidget(self.title)
        top.addSpacing(10)
        top.addWidget(self.count, 0, Qt.AlignmentFlag.AlignBottom)
        top.addStretch(1)
        self.filter = QtWidgets.QLineEdit()
        self.filter.setPlaceholderText("Filtrer…")
        self.filter.setClearButtonEnabled(True)
        self.filter.setFixedWidth(240)
        self._t = QtCore.QTimer(self, singleShot=True, interval=220)
        self._t.timeout.connect(self._apply)
        self.filter.textChanged.connect(lambda _x: self._t.start())
        self.sort = QtWidgets.QComboBox()
        self.sort.addItems(["Ordre du fournisseur", "A → Z", "Récemment ajoutés", "Mieux notés"])
        self.sort.currentIndexChanged.connect(lambda _i: self._apply())
        if kind == "live":
            self.sort.setVisible(False)
        top.addWidget(self.filter)
        top.addWidget(self.sort)
        rl.addLayout(top)
        self.grid = CardView(win, "channel" if kind == "live" else "poster")
        self.grid.item_clicked.connect(self._clicked)
        self.empty = label("", "empty")
        self.empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.stack = QtWidgets.QStackedWidget()
        self.stack.addWidget(self.grid)
        self.stack.addWidget(self.empty)
        rl.addWidget(self.stack, 1)

        h = QtWidgets.QHBoxLayout(self)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(0)
        h.addWidget(left)
        h.addWidget(right, 1)

    @staticmethod
    def _add(lw, text, data):
        it = QtWidgets.QListWidgetItem(text)
        it.setData(Qt.ItemDataRole.UserRole, data)
        lw.addItem(it)

    @staticmethod
    def _cur(lw):
        it = lw.currentItem()
        return it.data(Qt.ItemDataRole.UserRole) if it else None

    @staticmethod
    def _select(lw, data):
        for i in range(lw.count()):
            if lw.item(i).data(Qt.ItemDataRole.UserRole) == data:
                lw.setCurrentRow(i)
                return
        if lw.count():
            lw.setCurrentRow(0)

    def rebuild(self, country=None, group=None):
        self.pool = self.win.lib.by_kind[self.kind]
        counts = Counter(i["country"] for i in self.pool)
        prev = country or self._cur(self.countries)
        lw = self.countries
        lw.blockSignals(True)
        lw.clear()
        self._add(lw, f"🌍  Tous les pays   {len(self.pool)}", "*")
        for code in sorted(counts, key=lambda c: (c == "ZZ", norm(country_name(c)))):
            self._add(lw, f"{country_name(code)}   {counts[code]}", code)
        self._select(lw, prev if prev else "*")
        lw.blockSignals(False)
        self._refresh_groups(group)

    def _refresh_groups(self, group=None):
        code = self._cur(self.countries) or "*"
        self.subset = self.pool if code == "*" else [i for i in self.pool if i["country"] == code]
        prev = group or self._cur(self.groups)
        counts = Counter(i["group"] for i in self.subset)
        lw = self.groups
        lw.blockSignals(True)
        lw.clear()
        self._add(lw, f"Toutes   {len(self.subset)}", "*")
        order = list(dict.fromkeys(i["group"] for i in self.subset))
        for g in order:
            self._add(lw, f"{g}   {counts[g]}", g)
        self._select(lw, prev)
        lw.blockSignals(False)
        self._apply()

    def _apply(self):
        grp = self._cur(self.groups) or "*"
        res = self.subset if grp == "*" else [i for i in self.subset if i["group"] == grp]
        q = norm(self.filter.text().strip())
        if q:
            terms = q.split()
            res = [i for i in res if all(t in i["_q"] for t in terms)]
        s = self.sort.currentIndex()
        if s == 1:
            res = sorted(res, key=lambda i: norm(i.get("_title") or i["name"]))
        elif s == 2:
            res = sorted(res, key=lambda i: -int(i.get("added") or 0) if str(i.get("added") or "0").isdigit() else 0)
        elif s == 3:
            res = sorted(res, key=lambda i: -float(i.get("_rating") or 0))
        self.shown = res
        self.grid.set_items(res)
        self.count.setText(f"{len(res):,} titres".replace(",", " ") if self.kind != "live"
                           else f"{len(res):,} chaînes".replace(",", " "))
        if res:
            self.stack.setCurrentIndex(0)
        else:
            self.empty.setText("Aucun résultat." if self.pool else "Rien ici pour le moment.")
            self.stack.setCurrentIndex(1)

    def _clicked(self, it):
        if self.kind == "live":
            try:
                idx = self.shown.index(it)
            except ValueError:
                idx = 0
            self.win.play_items(self.shown, idx)
        else:
            self.win.open_item(it)


# --------------------------------------------------------------------------- #
#  Fiche film / série
# --------------------------------------------------------------------------- #
class EpisodeRow(ClickFrame):
    def __init__(self, win, ep, fallback_img, progress):
        super().__init__()
        self.setObjectName("episode")
        h = QtWidgets.QHBoxLayout(self)
        h.setContentsMargins(10, 10, 14, 10)
        h.setSpacing(18)
        thumb_box = QtWidgets.QWidget()
        thumb_box.setFixedSize(240, 135)
        self.thumb = ImageLabel(win.images, 240, 135, radius=8, parent=thumb_box)
        self.thumb.set_image(ep.get("still"), f"E{ep['num']}", fallback_img)
        play = QtWidgets.QLabel("▶", thumb_box)
        play.setObjectName("playbadge")
        play.setFixedSize(40, 40)
        play.setAlignment(Qt.AlignmentFlag.AlignCenter)
        play.move(100, 47)
        if progress:
            bar = QtWidgets.QProgressBar(thumb_box)
            bar.setObjectName("thin")
            bar.setTextVisible(False)
            bar.setRange(0, 100)
            bar.setValue(int(min(1, progress) * 100))
            bar.setGeometry(8, 124, 224, 4)
        h.addWidget(thumb_box, 0, Qt.AlignmentFlag.AlignTop)
        v = QtWidgets.QVBoxLayout()
        v.setSpacing(4)
        t = QtWidgets.QHBoxLayout()
        t.addWidget(label(f"{ep['num']}.  {ep['name']}", "eptitle", wrap=True), 1)
        if progress and progress >= 0.95:
            t.addWidget(label("✓ Vu", "seen"), 0, Qt.AlignmentFlag.AlignTop)
        v.addLayout(t)
        bits = [fmt_runtime(ep.get("runtime")), fmt_date(ep.get("air_date") or ""),
                f"★ {ep['rating']}" if ep.get("rating") and str(ep["rating"]) not in ("0", "0.0") else ""]
        m = " · ".join(b for b in bits if b)
        if m:
            v.addWidget(label(m, "meta"))
        plot = ep.get("plot") or ""
        if plot:
            pl = label(plot if len(plot) < 330 else plot[:327].rsplit(" ", 1)[0] + "…", "epplot", wrap=True)
            v.addWidget(pl)
        v.addStretch(1)
        h.addLayout(v, 1)


class DetailPage(ScrollPage):
    def __init__(self, win, item):
        super().__init__()
        self.win, self.item = win, item
        self.series = item["kind"] == "series"
        self.meta = None
        self.season_idx = 0
        self.content.setObjectName("page")

        self.hero = Backdrop(win.images)
        self.hero.setMinimumHeight(540)
        self.hero.set_images("", item.get("logo"))
        hl = QtWidgets.QHBoxLayout(self.hero)
        hl.setContentsMargins(48, 70, 48, 26)
        hl.setSpacing(36)
        self.poster = ImageLabel(win.images, 240, 360, radius=14)
        self.poster.set_image(item.get("logo"), initials(item.get("_title") or item["name"]))
        hl.addWidget(self.poster, 0, Qt.AlignmentFlag.AlignBottom)
        info = QtWidgets.QVBoxLayout()
        info.setSpacing(10)
        info.addStretch(1)
        self.kicker = label("SÉRIE" if self.series else "FILM", "kicker")
        self.title = label(item.get("_title") or item["name"], "herotitle", wrap=True)
        self.tagline = label("", "tagline", wrap=True)
        self.tagline.hide()
        self.meta_l = label(" · ".join(x for x in (item.get("_year"), item["group"]) if x), "meta")
        self.chips = QtWidgets.QHBoxLayout()
        self.chips.setSpacing(6)
        self.overview = label("Chargement des informations…", "overview", wrap=True)
        self.overview.setMaximumWidth(820)
        self.overview.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.crew = label("", "crew", wrap=True)
        self.crew.setMaximumWidth(820)
        self.crew.hide()
        btns = QtWidgets.QHBoxLayout()
        btns.setSpacing(10)
        self.b_play = button("▶  Lecture", "primary", self._play)
        self.b_restart = button("↺  Depuis le début", "glass", lambda: self._play(restart=True))
        self.b_trailer = button("🎬  Bande-annonce", "glass", self._trailer)
        self.b_fav = button("", "glass", self._fav)
        self.b_dl = button("⬇  Télécharger", "glass", self._download)
        self._ep_btns = {}
        win.downloads.changed.connect(self._dl_changed)
        self.b_restart.hide()
        self.b_trailer.hide()
        for b in (self.b_play, self.b_restart, self.b_trailer, self.b_fav, self.b_dl):
            btns.addWidget(b)
        self._dl_changed("")
        btns.addStretch(1)
        for w in (self.kicker, self.title, self.tagline, self.meta_l):
            info.addWidget(w)
        info.addLayout(self.chips)
        info.addWidget(self.overview)
        info.addWidget(self.crew)
        info.addSpacing(6)
        info.addLayout(btns)
        hl.addLayout(info, 1)
        self.v.addWidget(self.hero)

        self.body = body_box(self.v, (44, 22, 36, 48), 30)
        if self.series:
            sec = QtWidgets.QVBoxLayout()
            sec.setSpacing(12)
            head = QtWidgets.QHBoxLayout()
            head.addWidget(label("Épisodes", "rowtitle"))
            head.addStretch(1)
            sec.addLayout(head)
            self.season_bar = QtWidgets.QHBoxLayout()
            self.season_bar.setSpacing(8)
            sb_w = QtWidgets.QWidget()
            sb_w.setLayout(self.season_bar)
            self.season_scroll = QtWidgets.QScrollArea()
            self.season_scroll.setWidget(sb_w)
            self.season_scroll.setWidgetResizable(True)
            self.season_scroll.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
            self.season_scroll.setFixedHeight(50)
            self.season_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            sec.addWidget(self.season_scroll)
            self.eps_box = QtWidgets.QVBoxLayout()
            self.eps_box.setSpacing(6)
            self.eps_holder = QtWidgets.QWidget()
            self.eps_holder.setLayout(self.eps_box)
            sec.addWidget(self.eps_holder)
            self.eps_loading = label("Chargement des saisons…", "meta")
            self.eps_box.addWidget(self.eps_loading)
            self.body.addLayout(sec)
        self.cast_holder = QtWidgets.QVBoxLayout()
        self.body.addLayout(self.cast_holder)
        similar = [i for i in win.lib.by_kind[item["kind"]] if i["group"] == item["group"] and i is not item]
        if similar:
            random.shuffle(similar)
            self.body.addWidget(HRow(win, "Vous aimerez aussi", similar[:30], "poster"))
        self.body.addStretch(1)
        self._update_fav()
        self.refresh_progress()
        win.meta.request(item, self._on_meta)

    # -- données
    def _on_meta(self, m):
        if m is None:
            self.overview.setText("Aucune information disponible pour ce titre.")
            if self.series:
                self.eps_loading.setText("Impossible de charger les épisodes.")
            return
        self.meta = m
        self.title.setText(m.get("title") or self.item["name"])
        if m.get("tagline"):
            self.tagline.setText(f"« {m['tagline']} »")
            self.tagline.show()
        n_seasons = len(m.get("seasons") or [])
        bits = [m.get("year"),
                fmt_runtime(m.get("runtime")) if not self.series else
                (f"{n_seasons} saison{'s' if n_seasons > 1 else ''}" if n_seasons else ""),
                f"★ {m['rating']}" if m.get("rating") and str(m["rating"]) not in ("0", "0.0") else "",
                pretty_group(self.item["group"])]
        self.meta_l.setText("   ·   ".join(b for b in bits if b))
        while self.chips.count():
            w = self.chips.takeAt(0).widget()
            if w:
                w.deleteLater()
        if m.get("age"):
            self.chips.addWidget(label(str(m["age"]) if not str(m["age"]).isdigit() else f"{m['age']}+", "agechip"))
        for g in (m.get("genres") or [])[:5]:
            self.chips.addWidget(label(g, "chip"))
        self.chips.addStretch(1)
        self.overview.setText(m.get("overview") or "Pas de résumé disponible.")
        crew = []
        if m.get("director"):
            crew.append(f"<span style='color:#8b91a3'>{'Création' if self.series else 'Réalisation'} :</span> {m['director']}")
        if m.get("original_title") and m["original_title"] != m.get("title"):
            crew.append(f"<span style='color:#8b91a3'>Titre original :</span> {m['original_title']}")
        if crew:
            self.crew.setText("<br>".join(crew))
            self.crew.show()
        self.b_trailer.setVisible(bool(m.get("trailer")))
        self.hero.set_images(m.get("backdrop"), m.get("poster") or self.item.get("logo"))
        self.poster.set_image(m.get("poster") or self.item.get("logo"),
                              initials(m.get("title") or self.item["name"]), self.item.get("logo"))
        cast = [{"name": c["name"], "logo": c.get("photo") or "", "sub": c.get("role") or "",
                 "kind": "person", "tmdb_id": c.get("tmdb_id")} for c in m.get("cast") or [] if c.get("name")]
        if cast:
            self.cast_holder.addWidget(HRow(self.win, "Distribution", cast, "actor", on_click=self.win.open_person))
        if self.series:
            self._build_seasons()
        self.refresh_progress()

    def _build_seasons(self):
        seasons = self.meta.get("seasons") or []
        self.eps_loading.setVisible(not seasons)
        if not seasons:
            self.eps_loading.setText("Aucun épisode disponible.")
            return
        self.season_btns = []
        grp = QtWidgets.QButtonGroup(self)
        grp.setExclusive(True)
        start = self._resume_season_index()
        for i, s in enumerate(seasons):
            name = s.get("name") or f"Saison {s['number']}"
            if not re.search(r"\d", name) and s["number"]:
                name = f"{name} {s['number']}"
            b = button(f"{name}  ·  {len(s['episodes'])}", "seasonchip")
            b.setCheckable(True)
            grp.addButton(b)
            b.clicked.connect(lambda _c=False, j=i: self._show_season(j))
            self.season_bar.addWidget(b)
            self.season_btns.append(b)
        self.season_bar.addStretch(1)
        self._show_season(start)

    def _show_season(self, i):
        self.season_idx = i
        if hasattr(self, "season_btns") and i < len(self.season_btns):
            self.season_btns[i].setChecked(True)
        while self.eps_box.count():
            w = self.eps_box.takeAt(0).widget()
            if w and w is not self.eps_loading:
                w.deleteLater()
        self.eps_loading.hide()
        self._ep_gen = getattr(self, "_ep_gen", 0) + 1
        self._add_eps(i, 0, self._ep_gen)

    def _add_eps(self, i, start, gen):
        """Ajoute les épisodes par paquets pour ne jamais figer l'interface."""
        if gen != self._ep_gen:
            return
        try:
            season = self.meta["seasons"][i]
        except (TypeError, IndexError, KeyError):
            return
        prog = self.win.progress
        fallback = self.meta.get("backdrop") or self.item.get("logo")
        eps = season["episodes"]
        end = min(len(eps), start + 25)
        for j in range(start, end):
            ep = eps[j]
            pr = prog.get(ep["url"])
            frac = (pr["pos"] / pr["len"]) if pr and pr.get("len") else 0
            if pr and pr.get("done"):
                frac = 1
            row = EpisodeRow(self.win, ep, fallback, frac)
            row.clicked.connect(lambda s=i, e=j: self._play_episode(s, e))
            if hasattr(self, "_decorate_episode"):
                self._decorate_episode(row, i, j)
            self.eps_box.addWidget(row)
        if end < len(eps):
            QtCore.QTimer.singleShot(30, lambda: self._add_eps(i, end, gen))

    def _episode_items(self, si):
        season = self.meta["seasons"][si]
        name = self.meta.get("title") or self.item["name"]
        out = []
        for ep in season["episodes"]:
            out.append({"name": f"{name} — S{season['number']:02d}E{ep['num']:02d}  {ep['name']}",
                        "url": ep["url"], "kind": "episode", "logo": self.item.get("logo"),
                        "opts": ep.get("opts") or [],
                        "_series": {"url": self.item["url"], "name": name, "logo": self.item.get("logo"),
                                    "season": season["number"], "num": ep["num"], "ep_name": ep["name"]}})
        return out

    def _play_episode(self, si, ei, restart=False):
        self.win.play_items(self._episode_items(si), ei, resume=not restart)

    def _series_last(self):
        best = None
        for url, e in self.win.progress.items():
            s = e.get("series")
            if s and s.get("url") == self.item["url"] and (best is None or e.get("t", 0) > best[1].get("t", 0)):
                best = (url, e)
        return best

    def _resume_season_index(self):
        last = self._series_last()
        if last and self.meta:
            for i, s in enumerate(self.meta.get("seasons") or []):
                if s["number"] == last[1]["series"].get("season"):
                    return i
        return 0

    def _resume_target(self):
        """(saison, épisode, reprendre?) du prochain épisode à regarder."""
        seasons = (self.meta or {}).get("seasons") or []
        if not seasons:
            return None
        last = self._series_last()
        if last:
            url, e = last
            for si, s in enumerate(seasons):
                for ei, ep in enumerate(s["episodes"]):
                    if ep["url"] == url:
                        if e.get("done"):
                            if ei + 1 < len(s["episodes"]):
                                return si, ei + 1, False
                            if si + 1 < len(seasons) and seasons[si + 1]["episodes"]:
                                return si + 1, 0, False
                            return si, ei, False
                        return si, ei, e.get("pos", 0) > 30000
        return 0, 0, False

    def refresh_progress(self):
        if self.series:
            t = self._resume_target()
            if t is None:
                self.b_play.setText("▶  Lecture")
                self.b_play.setEnabled(bool(self.meta))
                return
            si, ei, resume = t
            s = self.meta["seasons"][si]
            ep = s["episodes"][ei]
            verb = "Reprendre" if resume else "Lecture"
            self.b_play.setText(f"▶  {verb}  S{s['number']} E{ep['num']}")
            self.b_play.setEnabled(True)
            if hasattr(self, "season_btns") and self.meta:
                self._show_season(self.season_idx)
            return
        pr = self.win.progress.get(self.item["url"])
        if pr and not pr.get("done") and pr.get("pos", 0) > 30000:
            self.b_play.setText(f"▶  Reprendre · {fmt_ms(pr['pos'])}")
            self.b_restart.show()
        else:
            self.b_play.setText("▶  Lecture")
            self.b_restart.hide()

    # -- actions
    def _play(self, restart=False):
        if self.series:
            t = self._resume_target()
            if t:
                self._play_episode(t[0], t[1], restart=not t[2])
            return
        self.win.play_items([self.item], 0, resume=not restart)

    def _trailer(self):
        if self.meta and self.meta.get("trailer"):
            QtGui.QDesktopServices.openUrl(QtCore.QUrl(self.meta["trailer"]))

    def _fav(self):
        self.win.toggle_favorite(self.item)
        self._update_fav()

    # -- téléchargements
    def _download(self):
        dm = self.win.downloads
        if self.series:
            if not self.meta or not self.meta.get("seasons"):
                return
            items = self._episode_items(self.season_idx)
            n = 0
            for it in items:
                if not dm.job_for(it["url"]):
                    dm.add(it, quiet=True)
                    n += 1
            self.win.toast(f"{n} épisode(s) ajouté(s) aux téléchargements." if n else "Saison déjà téléchargée ou en cours.")
            return
        j = dm.job_for(self.item["url"])
        if j is None or j.get("state") in ("error", "paused"):
            dm.add(self.item)
        else:
            self.win.go_root("downloads")

    def _dl_state_text(self, url, short=False):
        dm = self.win.downloads
        j = dm.job_for(url)
        st = j.get("state") if j else None
        if st is None:
            return "⬇" if short else "⬇  Télécharger"
        if st == "done":
            return "✓" if short else "✓  Téléchargé"
        if st == "downloading":
            return f"{dm.percent(j)} %" if short else f"⬇  {dm.percent(j)} %"
        if st == "queued":
            return "⏳" if short else "⏳  En attente"
        if st == "paused":
            return "⏸" if short else f"⏸  En pause {dm.percent(j)} %"
        return "⚠" if short else "⚠  Réessayer"

    def _dl_changed(self, _jid):
        try:
            if self.series:
                self.b_dl.setText("⬇  Télécharger la saison")
            else:
                self.b_dl.setText(self._dl_state_text(self.item["url"]))
            for url, b in list(self._ep_btns.items()):
                try:
                    b.setText(self._dl_state_text(url, short=True))
                except RuntimeError:
                    self._ep_btns.pop(url, None)
        except RuntimeError:
            pass

    def _decorate_episode(self, row, si, ej):
        ep = self.meta["seasons"][si]["episodes"][ej]
        b = QtWidgets.QPushButton(self._dl_state_text(ep["url"], short=True))
        b.setObjectName("epdl")
        b.setFixedSize(54, 40)
        b.setCursor(Qt.CursorShape.PointingHandCursor)
        b.setToolTip("Télécharger cet épisode (lecture hors ligne)")
        b.clicked.connect(lambda _c=False, si=si, ej=ej: self._dl_episode(si, ej))
        row.layout().addWidget(b, 0, Qt.AlignmentFlag.AlignVCenter)
        self._ep_btns[ep["url"]] = b

    def _dl_episode(self, si, ej):
        it = self._episode_items(si)[ej]
        dm = self.win.downloads
        j = dm.job_for(it["url"])
        if j is None or j.get("state") in ("error", "paused"):
            dm.add(it)
        elif j.get("state") == "done":
            self.win.toast("Épisode déjà téléchargé : il se lit hors ligne.")
        else:
            self.win.go_root("downloads")

    def _update_fav(self):
        on = self.item["url"] in self.win.favorites
        self.b_fav.setText("♥  Dans Ma liste" if on else "♡  Ma liste")


# --------------------------------------------------------------------------- #
#  Fiche acteur
# --------------------------------------------------------------------------- #
class PersonPage(ScrollPage):
    def __init__(self, win, person):
        super().__init__()
        self.win, self.person = win, person
        self.hero = Backdrop(win.images)
        self.hero.setMinimumHeight(360)
        hl = QtWidgets.QHBoxLayout(self.hero)
        hl.setContentsMargins(56, 70, 48, 20)
        hl.setSpacing(40)
        self.photo = ImageLabel(win.images, 230, 230, circle=True)
        self.photo.set_image(person.get("logo"), initials(person["name"]))
        hl.addWidget(self.photo, 0, Qt.AlignmentFlag.AlignTop)
        info = QtWidgets.QVBoxLayout()
        info.setSpacing(10)
        info.addWidget(label("ACTEUR · ACTRICE", "kicker"))
        info.addWidget(label(person["name"], "herotitle", wrap=True))
        self.meta_l = label(person.get("sub") and f"Rôle : {person['sub']}" or "", "meta", wrap=True)
        info.addWidget(self.meta_l)
        self.bio = label("Chargement…", "overview", wrap=True)
        self.bio.setMaximumWidth(860)
        self.bio.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        info.addWidget(self.bio)
        self.more = button("Lire la suite", "link", self._toggle_bio)
        self.more.hide()
        info.addWidget(self.more, 0, Qt.AlignmentFlag.AlignLeft)
        info.addStretch(1)
        hl.addLayout(info, 1)
        self.v.addWidget(self.hero)
        self.body = body_box(self.v, (44, 16, 36, 48), 30)
        self.full_bio = ""
        self._local_rows()
        if tmdb_key_of(win.cfg):
            win.meta.request_person(person, self._on_meta)
        else:
            self.bio.setText("Ajoutez une clé TMDB (gratuite) dans Paramètres pour afficher la photo, "
                             "la biographie et la filmographie complète des acteurs.")

    def _retry(self, force=True):
        try:
            self.bio.setText("Connexion à TMDB…")
            self.win.meta.request_person(self.person, self._on_meta, force=force)
        except RuntimeError:
            pass

    def _local_rows(self):
        items = self.win.lib.titles_with_actor(self.person["name"])
        self._local_urls = {i["url"] for i in items}
        if items:
            self.local_row = HRow(self.win, "Dans votre liste", items, "poster")
            self.body.addWidget(self.local_row)

    def _toggle_bio(self):
        if getattr(self, "_retry_mode", False):
            self._retry_mode = False
            self.more.hide()
            self._tries = 0
            self._retry(force=True)
            return
        if self.more.text() == "Lire la suite":
            self.bio.setText(self.full_bio)
            self.more.setText("Réduire")
        else:
            self.bio.setText(self._short(self.full_bio))
            self.more.setText("Lire la suite")

    @staticmethod
    def _short(t):
        return t if len(t) < 600 else t[:597].rsplit(" ", 1)[0] + "…"

    def _on_meta(self, m):
        if not m:
            tries = getattr(self, "_tries", 0)
            if tries < 2:
                self._tries = tries + 1
                self.bio.setText("Connexion à TMDB…")
                QtCore.QTimer.singleShot(2500 * (tries + 1), lambda: self._retry(force=True))
                return
            self.bio.setText("TMDB ne répond pas pour le moment (ou aucune fiche pour cette personne). "
                             "Réessayez dans un instant.")
            self._retry_mode = True
            self.more.setText("⟳  Réessayer")
            self.more.show()
            return
        self._retry_mode = False
        self.photo.set_image(m.get("photo") or self.person.get("logo"), initials(m["name"]), self.person.get("logo"))
        bits = []
        if m.get("birthday"):
            b = f"{m['born_word']} le {fmt_date(m['birthday'])}"
            if m.get("place"):
                b += f" à {m['place']}"
            if not m.get("deathday"):
                try:
                    bd = datetime.strptime(m["birthday"], "%Y-%m-%d")
                    now = datetime.now()
                    age = now.year - bd.year - ((now.month, now.day) < (bd.month, bd.day))
                    b += f"  ({age} ans)"
                except ValueError:
                    pass
            bits.append(b)
        if m.get("deathday"):
            bits.append(f"Décès le {fmt_date(m['deathday'])}")
        if self.person.get("sub"):
            bits.append(f"Rôle : {self.person['sub']}")
        self.meta_l.setText("   ·   ".join(bits))
        self.full_bio = m.get("bio") or "Pas de biographie disponible."
        self.bio.setText(self._short(self.full_bio))
        self.more.setVisible(len(self.full_bio) >= 600)
        lib = self.win.lib
        extra_local = []
        films, series = [], []
        for c in m.get("credits") or []:
            if not c["title"]:
                continue
            match = lib.match_title(c["kind"], c["title"], c.get("original_title"), c.get("year"))
            card = {"name": c["title"], "_title": c["title"], "logo": c["poster"],
                    "sub": " · ".join(x for x in (c["year"], c["role"]) if x),
                    "kind": c["kind"], "url": f"tmdb:{c['kind']}:{c['title']}:{c['year']}"}
            if match:
                card["available"] = True
                card["_lib"] = match
                if match["url"] not in self._local_urls:
                    extra_local.append(match)
                    self._local_urls.add(match["url"])
            else:
                card["unavailable"] = True
            (films if c["kind"] == "movie" else series).append(card)
        if extra_local:
            if hasattr(self, "local_row"):
                self.local_row.view.set_items(self.local_row.view.model_.items + extra_local)
            else:
                self.local_row = HRow(self.win, "Dans votre liste", extra_local, "poster")
                self.body.insertWidget(0, self.local_row)
        for title, lst in (("Filmographie · Films", films), ("Filmographie · Séries", series)):
            if lst:
                lst.sort(key=lambda c: (not c.get("available")))
                self.body.addWidget(HRow(self.win, title, lst[:60], "poster", on_click=self._credit_clicked))
        self.body.addStretch(1)

    def _credit_clicked(self, card):
        if card.get("_lib"):
            self.win.open_item(card["_lib"])
        else:
            self.win.toast(f"« {card['name']} » n'est pas disponible dans votre liste.")


# --------------------------------------------------------------------------- #
#  Ma liste / Recherche
# --------------------------------------------------------------------------- #
class CategoriesPage(QtWidgets.QWidget):
    TABS = [("movie", "Films"), ("series", "Séries"), ("live", "Chaînes TV")]

    def __init__(self, win):
        super().__init__()
        self.win = win
        self.kind = "movie"
        v = QtWidgets.QVBoxLayout(self)
        v.setContentsMargins(40, 26, 20, 0)
        v.setSpacing(14)
        top = QtWidgets.QHBoxLayout()
        top.addWidget(label("Catégories", "pagetitle"))
        top.addSpacing(24)
        self.grp = QtWidgets.QButtonGroup(self)
        self.btns = {}
        for k, t in self.TABS:
            b = button(t, "seg")
            b.setCheckable(True)
            b.clicked.connect(lambda _c=False, kk=k: self.show_kind(kk))
            self.grp.addButton(b)
            self.btns[k] = b
            top.addWidget(b)
        top.addStretch(1)
        v.addLayout(top)
        self.grid = CardView(win, "cat")
        self.grid.item_clicked.connect(win.open_category)
        v.addWidget(self.grid, 1)

    def show_kind(self, kind=None):
        self.kind = kind or self.kind
        self.btns[self.kind].setChecked(True)
        self.grid.set_items(self.win.category_items(self.kind, 10000))

    def rebuild(self):
        self.show_kind()


def avatar_pixmap(profile, size, circle=False):
    dpr = _dpr()
    pm = QtGui.QPixmap(int(size * dpr), int(size * dpr))
    pm.setDevicePixelRatio(dpr)
    pm.fill(Qt.GlobalColor.transparent)
    p = QtGui.QPainter(pm)
    p.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
    rect = QtCore.QRectF(0, 0, size, size)
    c = QtGui.QColor(profile.get("color") or ACCENT)
    g = QtGui.QLinearGradient(rect.topLeft(), rect.bottomRight())
    g.setColorAt(0, c.lighter(125))
    g.setColorAt(1, c.darker(135))
    p.setBrush(g)
    p.setPen(Qt.PenStyle.NoPen)
    if circle:
        p.drawEllipse(rect)
    else:
        p.drawRoundedRect(rect, size * 0.16, size * 0.16)
    f = QtGui.QFont("Segoe UI Emoji" if profile.get("emoji") else "Segoe UI")
    f.setPixelSize(int(size * (0.52 if profile.get("emoji") else 0.46)))
    f.setBold(True)
    p.setFont(f)
    p.setPen(QtGui.QColor("white"))
    p.drawText(rect, _flags(Qt.AlignmentFlag.AlignCenter),
               profile.get("emoji") or (profile.get("name") or "?")[:1].upper())
    p.end()
    return pm


class ProfileDialog(QtWidgets.QDialog):
    def __init__(self, parent, profile=None, can_delete=False):
        super().__init__(parent)
        self.setWindowTitle("Modifier le profil" if profile else "Nouveau profil")
        self.setMinimumWidth(600)
        self.profile = dict(profile or {"id": uuid.uuid4().hex[:8], "name": "", "color": random.choice(AVATAR_COLORS),
                                        "emoji": "", "kids": False, "pin": ""})
        self.deleted = False
        v = QtWidgets.QVBoxLayout(self)
        v.setSpacing(12)
        top = QtWidgets.QHBoxLayout()
        self.preview = QtWidgets.QLabel()
        top.addWidget(self.preview)
        top.addSpacing(14)
        f = QtWidgets.QFormLayout()
        self.name = QtWidgets.QLineEdit(self.profile["name"])
        self.name.setPlaceholderText("Prénom")
        self.name.textChanged.connect(self._upd)
        f.addRow("Nom", self.name)
        self.pin = QtWidgets.QLineEdit(self.profile.get("pin", ""))
        self.pin.setPlaceholderText("Facultatif — 4 chiffres")
        self.pin.setMaxLength(4)
        self.pin.setEchoMode(QtWidgets.QLineEdit.EchoMode.Password)
        self.pin.setValidator(QtGui.QRegularExpressionValidator(QtCore.QRegularExpression(r"\d{0,4}")))
        f.addRow("Code PIN", self.pin)
        self.kids = QtWidgets.QCheckBox("Profil enfant (masque les catégories pour adultes)")
        self.kids.setChecked(bool(self.profile.get("kids")))
        top.addLayout(f, 1)
        v.addLayout(top)
        v.addWidget(self.kids)
        v.addWidget(label("Couleur", "meta"))
        cr = QtWidgets.QHBoxLayout()
        for c in AVATAR_COLORS:
            b = QtWidgets.QPushButton()
            b.setFixedSize(34, 34)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setStyleSheet(f"background:{c}; border-radius:17px; border:2px solid #0e1016;")
            b.clicked.connect(lambda _c=False, cc=c: self._set("color", cc))
            cr.addWidget(b)
        cr.addStretch(1)
        v.addLayout(cr)
        v.addWidget(label("Avatar", "meta"))
        grid = QtWidgets.QGridLayout()
        grid.setSpacing(6)
        for i, e in enumerate(AVATAR_EMOJIS):
            b = QtWidgets.QPushButton(e or "Aa")
            b.setObjectName("emoji")
            b.setFixedSize(46, 46)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.clicked.connect(lambda _c=False, ee=e: self._set("emoji", ee))
            grid.addWidget(b, i // 8, i % 8)
        v.addLayout(grid)
        bb = QtWidgets.QHBoxLayout()
        if profile and can_delete:
            bb.addWidget(button("Supprimer le profil", "danger", self._delete))
        bb.addStretch(1)
        bb.addWidget(button("Annuler", "secondary", self.reject))
        bb.addWidget(button("Enregistrer", "primary", self._ok))
        v.addLayout(bb)
        self._upd()

    def _set(self, k, v):
        self.profile[k] = v
        self._upd()

    def _upd(self):
        self.profile["name"] = self.name.text().strip()
        self.preview.setPixmap(avatar_pixmap(self.profile, 110))

    def _delete(self):
        r = QtWidgets.QMessageBox.question(self, APP_TITLE, f"Supprimer le profil « {self.profile['name']} » "
                                                            "ainsi que ses favoris et son historique ?")
        if r == QtWidgets.QMessageBox.StandardButton.Yes:
            self.deleted = True
            self.accept()

    def _ok(self):
        if not self.name.text().strip():
            QtWidgets.QMessageBox.warning(self, APP_TITLE, "Donnez un nom au profil.")
            return
        pin = self.pin.text().strip()
        if pin and len(pin) != 4:
            QtWidgets.QMessageBox.warning(self, APP_TITLE, "Le code PIN doit comporter 4 chiffres.")
            return
        self.profile.update(name=self.name.text().strip(), pin=pin, kids=self.kids.isChecked())
        self.accept()


class ProfileTile(ClickFrame):
    def __init__(self, profile, size=150, add=False):
        super().__init__()
        self.setObjectName("ptile")
        v = QtWidgets.QVBoxLayout(self)
        v.setContentsMargins(8, 8, 8, 8)
        v.setSpacing(10)
        self.av = QtWidgets.QLabel()
        self.av.setFixedSize(size, size)
        self.av.setAlignment(Qt.AlignmentFlag.AlignCenter)
        if add:
            self.av.setObjectName("addtile")
            self.av.setText("＋")
        else:
            self.av.setPixmap(avatar_pixmap(profile, size))
        v.addWidget(self.av, 0, Qt.AlignmentFlag.AlignHCenter)
        name = label("Ajouter un profil" if add else profile["name"], "pname")
        name.setAlignment(Qt.AlignmentFlag.AlignCenter)
        v.addWidget(name)
        extra = []
        if not add and profile.get("kids"):
            extra.append("Enfant")
        if not add and profile.get("pin"):
            extra.append("🔒")
        if extra:
            e = label(" · ".join(extra), "meta")
            e.setAlignment(Qt.AlignmentFlag.AlignCenter)
            v.addWidget(e)
        self.edit = QtWidgets.QLabel("✎", self.av)
        self.edit.setObjectName("editbadge")
        self.edit.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.edit.setFixedSize(size, size)
        self.edit.hide()


class ProfilesPage(QtWidgets.QWidget):
    def __init__(self, win):
        super().__init__()
        self.win = win
        self.manage = False
        self.setObjectName("profiles")
        v = QtWidgets.QVBoxLayout(self)
        v.setContentsMargins(40, 40, 40, 40)
        v.addStretch(2)
        logo = QtWidgets.QLabel()
        pm = logo_pixmap(72, BG)
        if pm:
            logo.setPixmap(pm)
        else:
            logo.setText(APP_TITLE)
            logo.setObjectName("herotitle")
        v.addWidget(logo, 0, Qt.AlignmentFlag.AlignHCenter)
        v.addSpacing(34)
        self.title = label("Qui regarde ?", "whotitle")
        self.title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        v.addWidget(self.title)
        v.addSpacing(26)
        self.row = QtWidgets.QHBoxLayout()
        self.row.setSpacing(18)
        holder = QtWidgets.QWidget()
        holder.setLayout(self.row)
        v.addWidget(holder, 0, Qt.AlignmentFlag.AlignHCenter)
        v.addSpacing(34)
        self.b_manage = button("Gérer les profils", "outline", self._toggle_manage)
        v.addWidget(self.b_manage, 0, Qt.AlignmentFlag.AlignHCenter)
        v.addStretch(3)
        sig = label(APP_AUTHOR, "signature")
        v.addWidget(sig, 0, Qt.AlignmentFlag.AlignLeft)

    def rebuild(self):
        while self.row.count():
            w = self.row.takeAt(0).widget()
            if w:
                w.deleteLater()
        profiles = self.win.cfg["profiles"]
        for pr in profiles:
            t = ProfileTile(pr)
            t.edit.setVisible(self.manage)
            t.clicked.connect(lambda p=pr: self._clicked(p))
            self.row.addWidget(t, 0, Qt.AlignmentFlag.AlignTop)
        if len(profiles) < 8:
            t = ProfileTile({}, add=True)
            t.clicked.connect(self._add)
            self.row.addWidget(t, 0, Qt.AlignmentFlag.AlignTop)
        self.title.setText("Gérer les profils" if self.manage else "Qui regarde ?")
        self.b_manage.setText("Terminé" if self.manage else "✎  Gérer les profils")

    def _toggle_manage(self):
        self.manage = not self.manage
        self.rebuild()

    def _clicked(self, pr):
        if self.manage:
            self._edit(pr)
        else:
            self.win.pick_profile(pr["id"])

    def _add(self):
        dlg = ProfileDialog(self)
        if dlg.exec():
            self.win.cfg["profiles"].append(dlg.profile)
            self.win.cfg["pdata"].setdefault(dlg.profile["id"], {"favorites": [], "progress": {}, "live_hist": {}})
            self.win.save()
            self.rebuild()

    def _edit(self, pr):
        dlg = ProfileDialog(self, pr, can_delete=len(self.win.cfg["profiles"]) > 1)
        if not dlg.exec():
            return
        profs = self.win.cfg["profiles"]
        if dlg.deleted:
            self.win.cfg["profiles"] = [p for p in profs if p["id"] != pr["id"]]
            self.win.cfg["pdata"].pop(pr["id"], None)
            if self.win.profile and self.win.profile["id"] == pr["id"]:
                self.win.profile = None
        else:
            for i, p in enumerate(profs):
                if p["id"] == pr["id"]:
                    profs[i] = dlg.profile
                    if self.win.profile and self.win.profile["id"] == pr["id"]:
                        self.win.profile = dlg.profile
        self.win.save()
        self.rebuild()


class FavoritesPage(ScrollPage):
    def __init__(self, win):
        super().__init__()
        self.win = win

    def rebuild(self):
        self.reset()
        box = body_box(self.v, (44, 26, 30, 40), 28)
        box.addWidget(label("Ma liste", "pagetitle"))
        favs = [i for i in self.win.lib.items if i["url"] in self.win.favorites]
        if not favs:
            box.addWidget(label("Votre liste est vide.\nAjoutez des chaînes, films ou séries avec « ♡ Ma liste » "
                                "ou par clic droit.", "empty"))
        for kind, title, style in (("live", "Chaînes TV", "channel"), ("movie", "Films", "poster"),
                                   ("series", "Séries", "poster")):
            lst = [i for i in favs if i["kind"] == kind]
            if lst:
                if kind == "live":
                    row = HRow(self.win, title, lst, style,
                               on_click=lambda it, l=lst: self.win.play_items(l, l.index(it)))
                else:
                    row = HRow(self.win, title, lst, style)
                box.addWidget(row)
        box.addStretch(1)


class SearchPage(QtWidgets.QWidget):
    def __init__(self, win):
        super().__init__()
        self.win = win
        v = QtWidgets.QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)
        self.edit = QtWidgets.QLineEdit()
        self.edit.setObjectName("searchpill")
        self.edit.setPlaceholderText("Films, Séries, TV, Acteurs…")
        self.edit.setClearButtonEnabled(True)
        self.edit.setFixedWidth(440)
        self.edit.addAction(QtGui.QIcon(nav_icon("search", "#ffffff", 22)), QtWidgets.QLineEdit.ActionPosition.LeadingPosition)
        v.addWidget(PageHeader(win, "Recherche", self.edit))
        self.results = RichPage(win)
        v.addWidget(self.results, 1)
        self._t = QtCore.QTimer(self, singleShot=True, interval=350)
        self._t.timeout.connect(self._search)
        self.edit.textChanged.connect(lambda _x: self._t.start())
        self._token = 0
        self._disc_ver = -1

    def focus(self):
        self.edit.setFocus()
        self.edit.selectAll()

    def rebuild(self):
        if not self.edit.text().strip() and self._disc_ver != id(self.win.lib.items):
            self._search()

    def _discovery(self):
        self._disc_ver = id(self.win.lib.items)
        r = self.results
        box = r.body(10)
        key = tmdb_key_of(self.win.cfg)
        if key:
            r.trending_rows(box, "movie", "Films", "cover", subtitle="Les plus recherchés")
            r.trending_rows(box, "series", "Séries", "cover", subtitle="Les plus recherchées")
            r.actors_row(box, "Acteurs", "Les plus recherchés")
        else:
            box.addWidget(label("Ajoutez une clé TMDB (gratuite) dans Paramètres pour voir les titres et acteurs "
                                "les plus recherchés.", "empty", wrap=True))
            r.add_row(box, "Films", self.win.lib.recent("movie", 30), "cover", "Ajoutés récemment")
            r.add_row(box, "Séries", self.win.lib.recent("series", 30), "cover", "Ajoutées récemment")
        box.addStretch(1)

    def _search(self):
        q = norm(self.edit.text().strip())
        self.results.reset()
        self._token += 1
        if len(q) < 2:
            self._discovery()
            return
        r = self.results
        box = r.body(10)
        terms = q.split()
        found = 0
        lib = self.win.lib
        live = [i for i in lib.by_kind["live"] if all(t in i["_q"] for t in terms)][:60]
        if live:
            found += len(live)
            r.channels_row(box, f"Chaînes TV  ({len(live)})", live)
        for kind, title in (("movie", "Films"), ("series", "Séries")):
            lst = [i for i in lib.by_kind[kind] if all(t in i["_q"] for t in terms)][:80]
            if lst:
                found += len(lst)
                r.add_row(box, f"{title}  ({len(lst)})", lst, "cover")
        self.people_holder = QtWidgets.QVBoxLayout()
        box.addLayout(self.people_holder)
        self.no_res = label("Aucun résultat dans votre liste.", "empty")
        self.no_res.setVisible(not found)
        box.addWidget(self.no_res)
        box.addStretch(1)
        key = tmdb_key_of(self.win.cfg)
        if key:
            token, text = self._token, self.edit.text().strip()
            lang = self.win.cfg.get("lang", "fr-FR")
            self.win.run_task(lambda: TMDB(key, lang).search_person(text),
                              lambda res, t=token: self._people(t, res), lambda _e: None, quiet=True)

    def _people(self, token, res):
        if token != self._token:
            return
        people = [{"name": p.get("name") or "", "logo": TMDB.img(p.get("profile_path"), "w185"),
                   "sub": ", ".join(k.get("title") or k.get("name") or "" for k in (p.get("known_for") or [])[:2]),
                   "kind": "person", "tmdb_id": p.get("id")}
                  for p in res[:30] if p.get("known_for_department") == "Acting" and p.get("profile_path")]
        if people:
            try:
                self.people_holder.addWidget(HRow(self.win, "Acteurs", people, "actor2", on_click=self.win.open_person))
                self.no_res.hide()
            except RuntimeError:
                pass


# --------------------------------------------------------------------------- #
#  Paramètres & sources
# --------------------------------------------------------------------------- #
class DropZone(QtWidgets.QFrame):
    """Zone où l'on dépose un fichier M3U (ou clic pour parcourir)."""
    picked = QtCore.Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("dropzone")
        self.setAcceptDrops(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMinimumHeight(int(150 * UI.k))
        lay = QtWidgets.QVBoxLayout(self)
        lay.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.icon = QtWidgets.QLabel("📄")
        self.icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.icon.setStyleSheet(f"font-size:{int(34 * UI.k)}px; background:transparent;")
        self.text = QtWidgets.QLabel("<b>Déposez votre fichier M3U ici</b><br>"
                                     "<span style='color:#8b91a3'>ou cliquez pour le choisir (.m3u, .m3u8)</span>")
        self.text.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.text.setWordWrap(True)
        self.text.setStyleSheet(f"font-size:{int(14 * UI.k)}px; background:transparent;")
        lay.addWidget(self.icon)
        lay.addWidget(self.text)
        self._set_over(False)

    def _set_over(self, on):
        self.setStyleSheet("QFrame#dropzone { border:2px dashed %s; border-radius:16px; background:%s; }"
                           "QFrame#dropzone:focus { border:2px solid #ffffff; }"
                           % (ACCENT, "#10233f" if on else "rgba(255,255,255,0.03)"))

    def set_file(self, path, n):
        self.icon.setText("✅")
        self.text.setText(f"<b>{html.escape(os.path.basename(path))}</b><br>"
                          f"<span style='color:#8b91a3'>{n} entrée(s) — cliquez pour choisir un autre fichier</span>")

    def browse(self):
        path, _ = QtWidgets.QFileDialog.getOpenFileName(self, "Choisir une liste M3U", os.path.expanduser("~"),
                                                        "Listes M3U (*.m3u *.m3u8 *.txt);;Tous les fichiers (*)")
        if path:
            self.picked.emit(path)

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self.browse()

    def keyPressEvent(self, e):
        if e.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space):
            self.browse()
        else:
            super().keyPressEvent(e)

    @staticmethod
    def _local(e):
        for u in e.mimeData().urls() if e.mimeData().hasUrls() else []:
            if u.isLocalFile():
                return u.toLocalFile()
        return None

    def dragEnterEvent(self, e):
        if self._local(e):
            e.acceptProposedAction()
            self._set_over(True)

    def dragLeaveEvent(self, e):
        self._set_over(False)

    def dropEvent(self, e):
        self._set_over(False)
        p = self._local(e)
        if p:
            e.acceptProposedAction()
            self.picked.emit(p)


class SourceDialog(QtWidgets.QDialog):
    TAB_FILE, TAB_URL, TAB_XTREAM = 0, 1, 2

    def __init__(self, parent=None, start_tab=None, replace=None):
        super().__init__(parent)
        self.replace = replace
        self.setWindowTitle(f"Remplacer le fichier de « {replace['name']} »" if replace else "Ajouter une source")
        self.setMinimumWidth(int(620 * UI.k))
        self.result_source = None
        self.file_path = None
        self.tabs = QtWidgets.QTabWidget()

        w0 = QtWidgets.QWidget()
        f0 = QtWidgets.QVBoxLayout(w0)
        f0.setSpacing(10)
        self.f_name = QtWidgets.QLineEdit()
        self.f_name.setPlaceholderText("Nom de la liste (facultatif)")
        self.drop = DropZone()
        self.drop.picked.connect(self._picked)
        self.f_err = QtWidgets.QLabel("")
        self.f_err.setWordWrap(True)
        self.f_err.setStyleSheet("color:#ff6b6b;")
        self.f_err.hide()
        hint0 = QtWidgets.QLabel("La liste est copiée dans l'application : elle reste disponible même si le fichier "
                                 "d'origine est déplacé. Si vous modifiez le fichier d'origine, la nouvelle version "
                                 "est reprise à la prochaine actualisation.")
        hint0.setWordWrap(True)
        hint0.setStyleSheet("color:#8b91a3;")
        if not replace:
            f0.addWidget(self.f_name)
        f0.addWidget(self.drop, 1)
        f0.addWidget(self.f_err)
        f0.addWidget(hint0)
        self.tabs.addTab(w0, "📄  Fichier M3U")

        w1 = QtWidgets.QWidget()
        f1 = QtWidgets.QFormLayout(w1)
        self.m3u_name = QtWidgets.QLineEdit()
        self.m3u_name.setPlaceholderText("Ma liste")
        self.m3u_url = QtWidgets.QLineEdit()
        self.m3u_url.setPlaceholderText("https://…/playlist.m3u")
        f1.addRow("Nom", self.m3u_name)
        f1.addRow("Lien", self.m3u_url)
        hint = QtWidgets.QLabel("Un lien du type <i>get.php?username=…&password=…</i> est converti "
                                "automatiquement en compte Xtream (TV + films + séries + fiches).")
        hint.setWordWrap(True)
        hint.setStyleSheet("color:#8b91a3;")
        f1.addRow(hint)
        self.tabs.addTab(w1, "🔗  Lien M3U")

        w2 = QtWidgets.QWidget()
        f2 = QtWidgets.QFormLayout(w2)
        self.x_name = QtWidgets.QLineEdit()
        self.x_name.setPlaceholderText("Mon abonnement")
        self.x_server = QtWidgets.QLineEdit()
        self.x_server.setPlaceholderText("http://serveur.exemple.com:8080")
        self.x_user = QtWidgets.QLineEdit()
        self.x_pass = QtWidgets.QLineEdit()
        self.x_pass.setEchoMode(QtWidgets.QLineEdit.EchoMode.Password)
        self.x_ext = QtWidgets.QComboBox()
        self.x_ext.addItems(["ts", "m3u8"])
        f2.addRow("Nom", self.x_name)
        f2.addRow("Serveur", self.x_server)
        f2.addRow("Identifiant", self.x_user)
        f2.addRow("Mot de passe", self.x_pass)
        f2.addRow("Format live", self.x_ext)
        self.tabs.addTab(w2, "📡  Compte Xtream Codes")
        if replace:
            self.tabs.setTabVisible(self.TAB_URL, False)
            self.tabs.setTabVisible(self.TAB_XTREAM, False)
        self.tabs.setCurrentIndex(self.TAB_URL if start_tab is None and not replace else (start_tab or 0))

        bb = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.StandardButton.Ok |
                                        QtWidgets.QDialogButtonBox.StandardButton.Cancel)
        bb.button(QtWidgets.QDialogButtonBox.StandardButton.Ok).setText("Remplacer" if replace else "Ajouter")
        bb.button(QtWidgets.QDialogButtonBox.StandardButton.Cancel).setText("Annuler")
        bb.accepted.connect(self._accept)
        bb.rejected.connect(self.reject)
        lay = QtWidgets.QVBoxLayout(self)
        lay.addWidget(self.tabs)
        lay.addWidget(bb)
        self.setAcceptDrops(True)

    # un fichier déposé n'importe où sur la fenêtre est accepté
    def dragEnterEvent(self, e):
        if DropZone._local(e):
            e.acceptProposedAction()

    def dropEvent(self, e):
        p = DropZone._local(e)
        if p:
            self.tabs.setCurrentIndex(self.TAB_FILE)
            self._picked(p)

    def _picked(self, path):
        try:
            _data, n = read_playlist_file(path)
        except Exception as e:
            self.file_path = None
            self.f_err.setText(f"⚠ {e}")
            self.f_err.show()
            return
        self.f_err.hide()
        self.file_path = path
        self.drop.set_file(path, n)
        if not self.f_name.text():
            self.f_name.setText(os.path.splitext(os.path.basename(path))[0])

    def _accept(self):
        sid = uuid.uuid4().hex[:12]
        tab = self.tabs.currentIndex()
        if tab == self.TAB_FILE:
            if not self.file_path:
                self.f_err.setText("Choisissez d'abord un fichier M3U (ou déposez-le dans le cadre).")
                self.f_err.show()
                return
            try:
                if self.replace:
                    self.replace["url"] = import_playlist(self.replace["id"], self.file_path)
                    self.replace["file"] = os.path.basename(self.file_path)
                    self.replace["file_orig"] = os.path.abspath(self.file_path)
                    self.result_source = self.replace
                else:
                    self.result_source = file_source(self.file_path, self.f_name.text().strip())
            except Exception as e:
                self.f_err.setText(f"⚠ {e}")
                self.f_err.show()
                return
        elif tab == self.TAB_URL:
            url = self.m3u_url.text().strip().strip('"')
            if not url:
                QtWidgets.QMessageBox.warning(self, APP_TITLE, "Indiquez le lien de la liste M3U.")
                return
            if not re.match(r"^https?://", url, re.I):
                if os.path.isfile(url[7:] if url.lower().startswith("file://") else url):
                    self.tabs.setCurrentIndex(self.TAB_FILE)
                    self._picked(url[7:] if url.lower().startswith("file://") else url)
                    return
                QtWidgets.QMessageBox.warning(self, APP_TITLE, "Le lien doit commencer par http:// ou https://.\n"
                                              "Pour un fichier sur le PC, utilisez l'onglet « Fichier M3U ».")
                return
            pu = urllib.parse.urlparse(url)
            q = urllib.parse.parse_qs(pu.query)
            name = self.m3u_name.text().strip()
            if "get.php" in pu.path.lower() and q.get("username") and q.get("password"):
                self.result_source = {"id": sid, "type": "xtream", "name": name or pu.netloc,
                                      "server": f"{pu.scheme}://{pu.netloc}", "user": q["username"][0],
                                      "password": q["password"][0], "live_ext": "ts"}
            else:
                self.result_source = {"id": sid, "type": "m3u", "name": name or pu.netloc or "Liste M3U", "url": url}
        else:
            server, user, pwd = self.x_server.text().strip(), self.x_user.text().strip(), self.x_pass.text().strip()
            if not (server and user and pwd):
                QtWidgets.QMessageBox.warning(self, APP_TITLE, "Serveur, identifiant et mot de passe requis.")
                return
            self.result_source = {"id": sid, "type": "xtream",
                                  "name": self.x_name.text().strip() or urllib.parse.urlparse(
                                      server if "://" in server else "http://" + server).netloc,
                                  "server": server, "user": user, "password": pwd,
                                  "live_ext": self.x_ext.currentText()}
        self.accept()


class SettingsPage(ScrollPage):
    LANGS = [("fr-FR", "Français"), ("en-US", "English"), ("es-ES", "Español"), ("de-DE", "Deutsch"),
             ("it-IT", "Italiano"), ("pt-PT", "Português"), ("ar-SA", "العربية")]

    def __init__(self, win):
        super().__init__()
        self.win = win
        box = body_box(self.v, (44, 26, 44, 40), 18)
        box.addWidget(label("Paramètres", "pagetitle"))

        box.addWidget(label("Sources", "rowtitle"))
        self.sources = QtWidgets.QListWidget()
        self.sources.setObjectName("card")
        self.sources.setFixedHeight(170)
        box.addWidget(self.sources)
        row = QtWidgets.QHBoxLayout()
        row.addWidget(button("＋ Ajouter", "primary", win.add_source))
        row.addWidget(button("✓ Utiliser", "secondary", self._use))
        row.addWidget(button("⟳ Actualiser", "secondary", self._refresh))
        row.addWidget(button("📄 Remplacer le fichier", "secondary", self._replace_file))
        row.addWidget(button("🗑 Supprimer", "secondary", self._delete))
        row.addStretch(1)
        box.addLayout(row)

        box.addSpacing(10)
        box.addWidget(label("Fiches films, séries et acteurs (TMDB)", "rowtitle"))
        box.addWidget(label(
            "Avec une clé TMDB gratuite, l'application affiche les photos et biographies des acteurs, "
            "leur filmographie, les fonds d'écran, bandes-annonces, âges requis et vignettes d'épisodes. "
            "Créez un compte sur themoviedb.org → Paramètres → API, puis collez la clé API (v3) "
            "ou le jeton d'accès en lecture (v4)."
            + ("  Une clé est déjà intégrée à l'application : ce champ ne sert que si vous voulez utiliser la vôtre."
               if TMDB_BUILTIN_KEY else ""), "overview", wrap=True))
        krow = QtWidgets.QHBoxLayout()
        self.key = QtWidgets.QLineEdit(win.cfg.get("tmdb_key", ""))
        self.key.setPlaceholderText("Clé API TMDB")
        self.key.setEchoMode(QtWidgets.QLineEdit.EchoMode.PasswordEchoOnEdit)
        krow.addWidget(self.key, 1)
        krow.addWidget(button("Tester et enregistrer", "primary", self._save_key))
        krow.addWidget(button("Obtenir une clé", "secondary",
                              lambda: QtGui.QDesktopServices.openUrl(QtCore.QUrl("https://www.themoviedb.org/settings/api"))))
        box.addLayout(krow)
        lrow = QtWidgets.QHBoxLayout()
        lrow.addWidget(label("Langue des fiches :", "meta"))
        self.lang = QtWidgets.QComboBox()
        for code, name in self.LANGS:
            self.lang.addItem(name, code)
        i = self.lang.findData(win.cfg.get("lang", "fr-FR"))
        self.lang.setCurrentIndex(max(0, i))
        self.lang.currentIndexChanged.connect(self._lang)
        lrow.addWidget(self.lang)
        lrow.addStretch(1)
        box.addLayout(lrow)

        box.addSpacing(10)
        box.addWidget(label("Lecture, pré-chargement et téléchargements", "rowtitle"))
        box.addWidget(label(
            "Pré-chargement : le film ou l'épisode est téléchargé en avance pendant que vous regardez. "
            "Si la connexion ralentit, la lecture continue sur ce qui est déjà chargé ; si elle s'arrête, "
            "l'application se met en pause le temps de remplir la réserve choisie, puis repart sans à-coups. "
            "Avec un très petit débit, utilisez plutôt « ⬇ Télécharger » sur la fiche.", "overview", wrap=True))
        brow = QtWidgets.QHBoxLayout()
        brow.addWidget(label("Pré-chargement des films et séries :", "meta"))
        self.buf = QtWidgets.QComboBox()
        for v, t in ((0, "Désactivé (lecture directe)"), (1, "1 minute d'avance"), (5, "5 minutes d'avance"),
                     (10, "10 minutes d'avance")):
            self.buf.addItem(t, v)
        self.buf.setCurrentIndex(max(0, self.buf.findData(int(win.cfg.get("buffer_min", 0) or 0))))
        self.buf.currentIndexChanged.connect(self._set_buf)
        brow.addWidget(self.buf)
        brow.addSpacing(24)
        brow.addWidget(label("Mémoire tampon des chaînes TV :", "meta"))
        self.lcache = QtWidgets.QComboBox()
        for v, t in ((2500, "2,5 s (standard)"), (5000, "5 s"), (10000, "10 s"), (20000, "20 s"), (30000, "30 s")):
            self.lcache.addItem(t, v)
        self.lcache.setCurrentIndex(max(0, self.lcache.findData(int(win.cfg.get("live_cache", 2500)))))
        self.lcache.currentIndexChanged.connect(self._set_lcache)
        brow.addWidget(self.lcache)
        brow.addStretch(1)
        box.addLayout(brow)
        drow = QtWidgets.QHBoxLayout()
        self.dl_dir = label("", "meta")
        drow.addWidget(self.dl_dir)
        drow.addWidget(button("Changer…", "secondary", self._change_dl_dir))
        drow.addWidget(button("Voir les téléchargements", "secondary", lambda: win.go_root("downloads")))
        drow.addStretch(1)
        box.addLayout(drow)

        box.addSpacing(10)
        box.addWidget(label("Stockage", "rowtitle"))
        srow = QtWidgets.QHBoxLayout()
        srow.addWidget(button("Vider le cache des images", "secondary", self._clear_images))
        srow.addWidget(button("Vider le cache des fiches", "secondary", self._clear_meta))
        srow.addWidget(button("Effacer l'historique de lecture", "secondary", self._clear_progress))
        srow.addStretch(1)
        box.addLayout(srow)
        box.addWidget(label(f"Données : {DATA_DIR}", "meta"))
        vl = "VLC détecté ✓" if win.player.available() else f"VLC introuvable ✗ ({VLC_ERROR or 'libvlc'})"
        box.addWidget(label(vl, "meta"))
        box.addWidget(label(f"{APP_TITLE} {APP_VERSION} — conçu par {APP_AUTHOR}", "meta"))
        box.addStretch(1)

    def _set_buf(self):
        self.win.cfg["buffer_min"] = int(self.buf.currentData())
        self.win.save()

    def _set_lcache(self):
        self.win.cfg["live_cache"] = int(self.lcache.currentData())
        self.win.save()

    def _change_dl_dir(self):
        d = QtWidgets.QFileDialog.getExistingDirectory(self, "Dossier des téléchargements", self.win.downloads.folder())
        if d:
            self.win.cfg["download_dir"] = d
            self.win.save()
            self.rebuild()

    def rebuild(self):
        self.dl_dir.setText(f"Dossier des téléchargements : {self.win.downloads.folder()}")
        self.sources.clear()
        for s in self.win.cfg["sources"]:
            cur = self.win.current_source and self.win.current_source["id"] == s["id"]
            it = QtWidgets.QListWidgetItem(("● " if cur else "   ") + ("📡 " if s["type"] == "xtream" else "📄 ")
                                           + s["name"] + ("   —   Xtream Codes" if s["type"] == "xtream" else
                                                          (f"   —   fichier M3U ({s['file']})" if s.get("file") else "   —   lien M3U")))
            it.setData(Qt.ItemDataRole.UserRole, s["id"])
            self.sources.addItem(it)

    def _sel(self):
        it = self.sources.currentItem()
        return it.data(Qt.ItemDataRole.UserRole) if it else None

    def _use(self):
        if self._sel():
            self.win.set_source(self._sel())
            self.rebuild()

    def _refresh(self):
        sid = self._sel() or (self.win.current_source or {}).get("id")
        if sid:
            self.win.set_source(sid, force=True)

    def _replace_file(self):
        sid = self._sel() or (self.win.current_source or {}).get("id")
        src = self.win._source_by_id(sid) if sid else None
        if not src or not src.get("file"):
            QtWidgets.QMessageBox.information(self, APP_TITLE, "Sélectionnez une source ajoutée depuis un fichier M3U.")
            return
        self.win.replace_source_file(sid)
        self.rebuild()

    def _delete(self):
        if self._sel():
            self.win.delete_source(self._sel())
            self.rebuild()

    def _save_key(self):
        key = self.key.text().strip()
        if not key:
            self.win.cfg["tmdb_key"] = ""
            self.win.save()
            self.win.toast("Clé TMDB supprimée.")
            return

        def ok(_r):
            self.win.cfg["tmdb_key"] = key
            self.win.meta.clear_mem()
            self.win.save()
            self.win.toast("Clé TMDB valide et enregistrée ✓")

        self.win.run_task(lambda: TMDB(key).get("/configuration"), ok,
                          lambda e: QtWidgets.QMessageBox.warning(self, APP_TITLE, f"Clé refusée par TMDB :\n{e}"),
                          busy="Vérification de la clé…")

    def _lang(self):
        self.win.cfg["lang"] = self.lang.currentData()
        self.win.meta.clear_mem()
        self.win.save()

    def _clear_images(self):
        n = self.win.images.clear_disk()
        self.win.toast(f"{n} images supprimées du cache.")

    def _clear_meta(self):
        for f in os.listdir(META_DIR):
            try:
                os.remove(os.path.join(META_DIR, f))
            except OSError:
                pass
        self.win.meta.clear_mem()
        self.win.toast("Cache des fiches vidé.")

    def _clear_progress(self):
        self.win.progress.clear()
        self.win.save()
        self.win.home.refresh_continue()
        self.win.toast("Historique de lecture effacé.")


# --------------------------------------------------------------------------- #
#  Lecteur
# --------------------------------------------------------------------------- #
class VideoFrame(QtWidgets.QFrame):
    double_clicked = QtCore.Signal()

    def __init__(self):
        super().__init__()
        self.setMinimumSize(320, 180)
        pal = self.palette()
        pal.setColor(QtGui.QPalette.ColorRole.Window, QtGui.QColor("#000"))
        self.setPalette(pal)
        self.setAutoFillBackground(True)

    def mouseDoubleClickEvent(self, e):
        self.double_clicked.emit()


class PlayerPage(QtWidgets.QWidget):
    def __init__(self, win):
        super().__init__()
        self.win = win
        self.items, self.index, self.current = [], 0, None
        self._buf = None
        self._buf_pending = False
        self._rebuf = False
        self._dragging = False
        self._ticks = 0
        self._ended_handled = False
        self.immersive = False
        self._last_cursor = None
        self._idle = 0
        self.setObjectName("player")

        self.video = VideoFrame()
        self.video.double_clicked.connect(win.toggle_fullscreen)

        self.topbar = QtWidgets.QWidget()
        self.topbar.setObjectName("pbar")
        tb = QtWidgets.QHBoxLayout(self.topbar)
        tb.setContentsMargins(14, 8, 14, 8)
        tb.addWidget(button("‹  Retour", "glass", win.back))
        tt = QtWidgets.QVBoxLayout()
        tt.setSpacing(0)
        self.title = label("", "ptitle")
        self.subtitle = label("", "meta")
        tt.addWidget(self.title)
        tt.addWidget(self.subtitle)
        tb.addSpacing(10)
        tb.addLayout(tt, 1)
        self.b_list = button("☰  Chaînes", "glass", self._toggle_list)
        tb.addWidget(self.b_list)

        self.controls = QtWidgets.QWidget()
        self.controls.setObjectName("pbar")
        cl = QtWidgets.QVBoxLayout(self.controls)
        cl.setContentsMargins(16, 8, 16, 12)
        cl.setSpacing(6)
        row = QtWidgets.QHBoxLayout()
        self.pos_l = label("", "time")
        self.seek = QtWidgets.QSlider(Qt.Orientation.Horizontal)
        self.seek.setRange(0, 1000)
        self.seek.sliderPressed.connect(lambda: setattr(self, "_dragging", True))
        self.seek.sliderReleased.connect(self._seek_released)
        self.len_l = label("", "time")
        row.addWidget(self.pos_l)
        row.addWidget(self.seek, 1)
        row.addWidget(self.len_l)
        cl.addLayout(row)
        br = QtWidgets.QHBoxLayout()
        br.setSpacing(6)
        self.b_prev = button("⏮", "ctrl", self.prev)
        self.b_back = button("↺ 10", "ctrl", lambda: self.seek_rel(-10))
        self.b_play = button("⏸", "ctrlmain", self.toggle_pause)
        self.b_fwd = button("30 ↻", "ctrl", lambda: self.seek_rel(30))
        self.b_next = button("⏭", "ctrl", self.next)
        for b in (self.b_prev, self.b_back, self.b_play, self.b_fwd, self.b_next):
            br.addWidget(b)
        self.live_l = label("● EN DIRECT", "live")
        br.addSpacing(8)
        br.addWidget(self.live_l)
        self.buf_l = label("", "buflabel")
        self.buf_l.hide()
        br.addSpacing(10)
        br.addWidget(self.buf_l)
        br.addStretch(1)
        self.b_audio = button("🔊 Audio", "ctrl")
        self.menu_audio = QtWidgets.QMenu(self)
        self.menu_audio.aboutToShow.connect(self._fill_audio)
        self.b_audio.setMenu(self.menu_audio)
        self.b_subs = button("💬 Sous-titres", "ctrl")
        self.menu_subs = QtWidgets.QMenu(self)
        self.menu_subs.aboutToShow.connect(self._fill_subs)
        self.b_subs.setMenu(self.menu_subs)
        self.vol = QtWidgets.QSlider(Qt.Orientation.Horizontal)
        self.vol.setRange(0, 100)
        self.vol.setValue(int(win.cfg.get("volume", 80)))
        self.vol.setFixedWidth(110)
        self.vol.valueChanged.connect(self._set_volume)
        self.b_fs = button("⛶", "ctrl", win.toggle_fullscreen)
        self.b_fs.setToolTip("Plein écran (F)")
        for w in (self.b_audio, self.b_subs, label("🔈", "meta"), self.vol, self.b_fs):
            br.addWidget(w)
        cl.addLayout(br)

        self.side = QtWidgets.QListWidget()
        self.side.setObjectName("side")
        self.side.setFixedWidth(300)
        self.side.hide()
        self.side.itemClicked.connect(lambda it: self.play_index(self.side.row(it)))

        center = QtWidgets.QVBoxLayout()
        center.setContentsMargins(0, 0, 0, 0)
        center.setSpacing(0)
        center.addWidget(self.topbar)
        center.addWidget(self.video, 1)
        center.addWidget(self.controls)
        h = QtWidgets.QHBoxLayout(self)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(0)
        h.addLayout(center, 1)
        h.addWidget(self.side)

        self.instance = self.mp = None
        global VLC_ERROR
        if vlc is not None:
            try:
                self.instance = vlc.Instance("--network-caching=2500", "--no-video-title-show", "--quiet")
                self.mp = self.instance.media_player_new() if self.instance else None
            except Exception as e:
                VLC_ERROR = str(e)
                self.instance = self.mp = None
        if self.mp:
            wid = int(self.video.winId())
            if sys.platform.startswith("win"):
                self.mp.set_hwnd(wid)
            elif sys.platform == "darwin":
                self.mp.set_nsobject(wid)
            else:
                self.mp.set_xwindow(wid)
            self.mp.video_set_mouse_input(False)
            self.mp.video_set_key_input(False)
            self.mp.audio_set_volume(self.vol.value())

        self.timer = QtCore.QTimer(self, interval=500)
        self.timer.timeout.connect(self._tick)
        self.timer.start()

    def available(self):
        return self.mp is not None

    # -- lecture
    def play_list(self, items, index, resume=True):
        self.items = list(items)
        is_live = bool(self.items) and self.items[0].get("kind") == "live"
        self.side.clear()
        if len(self.items) > 1:
            for it in self.items:
                self.side.addItem(it.get("_title") or it["name"])
        self.b_list.setVisible(len(self.items) > 1)
        self.b_list.setText("☰  Chaînes" if is_live else "☰  Épisodes")
        self.play_index(index, resume)

    def play_index(self, i, resume=True):
        if not self.items:
            return
        self._save_now()
        i = max(0, min(len(self.items) - 1, i))
        self.index = i
        item = self.items[i]
        self.current = item
        self.win.note_live(item)
        self._ended_handled = False
        self.title.setText(item.get("_title") or item["name"])
        s = item.get("_series")
        self.subtitle.setText(f"Saison {s['season']} · Épisode {s['num']}" if s else
                              pretty_group(item.get("group") or ""))
        live = item.get("kind") == "live"
        self.live_l.setVisible(live)
        for w in (self.b_back, self.b_fwd):
            w.setVisible(not live)
        self.b_prev.setEnabled(i > 0)
        self.b_next.setEnabled(i < len(self.items) - 1)
        self.side.blockSignals(True)
        if self.side.count() > i:
            self.side.setCurrentRow(i)
        self.side.blockSignals(False)
        if not self.mp:
            QtWidgets.QMessageBox.warning(
                self, APP_TITLE, "Le moteur VLC est introuvable.\n\nInstallez VLC 64 bits (videolan.org) puis relancez."
                f"\n\nDétail : {VLC_ERROR or 'libvlc non chargé'}")
            return
        self._close_buffer()
        url = item["url"]
        pr = self.win.progress.get(url)
        start_s = pr["pos"] / 1000 if (resume and not live and pr and not pr.get("done") and pr.get("pos", 0) > 30000) else 0
        local = self.win.downloads.local_file(url)
        mins = int(self.win.cfg.get("buffer_min", 0) or 0)
        self.buf_l.hide()
        if local:
            media = self.instance.media_new_path(local)
            self.buf_l.setText("✓ Lecture du fichier téléchargé (hors ligne)")
            self.buf_l.show()
        elif not live and mins > 0 and url.lower().startswith(("http://", "https://")) and ".m3u8" not in url.lower():
            sid, sess, purl = BUFFER.open(url, mins * 60)
            if pr and pr.get("len"):
                sess.bps = 1_000_000.0
                sess._len_hint = pr["len"]
            self._buf = (sid, sess, start_s)
            self._buf_pending = True
            self._rebuf = False
            media = self.instance.media_new(purl)
            self.buf_l.setText("Connexion…")
            self.buf_l.show()
        else:
            media = self.instance.media_new(url)
            media.add_option(f":http-user-agent={USER_AGENT}")
        if live:
            media.add_option(f":network-caching={int(self.win.cfg.get('live_cache', 2500))}")
        for o in item.get("opts") or []:
            media.add_option(":" + o)
        if start_s:
            media.add_option(f":start-time={start_s:.0f}")
        self.mp.set_media(media)
        if not self._buf:
            self.mp.play()
        if live and item.get("stream_id"):
            self.win.fetch_epg(item, self._epg)

    def _epg(self, item, progs):
        if item is not self.current or not progs:
            return

        def hm(p, k):
            ts = p.get(k + "_ts")
            try:
                return datetime.fromtimestamp(int(ts)).strftime("%H:%M")
            except (TypeError, ValueError):
                return (p.get("start" if k == "start" else "end") or "")[11:16]
        now = progs[0]
        txt = f"Maintenant : {now['title']}  ({hm(now, 'start')}–{hm(now, 'stop')})"
        if len(progs) > 1:
            txt += f"     ·     Ensuite : {progs[1]['title']} ({hm(progs[1], 'start')})"
        self.subtitle.setText(txt)
        self.subtitle.setToolTip(now.get("desc") or "")

    def next(self):
        if self.index < len(self.items) - 1:
            self.play_index(self.index + 1)

    def prev(self):
        if self.index > 0:
            self.play_index(self.index - 1)

    def toggle_pause(self):
        if not self.mp:
            return
        if self._buf and (self._buf_pending or self._rebuf):
            self._buf_pending = self._rebuf = False
            self.mp.set_pause(0) if self.mp.get_media() and self.mp.get_time() > 0 else self.mp.play()
            return
        st = self.mp.get_state()
        if st in (vlc.State.Stopped, vlc.State.Ended, vlc.State.Error, vlc.State.NothingSpecial):
            if self.current:
                self.play_index(self.index)
        else:
            self.mp.pause()

    def seek_rel(self, secs):
        if self.mp and self.mp.get_length() > 0:
            self.mp.set_time(max(0, self.mp.get_time() + secs * 1000))

    def volume_rel(self, d):
        self.vol.setValue(max(0, min(100, self.vol.value() + d)))

    def stop(self):
        self._save_now()
        if self.mp:
            self.mp.stop()
        self._close_buffer()
        self.current = None

    # -- pré-chargement (1, 5 ou 10 minutes d'avance)
    def _close_buffer(self):
        if self._buf:
            BUFFER.close(self._buf[0])
        self._buf = None
        self._buf_pending = self._rebuf = False

    def _buffer_tick(self):
        sid, sess, start_s = self._buf
        if sess.failed and (self._buf_pending or sess.size is None):
            # flux non compatible : lecture directe classique
            item = self.current
            self._close_buffer()
            self.buf_l.setText("Pré-chargement indisponible pour ce flux : lecture directe")
            media = self.instance.media_new(item["url"])
            media.add_option(f":http-user-agent={USER_AGENT}")
            for o in item.get("opts") or []:
                media.add_option(":" + o)
            if start_s:
                media.add_option(f":start-time={start_s:.0f}")
            self.mp.set_media(media)
            self.mp.play()
            return
        length = self.mp.get_length() if self.mp else 0
        sess.set_length(length if length > 0 else getattr(sess, "_len_hint", 0))
        target = sess.ahead_secs
        sp = f"  ·  {fmt_size(sess.speed)}/s" if sess.speed > 0 else ""
        if self._buf_pending:
            if sess.size is None:
                self.buf_l.setText("Connexion au serveur…")
                return
            if start_s and length <= 0 and getattr(sess, "_len_hint", 0):
                sess.set_want(int(sess.size * min(0.99, start_s * 1000 / sess._len_hint)))
                start_s = 0
                self._buf = (sid, sess, 0)
            need = min(target, 30)
            ready = sess.ahead_ready()
            if ready >= need or sess.at_end():
                self._buf_pending = False
                self.mp.play()
            else:
                self.buf_l.setText(f"⬇ Pré-chargement {fmt_secs(ready)} / {fmt_secs(need)}{sp}")
            return
        ready = sess.ahead_ready()
        end = sess.at_end()
        if self._rebuf:
            if ready >= target * 0.95 or end:
                self._rebuf = False
                self.mp.set_pause(0)
            else:
                self.buf_l.setText(f"⏳ Mise en mémoire {fmt_secs(ready)} / {fmt_secs(target)}{sp}  —  ▶ pour reprendre")
                return
        if self.mp.is_playing() and not end and ready < 1.5 and self.mp.get_time() > 2000:
            self._rebuf = True
            self.mp.set_pause(1)
            return
        self.buf_l.setText("⬇ Film entièrement chargé" if end else f"⬇ {fmt_secs(ready)} d'avance{sp}")

    def shutdown(self):
        self.stop()
        if self.mp:
            self.mp.release()
            self.mp = None
        if self.instance:
            self.instance.release()
            self.instance = None

    def _save_now(self):
        if not self.mp or not self.current or self.current.get("kind") == "live":
            return
        length, t = self.mp.get_length(), self.mp.get_time()
        if length > 0 and t > 0:
            self.win.save_progress(self.current, t, length)

    def _toggle_list(self):
        self.side.setVisible(not self.side.isVisible())

    def _set_volume(self, v):
        self.win.cfg["volume"] = int(v)
        if self.mp:
            self.mp.audio_set_volume(int(v))

    def _seek_released(self):
        self._dragging = False
        if self.mp and self.mp.get_length() > 0:
            self.mp.set_position(self.seek.value() / 1000.0)

    def set_immersive(self, on):
        self.immersive = on
        self._idle = 0
        self._show_bars(True)
        if not on:
            self.setCursor(Qt.CursorShape.ArrowCursor)

    def _show_bars(self, on):
        self.topbar.setVisible(on)
        self.controls.setVisible(on)
        if self.immersive:
            self.video.setCursor(Qt.CursorShape.ArrowCursor if on else Qt.CursorShape.BlankCursor)

    def _tick(self):
        if self.immersive:
            pos = QtGui.QCursor.pos()
            if pos != self._last_cursor:
                self._last_cursor = pos
                self._idle = 0
                if not self.controls.isVisible():
                    self._show_bars(True)
            else:
                self._idle += 1
                if self._idle == 6 and not self.menu_audio.isVisible() and not self.menu_subs.isVisible():
                    self._show_bars(False)
        if not self.mp or not self.isVisible():
            return
        if self._buf:
            self._buffer_tick()
        playing = self.mp.is_playing()
        self.b_play.setText("⏸" if playing else "▶")
        st = self.mp.get_state()
        if st == vlc.State.Error and self.current:
            self.subtitle.setText("⚠  Impossible de lire ce flux (hors ligne ou format non supporté).")
        if st == vlc.State.Ended and self.current and not self._ended_handled:
            self._ended_handled = True
            if self.current.get("kind") != "live":
                self.win.save_progress(self.current, 1, 1)
                if self.index < len(self.items) - 1:
                    QtCore.QTimer.singleShot(800, self.next)
        length = self.mp.get_length()
        live = self.current and self.current.get("kind") == "live"
        if (st == vlc.State.Buffering or st == vlc.State.Opening) and not self._buf_pending:
            self.len_l.setText("Chargement…")
        if length > 0 and not live:
            self.seek.setEnabled(True)
            self.seek.show()
            if not self._dragging:
                self.seek.setValue(int(self.mp.get_position() * 1000))
            self.pos_l.setText(fmt_ms(self.mp.get_time()))
            self.len_l.setText(fmt_ms(length))
            self._ticks += 1
            if self._ticks % 10 == 0:
                self._save_now()
        else:
            self.seek.setEnabled(False)
            self.seek.setValue(0)
            self.seek.setVisible(not live)
            self.pos_l.setText("")
            if st not in (vlc.State.Buffering, vlc.State.Opening):
                self.len_l.setText("")

    def _fill_tracks(self, menu, getter, setter, current):
        menu.clear()
        try:
            tracks = (getter() or []) if self.mp else []
            cur = current() if self.mp else None
        except Exception:
            tracks, cur = [], None
        if not tracks:
            menu.addAction("Aucune piste disponible").setEnabled(False)
            return
        for tid, name in tracks:
            if isinstance(name, bytes):
                name = name.decode("utf-8", "replace")
            a = menu.addAction(str(name).replace("Disable", "Désactivés"))
            a.setCheckable(True)
            a.setChecked(tid == cur)
            a.triggered.connect(lambda _c=False, t=tid: setter(t))

    def _fill_audio(self):
        if self.mp:
            self._fill_tracks(self.menu_audio, self.mp.audio_get_track_description,
                              self.mp.audio_set_track, self.mp.audio_get_track)
        else:
            self._fill_tracks(self.menu_audio, list, None, None)

    def _fill_subs(self):
        if self.mp:
            self._fill_tracks(self.menu_subs, self.mp.video_get_spu_description,
                              self.mp.video_set_spu, self.mp.video_get_spu)
        else:
            self._fill_tracks(self.menu_subs, list, None, None)


# --------------------------------------------------------------------------- #
#  Bibliothèque & métadonnées
# --------------------------------------------------------------------------- #
class Library:
    def __init__(self):
        self.set_items([])
        self.actor_index = {}

    def set_items(self, items):
        self.items = items
        self.by_kind = {"live": [], "movie": [], "series": []}
        self.titles = {"movie": {}, "series": {}}
        self.by_url = {}
        for n, it in enumerate(items):
            it["_i"] = n
            self.by_url[it["url"]] = it
            if it["kind"] in ("movie", "series"):
                t, y = clean_title(it["name"])
                it["_title"], it["_year"] = t, y or ""
                it["_q"] = norm(it["name"] + " " + t)
                r = str(it.get("rating") or "")
                try:
                    rv = float(r)
                    if rv > 10:
                        rv = rv / 10
                    it["_rating"] = f"{rv:.1f}" if rv > 0 else ""
                except ValueError:
                    it["_rating"] = ""
                it["sub"] = " · ".join(x for x in (it["_year"], pretty_group(it["group"])) if x)
                self.titles[it["kind"]].setdefault(title_key(t), []).append(it)
            else:
                it["_title"] = strip_lead_tags(it["name"]) or it["name"]
                it["_q"] = norm(it["name"])
                it["sub"] = ""
            self.by_kind.setdefault(it["kind"], []).append(it)

    def recent(self, kind, n):
        lst = self.by_kind.get(kind) or []
        if not any(i.get("added") for i in lst[:200]):
            return lst[-n:][::-1] if len(lst) > n else lst[::-1]

        def k(i):
            a = str(i.get("added") or "0")
            return int(a) if a.isdigit() else 0
        return sorted(lst, key=k, reverse=True)[:n]

    def match_title(self, kind, title, original="", year=""):
        for t in (title, original):
            if not t:
                continue
            cands = self.titles.get(kind, {}).get(title_key(t))
            if cands:
                if year:
                    for c in cands:
                        if c.get("_year") == year:
                            return c
                return cands[0]
        return None

    def index_cast(self, item, meta):
        for c in (meta or {}).get("cast") or []:
            if c.get("name"):
                self.actor_index.setdefault(norm(c["name"]), set()).add(item["url"])

    def titles_with_actor(self, name):
        urls = self.actor_index.get(norm(name), set())
        return [i for i in self.items if i["url"] in urls]


class MetaService(QtCore.QObject):
    def __init__(self, win):
        super().__init__(win)
        self.win = win
        self.mem, self.pending = {}, {}
        self._stale, self._refresh_fn = set(), {}

    def clear_mem(self):
        self.mem.clear()

    def _disk(self, key):
        return os.path.join(META_DIR, hashlib.md5(key.encode("utf-8")).hexdigest() + ".json")

    def _run(self, key, compute, cb, force=False):
        if force:
            self.mem.pop(key, None)
        if key in self.mem:
            m = self.mem[key]
            QtCore.QTimer.singleShot(0, lambda: safe_call(cb, m))
            return
        if key in self.pending:
            self.pending[key].append(cb)
            return
        self.pending[key] = [cb]
        path = self._disk(key)

        def fresh():
            m = compute()
            if m:
                try:
                    with open(path, "w", encoding="utf-8") as f:
                        json.dump(m, f, ensure_ascii=False)
                except OSError:
                    pass
            return m

        def job():
            if not force:
                try:
                    if os.path.exists(path):
                        age = time.time() - os.path.getmtime(path)
                        with open(path, encoding="utf-8") as f:
                            m = json.load(f)
                        failed = isinstance(m, dict) and m.get("_tmdb") == "fail"
                        if failed and age > 20 * 60:
                            return fresh() or m          # TMDB n'avait pas répondu : on réessaie
                        if age < META_REFRESH or failed:
                            return m
                        if age < META_TTL * 8:
                            self._stale.add(key)       # affichée tout de suite, actualisée en arrière-plan
                            return m
                except Exception:
                    pass
            return fresh()

        self._refresh_fn[key] = fresh
        self.win.run_task(job, lambda m: self._done(key, m), lambda _e: self._done(key, None), quiet=True)

    def _done(self, key, m):
        if m:
            self.mem[key] = m
        for cb in self.pending.pop(key, []):
            safe_call(cb, m)
        if key in self._stale:
            self._stale.discard(key)
            fn = self._refresh_fn.get(key)
            if fn:
                self.win.run_task(fn, lambda nm, k=key: nm and self.mem.__setitem__(k, nm), lambda _e: None, quiet=True)
        self._refresh_fn.pop(key, None)

    def request(self, item, cb, force=False):
        cfg, src = self.win.cfg, self.win.current_source
        tkey, lang = tmdb_key_of(cfg), cfg.get("lang", "fr-FR")
        key = f"v3|{item['kind']}|{(src or {}).get('id')}|{item['url']}|{lang}|{bool(tkey)}"
        fn = series_meta if item["kind"] == "series" else movie_meta
        item_copy = {k: v for k, v in item.items() if not k.startswith("_")}

        def done(m, it=item):
            if m:
                self.win.lib.index_cast(it, m)
            safe_call(cb, m)
        self._run(key, lambda: fn(src, item_copy, tkey, lang), done, force)

    def request_list(self, name, compute, cb):
        """Listes TMDB (tendances, acteurs populaires) mises en cache pour la journée."""
        lang = self.win.cfg.get("lang", "fr-FR")
        key = f"list|{name}|{lang}|{time.strftime('%Y-%m-%d')}"
        self._run(key, compute, cb)

    def request_person(self, person, cb, force=False):
        cfg = self.win.cfg
        tkey, lang = tmdb_key_of(cfg), cfg.get("lang", "fr-FR")
        if not tkey:
            QtCore.QTimer.singleShot(0, lambda: safe_call(cb, None))
            return
        pid, name = person.get("tmdb_id"), person["name"]
        key = f"person|{pid or norm(name)}|{lang}"
        self._run(key, lambda: person_meta(tkey, lang, pid, name), cb, force)


# --------------------------------------------------------------------------- #
#  Fenêtre principale
# --------------------------------------------------------------------------- #
class Sidebar(QtWidgets.QFrame):
    """Menu latéral en dégradé (façon OCTO+)."""

    def paintEvent(self, e):
        p = QtGui.QPainter(self)
        r = QtCore.QRectF(self.rect())
        g = QtGui.QLinearGradient(r.topLeft(), r.bottomRight())
        g.setColorAt(0, QtGui.QColor(SIDEBAR_TOP))
        g.setColorAt(1, QtGui.QColor(SIDEBAR_BOTTOM))
        p.fillRect(r, g)
        p.fillRect(QtCore.QRectF(r.right() - 1, 0, 1, r.height()), QtGui.QColor(255, 255, 255, 18))


class PillBar(QtWidgets.QFrame):
    """Barre d'onglets flottante (menu replié)."""

    def paintEvent(self, e):
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        r = QtCore.QRectF(self.rect()).adjusted(1, 1, -1, -1)
        p.setPen(QtGui.QPen(QtGui.QColor(255, 255, 255, 40), 1))
        p.setBrush(QtGui.QColor(40, 48, 62, 225))
        p.drawRoundedRect(r, r.height() / 2, r.height() / 2)


# --------------------------------------------------------------------------- #
#  Pré-chargement (mémoire tampon en minutes) et téléchargements hors ligne
# --------------------------------------------------------------------------- #
BUF_CHUNK = 1 << 20          # 1 Mo
BUF_SEG = 64                 # blocs par fichier de cache (64 Mo)
STREAM_DIR = os.path.join(os.environ.get("LOCALAPPDATA") or DATA_DIR, "IPTVPlayer", "tampon")
VIDEO_EXTS = (".mp4", ".mkv", ".avi", ".mov", ".m4v", ".ts", ".wmv", ".flv", ".webm", ".mpg", ".mpeg")


def fmt_size(n):
    n = float(n or 0)
    if n >= 1 << 30:
        return f"{n / (1 << 30):.2f} Go".replace(".", ",")
    if n >= 1 << 20:
        return f"{n / (1 << 20):.0f} Mo"
    return f"{n / 1024:.0f} Ko"


def fmt_secs(sec):
    sec = int(max(0, sec))
    if sec >= 3600:
        return f"{sec // 3600} h {sec % 3600 // 60:02d}"
    return f"{sec // 60}:{sec % 60:02d}"


def safe_filename(name):
    n = re.sub(r'[\\/:*?"<>|\r\n\t]+', " ", name or "").strip().strip(".")
    return re.sub(r"\s+", " ", n)[:150] or "video"


def _http_open(url, start=0, timeout=25):
    h = {"User-Agent": USER_AGENT, "Accept": "*/*", "Range": f"bytes={int(start)}-"}
    req = urllib.request.Request(url, headers=h)
    return urllib.request.urlopen(req, timeout=timeout, context=_SSL_CTX)


def _total_size(resp, start):
    cr = resp.headers.get("Content-Range") or ""
    m = re.search(r"/(\d+)", cr)
    if m:
        return int(m.group(1)), True
    cl = (resp.headers.get("Content-Length") or "").strip()
    if cl.isdigit():
        partial = getattr(resp, "status", 200) == 206
        return int(cl) + (start if partial else 0), partial
    return None, False


def _check_video(resp):
    ct = (resp.headers.get("Content-Type") or "").lower()
    if "text/html" in ct or "mpegurl" in ct or "json" in ct:
        raise IOError("ce flux ne peut pas être téléchargé (réponse du serveur : %s)" % (ct or "?"))
    return ct


class BufferSession:
    """Télécharge le film en avance (jusqu'à N minutes devant la lecture) et le sert au lecteur."""

    def __init__(self, url, ahead_secs, bps=1_000_000.0):
        self.url = url
        self.ahead_secs = float(ahead_secs)
        self.bps = float(bps)
        self.size = None
        self.ranges_ok = True
        self.ctype = "video/mp4"
        self.have = set()
        self.cv = threading.Condition()
        self.flock = threading.Lock()
        self.want = 0
        self.reader = 0
        self.closed = False
        self.failed = ""
        self.speed = 0.0
        self._hold = False
        self.dir = os.path.join(STREAM_DIR, uuid.uuid4().hex[:12])
        os.makedirs(self.dir, exist_ok=True)
        self.segs = {}
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    # -- stockage par segments (évite de remplir de zéros un gros fichier sous Windows)
    def _seg(self, c):
        k = c // BUF_SEG
        f = self.segs.get(k)
        if f is None:
            f = open(os.path.join(self.dir, f"{k}.bin"), "w+b")
            self.segs[k] = f
        return f, (c % BUF_SEG) * BUF_CHUNK

    def _write(self, c, data):
        with self.flock:
            f, off = self._seg(c)
            f.seek(off)
            f.write(data)

    def read(self, pos, n):
        c = pos // BUF_CHUNK
        with self.flock:
            f, off = self._seg(c)
            f.seek(off + pos - c * BUF_CHUNK)
            return f.read(n)

    def _prune(self):
        """Libère le disque : oublie les segments bien derrière la position de lecture."""
        if not self.ranges_ok:
            return
        keep_from = (self.want // BUF_CHUNK) // BUF_SEG - 2
        for k in [k for k in self.segs if k < keep_from]:
            with self.cv:
                self.have -= set(range(k * BUF_SEG, (k + 1) * BUF_SEG))
            with self.flock:
                try:
                    self.segs.pop(k).close()
                    os.remove(os.path.join(self.dir, f"{k}.bin"))
                except (OSError, KeyError):
                    pass

    # -- état
    def nchunks(self):
        return (self.size + BUF_CHUNK - 1) // BUF_CHUNK if self.size else 0

    def ahead_bytes(self, frm=None):
        if not self.size:
            return 0
        frm = self.want if frm is None else frm
        c = frm // BUF_CHUNK
        with self.cv:
            while c in self.have:
                c += 1
        return max(0, min(self.size, c * BUF_CHUNK) - frm)

    def ahead_ready(self, frm=None):
        return self.ahead_bytes(frm) / max(1.0, self.bps)

    def at_end(self, frm=None):
        frm = self.want if frm is None else frm
        return bool(self.size) and frm + self.ahead_bytes(frm) >= self.size

    def set_length(self, length_ms):
        if self.size and length_ms and length_ms > 0:
            self.bps = max(40_000.0, self.size / (length_ms / 1000.0))

    def set_want(self, pos):
        with self.cv:
            self.want = max(0, int(pos))
            self.cv.notify_all()

    def new_reader(self, pos):
        with self.cv:
            self.reader += 1
            self.want = pos
            self.cv.notify_all()
            return self.reader

    def moved(self, rid, pos):
        with self.cv:
            if rid == self.reader:
                self.want = pos
                self.cv.notify_all()

    def wait_chunk(self, c, rid):
        with self.cv:
            while c not in self.have and not self.closed:
                if rid == self.reader and self.want // BUF_CHUNK != c:
                    self.want = c * BUF_CHUNK
                    self.cv.notify_all()
                self.cv.wait(0.5)
            return not self.closed

    def close(self):
        with self.cv:
            self.closed = True
            self.cv.notify_all()
        threading.Thread(target=self._cleanup, daemon=True).start()

    def _cleanup(self):
        self.thread.join(40)
        with self.flock:
            for f in self.segs.values():
                try:
                    f.close()
                except OSError:
                    pass
            self.segs.clear()
        shutil.rmtree(self.dir, ignore_errors=True)

    # -- téléchargement en avance
    def _limit(self):
        return self.ahead_secs * self.bps

    def _start_chunk(self):
        c = (self.want // BUF_CHUNK) if self.ranges_ok else 0
        while c in self.have:
            c += 1
        return c

    def _run(self):
        tries = 0
        while not self.closed:
            with self.cv:
                if self.size is not None:
                    c = self._start_chunk()
                    if c >= self.nchunks():
                        self.cv.wait(0.5)
                        continue
                    if self._full(c):
                        self.cv.wait(0.5)
                        continue
                else:
                    c = 0
            try:
                self._fetch(c)
                tries = 0
            except Exception as e:  # coupure, délai dépassé… on reprend là où on en était
                if self.closed:
                    break
                tries += 1
                if self.size is None and tries >= 3:
                    self.failed = str(e) or e.__class__.__name__
                    break
                time.sleep(min(10.0, 1.5 * tries))

    def _full(self, c):
        """Hystérésis : on s'arrête à N minutes d'avance, on repart quand il en reste nettement moins."""
        lim = self._limit()
        ahead = c * BUF_CHUNK - self.want
        low = max(0.0, lim - max(0.2 * lim, 30 * self.bps))
        if self._hold:
            if ahead > low:
                return True
            self._hold = False
            return False
        if ahead >= lim:
            self._hold = True
            return True
        return False

    def _fetch(self, c):
        start = c * BUF_CHUNK
        resp = _http_open(self.url, start)
        try:
            if self.size is None:
                ct = _check_video(resp)
                size, rng = _total_size(resp, start)
                if not size:
                    raise IOError("taille du fichier inconnue")
                with self.cv:
                    self.size = size
                    self.ranges_ok = rng
                    if ct:
                        self.ctype = ct.split(";")[0]
                    self.cv.notify_all()
            elif start and getattr(resp, "status", 200) != 206:
                self.ranges_ok = False
                return
            cur = c
            t0, b0 = time.monotonic(), 0
            while not self.closed and cur < self.nchunks():
                with self.cv:
                    if cur in self.have:
                        return
                    wc = self.want // BUF_CHUNK
                    if self.ranges_ok and wc not in self.have and (wc > cur + 1 or wc < c):
                        return  # le lecteur a sauté ailleurs : on se replace
                    while not self.closed and self._full(cur):
                        self.cv.wait(0.5)
                        wc = self.want // BUF_CHUNK
                        if self.ranges_ok and wc not in self.have and (wc > cur + 1 or wc < c):
                            return
                n = min(BUF_CHUNK, self.size - cur * BUF_CHUNK)
                buf = bytearray()
                while len(buf) < n and not self.closed:
                    d = resp.read(min(256 * 1024, n - len(buf)))
                    if not d:
                        break
                    buf += d
                    b0 += len(d)
                    dt = time.monotonic() - t0
                    if dt >= 2.0:
                        self.speed = b0 / dt
                        t0, b0 = time.monotonic(), 0
                if len(buf) < n:
                    if self.closed:
                        return
                    raise IOError("connexion interrompue")
                self._write(cur, bytes(buf))
                with self.cv:
                    self.have.add(cur)
                    self.cv.notify_all()
                cur += 1
                if cur % BUF_SEG == 0:
                    self._prune()
        finally:
            try:
                resp.close()
            except Exception:
                pass


class _BufHandler(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *a):
        pass

    def do_HEAD(self):
        self._serve(True)

    def do_GET(self):
        self._serve(False)

    def _serve(self, head):
        sid = self.path.strip("/").split("/")[-1].split(".")[0]
        s = BUFFER.sessions.get(sid)
        if s is None:
            self.send_error(404)
            return
        t_end = time.monotonic() + 40
        while s.size is None and not s.failed and not s.closed and time.monotonic() < t_end:
            time.sleep(0.1)
        if not s.size:
            self.send_error(502)
            return
        size = s.size
        start, end, partial = 0, size - 1, False
        m = re.match(r"bytes=(\d*)-(\d*)", self.headers.get("Range") or "")
        if m and (m.group(1) or m.group(2)):
            partial = True
            if m.group(1):
                start = int(m.group(1))
                if m.group(2):
                    end = min(end, int(m.group(2)))
            else:
                start = max(0, size - int(m.group(2)))
        if start >= size:
            self.send_response(416)
            self.send_header("Content-Range", f"bytes */{size}")
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        self.send_response(206 if partial else 200)
        self.send_header("Content-Type", s.ctype or "application/octet-stream")
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Length", str(end - start + 1))
        if partial:
            self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        self.end_headers()
        if head:
            return
        rid = s.new_reader(start)
        pos = start
        try:
            while pos <= end:
                c = pos // BUF_CHUNK
                if not s.wait_chunk(c, rid):
                    break
                n = min((c + 1) * BUF_CHUNK, end + 1) - pos
                data = s.read(pos, n)
                if not data:
                    break
                self.wfile.write(data)
                pos += len(data)
                s.moved(rid, pos)
        except (ConnectionError, OSError, ValueError):
            pass


class BufferProxy:
    def __init__(self):
        self.sessions = {}
        self.server = None
        self.port = 0

    def _start(self):
        if self.server:
            return
        shutil.rmtree(STREAM_DIR, ignore_errors=True)
        self.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _BufHandler)
        self.server.daemon_threads = True
        self.port = self.server.server_address[1]
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def open(self, url, ahead_secs, bps=1_000_000.0):
        self._start()
        sid = uuid.uuid4().hex[:12]
        s = BufferSession(url, ahead_secs, bps)
        self.sessions[sid] = s
        ext = os.path.splitext(urllib.parse.urlparse(url).path)[1].lower()
        if ext not in VIDEO_EXTS:
            ext = ".mp4"
        return sid, s, f"http://127.0.0.1:{self.port}/b/{sid}{ext}"

    def close(self, sid):
        s = self.sessions.pop(sid, None)
        if s:
            s.close()

    def close_all(self):
        for sid in list(self.sessions):
            self.close(sid)


BUFFER = BufferProxy()


class DownloadManager(QtCore.QObject):
    """Téléchargements hors ligne (un à la fois, reprise automatique)."""
    changed = QtCore.Signal(str)
    _finished = QtCore.Signal(str)

    def __init__(self, win):
        super().__init__(win)
        self.win = win
        self.jobs = win.cfg.setdefault("downloads", [])
        for j in self.jobs:
            if j.get("state") == "downloading":
                j["state"] = "queued"
        self.speed = {}
        self._stop = {}
        self._active = None
        self._finished.connect(self._on_finished)
        QtCore.QTimer.singleShot(2500, self._next)

    def folder(self):
        d = self.win.cfg.get("download_dir") or os.path.join(os.path.expanduser("~"), "Videos", "IPTV Player")
        try:
            os.makedirs(d, exist_ok=True)
        except OSError:
            pass
        return d

    def job_for(self, url):
        return next((j for j in self.jobs if j.get("url") == url), None)

    def local_file(self, url):
        j = self.job_for(url)
        if j and j.get("state") == "done" and os.path.exists(j.get("path") or ""):
            return j["path"]
        return None

    def state(self, url):
        j = self.job_for(url)
        return j.get("state") if j else None

    def percent(self, j):
        return int(100 * j["done"] / j["size"]) if j.get("size") else 0

    def add(self, item, quiet=False):
        url = item["url"]
        j = self.job_for(url)
        if j and j.get("state") == "done" and not os.path.exists(j.get("path") or ""):
            self.jobs.remove(j)  # fichier effacé du disque entre-temps : on le retélécharge
            j = None
        if j:
            if j["state"] in ("error", "paused"):
                self.resume(j["id"])
            return j
        s = item.get("_series")
        if s:
            name = f"{s['name']} - S{int(s['season']):02d}E{int(s['num']):02d}"
            if s.get("ep_name") and not re.fullmatch(r"(Épisode|Episode)\s*\d+", s["ep_name"]):
                name += f" - {s['ep_name']}"
        else:
            name = item.get("_title") or item["name"]
        ext = os.path.splitext(urllib.parse.urlparse(url).path)[1].lower()
        if ext not in VIDEO_EXTS:
            ext = ".mp4"
        base = safe_filename(name)
        path = os.path.join(self.folder(), base + ext)
        k = 2
        while os.path.exists(path) or any(x.get("path") == path for x in self.jobs):
            path = os.path.join(self.folder(), f"{base} ({k}){ext}")
            k += 1
        j = {"id": uuid.uuid4().hex[:12], "url": url, "name": name,
             "kind": "episode" if s else item.get("kind", "movie"),
             "logo": (s or {}).get("logo") or item.get("logo") or "", "series": s, "group": item.get("group", ""),
             "opts": list(item.get("opts") or []), "path": path, "size": 0, "done": 0, "state": "queued",
             "error": "", "added": time.time()}
        self.jobs.append(j)
        self.win.save()
        self.changed.emit(j["id"])
        if not quiet:
            self.win.toast(f"Ajouté aux téléchargements : {name}")
        self._next()
        return j

    def play_item(self, j):
        it = {"name": j["name"], "url": j["url"], "kind": "episode" if j.get("series") else "movie",
              "logo": j.get("logo", ""), "group": j.get("group", ""), "opts": j.get("opts") or []}
        if j.get("series"):
            it["_series"] = j["series"]
        return it

    def _next(self):
        if self._active:
            return
        j = next((x for x in self.jobs if x.get("state") == "queued"), None)
        if not j:
            return
        self._active = j["id"]
        j["state"], j["error"] = "downloading", ""
        ev = threading.Event()
        self._stop[j["id"]] = ev
        threading.Thread(target=self._work, args=(j, ev), daemon=True).start()
        self.changed.emit(j["id"])

    def _work(self, j, ev):
        part = j["path"] + ".part"
        state, err, tries = "done", "", 0
        while True:
            try:
                os.makedirs(os.path.dirname(part), exist_ok=True)
                have = os.path.getsize(part) if os.path.exists(part) else 0
                resp = _http_open(j["url"], have, timeout=30)
                try:
                    _check_video(resp)
                    size, _rng = _total_size(resp, have)
                    if have and getattr(resp, "status", 200) != 206:
                        have = 0
                    if size:
                        j["size"] = size
                    j["done"] = have
                    t0, b0, last = time.monotonic(), have, 0.0
                    with open(part, "ab" if have else "wb") as f:
                        while True:
                            if ev.is_set():
                                state = "paused"
                                break
                            d = resp.read(256 * 1024)
                            if not d:
                                break
                            f.write(d)
                            j["done"] += len(d)
                            now = time.monotonic()
                            if now - t0 >= 2.0:
                                self.speed[j["id"]] = (j["done"] - b0) / (now - t0)
                                t0, b0 = now, j["done"]
                            if now - last >= 0.5:
                                last = now
                                self.changed.emit(j["id"])
                finally:
                    resp.close()
                if state == "paused":
                    break
                if j.get("size") and j["done"] < j["size"]:
                    raise IOError("connexion interrompue")
                os.replace(part, j["path"])
                state = "done"
                break
            except Exception as e:
                if ev.is_set():
                    state = "paused"
                    break
                tries += 1
                if tries <= 6:
                    time.sleep(3 * tries)
                    continue
                state, err = "error", (str(e) or e.__class__.__name__)
                break
        j["state"], j["error"] = state, err
        self.speed.pop(j["id"], None)
        self._finished.emit(j["id"])

    def _on_finished(self, jid):
        self._active = None
        self._stop.pop(jid, None)
        j = next((x for x in self.jobs if x["id"] == jid), None)
        if j is None:  # supprimé pendant le téléchargement
            for p in list(getattr(self, "_trash", {}).pop(jid, [])):
                try:
                    os.remove(p)
                except OSError:
                    pass
        elif j["state"] == "done":
            self.win.toast(f"Téléchargement terminé ✓  {j['name']}")
        elif j["state"] == "error":
            self.win.toast(f"Échec du téléchargement : {j['name']}")
        self.win.save()
        self.changed.emit(jid)
        QtCore.QTimer.singleShot(300, self._next)

    def pause(self, jid):
        j = next((x for x in self.jobs if x["id"] == jid), None)
        if not j:
            return
        if self._active == jid:
            self._stop[jid].set()
        elif j["state"] == "queued":
            j["state"] = "paused"
            self.changed.emit(jid)

    def resume(self, jid):
        j = next((x for x in self.jobs if x["id"] == jid), None)
        if j and j["state"] in ("paused", "error"):
            j["state"], j["error"] = "queued", ""
            self.win.save()
            self.changed.emit(jid)
            self._next()

    def remove(self, jid):
        j = next((x for x in self.jobs if x["id"] == jid), None)
        if not j:
            return
        self.jobs.remove(j)
        files = [j["path"] + ".part", j["path"]]
        if self._active == jid:
            self._trash = getattr(self, "_trash", {})
            self._trash[jid] = files
            self._stop[jid].set()
        else:
            for p in files:
                try:
                    os.remove(p)
                except OSError:
                    pass
        self.win.save()
        self.changed.emit(jid)

    def shutdown(self):
        for ev in self._stop.values():
            ev.set()


class DownloadRow(QtWidgets.QFrame):
    def __init__(self, win, job):
        super().__init__()
        self.win, self.job = win, job
        self.setObjectName("episode")
        h = QtWidgets.QHBoxLayout(self)
        h.setContentsMargins(12, 10, 16, 10)
        h.setSpacing(18)
        img = ImageLabel(win.images, 78, 116, radius=8)
        img.set_image(job.get("logo"), initials(job["name"]))
        h.addWidget(img)
        v = QtWidgets.QVBoxLayout()
        v.setSpacing(6)
        v.addStretch(1)
        self.title = label(job["name"], "eptitle", wrap=True)
        self.status = label("", "meta")
        self.bar = QtWidgets.QProgressBar()
        self.bar.setObjectName("thin")
        self.bar.setTextVisible(False)
        self.bar.setRange(0, 1000)
        self.bar.setFixedHeight(4)
        v.addWidget(self.title)
        v.addWidget(self.status)
        v.addWidget(self.bar)
        v.addStretch(1)
        h.addLayout(v, 1)
        self.b_play = button("▶  Lire", "primary", self._play)
        self.b_toggle = button("", "glass", self._toggle)
        self.b_del = button("🗑", "glass", self._delete)
        self.b_del.setToolTip("Supprimer")
        for b in (self.b_play, self.b_toggle, self.b_del):
            h.addWidget(b, 0, Qt.AlignmentFlag.AlignVCenter)
        self.refresh()

    def refresh(self):
        j, dm = self.job, self.win.downloads
        st = j.get("state")
        pct = dm.percent(j)
        self.bar.setValue(int(1000 * j["done"] / j["size"]) if j.get("size") else 0)
        self.bar.setVisible(st != "done")
        if st == "done":
            txt = f"✓ Téléchargé · {fmt_size(j.get('size') or j.get('done'))} · disponible sans connexion"
        elif st == "downloading":
            sp = dm.speed.get(j["id"], 0)
            txt = f"Téléchargement… {pct} %  ·  {fmt_size(j['done'])}" + (f" / {fmt_size(j['size'])}" if j.get("size") else "")
            if sp > 0:
                txt += f"  ·  {fmt_size(sp)}/s"
                if j.get("size"):
                    txt += f"  ·  reste {fmt_secs((j['size'] - j['done']) / sp)}"
        elif st == "queued":
            txt = "En attente…"
        elif st == "paused":
            txt = f"En pause · {pct} %"
        else:
            txt = f"⚠ Échec : {j.get('error') or 'erreur inconnue'}"
        self.status.setText(txt)
        self.b_play.setVisible(st == "done")
        self.b_toggle.setVisible(st != "done")
        self.b_toggle.setText({"downloading": "⏸  Pause", "queued": "⏸  Pause", "paused": "▶  Reprendre"}
                              .get(st, "↻  Réessayer"))

    def _play(self):
        self.win.play_items([self.win.downloads.play_item(self.job)], 0)

    def _toggle(self):
        if self.job.get("state") in ("downloading", "queued"):
            self.win.downloads.pause(self.job["id"])
        else:
            self.win.downloads.resume(self.job["id"])

    def _delete(self):
        r = QtWidgets.QMessageBox.question(self, APP_TITLE, f"Supprimer « {self.job['name']} » de vos téléchargements ?\n"
                                           "Le fichier sera effacé du PC.")
        if r == QtWidgets.QMessageBox.StandardButton.Yes:
            self.win.downloads.remove(self.job["id"])


class DownloadsPage(ScrollPage):
    def __init__(self, win):
        super().__init__()
        self.win = win
        self.rows = {}
        self.content.setObjectName("page")
        right = QtWidgets.QWidget()
        rl = QtWidgets.QHBoxLayout(right)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.addWidget(button("📁  Ouvrir le dossier", "glass", self._open_folder))
        rl.addWidget(button("Changer de dossier…", "glass", self._change_folder))
        self.v.addWidget(PageHeader(win, "Téléchargements", right))
        box = body_box(self.v, (34, 0, 34, 40), 12)
        self.info = label("", "rowsub", wrap=True)
        box.addWidget(self.info)
        self.list = QtWidgets.QVBoxLayout()
        self.list.setSpacing(8)
        box.addLayout(self.list)
        self.empty = label("Aucun téléchargement pour l'instant.\n\nSur la fiche d'un film, cliquez sur « ⬇ Télécharger » ; "
                           "sur une série, sur ⬇ à côté d'un épisode ou « Télécharger la saison ». Le fichier est enregistré "
                           "sur votre PC : il se regarde ensuite sans coupure, même sans connexion — idéal avec un petit débit.",
                           "empty", wrap=True)
        box.addWidget(self.empty)
        box.addStretch(1)
        win.downloads.changed.connect(self._changed)

    def rebuild(self):
        for r in self.rows.values():
            r.setParent(None)
            r.deleteLater()
        self.rows = {}
        for j in sorted(self.win.downloads.jobs, key=lambda x: -x.get("added", 0)):
            r = DownloadRow(self.win, j)
            self.rows[j["id"]] = r
            self.list.addWidget(r)
        self._info()

    def _info(self):
        jobs = self.win.downloads.jobs
        self.empty.setVisible(not jobs)
        done = [j for j in jobs if j.get("state") == "done"]
        total = sum(j.get("size") or 0 for j in done)
        self.info.setText(f"{len(done)} vidéo(s) disponible(s) hors ligne · {fmt_size(total)} · Dossier : "
                          f"{self.win.downloads.folder()}\nAstuce : un seul téléchargement à la fois. Si votre abonnement "
                          "n'autorise qu'une connexion, évitez de regarder un autre flux pendant un téléchargement.")

    def _changed(self, jid):
        known = {j["id"] for j in self.win.downloads.jobs}
        if jid in self.rows and jid in known:
            self.rows[jid].refresh()
            if self.rows[jid].job.get("state") in ("done", "error"):
                self._info()
        elif self.isVisible():
            self.rebuild()

    def _open_folder(self):
        QtGui.QDesktopServices.openUrl(QtCore.QUrl.fromLocalFile(self.win.downloads.folder()))

    def _change_folder(self):
        d = QtWidgets.QFileDialog.getExistingDirectory(self, "Dossier des téléchargements", self.win.downloads.folder())
        if d:
            self.win.cfg["download_dir"] = d
            self.win.save()
            self._info()


PILL_NAMES = {"backfloat", "nav", "navprofile", "glasspill", "roundbtn", "pilltab", "whitepill", "outlinepill", "searchpill",
              "primary", "glass", "sourcecombo", "seg"}


def round_pill(w):
    try:
        r = max(4, w.height() // 2 - 1)
        w.setProperty("_pillr", r)
        w.setStyleSheet((w.property("_basess") or "") + f"border-radius:{r}px;")
    except RuntimeError:
        pass


KEYBOARD = {"on": False}     # navigation au clavier / à la télécommande en cours (contour de focus visible)


class FocusRing(QtWidgets.QWidget):
    """Contour blanc arrondi autour de l'élément choisi au clavier (PC branché sur une TV, télécommande, manette)."""

    def __init__(self, win):
        super().__init__(win)
        self.win = win
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground)
        self.radius = 12
        self.hide()
        self._t = QtCore.QTimer(self, interval=60)
        self._t.timeout.connect(self.follow)

    def target_rect(self):
        fw = QtWidgets.QApplication.focusWidget()
        if fw is None or fw.window() is not self.win or not fw.isVisible():
            return None
        if isinstance(fw, CardView):
            idx = fw.currentIndex()
            if not idx.isValid():
                return None
            r = fw.visualRect(idx).adjusted(5, 5, -5, -5)
            vp = fw.viewport()
            r = r.intersected(vp.rect())
            if r.width() < 20:
                return None
            self.radius = 14
            return QtCore.QRect(vp.mapTo(self.win, r.topLeft()), r.size())
        if isinstance(fw, (QtWidgets.QLineEdit, QtWidgets.QComboBox)):
            return None
        r = fw.rect().adjusted(-3, -3, 3, 3)
        self.radius = min(r.height() / 2, 18)
        return QtCore.QRect(fw.mapTo(self.win, r.topLeft()), r.size())

    def follow(self):
        if not KEYBOARD["on"] or self.win._in_player():
            self.hide()
            self._t.stop()
            return
        r = self.target_rect()
        if r is None:
            self.hide()
            return
        self.setGeometry(r.adjusted(-3, -3, 3, 3))
        self.show()
        self.raise_()
        if not self._t.isActive():
            self._t.start()

    def paintEvent(self, _e):
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        p.setPen(QtGui.QPen(QtGui.QColor("#ffffff"), 3))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(QtCore.QRectF(self.rect()).adjusted(2.5, 2.5, -2.5, -2.5), self.radius, self.radius)


class KeyNav(QtCore.QObject):
    """Navigation avec les flèches, Entrée et Retour arrière dans toute l'interface (hors lecteur)."""
    ARROWS = (Qt.Key.Key_Left, Qt.Key.Key_Right, Qt.Key.Key_Up, Qt.Key.Key_Down)
    KEYS = ARROWS + (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Backspace)

    def __init__(self, win):
        super().__init__(win)
        self.win = win
        self.ring = FocusRing(win)
        win.stack.currentChanged.connect(lambda _i: QtCore.QTimer.singleShot(180, self._page_changed))

    def _page_changed(self):
        """Nouvelle page affichée pendant la navigation au clavier : le focus va sur son premier élément."""
        if not KEYBOARD["on"] or self.win._in_player():
            return
        fw = QtWidgets.QApplication.focusWidget()
        page = self.win.stack.currentWidget()
        if fw is not None and fw.isVisible() and page is not None and page.isAncestorOf(fw):
            return
        first = self._first_target()
        if first is not None:
            self._focus(first, None)

    def _ours(self, e):
        if e.key() not in self.KEYS or e.modifiers() & (Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.AltModifier):
            return None
        win = self.win
        aw = QtWidgets.QApplication.activeWindow()
        if win._in_player() or (aw is not None and aw is not win) or QtWidgets.QApplication.activeModalWidget():
            return None
        fw = QtWidgets.QApplication.focusWidget()
        if fw is not None and fw.window() is not win:
            return None                       # boîtes de dialogue : comportement normal
        if isinstance(fw, (QtWidgets.QTextEdit, QtWidgets.QPlainTextEdit, QtWidgets.QAbstractSpinBox, QtWidgets.QSlider)):
            return None
        if isinstance(fw, QtWidgets.QLineEdit) and e.key() not in (Qt.Key.Key_Up, Qt.Key.Key_Down):
            return None
        if isinstance(fw, QtWidgets.QComboBox) and e.key() in (Qt.Key.Key_Up, Qt.Key.Key_Down):
            return None
        if isinstance(fw, QtWidgets.QAbstractItemView) and fw.state() == QtWidgets.QAbstractItemView.State.EditingState:
            return None
        return fw or win

    def eventFilter(self, obj, e):
        t = e.type()
        if t in (QtCore.QEvent.Type.MouseButtonPress, QtCore.QEvent.Type.Wheel) and KEYBOARD["on"]:
            KEYBOARD["on"] = False
            self.ring.hide()
            self._repaint_views()
            return False
        if t == QtCore.QEvent.Type.ShortcutOverride:
            if self._ours(e) is not None:
                e.accept()                    # les flèches servent à naviguer, pas aux raccourcis du lecteur
            return False
        if t != QtCore.QEvent.Type.KeyPress:
            return False
        if e.key() == Qt.Key.Key_Tab or e.key() == Qt.Key.Key_Backtab:
            self._kb_on()
            return False
        fw = self._ours(e)
        if fw is None:
            return False
        if obj is not fw and not (isinstance(fw, QtWidgets.QAbstractItemView) and obj is fw.viewport()):
            return False                      # on ne traite l'événement qu'une fois
        self._kb_on()
        k = e.key()
        if k == Qt.Key.Key_Backspace:
            if isinstance(fw, QtWidgets.QLineEdit):
                return False
            self.win.back()
            return True
        if k in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            if isinstance(fw, CardView):
                idx = fw.currentIndex()
                if idx.isValid():
                    fw.item_clicked.emit(idx.data(ITEM_ROLE))
                return True
            if isinstance(fw, QtWidgets.QAbstractButton):
                fw.click()
                return True
            if isinstance(fw, ClickFrame):
                fw.clicked.emit()
                return True
            return False
        if isinstance(fw, CardView) and self._move_in_view(fw, k):
            return True
        target = self._spatial(fw, k)
        if target is not None:
            sb = self.win.sidebar
            if sb.isAncestorOf(target) and not sb.isAncestorOf(fw):
                cur = [b for b in sb.findChildren(QtWidgets.QAbstractButton) if b.isCheckable() and b.isChecked()
                       and b.isVisible()]
                target = cur[0] if cur else target
            self._focus(target, self._src_rect(fw))
            return True
        if fw is self.win or fw is None:
            first = self._first_target()
            if first is not None:
                self._focus(first, None)
                return True
        return isinstance(fw, (CardView, QtWidgets.QAbstractButton, ClickFrame))

    def _kb_on(self):
        if not KEYBOARD["on"]:
            KEYBOARD["on"] = True
            self._repaint_views()
        QtCore.QTimer.singleShot(0, self.ring.follow)

    def _repaint_views(self):
        fw = QtWidgets.QApplication.focusWidget()
        if isinstance(fw, CardView):
            fw.viewport().update()

    # -- dans une rangée / une grille
    def _move_in_view(self, v, k):
        n = v.model().rowCount()
        if n == 0:
            return False
        idx = v.currentIndex()
        if not idx.isValid():
            idx = v.model().index(0, 0)
            v.setCurrentIndex(idx)
            v.scrollTo(idx)
            return True
        if v.horizontal:
            if k in (Qt.Key.Key_Up, Qt.Key.Key_Down):
                return False
            row = idx.row() + (1 if k == Qt.Key.Key_Right else -1)
            if not 0 <= row < n:
                return False
            new = v.model().index(row, 0)
        else:
            act = {Qt.Key.Key_Left: QtWidgets.QAbstractItemView.CursorAction.MoveLeft,
                   Qt.Key.Key_Right: QtWidgets.QAbstractItemView.CursorAction.MoveRight,
                   Qt.Key.Key_Up: QtWidgets.QAbstractItemView.CursorAction.MoveUp,
                   Qt.Key.Key_Down: QtWidgets.QAbstractItemView.CursorAction.MoveDown}[k]
            new = v.moveCursor(act, Qt.KeyboardModifier.NoModifier)
            if not new.isValid() or new == idx:
                return False
            a, b = v.visualRect(idx), v.visualRect(new)
            ok = {Qt.Key.Key_Left: b.center().x() < a.center().x() and abs(b.center().y() - a.center().y()) < a.height() / 2,
                  Qt.Key.Key_Right: b.center().x() > a.center().x() and abs(b.center().y() - a.center().y()) < a.height() / 2,
                  Qt.Key.Key_Up: b.center().y() < a.center().y(),
                  Qt.Key.Key_Down: b.center().y() > a.center().y()}[k]
            if not ok:
                return False
        v.setCurrentIndex(new)
        v.scrollTo(new)
        self._ensure_visible(v, v.visualRect(new))
        QtCore.QTimer.singleShot(0, self.ring.follow)
        return True

    # -- d'un élément à l'autre (rangées, boutons, menu)
    def _candidates(self):
        out = []
        for w in self.win.findChildren(QtWidgets.QWidget):
            if not isinstance(w, (CardView, QtWidgets.QAbstractButton, ClickFrame, QtWidgets.QLineEdit)):
                continue
            if w.focusPolicy() == Qt.FocusPolicy.NoFocus or not w.isEnabled() or not w.isVisibleTo(self.win):
                continue
            if isinstance(w, CardView) and w.model().rowCount() == 0:
                continue
            if isinstance(w, QtWidgets.QAbstractButton) and isinstance(w.parentWidget(), QtWidgets.QAbstractItemView):
                continue
            if not w.isVisible() or w.width() < 6 or w.height() < 6:
                continue
            if self.win.player.isAncestorOf(w):
                continue
            out.append(w)
        return out

    def _grect(self, w):
        return QtCore.QRect(w.mapTo(self.win, QtCore.QPoint(0, 0)), w.size())

    def _src_rect(self, fw):
        if isinstance(fw, CardView) and fw.currentIndex().isValid():
            r = fw.visualRect(fw.currentIndex())
            return QtCore.QRect(fw.viewport().mapTo(self.win, r.topLeft()), r.size())
        if isinstance(fw, QtWidgets.QWidget) and fw is not self.win:
            return self._grect(fw)
        return None

    def _spatial(self, fw, k):
        src = self._src_rect(fw)
        if src is None:
            return None
        best, best_s = None, None
        for w in self._candidates():
            if w is fw:
                continue
            r = self._grect(w)
            if isinstance(w, CardView):
                vis = w.viewport().rect()
                r = QtCore.QRect(w.viewport().mapTo(self.win, vis.topLeft()), vis.size())
            if k == Qt.Key.Key_Down:
                main = r.top() - src.bottom()
                side = max(0, r.left() - src.right(), src.left() - r.right())
            elif k == Qt.Key.Key_Up:
                main = src.top() - r.bottom()
                side = max(0, r.left() - src.right(), src.left() - r.right())
            elif k == Qt.Key.Key_Right:
                main = r.left() - src.right()
                side = max(0, r.top() - src.bottom(), src.top() - r.bottom())
            else:
                main = src.left() - r.right()
                side = max(0, r.top() - src.bottom(), src.top() - r.bottom())
            if main < -8:
                continue
            score = max(main, 0) + side * 3
            if best_s is None or score < best_s:
                best, best_s = w, score
        return best

    def _first_target(self):
        page = self.win.stack.currentWidget()
        c = [w for w in self._candidates() if page is not None and page.isAncestorOf(w)]
        c.sort(key=lambda w: (self._grect(w).top(), self._grect(w).left()))
        main = [w for w in c if isinstance(w, QtWidgets.QAbstractButton) and w.objectName() in ("whitepill", "primary")]
        views = [w for w in c if isinstance(w, CardView)]
        return (main or views or c or [None])[0]

    def _focus(self, w, src):
        if not self.win.isActiveWindow():
            self.win.activateWindow()
        w.setFocus(Qt.FocusReason.TabFocusReason)
        if isinstance(w, CardView):
            n = w.model().rowCount()
            idx = w.currentIndex()
            if src is not None and n:
                # case la plus proche horizontalement de celle qu'on quitte
                best, bd = None, None
                vp = w.viewport()
                cx = vp.mapFrom(self.win, src.center()).x()
                for row in range(n):
                    i = w.model().index(row, 0)
                    vr = w.visualRect(i)
                    if not vp.rect().intersects(vr) and best is not None:
                        continue
                    d = abs(vr.center().x() - cx) + (0 if vp.rect().contains(vr.center()) else 10000)
                    if bd is None or d < bd:
                        best, bd = i, d
                idx = best or idx
            if not idx.isValid() and n:
                idx = w.model().index(0, 0)
            w.setCurrentIndex(idx)
            w.scrollTo(idx)
            self._ensure_visible(w, w.visualRect(idx))
        else:
            self._ensure_visible(w, None)
        QtCore.QTimer.singleShot(0, self.ring.follow)

    def _ensure_visible(self, w, item_rect):
        p = w.parentWidget()
        while p is not None and not isinstance(p, QtWidgets.QScrollArea):
            p = p.parentWidget()
        if p is None:
            return
        if item_rect is not None and isinstance(w, QtWidgets.QAbstractItemView):
            c = w.viewport().mapTo(p.widget(), item_rect.center())
            p.ensureVisible(c.x(), c.y(), 40, item_rect.height() // 2 + 60)
        else:
            p.ensureWidgetVisible(w, 40, 60)


class PillRounder(QtCore.QObject):
    """Qt ignore un border-radius supérieur à la moitié de la hauteur : on l'ajuste à chaque redimensionnement.
    Gère aussi le bouton « précédent » des souris (retour)."""
    def eventFilter(self, obj, ev):
        if ev.type() in (QtCore.QEvent.Type.Resize, QtCore.QEvent.Type.Show) \
                and obj is getattr(self.parent(), "content_area", None):
            self.parent()._scale_timer.start()
            self.parent()._place_overlays()
        if ev.type() == QtCore.QEvent.Type.MouseButtonPress and ev.button() == Qt.MouseButton.BackButton:
            win = self.parent()
            if win is not None and win.isActiveWindow():
                win.back()
                return True
        if ev.type() in (QtCore.QEvent.Type.Resize, QtCore.QEvent.Type.Show) and isinstance(obj, QtWidgets.QWidget) \
                and obj.objectName() in PILL_NAMES:
            r = max(4, obj.height() // 2 - 1)
            if obj.property("_pillr") != r:
                obj.setProperty("_pillr", r)
                obj.setStyleSheet((obj.property("_basess") or "") + f"border-radius:{r}px;")
        return False


class MainWindow(QtWidgets.QMainWindow):
    NAV = [("home", "home", "Accueil"), ("movie", "film", "Films"), ("series", "series", "Séries"),
           ("live", "tv", "Chaînes TV"), ("favorites", "heart", "Ma liste"), ("downloads", "download", "Téléchargés"),
           ("search", "search", "Recherche")]
    PILL = [("home", "Accueil"), ("movie", "Films"), ("series", "Séries"), ("live", "Chaînes TV")]

    def __init__(self):
        super().__init__()
        self._rounder = PillRounder(self)
        self._keynav = None
        self._scale_timer = QtCore.QTimer(self, singleShot=True, interval=180)
        self._scale_timer.timeout.connect(self._update_scale)
        QtWidgets.QApplication.instance().installEventFilter(self._rounder)
        QtCore.QTimer.singleShot(0, self._install_keynav)
        self.setWindowTitle(f"{APP_TITLE} — par {APP_AUTHOR}")
        self.setAcceptDrops(True)
        self.resize(1560, 920)
        self.cfg = load_config()
        self.downloads = DownloadManager(self)
        self.profile = None
        self.favorites = set()
        self.current_source = None
        self._raw = ([], "")
        self.lib = Library()
        self.images = ImageCache(self)
        self.meta = MetaService(self)
        self._tasks, self._task_seq, self._busy = {}, 0, 0
        self._fs = False
        self.history = []
        self._dirty = False
        self._build()
        self._save_timer = QtCore.QTimer(self, interval=20000)
        self._save_timer.timeout.connect(lambda: self._dirty and self.save())
        self._save_timer.start()
        profs = self.cfg["profiles"]
        last = next((p for p in profs if p["id"] == self.cfg.get("current_profile")), None)
        if len(profs) == 1 and not profs[0].get("pin"):
            self.select_profile(profs[0]["id"], go_home=False)
        else:
            if last and not last.get("pin"):
                self.select_profile(last["id"], go_home=False)
            self.show_profiles()
        self._reload_sources()
        QtCore.QTimer.singleShot(300, lambda: None if self.cfg["sources"] else self.add_source())

    # ------------------------------------------------------------ profils
    @property
    def pdata(self):
        pid = (self.profile or {}).get("id") or "p1"
        d = self.cfg["pdata"].setdefault(pid, {})
        d.setdefault("favorites", [])
        d.setdefault("progress", {})
        d.setdefault("live_hist", {})
        return d

    @property
    def progress(self):
        return self.pdata["progress"]

    def show_profiles(self):
        if self._fs:
            self.toggle_fullscreen()
        self._clear_history()
        self.profiles_page.manage = False
        self.profiles_page.rebuild()
        self.stack.setCurrentWidget(self.profiles_page)
        self._set_chrome(False)

    def pick_profile(self, pid):
        pr = next((p for p in self.cfg["profiles"] if p["id"] == pid), None)
        if not pr:
            return
        if pr.get("pin") and (not self.profile or self.profile["id"] != pid):
            code, ok = QtWidgets.QInputDialog.getText(self, pr["name"], f"Code PIN de {pr['name']} :",
                                                      QtWidgets.QLineEdit.EchoMode.Password)
            if not ok:
                return
            if code.strip() != pr["pin"]:
                QtWidgets.QMessageBox.warning(self, APP_TITLE, "Code PIN incorrect.")
                return
        self.select_profile(pid)

    def select_profile(self, pid, go_home=True):
        if self.profile:
            self.pdata["favorites"] = sorted(self.favorites)
        pr = next((p for p in self.cfg["profiles"] if p["id"] == pid), None)
        if not pr:
            return
        changed_kids = bool((self.profile or {}).get("kids")) != bool(pr.get("kids"))
        self.profile = pr
        self.cfg["current_profile"] = pid
        self.favorites = set(self.pdata["favorites"])
        self._update_avatar()
        self.save()
        if go_home:
            self._set_chrome(True)
            if changed_kids or True:
                self._apply_library(*self._raw)
            self.go_root("home")
            self.toast(f"Bonjour {pr['name']} 👋")

    def _update_avatar(self):
        if self.profile:
            self.b_avatar.setIcon(QtGui.QIcon(avatar_pixmap(self.profile, 34, circle=True)))
            self.b_avatar.setText("  " + self.profile["name"])
            self.b_avatar.setToolTip(f"Profil : {self.profile['name']}")
        m = self.avatar_menu
        m.clear()
        for pr in self.cfg["profiles"]:
            a = m.addAction(QtGui.QIcon(avatar_pixmap(pr, 22, circle=True)), pr["name"])
            a.setCheckable(True)
            a.setChecked(bool(self.profile) and pr["id"] == self.profile["id"])
            a.triggered.connect(lambda _c=False, pid=pr["id"]: self.pick_profile(pid))
        m.addSeparator()
        m.addAction("✎  Gérer les profils", lambda: (self.show_profiles(), self.profiles_page._toggle_manage()))
        m.addAction("⇄  Changer de profil", self.show_profiles)
        m.addSeparator()
        m.addAction("⚙  Paramètres", lambda: self.go_root("settings"))

    # ------------------------------------------------------------------ UI
    def _build(self):
        self._collapsed = bool(self.cfg.get("sidebar_collapsed"))
        self._root = "home"
        central = QtWidgets.QWidget()
        central.setObjectName("root")
        h = QtWidgets.QHBoxLayout(central)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(0)

        # ---- menu latéral
        self.sidebar = Sidebar()
        self.sidebar.setObjectName("sidebar")
        self.sidebar.setFixedWidth(290)
        sl = QtWidgets.QVBoxLayout(self.sidebar)
        sl.setContentsMargins(18, 18, 18, 14)
        sl.setSpacing(6)
        top = QtWidgets.QHBoxLayout()
        b_edit = button("Modifier", "glasspill", lambda: self.go_root("settings"))
        b_edit.setToolTip("Sources, clé TMDB, profils, stockage")
        top.addWidget(b_edit)
        top.addStretch(1)
        b_col = QtWidgets.QPushButton()
        b_col.setObjectName("roundbtn")
        b_col.setIcon(QtGui.QIcon(nav_icon("sidebar", "#ffffff", 26)))
        b_col.setIconSize(QtCore.QSize(24, 24))
        b_col.setToolTip("Masquer le menu")
        b_col.setCursor(Qt.CursorShape.PointingHandCursor)
        b_col.clicked.connect(lambda: self.set_collapsed(True))
        top.addWidget(b_col)
        sl.addLayout(top)
        sl.addSpacing(18)
        logo = ClickLabel()
        pm = logo_pixmap(46, SIDEBAR_TOP)
        if pm:
            logo.setPixmap(pm)
        else:
            logo.setText(APP_TITLE)
            logo.setObjectName("logo")
        logo.setCursor(Qt.CursorShape.PointingHandCursor)
        logo.clicked.connect(lambda: self.go_root("home"))
        sl.addWidget(logo, 0, Qt.AlignmentFlag.AlignLeft)
        sl.addSpacing(18)
        self.nav_btns = {}
        for key, icon, text in self.NAV:
            b = QtWidgets.QPushButton("  " + text)
            b.setObjectName("nav")
            b.setCheckable(True)
            b.setIcon(QtGui.QIcon(nav_icon(icon, ACCENT, 30)))
            b.setIconSize(QtCore.QSize(30, 30))
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.clicked.connect(lambda _c=False, k=key: self.go_root(k))
            self.nav_btns[key] = b
            sl.addWidget(b)
        self.b_avatar = QtWidgets.QToolButton()
        self.b_avatar.setObjectName("navprofile")
        self.b_avatar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.b_avatar.setIconSize(QtCore.QSize(34, 34))
        self.b_avatar.setPopupMode(QtWidgets.QToolButton.ToolButtonPopupMode.InstantPopup)
        self.b_avatar.setCursor(Qt.CursorShape.PointingHandCursor)
        self.b_avatar.setSizePolicy(QtWidgets.QSizePolicy.Policy.Expanding, QtWidgets.QSizePolicy.Policy.Fixed)
        self.avatar_menu = QtWidgets.QMenu(self)
        self.b_avatar.setMenu(self.avatar_menu)
        sl.addWidget(self.b_avatar)
        sl.addStretch(1)
        sl.addWidget(label("SOURCE", "h"))
        self.source_combo = QtWidgets.QComboBox()
        self.source_combo.setObjectName("sourcecombo")
        self.source_combo.currentIndexChanged.connect(self._combo_changed)
        sl.addWidget(self.source_combo)
        busy = QtWidgets.QHBoxLayout()
        self.busy_l = label("", "tiny")
        self.progress_bar = QtWidgets.QProgressBar()
        self.progress_bar.setObjectName("thin")
        self.progress_bar.setRange(0, 0)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setFixedSize(60, 4)
        self.progress_bar.hide()
        busy.addWidget(self.busy_l, 1)
        busy.addWidget(self.progress_bar)
        sl.addLayout(busy)
        sl.addSpacing(6)
        sig = label(APP_AUTHOR, "signature_side")
        sig.setToolTip(f"{APP_TITLE} {APP_VERSION} — conçu par {APP_AUTHOR}")
        sl.addWidget(sig, 0, Qt.AlignmentFlag.AlignLeft)
        h.addWidget(self.sidebar)

        # ---- contenu
        self.content_area = QtWidgets.QWidget()
        cl = QtWidgets.QVBoxLayout(self.content_area)
        cl.setContentsMargins(0, 0, 0, 0)
        self.stack = QtWidgets.QStackedWidget()
        cl.addWidget(self.stack)
        h.addWidget(self.content_area, 1)
        # Le lecteur (fenêtre native pour VLC) est À CÔTÉ du contenu, pas dedans : sinon Windows rend
        # la zone de contenu « native » et les boutons flottants (barre du haut, Retour) ne reçoivent plus les clics.
        self.player = PlayerPage(self)
        self._player_on = False
        h.addWidget(self.player, 1)
        self.player.hide()
        self.home = HomePage(self)
        self.profiles_page = ProfilesPage(self)
        self.pages = {
            "home": self.home,
            "movie": MediaPage(self, "movie"),
            "series": MediaPage(self, "series"),
            "live": LivePage(self),
            "categories": CategoriesPage(self),
            "favorites": FavoritesPage(self),
            "search": SearchPage(self),
            "downloads": DownloadsPage(self),
        }
        self.pages["settings"] = SettingsPage(self)
        for pg in self.pages.values():
            self.stack.addWidget(pg)
        self.stack.addWidget(self.profiles_page)
        self.stack.currentChanged.connect(lambda _i: self._apply_chrome())
        self.setCentralWidget(central)
        self.source_info = self.source_combo

        # ---- barre flottante (menu replié)
        self.pill = PillBar(self.content_area)
        self.back_btn = QtWidgets.QPushButton("‹  Retour", self.content_area)
        self.back_btn.setObjectName("backfloat")
        self.back_btn.setFixedHeight(46)
        self.back_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.back_btn.clicked.connect(self.back)
        self.back_btn.hide()
        pl = QtWidgets.QHBoxLayout(self.pill)
        pl.setContentsMargins(8, 6, 8, 6)
        pl.setSpacing(2)
        b_exp = QtWidgets.QPushButton()
        b_exp.setObjectName("pilltab")
        b_exp.setIcon(QtGui.QIcon(nav_icon("sidebar", "#ffffff", 26)))
        b_exp.setIconSize(QtCore.QSize(24, 24))
        b_exp.setToolTip("Afficher le menu")
        b_exp.clicked.connect(lambda: self.set_collapsed(False))
        pl.addWidget(b_exp)
        self.pill_btns = {}
        for key, text in self.PILL:
            b = QtWidgets.QPushButton(text)
            b.setObjectName("pilltab")
            b.setCheckable(True)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.clicked.connect(lambda _c=False, k=key: self.go_root(k))
            self.pill_btns[key] = b
            pl.addWidget(b)
        for key, icon in (("favorites", "heart"), ("downloads", "download"), ("search", "search")):
            b = QtWidgets.QPushButton()
            b.setObjectName("pilltab")
            b.setCheckable(True)
            b.setIcon(QtGui.QIcon(nav_icon(icon, "#ffffff", 24)))
            b.setIconSize(QtCore.QSize(22, 22))
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.clicked.connect(lambda _c=False, k=key: self.go_root(k))
            self.pill_btns[key] = b
            pl.addWidget(b)
        self.pill.hide()

        self.signature = QtWidgets.QLabel(APP_AUTHOR, self.content_area)
        self.signature.setObjectName("signature")
        self.signature.setToolTip(f"{APP_TITLE} {APP_VERSION} — conçu par {APP_AUTHOR}")
        self.signature.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.signature.adjustSize()

        self.toast_l = QtWidgets.QLabel(self)
        self.toast_l.setObjectName("toast")
        self.toast_l.hide()
        self._toast_t = QtCore.QTimer(self, singleShot=True, interval=3200)
        self._toast_t.timeout.connect(self.toast_l.hide)

        def sc(seq, fn):
            QtGui.QShortcut(QtGui.QKeySequence(seq), self, activated=fn)
        sc("F11", self.toggle_fullscreen)
        sc("Escape", self._escape)
        sc("Alt+Left", self.back)
        sc("Ctrl+F", lambda: (self.go_root("search"), self.pages["search"].focus()))
        sc("Ctrl+B", lambda: self.set_collapsed(not self._collapsed))
        sc("Space", lambda: self._in_player() and self.player.toggle_pause())
        sc("F", lambda: self._in_player() and self.toggle_fullscreen())
        sc("Left", lambda: self._in_player() and self.player.seek_rel(-10))
        sc("Right", lambda: self._in_player() and self.player.seek_rel(30))
        sc("Up", lambda: self._in_player() and (self.player.prev() if self._live() else self.player.volume_rel(5)))
        sc("Down", lambda: self._in_player() and (self.player.next() if self._live() else self.player.volume_rel(-5)))
        sc("PgUp", lambda: self._in_player() and self.player.prev())
        sc("PgDown", lambda: self._in_player() and self.player.next())
        sc("N", lambda: self._in_player() and self.player.next())
        self._chrome_on = True
        self._apply_chrome()
        self._update_avatar()
        self.go_root("home")

    # ---- menu : affichage / repli
    def set_collapsed(self, on):
        self._collapsed = bool(on)
        self.cfg["sidebar_collapsed"] = self._collapsed
        self._dirty = True
        self._apply_chrome()
        for ph in self.findChildren(PageHeader):
            ph.fit()
        for hc in self.findChildren(HeroCarousel):
            hc._frames.clear()
            hc._layout()
            hc.update()

    def _set_chrome(self, on):
        self._chrome_on = bool(on)
        self._apply_chrome()

    def _apply_chrome(self):
        if not hasattr(self, "pill") or not hasattr(self, "_chrome_on"):
            return
        cur = self._cur()
        special = cur is self.profiles_page or self._fs or cur is self.player
        show = self._chrome_on and not special
        self.sidebar.setVisible(show and not self._collapsed)
        self.pill.setVisible(show and self._collapsed and cur is not self.player)
        self._place_overlays()

    def _place_overlays(self):
        if not hasattr(self, "pill"):
            return
        cur = self._cur()
        show = self._chrome_on and not self._fs and cur is not self.profiles_page
        self.pill.setVisible(show and self._collapsed and cur is not self.player)
        if self.pill.isVisible():
            self.pill.ensurePolished()
            self.pill.resize(self.pill.sizeHint())
            self.pill.move((self.content_area.width() - self.pill.width()) // 2, 16)
            self.pill.raise_()
        sig_vis = show and self._collapsed and cur is not self.player
        if hasattr(self, "back_btn"):
            bvis = bool(self.history) and cur is not self.player and cur is not self.profiles_page \
                and not getattr(cur, "has_own_back", False)
            self.back_btn.setVisible(bvis)
            if bvis:
                self.back_btn.adjustSize()
                self.back_btn.move(22, 18)
                self.back_btn.raise_()
        self.signature.setVisible(sig_vis)
        if sig_vis:
            self.signature.adjustSize()
            self.signature.move(16, self.content_area.height() - self.signature.height() - 8)
            self.signature.raise_()

    def _mark(self, key):
        for group in (self.nav_btns, self.pill_btns):
            for k, b in group.items():
                b.setChecked(k == key)

    def _place_signature(self):
        self._place_overlays()

    def _in_player(self):
        return self._player_on

    def _install_keynav(self):
        if self._keynav is None:
            self._keynav = KeyNav(self)
            QtWidgets.QApplication.instance().installEventFilter(self._keynav)

    def _live(self):
        return bool(self.player.current) and self.player.current.get("kind") == "live"

    def _escape(self):
        if self._fs:
            self.toggle_fullscreen()
        elif self.history:
            self.back()

    def toast(self, text):
        self.toast_l.setText(text)
        self.toast_l.adjustSize()
        self.toast_l.move((self.width() - self.toast_l.width()) // 2, self.height() - self.toast_l.height() - 40)
        self.toast_l.raise_()
        self.toast_l.show()
        self._toast_t.start()

    # ------------------------------------------------------------- tâches
    def run_task(self, fn, on_done, on_fail=None, busy=None, quiet=False):
        self._task_seq += 1
        t = Task(self._task_seq, fn)
        t.signals.done.connect(self._task_done)
        t.signals.failed.connect(self._task_failed)
        self._tasks[self._task_seq] = (on_done, on_fail, t.signals, quiet)
        if not quiet:
            self._busy += 1
            self.progress_bar.show()
            if busy:
                self.busy_l.setText(busy)
        # les chargements de source passent avant les fiches et images en attente
        QtCore.QThreadPool.globalInstance().start(t, 0 if quiet else 10)

    def _task_end(self, quiet):
        if quiet:
            return
        self._busy = max(0, self._busy - 1)
        if not self._busy:
            self.progress_bar.hide()
            self.busy_l.setText("")

    def _task_done(self, payload):
        tid, res = payload
        on_done, _f, _s, quiet = self._tasks.pop(tid, (None, None, None, True))
        self._task_end(quiet)
        if on_done:
            safe_call(on_done, res)

    def _task_failed(self, payload):
        tid, msg = payload
        _d, on_fail, _s, quiet = self._tasks.pop(tid, (None, None, None, True))
        self._task_end(quiet)
        if on_fail:
            safe_call(on_fail, msg)
        else:
            QtWidgets.QMessageBox.warning(self, APP_TITLE, msg)

    # ---------------------------------------------------------- navigation
    def _clear_history(self):
        for w in self.history:
            if w is self.player:
                self.player.stop()
                self._show_player(False)
            elif w not in self.pages.values():
                self.stack.removeWidget(w)
                w.deleteLater()
        self.history = []

    def go_root(self, key):
        if self._fs:
            self.toggle_fullscreen()
        self._clear_history()
        if self.profile is None and self.cfg["profiles"]:
            return
        self._root = key
        page = self.pages[key]
        self._mark(key)
        if key in ("favorites", "categories", "search", "downloads"):
            page.rebuild()
        elif key == "settings":
            page.rebuild()
        elif key in ("home", "live", "movie", "series"):
            if getattr(page, "_built", -1) != getattr(self, "lib_ver", 0):
                page.rebuild()
                page._built = getattr(self, "lib_ver", 0)
            else:
                page.refresh_resume()
        self.stack.setCurrentWidget(page)
        if key == "search":
            page.focus()

    def browse(self, kind, country=None, group=None):
        """Liste complète (grille + filtres pays / catégories), ouverte par « › »."""
        pg = BrowsePage(self, kind)
        self.push(pg)
        pg.rebuild(country=country, group=group)

    def _update_scale(self):
        """27 pouces = 1 ; 49 pouces ultra-large, TV 4K : vignettes plus grandes, et donc plus nombreuses à l'écran."""
        a = self.content_area
        if a.width() < 200 or a.height() < 200:
            return
        UI.set(min(1.5, a.width() / 1300.0, a.height() / 820.0))

    def _cur(self):
        if getattr(self, "_player_on", False):
            return self.player
        return self.stack.currentWidget() if hasattr(self, "stack") else None

    def _show_player(self, on):
        if self._player_on == on:
            return
        self._player_on = on
        self.content_area.setVisible(not on)
        self.player.setVisible(on)
        self._apply_chrome()

    def push(self, w):
        self.history.append(w)
        if w is self.player:
            self._show_player(True)
            return
        self.stack.addWidget(w)
        self.stack.setCurrentWidget(w)
        self._show_player(False)

    def back(self):
        if not self.history:
            return
        if self._fs:
            self.toggle_fullscreen()
        w = self.history.pop()
        if w is self.player:
            self.player.stop()
            self._show_player(False)
        else:
            self.stack.removeWidget(w)
            w.deleteLater()
        target = self.history[-1] if self.history else self.pages[self._root_key()]
        if target is self.player:
            self._show_player(True)
            return
        self.stack.setCurrentWidget(target)
        if hasattr(target, "refresh_progress"):
            target.refresh_progress()
        if hasattr(target, "refresh_resume"):
            target.refresh_resume()

    def _root_key(self):
        return getattr(self, "_root", "home")

    def open_item(self, it):
        if not it:
            return
        if it.get("kind") == "live":
            self.play_items([it], 0)
        elif it.get("kind") in ("movie", "series"):
            if it.get("_lib"):
                it = it["_lib"]
            self.push(DetailPage(self, it))
        elif it.get("kind") == "person":
            self.open_person(it)

    def open_collection(self, title, cards, loader=None):
        self.push(CollectionPage(self, title, cards, loader))

    def open_person(self, person):
        self.push(PersonPage(self, person))

    def play_items(self, items, index, resume=True):
        if not self.player.available():
            QtWidgets.QMessageBox.warning(self, APP_TITLE,
                                          "VLC 64 bits est introuvable : installez-le depuis videolan.org puis relancez.")
            return
        if not self._player_on:
            self.push(self.player)
        self.player.play_list(items, index, resume)

    def note_live(self, item):
        if item and item.get("kind") == "live" and self.profile:
            h = self.pdata["live_hist"]
            h[item["url"]] = h.get(item["url"], 0) + 1
            if len(h) > 300:
                for k, _v in sorted(h.items(), key=lambda kv: kv[1])[:len(h) - 300]:
                    h.pop(k, None)
            self._dirty = True

    def toggle_fullscreen(self):
        in_player = self._in_player()
        if not self._fs:
            self._fs_max = self.isMaximized()
            self._fs = True
            self._apply_chrome()
            if in_player:
                self.player.set_immersive(True)
            self.showFullScreen()
        else:
            self._fs = False
            self._apply_chrome()
            self.player.set_immersive(False)
            self.showNormal()
            if self._fs_max:
                self.showMaximized()
        self._place_signature()

    # ------------------------------------------------------------- sources
    def _reload_sources(self, select_id=None):
        cb = self.source_combo
        cb.blockSignals(True)
        cb.clear()
        for s in self.cfg["sources"]:
            cb.addItem(("📡 " if s["type"] == "xtream" else "📄 ") + s["name"], s["id"])
        cb.addItem("＋ Ajouter une source…", "__add__")
        idx = cb.findData(select_id or self.cfg.get("last_source"))
        if idx < 0 and self.cfg["sources"]:
            idx = 0
        cb.setCurrentIndex(max(0, idx) if self.cfg["sources"] else -1)
        cb.blockSignals(False)
        sid = cb.currentData()
        if sid and sid != "__add__":
            self.set_source(sid)
        else:
            self.current_source = None
            self._apply_library([], "")

    def _combo_changed(self, _i):
        sid = self.source_combo.currentData()
        if sid == "__add__":
            self.source_combo.blockSignals(True)
            prev = self.source_combo.findData((self.current_source or {}).get("id"))
            self.source_combo.setCurrentIndex(prev)
            self.source_combo.blockSignals(False)
            self.add_source()
        elif sid:
            self.set_source(sid)

    def _source_by_id(self, sid):
        return next((s for s in self.cfg["sources"] if s["id"] == sid), None)

    def set_source(self, sid, force=False):
        src = self._source_by_id(sid)
        if not src:
            return
        changed = not self.current_source or self.current_source["id"] != sid
        self.current_source = src
        self.cfg["last_source"] = sid
        i = self.source_combo.findData(sid)
        if i >= 0 and self.source_combo.currentIndex() != i:
            self.source_combo.blockSignals(True)
            self.source_combo.setCurrentIndex(i)
            self.source_combo.blockSignals(False)
        self.save()
        path = cache_path(sid)
        if not force and os.path.exists(path):
            try:
                with open(path, encoding="utf-8") as f:
                    data = json.load(f)
                self._apply_source_data(src, data)
                return
            except Exception:
                pass
        if changed:
            self._apply_library([], "")
        self.run_task(lambda: fetch_source(src), lambda d, s=src: self._fetched(s, d),
                      lambda e, s=src: QtWidgets.QMessageBox.warning(self, APP_TITLE,
                                                                     f"Impossible de charger « {s['name']} » :\n\n{e}"),
                      busy=f"Chargement de « {src['name']} »…")

    def _fetched(self, src, data):
        try:
            with open(cache_path(src["id"]), "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False)
        except OSError:
            pass
        if self.current_source and self.current_source["id"] == src["id"]:
            self._apply_source_data(src, data)
            self.toast(f"« {src['name']} » chargée : {len(data.get('items') or []):,} éléments".replace(",", " "))

    def _apply_source_data(self, src, data):
        info = [x for x in (data.get("info"), f"Mise à jour : {data['updated']}" if data.get("updated") else "") if x]
        self._apply_library(data.get("items") or [], "\n".join(info))

    def _apply_library(self, items, info):
        self._raw = (items, info)
        if (self.profile or {}).get("kids"):
            items = [i for i in items if not ADULT_RE.search(f"{i['group']} {i['name']}")]
        self.lib.set_items(items)
        c = Counter(i["kind"] for i in items)
        self.source_combo.setToolTip(info)
        for k in ("live", "movie", "series"):
            self.nav_btns[k].setToolTip(f"{c.get(k, 0):,} éléments".replace(",", " "))
        self.lib_ver = getattr(self, "lib_ver", 0) + 1
        root = self._root_key()
        for k in ("home", "live", "movie", "series"):
            self.pages[k]._built = -1
        if root in ("home", "live", "movie", "series"):
            self.pages[root].rebuild()
            self.pages[root]._built = self.lib_ver
        elif root in ("favorites", "settings", "categories", "search") and not self.history:
            self.pages[root].rebuild()

    def add_source(self, tab=None):
        dlg = SourceDialog(self, start_tab=tab)
        if dlg.exec() and dlg.result_source:
            self._add_source(dlg.result_source)

    def add_file_source(self):
        self.add_source(SourceDialog.TAB_FILE)

    def _add_source(self, src):
        self.cfg["sources"].append(src)
        self.save()
        self._reload_sources(src["id"])
        self.pages["settings"].rebuild()

    def replace_source_file(self, sid):
        src = self._source_by_id(sid)
        if not src or not src.get("file"):
            return
        dlg = SourceDialog(self, replace=src)
        if dlg.exec() and dlg.result_source:
            self.save()
            self.set_source(sid, force=True)
            self.toast(f"Liste « {src['name']} » mise à jour.")

    def open_playlist_files(self, paths):
        """Fichiers M3U déposés sur la fenêtre ou ouverts avec l'application."""
        for p in paths:
            if not (os.path.isfile(p) and p.lower().endswith(M3U_EXTS)):
                continue
            ap = os.path.abspath(p)
            same = [s for s in self.cfg["sources"] if s.get("file_orig") and os.path.normcase(s["file_orig"]) == os.path.normcase(ap)]
            try:
                if same:
                    import_playlist(same[0]["id"], ap)
                    self.set_source(same[0]["id"], force=True)
                    self.toast(f"Liste « {same[0]['name']} » mise à jour.")
                else:
                    self._add_source(file_source(ap))
                    self.toast(f"Liste « {os.path.basename(ap)} » ajoutée.")
            except Exception as e:
                QtWidgets.QMessageBox.warning(self, APP_TITLE, str(e))

    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls() and any(u.isLocalFile() and u.toLocalFile().lower().endswith(M3U_EXTS)
                                          for u in e.mimeData().urls()):
            e.acceptProposedAction()

    def dropEvent(self, e):
        self.open_playlist_files([u.toLocalFile() for u in e.mimeData().urls() if u.isLocalFile()])

    def delete_source(self, sid):
        src = self._source_by_id(sid)
        if not src:
            return
        r = QtWidgets.QMessageBox.question(self, APP_TITLE, f"Supprimer la source « {src['name']} » ?")
        if r != QtWidgets.QMessageBox.StandardButton.Yes:
            return
        self.cfg["sources"] = [s for s in self.cfg["sources"] if s["id"] != sid]
        for f in (cache_path(sid), os.path.join(PLAYLIST_DIR, sid + ".m3u")):
            try:
                os.remove(f)
            except OSError:
                pass
        if self.cfg.get("last_source") == sid:
            self.cfg.pop("last_source", None)
            self.current_source = None
        self.save()
        self._reload_sources()

    def fetch_epg(self, item, cb):
        src = self.current_source
        if not src or src["type"] != "xtream":
            return
        self.run_task(lambda: xtream_client(src).short_epg(item["stream_id"]),
                      lambda progs, it=item: cb(it, progs), lambda _e: None, quiet=True)

    # --------------------------------------------------------- tendances
    def trending_channels(self, n):
        live = self.lib.by_kind["live"]
        if not live:
            return []
        by_url = {i["url"]: i for i in live}
        hist = self.pdata["live_hist"]
        out, seen = [], set()
        for url, _c in sorted(hist.items(), key=lambda kv: -kv[1]):
            if url in by_url and url not in seen:
                out.append(by_url[url])
                seen.add(url)
        for i in live:
            if i["url"] in self.favorites and i["url"] not in seen:
                out.append(i)
                seen.add(i["url"])
        top = Counter(i["country"] for i in live if i["country"] != "ZZ").most_common(1)
        code = top[0][0] if top else None
        for i in live:
            if len(out) >= n:
                break
            if (code is None or i["country"] == code) and i["url"] not in seen:
                out.append(i)
                seen.add(i["url"])
        return out[:n]

    def category_items(self, kind, n, special=False):
        pool = self.lib.by_kind.get(kind) or []
        counts = Counter(i["group"] for i in pool)
        first_img = {}
        for i in pool:
            if i.get("logo") and i["group"] not in first_img:
                first_img[i["group"]] = i["logo"]
        unit = "chaînes" if kind == "live" else "titres"
        out = []
        if special:
            out.append({"kind": "category", "special": True, "_ckind": kind,
                        "icon": {"movie": "🎬", "series": "🎞", "live": "📺"}[kind],
                        "name": {"movie": "Films par catégories", "series": "Séries par catégories",
                                 "live": "Chaînes par catégories"}[kind]})
        for g, c in counts.most_common(n):
            cc = detect_country(g) if kind == "live" else "ZZ"
            u = unit if c > 1 else unit[:-1]
            sub = f"{country_name(cc)} · {c} {u}" if cc != "ZZ" else f"{c} {u}"
            out.append({"kind": "category", "name": pretty_group(g), "sub": sub, "logo": first_img.get(g, ""),
                        "_ckind": kind, "_group": g, "url": f"cat:{kind}:{g}"})
        return out

    def open_category(self, it):
        if it.get("special"):
            self.go_root("categories")
            self.pages["categories"].show_kind(it["_ckind"])
        else:
            self.browse(it["_ckind"], group=it["_group"])

    # ----------------------------------------------------------- favoris
    def toggle_favorite(self, it):
        if it["url"] in self.favorites:
            self.favorites.discard(it["url"])
            self.toast("Retiré de Ma liste")
        else:
            self.favorites.add(it["url"])
            self.toast("Ajouté à Ma liste ♥")
        self.save()

    # ---------------------------------------------------------- progression
    def save_progress(self, item, pos, length):
        prog = self.progress
        done = length > 0 and pos / length >= 0.95
        entry = {"pos": int(pos), "len": int(length), "t": time.time(), "done": done,
                 "src": (self.current_source or {}).get("id"),
                 "item": {k: v for k, v in item.items() if k in ("name", "url", "logo", "kind", "opts", "group")}}
        if item.get("_series"):
            entry["series"] = item["_series"]
        prog[item["url"]] = entry
        if len(prog) > 500:
            for k, _v in sorted(prog.items(), key=lambda kv: kv[1].get("t", 0))[:len(prog) - 500]:
                prog.pop(k, None)
        self._dirty = True

    def continue_items(self):
        src = (self.current_source or {}).get("id")
        out, seen_series = [], set()
        for url, e in sorted(self.progress.items(), key=lambda kv: -kv[1].get("t", 0)):
            if e.get("src") != src or e.get("done") or not e.get("len"):
                continue
            it = dict(e["item"])
            s = e.get("series")
            if s:
                if s["url"] in seen_series:
                    continue
                seen_series.add(s["url"])
                it["_title"] = s["name"]
                it["sub"] = f"S{s['season']} E{s['num']} · {s.get('ep_name') or ''}".strip(" ·")
                it["logo"] = s.get("logo") or it.get("logo")
                it["_series"] = True
                it["_remain"] = f"S{s['season']}, E{s['num']}  •  {max(1, (e['len'] - e['pos']) // 60000)}mn"
            else:
                it["_title"] = clean_title(it["name"])[0]
                it["sub"] = f"Reste {fmt_ms(e['len'] - e['pos'])}"
                it["_remain"] = f"{max(1, (e['len'] - e['pos']) // 60000)}mn"
            it["progress"] = e["pos"] / e["len"]
            it["_entry_url"] = url
            it["_lib"] = self.lib.by_url.get(s["url"] if s else url)
            out.append(it)
            if len(out) >= 20:
                break
        return out

    def resume_entry(self, it):
        e = self.progress.get(it.get("_entry_url") or it["url"])
        if not e:
            return
        item = dict(e["item"])
        if e.get("series"):
            item["_series"] = e["series"]
            s = e["series"]
            item["name"] = f"{s['name']} — S{s['season']:02d}E{s['num']:02d}  {s.get('ep_name') or ''}"
        self.play_items([item], 0, resume=True)

    # -------------------------------------------------------------- divers
    def save(self):
        if self.profile:
            self.pdata["favorites"] = sorted(self.favorites)
        try:
            save_config(self.cfg)
            self._dirty = False
        except OSError:
            pass

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._place_signature()
        if self.toast_l.isVisible():
            self.toast_l.move((self.width() - self.toast_l.width()) // 2,
                              self.height() - self.toast_l.height() - 40)

    def closeEvent(self, e):
        self.player.shutdown()
        self.downloads.shutdown()
        BUFFER.close_all()
        self.save()
        super().closeEvent(e)


# --------------------------------------------------------------------------- #
#  Thème
# --------------------------------------------------------------------------- #
STYLE = """
* { font-family:'Segoe UI', 'Segoe UI Emoji', sans-serif; }
QWidget { background:transparent; color:#e8eaf0; font-size:10pt; }
QMainWindow, #root, QStackedWidget, #page, QScrollArea, QScrollArea > QWidget > QWidget { background:%(BG)s; }
QDialog, QMessageBox { background:#161821; }
#sidebar QLabel, #sidebar QWidget { background:transparent; }
QPushButton#nav { text-align:left; padding:11px 16px; border:0; border-radius:25px; color:white;
                  font-size:15pt; font-weight:600; background:transparent; }
QPushButton#nav:hover { background:rgba(255,255,255,0.06); }
QPushButton#nav:checked { background:rgba(255,255,255,0.13); }
QToolButton#navprofile { text-align:left; padding:9px 14px; border:0; border-radius:25px; color:white;
                         font-size:15pt; font-weight:600; background:transparent; }
QToolButton#navprofile:hover { background:rgba(255,255,255,0.06); }
QToolButton#navprofile::menu-indicator { image:none; width:0; }
QPushButton#glasspill { background:rgba(255,255,255,0.10); border:1px solid rgba(255,255,255,0.14); border-radius:22px;
                        padding:10px 22px; font-size:13pt; font-weight:600; color:white; }
QPushButton#glasspill:hover { background:rgba(255,255,255,0.18); }
QPushButton#roundbtn { background:rgba(255,255,255,0.10); border:1px solid rgba(255,255,255,0.14); border-radius:24px;
                       min-width:48px; max-width:48px; min-height:48px; max-height:48px; padding:0; }
QPushButton#roundbtn:hover { background:rgba(255,255,255,0.18); }
QPushButton#pilltab { background:transparent; border:0; border-radius:20px; padding:9px 18px; color:white;
                      font-size:13.5pt; font-weight:600; }
QPushButton#pilltab:hover { background:rgba(255,255,255,0.08); }
QPushButton#pilltab:checked { background:rgba(10,14,22,0.75); color:%(ACCENT)s; }
QPushButton#heroarrow { background:rgba(10,14,22,0.55); border:1px solid rgba(255,255,255,0.18); border-radius:25px;
                        color:white; font-size:24pt; font-weight:700; padding:0 0 4px 0; }
QPushButton#heroarrow:hover { background:rgba(10,14,22,0.85); }
QPushButton#backfloat { background:rgba(10,14,22,0.62); border:1px solid rgba(255,255,255,0.18); border-radius:23px;
                        color:white; font-size:12.5pt; font-weight:700; padding:0 18px 2px 14px; }
QPushButton#backfloat:hover { background:rgba(30,36,48,0.92); }
#buflabel { color:#b9c6da; font-size:10pt; font-weight:600; }
QPushButton#epdl { background:rgba(255,255,255,0.08); border:1px solid rgba(255,255,255,0.14); border-radius:12px;
                   color:white; font-size:11pt; font-weight:700; padding:0; }
QPushButton#epdl:hover { background:rgba(255,255,255,0.18); border-color:%(ACCENT)s; }
QPushButton#whitepill { background:white; color:black; border:0; border-radius:28px; padding:14px 36px;
                        font-size:15pt; font-weight:800; }
QPushButton#whitepill:hover { background:#e9ecf2; }
#outlinepill { background:rgba(0,0,0,0.35); border:1.5px solid rgba(255,255,255,0.8); border-radius:15px;
               padding:4px 14px; color:white; font-size:11pt; font-weight:700; }
#herotitle2 { font-size:34pt; font-weight:900; color:white; background:transparent; }
#herometa { font-size:12.5pt; font-weight:600; color:#e6e8ee; background:transparent; }
#pagetitle2 { font-size:32pt; font-weight:900; color:white; background:transparent; }
QLineEdit#searchpill { background:rgba(255,255,255,0.10); border:1px solid rgba(255,255,255,0.14); border-radius:24px;
                       padding:10px 16px; font-size:13.5pt; color:white; }
QLineEdit#searchpill:focus { border-color:%(ACCENT)s; }
#signature_side { font-family:'Segoe Script', 'Brush Script MT', 'Lucida Handwriting', cursive; font-size:17pt;
                  font-style:italic; color:rgba(255,255,255,0.8); padding-left:6px; }
#logo { font-size:17pt; font-weight:800; }
QPushButton#tab { background:transparent; border:0; border-radius:0; border-bottom:3px solid transparent;
                  padding:22px 2px 19px 2px; margin:0 13px; color:#aeb3c2; font-size:11.5pt; font-weight:600; }
QPushButton#tab:hover { color:white; }
QPushButton#tab:checked { color:white; border-bottom:3px solid %(ACCENT)s; }
QPushButton#iconbtn { background:transparent; border:0; border-radius:19px; min-width:38px; max-width:38px;
                      min-height:38px; max-height:38px; padding:0; font-size:14pt; color:#dfe2ea; }
QPushButton#iconbtn:hover, QPushButton#iconbtn:checked { background:#1c2029; }
QComboBox#sourcecombo { background:rgba(255,255,255,0.08); border:1px solid rgba(255,255,255,0.12); border-radius:16px;
                        padding:6px 12px; color:white; }
QToolButton#avatar { background:transparent; border:0; padding:0; }
QToolButton#avatar::menu-indicator { image:none; width:0; }
#rowsub { color:#9aa0b2; font-size:12pt; }
#livepill { background:%(ACCENT)s; color:white; font-weight:800; font-size:9pt; border-radius:6px; padding:3px 9px; }
QPushButton#seg { background:#141821; border:1px solid #242938; border-radius:16px; padding:7px 18px; font-weight:600; }
QPushButton#seg:checked { background:white; color:#0e1016; border-color:white; }
#profiles { background:%(BG)s; }
#whotitle { font-size:30pt; font-weight:700; color:white; }
#pname { font-size:12pt; color:#c9ccd6; font-weight:600; }
#ptile { background:transparent; border-radius:14px; }
#ptile:hover { background:#161a23; }
#ptile:hover #pname { color:white; }
#addtile { background:#141821; border:2px dashed #3a4050; border-radius:24px; color:#8b91a3; font-size:40pt; }
#editbadge { background:rgba(0,0,0,0.55); color:white; font-size:34pt; border-radius:24px; }
QPushButton#emoji { background:#141821; border:1px solid #242938; border-radius:10px; font-size:17pt; padding:0;
                    font-family:'Segoe UI Emoji'; }
QPushButton#emoji:hover { border-color:%(ACCENT)s; }
QPushButton#danger { background:transparent; border:1px solid #6b1f23; color:#ff6b70; }
QPushButton#danger:hover { background:#2a1214; }
QPushButton#outline { background:transparent; border:1px solid #6b7183; color:#c9ccd6; padding:10px 26px;
                      font-size:11pt; letter-spacing:1px; border-radius:6px; }
QPushButton#outline:hover { border-color:white; color:white; }
#h { color:#6b7183; font-size:8pt; font-weight:700; letter-spacing:1px; padding:8px 4px 4px; }
#tiny { color:#6b7183; font-size:8pt; }
#signature { font-family:'Segoe Script', 'Brush Script MT', 'Lucida Handwriting', cursive; font-size:15pt;
             font-style:italic; color:rgba(255,255,255,0.85); background:rgba(10,12,16,0.82);
             border-radius:10px; padding:0 12px 2px 10px; }
#filters { background:#0b0d12; border-right:1px solid #1c1f28; }
#pagetitle { font-size:22pt; font-weight:800; }
#rowtitle { font-size:19pt; font-weight:800; color:white; }
#herotitle { font-size:30pt; font-weight:800; color:white; }
#kicker { color:%(ACCENT)s; font-size:9pt; font-weight:800; letter-spacing:2px; }
#tagline { color:#c9cbd6; font-style:italic; font-size:11pt; }
#meta { color:#a3a8b8; font-size:10pt; }
#crew { color:#d5d8e2; font-size:10pt; }
#overview { color:#d5d8e2; font-size:11pt; line-height:150%%; }
#empty { color:#6b7183; font-size:12pt; padding:40px; }
#dots { color:#8b91a3; font-size:9pt; letter-spacing:2px; }
#chip { background:rgba(255,255,255,0.08); border:1px solid rgba(255,255,255,0.12); border-radius:9px;
        padding:3px 11px; color:#dfe2ea; font-size:9pt; }
#agechip { background:transparent; border:1.5px solid #c9ccd6; border-radius:5px; padding:1px 7px;
           color:#e8eaf0; font-size:9pt; font-weight:700; }
#seen { color:#3ecf8e; font-weight:700; }
QPushButton { background:#1c1f29; border:1px solid #2a2e3b; border-radius:9px; padding:8px 16px; color:#e8eaf0; }
QPushButton:hover { background:#262a37; }
QPushButton#primary { background:white; border:0; color:black; font-weight:800; font-size:11pt; padding:11px 26px;
                      border-radius:22px; }
QPushButton#primary:hover { background:#e9ecf2; }
QPushButton#primary:disabled { background:#3a3f4a; color:#8b91a3; }
QPushButton#glass { background:rgba(255,255,255,0.10); border:1px solid rgba(255,255,255,0.16); color:white;
                    font-weight:600; font-size:10.5pt; padding:10px 18px; border-radius:22px; }
QPushButton#glass:hover { background:rgba(255,255,255,0.18); }
QPushButton#link { background:transparent; border:0; color:%(ACCENT)s; font-weight:700; padding:2px 8px; }
QPushButton#link:hover { color:#7db7ff; }
QPushButton#arrow { background:rgba(255,255,255,0.06); border:0; border-radius:15px; padding:0; font-size:14pt; color:#c9ccd6; }
QPushButton#arrow:hover { background:%(ACCENT)s; color:white; border-color:%(ACCENT)s; }
QPushButton#seasonchip { background:#161923; border:1px solid #262a37; border-radius:15px; padding:7px 16px; font-weight:600; }
QPushButton#seasonchip:checked { background:white; color:#0d0e12; border-color:white; }
QPushButton#ctrl { background:transparent; border:0; border-radius:8px; padding:6px 10px; font-size:11pt; }
QPushButton#ctrl:hover { background:rgba(255,255,255,0.12); }
QPushButton#ctrl:disabled { color:#4b4f5c; }
QPushButton#ctrl::menu-indicator { image:none; width:0; }
QPushButton#ctrlmain { background:white; color:#0d0e12; border:0; border-radius:19px; min-width:40px; min-height:40px;
                       max-width:40px; max-height:40px; padding:0; font-size:13pt; }
#player { background:black; }
#pbar { background:#07080b; }
#ptitle { font-size:13pt; font-weight:700; }
#time { color:#c9ccd6; font-size:9pt; min-width:54px; }
#live { color:#ff4d5e; font-weight:800; font-size:9pt; letter-spacing:1px; }
#side { background:#0b0c10; border-left:1px solid #1b1d25; }
#episode { background:transparent; border-radius:12px; }
#episode:hover { background:#161923; }
#eptitle { font-size:11pt; font-weight:700; }
#epplot { color:#a3a8b8; font-size:9.5pt; }
#playbadge { background:rgba(0,0,0,0.55); color:white; border-radius:20px; font-size:13pt; }
#toast { background:#1c2029; color:white; border:1px solid %(ACCENT)s; border-radius:10px; padding:10px 18px; font-weight:600; }
QLineEdit, QComboBox { background:#161923; border:1px solid #262a37; border-radius:9px; padding:7px 10px; }
QLineEdit:focus, QComboBox:focus { border-color:%(ACCENT)s; }
QLineEdit#bigsearch { font-size:14pt; padding:12px 16px; border-radius:12px; }
QComboBox QAbstractItemView { background:#161923; selection-background-color:%(ACCENT)s; border:1px solid #262a37; }
QListWidget { background:transparent; border:0; outline:0; }
QListWidget#card { background:#11131a; border:1px solid #1f222d; border-radius:10px; padding:4px; }
QListWidget::item { padding:7px 10px; border-radius:8px; color:#c9ccd6; }
QListWidget::item:selected { background:rgba(46,139,255,0.18); color:white; border-left:3px solid %(ACCENT)s; }
QListWidget::item:hover:!selected { background:#151822; }
QListView { background:transparent; border:0; outline:0; }
QTabWidget::pane { border:1px solid #262a37; border-radius:8px; top:-1px; }
QTabBar::tab { background:transparent; padding:7px 16px; color:#a3a8b8; border-radius:7px; }
QTabBar::tab:selected { background:%(ACCENT)s; color:white; }
QSlider::groove:horizontal { height:4px; background:rgba(255,255,255,0.18); border-radius:2px; }
QSlider::sub-page:horizontal { background:%(ACCENT)s; border-radius:2px; }
QSlider::handle:horizontal { background:white; width:14px; margin:-5px 0; border-radius:7px; }
QSlider::sub-page:horizontal:disabled { background:rgba(255,255,255,0.18); }
QProgressBar#thin { background:rgba(255,255,255,0.15); border:0; border-radius:2px; }
QProgressBar#thin::chunk { background:%(ACCENT)s; border-radius:2px; }
QMenu { background:#161923; border:1px solid #262a37; padding:5px; }
QMenu::item { padding:7px 22px; border-radius:6px; }
QMenu::item:selected { background:%(ACCENT)s; }
QScrollBar:vertical { background:transparent; width:8px; margin:2px; }
QScrollBar::handle:vertical { background:#2a2e3b; border-radius:4px; min-height:40px; }
QScrollBar::handle:vertical:hover { background:#3a3f50; }
QScrollBar:horizontal { background:transparent; height:8px; margin:2px; }
QScrollBar::handle:horizontal { background:#2a2e3b; border-radius:3px; min-width:40px; }
QScrollBar::add-line, QScrollBar::sub-line { width:0; height:0; }
QScrollBar::add-page, QScrollBar::sub-page { background:transparent; }
QToolTip { background:#161923; color:#e8eaf0; border:1px solid #262a37; padding:5px; }
""" % {"BG": BG, "ACCENT": ACCENT}


def app_icon():
    ico = os.path.join(APP_DIR, "app.ico")
    if os.path.exists(ico):
        return QtGui.QIcon(ico)
    pm = QtGui.QPixmap(64, 64)
    pm.fill(Qt.GlobalColor.transparent)
    p = QtGui.QPainter(pm)
    p.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
    g = QtGui.QLinearGradient(0, 0, 64, 64)
    g.setColorAt(0, QtGui.QColor("#1b3a8c"))
    g.setColorAt(1, QtGui.QColor("#0b183e"))
    p.setBrush(g)
    p.setPen(Qt.PenStyle.NoPen)
    p.drawRoundedRect(4, 4, 56, 56, 14, 14)
    p.setBrush(QtGui.QColor("white"))
    p.drawPolygon(QtGui.QPolygon([QtCore.QPoint(25, 19), QtCore.QPoint(25, 45), QtCore.QPoint(46, 32)]))
    p.end()
    return QtGui.QIcon(pm)


def _install_crash_log():
    """Toute erreur (même un plantage brutal) est écrite dans %APPDATA%\\IPTVPlayer\\crash.log."""
    import traceback
    import faulthandler
    try:
        os.makedirs(DATA_DIR, exist_ok=True)
        path = os.path.join(DATA_DIR, "crash.log")
        if os.path.isfile(path) and os.path.getsize(path) > 2_000_000:
            os.replace(path, path + ".old")
        f = open(path, "a", encoding="utf-8", buffering=1)
        f.write(f"\n===== {time.strftime('%Y-%m-%d %H:%M:%S')}  IPTV Player {APP_VERSION} =====\n")
        faulthandler.enable(file=f, all_threads=True)
    except Exception:
        return

    def hook(t, v, tb):
        try:
            f.write("".join(traceback.format_exception(t, v, tb)))
        except Exception:
            pass

    sys.excepthook = hook
    threading.excepthook = lambda a: hook(a.exc_type, a.exc_value, a.exc_traceback)
    if sys.stderr is None:          # pythonw : pas de console, les messages vont dans le journal
        sys.stderr = f


def main():
    _install_crash_log()
    if sys.platform.startswith("win"):
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("IPTVPlayer.App")
        except Exception:
            pass
    QtCore.QCoreApplication.setAttribute(Qt.ApplicationAttribute.AA_DontCreateNativeWidgetSiblings)
    app = QtWidgets.QApplication(sys.argv)
    app.setApplicationName(APP_TITLE)
    app.setApplicationVersion(APP_VERSION)
    app.setOrganizationName(APP_AUTHOR)
    app.setStyle("Fusion")
    app.setStyleSheet(STYLE)
    app.setWindowIcon(app_icon())
    files = [os.path.abspath(a) for a in sys.argv[1:] if a.lower().endswith(M3U_EXTS) and os.path.isfile(a)]
    # Une seule fenêtre : si l'application est déjà ouverte, on lui passe le fichier et on s'arrête.
    sock_name = "IPTVPlayer-" + re.sub(r"\W", "", os.environ.get("USERNAME") or os.environ.get("USER") or "u")
    sock = QtNetwork.QLocalSocket()
    sock.connectToServer(sock_name)
    if sock.waitForConnected(400):
        sock.write(("\n".join(files) or "__show__").encode("utf-8"))
        sock.flush()
        sock.waitForBytesWritten(1000)
        sock.disconnectFromServer()
        return
    QtNetwork.QLocalServer.removeServer(sock_name)
    server = QtNetwork.QLocalServer(app)
    server.listen(sock_name)
    w = MainWindow()
    w.show()

    def _incoming():
        c = server.nextPendingConnection()
        if c is None:
            return

        def _read(c=c):
            data = bytes(c.readAll()).decode("utf-8", "replace").strip()
            w.showNormal() if w.isMinimized() else None
            w.raise_()
            w.activateWindow()
            got = [x for x in data.split("\n") if x and x != "__show__"]
            if got:
                w.open_playlist_files(got)
        c.readyRead.connect(_read)
        c.disconnected.connect(c.deleteLater)
    server.newConnection.connect(_incoming)
    if files:
        QtCore.QTimer.singleShot(600, lambda: w.open_playlist_files(files))
    if not w.player.available():
        QtWidgets.QMessageBox.warning(
            w, APP_TITLE,
            "VLC 64 bits est introuvable : la navigation fonctionne mais la lecture est désactivée.\n\n"
            "Installez VLC 64 bits depuis videolan.org puis relancez le programme.\n\n"
            f"Détail : {VLC_ERROR or 'libvlc non chargé'}")
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
