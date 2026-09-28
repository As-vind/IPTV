#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Installateur d'IPTV Player (par Asvind)

Utilise le Python officiel déjà installé (signé, donc accepté par le contrôle
intelligent des applications). Il :
  1. installe les modules Python nécessaires (PySide6, python-vlc, pylnk3) ;
  2. copie le logiciel dans %LOCALAPPDATA%\\Programs\\IPTV Player (pas besoin d'admin) ;
  3. intègre le moteur VLC 64 bits (libvlc + modules) dans le dossier du logiciel :
     copié depuis un VLC déjà installé, sinon téléchargé depuis videolan.org ;
  4. crée les raccourcis Bureau / menu Démarrer ;
  5. ajoute IPTV Player dans « Applications installées » (désinstallation propre).
"""

import os
import re
import sys
import json
import shutil
import struct
import hashlib
import zipfile
import subprocess
import urllib.request

APP_NAME = "IPTV Player"
APP_VERSION = "2.1"
PUBLISHER = "Asvind"
REG_KEY = r"Software\Microsoft\Windows\CurrentVersion\Uninstall\IPTVPlayer"
HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_DIR = os.path.join(os.environ.get("LOCALAPPDATA") or os.path.expanduser("~"), "Programs", APP_NAME)
APP_FILES = ["iptv_player.py", "uninstall.py", "app.ico", "logo_dark.png", "logo_light.png", "LISEZMOI.txt"]
VLC_FILES = ["libvlc.dll", "libvlccore.dll"]
VLC_INDEX = "https://download.videolan.org/pub/videolan/vlc/last/win64/"
VLC_FALLBACK = "https://download.videolan.org/pub/videolan/vlc/3.0.21/win64/vlc-3.0.21-win64.zip"
NO_WINDOW = 0x08000000


# --------------------------------------------------------------------------- #
#  Étape 0 : modules Python (en console, avant l'interface)
# --------------------------------------------------------------------------- #
def ensure_modules():
    try:
        import PySide6  # noqa: F401
        import vlc  # noqa: F401  (le module python ; la DLL VLC est gérée plus loin)
        import pylnk3  # noqa: F401
        return True
    except Exception:
        pass
    print("=" * 64)
    print(f"  {APP_NAME} {APP_VERSION} — installation des modules Python")
    print("=" * 64)
    cmd = [sys.executable, "-m", "pip", "install", "--upgrade", "--disable-pip-version-check",
           "PySide6>=6.5", "python-vlc>=3.0.18", "pylnk3"]
    r = subprocess.call(cmd)
    if r != 0:
        print("\nÉchec de l'installation des modules (voir ci-dessus).")
        input("Appuyez sur Entrée pour fermer…")
        sys.exit(1)
    # les modules installés dans le dossier utilisateur ne sont visibles qu'au prochain lancement
    sys.exit(subprocess.call([sys.executable, os.path.abspath(__file__), "--gui"]))


if __name__ == "__main__" and "--gui" not in sys.argv:
    ensure_modules()

from PySide6 import QtCore, QtGui, QtWidgets  # noqa: E402

Qt = QtCore.Qt


# --------------------------------------------------------------------------- #
#  Utilitaires
# --------------------------------------------------------------------------- #
def pythonw_path():
    d = os.path.dirname(sys.executable)
    for name in ("pythonw.exe", "pythonw"):
        p = os.path.join(d, name)
        if os.path.exists(p):
            return p
    return sys.executable


def find_installed_vlc():
    """Dossier d'un VLC 64 bits déjà installé, ou None."""
    cands = []
    try:
        import winreg
        for hive in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
            for view in (winreg.KEY_WOW64_64KEY, 0):
                try:
                    with winreg.OpenKey(hive, r"SOFTWARE\VideoLAN\VLC", 0, winreg.KEY_READ | view) as k:
                        cands.append(winreg.QueryValueEx(k, "InstallDir")[0])
                except OSError:
                    pass
    except ImportError:
        pass
    pf = os.environ.get("ProgramW6432") or os.environ.get("ProgramFiles") or r"C:\Program Files"
    cands.append(os.path.join(pf, "VideoLAN", "VLC"))
    for c in cands:
        if c and os.path.isfile(os.path.join(c, "libvlc.dll")) and os.path.isdir(os.path.join(c, "plugins")) \
                and "(x86)" not in c:
            return c
    return None


def vlc_ok(folder):
    """Vérifie, dans un processus séparé, que le moteur VLC du dossier se charge."""
    code = ("import os,sys;d=sys.argv[1];os.environ['PYTHON_VLC_LIB_PATH']=os.path.join(d,'libvlc.dll');"
            "os.environ['PYTHON_VLC_MODULE_PATH']=os.path.join(d,'plugins');"
            "os.add_dll_directory(d);import vlc;i=vlc.Instance('--quiet');sys.exit(0 if i else 3)")
    try:
        r = subprocess.run([sys.executable, "-c", code, folder], capture_output=True, timeout=60,
                           creationflags=NO_WINDOW if os.name == "nt" else 0)
        return r.returncode == 0
    except Exception:
        return False


def make_shortcut(path, target, args, icon, workdir, desc):
    import pylnk3
    os.makedirs(os.path.dirname(path), exist_ok=True)
    pylnk3.for_file(target, path, arguments=args, description=desc, icon_file=icon, work_dir=workdir)


def special_folder(name):
    """Bureau / menu Démarrer de l'utilisateur (gère les dossiers redirigés, ex. OneDrive)."""
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                            r"Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders") as k:
            v = winreg.QueryValueEx(k, name)[0]
            return os.path.expandvars(v)
    except Exception:
        home = os.path.expanduser("~")
        return os.path.join(home, "Desktop") if name == "Desktop" else \
            os.path.join(os.environ.get("APPDATA", home), r"Microsoft\Windows\Start Menu\Programs")


def dir_size_kb(path):
    total = 0
    for root, _d, files in os.walk(path):
        for f in files:
            try:
                total += os.path.getsize(os.path.join(root, f))
            except OSError:
                pass
    return total // 1024


# --------------------------------------------------------------------------- #
#  Travail d'installation (thread)
# --------------------------------------------------------------------------- #
class Installer(QtCore.QObject):
    step = QtCore.Signal(str)
    progress = QtCore.Signal(int, int)       # valeur, maximum (0 = indéterminé)
    log = QtCore.Signal(str)
    finished = QtCore.Signal(bool, str)

    def __init__(self, target, desktop, startmenu):
        super().__init__()
        self.target, self.desktop, self.startmenu = target, desktop, startmenu

    def run(self):
        try:
            self._run()
            self.finished.emit(True, "")
        except Exception as e:
            self.finished.emit(False, str(e))

    def _run(self):
        t = self.target
        os.makedirs(t, exist_ok=True)

        # 1. fichiers du logiciel
        self.step.emit("Copie du logiciel…")
        self.progress.emit(0, 0)
        for f in APP_FILES:
            src = os.path.join(HERE, f)
            if os.path.exists(src):
                shutil.copy2(src, os.path.join(t, f))
                self.log.emit(f"✓ {f}")
        if not os.path.exists(os.path.join(t, "iptv_player.py")):
            raise RuntimeError("iptv_player.py est introuvable à côté de l'installateur.")

        # 2. moteur VLC intégré
        vdir = os.path.join(t, "vlc")
        if os.path.isfile(os.path.join(vdir, "libvlc.dll")) and vlc_ok(vdir):
            self.log.emit("✓ Moteur VLC déjà présent")
        else:
            src = find_installed_vlc()
            if src:
                self.step.emit("Intégration du moteur VLC (depuis votre VLC installé)…")
                self.log.emit(f"VLC trouvé : {src}")
                self._copy_vlc_from(src, vdir)
            else:
                self.step.emit("Téléchargement du moteur VLC depuis videolan.org…")
                self._download_vlc(vdir)
            self.step.emit("Vérification du moteur VLC…")
            self.progress.emit(0, 0)
            if not vlc_ok(vdir):
                raise RuntimeError("Le moteur VLC intégré ne se charge pas. Vérifiez que Python est bien en "
                                   "64 bits, puis relancez l'installation.")
            self.log.emit("✓ Moteur VLC opérationnel")

        # 3. raccourcis
        self.step.emit("Création des raccourcis…")
        pyw = pythonw_path()
        script = os.path.join(t, "iptv_player.py")
        icon = os.path.join(t, "app.ico")
        args = f'"{script}"'
        todo = []
        if self.desktop:
            todo.append((os.path.join(special_folder("Desktop"), f"{APP_NAME}.lnk"), args, APP_NAME, "Bureau"))
        if self.startmenu:
            sm = os.path.join(special_folder("Programs"), APP_NAME)
            todo.append((os.path.join(sm, f"{APP_NAME}.lnk"), args, APP_NAME, "menu Démarrer"))
            todo.append((os.path.join(sm, f"Désinstaller {APP_NAME}.lnk"),
                         f'"{os.path.join(t, "uninstall.py")}"', f"Désinstaller {APP_NAME}", None))
        for path, a, desc, where in todo:
            try:
                make_shortcut(path, pyw, a, icon, t, f"{desc} — par {PUBLISHER}")
                if where:
                    self.log.emit(f"✓ Raccourci : {where}")
            except Exception as e:
                self.log.emit(f"⚠ Raccourci non créé ({os.path.basename(path)}) : {e}")

        # 4. « Applications installées »
        self.step.emit("Enregistrement dans Windows…")
        try:
            import winreg
            with winreg.CreateKey(winreg.HKEY_CURRENT_USER, REG_KEY) as k:
                vals = {
                    "DisplayName": APP_NAME, "DisplayVersion": APP_VERSION, "Publisher": PUBLISHER,
                    "DisplayIcon": icon, "InstallLocation": t,
                    "UninstallString": f'"{pyw}" "{os.path.join(t, "uninstall.py")}"',
                    "QuietUninstallString": f'"{pyw}" "{os.path.join(t, "uninstall.py")}" --quiet',
                }
                for n, v in vals.items():
                    winreg.SetValueEx(k, n, 0, winreg.REG_SZ, v)
                winreg.SetValueEx(k, "EstimatedSize", 0, winreg.REG_DWORD, dir_size_kb(t))
                winreg.SetValueEx(k, "NoModify", 0, winreg.REG_DWORD, 1)
                winreg.SetValueEx(k, "NoRepair", 0, winreg.REG_DWORD, 1)
            self.log.emit("✓ Ajouté à « Applications installées »")
        except Exception as e:
            self.log.emit(f"(registre non modifié : {e})")
        with open(os.path.join(t, "install.json"), "w", encoding="utf-8") as f:
            json.dump({"version": APP_VERSION, "python": sys.executable, "pythonw": pyw,
                       "desktop": self.desktop, "startmenu": self.startmenu}, f, indent=1)

    def _copy_vlc_from(self, src, dst):
        files = [os.path.join(src, f) for f in VLC_FILES]
        for root, _d, fs in os.walk(os.path.join(src, "plugins")):
            files += [os.path.join(root, f) for f in fs]
        if os.path.isdir(dst):
            shutil.rmtree(dst, ignore_errors=True)
        n = len(files)
        for i, f in enumerate(files):
            rel = os.path.relpath(f, src)
            out = os.path.join(dst, rel)
            os.makedirs(os.path.dirname(out), exist_ok=True)
            shutil.copy2(f, out)
            if i % 20 == 0:
                self.progress.emit(i, n)
        self.progress.emit(n, n)
        self.log.emit(f"✓ {n} fichiers VLC intégrés")

    def _download_vlc(self, dst):
        url = VLC_FALLBACK
        try:
            html = urllib.request.urlopen(VLC_INDEX, timeout=20).read().decode("utf-8", "replace")
            m = re.search(r'href="(vlc-[\d.]+-win64\.zip)"', html)
            if m:
                url = VLC_INDEX + m.group(1)
        except Exception:
            pass
        self.log.emit(f"Source : {url}")
        tmp = os.path.join(os.environ.get("TEMP", self.target), "iptvplayer-vlc.zip")
        req = urllib.request.Request(url, headers={"User-Agent": f"{APP_NAME}-installer/{APP_VERSION}"})
        h = hashlib.sha256()
        with urllib.request.urlopen(req, timeout=60) as r, open(tmp, "wb") as f:
            total = int(r.headers.get("Content-Length") or 0)
            done = 0
            while True:
                chunk = r.read(1 << 16)
                if not chunk:
                    break
                f.write(chunk)
                h.update(chunk)
                done += len(chunk)
                self.progress.emit(done // 1024, total // 1024)
        self.log.emit(f"✓ Téléchargé ({done // (1 << 20)} Mo)")
        try:
            ref = urllib.request.urlopen(url + ".sha256", timeout=20).read().decode().split()[0].lower()
            if ref != h.hexdigest():
                os.remove(tmp)
                raise RuntimeError("Le fichier VLC téléchargé est corrompu (empreinte SHA-256 différente).")
            self.log.emit("✓ Empreinte SHA-256 vérifiée")
        except RuntimeError:
            raise
        except Exception:
            self.log.emit("(empreinte SHA-256 non disponible)")
        self.step.emit("Extraction du moteur VLC…")
        if os.path.isdir(dst):
            shutil.rmtree(dst, ignore_errors=True)
        with zipfile.ZipFile(tmp) as z:
            names = [n for n in z.namelist() if not n.endswith("/")]
            keep = []
            for n in names:
                parts = n.split("/", 1)
                if len(parts) < 2:
                    continue
                rel = parts[1]
                if rel in VLC_FILES or rel.startswith("plugins/"):
                    keep.append((n, rel))
            for i, (n, rel) in enumerate(keep):
                out = os.path.join(dst, *rel.split("/"))
                os.makedirs(os.path.dirname(out), exist_ok=True)
                with z.open(n) as s, open(out, "wb") as o:
                    shutil.copyfileobj(s, o)
                if i % 20 == 0:
                    self.progress.emit(i, len(keep))
        try:
            os.remove(tmp)
        except OSError:
            pass
        self.log.emit(f"✓ {len(keep)} fichiers VLC intégrés")


# --------------------------------------------------------------------------- #
#  Interface
# --------------------------------------------------------------------------- #
ACCENT = "#e8252c"
STYLE = """
QWidget { background:#0e1016; color:#e8eaf0; font-family:'Segoe UI'; font-size:10pt; }
#title { font-size:24pt; font-weight:800; }
#sub { color:#a3a8b8; font-size:10.5pt; }
#sig { font-family:'Segoe Script','Brush Script MT',cursive; font-size:16pt; font-style:italic; color:%(A)s; }
#step { font-weight:700; font-size:10.5pt; }
QLineEdit { background:#161923; border:1px solid #262a37; border-radius:8px; padding:7px 10px; }
QPushButton { background:#1c1f29; border:1px solid #2a2e3b; border-radius:9px; padding:8px 16px; }
QPushButton:hover { background:#262a37; }
QPushButton#primary { background:%(A)s; border:0; color:white; font-weight:700; padding:10px 26px; font-size:10.5pt; }
QPushButton#primary:hover { background:#ff3b41; }
QPushButton#primary:disabled { background:#4a2a2c; color:#b09a9a; }
QCheckBox { spacing:8px; }
QCheckBox::indicator { width:18px; height:18px; border-radius:5px; border:1px solid #3a3f50; background:#161923; }
QCheckBox::indicator:checked { background:%(A)s; border-color:%(A)s; }
QProgressBar { background:#1c1f29; border:0; border-radius:4px; height:8px; text-align:center; color:transparent; }
QProgressBar::chunk { background:%(A)s; border-radius:4px; }
QPlainTextEdit { background:#0a0b0f; border:1px solid #1f222d; border-radius:8px; color:#a3a8b8; font-size:9pt; }
""" % {"A": ACCENT}


def logo_pixmap(size=72):
    ico = os.path.join(HERE, "app.ico")
    if os.path.exists(ico):
        return QtGui.QIcon(ico).pixmap(size, size)
    pm = QtGui.QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)
    return pm


class Window(QtWidgets.QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"Installation — {APP_NAME} {APP_VERSION}")
        ico = os.path.join(HERE, "app.ico")
        if os.path.exists(ico):
            self.setWindowIcon(QtGui.QIcon(ico))
        self.setFixedSize(640, 560)
        v = QtWidgets.QVBoxLayout(self)
        v.setContentsMargins(34, 28, 34, 24)
        v.setSpacing(12)

        head = QtWidgets.QVBoxLayout()
        lg = QtWidgets.QLabel()
        logo = os.path.join(HERE, "logo_dark.png")   # fond sombre → logo inversé
        if os.path.exists(logo):
            pm = QtGui.QPixmap(logo)
            dpr = self.devicePixelRatioF()
            pm = pm.scaledToHeight(int(62 * dpr), Qt.TransformationMode.SmoothTransformation)
            pm.setDevicePixelRatio(dpr)
            lg.setPixmap(pm)
        else:
            lg.setPixmap(logo_pixmap(72))
        head.addWidget(lg)
        s = QtWidgets.QLabel(f"Version {APP_VERSION} · TV, films et séries IPTV pour Windows")
        s.setObjectName("sub")
        head.addWidget(s)
        v.addLayout(head)
        v.addSpacing(6)

        v.addWidget(QtWidgets.QLabel("Dossier d'installation (aucun droit administrateur nécessaire) :"))
        row = QtWidgets.QHBoxLayout()
        self.path = QtWidgets.QLineEdit(DEFAULT_DIR)
        b = QtWidgets.QPushButton("Parcourir…")
        b.clicked.connect(self._browse)
        row.addWidget(self.path, 1)
        row.addWidget(b)
        v.addLayout(row)
        self.cb_desk = QtWidgets.QCheckBox("Créer un raccourci sur le Bureau")
        self.cb_start = QtWidgets.QCheckBox("Ajouter au menu Démarrer")
        self.cb_run = QtWidgets.QCheckBox("Lancer IPTV Player à la fin de l'installation")
        for c in (self.cb_desk, self.cb_start, self.cb_run):
            c.setChecked(True)
            v.addWidget(c)
        vlc_src = find_installed_vlc()
        info = QtWidgets.QLabel(
            "Moteur vidéo : " + ("copié depuis votre VLC installé." if vlc_src else
                                 "VLC 64 bits sera téléchargé depuis videolan.org (≈ 60 Mo) et intégré au logiciel."))
        info.setObjectName("sub")
        info.setWordWrap(True)
        v.addWidget(info)
        if struct.calcsize("P") != 8:
            warn = QtWidgets.QLabel("⚠ Ce Python est en 32 bits : installez Python 64 bits depuis python.org.")
            warn.setStyleSheet("color:#ff6b7a; font-weight:700;")
            v.addWidget(warn)

        v.addSpacing(4)
        self.step = QtWidgets.QLabel("Prêt à installer.")
        self.step.setObjectName("step")
        self.bar = QtWidgets.QProgressBar()
        self.bar.setFixedHeight(8)
        self.bar.setRange(0, 1)
        self.bar.setValue(0)
        self.logw = QtWidgets.QPlainTextEdit()
        self.logw.setReadOnly(True)
        v.addWidget(self.step)
        v.addWidget(self.bar)
        v.addWidget(self.logw, 1)

        foot = QtWidgets.QHBoxLayout()
        sig = QtWidgets.QLabel(PUBLISHER)
        sig.setObjectName("sig")
        foot.addWidget(sig, 0, Qt.AlignmentFlag.AlignBottom)
        foot.addStretch(1)
        self.b_cancel = QtWidgets.QPushButton("Fermer")
        self.b_cancel.clicked.connect(self.close)
        self.b_go = QtWidgets.QPushButton("Installer")
        self.b_go.setObjectName("primary")
        self.b_go.clicked.connect(self._go)
        foot.addWidget(self.b_cancel)
        foot.addWidget(self.b_go)
        v.addLayout(foot)
        self.thread = None
        self.done = False

    def _browse(self):
        d = QtWidgets.QFileDialog.getExistingDirectory(self, "Dossier d'installation", self.path.text())
        if d:
            d = os.path.normpath(d)
            if os.path.basename(d).lower() != APP_NAME.lower():
                d = os.path.join(d, APP_NAME)
            self.path.setText(d)

    def _go(self):
        if self.done:
            self._launch()
            return
        if struct.calcsize("P") != 8:
            QtWidgets.QMessageBox.warning(self, APP_NAME, "Python 64 bits est nécessaire pour le moteur VLC.")
            return
        self.b_go.setEnabled(False)
        self.b_cancel.setEnabled(False)
        for w in (self.path, self.cb_desk, self.cb_start):
            w.setEnabled(False)
        self.worker = Installer(os.path.normpath(self.path.text().strip()), self.cb_desk.isChecked(),
                                self.cb_start.isChecked())
        self.thread = QtCore.QThread(self)
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.run)
        self.worker.step.connect(self.step.setText)
        self.worker.log.connect(self.logw.appendPlainText)
        self.worker.progress.connect(self._progress)
        self.worker.finished.connect(self._finished)
        self.thread.start()

    def _progress(self, val, mx):
        self.bar.setRange(0, mx)
        if mx:
            self.bar.setValue(val)

    def _finished(self, ok, err):
        self.thread.quit()
        self.thread.wait()
        self.b_cancel.setEnabled(True)
        self.bar.setRange(0, 1)
        if ok:
            self.bar.setValue(1)
            self.step.setText("✓ Installation terminée.")
            self.logw.appendPlainText(f"\n{APP_NAME} est installé dans :\n{self.worker.target}")
            self.done = True
            self.b_go.setText("Lancer IPTV Player")
            self.b_go.setEnabled(True)
            if self.cb_run.isChecked():
                self._launch()
        else:
            self.bar.setValue(0)
            self.step.setText("✗ L'installation a échoué.")
            self.logw.appendPlainText(f"\nErreur : {err}")
            self.b_go.setEnabled(True)
            for w in (self.path, self.cb_desk, self.cb_start):
                w.setEnabled(True)
            QtWidgets.QMessageBox.critical(self, APP_NAME, f"L'installation a échoué :\n\n{err}")

    def _launch(self):
        t = self.worker.target
        subprocess.Popen([pythonw_path(), os.path.join(t, "iptv_player.py")], cwd=t,
                         creationflags=NO_WINDOW if os.name == "nt" else 0)
        self.close()


def main():
    if sys.platform.startswith("win"):
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("IPTVPlayer.Installer")
        except Exception:
            pass
    app = QtWidgets.QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setStyleSheet(STYLE)
    w = Window()
    w.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
