import 'package:flutter/material.dart';

/// Immersive AI chat dark palette (ChatGPT-style neutrals) and related accents.
/// Light mode resolves via [ColorScheme] in the screen; these tokens apply when
/// chat uses the dedicated dark immersive chrome.
abstract final class ChatImmersivePalette {
  /// Send / cursor accent (quota retry, composer affordances).
  static const Color sendGreen = Color(0xFF10A37F);

  static const Color darkCanvas = Color(0xFF0D0D0D);
  static const Color darkRaised = Color(0xFF171717);
  static const Color darkBubble = Color(0xFF2F2F2F);
  static const Color darkComposer = Color(0xFF1A1A1A);
  static const Color darkBorder = Color(0xFF3D3D3D);
  static const Color darkText = Color(0xFFECECEC);
  static const Color darkMuted = Color(0xFF9B9B9B);
  static const Color darkLink = Color(0xFFCACACA);
  static const Color darkStopFill = Color(0xFF2C2C2C);
  static const Color darkEditRing = Color(0xFF6A6A6A);

  /// Document citation chips (distinct from generic link).
  static const Color sourceDocAccentDark = Color(0xFF5EEAD4);
  static const Color sourceDocAccentLight = Color(0xFF0D9488);

  /// Send control: white disc, black glyph.
  static const Color sendButtonWhite = Color(0xFFFFFFFF);
  static const Color sendArrowBlack = Color(0xFF000000);

  static Color sourceDocAccentForBrightness(Brightness brightness) =>
      brightness == Brightness.dark
          ? sourceDocAccentDark
          : sourceDocAccentLight;
}
