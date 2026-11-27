import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';

import '../core/format.dart';
import '../data/api/strata_api.dart';

/// 赛事档案行卡（档案列表页与首页对话区/IP 区共用，docs/16 不复制控件）。
///
/// 2026-11-26 改版（用户认可）：主数换「官方清单」条数、在库退为次数——
/// 旧版只显在库数（十征 718），读者会当成「这届只有 718 本」，得靠顶部一行
/// 口径说明救；两个数并排后差距自己会说话。X征 tab 另开左轨年份列
/// （`yearRail`）：14 届是同一系列的年表，一屏看完 2013→2026 的规模变化。
class ContestRowCard extends StatelessWidget {
  final ContestGroup group;

  /// 左轨年份列只在 X征 tab 开（同系列年表有意义；跨系列混排时年份会误导）。
  final bool yearRail;

  const ContestRowCard({
    super.key,
    required this.group,
    this.yearRail = false,
  });

  // 列表页表头与行共用同一套列宽，数字才落得齐。
  static const double colYear = 44;
  static const double colLib = 42;
  static const double colOfficial = 64;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final g = group;
    final status = statusOf(g, DateTime.now());
    return InkWell(
      onTap: () => context.push('/contests/${Uri.encodeComponent(g.name)}'),
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 9),
        child: Row(
          children: [
            if (yearRail)
              SizedBox(
                width: colYear,
                child: Text(
                  g.year == null ? '早期' : '${g.year}',
                  style: TextStyle(
                    fontSize: 11.5,
                    fontFamily: g.year == null ? null : 'serif',
                    color: g.year == null
                        ? scheme.onSurfaceVariant
                        : scheme.onSurfaceVariant,
                  ),
                ),
              ),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(
                    children: [
                      Flexible(
                        child: Text(
                          g.name,
                          overflow: TextOverflow.ellipsis,
                          style: const TextStyle(
                            fontSize: 14.5,
                            fontWeight: FontWeight.w600,
                          ),
                        ),
                      ),
                      if (status != null) ...[
                        const SizedBox(width: 6),
                        _StatusBadge(label: status),
                      ],
                    ],
                  ),
                  const SizedBox(height: 2),
                  Text(
                    _subtitle(g),
                    style: TextStyle(
                      fontSize: 11,
                      color: scheme.onSurfaceVariant,
                    ),
                  ),
                ],
              ),
            ),
            SizedBox(
              width: colLib,
              child: Text(
                g.count == 0 ? '—' : fmtCount(g.count),
                textAlign: TextAlign.end,
                // 对比度修正（2026-11-27 用户四次反馈）：原 outline 色
                //（#E6DFCE）在米色 bg 上几乎隐形，改全深字加粗。
                style: TextStyle(
                  fontSize: 11.5,
                  fontWeight: FontWeight.w600,
                  color: scheme.onSurface,
                ),
              ),
            ),
            const SizedBox(width: 10),
            SizedBox(
              width: colOfficial,
              child: Text(
                // 获奖事件（一/二/三征）没有参赛清单：参赛总数未知（台账
                // roster_total 为空），直接写「未知」——不把获奖名额冒充
                // 总数（用户裁定 2026-11-27）。
                g.listKind != 'award'
                    ? fmtCount(g.rosterTotal)
                    : '未知',
                textAlign: TextAlign.end,
                style: TextStyle(
                  fontSize: g.listKind != 'award' ? 14 : 11,
                  fontFamily: g.listKind != 'award' ? 'serif' : null,
                  fontWeight:
                      g.listKind != 'award' ? FontWeight.w600 : FontWeight.w500,
                  color: g.listKind != 'award'
                      ? scheme.secondary
                      : scheme.onSurfaceVariant,
                ),
              ),
            ),
            Icon(Icons.chevron_right, size: 18, color: scheme.outline),
          ],
        ),
      ),
    );
  }

  /// 行副题：官方赛程优先（开赛 → 截止，缺哪段省哪段）；只有公布日就写
  /// 结果；台账 `note` 覆盖一切。全都没有 = 「赛程日期官方未给」——不写
  /// 在库年份区间，那跟赛期无关，写上去只会被读成赛期。
  String _subtitle(ContestGroup g) {
    // 年份已成左轨时不再在副题里重复。
    final head = (!yearRail && g.year != null) ? '${g.year} 年 · ' : '';
    if (g.note != null) return g.note!;
    if (g.start != null) {
      return '$head开赛 ${fmtMonth(g.start!)}'
          '${g.end == null ? '' : ' · 截止 ${fmtMonth(g.end!)}'}';
    }
    if (g.result != null) return '$head结果 ${fmtMonth(g.result!)}';
    return '$head赛程日期官方未给';
  }

  /// 赛程状态徽标：只有「当下还在发生」的两态值得说（投稿中 / 待公布）。
  /// 已结束是默认，挂个「已结束」纯噪音。
  static String? statusOf(ContestGroup g, DateTime now) {
    final today = DateTime(now.year, now.month, now.day);
    if (g.start != null && g.end != null) {
      final started = !DateTime.parse(g.start!).isAfter(today);
      if (started && !DateTime.parse(g.end!).isBefore(today)) return '投稿中';
    }
    if (g.result != null && DateTime.parse(g.result!).isAfter(today)) {
      return '待公布';
    }
    return null;
  }
}

class _StatusBadge extends StatelessWidget {
  final String label;

  const _StatusBadge({required this.label});

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 5, vertical: 1),
      decoration: BoxDecoration(
        color: scheme.secondaryContainer,
        borderRadius: BorderRadius.circular(3),
      ),
      child: Text(
        label,
        style: TextStyle(
          fontSize: 10,
          height: 1.3,
          color: scheme.onSecondaryContainer,
        ),
      ),
    );
  }
}
