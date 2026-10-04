import 'package:flutter/material.dart';

/// Fixed colors for the login-hero splash.
///
/// The splash matches the backoffice sign-in canvas and does not follow the
/// app light/dark theme, so these live with the other theme palettes instead
/// of as raw literals in the screen.
abstract final class SplashHeroPalette {
  static const navy = Color(0xFF011E41);
  static const navyMid = Color(0xFF0A2F66);
  static const navyDeep = Color(0xFF00060F);
  static const blue = Color(0xFF3E7BFA);
  static const red = Color(0xFFC8102E);
  static const redLight = Color(0xFFFF5470);
  static const sky = Color(0xFF93C5FD);
  static const ink = Color(0xFFFFFFFF);
  static const inkBody = Color(0xD1FFFFFF);
  static const inkLabel = Color(0xEBFFFFFF);
  static const shadow = Color(0xFF000000);
}
