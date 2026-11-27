import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../core/format.dart';
import '../core/providers.dart';
import '../data/api/strata_api.dart';
import '../widgets/back_to_top.dart';
import '../widgets/contest_row_card.dart';

/// 赛事档案列表（docs/contest-display-in-app.md 形态一）：本地零请求视图。
///
/// 2026-11-22 改版（用户裁定）：榜单 tab 同款切换——春季 / x征 / 秋季 /
/// 冬季 / 其他 五个 tab，与引擎 series 一一对应；「其他」tab 只含主题类
/// （group.lane 为空）——对话线归档放首页对话区、IP 线归档放 IP 区
/// （lane 分类在引擎侧）。
///
/// 2026-11-26 改版（用户认可）：排序改「最近一届在前」（引擎侧），主数换
/// 官方清单条数、在库退为次数，顶部口径说明删除；X征 tab 加年代轨；
/// 首页对话区入口带 `?lane=dialogue` 进对话线归档（`initialLane`），
/// 否则这些档案在 app 里没有任何入口。组序沿用引擎返回。
class ContestListPage extends ConsumerStatefulWidget {
  const ContestListPage({super.key, this.initialTab, this.initialLane});
  final String? initialTab;

  /// 'dialogue' / 'ip'：从首页对应内容区进来时只看这一条线（null = 不限）。
  final String? initialLane;

  @override
  ConsumerState<ContestListPage> createState() => _ContestListPageState();
}

class _ContestListPageState extends ConsumerState<ContestListPage>
    with SingleTickerProviderStateMixin {
  // tab 顺序 = 用户裁定（春 / x征 / 秋 / 冬 / 其他），与引擎 seriesOrder
  // 一致；series 值即过滤键。
  static const _tabs = [
    ('spring', '春季'),
    ('x', 'X征'),
    ('autumn', '秋季'),
    ('winter', '冬季'),
    ('other', '其他'),
  ];
  static const _laneTitles = {'dialogue': '对话线归档', 'ip': 'IP 联动归档'};

  late final TabController _tabCtrl;
  String? _lane;
  final _scroll = ScrollController();
  bool _showTop = false;

  @override
  void initState() {
    super.initState();
    _lane = widget.initialLane;
    _tabCtrl = TabController(length: _tabs.length, vsync: this);
    // 详情页比赛卡片跳转：按 series 定位到对应分类 tab（用户 2026-11-25）；
    // 首页对话区跳转带 lane——对话线只挂在「其他」系列上。
    final idx = _tabs.indexWhere((t) => t.$1 == widget.initialTab);
    if (_lane != null) {
      _tabCtrl.index = _tabs.indexWhere((t) => t.$1 == 'other');
    } else if (idx > 0) {
      _tabCtrl.index = idx;
    }
    _tabCtrl.addListener(() {
      if (!_tabCtrl.indexIsChanging) return;
      // 手动换 tab 即退出单线视图（lane 只属于「其他」系列）。
      setState(() => _lane = null);
    });
    _scroll.addListener(() {
      final show = _scroll.hasClients && _scroll.offset > 500;
      if (show != _showTop) setState(() => _showTop = show);
    });
  }

  @override
  void dispose() {
    _tabCtrl.dispose();
    _scroll.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final groups = ref.watch(contestArchiveProvider);
    return Scaffold(
      appBar: AppBar(
        title: Text(_lane == null ? '赛事档案' : _laneTitles[_lane]!),
        actions: [
          // 萌神大赛纳入比赛归档（用户 2026-11-25）：入口常驻归档页头部。
          IconButton(
            icon: const Icon(Icons.emoji_events),
            tooltip: '萌神获奖',
            onPressed: () => context.push('/moe-goddess'),
          ),
        ],
        bottom: TabBar(
          controller: _tabCtrl,
          labelColor: scheme.primary,
          unselectedLabelColor: scheme.onSurfaceVariant,
          indicatorColor: scheme.primary,
          dividerColor: Colors.transparent,
          labelStyle: const TextStyle(
            fontSize: 13.5,
            fontWeight: FontWeight.w600,
          ),
          unselectedLabelStyle: const TextStyle(fontSize: 13.5),
          tabs: [for (final (_, label) in _tabs) Tab(text: label)],
        ),
      ),
      body: Stack(
        children: [
          groups.when(
            loading: () => const Center(child: CircularProgressIndicator()),
            error: (e, _) => Center(
              child: Padding(
                padding: const EdgeInsets.all(24),
                child: Text(
                  '赛事档案加载失败：$e',
                  style: TextStyle(
                      fontSize: 13, color: scheme.onSurfaceVariant),
                ),
              ),
            ),
            data: (list) {
              final series = _tabs[_tabCtrl.index].$1;
              // lane 视图：只看这一条线（首页对话区入口）。否则「其他」tab
              // 只含主题类（lane 为空）——对话线/IP 线归档各有自己的入口
              // （2026-11-22 用户裁定）。
              final items = _lane != null
                  ? list.where((g) => g.lane == _lane).toList()
                  : list
                      .where((g) =>
                          g.series == series &&
                          (series != 'other' || g.lane.isEmpty))
                      .toList();
              if (items.isEmpty) {
                return Center(
                  child: Text(
                    '该分类暂无档案',
                    style: TextStyle(color: scheme.onSurfaceVariant),
                  ),
                );
              }
              return ListView(
                controller: _scroll,
                padding: const EdgeInsets.only(bottom: 24),
                children: [
                  _columns(context, scheme, rail: series == 'x'),
                  for (final g in items)
                    ContestRowCard(group: g, yearRail: series == 'x'),
                  _summary(context, scheme, list, items, series),
                ],
              );
            },
          ),
          if (_showTop)
            Positioned(
              right: 16,
              bottom: 24,
              child: BackToTop(
                onTap: () => _scroll.animateTo(
                  0,
                  duration: const Duration(milliseconds: 400),
                  curve: Curves.easeOut,
                ),
              ),
            ),
        ],
      ),
    );
  }

  /// 列头：与 [ContestRowCard] 同一套列宽，数字才落得齐。「年份」只在
  /// X征 tab 出现（那一列就是左轨）。
  Widget _columns(BuildContext context, ColorScheme scheme,
      {required bool rail}) {
    // 对比度修正（2026-11-27 用户四次反馈）：表头原 outline 色（#E6DFCE）
    // 在米色 bg 上几乎隐形——「在库」列标签是用户看不清的主体。
    final label = TextStyle(fontSize: 10.5, color: scheme.onSurfaceVariant);
    return Padding(
      padding: const EdgeInsets.fromLTRB(16, 10, 16, 0),
      child: Row(
        children: [
          if (rail)
            SizedBox(width: ContestRowCard.colYear, child: Text('年份', style: label)),
          const Spacer(),
          SizedBox(
            width: ContestRowCard.colLib,
            child: Text('在库', textAlign: TextAlign.end, style: label),
          ),
          const SizedBox(width: 10),
          SizedBox(
            width: ContestRowCard.colOfficial,
            child: Text('官方清单', textAlign: TextAlign.end, style: label),
          ),
          const SizedBox(width: 18),
        ],
      ),
    );
  }

  /// 尾部合计（取代旧版顶部的口径说明行）：本 tab 届数 + 官方清单条数合计
  /// + 本地在库本数。缺清单的届数如实点出，不把部分求和写成全量；获奖
  /// 事件（只有获奖名单、没有参赛清单）单独点名，名额不进「条」的合计。
  Widget _summary(BuildContext context, ColorScheme scheme,
      List<ContestGroup> all, List<ContestGroup> items, String series) {
    final known = items.where((g) => g.rosterTotal != null).toList();
    final off = known.fold<int>(0, (a, g) => a + g.rosterTotal!);
    final inst = items.fold<int>(0, (a, g) => a + g.count);
    final awardOnly = items.where((g) => g.listKind == 'award').length;
    final missing = items.length - known.length - awardOnly;
    final dialogue = all.where((g) => g.lane == 'dialogue').length;
    final ip = all.where((g) => g.lane == 'ip').length;
    final text = StringBuffer('本分类共 ${items.length} 届 · 官方清单合计 '
        '${fmtCount(off)} 条 · 本地在库 ${fmtCount(inst)} 本');
    if (missing > 0 || awardOnly > 0) {
      final why = <String>[
        if (awardOnly > 0) '$awardOnly 届只有获奖名单',
        if (missing > 0) '$missing 届无清单接口',
      ];
      text.write('（${why.join('、')}，未计入）');
    }
    if (_lane == null && series == 'other') {
      text.write('\n对话线 $dialogue 项在首页对话区，IP 联动 $ip 项在首页 IP 区。');
    }
    return Padding(
      padding: const EdgeInsets.fromLTRB(16, 14, 16, 0),
      child: Text(
        text.toString(),
        style: TextStyle(fontSize: 11, color: scheme.onSurfaceVariant),
      ),
    );
  }
}
