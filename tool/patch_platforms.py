#!/usr/bin/env python3
"""Réglages natifs : réseau HTTP, Android TV, nom de l'app, iOS 13+."""
import os, re, shutil

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP = "IPTV Player"

# ---------------- Android
man = os.path.join(ROOT, "android/app/src/main/AndroidManifest.xml")
s = open(man, encoding="utf-8").read()
if "android.permission.INTERNET" not in s:
    s = s.replace("<application", '<uses-permission android:name="android.permission.INTERNET"/>\n'
                  '    <uses-feature android:name="android.software.leanback" android:required="false"/>\n'
                  '    <uses-feature android:name="android.hardware.touchscreen" android:required="false"/>\n'
                  "    <application", 1)
s = re.sub(r'android:label="[^"]*"', f'android:label="{APP}"', s, count=1)
if "usesCleartextTraffic" not in s:
    s = s.replace("<application", '<application\n        android:usesCleartextTraffic="true"\n        android:banner="@drawable/tv_banner"', 1)
if "LEANBACK_LAUNCHER" not in s:
    s = s.replace('<category android:name="android.intent.category.LAUNCHER"/>',
                  '<category android:name="android.intent.category.LAUNCHER"/>\n'
                  '                <category android:name="android.intent.category.LEANBACK_LAUNCHER"/>', 1)
open(man, "w", encoding="utf-8").write(s)
dr = os.path.join(ROOT, "android/app/src/main/res/drawable")
os.makedirs(dr, exist_ok=True)
shutil.copy(os.path.join(ROOT, "assets/tv_banner.png"), os.path.join(dr, "tv_banner.png"))

# ---------------- Android : signature « stores » (android/key.properties créé en CI à partir des secrets)
for gname in ("android/app/build.gradle.kts", "android/app/build.gradle"):
    gp = os.path.join(ROOT, gname)
    if not os.path.exists(gp):
        continue
    g = open(gp, encoding="utf-8").read()
    if "key.properties" in g:
        break
    if gname.endswith(".kts"):
        g = "import java.util.Properties\nimport java.io.FileInputStream\n\n" + g
        g = g.replace("android {", """val keystoreProperties = Properties()
val keystorePropertiesFile = rootProject.file("key.properties")
if (keystorePropertiesFile.exists()) {
    keystoreProperties.load(FileInputStream(keystorePropertiesFile))
}

android {
    signingConfigs {
        create("release") {
            if (keystorePropertiesFile.exists()) {
                keyAlias = keystoreProperties["keyAlias"] as String
                keyPassword = keystoreProperties["keyPassword"] as String
                storeFile = file(keystoreProperties["storeFile"] as String)
                storePassword = keystoreProperties["storePassword"] as String
            }
        }
    }""", 1)
        g = re.sub(r'signingConfig = signingConfigs\.getByName\("debug"\)',
                   'signingConfig = if (keystorePropertiesFile.exists()) signingConfigs.getByName("release") '
                   'else signingConfigs.getByName("debug")', g, count=1)
    else:
        g = g.replace("android {", """def keystoreProperties = new Properties()
def keystorePropertiesFile = rootProject.file('key.properties')
if (keystorePropertiesFile.exists()) {
    keystoreProperties.load(new FileInputStream(keystorePropertiesFile))
}

android {
    signingConfigs {
        release {
            if (keystorePropertiesFile.exists()) {
                keyAlias keystoreProperties['keyAlias']
                keyPassword keystoreProperties['keyPassword']
                storeFile file(keystoreProperties['storeFile'])
                storePassword keystoreProperties['storePassword']
            }
        }
    }""", 1)
        g = re.sub(r"signingConfig signingConfigs\.debug",
                   "signingConfig keystorePropertiesFile.exists() ? signingConfigs.release : signingConfigs.debug", g, count=1)
    open(gp, "w", encoding="utf-8").write(g)
    break

# ---------------- iOS
plist = os.path.join(ROOT, "ios/Runner/Info.plist")
p = open(plist, encoding="utf-8").read()
p = re.sub(r"(<key>CFBundleDisplayName</key>\s*<string>)[^<]*(</string>)", rf"\g<1>{APP}\g<2>", p)
if "NSAppTransportSecurity" not in p:
    extra = ("\t<key>NSAppTransportSecurity</key>\n\t<dict>\n\t\t<key>NSAllowsArbitraryLoads</key>\n\t\t<true/>\n"
             "\t\t<key>NSAllowsArbitraryLoadsForMedia</key>\n\t\t<true/>\n\t</dict>\n"
             "\t<key>UIFileSharingEnabled</key>\n\t<true/>\n"
             "\t<key>LSSupportsOpeningDocumentsInPlace</key>\n\t<true/>\n"
             "\t<key>ITSAppUsesNonExemptEncryption</key>\n\t<false/>\n")
    idx = p.rfind("</dict>")
    p = p[:idx] + extra + p[idx:]
open(plist, "w", encoding="utf-8").write(p)
pod = os.path.join(ROOT, "ios/Podfile")
if os.path.exists(pod):
    t = open(pod, encoding="utf-8").read()
    t = re.sub(r"^#?\s*platform :ios, '[\d.]+'", "platform :ios, '13.0'", t, flags=re.M)
    open(pod, "w", encoding="utf-8").write(t)
pbx = os.path.join(ROOT, "ios/Runner.xcodeproj/project.pbxproj")
t = open(pbx, encoding="utf-8").read()
t = re.sub(r"IPHONEOS_DEPLOYMENT_TARGET = [\d.]+;", "IPHONEOS_DEPLOYMENT_TARGET = 13.0;", t)
open(pbx, "w", encoding="utf-8").write(t)
print("Plateformes configurées.")
