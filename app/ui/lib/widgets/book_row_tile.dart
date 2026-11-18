import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';

import '../data/api/strata_api.dart';
import 'default_cover.dart';
import 'metric_badge.dart';

/// 书籍行卡：封面 + 标题/作者 + tags chips + 指标行（字数·点击·收藏·赞）。
/// 随机池 100 本二级页与 curated 全量列表页（授权作品/萌神获奖）共用。
class BookRowTile extends StatelessWidget {
  final RankItem item;

  const BookRowTile({super.key, required this.item});

  static String wan(int? n) {
    if (n == null) return '';
    if (n >= 10000) return '${(n / 10000).toStringAsFixed(1)}万';
    return '$n';
  }

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final coverUrl = item.coverUrl;
    final hasCover = coverUrl != null && coverUrl.isNotEmpty;

    // 标签：题材 + book_tags（最多 3 个）
    final tags = <String>[
      if (item.genre != null && item.genre!.isNotEmpty) item.genre!,
      ...item.tags,
    ];
    if (tags.toSet().length != tags.length) {
      // 去重且保持顺序
      final seen = <String>{};
      tags.removeWhere((t) => !seen.add(t));
    }

    // 指标行：字数 · 点击 · 收藏 · 赞（非空才显示；顺序对齐官方 app 排版）
    final metrics = <(IconData, String)>[
      if (item.words != null) (MetricIcons.words, '${wan(item.words)}字'),
      if (item.clicks != null) (MetricIcons.clicks, wan(item.clicks)),
      if (item.favs > 0) (MetricIcons.favs, wan(item.favs)),
      if (item.praises != null && item.praises! > 0)
        (MetricIcons.praises, wan(item.praises)),
    ];

    return InkWell(
      onTap: () => context.push('/book/${item.nid}'),
      borderRadius: BorderRadius.circular(12),
      child: Container(
        margin: const EdgeInsets.symmetric(vertical: 5),
        padding: const EdgeInsets.all(10),
        decoration: BoxDecoration(
          color: scheme.surface,
          borderRadius: BorderRadius.circular(12),
          border: Border.all(
              color: scheme.outline.withValues(alpha: .25)),
        ),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            SizedBox(
              width: 48,
              height: 64,
              child: ClipRRect(
                borderRadius: BorderRadius.circular(6),
                child: hasCover
                    ? Image.network(
                        coverImageUrl(coverUrl)!,
                        fit: BoxFit.cover,
                        loadingBuilder: coverLoadingBuilder,
                        errorBuilder: (_, _, _) =>
                            defaultCover(item.nid),
                      )
                    : defaultCover(item.nid),
              ),
            ),
            const SizedBox(width: 12),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(item.title,
                      maxLines: 2,
                      overflow: TextOverflow.ellipsis,
                      style: const TextStyle(
                          fontSize: 13, fontWeight: FontWeight.w600)),
                  const SizedBox(height: 3),
                  Text(item.author,
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style:
                          TextStyle(fontSize: 11, color: scheme.secondary)),
                  if (tags.isNotEmpty) ...[
                    const SizedBox(height: 6),
                    Wrap(
                      spacing: 4,
                      runSpacing: 4,
                      children: [
                        for (final t in tags.take(3))
                          Container(
                            padding: const EdgeInsets.symmetric(
                                horizontal: 6, vertical: 2),
                            decoration: BoxDecoration(
                              color: scheme.primary.withValues(alpha: .08),
                              borderRadius: BorderRadius.circular(4),
                            ),
                            child: Text(t,
                                style: TextStyle(
                                    fontSize: 10,
                                    color: scheme.primary)),
                          ),
                      ],
                    ),
                  ],
                  if (metrics.isNotEmpty) ...[
                    const SizedBox(height: 6),
                    // 大书四指标全显时会超宽（实测 2.6px），scaleDown
                    // 仅在溢出时等比缩小，不丢内容。
                    FittedBox(
                      fit: BoxFit.scaleDown,
                      child: Row(
                        mainAxisSize: MainAxisSize.min,
                        children: [
                          for (var i = 0; i < metrics.length; i++) ...[
                            if (i > 0) const SizedBox(width: 10),
                            MetricBadge(
                                icon: metrics[i].$1, text: metrics[i].$2),
                          ],
                        ],
                      ),
                    ),
                  ],
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}
