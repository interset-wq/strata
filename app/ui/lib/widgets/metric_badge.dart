import 'package:flutter/material.dart';

/// 指标展示图标（app/docs/15 · Icon 语义表）。
/// 规则：同一语义任何页面用同一个 icon；展示一律线性（outlined），
/// 实心只用于"可点击/已激活"。新增语义先在 15 号文档登记。
class MetricIcons {
  MetricIcons._();

  static const IconData favs = Icons.favorite_border; // 收藏
  static const IconData praises = Icons.thumb_up_outlined; // 点赞/推荐
  static const IconData words = Icons.format_size; // 字数
  static const IconData clicks = Icons.visibility_outlined; // 点击/阅读
}

/// 紧凑指标展示：12px 线性 icon + 10px 文本，icon 与文本同色。
/// 所有"图标+数字"的指标展示点必须走本组件，禁止手写 Icon+Text 拼指标。
class MetricBadge extends StatelessWidget {
  final IconData icon;
  final String text;
  final Color? color;

  const MetricBadge({
    super.key,
    required this.icon,
    required this.text,
    this.color,
  });

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final c = color ?? scheme.onSurfaceVariant;
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        Icon(icon, size: 12, color: c),
        const SizedBox(width: 2),
        Text(text, style: TextStyle(fontSize: 10, color: c)),
      ],
    );
  }
}
