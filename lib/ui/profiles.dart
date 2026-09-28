// « Qui regarde ? » : choix, création et modification des profils.
import 'dart:math';

import 'package:flutter/material.dart';

import '../core/store.dart';
import 'scope.dart';
import 'theme.dart';
import 'widgets.dart';

class ProfilesScreen extends StatefulWidget {
  const ProfilesScreen({super.key});
  @override
  State<ProfilesScreen> createState() => _ProfilesScreenState();
}

class _ProfilesScreenState extends State<ProfilesScreen> {
  bool _manage = false;

  Future<void> _pick(AppState s, Map<String, dynamic> p) async {
    if (_manage) return _edit(s, p);
    final pin = '${p['pin'] ?? ''}';
    if (pin.isNotEmpty) {
      final code = await showDialog<String>(context: context, builder: (_) => _PinDialog(name: '${p['name']}'));
      if (code == null) return;
      if (code != pin) {
        if (mounted) toast(context, 'Code PIN incorrect.');
        return;
      }
    }
    s.selectProfile('${p['id']}');
    if (mounted) toast(context, 'Bonjour ${p['name']} 👋');
  }

  Future<void> _edit(AppState s, Map<String, dynamic>? p) async {
    final res = await showDialog<Object>(
        context: context, builder: (_) => ProfileDialog(profile: p, canDelete: p != null && s.profiles.length > 1));
    if (res == 'delete' && p != null) {
      s.deleteProfile('${p['id']}');
    } else if (res is Map<String, dynamic>) {
      s.upsertProfile(res);
    }
  }

  @override
  Widget build(BuildContext context) {
    final s = AppScope.of(context);
    final wide = isWide(context);
    final size = wide ? 140.0 : 100.0;
    final profiles = s.profiles;
    return Scaffold(
      body: SafeArea(
        child: Stack(children: [
          Center(
            child: SingleChildScrollView(
              padding: const EdgeInsets.all(24),
              child: Column(mainAxisSize: MainAxisSize.min, children: [
                Logo(height: wide ? 72 : 56),
                const SizedBox(height: 30),
                Text(_manage ? 'Gérer les profils' : 'Qui regarde ?',
                    style: TextStyle(fontSize: wide ? 34 : 26, fontWeight: FontWeight.w800, color: Colors.white)),
                const SizedBox(height: 26),
                Wrap(spacing: 18, runSpacing: 18, alignment: WrapAlignment.center, children: [
                  for (var i = 0; i < profiles.length; i++)
                    SizedBox(
                      width: size + 20,
                      child: FocusTile(
                        autofocus: i == 0,
                        onTap: () => _pick(s, profiles[i]),
                        builder: (on) => Column(children: [
                          Stack(children: [
                            Container(
                              decoration: BoxDecoration(
                                borderRadius: BorderRadius.circular(size * .18),
                                border: Border.all(color: on ? Colors.white : Colors.transparent, width: 3),
                              ),
                              child: AvatarView(profiles[i], size: size),
                            ),
                            if (_manage)
                              Positioned.fill(
                                child: Container(
                                  decoration: BoxDecoration(color: Colors.black54, borderRadius: BorderRadius.circular(size * .16)),
                                  child: const Icon(Icons.edit, size: 40),
                                ),
                              ),
                          ]),
                          const SizedBox(height: 10),
                          Text('${profiles[i]['name']}', maxLines: 1, overflow: TextOverflow.ellipsis,
                              style: TextStyle(fontWeight: FontWeight.w700, fontSize: 15, color: on ? Colors.white : const Color(0xFFC9CCD6))),
                          if (profiles[i]['kids'] == true || '${profiles[i]['pin'] ?? ''}'.isNotEmpty)
                            Text([if (profiles[i]['kids'] == true) 'Enfant', if ('${profiles[i]['pin'] ?? ''}'.isNotEmpty) '🔒'].join(' · '),
                                style: const TextStyle(color: kMuted, fontSize: 12)),
                        ]),
                      ),
                    ),
                  if (profiles.length < 8)
                    SizedBox(
                      width: size + 20,
                      child: FocusTile(
                        onTap: () => _edit(s, null),
                        builder: (on) => Column(children: [
                          Container(
                            width: size, height: size,
                            decoration: BoxDecoration(
                              color: kCard2,
                              borderRadius: BorderRadius.circular(size * .16),
                              border: Border.all(color: on ? Colors.white : const Color(0xFF3A4050), width: 2),
                            ),
                            child: const Icon(Icons.add, size: 44, color: kMuted),
                          ),
                          const SizedBox(height: 10),
                          const Text('Ajouter un profil', style: TextStyle(fontWeight: FontWeight.w700, fontSize: 15)),
                        ]),
                      ),
                    ),
                ]),
                const SizedBox(height: 34),
                OutlinedButton.icon(
                  onPressed: () => setState(() => _manage = !_manage),
                  icon: Icon(_manage ? Icons.check : Icons.edit_outlined),
                  label: Text(_manage ? 'Terminé' : 'Gérer les profils'),
                ),
              ]),
            ),
          ),
          const Positioned(left: 14, bottom: 12, child: Signature(size: 18)),
        ]),
      ),
    );
  }
}

class _PinDialog extends StatefulWidget {
  final String name;
  const _PinDialog({required this.name});
  @override
  State<_PinDialog> createState() => _PinDialogState();
}

class _PinDialogState extends State<_PinDialog> {
  final _c = TextEditingController();
  @override
  Widget build(BuildContext context) => AlertDialog(
        title: Text('Code PIN de ${widget.name}'),
        content: TextField(
          controller: _c,
          autofocus: true,
          obscureText: true,
          maxLength: 4,
          keyboardType: TextInputType.number,
          textAlign: TextAlign.center,
          style: const TextStyle(fontSize: 26, letterSpacing: 12),
          onSubmitted: (v) => Navigator.pop(context, v.trim()),
        ),
        actions: [
          TextButton(onPressed: () => Navigator.pop(context), child: const Text('Annuler')),
          FilledButton(onPressed: () => Navigator.pop(context, _c.text.trim()), child: const Text('Valider')),
        ],
      );
}

class ProfileDialog extends StatefulWidget {
  final Map<String, dynamic>? profile;
  final bool canDelete;
  const ProfileDialog({super.key, this.profile, this.canDelete = false});
  @override
  State<ProfileDialog> createState() => _ProfileDialogState();
}

class _ProfileDialogState extends State<ProfileDialog> {
  late final Map<String, dynamic> _p = Map<String, dynamic>.from(widget.profile ??
      {'id': AppState.newId(), 'name': '', 'color': kAvatarColors[Random().nextInt(kAvatarColors.length)], 'emoji': '', 'kids': false, 'pin': ''});
  late final _name = TextEditingController(text: '${_p['name']}');
  late final _pin = TextEditingController(text: '${_p['pin'] ?? ''}');
  String? _err;

  void _save() {
    final n = _name.text.trim();
    final pin = _pin.text.trim();
    if (n.isEmpty) return setState(() => _err = 'Donnez un nom au profil.');
    if (pin.isNotEmpty && !RegExp(r'^\d{4}$').hasMatch(pin)) return setState(() => _err = 'Le code PIN doit comporter 4 chiffres.');
    _p['name'] = n;
    _p['pin'] = pin;
    Navigator.pop(context, _p);
  }

  @override
  Widget build(BuildContext context) {
    return AlertDialog(
      title: Text(widget.profile == null ? 'Nouveau profil' : 'Modifier le profil'),
      content: SizedBox(
        width: 480,
        child: SingleChildScrollView(
          child: Column(mainAxisSize: MainAxisSize.min, crossAxisAlignment: CrossAxisAlignment.start, children: [
            Row(children: [
              AvatarView({..._p, 'name': _name.text}, size: 84),
              const SizedBox(width: 16),
              Expanded(
                child: Column(children: [
                  TextField(controller: _name, onChanged: (_) => setState(() {}), decoration: const InputDecoration(labelText: 'Nom')),
                  const SizedBox(height: 10),
                  TextField(
                    controller: _pin, obscureText: true, maxLength: 4, keyboardType: TextInputType.number,
                    decoration: const InputDecoration(labelText: 'Code PIN (facultatif)', counterText: ''),
                  ),
                ]),
              ),
            ]),
            SwitchListTile(
              contentPadding: EdgeInsets.zero,
              value: _p['kids'] == true,
              onChanged: (v) => setState(() => _p['kids'] = v),
              title: const Text('Profil enfant'),
              subtitle: const Text('Masque les catégories pour adultes', style: TextStyle(color: kMuted)),
            ),
            const Text('Couleur', style: TextStyle(color: kMuted)),
            const SizedBox(height: 6),
            Wrap(spacing: 8, runSpacing: 8, children: [
              for (final c in kAvatarColors)
                InkWell(
                  onTap: () => setState(() => _p['color'] = c),
                  customBorder: const CircleBorder(),
                  child: Container(
                    width: 34, height: 34,
                    decoration: BoxDecoration(
                      color: Color(c), shape: BoxShape.circle,
                      border: Border.all(color: _p['color'] == c ? Colors.white : Colors.transparent, width: 3),
                    ),
                  ),
                ),
            ]),
            const SizedBox(height: 14),
            const Text('Avatar', style: TextStyle(color: kMuted)),
            const SizedBox(height: 6),
            Wrap(spacing: 6, runSpacing: 6, children: [
              for (final e in kAvatarEmojis)
                InkWell(
                  onTap: () => setState(() => _p['emoji'] = e),
                  borderRadius: BorderRadius.circular(10),
                  child: Container(
                    width: 44, height: 44,
                    alignment: Alignment.center,
                    decoration: BoxDecoration(
                      color: kCard2,
                      borderRadius: BorderRadius.circular(10),
                      border: Border.all(color: _p['emoji'] == e ? kAccent : kBorder, width: _p['emoji'] == e ? 2 : 1),
                    ),
                    child: Text(e.isEmpty ? 'Aa' : e, style: const TextStyle(fontSize: 20)),
                  ),
                ),
            ]),
            if (_err != null) Padding(padding: const EdgeInsets.only(top: 10), child: Text(_err!, style: const TextStyle(color: kAccent))),
          ]),
        ),
      ),
      actions: [
        if (widget.canDelete)
          TextButton(
            onPressed: () => Navigator.pop(context, 'delete'),
            style: TextButton.styleFrom(foregroundColor: kAccent),
            child: const Text('Supprimer'),
          ),
        TextButton(onPressed: () => Navigator.pop(context), child: const Text('Annuler')),
        FilledButton(onPressed: _save, child: const Text('Enregistrer')),
      ],
    );
  }
}
