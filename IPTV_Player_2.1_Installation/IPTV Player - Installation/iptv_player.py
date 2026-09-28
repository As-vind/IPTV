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
import time
import uuid
import base64
import random
import hashlib
import unicodedata
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
APP_VERSION = "2.1"
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
META_TTL = 7 * 86400
ITEM_ROLE = Qt.ItemDataRole.UserRole + 1

BG = "#0e1016"
ACCENT = "#e8252c"
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


def fetch_source(src):
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
        return json.loads(decode_text(http_get(url, timeout=20, headers=headers)))

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
        return self.get(f"/movie/{mid}", append_to_response="credits,videos,release_dates",
                        include_video_language=f"{self.lang[:2]},en,null")

    def tv(self, tid):
        return self.get(f"/tv/{tid}", append_to_response="credits,videos,content_ratings",
                        include_video_language=f"{self.lang[:2]},en,null")

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


def _merge_tmdb_common(meta, d, kind):
    if not d:
        return
    meta["tmdb_id"] = d.get("id")
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
                meta["backdrop"] = _first(info.get("backdrop_path"))
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
        except Exception:
            pass
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
        meta["backdrop"] = _first(info.get("backdrop_path"))
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
                for s in seasons[:25]:
                    try:
                        sd = tm.season(tmdb_id, s["number"])
                    except Exception:
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
        except Exception:
            pass
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
        if pm.width() > 1600 or pm.height() > 1600:
            pm = pm.scaled(QtCore.QSize(1600, 1600), Qt.AspectRatioMode.KeepAspectRatio,
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
    "wide": QtCore.QSize(312, 238),
    "cat": QtCore.QSize(214, 98),
}


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
            u = it.get("_img") or it.get("logo")
            if u:
                self.rows_by_img.setdefault(u, []).append(i)
        self.endResetModel()

    def refresh(self, it):
        for i, x in enumerate(self.items):
            if x is it:
                u = it.get("_img") or it.get("logo")
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

    def sizeHint(self, option, index):
        return CARD_SIZES[self.style]

    def paint(self, p, option, index):
        it = index.data(ITEM_ROLE)
        if not it:
            return
        hov = bool(option.state & QtWidgets.QStyle.StateFlag.State_MouseOver)
        sel = bool(option.state & QtWidgets.QStyle.StateFlag.State_HasFocus) and \
            bool(option.state & QtWidgets.QStyle.StateFlag.State_Selected)
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

        if self.style == "wide":
            self._paint_wide(p, option, it, r, pm, title, hov, f_title, f_sub)
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
        if hov:
            img.adjust(-2, -2, 2, 2)
        path = QtGui.QPainterPath()
        path.addRoundedRect(img, 10, 10)
        live_logo = it.get("kind") == "live" and not it.get("_img")
        p.save()
        p.setClipPath(path)
        if live_logo:
            g = QtGui.QLinearGradient(img.topLeft(), img.bottomRight())
            g.setColorAt(0, QtGui.QColor("#232a3d"))
            g.setColorAt(1, QtGui.QColor("#10131b"))
            p.fillPath(path, g)
            if pm is not None and not pm.isNull():
                draw_image(p, img.adjusted(img.width() * 0.2, img.height() * 0.16,
                                           -img.width() * 0.2, -img.height() * 0.3), pm, "contain")
            else:
                draw_placeholder(p, img, initials(it.get("overlay") or title), option.font, 10)
        elif pm is not None and not pm.isNull():
            draw_image(p, img, pm, "cover")
        else:
            draw_placeholder(p, img, initials(title), option.font, 10, big=True)
        if it.get("overlay"):
            g = QtGui.QLinearGradient(0, img.bottom() - img.height() * 0.45, 0, img.bottom())
            g.setColorAt(0, QtGui.QColor(0, 0, 0, 0))
            g.setColorAt(1, QtGui.QColor(0, 0, 0, 190))
            p.fillRect(img, g)
            f = QtGui.QFont(option.font)
            f.setPointSizeF(10)
            f.setBold(True)
            p.setFont(f)
            p.setPen(QtGui.QColor("white"))
            p.drawText(QtCore.QRectF(img.left() + 12, img.bottom() - 32, img.width() - 24, 24),
                       _flags(Qt.AlignmentFlag.AlignLeft, Qt.AlignmentFlag.AlignVCenter),
                       QtGui.QFontMetrics(f).elidedText(it["overlay"], Qt.TextElideMode.ElideRight, int(img.width() - 24)))
        prog = it.get("progress")
        if prog:
            bar = QtCore.QRectF(img.left(), img.bottom() - 4, img.width(), 4)
            p.fillRect(bar, QtGui.QColor(255, 255, 255, 60))
            p.fillRect(QtCore.QRectF(bar.left(), bar.top(), bar.width() * min(1, prog), 4), QtGui.QColor(ACCENT))
        p.restore()
        if hov:
            p.setPen(QtGui.QPen(QtGui.QColor(ACCENT), 2.5))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawPath(path)
        if it.get("badge") == "LIVE":
            self._pill(p, (img.right() - 10, img.top() + 10), "LIVE", ACCENT, option.font, right=True)
        elif it.get("badge"):
            self._pill(p, (img.left() + 10, img.top() + 10), it["badge"], ACCENT, option.font, 7.5)
        if it.get("time"):
            self._pill(p, (img.left() + 10, img.top() + 10), it["time"], "#1a5fd8", option.font, 9)
        tr = QtCore.QRectF(r.left() + 2, img.bottom() + 8, r.width() - 4, 20)
        f = QtGui.QFont(f_title)
        f.setPointSizeF(10.5)
        f.setBold(False)
        f.setWeight(QtGui.QFont.Weight.DemiBold)
        p.setFont(f)
        p.setPen(QtGui.QColor("#ffffff" if hov else "#e6e8ee"))
        p.drawText(tr, _flags(Qt.AlignmentFlag.AlignLeft),
                   QtGui.QFontMetrics(f).elidedText(title, Qt.TextElideMode.ElideRight, int(tr.width())))
        if it.get("sub"):
            p.setFont(f_sub)
            p.setPen(QtGui.QColor("#8b91a3"))
            sr = QtCore.QRectF(tr.left(), tr.bottom() + 1, tr.width(), 18)
            p.drawText(sr, _flags(Qt.AlignmentFlag.AlignLeft),
                       QtGui.QFontMetrics(f_sub).elidedText(it["sub"], Qt.TextElideMode.ElideRight, int(sr.width())))

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
        self.setGridSize(CARD_SIZES[style])
        if horizontal:
            self.setFlow(QtWidgets.QListView.Flow.LeftToRight)
            self.setWrapping(False)
            self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            self.setFixedHeight(CARD_SIZES[style].height() + 6)
        else:
            self.setViewMode(QtWidgets.QListView.ViewMode.IconMode)
            self.setResizeMode(QtWidgets.QListView.ResizeMode.Adjust)
            self.setLayoutMode(QtWidgets.QListView.LayoutMode.Batched)
            self.setBatchSize(400)
            self.verticalScrollBar().setSingleStep(40)
        self.clicked.connect(lambda idx: self.item_clicked.emit(idx.data(ITEM_ROLE)))
        self.activated.connect(lambda idx: None)

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
        lab = ClickLabel(title + (f"  <span style='color:{ACCENT}'>›</span>" if see_all and title else ""))
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
class HeroBanner(Backdrop):
    def __init__(self, win):
        super().__init__(win.images)
        self.win = win
        self.items, self.idx, self.meta = [], 0, None
        self.setFixedHeight(500)
        lay = QtWidgets.QVBoxLayout(self)
        lay.setContentsMargins(48, 60, 48, 36)
        lay.setSpacing(12)
        lay.addStretch(1)
        self.kind = label("", "kicker")
        self.title = label("", "herotitle", wrap=True)
        self.title.setMaximumWidth(760)
        self.meta_l = label("", "meta")
        self.overview = label("", "overview", wrap=True)
        self.overview.setMaximumWidth(640)
        self.overview.setMaximumHeight(92)
        btns = QtWidgets.QHBoxLayout()
        btns.setSpacing(10)
        self.b_play = button("▶  Lecture", "primary", self._play)
        self.b_info = button("ⓘ  Plus d'infos", "glass", self._info)
        btns.addWidget(self.b_play)
        btns.addWidget(self.b_info)
        btns.addStretch(1)
        self.dots = label("", "dots")
        btns.addWidget(self.dots)
        for w in (self.kind, self.title, self.meta_l, self.overview):
            lay.addWidget(w)
        lay.addSpacing(6)
        lay.addLayout(btns)
        self.timer = QtCore.QTimer(self, interval=11000)
        self.timer.timeout.connect(lambda: self.show_index(self.idx + 1))

    def set_items(self, items):
        self.items = items
        self.setVisible(bool(items))
        if items:
            self.show_index(0)
            self.timer.start()
            for it in items:
                self.win.meta.request(it, lambda m: None)
        else:
            self.timer.stop()

    def mousePressEvent(self, e):
        if e.position().y() > self.height() - 60 and e.position().x() > self.width() - 200:
            self.show_index(self.idx + 1)
            self.timer.start()

    def show_index(self, i):
        if not self.items:
            return
        self.idx = i % len(self.items)
        it = self.items[self.idx]
        self.meta = None
        self.kind.setText("SÉRIE" if it["kind"] == "series" else "FILM")
        self.title.setText(it.get("_title") or it["name"])
        self.meta_l.setText(" · ".join(x for x in (it.get("_year"), it["group"]) if x))
        self.overview.setText("")
        self.set_images("", it.get("logo"))
        self.dots.setText("  ".join("●" if j == self.idx else "○" for j in range(len(self.items))))
        self.win.meta.request(it, lambda m, item=it: self._meta(item, m))

    def _meta(self, item, m):
        if not m or not self.items or self.items[self.idx] is not item:
            return
        self.meta = m
        self.title.setText(m.get("title") or item["name"])
        bits = [m.get("year"), " · ".join(m.get("genres", [])[:3]),
                f"★ {m['rating']}" if m.get("rating") else "", fmt_runtime(m.get("runtime"))]
        self.meta_l.setText("   ·   ".join(b for b in bits if b))
        ov = m.get("overview") or ""
        self.overview.setText(ov if len(ov) < 260 else ov[:257].rsplit(" ", 1)[0] + "…")
        self.set_images(m.get("backdrop"), m.get("poster") or item.get("logo"))

    def _play(self):
        if self.items:
            it = self.items[self.idx]
            if it["kind"] == "movie":
                self.win.play_items([it], 0)
            else:
                self.win.open_item(it)

    def _info(self):
        if self.items:
            self.win.open_item(self.items[self.idx])


def epg_hm(p, k):
    ts = p.get(k + "_ts")
    try:
        return datetime.fromtimestamp(int(ts)).strftime("%H:%M")
    except (TypeError, ValueError):
        return (p.get("start" if k == "start" else "end") or "")[11:16]


class HomePage(ScrollPage):
    def __init__(self, win):
        super().__init__()
        self.win = win
        self.continue_row = None

    def rebuild(self):
        self.reset()
        self.continue_row = None
        win, lib = self.win, self.win.lib
        if not lib.items:
            box = body_box(self.v, (48, 120, 48, 40))
            box.addWidget(label("Bienvenue 👋", "herotitle"))
            box.addWidget(label("Ajoutez une liste M3U ou un compte Xtream Codes pour commencer.", "overview"))
            b = button("＋  Ajouter une source", "primary", win.add_source)
            box.addWidget(b, 0, Qt.AlignmentFlag.AlignLeft)
            box.addStretch(1)
            return
        hero_pool = [i for i in lib.recent("movie", 30) + lib.recent("series", 20) if i.get("logo")]
        if not hero_pool:
            hero_pool = [i for i in lib.by_kind["movie"] + lib.by_kind["series"] if i.get("logo")][:300]
        self.hero = HeroBanner(win)
        self.v.addWidget(self.hero)
        self.hero.set_items(random.sample(hero_pool, min(6, len(hero_pool))) if hero_pool else [])
        self.body = body_box(self.v, (40, 14 if hero_pool else 34, 26, 60), 30)
        self.continue_holder = QtWidgets.QVBoxLayout()
        self.continue_holder.setContentsMargins(0, 0, 0, 0)
        self.body.addLayout(self.continue_holder)
        self.refresh_continue()

        # Les chaînes du moment
        chans = win.trending_channels(24)
        if chans:
            cards = []
            for c in chans:
                name = c.get("_title") or c["name"]
                cards.append({**{k: v for k, v in c.items() if not k.startswith("_")}, "_lib": c, "overlay": name,
                              "_title": name, "badge": "LIVE", "sub": c["group"]})
            row = HRow(win, "Les chaînes du moment", cards, "wide",
                       on_click=lambda it, l=cards: win.play_items([x["_lib"] for x in l], l.index(it)),
                       see_all=lambda: win.go_root("live"),
                       subtitle="Les chaînes les plus regardées actuellement", badge="LIVE")
            self.body.addWidget(row)
            for d in cards:
                if d["_lib"].get("stream_id"):
                    win.fetch_epg(d["_lib"], lambda _it, progs, d=d, row=row: self._epg(row, d, progs))
        # Films / séries en ce moment
        for kind, title in (("movie", "Films en ce moment"), ("series", "Séries en ce moment")):
            rec = lib.recent(kind, 40)
            if rec:
                self.body.addWidget(HRow(win, title, rec, "poster", see_all=lambda k=kind: win.browse(k)))
            if kind == "movie":
                cats = win.category_items("movie", 20, special=True)
                if len(cats) > 1:
                    self.body.addWidget(HRow(win, "", cats, "cat", on_click=win.open_category))
        # Nouveautés
        news = sorted(lib.recent("movie", 12) + lib.recent("series", 8),
                      key=lambda i: -int(i.get("added") or 0) if str(i.get("added") or "0").isdigit() else 0)
        if news:
            cards = [{**{k: v for k, v in i.items() if not k.startswith("_")}, "_lib": i,
                      "_title": i.get("_title") or i["name"], "badge": "NOUVEAU",
                      "sub": " · ".join(x for x in ("Série" if i["kind"] == "series" else "Film",
                                                     i.get("_year"), pretty_group(i["group"])) if x)} for i in news]
            row = HRow(win, f"Nouveautés sur {APP_TITLE}", cards, "wide")
            self.body.addWidget(row)
            for d in cards:
                win.meta.request(d["_lib"], lambda m, d=d, row=row: self._news_meta(row, d, m))
        cats = win.category_items("series", 20, special=True)
        if len(cats) > 1:
            self.body.addWidget(HRow(win, "", cats, "cat", on_click=win.open_category))
        for kind, prefix in (("movie", "Films"), ("series", "Séries")):
            for g, _n in Counter(i["group"] for i in lib.by_kind[kind]).most_common(3):
                items = [i for i in lib.by_kind[kind] if i["group"] == g][:40]
                self.body.addWidget(HRow(win, f"{prefix} · {pretty_group(g)}", items, "poster",
                                         see_all=lambda k=kind, gg=g: win.browse(k, group=gg)))
        self.body.addStretch(1)

    @staticmethod
    def _epg(row, d, progs):
        if not progs:
            return
        now = progs[0]
        d["_title"] = now["title"] or d["_title"]
        d["sub"] = f"{epg_hm(now, 'start')} – {epg_hm(now, 'stop')}"
        try:
            row.refresh(d)
        except RuntimeError:
            pass

    @staticmethod
    def _news_meta(row, d, m):
        if not m:
            return
        if m.get("backdrop"):
            d["_img"] = m["backdrop"]
        d["_title"] = m.get("title") or d["_title"]
        try:
            row.refresh(d)
        except RuntimeError:
            pass

    def refresh_continue(self):
        if not hasattr(self, "continue_holder"):
            return
        if self.continue_row is not None:
            try:
                self.continue_row.deleteLater()
            except RuntimeError:
                pass
            self.continue_row = None
        items = self.win.continue_items()
        if items:
            row = HRow(self.win, "Reprendre la lecture", items, "wide", on_click=self.win.resume_entry)
            self.continue_row = row
            self.continue_holder.addWidget(row)
            for d in items:
                if d.get("_lib"):
                    self.win.meta.request(d["_lib"], lambda m, d=d, row=row: self._cont_meta(row, d, m))

    @staticmethod
    def _cont_meta(row, d, m):
        if m and m.get("backdrop"):
            d["_img"] = m["backdrop"]
            try:
                row.refresh(d)
            except RuntimeError:
                pass


# --------------------------------------------------------------------------- #
#  Parcourir (TV / Films / Séries)
# --------------------------------------------------------------------------- #
class BrowsePage(QtWidgets.QWidget):
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
        self.b_restart.hide()
        self.b_trailer.hide()
        for b in (self.b_play, self.b_restart, self.b_trailer, self.b_fav):
            btns.addWidget(b)
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
        season = self.meta["seasons"][i]
        prog = self.win.progress
        fallback = self.meta.get("backdrop") or self.item.get("logo")
        for j, ep in enumerate(season["episodes"]):
            pr = prog.get(ep["url"])
            frac = (pr["pos"] / pr["len"]) if pr and pr.get("len") else 0
            if pr and pr.get("done"):
                frac = 1
            row = EpisodeRow(self.win, ep, fallback, frac)
            row.clicked.connect(lambda s=i, e=j: self._play_episode(s, e))
            self.eps_box.addWidget(row)

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
        if win.cfg.get("tmdb_key"):
            win.meta.request_person(person, self._on_meta)
        else:
            self.bio.setText("Ajoutez une clé TMDB (gratuite) dans Paramètres pour afficher la photo, "
                             "la biographie et la filmographie complète des acteurs.")

    def _local_rows(self):
        items = self.win.lib.titles_with_actor(self.person["name"])
        self._local_urls = {i["url"] for i in items}
        if items:
            self.local_row = HRow(self.win, "Dans votre liste", items, "poster")
            self.body.addWidget(self.local_row)

    def _toggle_bio(self):
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
            self.bio.setText("Aucune information trouvée pour cette personne.")
            return
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
        top = QtWidgets.QWidget()
        tl = QtWidgets.QVBoxLayout(top)
        tl.setContentsMargins(44, 26, 44, 8)
        tl.addWidget(label("Rechercher", "pagetitle"))
        self.edit = QtWidgets.QLineEdit()
        self.edit.setObjectName("bigsearch")
        self.edit.setPlaceholderText("🔍   Chaîne, film, série, acteur…")
        self.edit.setClearButtonEnabled(True)
        tl.addWidget(self.edit)
        v.addWidget(top)
        self.results = ScrollPage()
        v.addWidget(self.results, 1)
        self._t = QtCore.QTimer(self, singleShot=True, interval=350)
        self._t.timeout.connect(self._search)
        self.edit.textChanged.connect(lambda _x: self._t.start())
        self._token = 0

    def focus(self):
        self.edit.setFocus()
        self.edit.selectAll()

    def _search(self):
        q = norm(self.edit.text().strip())
        self.results.reset()
        box = body_box(self.results.v, (44, 10, 30, 40), 26)
        self.box = box
        self._token += 1
        if len(q) < 2:
            box.addWidget(label("Tapez au moins 2 caractères.", "empty"))
            box.addStretch(1)
            return
        terms = q.split()
        found = 0
        for kind, title, style in (("live", "Chaînes TV", "channel"), ("movie", "Films", "poster"),
                                   ("series", "Séries", "poster")):
            lst = [i for i in self.win.lib.by_kind[kind] if all(t in i["_q"] for t in terms)][:80]
            if lst:
                found += len(lst)
                if kind == "live":
                    box.addWidget(HRow(self.win, f"{title}  ({len(lst)})", lst, style,
                                       on_click=lambda it, l=lst: self.win.play_items(l, l.index(it))))
                else:
                    box.addWidget(HRow(self.win, f"{title}  ({len(lst)})", lst, style))
        self.people_holder = QtWidgets.QVBoxLayout()
        box.addLayout(self.people_holder)
        self.no_res = label("Aucun résultat dans votre liste.", "empty")
        self.no_res.setVisible(not found)
        box.addWidget(self.no_res)
        box.addStretch(1)
        key = self.win.cfg.get("tmdb_key")
        if key:
            token, text = self._token, self.edit.text().strip()
            lang = self.win.cfg.get("lang", "fr-FR")
            self.win.run_task(lambda: TMDB(key, lang).search_person(text),
                              lambda res, t=token: self._people(t, res), lambda _e: None)

    def _people(self, token, res):
        if token != self._token:
            return
        people = [{"name": p.get("name") or "", "logo": TMDB.img(p.get("profile_path"), "w185"),
                   "sub": ", ".join(k.get("title") or k.get("name") or "" for k in (p.get("known_for") or [])[:2]),
                   "kind": "person", "tmdb_id": p.get("id")}
                  for p in res[:30] if p.get("known_for_department") == "Acting" and p.get("profile_path")]
        if people:
            try:
                self.people_holder.addWidget(HRow(self.win, "Acteurs", people, "actor", on_click=self.win.open_person))
                self.no_res.hide()
            except RuntimeError:
                pass


# --------------------------------------------------------------------------- #
#  Paramètres & sources
# --------------------------------------------------------------------------- #
class SourceDialog(QtWidgets.QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Ajouter une source")
        self.setMinimumWidth(580)
        self.result_source = None
        self.tabs = QtWidgets.QTabWidget()

        w1 = QtWidgets.QWidget()
        f1 = QtWidgets.QFormLayout(w1)
        self.m3u_name = QtWidgets.QLineEdit()
        self.m3u_name.setPlaceholderText("Ma liste")
        self.m3u_url = QtWidgets.QLineEdit()
        self.m3u_url.setPlaceholderText("https://…/playlist.m3u   ou   C:\\…\\liste.m3u")
        browse = QtWidgets.QPushButton("Parcourir…")
        browse.clicked.connect(self._browse)
        row = QtWidgets.QHBoxLayout()
        row.addWidget(self.m3u_url, 1)
        row.addWidget(browse)
        f1.addRow("Nom", self.m3u_name)
        f1.addRow("Lien ou fichier", row)
        hint = QtWidgets.QLabel("Un lien du type <i>get.php?username=…&password=…</i> est converti "
                                "automatiquement en compte Xtream (TV + films + séries + fiches).")
        hint.setWordWrap(True)
        hint.setStyleSheet("color:#8b91a3;")
        f1.addRow(hint)
        self.tabs.addTab(w1, "Lien M3U")

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
        self.tabs.addTab(w2, "Compte Xtream Codes")

        bb = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.StandardButton.Ok |
                                        QtWidgets.QDialogButtonBox.StandardButton.Cancel)
        bb.button(QtWidgets.QDialogButtonBox.StandardButton.Ok).setText("Ajouter")
        bb.button(QtWidgets.QDialogButtonBox.StandardButton.Cancel).setText("Annuler")
        bb.accepted.connect(self._accept)
        bb.rejected.connect(self.reject)
        lay = QtWidgets.QVBoxLayout(self)
        lay.addWidget(self.tabs)
        lay.addWidget(bb)

    def _browse(self):
        path, _ = QtWidgets.QFileDialog.getOpenFileName(self, "Choisir une liste M3U", "",
                                                        "Listes M3U (*.m3u *.m3u8);;Tous les fichiers (*)")
        if path:
            self.m3u_url.setText(path)
            if not self.m3u_name.text():
                self.m3u_name.setText(os.path.splitext(os.path.basename(path))[0])

    def _accept(self):
        sid = uuid.uuid4().hex[:12]
        if self.tabs.currentIndex() == 0:
            url = self.m3u_url.text().strip()
            if not url:
                QtWidgets.QMessageBox.warning(self, APP_TITLE, "Indiquez un lien ou un fichier M3U.")
                return
            pu = urllib.parse.urlparse(url)
            q = urllib.parse.parse_qs(pu.query)
            name = self.m3u_name.text().strip()
            if "get.php" in pu.path.lower() and q.get("username") and q.get("password"):
                self.result_source = {"id": sid, "type": "xtream", "name": name or pu.netloc,
                                      "server": f"{pu.scheme}://{pu.netloc}", "user": q["username"][0],
                                      "password": q["password"][0], "live_ext": "ts"}
            else:
                if not re.match(r"^https?://", url, re.I) and not os.path.exists(url):
                    QtWidgets.QMessageBox.warning(self, APP_TITLE, "Fichier introuvable.")
                    return
                default = pu.netloc if pu.netloc else os.path.splitext(os.path.basename(url))[0]
                self.result_source = {"id": sid, "type": "m3u", "name": name or default or "Liste M3U", "url": url}
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
        row.addWidget(button("🗑 Supprimer", "secondary", self._delete))
        row.addStretch(1)
        box.addLayout(row)

        box.addSpacing(10)
        box.addWidget(label("Fiches films, séries et acteurs (TMDB)", "rowtitle"))
        box.addWidget(label(
            "Avec une clé TMDB gratuite, l'application affiche les photos et biographies des acteurs, "
            "leur filmographie, les fonds d'écran, bandes-annonces, âges requis et vignettes d'épisodes. "
            "Créez un compte sur themoviedb.org → Paramètres → API, puis collez la clé API (v3) "
            "ou le jeton d'accès en lecture (v4).", "overview", wrap=True))
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

    def rebuild(self):
        self.sources.clear()
        for s in self.win.cfg["sources"]:
            cur = self.win.current_source and self.win.current_source["id"] == s["id"]
            it = QtWidgets.QListWidgetItem(("● " if cur else "   ") + ("📡 " if s["type"] == "xtream" else "📄 ")
                                           + s["name"] + ("   —   Xtream Codes" if s["type"] == "xtream" else "   —   M3U"))
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
                              (item.get("group") or ""))
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
        media = self.instance.media_new(item["url"])
        media.add_option(f":http-user-agent={USER_AGENT}")
        for o in item.get("opts") or []:
            media.add_option(":" + o)
        pr = self.win.progress.get(item["url"])
        if resume and not live and pr and not pr.get("done") and pr.get("pos", 0) > 30000:
            media.add_option(f":start-time={pr['pos'] / 1000:.0f}")
        self.mp.set_media(media)
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
        self.current = None

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
        if st == vlc.State.Buffering or st == vlc.State.Opening:
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

    def clear_mem(self):
        self.mem.clear()

    def _disk(self, key):
        return os.path.join(META_DIR, hashlib.md5(key.encode("utf-8")).hexdigest() + ".json")

    def _run(self, key, compute, cb):
        if key in self.mem:
            m = self.mem[key]
            QtCore.QTimer.singleShot(0, lambda: safe_call(cb, m))
            return
        if key in self.pending:
            self.pending[key].append(cb)
            return
        self.pending[key] = [cb]
        path = self._disk(key)

        def job():
            try:
                if os.path.exists(path) and time.time() - os.path.getmtime(path) < META_TTL:
                    with open(path, encoding="utf-8") as f:
                        return json.load(f)
            except Exception:
                pass
            m = compute()
            if m:
                try:
                    with open(path, "w", encoding="utf-8") as f:
                        json.dump(m, f, ensure_ascii=False)
                except OSError:
                    pass
            return m

        self.win.run_task(job, lambda m: self._done(key, m), lambda _e: self._done(key, None), quiet=True)

    def _done(self, key, m):
        if m:
            self.mem[key] = m
        for cb in self.pending.pop(key, []):
            safe_call(cb, m)

    def request(self, item, cb):
        cfg, src = self.win.cfg, self.win.current_source
        tkey, lang = cfg.get("tmdb_key", ""), cfg.get("lang", "fr-FR")
        key = f"{item['kind']}|{(src or {}).get('id')}|{item['url']}|{lang}|{bool(tkey)}"
        fn = series_meta if item["kind"] == "series" else movie_meta
        item_copy = {k: v for k, v in item.items() if not k.startswith("_")}

        def done(m, it=item):
            if m:
                self.win.lib.index_cast(it, m)
            safe_call(cb, m)
        self._run(key, lambda: fn(src, item_copy, tkey, lang), done)

    def request_person(self, person, cb):
        cfg = self.win.cfg
        tkey, lang = cfg.get("tmdb_key", ""), cfg.get("lang", "fr-FR")
        if not tkey:
            QtCore.QTimer.singleShot(0, lambda: safe_call(cb, None))
            return
        pid, name = person.get("tmdb_id"), person["name"]
        key = f"person|{pid or norm(name)}|{lang}"
        self._run(key, lambda: person_meta(tkey, lang, pid, name), cb)


# --------------------------------------------------------------------------- #
#  Fenêtre principale
# --------------------------------------------------------------------------- #
class MainWindow(QtWidgets.QMainWindow):
    TABS = [("home", "Accueil"), ("movie", "Films"), ("series", "Séries"), ("live", "Chaînes TV"),
            ("categories", "Catégories"), ("favorites", "Ma liste")]

    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"{APP_TITLE} — par {APP_AUTHOR}")
        self.resize(1560, 920)
        self.cfg = load_config()
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
        self.topbar.hide()
        self.signature.hide()
        self.profiles_page.manage = False
        self.profiles_page.rebuild()
        self.stack.setCurrentWidget(self.profiles_page)

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
            self.topbar.show()
            self.signature.show()
            if changed_kids or True:
                self._apply_library(*self._raw)
            self.go_root("home")
            self.toast(f"Bonjour {pr['name']} 👋")

    def _update_avatar(self):
        if self.profile:
            self.b_avatar.setIcon(QtGui.QIcon(avatar_pixmap(self.profile, 34, circle=True)))
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
        central = QtWidgets.QWidget()
        central.setObjectName("root")
        v = QtWidgets.QVBoxLayout(central)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)

        self.topbar = QtWidgets.QFrame()
        self.topbar.setObjectName("topbar")
        self.topbar.setFixedHeight(68)
        tl = QtWidgets.QHBoxLayout(self.topbar)
        tl.setContentsMargins(26, 0, 20, 0)
        tl.setSpacing(0)
        logo = ClickLabel()
        pm = logo_pixmap(40, BG)
        if pm:
            logo.setPixmap(pm)
        else:
            logo.setText(APP_TITLE)
            logo.setObjectName("logo")
        logo.setCursor(Qt.CursorShape.PointingHandCursor)
        logo.clicked.connect(lambda: self.go_root("home"))
        tl.addWidget(logo)
        tl.addSpacing(30)
        self.nav_group = QtWidgets.QButtonGroup(self)
        self.nav_group.setExclusive(True)
        self.nav_btns = {}
        for key, text in self.TABS:
            b = QtWidgets.QPushButton(text)
            b.setObjectName("tab")
            b.setCheckable(True)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.clicked.connect(lambda _c=False, k=key: self.go_root(k))
            self.nav_group.addButton(b)
            self.nav_btns[key] = b
            tl.addWidget(b)
        tl.addStretch(1)
        self.progress_bar = QtWidgets.QProgressBar()
        self.progress_bar.setObjectName("thin")
        self.progress_bar.setRange(0, 0)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setFixedSize(70, 4)
        self.progress_bar.hide()
        self.busy_l = label("", "tiny")
        tl.addWidget(self.busy_l)
        tl.addSpacing(6)
        tl.addWidget(self.progress_bar)
        tl.addSpacing(12)
        for key, icon, tip in (("search", "🔍", "Rechercher (Ctrl+F)"), ("settings", "⚙", "Paramètres")):
            b = QtWidgets.QPushButton(icon)
            b.setObjectName("iconbtn")
            b.setCheckable(True)
            b.setToolTip(tip)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.clicked.connect(lambda _c=False, k=key: self.go_root(k))
            self.nav_group.addButton(b)
            self.nav_btns[key] = b
            tl.addWidget(b)
            tl.addSpacing(4)
        tl.addSpacing(8)
        self.source_combo = QtWidgets.QComboBox()
        self.source_combo.setObjectName("sourcecombo")
        self.source_combo.setFixedWidth(200)
        self.source_combo.currentIndexChanged.connect(self._combo_changed)
        tl.addWidget(self.source_combo)
        tl.addSpacing(12)
        self.b_avatar = QtWidgets.QToolButton()
        self.b_avatar.setObjectName("avatar")
        self.b_avatar.setIconSize(QtCore.QSize(34, 34))
        self.b_avatar.setPopupMode(QtWidgets.QToolButton.ToolButtonPopupMode.InstantPopup)
        self.b_avatar.setCursor(Qt.CursorShape.PointingHandCursor)
        self.avatar_menu = QtWidgets.QMenu(self)
        self.b_avatar.setMenu(self.avatar_menu)
        tl.addWidget(self.b_avatar)
        v.addWidget(self.topbar)

        self.stack = QtWidgets.QStackedWidget()
        self.player = PlayerPage(self)
        self.home = HomePage(self)
        self.profiles_page = ProfilesPage(self)
        self.pages = {
            "home": self.home,
            "live": BrowsePage(self, "live"),
            "movie": BrowsePage(self, "movie"),
            "series": BrowsePage(self, "series"),
            "categories": CategoriesPage(self),
            "favorites": FavoritesPage(self),
            "search": SearchPage(self),
        }
        self.pages["settings"] = SettingsPage(self)
        for pg in self.pages.values():
            self.stack.addWidget(pg)
        self.stack.addWidget(self.player)
        self.stack.addWidget(self.profiles_page)
        self.stack.currentChanged.connect(lambda _i: self._place_signature())
        v.addWidget(self.stack, 1)
        self.setCentralWidget(central)
        self.source_info = self.source_combo  # infos de la source en info-bulle

        self.signature = QtWidgets.QLabel(APP_AUTHOR, central)
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
        sc("Space", lambda: self._in_player() and self.player.toggle_pause())
        sc("F", lambda: self._in_player() and self.toggle_fullscreen())
        sc("Left", lambda: self._in_player() and self.player.seek_rel(-10))
        sc("Right", lambda: self._in_player() and self.player.seek_rel(30))
        sc("Up", lambda: self._in_player() and (self.player.prev() if self._live() else self.player.volume_rel(5)))
        sc("Down", lambda: self._in_player() and (self.player.next() if self._live() else self.player.volume_rel(-5)))
        sc("PgUp", lambda: self._in_player() and self.player.prev())
        sc("PgDown", lambda: self._in_player() and self.player.next())
        sc("N", lambda: self._in_player() and self.player.next())
        self._update_avatar()
        self.go_root("home")

    def _place_signature(self):
        if not hasattr(self, "signature"):
            return
        cur = self.stack.currentWidget()
        vis = cur is not self.player and cur is not self.profiles_page and not self._fs
        self.signature.setVisible(vis)
        if vis:
            self.signature.adjustSize()
            self.signature.move(18, self.centralWidget().height() - self.signature.height() - 6)
            self.signature.raise_()

    def _in_player(self):
        return self.stack.currentWidget() is self.player

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
        QtCore.QThreadPool.globalInstance().start(t)

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
        self.topbar.show()
        page = self.pages[key]
        self.nav_btns[key].setChecked(True)
        if key in ("favorites", "categories"):
            page.rebuild()
        elif key == "settings":
            page.rebuild()
        elif key == "home":
            page.refresh_continue()
        self.stack.setCurrentWidget(page)
        if key == "search":
            page.focus()

    def browse(self, kind, country=None, group=None):
        self.go_root(kind)
        self.pages[kind].rebuild(country=country, group=group)

    def push(self, w):
        if w is not self.player:
            self.stack.addWidget(w)
        self.history.append(w)
        self.stack.setCurrentWidget(w)

    def back(self):
        if not self.history:
            return
        if self._fs:
            self.toggle_fullscreen()
        w = self.history.pop()
        if w is self.player:
            self.player.stop()
        else:
            self.stack.removeWidget(w)
            w.deleteLater()
        target = self.history[-1] if self.history else self.pages[self._root_key()]
        self.stack.setCurrentWidget(target)
        if hasattr(target, "refresh_progress"):
            target.refresh_progress()
        if target is self.home:
            self.home.refresh_continue()

    def _root_key(self):
        b = self.nav_group.checkedButton()
        for k, v in self.nav_btns.items():
            if v is b:
                return k
        return "home"

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

    def open_person(self, person):
        self.push(PersonPage(self, person))

    def play_items(self, items, index, resume=True):
        if not self.player.available():
            QtWidgets.QMessageBox.warning(self, APP_TITLE,
                                          "VLC 64 bits est introuvable : installez-le depuis videolan.org puis relancez.")
            return
        if self.stack.currentWidget() is not self.player:
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
            self.topbar.hide()
            if in_player:
                self.player.set_immersive(True)
            self.showFullScreen()
            self._fs = True
        else:
            self.topbar.show()
            self.player.set_immersive(False)
            self.showNormal()
            if self._fs_max:
                self.showMaximized()
            self._fs = False
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
        self.home.rebuild()
        for k in ("live", "movie", "series"):
            self.pages[k].rebuild()
        if self._root_key() in ("favorites", "settings", "categories") and not self.history:
            self.pages[self._root_key()].rebuild()

    def add_source(self):
        dlg = SourceDialog(self)
        if dlg.exec() and dlg.result_source:
            self.cfg["sources"].append(dlg.result_source)
            self.save()
            self._reload_sources(dlg.result_source["id"])
            self.pages["settings"].rebuild()

    def delete_source(self, sid):
        src = self._source_by_id(sid)
        if not src:
            return
        r = QtWidgets.QMessageBox.question(self, APP_TITLE, f"Supprimer la source « {src['name']} » ?")
        if r != QtWidgets.QMessageBox.StandardButton.Yes:
            return
        self.cfg["sources"] = [s for s in self.cfg["sources"] if s["id"] != sid]
        try:
            os.remove(cache_path(sid))
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
            else:
                it["_title"] = clean_title(it["name"])[0]
                it["sub"] = f"Reste {fmt_ms(e['len'] - e['pos'])}"
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
#topbar { background:#0a0c10; border-bottom:1px solid #1c1f28; }
#logo { font-size:17pt; font-weight:800; }
QPushButton#tab { background:transparent; border:0; border-radius:0; border-bottom:3px solid transparent;
                  padding:22px 2px 19px 2px; margin:0 13px; color:#aeb3c2; font-size:11.5pt; font-weight:600; }
QPushButton#tab:hover { color:white; }
QPushButton#tab:checked { color:white; border-bottom:3px solid %(ACCENT)s; }
QPushButton#iconbtn { background:transparent; border:0; border-radius:19px; min-width:38px; max-width:38px;
                      min-height:38px; max-height:38px; padding:0; font-size:14pt; color:#dfe2ea; }
QPushButton#iconbtn:hover, QPushButton#iconbtn:checked { background:#1c2029; }
QComboBox#sourcecombo { background:#141821; border:1px solid #242938; border-radius:17px; padding:6px 12px; }
QToolButton#avatar { background:transparent; border:0; padding:0; }
QToolButton#avatar::menu-indicator { image:none; width:0; }
#rowsub { color:#9aa0b2; font-size:10pt; }
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
#rowtitle { font-size:15.5pt; font-weight:700; color:white; }
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
QPushButton#primary { background:%(ACCENT)s; border:0; color:white; font-weight:700; font-size:10.5pt; padding:10px 22px; }
QPushButton#primary:hover { background:#ff3b41; }
QPushButton#primary:disabled { background:#4a2a2c; color:#b09a9a; }
QPushButton#glass { background:rgba(255,255,255,0.10); border:1px solid rgba(255,255,255,0.16); color:white;
                    font-weight:600; font-size:10.5pt; padding:10px 18px; }
QPushButton#glass:hover { background:rgba(255,255,255,0.18); }
QPushButton#link { background:transparent; border:0; color:%(ACCENT)s; font-weight:700; padding:2px 8px; }
QPushButton#link:hover { color:#ff6b70; }
QPushButton#arrow { background:#161923; border:1px solid #232735; border-radius:8px; padding:0; font-size:14pt; color:#c9ccd6; }
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
QListWidget::item:selected { background:#2a1517; color:white; border-left:3px solid %(ACCENT)s; }
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
QScrollBar:vertical { background:transparent; width:10px; margin:2px; }
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


def main():
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
    w = MainWindow()
    w.show()
    if not w.player.available():
        QtWidgets.QMessageBox.warning(
            w, APP_TITLE,
            "VLC 64 bits est introuvable : la navigation fonctionne mais la lecture est désactivée.\n\n"
            "Installez VLC 64 bits depuis videolan.org puis relancez le programme.\n\n"
            f"Détail : {VLC_ERROR or 'libvlc non chargé'}")
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
