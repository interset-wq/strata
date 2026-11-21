import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../core/providers.dart';
import '../data/api/strata_api.dart';
import '../widgets/back_to_top.dart';

/// 赛事档案列表（docs/contest-display-in-app.md 形态一）：本地零请求视图。
///
/// 数据源 = seed 内置库的 contest 字段标注（平台标注，非官方全量参赛规模——
/// 库外规模与获奖属 P1 清单 API）；官方日期来自引擎内嵌的用户核实静态表
///（analysis/references/contest-editions.md），缺失时只显届次/年份，不编造。
class ContestListPage extends StatefulWidget {
  const ContestListPage({super.key});

  @override
  State<ContestListPage> createState() => _ContestListPageState();
}

class _ContestListPageState extends State<ContestListPage> {
  final _scroll = ScrollController();
  bool _showTop = false;

  @override
  void initState() {
    super.initState();
    _scroll.addListener(() {
      final show = _scroll.hasClients && _scroll.offset > 500;
      if (show != _showTop) setState(() => _showTop = show);
    });
  }

  @override
  void dispose() {
    _scroll.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('赛事档案')),
      body: Stack(
        children: [
          _Body(scroll: _scroll),
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

class _Body extends ConsumerWidget {
  final ScrollController scroll;

  const _Body({required this.scroll});

  static const _seriesLabels = {
    'x': 'N征系列',
    'winter': '冬季征文',
    'spring': '春季征文',
    'autumn': '秋季征文',
    'other': '其他赛事',
  };
  static const _seriesOrder = ['x', 'winter', 'spring', 'autumn', 'other'];

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final scheme = Theme.of(context).colorScheme;
    final groups = ref.watch(contestArchiveProvider);
    return groups.when(
      loading: () => const Center(child: CircularProgressIndicator()),
      error: (e, _) => Center(
        child: Padding(
          padding: const EdgeInsets.all(24),
          child: Text(
            '赛事档案加载失败：$e',
            style: TextStyle(fontSize: 13, color: scheme.onSurfaceVariant),
          ),
        ),
      ),
      data: (list) {
        final bySeries = {for (final s in _seriesOrder) s: <ContestGroup>[]};
        for (final g in list) {
          bySeries.putIfAbsent(g.series, () => <ContestGroup>[]).add(g);
        }
        return ListView(
          controller: scroll,
          padding: const EdgeInsets.only(bottom: 24),
          children: [
            Padding(
              padding: const EdgeInsets.fromLTRB(16, 12, 16, 4),
              child: Text(
                '本地内置库中标注过该赛事的作品；官方参赛规模与获奖'
                '信息将在清单 API（P1）接入后补齐。',
                style: TextStyle(fontSize: 11, color: scheme.onSurfaceVariant),
              ),
            ),
            for (final s in _seriesOrder) ...[
              if (bySeries[s]!.isNotEmpty)
                Padding(
                  padding: const EdgeInsets.fromLTRB(16, 14, 16, 2),
                  child: Text(
                    _seriesLabels[s]!,
                    style: TextStyle(
                      fontSize: 12,
                      fontWeight: FontWeight.w600,
                      color: scheme.secondary,
                    ),
                  ),
                ),
              for (final g in bySeries[s]!) _ContestRow(group: g),
            ],
          ],
        );
      },
    );
  }
}

class _ContestRow extends StatelessWidget {
  final ContestGroup group;

  const _ContestRow({required this.group});

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
