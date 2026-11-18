import 'package:flutter/material.dart';

/// 长页面统一的回到顶部按钮（设计原则：较长的页面统一提供）。
/// 样式与榜单页既有实现一致：圆形 surface 底 + 主色上箭头。
class BackToTop extends StatelessWidget {
  final VoidCallback onTap;

  const BackToTop({super.key, required this.onTap});

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return Material(
      color: scheme.surface,
      borderRadius: BorderRadius.circular(20),
      elevation: 3,
      child: InkWell(
        onTap: onTap,
        customBorder: const CircleBorder(),
        child: SizedBox(
          width: 40,
          height: 40,
          child: Icon(Icons.arrow_upward, size: 20, color: scheme.primary),
        ),
      ),
    );
  }
}
