import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';

import '../data/api/strata_api.dart';

/// 赛事档案行卡（档案列表页与首页对话区/IP 区共用，docs/16 不复制控件）：
/// 赛事名 + 副题（官方启动年份优先；无元数据时显在库年份区间——不编造
/// 日期）+ 在库计数；点击进档案页（/contests/:name）。
class ContestRowCard extends StatelessWidget {
  final ContestGroup group;

  const ContestRowCard({super.key, required this.group});

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return InkWell(
      onTap: () => context.push('/contests/${Uri.encodeComponent(group.name)}'),
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 10),
        child: Row(
          children: [
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    group.name,
                    style: const TextStyle(
                      fontSize: 14.5,
                      fontWeight: FontWeight.w600,
                    ),
                  ),
                  const SizedBox(height: 2),
                  Text(
                    _subtitle(group),
                    style: TextStyle(
                      fontSize: 11,
                      color: scheme.onSurfaceVariant,
                    ),
                  ),
                ],
              ),
            ),
            Padding(
              padding: const EdgeInsets.only(right: 2),
              child: Text(
                '${group.count}',
                style: TextStyle(
                  fontSize: 13,
                  fontFamily: 'serif',
                  color: scheme.secondary,
                ),
              ),
            ),
            Icon(Icons.chevron_right, size: 18, color: scheme.outline),
          ],
        ),
      ),
    );
  }

  /// 行副题：官方启动年份优先；无元数据时显在库年份区间（不编造日期）。
  static String _subtitle(ContestGroup g) {
    if (g.year != null) return '${g.year} 启动';
    if (g.yearMin == g.yearMax) return '在库 ${g.yearMin}';
    return '在库 ${g.yearMin}–${g.yearMax}';
  }
}
