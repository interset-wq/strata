import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../core/providers.dart';
import '../widgets/back_to_top.dart';
import '../widgets/contest_row_card.dart';

/// 赛事档案列表（docs/contest-display-in-app.md 形态一）：本地零请求视图。
///
/// 2026-11-22 改版（用户裁定）：榜单 tab 同款切换——春季 / x征 / 秋季 /
/// 冬季 / 其他 五个 tab，与引擎 series 一一对应；「其他」tab 只含主题类
/// （group.lane 为空）——对话线归档放首页对话区、IP 线归档放 IP 区
/// （lane 分类在引擎侧）。组序沿用引擎返回：各 tab 按开赛年份增序
/// （官方元数据年份优先，缺失落在库年份下限），稳定排序。
///
/// 数据源 = seed 内置库的 contest 字段标注（平台标注，非官方全量参赛
/// 规模——库外规模见档案页「查看官方清单」）。
class ContestListPage extends ConsumerStatefulWidget {
  const ContestListPage({super.key, this.initialTab});
  final String? initialTab;

  @override
  ConsumerState<ContestListPage> createState() => _ContestListPageState();
}

class _ContestListPageState extends ConsumerState<ContestListPage>
    with SingleTickerProviderStateMixin {
  // tab 顺序 = 用户裁定（春 / x征 / 秋 / 冬 / 其他），与引擎 seriesOrder
  // 一致；series 值即过滤键。
  static const _tabs = [
    ('spring', '春季'),
    ('x', 'x征'),
    ('autumn', '秋季'),
    ('winter', '冬季'),
    ('other', '其他'),
  ];

  late final TabController _tabCtrl;
  final _scroll = ScrollController();
  bool _showTop = false;

  @override
  void initState() {
    super.initState();
    _tabCtrl = TabController(length: _tabs.length, vsync: this);
    // 详情页比赛卡片跳转：按 series 定位到对应分类 tab（用户 2026-11-25）。
    final idx = _tabs.indexWhere((t) => t.$1 == widget.initialTab);
    if (idx > 0) _tabCtrl.index = idx;
    _tabCtrl.addListener(() => setState(() {}));
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
        title: const Text('赛事档案'),
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
              // 「其他」tab 只含主题类（lane 为空）：对话线/IP 线归档已
              // 迁往首页对话区与 IP 区（2026-11-22 用户裁定）。
              final items = list
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
                  Padding(
                    padding: const EdgeInsets.fromLTRB(16, 12, 16, 4),
                    child: Text(
                      '计数 = 本地内置库中标注该赛事的作品；官方参赛规模见'
                      '档案页「查看官方清单」。',
                      style: TextStyle(
                          fontSize: 11, color: scheme.onSurfaceVariant),
                    ),
                  ),
                  for (final g in items) ContestRowCard(group: g),
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
}
