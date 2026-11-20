import 'package:flutter/material.dart';

/// 文房纸墨设计 token（temp/ui-design/mockups.html 同源）。
/// 浅色=纸面，深色=夜读；衬线仅用于标题类文字。
abstract final class StrataTokens {
  // 浅色（纸面）
  static const lightBg = Color(0xFFF6F2E9);
  static const lightSurface = Color(0xFFFFFDF8);
  static const lightInk = Color(0xFF211E17);
  static const lightInk2 = Color(0xFF6E6656);
  static const lightInk3 = Color(0xFFA29A88);
  static const lightHairline = Color(0xFFE6DFCE);
  static const lightCinnabar = Color(0xFFBF3B2B);
  static const lightCinnabarSoft = Color(0xFFF7E3DE);
  static const lightGold = Color(0xFFA8834F);
  static const lightGreen = Color(0xFF4F7A5B);
  static const lightBlue = Color(0xFF3F6B8C);

  // 深色（夜读）
  static const darkBg = Color(0xFF181511);
  static const darkSurface = Color(0xFF221E18);
  static const darkInk = Color(0xFFEDE6D6);
  static const darkInk2 = Color(0xFFAFA48E);
  static const darkInk3 = Color(0xFF7C7462);
  static const darkHairline = Color(0xFF332E25);
  static const darkCinnabar = Color(0xFFE06A55);
  static const darkCinnabarSoft = Color(0xFF3A2621);
  static const darkGold = Color(0xFFC9A36B);
  static const darkGreen = Color(0xFF7BA98A);
  static const darkBlue = Color(0xFF7FA3C4);

  /// 衬线字族（书名/标题/大数字），无衬线走默认。
  static const serif = 'Noto Serif SC';
}

class StrataTheme {
  StrataTheme._();

  static ThemeData light() => _base(Brightness.light);
  static ThemeData dark() => _base(Brightness.dark);

  static ThemeData _base(Brightness brightness) {
    final isLight = brightness == Brightness.light;
    final scheme = ColorScheme.light(
      primary: isLight ? StrataTokens.lightCinnabar : StrataTokens.darkCinnabar,
      onPrimary: const Color(0xFFFFF8F0),
      secondary: isLight ? StrataTokens.lightGold : StrataTokens.darkGold,
      surface: isLight ? StrataTokens.lightSurface : StrataTokens.darkSurface,
      onSurface: isLight ? StrataTokens.lightInk : StrataTokens.darkInk,
      surfaceContainerHighest: isLight ? StrataTokens.lightBg : StrataTokens.darkBg,
      onSurfaceVariant: isLight ? StrataTokens.lightInk2 : StrataTokens.darkInk2,
      outline: isLight ? StrataTokens.lightHairline : StrataTokens.darkHairline,
      error: isLight ? StrataTokens.lightCinnabar : StrataTokens.darkCinnabar,
    );

    final serif = StrataTokens.serif;
    return ThemeData(
      useMaterial3: true,
      colorScheme: scheme,
      scaffoldBackgroundColor:
          isLight ? StrataTokens.lightBg : StrataTokens.darkBg,
      appBarTheme: AppBarTheme(
        backgroundColor:
            isLight ? StrataTokens.lightBg : StrataTokens.darkBg,
        foregroundColor: isLight ? StrataTokens.lightInk : StrataTokens.darkInk,
        elevation: 0,
        centerTitle: false,
        titleTextStyle: TextStyle(
          fontFamily: serif,
          fontSize: 18,
          fontWeight: FontWeight.w700,
          letterSpacing: 2,
          color: isLight ? StrataTokens.lightInk : StrataTokens.darkInk,
        ),
      ),
      cardTheme: CardThemeData(
        color: isLight ? StrataTokens.lightSurface : StrataTokens.darkSurface,
        elevation: 0,
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(16),
          side: BorderSide(
            color: isLight ? StrataTokens.lightHairline : StrataTokens.darkHairline,
          ),
        ),
        margin: EdgeInsets.zero,
      ),
      chipTheme: ChipThemeData(
        backgroundColor:
            isLight ? StrataTokens.lightSurface : StrataTokens.darkSurface,
        selectedColor:
            isLight ? StrataTokens.lightCinnabar : StrataTokens.darkCinnabar,
        side: BorderSide(
          color: isLight ? StrataTokens.lightHairline : StrataTokens.darkHairline,
        ),
        shape: const StadiumBorder(),
        labelStyle: TextStyle(
          fontSize: 12,
          color: isLight ? StrataTokens.lightInk2 : StrataTokens.darkInk2,
        ),
        secondaryLabelStyle: const TextStyle(
          fontSize: 12,
          fontWeight: FontWeight.w600,
          color: Color(0xFFFFF8F0),
        ),
      ),
      dividerTheme: DividerThemeData(
        color: isLight ? StrataTokens.lightHairline : StrataTokens.darkHairline,
        thickness: 1,
      ),
      navigationBarTheme: NavigationBarThemeData(
        backgroundColor:
            isLight ? StrataTokens.lightSurface : StrataTokens.darkSurface,
        indicatorColor:
            (isLight ? StrataTokens.lightCinnabar : StrataTokens.darkCinnabar).withValues(alpha: .12),
        labelTextStyle: WidgetStateProperty.resolveWith((states) => TextStyle(
              fontSize: 11,
              fontWeight: states.contains(WidgetState.selected)
                  ? FontWeight.w600
                  : FontWeight.w400,
              color: states.contains(WidgetState.selected)
                  ? (isLight ? StrataTokens.lightCinnabar : StrataTokens.darkCinnabar)
                  : (isLight ? StrataTokens.lightInk3 : StrataTokens.darkInk3),
            )),
        iconTheme: WidgetStateProperty.resolveWith((states) => IconThemeData(
              size: 22,
              color: states.contains(WidgetState.selected)
                  ? (isLight ? StrataTokens.lightCinnabar : StrataTokens.darkCinnabar)
                  : (isLight ? StrataTokens.lightInk3 : StrataTokens.darkInk3),
            )),
      ),
      textTheme: TextTheme(
        titleLarge: TextStyle(
          fontFamily: serif,
          fontWeight: FontWeight.w700,
          color: isLight ? StrataTokens.lightInk : StrataTokens.darkInk,
        ),
        headlineSmall: TextStyle(
          fontFamily: serif,
          fontWeight: FontWeight.w700,
          color: isLight ? StrataTokens.lightInk : StrataTokens.darkInk,
        ),
      ),
    );
  }
}
