import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../core/providers.dart';
import '../data/api/strata_api.dart';
import '../widgets/book_row_card.dart';

/// 获奖作品列表页（用户裁定 2026-11-26）：单届赛事档案页不再内联
/// 获奖作品——只保留一个入口行；全量名单（官方已核实、按奖项等级排序）
/// 收进本页，行式用通用榜单行（BookRowCard，与经典榜单同款）。
///
/// 奖项名走通用行的首个徽标位（contest 字段的 primary 徽标）；库外
/// 获奖行作者/代系为空，通用行空值段自动省略（2026-11-26 健壮化）。
/// 点行进 /book/{nid}：库内书直接出详情，库外书触发自动收录
/// （收录即库内，用户裁定 2026-11-25）。
class ContestAwardsPage extends ConsumerWidget {
  final String name;

  const ContestAwardsPage({super.key, required this.name});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final scheme = Theme.of(context).colorScheme;
    final data = ref.watch(contestArchiveBooksProvider(name));
    return Scaffold(
      appBar: AppBar(title: Text('$name 获奖作品')),
      body: data.when(
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (e, _) => Center(
          child: Padding(
            padding: const EdgeInsets.all(24),
            child: Text(
              '获奖作品加载失败：$e',
              style: TextStyle(fontSize: 13, color: scheme.onSurfaceVariant),
            ),
          ),
        ),
        data: (res) {
          if (res.awards.isEmpty) {
            return Center(
              child: Text(
                '这一届暂无官方已核实的获奖作品。',
                style:
                    TextStyle(fontSize: 12, color: scheme.onSurfaceVariant),
              ),
            );
          }
          return ListView.builder(
            padding: const EdgeInsets.all(16),
            itemCount: res.awards.length,
            itemBuilder: (context, i) {
              final a = res.awards[i];
              // RankItem 仅有 fromJson 构造：经 map 组装，缺省字段留空
              // （form/tags/cqs 等本页用不到）。
              return BookRowCard(
                item: RankItem.fromJson({
                  'rank': i + 1,
                  'nid': a.nid,
                  'title': a.title,
                  'author': a.author,
                  'est_year': a.estYear ?? 0,
                  'favs': a.favs ?? 0,
                  // 奖项名（可多奖）放通用行首个徽标位。
                  'contest': a.awards.join(' · '),
                  'cover_url': a.coverUrl,
                }),
              );
            },
          );
        },
      ),
    );
  }
}
