import 'package:flutter/material.dart';

/// 文房纸墨设计 token（temp/ui-design/mockups.html 同源）。
/// 浅色=纸面，深色=夜读；衬线仅用于标题类文字。
abstract final class StrataTokens {
  // 浅色（纸面）
  static const lightBg = Color(0xFFF6F2E9);
  static const lightSurface = Color(0xFFFFFDF8);
  static const lightInk = Color(0xFF211E17);
  // 对比度二次修正（2026-11-27 用户反馈）：ink2 #6E6656 在米色纸面仅
  // ~4.7:1，小字号下用户仍看不清——再加深至 #514A39（~7:1）。
  static const lightInk2 = Color(0xFF514A39);
  // 对比度修正（2026-11-26）：ink3 原 #A29A88 在纸面仅 2.5:1（不达
  // WCAG AA 4.5:1，底部导航未选中/弱提示几乎看不清）；2026-11-27 随
  // ink2 一并再加深至 #5A5344（~6.5:1），保留「比 ink2 略浅」的层级。
  static const lightInk3 = Color(0xFF5A5344);
  static const lightHairline = Color(0xFFE6DFCE);
  // 朱砂主色 #BF3B2B → #B03B2E（对比度修正 2026-11-26）：纸面 4.85→5.35、
  // 卡面 5.33→5.88、软朱砂底 4.39→4.84，全部过 AA；顺带与 App 图标底
  // #B03B2E（flutter_launcher_icons）对齐，品牌更统一。
  static const lightCinnabar = Color(0xFFB03B2E);
  static const lightCinnabarSoft = Color(0xFFF7E3DE);
  // 描金 #A8834F → #84662F（2026-11-26）：原在纸面 3.1–3.4:1，10px 级
  // 分位/统计徽标文字不达标；加深后 4.8–5.3:1。
  static const lightGold = Color(0xFF84662F);
  // 竹青 #4F7A5B → #4A7254（2026-11-26）：纸面 4.40→4.91，临界值补足。
  static const lightGreen = Color(0xFF4A7254);
  static const lightBlue = Color(0xFF3F6B8C);

  // 深色（夜读）
  static const darkBg = Color(0xFF181511);
  static const darkSurface = Color(0xFF221E18);
  static const darkInk = Color(0xFFEDE6D6);
  // 对比度二次修正（2026-11-27 用户反馈）：深色 ink2 #AFA48E 提亮至
  // #C6BCA6（深棕底上 ~7:1）。
  static const darkInk2 = Color(0xFFC6BCA6);
  // 对比度修正（2026-11-26）：深色 ink3 原 #7C7462 在卡面 3.58:1（临界
  // 以下）；2026-11-27 随 ink2 一并提亮至 #ADA287，保留层级。
  static const darkInk3 = Color(0xFFADA287);
  static const darkHairline = Color(0xFF332E25);
  static const darkCinnabar = Color(0xFFE06A55);
  // 深色软朱砂底 #3A2621 → #301D19（2026-11-26）：朱砂字在其上 4.30→4.84。
  static const darkCinnabarSoft = Color(0xFF301D19);
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
      // Container 三组（2026-11-27 用户裁定）：不显式定义时 M3 从金棕
      // secondary 派生出棕底 + 默认黑字，对比度过低（比赛行「待公布」
      // 徽标/作者榜头像兜底/roster 徽标）。统一浅底深字高对比。
      primaryContainer:
          isLight ? StrataTokens.lightCinnabarSoft : StrataTokens.darkCinnabarSoft,
      onPrimaryContainer:
          isLight ? const Color(0xFF7A2419) : StrataTokens.darkCinnabar,
      secondaryContainer:
          isLight ? const Color(0xFFF0E7D2) : const Color(0xFF2E2820),
      onSecondaryContainer:
          isLight ? StrataTokens.lightGold : StrataTokens.darkGold,
      tertiary: isLight ? StrataTokens.lightGreen : StrataTokens.darkGreen,
      onTertiary: const Color(0xFFFFF8F0),
      tertiaryContainer:
          isLight ? const Color(0xFFE2EBE4) : const Color(0xFF1F2A24),
      onTertiaryContainer:
          isLight ? StrataTokens.lightGreen : StrataTokens.darkGreen,
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
