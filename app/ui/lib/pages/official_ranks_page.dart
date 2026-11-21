import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../core/providers.dart';
import '../data/api/strata_api.dart';
import '../widgets/default_cover.dart';

/// 官方榜单：在榜单页内用 Tab 切换月票/新书/热销/打赏，不再有中间网格页。
/// 对话月票榜（m4）仍从对话 tab 直达，不进入长篇的 Tab 组。
/// 来源（docs/sfacg-live-ranks.md）：
///  1. 历史月榜库（MonthlyBoy.ashx，2013-03 起任意月份，月票带票数；
///     对话 rank=4 从 2017-07 起）
///  2. PC 月度打赏榜（book.sfacg.com/Rank/）；PC 月票/热销与月榜库当月
///     rank=0/3 是同一榜，不重复展示；粉丝榜为用户充值榜
/// 移动榜单 2026-11-21 整体移除（官方 API 多 bug，数据不可信；端点保真保留）。

/// 榜单定义：id 同时是路由参数。
/// m0/m2/m3/m4 = 月榜库 rank 0/2/3/4；pc1 = PC 月度打赏榜。
const _officialBoards = [
  ('m0', '月票榜', '月票票数榜（top 20，带票数）'),
  ('m2', '新书榜', '官方月度新书榜（top 10）'),
  ('m3', '热销榜', '当期点券消耗排序；免费书结构性不可入榜'),
  ('m4', '对话月票榜', '对话产品线月票票数榜（2017-07 第一份；2018-07 起连续）'),
  ('pc1', '月度打赏榜', '当期打赏（无数值）'),
];

/// 长篇官方榜的 Tab 顺序。对话月票榜只在对话 tab 直达。
const _longBoardIds = ['m0', 'm2', 'm3', 'pc1'];

String _boardTitle(String id) {
  for (final (bid, title, _) in _officialBoards) {
    if (bid == id) return title;
  }
  return id;
}

String _boardNote(String id) {
  for (final (bid, _, note) in _officialBoards) {
    if (bid == id) return note;
  }
  return '';
}

bool _isMonthlyBoard(String id) => id.startsWith('m') && id.length == 2;

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
        final items = await handle.api.officialRanksMonthly(
          month: month,
          rank: rank,
        );
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
          note: _boardNote(board),
          items: b.entries,
          valueLabel: b.name == '月度月票榜' ? '月票' : null,
        );
      }
      throw ArgumentError('unknown board: $board');
    });

/// 对话月票榜直达页：标题 + 榜单正文（无中间页）。
class OfficialRankDetailPage extends StatelessWidget {
  final String board;

  const OfficialRankDetailPage({super.key, required this.board});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: Text(_boardTitle(board))),
      body: _OfficialBoardView(board: board),
    );
  }
}

/// 单个官方榜的正文：月份切换条 + 说明 + 榜单行。
/// 长篇 Tab 页也复用它，避免月份逻辑重复。
class _OfficialBoardView extends ConsumerStatefulWidget {
  final String board;

  const _OfficialBoardView({required this.board});

  @override
  ConsumerState<_OfficialBoardView> createState() => _OfficialBoardViewState();
}

class _OfficialBoardViewState extends ConsumerState<_OfficialBoardView> {
  late String _month = _ym(DateTime.now());

  static String _ym(DateTime d) =>
      '${d.year.toString().padLeft(4, '0')}-${d.month.toString().padLeft(2, '0')}';

  bool get _isMonthly => _isMonthlyBoard(widget.board);

  /// 对话月票榜第一份数据在 2017-07，2018-07 起连续（2026-11-21
  /// 用户核实）。因此对话榜的可选下界取 2017-07；中间空槽照常显示
  /// “无数据”。其余历史月榜从 2013-03 起。
  String get _firstMonth => widget.board == 'm4' ? '2017-07' : '2013-03';

  bool get _canPrev => _isMonthly && _month.compareTo(_firstMonth) > 0;

  bool get _canNext => _isMonthly && _month.compareTo(_ym(DateTime.now())) < 0;

  void _shiftMonth(int delta) {
    final parts = _month.split('-');
    setState(() {
      _month = _ym(DateTime(int.parse(parts[0]), int.parse(parts[1]) + delta));
    });
  }

  Future<void> _pickMonth() async {
    final parts = _month.split('-');
    final first = _firstMonth.split('-');
    final now = DateTime.now();
    final scheme = Theme.of(context).colorScheme;
    await showModalBottomSheet<void>(
      context: context,
      backgroundColor: scheme.surface,
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(20)),
      ),
      builder: (_) => _MonthSheet(
        minYear: int.parse(first[0]),
        minMonth: int.parse(first[1]),
        maxYear: now.year,
        maxMonth: now.month,
        initialYear: int.parse(parts[0]),
        initialMonth: int.parse(parts[1]),
        onSelect: (year, month) =>
            setState(() => _month = _ym(DateTime(year, month))),
      ),
    );
  }

  Widget _monthBar(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return Padding(
      padding: const EdgeInsets.fromLTRB(8, 8, 8, 0),
      child: Row(
        children: [
          IconButton(
            onPressed: _canPrev ? () => _shiftMonth(-1) : null,
            icon: const Icon(Icons.chevron_left),
            tooltip: '上个月',
          ),
          Expanded(
            child: Center(
              child: TextButton.icon(
                onPressed: _pickMonth,
                icon: const Icon(Icons.calendar_month, size: 16),
                label: Text(
                  _month,
                  style: TextStyle(
                    fontSize: 14,
                    fontWeight: FontWeight.w600,
                    color: scheme.onSurface,
                  ),
                ),
              ),
            ),
          ),
          IconButton(
            onPressed: _canNext ? () => _shiftMonth(1) : null,
            icon: const Icon(Icons.chevron_right),
            tooltip: '下个月',
          ),
        ],
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final detail = ref.watch(
      _boardDetailProvider((widget.board, _isMonthly ? _month : 'now')),
    );

    return Column(
      children: [
        if (_isMonthly) _monthBar(context),
        Expanded(
          child: detail.when(
            loading: () => const Center(child: CircularProgressIndicator()),
            error: (e, _) => _ErrorRow(error: e),
            data: (d) => ListView(
              padding: const EdgeInsets.all(12),
              children: [
                Text(
                  d.note,
                  style: Theme.of(context).textTheme.bodySmall
                      ?.copyWith(color: scheme.onSurfaceVariant),
                ),
                const SizedBox(height: 8),
                _RankList(
                  items: d.items,
                  valueLabel: d.valueLabel,
                  // 月度打赏榜不显示封面（2026-11-21 用户拍板）：官方页无
                  // 图片标记，入榜单书多在 seed 外、无法本地补封面。
                  showCover: widget.board != 'pc1',
                ),
              ],
            ),
          ),
        ),
      ],
    );
  }
}

/// 月份选择 BottomSheet：年份横滑 + 月份 4×3 网格。
/// 不用 Dropdown：用户 2026-11-21 明确反馈下拉切换 bug 多且有旧 Web 表单感。
class _MonthSheet extends StatefulWidget {
  final int minYear;
  final int minMonth;
  final int maxYear;
  final int maxMonth;
  final int initialYear;
  final int initialMonth;
  final void Function(int year, int month) onSelect;

  const _MonthSheet({
    required this.minYear,
    required this.minMonth,
    required this.maxYear,
    required this.maxMonth,
    required this.initialYear,
    required this.initialMonth,
    required this.onSelect,
  });

  @override
  State<_MonthSheet> createState() => _MonthSheetState();
}

class _MonthSheetState extends State<_MonthSheet> {
  late int _year = widget.initialYear;

  bool _enabled(int month) {
    if (_year == widget.minYear && month < widget.minMonth) return false;
    if (_year == widget.maxYear && month > widget.maxMonth) return false;
    return true;
  }

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return SafeArea(
      child: Padding(
        padding: const EdgeInsets.fromLTRB(16, 16, 16, 20),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                const Text(
                  '选择月份',
                  style: TextStyle(fontSize: 15, fontWeight: FontWeight.w600),
                ),
                const Spacer(),
                Text(
                  '点年份切换 · 点月份查看',
                  style: TextStyle(
                    fontSize: 11,
                    color: scheme.onSurfaceVariant,
                  ),
                ),
              ],
            ),
            const SizedBox(height: 12),
            SizedBox(
              height: 40,
              child: SingleChildScrollView(
                scrollDirection: Axis.horizontal,
                child: Row(
                  children: [
                    for (int y = widget.minYear; y <= widget.maxYear; y++)
                      Padding(
                        padding: const EdgeInsets.only(right: 8),
                        child: FilterChip(
                          label: Text('$y'),
                          selected: _year == y,
                          showCheckmark: false,
                          onSelected: (_) => setState(() => _year = y),
                        ),
                      ),
                  ],
                ),
              ),
            ),
            const SizedBox(height: 12),
            GridView.count(
              crossAxisCount: 4,
              shrinkWrap: true,
              physics: const NeverScrollableScrollPhysics(),
              mainAxisSpacing: 8,
              crossAxisSpacing: 8,
              childAspectRatio: 2.6,
              children: [
                for (int m = 1; m <= 12; m++)
                  FilterChip(
                    label: Text('$m月'),
                    selected:
                        _year == widget.initialYear && m == widget.initialMonth,
                    showCheckmark: false,
                    onSelected: _enabled(m)
                        ? (_) {
                            widget.onSelect(_year, m);
                            Navigator.of(context).pop();
                          }
                        : null,
                  ),
              ],
            ),
          ],
        ),
      ),
    );
  }
}

// ---------------------------------------------------------------------------
// 榜单 Tab 页
// ---------------------------------------------------------------------------

class OfficialRanksPage extends ConsumerStatefulWidget {
  const OfficialRanksPage({super.key});

  @override
  ConsumerState<OfficialRanksPage> createState() => _OfficialRanksPageState();
}

class _OfficialRanksPageState extends ConsumerState<OfficialRanksPage>
    with SingleTickerProviderStateMixin {
  late final TabController _tabs;

  @override
  void initState() {
    super.initState();
    _tabs = TabController(length: _longBoardIds.length, vsync: this)
      ..addListener(_onTabChanged);
  }

  void _onTabChanged() {
    if (_tabs.indexIsChanging) return;
    setState(() {});
  }

  @override
  void dispose() {
    _tabs.removeListener(_onTabChanged);
    _tabs.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final board = _longBoardIds[_tabs.index];
    return Scaffold(
      appBar: AppBar(
        title: const Text('官方榜单'),
        bottom: TabBar(
          controller: _tabs,
          tabs: [for (final id in _longBoardIds) Tab(text: _boardTitle(id))],
        ),
      ),
      body: _OfficialBoardView(board: board),
    );
  }
}

/// 榜单行列表：序号 +（封面）+ 标题 + 作者/题材 + 数值（月票/火券）。
/// showCover=false 的榜（月度打赏榜）行内无封面。
class _RankList extends ConsumerWidget {
  final List<OfficialRankEntry> items;
  final String? valueLabel;
  final bool showCover;

  const _RankList({
    required this.items,
    this.valueLabel,
    this.showCover = true,
  });

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    if (items.isEmpty) {
      return Padding(
        padding: const EdgeInsets.all(16),
        child: Text(
          '该月该榜无数据',
          style: TextStyle(
            color: Theme.of(context).colorScheme.onSurfaceVariant,
          ),
        ),
      );
    }
    return Column(
      children: [
        for (final it in items)
          InkWell(
            // 点行 → 详情页：seed 书走常规详情；库外书先预写 book_meta
            // （rank-seed，纯本地），详情页首帧即渲染 overlay，完整数据
            // 由后台 refresh 补全（docs/08 §rank-seed）。无 nid 条目不可点。
            onTap: it.nid > 0
                ? () async {
                    try {
                      final h = await ref.read(bootProvider.future);
                      await h.api.rankSeed(
                        nid: it.nid,
                        title: it.title,
                        author: it.author,
                        coverUrl: it.coverUrl ?? '',
                        genre: it.genre ?? '',
                      );
                    } catch (_) {}
                    if (!context.mounted) return;
                    context.push('/book/${it.nid}');
                  }
                : null,
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
                  if (showCover)
                    SizedBox(
                      width: 38,
                      height: 54,
                      child: coverImage(it.coverUrl, it.nid),
                    ),
                  if (showCover) const SizedBox(width: 10),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          it.title,
                          style: const TextStyle(
                            fontWeight: FontWeight.w600,
                            fontSize: 14,
                          ),
                        ),
                        if (it.author.isNotEmpty || it.genre != null)
                          Text(
                            [it.author, it.genre]
                                .where((s) => s != null && s.isNotEmpty)
                                .join(' · '),
                            style: TextStyle(
                              fontSize: 12,
                              color: Theme.of(context)
                                  .colorScheme
                                  .onSurfaceVariant,
                            ),
                          ),
                      ],
                    ),
                  ),
                  if (it.value > 0 && valueLabel != null)
                    Container(
                      padding: const EdgeInsets.symmetric(
                        horizontal: 8,
                        vertical: 3,
                      ),
                      decoration: BoxDecoration(
                        color: Theme.of(context).colorScheme.primary
                            .withValues(alpha: .08),
                        borderRadius: BorderRadius.circular(10),
                      ),
                      child: Text(
                        '$valueLabel ${it.value}',
                        style: TextStyle(
                          fontSize: 12,
                          color: Theme.of(context).colorScheme.primary,
                        ),
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
          Icon(
            Icons.cloud_off_outlined,
            size: 18,
            color: Theme.of(context).colorScheme.error,
          ),
          const SizedBox(width: 8),
          Expanded(
            child: Text(
              _text,
              style: TextStyle(color: Theme.of(context).colorScheme.error),
            ),
          ),
        ],
      ),
    );
  }
}
