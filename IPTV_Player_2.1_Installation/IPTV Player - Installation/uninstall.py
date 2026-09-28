#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Désinstallation d'IPTV Player (par Asvind)."""
import os
import sys
import shutil

APP_NAME = "IPTV Player"
REG_KEY = r"Software\Microsoft\Windows\CurrentVersion\Uninstall\IPTVPlayer"
HERE = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(os.environ.get("APPDATA") or os.path.expanduser("~"), "IPTVPlayer")


def special_folder(name):
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                            r"Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders") as k:
            return os.path.expandvars(winreg.QueryValueEx(k, name)[0])
    except Exception:
        home = os.path.expanduser("~")
        return os.path.join(home, "Desktop") if name == "Desktop" else \
            os.path.join(os.environ.get("APPDATA", home), r"Microsoft\Windows\Start Menu\Programs")


def uninstall(remove_data):
    for p in (os.path.join(special_folder("Desktop"), f"{APP_NAME}.lnk"),):
        try:
            os.remove(p)
        except OSError:
            pass
    shutil.rmtree(os.path.join(special_folder("Programs"), APP_NAME), ignore_errors=True)
    try:
        import winreg
        winreg.DeleteKey(winreg.HKEY_CURRENT_USER, REG_KEY)
    except Exception:
        pass
    if remove_data:
        shutil.rmtree(DATA_DIR, ignore_errors=True)
    # sécurité : on ne supprime que le dossier du logiciel lui-même
    if os.path.exists(os.path.join(HERE, "iptv_player.py")) and os.path.exists(os.path.join(HERE, "install.json")):
        shutil.rmtree(HERE, ignore_errors=True)


def main():
    quiet = "--quiet" in sys.argv
    if quiet:
        uninstall(False)
        return
    from PySide6 import QtWidgets
    app = QtWidgets.QApplication(sys.argv)
    app.setStyle("Fusion")
    box = QtWidgets.QMessageBox()
    box.setWindowTitle(f"Désinstaller {APP_NAME}")
    box.setText(f"Voulez-vous désinstaller {APP_NAME} ?")
    cb = QtWidgets.QCheckBox("Supprimer aussi mes sources, favoris, historique et caches")
    box.setCheckBox(cb)
    box.setStandardButtons(QtWidgets.QMessageBox.StandardButton.Yes | QtWidgets.QMessageBox.StandardButton.No)
    box.button(QtWidgets.QMessageBox.StandardButton.Yes).setText("Désinstaller")
    box.button(QtWidgets.QMessageBox.StandardButton.No).setText("Annuler")
    if box.exec() != QtWidgets.QMessageBox.StandardButton.Yes:
        return
    uninstall(cb.isChecked())
    QtWidgets.QMessageBox.information(None, APP_NAME, f"{APP_NAME} a été désinstallé.")


if __name__ == "__main__":
    main()
