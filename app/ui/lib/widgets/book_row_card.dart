import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';

import '../data/api/strata_api.dart';
import 'default_cover.dart';
import 'metric_badge.dart';

/// 统一列表行卡（榜单页与二级浏览页共用）：衬线排名序号 + 小封面
///（朱砂偏移阴影）+ 单行标题 + 「作者 · 题材 · N 代」+ 指标徽标。
class BookRowCard extends StatelessWidget {
  final RankItem item;

  const BookRowCard({super.key, required this.item});

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final cover = coverImage(item.coverUrl, item.nid);
    final top = item.rank <= 3;
    return Card(
      margin: const EdgeInsets.only(bottom: 10),
      child: InkWell(
        onTap: () => context.push('/book/${item.nid}'),
        borderRadius: BorderRadius.circular(16),
        child: Padding(
          padding: const EdgeInsets.all(12),
          child: Row(
            crossAxisAlignment: CrossAxisAlignment.center,
            children: [
              SizedBox(
                width: 30,
                child: Text(
                  '${item.rank}',
                  textAlign: TextAlign.center,
                  style: TextStyle(
                    fontFamily: 'serif',
                    fontSize: top ? 20 : 18,
                    fontWeight: FontWeight.w700,
                    color: top ? scheme.primary : scheme.onSurfaceVariant,
                  ),
                ),
              ),
              const SizedBox(width: 12),
              Container(
                width: 40,
                height: 56,
                decoration: BoxDecoration(
                  borderRadius: BorderRadius.circular(6),
                  boxShadow: [
                    BoxShadow(
                        color: scheme.primary.withValues(alpha: .25),
                        offset: const Offset(-4, 4)),
                  ],
                ),
                child: ClipRRect(
                  borderRadius: BorderRadius.circular(6),
                  child: cover,
                ),
              ),
              const SizedBox(width: 12),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(item.title,
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        style: Theme.of(context)
                            .textTheme
                            .titleLarge
                            ?.copyWith(fontSize: 13.5)),
                    const SizedBox(height: 3),
                    Text(
                      '${item.author} · ${item.genre ?? '未分类'} · ${item.estYear}',
                      style: TextStyle(
                          fontSize: 11, color: scheme.onSurfaceVariant),
                    ),
                    const SizedBox(height: 5),
                    Wrap(
                      spacing: 4,
                      runSpacing: 4,
                      children: [
                        if (item.contest != null && item.contest!.isNotEmpty)
                          bookBadge(context, item.contest!,
                              fg: scheme.primary,
                              bg: scheme.primary.withValues(alpha: .12)),
                        bookBadge(context, '收藏 ${wanText(item.favs)}',
                            fg: scheme.onSurfaceVariant,
                            icon: MetricIcons.favs),
                        // 空值不显示（与 BookRowTile 同口径）：库外/未收录
                        // 书没有种子点击量，显示 0 会误导（用户 2026-11-22
                        // 反馈「全是 0」即由此来）。
                        if (item.clicks != null)
                          bookBadge(context, '点击 ${wanText(item.clicks!)}',
                              fg: scheme.secondary, icon: MetricIcons.clicks),
                      ],
                    ),
                  ],
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

/// 统一指标徽标（胶囊描边 + 可选图标）。
Widget bookBadge(
  BuildContext context,
  String text, {
  Color? fg,
  Color? bg,
  IconData? icon,
}) {
  final scheme = Theme.of(context).colorScheme;
  return Container(
    padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 1),
    decoration: BoxDecoration(
      color: bg ?? Colors.transparent,
      border: Border.all(color: scheme.outline.withValues(alpha: .5)),
      borderRadius: BorderRadius.circular(999),
    ),
    child: Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        if (icon != null) ...[
          Icon(icon, size: 11, color: fg ?? scheme.onSurfaceVariant),
          const SizedBox(width: 2),
        ],
        Text(text, style: TextStyle(fontSize: 10, color: fg ?? scheme.onSurfaceVariant)),
      ],
    ),
  );
}

String wanText(int n) {
  if (n >= 10000) return '${(n / 10000).toStringAsFixed(1)}万';
  return '$n';
}
