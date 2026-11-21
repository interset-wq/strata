import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../core/providers.dart';
import '../data/api/strata_api.dart';
import '../widgets/default_cover.dart';

/// 官方榜单页（网格入口）：每格指向一个榜单详情页。
/// 来源（docs/sfacg-live-ranks.md）：
///  1. 历史月榜库（MonthlyBoy.ashx，2013-03 起任意月份，月票带票数）
///  2. PC 当期四榜（book.sfacg.com/Rank/）
///  3. 移动热销榜（m.sfacg.com/rank/sale.html）——移动五榜中仅此一个有效
///     （人气/收藏/新书/日轻四个榜数据落后 >3 年，2026-11-20 用户实测判定过时）
/// 网格结构与详情页分离，便于后续由 demo 改造为正式榜单页。

/// 榜单格定义：id 同时是路由参数。
/// m0/m2/m3/m4 = 月榜库 rank 0/2/3/4；pc0..pc3 = PC 页第 1..4 个板；sale = 移动热销榜。
const _boardGroups = [
  (
    '历史月榜库（2013-03 至今）',
    'MonthlyBoy.ashx——官方历史月榜，任意月份可查、按月清零；'
        '月票票数是站内唯一公开的付费强度信号',
    [
      ('m0', '月票榜', '月票票数榜（top 20，带票数）'),
      ('m2', '新书榜', '官方月度新书榜（top 10）'),
      ('m3', '热销榜', '当期点券消耗排序；免费书结构性不可入榜'),
      ('m4', '对话月票榜', '对话产品线月票票数榜（2017-07 起）'),
    ],
  ),
  (
    'PC 当期四榜',
    'book.sfacg.com/Rank/——当期月榜一页四榜',
    [
      ('pc0', '月度月票榜', '带月票票数'),
      ('pc1', '月度打赏榜', '当期打赏（无数值）'),
      ('pc2', '月度热销榜', '当期点券消耗（无数值）'),
      ('pc3', '粉丝榜', '读者侧（消费火券，无书 nid）'),
    ],
  ),
  (
    '移动',
    'm.sfacg.com/rank/——仅热销榜有效（与手机 App「畅销榜」几乎一致，'
        '数据更新滞后约 ≤3 天）；人气/收藏/新书/日轻四榜数据落后 >3 年，'
        '2026-11-20 实测判定过时，不展示',
    [
      ('sale', '热销榜', '与手机 App「畅销榜」一致（top 20，无数值）'),
    ],
  ),
];

String _boardTitle(String id) {
  for (final (_, _, boards) in _boardGroups) {
    for (final (bid, title, _) in boards) {
      if (bid == id) return title;
    }
  }
  return id;
}

String _boardNote(String id) {
  for (final (_, _, boards) in _boardGroups) {
    for (final (bid, _, note) in boards) {
      if (bid == id) return note;
    }
  }
  return '';
}

// ---------------------------------------------------------------------------
// 详情页
// ---------------------------------------------------------------------------

class _BoardDetail {
  final String title;
  final String note;
  final List<OfficialRankEntry> items;
  final String? valueLabel;

  const _BoardDetail({
    required this.title,
    required this.note,
    required this.items,
    this.valueLabel,
  });
}

final _boardDetailProvider = FutureProvider.autoDispose
    .family<_BoardDetail, (String, String)>((ref, arg) async {
  final (board, month) = arg;
  final handle = await ref.watch(bootProvider.future);

  if (board.startsWith('m') && board.length == 2) {
    final rank = int.parse(board[1]);
    final items =
        await handle.api.officialRanksMonthly(month: month, rank: rank);
    final kind = {0: '月票榜', 2: '新书榜', 3: '热销榜', 4: '对话月票榜'}[rank];
    return _BoardDetail(
      title: '$kind（$month）',
      note: _boardNote(board),
      items: items,
      valueLabel: (rank == 0 || rank == 4) ? '月票' : null,
    );
  }
  if (board.startsWith('pc') && board.length == 3) {
    final boards = await handle.api.officialRanksPc();
    final b = boards[int.parse(board[2])];
    return _BoardDetail(
      title: b.name,
      note: b.name == '粉丝榜'
          ? '读者侧当期月榜（消费火券）——不是书榜'
          : _boardNote(board),
      items: b.entries,
      valueLabel: b.name == '月度月票榜'
          ? '月票'
          : (b.name == '粉丝榜' ? '火券' : null),
    );
  }
  if (board == 'sale') {
    final items = await handle.api.officialRanksMobile(slug: 'sale');
    return _BoardDetail(
      title: '移动热销榜',
      note: 'm.sfacg.com/rank/sale.html——与手机 App「畅销榜」几乎一致，'
          '数据更新滞后约 ≤3 天',
      items: items,
    );
  }
  throw ArgumentError('unknown board: $board');
});

/// 榜单详情页：说明 + （月榜库带月份切换）+ 榜单行。
class OfficialRankDetailPage extends ConsumerStatefulWidget {
  final String board;

  const OfficialRankDetailPage({super.key, required this.board});

  @override
  ConsumerState<OfficialRankDetailPage> createState() =>
      _OfficialRankDetailPageState();
}

class _OfficialRankDetailPageState
    extends ConsumerState<OfficialRankDetailPage> {
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

  bool get _isMonthly =>
      widget.board.startsWith('m') && widget.board.length == 2;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final detail = ref.watch(
        _boardDetailProvider((widget.board, _isMonthly ? _month : 'now')));

    return Scaffold(
      appBar: AppBar(title: Text(_boardTitle(widget.board))),
      body: Column(
        children: [
          if (_isMonthly)
            Padding(
              padding: const EdgeInsets.fromLTRB(16, 12, 16, 0),
              child: DropdownButtonFormField<String>(
                initialValue: _month,
                decoration: const InputDecoration(
                  labelText: '月份（2013-03 起可查）',
                  contentPadding:
                      EdgeInsets.symmetric(horizontal: 16),
                ),
                items: [
                  for (final m in _monthOptions)
                    DropdownMenuItem(value: m, child: Text(m)),
                ],
                onChanged: (m) => setState(() => _month = m!),
              ),
            ),
          Expanded(
            child: detail.when(
              loading: () => const Center(child: CircularProgressIndicator()),
              error: (e, _) => _ErrorRow(error: e),
              data: (d) => ListView(
                padding: const EdgeInsets.all(12),
                children: [
                  Text(d.note,
                      style: Theme.of(context)
                          .textTheme
                          .bodySmall
                          ?.copyWith(color: scheme.onSurfaceVariant)),
                  const SizedBox(height: 8),
                  _RankList(items: d.items, valueLabel: d.valueLabel),
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }
}

// ---------------------------------------------------------------------------
// 网格入口页
// ---------------------------------------------------------------------------

class OfficialRanksPage extends ConsumerWidget {
  const OfficialRanksPage({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final scheme = Theme.of(context).colorScheme;

    return Scaffold(
      appBar: AppBar(title: const Text('官方榜单')),
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          for (final (groupTitle, groupNote, boards) in _boardGroups) ...[
            Text(groupTitle, style: Theme.of(context).textTheme.titleLarge),
            const SizedBox(height: 4),
            Text(groupNote,
                style: Theme.of(context)
                    .textTheme
                    .bodySmall
                    ?.copyWith(color: scheme.onSurfaceVariant)),
            const SizedBox(height: 8),
            GridView.builder(
              shrinkWrap: true,
              physics: const NeverScrollableScrollPhysics(),
              gridDelegate:
                  const SliverGridDelegateWithFixedCrossAxisCount(
                crossAxisCount: 2,
                mainAxisExtent: 92,
                crossAxisSpacing: 10,
                mainAxisSpacing: 10,
              ),
              itemCount: boards.length,
              itemBuilder: (context, i) {
                final (id, title, note) = boards[i];
                return Card(
                  clipBehavior: Clip.antiAlias,
                  child: InkWell(
                    onTap: () => context.push('/official-ranks/$id'),
                    child: Padding(
                      padding: const EdgeInsets.all(12),
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        mainAxisAlignment: MainAxisAlignment.center,
                        children: [
                          Text(title,
                              style: const TextStyle(
                                  fontSize: 15,
                                  fontWeight: FontWeight.w600)),
                          const SizedBox(height: 4),
                          Text(note,
                              maxLines: 2,
                              overflow: TextOverflow.ellipsis,
                              style: TextStyle(
                                  fontSize: 11,
                                  color: scheme.onSurfaceVariant)),
                        ],
                      ),
                    ),
                  ),
                );
              },
            ),
            const SizedBox(height: 20),
          ],
        ],
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
            style: TextStyle(
                color: Theme.of(context).colorScheme.onSurfaceVariant)),
      );
    }
    return Column(
      children: [
        for (final it in items)
          InkWell(
            // 点行 → 详情页：seed 书走常规详情；库外书 404 后由详情页
            // 自动收录（按需抓取写回 user.db，docs/08 §search-remote）。
            // PC 粉丝榜条目无 nid（读者侧），不可点。
            onTap: it.nid > 0 ? () => context.push('/book/${it.nid}') : null,
            child: Padding(
              padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 6),
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
                  const SizedBox(width: 8),
                  SizedBox(
                    width: 38,
                    height: 54,
                    child: coverImage(it.coverUrl, it.nid),
                  ),
                  const SizedBox(width: 10),
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
          ),
      ],
    );
  }
}

class _ErrorRow extends StatelessWidget {
  final Object? error;

  const _ErrorRow({required this.error});

  String get _text {
    final e = error;
    if (e is StrataApiException && e.code == 'offline') {
      return e.message;
    }
    return '抓取失败：$e（限速器排队或官方页面变动，稍后重试）';
  }

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
            child: Text(_text,
                style: TextStyle(color: Theme.of(context).colorScheme.error)),
          ),
        ],
      ),
    );
  }
}
