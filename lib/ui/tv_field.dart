// Champ de saisie adapté à la télécommande :
// - sélectionner le champ (flèches) ne fait JAMAIS apparaître le clavier ;
// - la touche OK ouvre la saisie dans un panneau en haut de l'écran, toujours au-dessus du clavier ;
// - OK / « Terminé » valide, Retour annule ; le clavier se ferme et le focus revient sur le champ ;
// - au doigt (téléphone, tablette), un appui sur le champ permet d'écrire directement.
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import 'theme.dart';

/// Touches qui valident (OK de la télécommande, Entrée, bouton A d'une manette).
bool isOkKey(LogicalKeyboardKey k) =>
    k == LogicalKeyboardKey.select ||
    k == LogicalKeyboardKey.enter ||
    k == LogicalKeyboardKey.numpadEnter ||
    k == LogicalKeyboardKey.gameButtonA;

class TvTextField extends StatefulWidget {
  final TextEditingController controller;
  final String label;
  final String? hint;
  final bool obscure;
  final TextInputType? keyboardType;
  final bool autofocus;
  final ValueChanged<String>? onSubmitted;
  final ValueChanged<String>? onChanged;
  final Widget? prefixIcon;
  final TextInputAction action;

  const TvTextField({
    super.key,
    required this.controller,
    this.label = '',
    this.hint,
    this.obscure = false,
    this.keyboardType,
    this.autofocus = false,
    this.onSubmitted,
    this.onChanged,
    this.prefixIcon,
    this.action = TextInputAction.done,
  });

  @override
  State<TvTextField> createState() => _TvTextFieldState();
}

class _TvTextFieldState extends State<TvTextField> {
  final _shell = FocusNode(debugLabel: 'champ');
  final _input = FocusNode(debugLabel: 'saisie');
  bool _inline = false; // saisie directe au doigt

  @override
  void initState() {
    super.initState();
    widget.controller.addListener(_changed);
    _shell.addListener(_changed);
    _input.addListener(() {
      if (!_input.hasFocus && _inline) _endInline(keepFocus: false);
    });
  }

  @override
  void didUpdateWidget(TvTextField old) {
    super.didUpdateWidget(old);
    if (old.controller != widget.controller) {
      old.controller.removeListener(_changed);
      widget.controller.addListener(_changed);
    }
  }

  @override
  void dispose() {
    widget.controller.removeListener(_changed);
    _shell.dispose();
    _input.dispose();
    super.dispose();
  }

  void _changed() {
    if (mounted) setState(() {});
  }

  static void hideKeyboard() => SystemChannels.textInput.invokeMethod<void>('TextInput.hide');

  /// Saisie à la télécommande : panneau en haut de l'écran.
  Future<void> _openEditor() async {
    final v = await showGeneralDialog<String>(
      context: context,
      barrierDismissible: false,
      barrierColor: Colors.black.withValues(alpha: .72),
      transitionDuration: const Duration(milliseconds: 120),
      pageBuilder: (c, _, __) => _Editor(
        label: widget.label.isNotEmpty ? widget.label : (widget.hint ?? ''),
        hint: widget.hint,
        initial: widget.controller.text,
        obscure: widget.obscure,
        keyboardType: widget.keyboardType,
        action: widget.action,
        onChanged: widget.onChanged,
      ),
    );
    hideKeyboard();
    if (!mounted) return;
    if (v != null) {
      widget.controller.text = v;
      widget.controller.selection = TextSelection.collapsed(offset: v.length);
      widget.onChanged?.call(v);
      widget.onSubmitted?.call(v);
    }
    _shell.requestFocus(); // le focus reste sur ce champ, sans rouvrir le clavier
  }

  void _startInline() {
    setState(() => _inline = true);
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted) return;
      _input.requestFocus();
      Scrollable.ensureVisible(context, alignment: .15, duration: const Duration(milliseconds: 200));
    });
  }

  void _endInline({bool keepFocus = true}) {
    if (!_inline) return;
    hideKeyboard();
    setState(() => _inline = false);
    if (keepFocus) {
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (mounted) _shell.requestFocus();
      });
    }
  }

  KeyEventResult _onShellKey(FocusNode n, KeyEvent e) {
    if (e is KeyDownEvent && isOkKey(e.logicalKey)) {
      _openEditor();
      return KeyEventResult.handled;
    }
    return KeyEventResult.ignored;
  }

  KeyEventResult _onInputKey(FocusNode n, KeyEvent e) {
    if (e is! KeyDownEvent) return KeyEventResult.ignored;
    final k = e.logicalKey;
    if (k == LogicalKeyboardKey.escape || k == LogicalKeyboardKey.goBack) {
      _endInline();
      return KeyEventResult.handled;
    }
    if (k == LogicalKeyboardKey.arrowUp || k == LogicalKeyboardKey.arrowDown) {
      // les flèches haut / bas quittent la saisie et passent au champ suivant : jamais de blocage
      _endInline();
      WidgetsBinding.instance.addPostFrameCallback((_) {
        _shell.focusInDirection(k == LogicalKeyboardKey.arrowUp ? TraversalDirection.up : TraversalDirection.down);
      });
      return KeyEventResult.handled;
    }
    return KeyEventResult.ignored;
  }

  InputDecoration _deco(bool focused) => InputDecoration(
        labelText: widget.label.isEmpty ? null : widget.label,
        hintText: widget.hint,
        prefixIcon: widget.prefixIcon,
        enabledBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(10),
          borderSide: focused ? BorderSide(color: kFocus, width: 3) : BorderSide(color: kBorder),
        ),
        fillColor: focused ? kHi : null,
      );

  @override
  Widget build(BuildContext context) {
    if (_inline) {
      return Focus(
        onKeyEvent: _onInputKey,
        canRequestFocus: false,
        skipTraversal: true,
        child: TextField(
          controller: widget.controller,
          focusNode: _input,
          obscureText: widget.obscure,
          keyboardType: widget.keyboardType,
          textInputAction: widget.action,
          decoration: _deco(false),
          onChanged: widget.onChanged,
          onSubmitted: (v) {
            _endInline();
            widget.onSubmitted?.call(v);
          },
          onTapOutside: (_) => _input.unfocus(),
        ),
      );
    }
    final focused = _shell.hasFocus;
    final text = widget.controller.text;
    return Focus(
      focusNode: _shell,
      autofocus: widget.autofocus,
      onKeyEvent: _onShellKey,
      child: GestureDetector(
        behavior: HitTestBehavior.opaque,
        onTap: _startInline,
        child: InputDecorator(
          isFocused: false,
          isEmpty: text.isEmpty,
          decoration: _deco(focused),
          child: Row(children: [
            Expanded(
              child: Text(
                widget.obscure ? '•' * text.length : text,
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
                style: TextStyle(fontSize: 16, color: kInk),
              ),
            ),
            if (focused)
              Padding(
                padding: EdgeInsets.only(left: 8),
                child: Text('OK pour écrire', style: TextStyle(color: kMuted, fontSize: 12)),
              ),
          ]),
        ),
      ),
    );
  }
}

/// Panneau de saisie (télécommande) : en haut de l'écran, donc jamais caché par le clavier.
class _Editor extends StatefulWidget {
  final String label, initial;
  final String? hint;
  final bool obscure;
  final TextInputType? keyboardType;
  final TextInputAction action;
  final ValueChanged<String>? onChanged;
  const _Editor({
    required this.label,
    required this.initial,
    this.hint,
    required this.obscure,
    this.keyboardType,
    required this.action,
    this.onChanged,
  });
  @override
  State<_Editor> createState() => _EditorState();
}

class _EditorState extends State<_Editor> {
  late final _c = TextEditingController(text: widget.initial)
    ..selection = TextSelection.collapsed(offset: widget.initial.length);
  final _f = FocusNode();
  bool _show = false;

  @override
  void initState() {
    super.initState();
    _show = !widget.obscure;
    WidgetsBinding.instance.addPostFrameCallback((_) {
      _f.requestFocus();
      // OK a été pressé volontairement : on affiche le clavier (certaines TV ne l'ouvrent pas d'elles-mêmes)
      WidgetsBinding.instance.addPostFrameCallback((_) => SystemChannels.textInput.invokeMethod<void>('TextInput.show'));
    });
  }

  @override
  void dispose() {
    _c.dispose();
    _f.dispose();
    super.dispose();
  }

  void _ok() => Navigator.of(context).pop(_c.text);

  @override
  Widget build(BuildContext context) {
    return Material(
      type: MaterialType.transparency,
      child: SafeArea(
        child: Align(
          alignment: Alignment.topCenter,
          child: Container(
            constraints: const BoxConstraints(maxWidth: 900),
            margin: const EdgeInsets.fromLTRB(24, 18, 24, 0),
            padding: const EdgeInsets.fromLTRB(18, 14, 18, 14),
            decoration: BoxDecoration(
              color: kPanel,
              borderRadius: BorderRadius.circular(16),
              border: Border.all(color: kAccent, width: 2),
            ),
            child: Column(mainAxisSize: MainAxisSize.min, crossAxisAlignment: CrossAxisAlignment.start, children: [
              Text(widget.label, style: TextStyle(fontSize: 16, fontWeight: FontWeight.w700, color: kInk)),
              const SizedBox(height: 10),
              Row(children: [
                Expanded(
                  child: TextField(
                    controller: _c,
                    focusNode: _f,
                    obscureText: widget.obscure && !_show,
                    keyboardType: widget.keyboardType,
                    textInputAction: TextInputAction.done,
                    autocorrect: false,
                    style: TextStyle(fontSize: 20, color: kInk),
                    decoration: InputDecoration(hintText: widget.hint),
                    onChanged: widget.onChanged,
                    onSubmitted: (_) => _ok(),
                  ),
                ),
                if (widget.obscure)
                  IconButton(
                    tooltip: _show ? 'Masquer' : 'Afficher',
                    onPressed: () => setState(() => _show = !_show),
                    icon: Icon(_show ? Icons.visibility_off : Icons.visibility),
                  ),
                const SizedBox(width: 8),
                TextButton(onPressed: () => Navigator.of(context).pop(), child: const Text('Annuler')),
                const SizedBox(width: 4),
                FilledButton(onPressed: _ok, child: const Text('Valider')),
              ]),
              const SizedBox(height: 8),
              Text('« OK » ou « Terminé » sur le clavier pour valider · « Retour » pour annuler',
                  style: TextStyle(color: kMuted, fontSize: 12.5)),
            ]),
          ),
        ),
      ),
    );
  }
}
