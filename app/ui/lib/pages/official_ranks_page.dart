import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../core/providers.dart';
import '../data/api/strata_api.dart';

/// 官方榜单 demo 页：接入 SFACG 官方三个榜单来源（docs/sfacg-live-ranks.md），
/// 让用户直观看到「这些具体是什么榜单」：
///  1. 历史月榜库（MonthlyBoy.ashx，2013-03 起任意月份，月票带票数）
///  2. PC 当期四榜（月票带票数 / 打赏 / 热销 / 粉丝榜读者侧）
///  3. 移动五榜（人气/收藏/新书/日轻/热销，无数值）
/// 抓取走引擎限速器（前台优先），每个板首次展开时懒加载。

final _pcBoardsProvider =
    FutureProvider.autoDispose<List<OfficialPcBoard>>((ref) async {
  final handle = await ref.watch(bootProvider.future);
  return handle.api.officialRanksPc();
});

final _mobileBoardProvider = FutureProvider.autoDispose
    .family<List<OfficialRankEntry>, String>((ref, slug) async {
  final handle = await ref.watch(bootProvider.future);
  return handle.api.officialRanksMobile(slug: slug);
});

final _monthlyBoardProvider = FutureProvider.autoDispose
    .family<List<OfficialRankEntry>, (String, int)>((ref, arg) async {
  final handle = await ref.watch(bootProvider.future);
  return handle.api.officialRanksMonthly(month: arg.$1, rank: arg.$2);
});

const _monthlyBoards = [
  (0, '月票榜',
      '月票票数榜——站内唯一公开的付费强度信号；免费书可入榜；按月清零'),
  (2, '新书榜', '官方月度新书榜（top 10）'),
  (3, '热销榜', '当期点券消耗（订阅额）排序；免费书结构性不可入榜'),
  (4, '对话月票榜', '对话产品线月票票数榜（2017-07 起）'),
];

const _mobileBoards = [
  ('original', '人气榜', '官方移动端人气榜 top 20（无数值，算法未公开）'),
  ('bm', '收藏榜', '官方移动端收藏榜 top 20（无数值）'),
  ('new', '新书榜', '官方移动端新书榜 top 20（无数值）'),
  ('jp', '日轻榜', '日系轻小说池榜单 top 20（无数值）'),
  ('sale', '热销榜', '官方移动端热销榜 top 20（无数值）'),
];

class OfficialRanksPage extends ConsumerStatefulWidget {
  const OfficialRanksPage({super.key});

  @override
  ConsumerState<OfficialRanksPage> createState() => _OfficialRanksPageState();
}

class _OfficialRanksPageState extends ConsumerState<OfficialRanksPage> {
  /// 默认当前月；下拉覆盖最近 13 个月。
  late String _month = _ym(DateTime.now());

  static String _ym(DateTime d) =>
      '${d.year.toString().padLeft(4, '0')}-${d.month.toString().padLeft(2, '0')}';

  List<String> get _monthOptions {
    final now = DateTime.now();
    final out = <String>[];
    for (var i = 0; i < 13; i++) {
      out.add(_ym(DateTime(now.year, now.month - i)));
    }
    return out;
  }

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;

    return Scaffold(
      appBar: AppBar(title: const Text('官方榜单（demo）')),
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          Text('历史月榜库（2013-03 至今）',
              style: Theme.of(context).textTheme.titleLarge),
          const SizedBox(height: 4),
          Text('MonthlyBoy.ashx——官方历史月榜，任意月份可查、按月清零；'
              '月票票数是站内唯一公开的付费强度信号',
              style: Theme.of(context)
                  .textTheme
                  .bodySmall
                  ?.copyWith(color: scheme.onSurfaceVariant)),
          const SizedBox(height: 8),
          Card(
            child: DropdownButtonFormField<String>(
              initialValue: _month,
              decoration: const InputDecoration(
                labelText: '月份',
                contentPadding: EdgeInsets.symmetric(horizontal: 16),
              ),
              items: [
                for (final m in _monthOptions)
                  DropdownMenuItem(value: m, child: Text(m)),
              ],
              onChanged: (m) => setState(() => _month = m!),
            ),
          ),
          const SizedBox(height: 8),
          for (final (rank, label, note) in _monthlyBoards)
            _BoardCard(
              title: label,
              note: note,
              leading: rank == 0 ? Icons.star_outline : null,
              child: ref.watch(_monthlyBoardProvider((_month, rank))).when(
                    loading: () => const Padding(
                        padding: EdgeInsets.all(16),
                        child: Center(child: CircularProgressIndicator())),
                    error: (e, _) => _ErrorRow(message: '$e'),
                    data: (items) => _RankList(
                      items: items,
                      valueLabel: rank == 0
                          ? '月票'
                          : (rank == 3 || rank == 4)
                              ? null
                              : null,
                    ),
                  ),
            ),
          const SizedBox(height: 24),
          Text('PC 当期四榜', style: Theme.of(context).textTheme.titleLarge),
          const SizedBox(height: 4),
          Text('book.sfacg.com/Rank/——当期月榜一页四榜；'
              '月票榜带票数，粉丝榜是读者侧（消费火券）',
              style: Theme.of(context)
                  .textTheme
                  .bodySmall
                  ?.copyWith(color: scheme.onSurfaceVariant)),
          const SizedBox(height: 8),
          ref.watch(_pcBoardsProvider).when(
                loading: () => const Padding(
                    padding: EdgeInsets.all(16),
                    child: Center(child: CircularProgressIndicator())),
                error: (e, _) => _ErrorRow(message: '$e'),
                data: (boards) => Column(
                  children: [
                    for (final b in boards)
                      _BoardCard(
                        title: b.name,
                        note: b.name == '粉丝榜'
                            ? '读者侧当期月榜（消费火券）——不是书榜'
                            : (b.name == '月度月票榜' ? '带月票票数' : '无数值'),
                        child: _RankList(
                          items: b.entries,
                          valueLabel: b.name == '粉丝榜'
                              ? '火券'
                              : (b.name == '月度月票榜' ? '月票' : null),
                        ),
                      ),
                  ],
                ),
              ),
          const SizedBox(height: 24),
          Text('移动五榜', style: Theme.of(context).textTheme.titleLarge),
          const SizedBox(height: 4),
          Text('m.sfacg.com/rank/——官方移动端当期榜，各 top 20，无数值',
              style: Theme.of(context)
                  .textTheme
                  .bodySmall
                  ?.copyWith(color: scheme.onSurfaceVariant)),
          const SizedBox(height: 8),
          for (final (slug, label, note) in _mobileBoards)
            _BoardCard(
              title: label,
              note: note,
              child: ref.watch(_mobileBoardProvider(slug)).when(
                    loading: () => const Padding(
                        padding: EdgeInsets.all(16),
                        child: Center(child: CircularProgressIndicator())),
                    error: (e, _) => _ErrorRow(message: '$e'),
                    data: (items) => _RankList(items: items),
                  ),
            ),
        ],
      ),
    );
  }
}

/// 一个榜单卡：标题 + 语义说明 + 可展开的榜单行。
class _BoardCard extends StatelessWidget {
  final String title;
  final String note;
  final IconData? leading;
  final Widget child;

  const _BoardCard({
    required this.title,
    required this.note,
    required this.child,
    this.leading,
  });

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return Card(
      margin: const EdgeInsets.symmetric(vertical: 4),
      child: ExpansionTile(
        leading: leading != null ? Icon(leading) : null,
        title: Text(title,
            style: const TextStyle(fontWeight: FontWeight.w600)),
        subtitle: Text(note, style: TextStyle(color: scheme.onSurfaceVariant)),
        children: [child],
      ),
    );
  }
}

/// 榜单行列表：序号 + 标题 + 作者/题材 + 数值（月票/火券）。
class _RankList extends StatelessWidget {
  final List<OfficialRankEntry> items;
  final String? valueLabel;

  const _RankList({required this.items, this.valueLabel});

  @override
  Widget build(BuildContext context) {
    if (items.isEmpty) {
      return Padding(
        padding: const EdgeInsets.all(16),
        child: Text('该月该榜无数据（2013-03 之前为空）',
            style: TextStyle(color: Theme.of(context).colorScheme.onSurfaceVariant)),
      );
    }
    return Column(
      children: [
        for (final it in items)
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 6),
            child: Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                SizedBox(
                  width: 24,
                  child: Text(
                    '${it.rank}',
                    style: TextStyle(
                      fontSize: 14,
                      fontWeight: it.rank <= 3
                          ? FontWeight.w700
                          : FontWeight.w400,
                      color: it.rank <= 3
                          ? Theme.of(context).colorScheme.primary
                          : Theme.of(context).colorScheme.onSurfaceVariant,
                    ),
                  ),
                ),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(it.title,
                          style: const TextStyle(
                              fontWeight: FontWeight.w600, fontSize: 14)),
                      if (it.author.isNotEmpty || it.genre != null)
                        Text(
                          [it.author, it.genre]
                              .where((s) => s != null && s.isNotEmpty)
                              .join(' · '),
                          style: TextStyle(
                              fontSize: 12,
                              color: Theme.of(context)
                                  .colorScheme
                                  .onSurfaceVariant),
                        ),
                    ],
                  ),
                ),
                if (it.value > 0 && valueLabel != null)
                  Container(
                    padding: const EdgeInsets.symmetric(
                        horizontal: 8, vertical: 3),
                    decoration: BoxDecoration(
                      color: Theme.of(context).colorScheme.primary
                          .withValues(alpha: .08),
                      borderRadius: BorderRadius.circular(10),
                    ),
                    child: Text(
                      '$valueLabel ${it.value}',
                      style: TextStyle(
                          fontSize: 12,
                          color: Theme.of(context).colorScheme.primary),
                    ),
                  ),
              ],
            ),
          ),
      ],
    );
  }
}

class _ErrorRow extends StatelessWidget {
  final String message;

  const _ErrorRow({required this.message});

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.all(16),
      child: Row(
        children: [
          Icon(Icons.cloud_off_outlined,
              size: 18, color: Theme.of(context).colorScheme.error),
          const SizedBox(width: 8),
          Expanded(
            child: Text('抓取失败：$message（限速器排队或官方页面变动，稍后重试）',
                style: TextStyle(color: Theme.of(context).colorScheme.error)),
          ),
        ],
      ),
    );
  }
}
