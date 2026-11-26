import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:url_launcher/url_launcher.dart';
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
/// UI 标「入库日期（估计）」；low 档只入月视图（引擎侧过滤）；
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
  int _genMin = 2007, _genMax = 2026; // manifest 右删失边界（initState 加载）

  final _dayScroll = ScrollController();
  bool _showTop = false;

  DateTime get _minDate => DateTime(_genMin, 1, 1);
  DateTime get _maxDate => DateTime(_genMax, 12, 31);

  DateTime _mondayOf(DateTime d) =>
      d.subtract(Duration(days: (d.weekday - DateTime.monday)));

  // 周一开头周的周六 = VIP 期数键（§7.5：只有周六有数据）。
  DateTime _saturdayOf(DateTime d) => _mondayOf(d).add(const Duration(days: 5));

  String _pad(int n) => n.toString().padLeft(2, '0');

  String _anchor() {
    final f = _focus;
    switch (_granularity) {
      case 'month':
        return '${f.year}-${_pad(f.month)}-01';
      case 'vip':
        final s = _saturdayOf(f);
        return '${s.year}${_pad(s.month)}${_pad(s.day)}';
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
      case 'vip':
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
      case 'vip':
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
        case 'vip':
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

  // 双列滚轮选年月（用户 2026-11-25 定）：CupertinoPicker 拖动即时生效
  //（年列与月列联动，sheet 不关）；日历只需年月精度，不用完整日历选择器。
  Future<void> _pickDate() async {
    final scheme = Theme.of(context).colorScheme;
    await showModalBottomSheet<void>(
      context: context,
      backgroundColor: scheme.surface,
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(20)),
      ),
      builder: (_) => _YearMonthWheel(
        minYear: _genMin,
        maxYear: _genMax,
        initialYear: _focus.year,
        initialMonth: _focus.month,
        onChanged: (y, m) {
          if (mounted) {
            setState(() => _focus = DateTime(y, m, 1));
          }
        },
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
      // 失败保留默认边界（当前种子内容上界 2007..2026）
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
      case 'vip':
        final s = _saturdayOf(f);
        return '${s.month}月${s.day}日 期（周六）';
      default:
        return '${f.month}月${f.day}日（周${_weekdays[f.weekday - 1]}）';
    }
  }

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final isVip = _granularity == 'vip';
    final data = isVip
        ? null
        : ref.watch(
            calendarProvider(
              CalendarQuery(
                granularity: _granularity,
                anchor: _anchor(),
                perCell: _granularity == 'day' ? 50 : 3,
              ),
            ),
          );

    return Scaffold(
      appBar: AppBar(
        title: const Text('发书日历'),
        actions: [
          IconButton(
            icon: const Icon(Icons.insights),
            tooltip: '世代探索',
            onPressed: () => context.push('/eras-explorer'),
          ),
        ],
      ),
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
                      fontSize: 11,
                      color: scheme.onSurfaceVariant,
                    ),
                  ),
                  const SizedBox(height: 2),
                  Text(
                    '定年 = nid 锚点内插（中位误差 2 天）；入库日期为估计值，非首章发布日期',
                    style: TextStyle(
                      fontSize: 11,
                      color: scheme.onSurfaceVariant,
                    ),
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
                  ButtonSegment(value: 'vip', label: Text('VIP')),
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
                      onTap: _pickDate,
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
                                fontFamily: StrataTokens.serif,
                              ),
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
              child: isVip
                  ? _buildVip(scheme)
                  : data!.when(
                      loading: () =>
                          const Center(child: CircularProgressIndicator()),
                      error: (e, _) => Center(child: Text('日历加载失败：$e')),
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
                      fontSize: 11,
                      color: scheme.onSurfaceVariant,
                    ),
                  ),
                ),
            ],
          ),
          const SizedBox(height: 6),
          Expanded(
            child: GridView.builder(
              gridDelegate: const SliverGridDelegateWithFixedCrossAxisCount(
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
                              color: scheme.outline.withValues(alpha: .35),
                            )
                          : null,
                    ),
                    child: Column(
                      mainAxisAlignment: MainAxisAlignment.center,
                      children: [
                        Text(
                          '$dayNum',
                          style: TextStyle(
                            fontSize: 13,
                            fontWeight: has ? FontWeight.w700 : FontWeight.w400,
                            color: has
                                ? scheme.onSurface
                                : scheme.onSurfaceVariant.withValues(alpha: .7),
                          ),
                        ),
                        if (has)
                          Text(
                            '~${c.universe}',
                            style: TextStyle(
                              fontSize: 11,
                              fontWeight: FontWeight.w700,
                              color: scheme.primary,
                            ),
                          ),
                        if (has)
                          Text(
                            '${c.total}内置',
                            style: TextStyle(
                              fontSize: 9,
                              color: scheme.onSurfaceVariant,
                            ),
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
              style: TextStyle(fontSize: 11, color: scheme.onSurfaceVariant),
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
              border: Border.all(color: scheme.outline.withValues(alpha: .25)),
            ),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  children: [
                    Text(
                      '${d.month}月${d.day}日',
                      style: const TextStyle(
                        fontSize: 14,
                        fontWeight: FontWeight.w600,
                      ),
                    ),
                    const SizedBox(width: 6),
                    Text(
                      '（周${_weekdays[d.weekday - 1]}）',
                      style: TextStyle(
                        fontSize: 12,
                        color: scheme.onSurfaceVariant,
                      ),
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
                          color: scheme.primary,
                        ),
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
                                style: const TextStyle(fontSize: 12),
                              ),
                              const SizedBox(height: 2),
                              Text(
                                it.author,
                                maxLines: 1,
                                overflow: TextOverflow.ellipsis,
                                style: TextStyle(
                                  fontSize: 10,
                                  color: scheme.onSurfaceVariant,
                                ),
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
      return _empty('内置库当日无可点击作品（全平台估计 ~${day.universe} 本）');
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
                      fontSize: 11,
                      color: scheme.onSurfaceVariant,
                    ),
                  ),
                ),
              );
            }
            final it = day.items[i];
            return _CalendarBookRow(
              item: it,
              onOpen: () => context.push('/book/${it.nid}'),
            );
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

  // ── VIP 视图（docs/14 §1.5）：官方每周签约升 VIP 推荐期次（在线层）。
  // 口径红线（sfacg-endpoints §7.5）：date 是预定签约升 VIP 周，不是首发日，
  // 与 est_date「入库日期（估计）」分列展示、不得互推。─────────────────

  Widget _buildVip(ColorScheme scheme) {
    final sat = _saturdayOf(_focus);
    final key = '${sat.year}${_pad(sat.month)}${_pad(sat.day)}';
    final data = ref.watch(preorderProvider(key));
    return data.when(
      loading: () => const Center(child: CircularProgressIndicator()),
      error: (e, _) => Center(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Text(
              'VIP 期次加载失败：$e',
              style: TextStyle(fontSize: 12, color: scheme.error),
            ),
            const SizedBox(height: 8),
            TextButton(
              onPressed: () => ref.invalidate(preorderProvider(key)),
              child: const Text('重试'),
            ),
          ],
        ),
      ),
      data: (resp) {
        if (resp.items.isEmpty) {
          return _empty('该周没有签约升 VIP 预告（官方编辑精选期次）');
        }
        return ListView.separated(
          padding: const EdgeInsets.fromLTRB(16, 4, 16, 16),
          itemCount: resp.items.length + 1,
          separatorBuilder: (_, _) => const SizedBox(height: 4),
          itemBuilder: (context, i) {
            if (i == resp.items.length) {
              // 官方签约升 VIP 预告 H5（§7.5）：给出来源页防"数据是编的"。
              final url =
                  'https://pages.sfacg.com/h5/general/preorder-${resp.date}.html?type=android';
              return Padding(
                padding: const EdgeInsets.all(12),
                child: Column(
                  children: [
                    Text(
                      '— ${resp.date} 期 · 官方编辑精选 · 预定签约升 VIP 周（在线数据，非首发/入库日）—',
                      textAlign: TextAlign.center,
                      style: TextStyle(
                        fontSize: 11,
                        color: scheme.onSurfaceVariant,
                      ),
                    ),
                    TextButton.icon(
                      onPressed: () => launchUrl(
                        Uri.parse(url),
                        mode: LaunchMode.externalApplication,
                      ),
                      icon: const Icon(Icons.open_in_new, size: 14),
                      label: const Text(
                        '打开官方签约升 VIP 预告页',
                        style: TextStyle(fontSize: 11),
                      ),
                    ),
                  ],
                ),
              );
            }
            final it = resp.items[i];
            return _PreorderRow(
              item: it,
              onOpen: () async {
                if (!it.inSeed) {
                  // 库外书自动收录：rank-seed 预写标题/封面（纯本地写），
                  // 进详情页后 words==null 自动后台 refresh 补全（docs/08）。
                  try {
                    final handle = await ref.read(bootProvider.future);
                    await handle.api.rankSeed(
                      nid: it.nid,
                      title: it.title,
                      coverUrl: it.cover ?? '',
                    );
                  } catch (_) {
                    // 预写失败也进详情：详情页会自行报错可重试。
                  }
                }
                if (context.mounted) context.push('/book/${it.nid}');
              },
            );
          },
        );
      },
    );
  }

  Widget _miniCover(CalendarItem it) {
    final coverUrl = it.coverUrl;
    if (coverUrl == null || coverUrl.isEmpty) {
      return defaultCover(it.nid, title: it.title);
    }
    return coverImage(
      coverImageUrl(coverUrl) == null ? null : coverUrl,
      it.nid,
    );
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
                    ? coverImage(coverUrl, item.nid, title: item.title)
                    : defaultCover(item.nid, title: item.title),
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
                      fontSize: 13,
                      fontWeight: FontWeight.w600,
                    ),
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
                      Icon(
                        MetricIcons.favs,
                        size: 13,
                        color: scheme.onSurfaceVariant,
                      ),
                      const SizedBox(width: 3),
                      Text(
                        BookRowTile.wan(item.favs),
                        style: TextStyle(
                          fontSize: 11,
                          color: scheme.onSurfaceVariant,
                        ),
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

/// VIP 签约升卡（docs/14 §1.5）：第一行通用卡（封面+标题+徽标+tags），
/// 第二行完整 intro 容器（官方 <br> 转换行，不截断）；库外书点击先
/// rank-seed 预写收录再进详情页（详情页 words==null 自动 refresh 补全）。
class _PreorderRow extends StatelessWidget {
  final PreorderItem item;
  final VoidCallback onOpen;

  const _PreorderRow({required this.item, required this.onOpen});

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final author = item.inSeed && (item.inLibAuthor?.isNotEmpty ?? false)
        ? item.inLibAuthor!
        : null;
    // 官方 intro 是内嵌 <br> 的 HTML 片段，转真实换行后全文展示。
    final intro = item.intro.replaceAll(RegExp(r'<br\s*/?>'), '\n').trim();
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
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                SizedBox(
                  width: 48,
                  height: 64,
                  child: ClipRRect(
                    borderRadius: BorderRadius.circular(6),
                    child: coverImage(item.cover, item.nid),
                  ),
                ),
                const SizedBox(width: 12),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Row(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Flexible(
                            child: Text(
                              item.title,
                              maxLines: 2,
                              overflow: TextOverflow.ellipsis,
                              style: const TextStyle(
                                fontSize: 13,
                                fontWeight: FontWeight.w600,
                              ),
                            ),
                          ),
                          if (item.isMainPush) ...[
                            const SizedBox(width: 6),
                            const _VipBadge(),
                          ],
                        ],
                      ),
                      if (author != null) ...[
                        const SizedBox(height: 3),
                        Text(
                          author,
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                          style: TextStyle(
                            fontSize: 11,
                            color: scheme.secondary,
                          ),
                        ),
                      ],
                      if (item.tags.isNotEmpty) ...[
                        const SizedBox(height: 3),
                        Text(
                          item.tags.join('  '),
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                          style: TextStyle(
                            fontSize: 10,
                            color: scheme.primary,
                          ),
                        ),
                      ],
                      if (item.inSeed && (item.inLibFavs ?? 0) > 0) ...[
                        const SizedBox(height: 4),
                        Row(
                          children: [
                            Icon(
                              MetricIcons.favs,
                              size: 13,
                              color: scheme.onSurfaceVariant,
                            ),
                            const SizedBox(width: 3),
                            Text(
                              BookRowTile.wan(item.inLibFavs),
                              style: TextStyle(
                                fontSize: 11,
                                color: scheme.onSurfaceVariant,
                              ),
                            ),
                          ],
                        ),
                      ],
                      if (!item.inSeed) ...[
                        const SizedBox(height: 4),
                        Text(
                          '库外作品 · 点击自动收录进详情',
                          style: TextStyle(
                            fontSize: 10,
                            color: scheme.onSurfaceVariant.withValues(
                              alpha: .7,
                            ),
                          ),
                        ),
                      ],
                    ],
                  ),
                ),
              ],
            ),
            if (intro.isNotEmpty) ...[
              const SizedBox(height: 8),
              Container(
                width: double.infinity,
                padding: const EdgeInsets.all(8),
                decoration: BoxDecoration(
                  color: scheme.onSurface.withValues(alpha: .04),
                  borderRadius: BorderRadius.circular(8),
                ),
                child: Text(
                  intro,
                  style: TextStyle(
                    fontSize: 11.5,
                    height: 1.5,
                    color: scheme.onSurface.withValues(alpha: .85),
                  ),
                ),
              ),
            ],
          ],
        ),
      ),
    );
  }
}

/// 主编推荐徽标（isMainPush=true 才显示；无对应 else 形态）。
class _VipBadge extends StatelessWidget {
  const _VipBadge();

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 5, vertical: 1),
      decoration: BoxDecoration(
        color: scheme.primary.withValues(alpha: .12),
        borderRadius: BorderRadius.circular(4),
        border: Border.all(color: scheme.primary.withValues(alpha: .5)),
      ),
      child: Text(
        '主编推荐',
        style: TextStyle(fontSize: 10, color: scheme.primary),
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
              : scheme.outline.withValues(alpha: .3),
        ),
      ),
      child: Text(
        exact ? '精确' : '估计',
        style: TextStyle(
          fontSize: 10,
          color: exact ? scheme.primary : scheme.onSurfaceVariant,
        ),
      ),
    );
  }
}

/// 双列滚轮选年月（CupertinoPicker）：拖动即时切换（年月联动，sheet 不
/// 关）；年范围 = 右删失边界（genMin..genMax），无需禁用态。
class _YearMonthWheel extends StatefulWidget {
  final int minYear;
  final int maxYear;
  final int initialYear;
  final int initialMonth;
  final void Function(int year, int month) onChanged;

  const _YearMonthWheel({
    required this.minYear,
    required this.maxYear,
    required this.initialYear,
    required this.initialMonth,
    required this.onChanged,
  });

  @override
  State<_YearMonthWheel> createState() => _YearMonthWheelState();
}

class _YearMonthWheelState extends State<_YearMonthWheel> {
  late final FixedExtentScrollController _year = FixedExtentScrollController(
    initialItem: widget.initialYear - minYear,
  );
  late final FixedExtentScrollController _month = FixedExtentScrollController(
    initialItem: widget.initialMonth - 1,
  );
  late int _yearItem = _year.selectedItem;
  late int _monthItem = _month.selectedItem;

  int get minYear => widget.minYear;

  @override
  void dispose() {
    _year.dispose();
    _month.dispose();
    super.dispose();
  }

  void _emit() => widget.onChanged(minYear + _yearItem, _monthItem + 1);

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final itemStyle = TextStyle(fontSize: 17, color: scheme.onSurface);
    return SafeArea(
      child: SizedBox(
        height: 210,
        child: Row(
          children: [
            Expanded(
              child: CupertinoPicker(
                scrollController: _year,
                itemExtent: 42,
                useMagnifier: true,
                magnification: 1.08,
                onSelectedItemChanged: (i) {
                  _yearItem = i;
                  _emit();
                },
                children: [
                  for (int y = widget.minYear; y <= widget.maxYear; y++)
                    // 子项高度必须等于 itemExtent，否则选中项相对高亮中央
                    // 逐项累积偏移（真机复现的错位根因）。
                    SizedBox(
                      height: 42,
                      child: Center(child: Text('$y', style: itemStyle)),
                    ),
                ],
              ),
            ),
            Expanded(
              child: CupertinoPicker(
                scrollController: _month,
                itemExtent: 42,
                useMagnifier: true,
                magnification: 1.08,
                onSelectedItemChanged: (i) {
                  _monthItem = i;
                  _emit();
                },
                children: [
                  for (int m = 1; m <= 12; m++)
                    SizedBox(
                      height: 42,
                      child: Center(child: Text('$m 月', style: itemStyle)),
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
