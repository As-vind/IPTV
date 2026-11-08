#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Désinstallation d'IPTV Player (par Asvind).

Enlève tout ce que l'installateur a posé, quelle que soit la version installée :
  - ferme IPTV Player s'il est ouvert ;
  - raccourcis Bureau (y compris Bureau OneDrive), menu Démarrer et barre des tâches ;
  - entrée(s) « Applications installées » (anciennes versions comprises) ;
  - dossier du logiciel (fichiers + moteur VLC), même s'il est encore verrouillé un instant ;
  - en option : sources, favoris, historique, caches et films téléchargés.
Ces fonctions servent aussi à l'installateur pour retirer proprement l'ancienne version avant une mise à jour.
"""
import os
import sys
import json
import time
import shutil
import tempfile
import subprocess

APP_NAME = "IPTV Player"
PUBLISHER = "Asvind"
REG_KEY = r"Software\Microsoft\Windows\CurrentVersion\Uninstall\IPTVPlayer"
REG_ROOT = r"Software\Microsoft\Windows\CurrentVersion\Uninstall"
HERE = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(os.environ.get("APPDATA") or os.path.expanduser("~"), "IPTVPlayer")
LOCAL_DIR = os.path.join(os.environ.get("LOCALAPPDATA") or os.path.expanduser("~"), "IPTVPlayer")
DEFAULT_DIR = os.path.join(os.environ.get("LOCALAPPDATA") or os.path.expanduser("~"), "Programs", APP_NAME)
NO_WINDOW = 0x08000000
IS_WIN = sys.platform.startswith("win")


def special_folder(name):
    """Dossiers Windows de l'utilisateur (gère les dossiers redirigés, ex. OneDrive)."""
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                            r"Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders") as k:
            return os.path.expandvars(winreg.QueryValueEx(k, name)[0])
    except Exception:
        home = os.path.expanduser("~")
        return os.path.join(home, "Desktop") if name == "Desktop" else \
            os.path.join(os.environ.get("APPDATA", home), r"Microsoft\Windows\Start Menu\Programs")


# --------------------------------------------------------------------------- #
#  Installations existantes
# --------------------------------------------------------------------------- #
def _q(winreg, k, n):
    try:
        return str(winreg.QueryValueEx(k, n)[0] or "")
    except OSError:
        return ""


def registered_installs():
    """[(clé, dossier, version)] pour toutes les entrées « IPTV Player » d'« Applications installées »."""
    out = []
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_ROOT) as root:
            i = 0
            while True:
                try:
                    sub = winreg.EnumKey(root, i)
                except OSError:
                    break
                i += 1
                try:
                    with winreg.OpenKey(root, sub) as k:
                        name, pub = _q(winreg, k, "DisplayName"), _q(winreg, k, "Publisher")
                        if sub == "IPTVPlayer" or (name.startswith(APP_NAME) and pub in ("", PUBLISHER)):
                            out.append((sub, _q(winreg, k, "InstallLocation"), _q(winreg, k, "DisplayVersion")))
                except OSError:
                    pass
    except Exception:
        pass
    return out


def is_app_dir(d):
    """Sécurité : on ne supprime jamais un dossier qui n'est pas celui du logiciel."""
    return bool(d) and os.path.isdir(d) and os.path.exists(os.path.join(d, "iptv_player.py")) and \
        (os.path.exists(os.path.join(d, "install.json")) or os.path.exists(os.path.join(d, "uninstall.py")))


def install_dirs():
    cands = [loc for _s, loc, _v in registered_installs() if loc] + [DEFAULT_DIR]
    seen, res = set(), []
    for d in cands:
        n = os.path.normcase(os.path.normpath(d))
        if n not in seen and is_app_dir(d):
            seen.add(n)
            res.append(d)
    return res


# --------------------------------------------------------------------------- #
#  Nettoyage
# --------------------------------------------------------------------------- #
def close_running_app():
    """Ferme IPTV Player s'il tourne (sinon Windows refuse de supprimer le moteur VLC)."""
    if not IS_WIN:
        return
    ps = ("Get-CimInstance Win32_Process | Where-Object { ($_.Name -like 'python*') -and "
          "($_.CommandLine -like '*iptv_player.py*') -and ($_.ProcessId -ne %d) } | "
          "ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }" % os.getpid())
    try:
        subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps],
                       timeout=25, creationflags=NO_WINDOW, capture_output=True)
        time.sleep(0.8)
    except Exception:
        pass


def _lnk_is_ours(path):
    try:
        with open(path, "rb") as f:
            data = f.read().lower()
        return b"iptv_player" in data or "iptv_player".encode("utf-16-le") in data
    except OSError:
        return False


def remove_shortcuts():
    """Raccourcis du Bureau (local, OneDrive, public), du menu Démarrer et épinglés à la barre des tâches."""
    removed = 0
    home = os.path.expanduser("~")
    appdata = os.environ.get("APPDATA") or ""
    folders = {special_folder("Desktop"), os.path.join(home, "Desktop"), os.path.join(home, "Bureau"),
               os.path.join(os.environ.get("PUBLIC", r"C:\Users\Public"), "Desktop"),
               os.path.join(appdata, r"Microsoft\Internet Explorer\Quick Launch\User Pinned\TaskBar"),
               os.path.join(appdata, r"Microsoft\Internet Explorer\Quick Launch\User Pinned\StartMenu"),
               os.path.join(appdata, r"Microsoft\Internet Explorer\Quick Launch"),
               special_folder("Programs")}
    for env in ("OneDrive", "OneDriveConsumer", "OneDriveCommercial"):
        if os.environ.get(env):
            folders.add(os.path.join(os.environ[env], "Desktop"))
            folders.add(os.path.join(os.environ[env], "Bureau"))
    for d in folders:
        if not d or not os.path.isdir(d):
            continue
        for f in os.listdir(d):
            p = os.path.join(d, f)
            low = f.lower()
            if low.endswith(".lnk") and (low.startswith("iptv player") or low.startswith("désinstaller iptv")
                                         or _lnk_is_ours(p)):
                try:
                    os.remove(p)
                    removed += 1
                except OSError:
                    pass
    shutil.rmtree(os.path.join(special_folder("Programs"), APP_NAME), ignore_errors=True)
    return removed


def remove_registry():
    try:
        import winreg
        for sub, _loc, _v in registered_installs():
            try:
                winreg.DeleteKey(winreg.HKEY_CURRENT_USER, REG_ROOT + "\\" + sub)
            except OSError:
                pass
    except Exception:
        pass
    # association « Ouvrir avec » des fichiers .m3u
    try:
        import winreg
        for key in (r"Software\Classes\IPTVPlayer.m3u\shell\open\command", r"Software\Classes\IPTVPlayer.m3u\shell\open",
                    r"Software\Classes\IPTVPlayer.m3u\shell", r"Software\Classes\IPTVPlayer.m3u\DefaultIcon",
                    r"Software\Classes\IPTVPlayer.m3u"):
            try:
                winreg.DeleteKey(winreg.HKEY_CURRENT_USER, key)
            except OSError:
                pass
        for ext in (".m3u", ".m3u8"):
            try:
                with winreg.OpenKey(winreg.HKEY_CURRENT_USER, rf"Software\Classes\{ext}\OpenWithProgids", 0,
                                    winreg.KEY_SET_VALUE) as k:
                    winreg.DeleteValue(k, "IPTVPlayer.m3u")
            except OSError:
                pass
    except Exception:
        pass


def remove_dir(d):
    """Supprime le dossier ; ce qui est encore verrouillé est effacé quelques secondes après."""
    if not is_app_dir(d):
        return True
    try:
        if os.path.normcase(os.path.abspath(os.getcwd())).startswith(os.path.normcase(os.path.abspath(d))):
            os.chdir(tempfile.gettempdir())
    except OSError:
        pass
    for _ in range(3):
        shutil.rmtree(d, ignore_errors=True)
        if not os.path.exists(d):
            return True
        time.sleep(1)
    if IS_WIN:
        try:
            subprocess.Popen(f'cmd /c ping 127.0.0.1 -n 4 >nul & rmdir /s /q "{d}"', shell=True,
                             creationflags=NO_WINDOW, cwd=tempfile.gettempdir())
        except Exception:
            pass
    return False


def refresh_icons():
    """Demande à Windows de rafraîchir ses icônes (évite les anciennes icônes « fantômes »)."""
    if not IS_WIN:
        return
    try:
        import ctypes
        ctypes.windll.shell32.SHChangeNotify(0x08000000, 0x0000, None, None)  # SHCNE_ASSOCCHANGED
    except Exception:
        pass


def download_dir():
    try:
        with open(os.path.join(DATA_DIR, "config.json"), encoding="utf-8") as f:
            d = json.load(f).get("download_dir")
        if d:
            return d
    except Exception:
        pass
    return os.path.join(os.path.expanduser("~"), "Videos", APP_NAME)


def remove_previous(keep_dir=None, log=print):
    """Pour l'installateur : retire l'ancienne version (raccourcis, registre, fichiers) sans toucher aux données."""
    close_running_app()
    n = remove_shortcuts()
    if n:
        log(f"✓ {n} ancien(s) raccourci(s) supprimé(s)")
    keep = os.path.normcase(os.path.normpath(keep_dir)) if keep_dir else None
    here = os.path.normcase(os.path.normpath(HERE))
    olds = [d for d in install_dirs() if os.path.normcase(os.path.normpath(d)) not in (keep, here)]
    versions = sorted({v for _s, _l, v in registered_installs() if v})
    remove_registry()
    if versions:
        log(f"✓ Ancienne entrée retirée d'« Applications installées » (version {', '.join(versions)})")
    for d in olds:
        remove_dir(d)
        log(f"✓ Ancienne installation supprimée : {d}")


def uninstall(remove_data, remove_videos=False):
    close_running_app()
    remove_shortcuts()
    dirs = install_dirs()
    remove_registry()
    shutil.rmtree(os.path.join(LOCAL_DIR, "tampon"), ignore_errors=True)
    if remove_data:
        shutil.rmtree(DATA_DIR, ignore_errors=True)
        shutil.rmtree(LOCAL_DIR, ignore_errors=True)
    if remove_videos:
        dd = download_dir()
        if os.path.isdir(dd):
            for f in os.listdir(dd):
                if f.lower().endswith((".mp4", ".mkv", ".avi", ".mov", ".m4v", ".ts", ".wmv", ".flv", ".webm",
                                       ".mpg", ".mpeg", ".part")):
                    try:
                        os.remove(os.path.join(dd, f))
                    except OSError:
                        pass
            try:
                os.rmdir(dd)
            except OSError:
                pass
    ok = True
    here_installed = os.path.exists(os.path.join(HERE, "install.json"))
    for d in dirs + ([HERE] if here_installed and is_app_dir(HERE) and HERE not in dirs else []):
        ok = remove_dir(d) and ok
    refresh_icons()
    return ok


def main():
    if "--quiet" in sys.argv:
        uninstall(False)
        return
    from PySide6 import QtWidgets
    app = QtWidgets.QApplication(sys.argv)
    app.setStyle("Fusion")
    vers = ", ".join(sorted({v for _s, _l, v in registered_installs() if v})) or "installée"
    dlg = QtWidgets.QDialog()
    dlg.setWindowTitle(f"Désinstaller {APP_NAME}")
    v = QtWidgets.QVBoxLayout(dlg)
    v.addWidget(QtWidgets.QLabel(f"<b>Désinstaller {APP_NAME} (version {vers}) ?</b><br><br>"
                                 "Le logiciel, son moteur VLC et tous ses raccourcis (Bureau, menu Démarrer, "
                                 "barre des tâches) seront supprimés."))
    cb = QtWidgets.QCheckBox("Supprimer aussi mes sources, profils, favoris, historique et caches")
    cb2 = QtWidgets.QCheckBox(f"Supprimer aussi les films téléchargés  ({download_dir()})")
    v.addWidget(cb)
    v.addWidget(cb2)
    bb = QtWidgets.QDialogButtonBox()
    b_ok = bb.addButton("Désinstaller", QtWidgets.QDialogButtonBox.ButtonRole.AcceptRole)
    bb.addButton("Annuler", QtWidgets.QDialogButtonBox.ButtonRole.RejectRole)
    bb.accepted.connect(dlg.accept)
    bb.rejected.connect(dlg.reject)
    b_ok.setDefault(True)
    v.addWidget(bb)
    if dlg.exec() != QtWidgets.QDialog.DialogCode.Accepted:
        return
    uninstall(cb.isChecked(), cb2.isChecked())
    QtWidgets.QMessageBox.information(None, APP_NAME, f"{APP_NAME} a été entièrement désinstallé.")


if __name__ == "__main__":
    main()
