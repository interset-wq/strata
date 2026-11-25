import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';

import '../app/theme.dart';
import '../data/api/strata_api.dart';
import 'default_cover.dart';
import 'metric_badge.dart';

/// 书籍行卡：封面 + 标题/作者 + tags chips + 指标行（字数·点击·收藏·赞）。
/// 随机池 100 本二级页与 curated 全量列表页（授权作品/萌神获奖）共用。
class BookRowTile extends StatelessWidget {
  final RankItem item;

  /// IP 徽标（tag 行首位，比普通 tag 更重）：列表混排多个联动 IP 时
  /// 每本需要 IP 标识（IP 二级页的“其他”旧深链）。
  final String? ipLabel;

  const BookRowTile({super.key, required this.item, this.ipLabel});

  static String wan(int? n) {
    if (n == null) return '';
    if (n >= 10000) return '${(n / 10000).toStringAsFixed(1)}万';
    return '$n';
  }

  /// 状态/付费小徽标：浅底 + 彩色字（用户 2026-11-25 榜单行版式）。
  Widget _pill(BuildContext context, String text, Color fg, Color bg) {
    return Container(
      margin: const EdgeInsets.only(left: 6),
      padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
      decoration: BoxDecoration(
        color: bg,
        borderRadius: BorderRadius.circular(4),
      ),
      child: Text(text, style: TextStyle(fontSize: 10, color: fg)),
    );
  }

  /// 标签 pill：题材深底（deep: true）、book_tags 浅底——竖线分隔看不清，
  /// 改背景深浅区分（用户 2026-11-25）。
  Widget _tagPill(BuildContext context, String t, {bool deep = false}) {
    final scheme = Theme.of(context).colorScheme;
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
      decoration: BoxDecoration(
        color: scheme.primary.withValues(alpha: deep ? .18 : .08),
        borderRadius: BorderRadius.circular(4),
      ),
      child: Text(
        t,
        style: TextStyle(
          fontSize: 10,
          fontWeight: deep ? FontWeight.w600 : FontWeight.w400,
          color: scheme.primary,
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final coverUrl = item.coverUrl;
    final hasCover = coverUrl != null && coverUrl.isNotEmpty;

    // 标签行：题材 + book_tags（去重；题材与 book_tags 之间竖线分隔，
    // 用户 2026-11-25 最终版排版）。
    final genre = (item.genre != null && item.genre!.isNotEmpty)
        ? item.genre!
        : null;
    final bookTags = <String>[];
    for (final t in item.tags) {
      if (t != genre && !bookTags.contains(t)) bookTags.add(t);
    }

    // 状态徽标（标题行右侧；未判定不显示）
    final status =
        (item.status != null && item.status!.isNotEmpty) ? item.status! : null;
    // 付费徽标（作者行右侧；免费不显示——用户 2026-11-25）
    final price = item.priceType;

    // 指标行：字数 · 点击 · 收藏 · 赞（非空才显示；顺序对齐官方 app 排版）
    final metrics = <(IconData, String)>[
      if (item.words != null) (MetricIcons.words, '${wan(item.words)}字'),
      if (item.clicks != null) (MetricIcons.clicks, wan(item.clicks)),
      if (item.favs > 0) (MetricIcons.favs, wan(item.favs)),
      if (item.praises != null && item.praises! > 0)
        (MetricIcons.praises, wan(item.praises)),
    ];
    final ip = ipLabel;

    return InkWell(
      onTap: () => context.push('/book/${item.nid}'),
      borderRadius: BorderRadius.circular(12),
      child: Container(
        margin: const EdgeInsets.symmetric(vertical: 5),
        padding: const EdgeInsets.all(10),
        decoration: BoxDecoration(
          color: scheme.surface,
          borderRadius: BorderRadius.circular(12),
          border: Border.all(color: scheme.outline.withValues(alpha: .25)),
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
                    ? coverImage(coverUrl, item.nid)
                    : defaultCover(item.nid),
              ),
            ),
            const SizedBox(width: 12),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  // 标题行：单行标题 + 状态徽标（用户 2026-11-25）
                  Row(
                    children: [
                      Expanded(
                        child: Text(
                          item.title,
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                          style: const TextStyle(
                            fontSize: 13,
                            fontWeight: FontWeight.w600,
                          ),
                        ),
                      ),
                      // 付费徽标占标题行（免费不显示）；状态徽标在作者行
                      if (price != null && price.isNotEmpty && price != '免费')
                        _pill(context, price, Colors.amber.shade900,
                            Colors.amber.withValues(alpha: .15)),
                    ],
                  ),
                  const SizedBox(height: 3),
                  // 作者行：作者（左）…… 状态徽标 · 代系（右对齐；
                  // 缺失不显示）
                  Row(
                    children: [
                      Expanded(
                        child: Text(
                          item.author,
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                          style:
                              TextStyle(fontSize: 11, color: scheme.secondary),
                        ),
                      ),
                      if (status != null)
                        _pill(
                          context,
                          status,
                          status == '连载中'
                              ? scheme.primary
                              : scheme.onSurfaceVariant,
                          status == '连载中'
                              ? scheme.primary.withValues(alpha: .12)
                              : scheme.outline.withValues(alpha: .15),
                        ),
                      if (item.estYear > 0)
                        Text('${item.estYear}',
                            style: TextStyle(
                                fontSize: 10,
                                color: scheme.onSurfaceVariant)),
                    ],
                  ),
                  if (genre != null || bookTags.isNotEmpty) ...[
                    const SizedBox(height: 6),
                    Wrap(
                      spacing: 4,
                      runSpacing: 4,
                      children: [
                        if (ip != null && ip.isNotEmpty)
                          Container(
                            padding: const EdgeInsets.symmetric(
                              horizontal: 6,
                              vertical: 2,
                            ),
                            decoration: BoxDecoration(
                              color: scheme.primary.withValues(alpha: .16),
                              borderRadius: BorderRadius.circular(4),
                              border: Border.all(
                                color: scheme.primary.withValues(alpha: .5),
                              ),
                            ),
                            child: Text(
                              ip,
                              style: TextStyle(
                                fontSize: 10,
                                fontWeight: FontWeight.w700,
                                fontFamily: StrataTokens.serif,
                                color: scheme.primary,
                              ),
                            ),
                          ),
                        if (genre != null)
                          _tagPill(context, genre, deep: true),
                        for (final t in bookTags.take(genre == null ? 3 : 2))
                          _tagPill(context, t),
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
                              icon: metrics[i].$1,
                              text: metrics[i].$2,
                            ),
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
