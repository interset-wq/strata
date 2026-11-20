import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../app/theme.dart';
import '../core/providers.dart';
import '../data/api/strata_api.dart';
import '../widgets/back_to_top.dart';
import '../widgets/book_row_tile.dart';
import '../widgets/default_cover.dart';
import '../widgets/metric_badge.dart';

/// 发书日历（docs/14 P1，底部导航替换搜索 tab）：
/// 「同期出发的作品」——按 est_date 聚合 seed 书浏览。三个粒度：
///  - 月视图（默认）：7 列日期格（每格作品数），点有书格子进日视图
///  - 周视图：7 行（每日一行）+ 前三本迷你卡，点行进日视图
///  - 日视图：全量列表（收藏降序，带 est_conf 精度徽标）
/// 口径（docs/14 §1.3）：日期是「作品创建时间估计」，非首章发布日期，
/// UI 标「上架日期（估计）」；low 档只入月视图（引擎侧过滤）；
/// 右删失边界 = manifest genMin..genMax（日历不显示界外年份）。
/// 推荐层不消费日历——只改变浏览路径，不改打分（12 §信号白名单）。
class CalendarPage extends ConsumerStatefulWidget {
  const CalendarPage({super.key});

  @override
  ConsumerState<CalendarPage> createState() => _CalendarPageState();
}

class _CalendarPageState extends ConsumerState<CalendarPage> {
  static const _weekdays = ['一', '二', '三', '四', '五', '六', '日'];

  String _granularity = 'month'; // month|week|day
  late DateTime _focus = DateTime(2025, 1, 1); // 用户当前聚焦日（统一锚点）
  int _genMin = 2007, _genMax = 2025; // manifest 右删失边界（initState 加载）

  final _dayScroll = ScrollController();
  bool _showTop = false;

  DateTime get _minDate => DateTime(_genMin, 1, 1);
  DateTime get _maxDate => DateTime(_genMax, 12, 31);

  DateTime _mondayOf(DateTime d) =>
      d.subtract(Duration(days: (d.weekday - DateTime.monday)));

  String _pad(int n) => n.toString().padLeft(2, '0');

  String _anchor() {
    final f = _focus;
    switch (_granularity) {
      case 'month':
        return '${f.year}-${_pad(f.month)}-01';
      case 'week':
        final m = _mondayOf(f);
        return '${m.year}-${_pad(m.month)}-${_pad(m.day)}';
      default:
        return '${f.year}-${_pad(f.month)}-${_pad(f.day)}';
    }
  }

  DateTime _viewStart() {
    final f = _focus;
    switch (_granularity) {
      case 'month':
        return DateTime(f.year, f.month, 1);
      case 'week':
        return _mondayOf(f);
      default:
        return DateTime(f.year, f.month, f.day);
    }
  }

  DateTime _viewEnd() {
    final f = _focus;
    switch (_granularity) {
      case 'month':
        return DateTime(f.year, f.month + 1, 0);
      case 'week':
        return _mondayOf(f).add(const Duration(days: 6));
      default:
        return DateTime(f.year, f.month, f.day);
    }
  }

  // 右删失（docs/14 §1.3）：越界一步即禁用导航。
  bool get _canPrev =>
      !_viewStart().subtract(const Duration(days: 1)).isBefore(_minDate);
  bool get _canNext =>
      !_viewEnd().add(const Duration(days: 1)).isAfter(_maxDate);

  void _shift(int dir) {
    setState(() {
      final f = _focus;
      switch (_granularity) {
        case 'month':
          _focus = DateTime(f.year, f.month + dir, 1);
        case 'week':
          _focus = f.add(Duration(days: 7 * dir));
        default:
          _focus = f.add(Duration(days: dir));
      }
      if (_focus.isBefore(_minDate)) _focus = _minDate;
      if (_focus.isAfter(_maxDate)) _focus = _maxDate;
    });
  }

  void _openDay(DateTime d) {
    setState(() {
      _focus = DateTime(d.year, d.month, d.day);
      _granularity = 'day';
    });
  }

  // ── 年月快速跳转：标题点击打开二维选择器（年横滑行 × 月 4×3 网格）。
  // 点年即时切换（保留月，sheet 不关，可继续点月）；点月跳转并关闭。
  // 右删失边界直接由年范围表达（genMin..genMax），无需禁用态。

  void _jumpTo(int y, int m) {
    setState(() => _focus = DateTime(y, m, 1));
  }

  Future<void> _showYearMonthPicker() async {
    final scheme = Theme.of(context).colorScheme;
    await showModalBottomSheet<void>(
      context: context,
      backgroundColor: scheme.surface,
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(20)),
      ),
      builder: (_) => _YearMonthSheet(
        minYear: _genMin,
        maxYear: _genMax,
        initialYear: _focus.year,
        initialMonth: _focus.month,
        onYear: (y) => _jumpTo(y, _focus.month),
        onMonth: (m) => _jumpTo(_focus.year, m),
      ),
    );
  }

  @override
  void initState() {
    super.initState();
    _dayScroll.addListener(() {
      final show = _dayScroll.offset > 500;
      if (show != _showTop) setState(() => _showTop = show);
    });
    _loadBounds();
  }

  Future<void> _loadBounds() async {
    try {
      final handle = await ref.read(bootProvider.future);
      final meta = await handle.api.meta();
      if (!mounted) return;
      setState(() {
        _genMin = meta.manifest.genMin;
        _genMax = meta.manifest.genMax;
        if (_focus.isAfter(_maxDate)) _focus = _maxDate;
      });
    } catch (_) {
      // 失败保留默认边界（当前种子内容上界 2007..2025）
    }
  }

  @override
  void dispose() {
    _dayScroll.dispose();
    super.dispose();
  }

  String _title() {
    final f = _focus;
    switch (_granularity) {
      case 'month':
        return '${f.year}年${f.month}月';
      case 'week':
        final m = _mondayOf(f);
        final s = m.add(const Duration(days: 6));
        return '${m.month}月${m.day}日 – ${s.month}月${s.day}日';
      default:
        return '${f.month}月${f.day}日（周${_weekdays[f.weekday - 1]}）';
    }
  }

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final data = ref.watch(calendarProvider(CalendarQuery(
      granularity: _granularity,
      anchor: _anchor(),
      perCell: _granularity == 'day' ? 50 : 3,
    )));

    return Scaffold(
      appBar: AppBar(title: const Text('发书日历')),
      body: SafeArea(
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            // 口径标注（docs/14 §1.3 + 样本口径）：本日历聚合的是内置库
            // （seed 收录子集），不是全站新书数；日期是创建时间估计。
            Padding(
              padding: const EdgeInsets.fromLTRB(16, 2, 16, 6),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    '双层计数：~N = 全平台估计新书  N 内置 = 可点击内置库子集',
                    style: TextStyle(
                        fontSize: 11, color: scheme.onSurfaceVariant),
                  ),
                  const SizedBox(height: 2),
                  Text(
                    '定年 = nid 锚点内插（中位误差 2 天）；上架日期为估计值，非首章发布日期',
                    style: TextStyle(
                        fontSize: 11, color: scheme.onSurfaceVariant),
                  ),
                ],
              ),
            ),
            // 粒度切换：月/周/日（从日/周切回月 = 回到月网格）
            Padding(
              padding: const EdgeInsets.symmetric(horizontal: 16),
              child: SegmentedButton<String>(
                segments: const [
                  ButtonSegment(value: 'month', label: Text('月')),
                  ButtonSegment(value: 'week', label: Text('周')),
                  ButtonSegment(value: 'day', label: Text('日')),
                ],
                selected: {_granularity},
                onSelectionChanged: (s) =>
                    setState(() => _granularity = s.first),
              ),
            ),
            // 日期导航行（右删失边界处禁用）
            Padding(
              padding: const EdgeInsets.fromLTRB(8, 8, 8, 4),
              child: Row(
                children: [
                  IconButton(
                    icon: const Icon(Icons.chevron_left),
                    onPressed: _canPrev ? () => _shift(-1) : null,
                  ),
                  Expanded(
                    child: InkWell(
                      onTap: _showYearMonthPicker,
                      child: Padding(
                        padding: const EdgeInsets.symmetric(vertical: 8),
                        child: Row(
                          mainAxisSize: MainAxisSize.min,
                          mainAxisAlignment: MainAxisAlignment.center,
                          children: [
                            Text(
                              _title(),
                              style: const TextStyle(
                                  fontSize: 16,
                                  fontWeight: FontWeight.w600,
                                  fontFamily: StrataTokens.serif),
                            ),
                            const SizedBox(width: 4),
                            Icon(
                              Icons.expand_more,
                              size: 18,
                              color: scheme.onSurfaceVariant,
                            ),
                          ],
                        ),
                      ),
                    ),
                  ),
                  IconButton(
                    icon: const Icon(Icons.chevron_right),
                    onPressed: _canNext ? () => _shift(1) : null,
                  ),
                ],
              ),
            ),
            // 内容区
            Expanded(
              child: data.when(
                loading: () =>
                    const Center(child: CircularProgressIndicator()),
                error: (e, _) =>
                    Center(child: Text('日历加载失败：$e')),
                data: (resp) => switch (_granularity) {
                  'month' => _buildMonth(resp, scheme),
                  'week' => _buildWeek(resp, scheme),
                  _ => _buildDay(resp, scheme),
                },
              ),
            ),
          ],
        ),
      ),
    );
  }

  // ── 月视图：7 列日期格，每格作品数；点有书格子进日视图 ──────────────

  Widget _buildMonth(CalendarResponse resp, ColorScheme scheme) {
    final days = resp.cells;
    if (days.isEmpty) {
      return _empty('本月没有估计发书作品');
    }
    final firstWeekday = DateTime.parse(days.first.date).weekday - 1;
    final total = days.fold<int>(0, (s, c) => s + c.total);
    final uni = days.fold<int>(0, (s, c) => s + c.universe);
    if (total == 0 && uni == 0) {
      return _empty('本月没有估计发书作品');
    }
    return Padding(
      padding: const EdgeInsets.fromLTRB(12, 4, 12, 12),
      child: Column(
        children: [
          Row(
            children: [
              for (final w in _weekdays)
                Expanded(
                  child: Text(
                    '周$w',
                    textAlign: TextAlign.center,
                    style: TextStyle(
                        fontSize: 11, color: scheme.onSurfaceVariant),
                  ),
                ),
            ],
          ),
          const SizedBox(height: 6),
          Expanded(
            child: GridView.builder(
              gridDelegate:
                  const SliverGridDelegateWithFixedCrossAxisCount(
                crossAxisCount: 7,
                mainAxisSpacing: 6,
                crossAxisSpacing: 6,
                childAspectRatio: 0.72,
              ),
              itemCount: firstWeekday + days.length,
              itemBuilder: (context, i) {
                if (i < firstWeekday) return const SizedBox.shrink();
                final c = days[i - firstWeekday];
                final dayNum = int.parse(c.date.substring(8));
                final has = c.total > 0;
                return GestureDetector(
                  onTap: has ? () => _openDay(DateTime.parse(c.date)) : null,
                  child: Container(
                    decoration: BoxDecoration(
                      color: has ? scheme.surface : Colors.transparent,
                      borderRadius: BorderRadius.circular(8),
                      border: has
                          ? Border.all(
                              color: scheme.outline.withValues(alpha: .35))
                          : null,
                    ),
                    child: Column(
                      mainAxisAlignment: MainAxisAlignment.center,
                      children: [
                        Text(
                          '$dayNum',
                          style: TextStyle(
                            fontSize: 13,
                            fontWeight:
                                has ? FontWeight.w700 : FontWeight.w400,
                            color: has
                                ? scheme.onSurface
                                : scheme.onSurfaceVariant
                                    .withValues(alpha: .7),
                          ),
                        ),
                        if (has)
                          Text(
                            '~${c.universe}',
                            style: TextStyle(
                                fontSize: 11,
                                fontWeight: FontWeight.w700,
                                color: scheme.primary),
                          ),
                        if (has)
                          Text(
                            '${c.total}内置',
                            style: TextStyle(
                                fontSize: 9, color: scheme.onSurfaceVariant),
                          ),
                      ],
                    ),
                  ),
                );
              },
            ),
          ),
          const SizedBox(height: 8),
          Center(
            child: Text(
              '本月：全平台估计 ~$uni 本 · 内置库 $total 本（可点击）',
              style:
                  TextStyle(fontSize: 11, color: scheme.onSurfaceVariant),
            ),
          ),
        ],
      ),
    );
  }

  // ── 周视图：每日一行 + 前三本迷你卡（conf 徽标），点行进日视图 ────────

  Widget _buildWeek(CalendarResponse resp, ColorScheme scheme) {
    final days = resp.cells;
    final weekUni = days.fold<int>(0, (s, c) => s + c.universe);
    if (days.every((c) => c.total == 0) && weekUni == 0) {
      return _empty('本周没有估计发书作品');
    }
    return ListView.separated(
      padding: const EdgeInsets.fromLTRB(16, 4, 16, 16),
      itemCount: days.length,
      separatorBuilder: (_, _) => const SizedBox(height: 8),
      itemBuilder: (context, i) {
        final c = days[i];
        final d = DateTime.parse(c.date);
        return GestureDetector(
          onTap: c.total > 0 ? () => _openDay(d) : null,
          child: Container(
            padding: const EdgeInsets.all(12),
            decoration: BoxDecoration(
              color: scheme.surface,
              borderRadius: BorderRadius.circular(12),
              border: Border.all(
                  color: scheme.outline.withValues(alpha: .25)),
            ),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  children: [
                    Text(
                      '${d.month}月${d.day}日',
                      style: const TextStyle(
                          fontSize: 14, fontWeight: FontWeight.w600),
                    ),
                    const SizedBox(width: 6),
                    Text(
                      '（周${_weekdays[d.weekday - 1]}）',
                      style: TextStyle(
                          fontSize: 12, color: scheme.onSurfaceVariant),
                    ),
                    const Spacer(),
                    if (c.total > 0 || c.universe > 0)
                      Text(
                        c.universe > 0
                            ? '~${c.universe}本 · ${c.total}内置'
                            : '${c.total}本',
                        style: TextStyle(
                            fontSize: 11,
                            fontWeight: FontWeight.w600,
                            color: scheme.primary),
                      ),
                  ],
                ),
                for (final it in c.items)
                  Padding(
                    padding: const EdgeInsets.only(top: 10),
                    child: Row(
                      children: [
                        SizedBox(
                          width: 34,
                          height: 46,
                          child: ClipRRect(
                            borderRadius: BorderRadius.circular(4),
                            child: _miniCover(it),
                          ),
                        ),
                        const SizedBox(width: 10),
                        Expanded(
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              Text(
                                it.title,
                                maxLines: 1,
                                overflow: TextOverflow.ellipsis,
                                style:
                                    const TextStyle(fontSize: 12),
                              ),
                              const SizedBox(height: 2),
                              Text(
                                it.author,
                                maxLines: 1,
                                overflow: TextOverflow.ellipsis,
                                style: TextStyle(
                                    fontSize: 10,
                                    color: scheme.onSurfaceVariant),
                              ),
                            ],
                          ),
                        ),
                        _ConfBadge(conf: it.estConf),
                      ],
                    ),
                  ),
              ],
            ),
          ),
        );
      },
    );
  }

  // ── 日视图：全量列表（收藏降序），长列表带 back-to-top ───────────────

  Widget _buildDay(CalendarResponse resp, ColorScheme scheme) {
    final day = resp.cells.single;
    if (day.total == 0 && day.universe == 0) {
      return _empty('当日没有估计发书作品');
    }
    if (day.total == 0) {
      return _empty(
          '内置库当日无可点击作品（全平台估计 ~${day.universe} 本）');
    }
    return Stack(
      children: [
        ListView.separated(
          controller: _dayScroll,
          padding: const EdgeInsets.fromLTRB(16, 4, 16, 16),
          itemCount: day.items.length + 1,
          separatorBuilder: (_, _) => const SizedBox(height: 4),
          itemBuilder: (context, i) {
            if (i == day.items.length) {
              return Center(
                child: Padding(
                  padding: const EdgeInsets.all(12),
                  child: Text(
                    day.universe > 0
                        ? '— 全平台估计当日发书 ~${day.universe} 本 · 内置库 ${day.total} 本，按收藏排序 —'
                        : '— 内置库 ${day.total} 本，按收藏排序 —',
                    style: TextStyle(
                        fontSize: 11, color: scheme.onSurfaceVariant),
                  ),
                ),
              );
            }
            final it = day.items[i];
            return _CalendarBookRow(
                item: it, onOpen: () => context.push('/book/${it.nid}'));
          },
        ),
        if (_showTop)
          Positioned(
            right: 16,
            bottom: 24,
            child: BackToTop(
              onTap: () => _dayScroll.animateTo(
                0,
                duration: const Duration(milliseconds: 400),
                curve: Curves.easeOut,
              ),
            ),
          ),
      ],
    );
  }

  Widget _miniCover(CalendarItem it) {
    final coverUrl = it.coverUrl;
    if (coverUrl == null || coverUrl.isEmpty) {
      return defaultCover(it.nid);
    }
    return coverImage(coverImageUrl(coverUrl) == null ? null : coverUrl, it.nid);
  }

  Widget _empty(String msg) {
    final scheme = Theme.of(context).colorScheme;
    return Center(
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(
            Icons.event_available_outlined,
            size: 56,
            color: scheme.onSurfaceVariant.withValues(alpha: .5),
          ),
          const SizedBox(height: 12),
          Text(
            msg,
            style: TextStyle(fontSize: 13, color: scheme.onSurfaceVariant),
          ),
        ],
      ),
    );
  }
}

/// 日视图行卡：封面 + 标题/作者/题材 + 收藏数 + est_conf 精度徽标。
class _CalendarBookRow extends StatelessWidget {
  final CalendarItem item;
  final VoidCallback onOpen;

  const _CalendarBookRow({required this.item, required this.onOpen});

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final coverUrl = item.coverUrl;
    final hasCover = coverUrl != null && coverUrl.isNotEmpty;
    final sub = [
      item.author,
      if (item.genre != null && item.genre!.isNotEmpty) item.genre!,
    ].join('  ');
    return InkWell(
      onTap: onOpen,
      borderRadius: BorderRadius.circular(12),
      child: Container(
        margin: const EdgeInsets.symmetric(vertical: 3),
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
                  Text(
                    item.title,
                    maxLines: 2,
                    overflow: TextOverflow.ellipsis,
                    style: const TextStyle(
                        fontSize: 13, fontWeight: FontWeight.w600),
                  ),
                  const SizedBox(height: 3),
                  Text(
                    sub,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: TextStyle(fontSize: 11, color: scheme.secondary),
                  ),
                  const SizedBox(height: 6),
                  Row(
                    children: [
                      Icon(MetricIcons.favs,
                          size: 13, color: scheme.onSurfaceVariant),
                      const SizedBox(width: 3),
                      Text(
                        BookRowTile.wan(item.favs),
                        style: TextStyle(
                            fontSize: 11,
                            color: scheme.onSurfaceVariant),
                      ),
                      const SizedBox(width: 10),
                      _ConfBadge(conf: item.estConf),
                    ],
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}

/// est_conf 精度徽标（docs/14 §1.3）：exact = 官方 addTime（精确）；
/// high/mid = 内插估计（中位误差 2 天）→「估计」。low 档不出现在日/周视图。
class _ConfBadge extends StatelessWidget {
  final String conf;

  const _ConfBadge({required this.conf});

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final exact = conf == 'exact';
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 5, vertical: 1),
      decoration: BoxDecoration(
        color: exact
            ? scheme.primary.withValues(alpha: .12)
            : scheme.onSurface.withValues(alpha: .05),
        borderRadius: BorderRadius.circular(4),
        border: Border.all(
            color: exact
                ? scheme.primary.withValues(alpha: .5)
                : scheme.outline.withValues(alpha: .3)),
      ),
      child: Text(
        exact ? '精确' : '估计',
        style: TextStyle(
            fontSize: 10,
            color: exact ? scheme.primary : scheme.onSurfaceVariant),
      ),
    );
  }
}

/// 二维年月选择器（BottomSheet）：点年即时切换（保留月，sheet 不关，可继续
/// 点月）；点月跳转并关闭。年范围 = 右删失边界（genMin..genMax），无需禁用态。
class _YearMonthSheet extends StatefulWidget {
  final int minYear;
  final int maxYear;
  final int initialYear;
  final int initialMonth;
  final ValueChanged<int> onYear;
  final ValueChanged<int> onMonth;

  const _YearMonthSheet({
    required this.minYear,
    required this.maxYear,
    required this.initialYear,
    required this.initialMonth,
    required this.onYear,
    required this.onMonth,
  });

  @override
  State<_YearMonthSheet> createState() => _YearMonthSheetState();
}

class _YearMonthSheetState extends State<_YearMonthSheet> {
  late int _year = widget.initialYear;

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
                  '选择年月',
                  style: TextStyle(
                      fontSize: 15,
                      fontWeight: FontWeight.w600,
                      fontFamily: StrataTokens.serif),
                ),
                const Spacer(),
                Text(
                  '点年即时切换 · 点月跳转',
                  style: TextStyle(
                      fontSize: 11, color: scheme.onSurfaceVariant),
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
                          onSelected: (_) {
                            setState(() => _year = y);
                            widget.onYear(y);
                          },
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
                    selected: widget.initialMonth == m,
                    showCheckmark: false,
                    onSelected: (_) {
                      widget.onMonth(m);
                      Navigator.of(context).pop();
                    },
                  ),
              ],
            ),
          ],
        ),
      ),
    );
  }
}
