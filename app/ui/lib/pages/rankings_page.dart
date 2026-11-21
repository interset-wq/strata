import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../core/providers.dart';
import '../data/api/strata_api.dart';
import '../widgets/book_row_card.dart';

/// Classic 六榜（docs/12 展示列）：顶部横滑 tab 导航，平台累计值排序。
const _boards = [
  ('recommend', '点赞榜'),
  ('popular', '人气榜'),
  ('favs', '收藏榜'),
  ('new', '新书榜'),
  ('finish', '完结榜'),
  ('words', '字数榜'),
];

final _boardProvider = FutureProvider.autoDispose
    .family<List<RankItem>, (String, int, int)>((ref, arg) async {
  final handle = await ref.watch(bootProvider.future);
  return handle.api.rankingBoard(
      kind: arg.$1, year: arg.$2, limit: 50, offset: arg.$3);
});

/// 榜单页：顶部六榜 tab + 年份快速切换（demo 原下拉风格）。
/// 无页面标题、无模式行；列表与其他页面共用统一行卡（BookRowCard）。
/// 新书榜不显示年份行（新书定义即最新一代）。
class RankingsPage extends ConsumerStatefulWidget {
  const RankingsPage({super.key});

  @override
  ConsumerState<RankingsPage> createState() => _RankingsPageState();
}

class _RankingsPageState extends ConsumerState<RankingsPage>
    with SingleTickerProviderStateMixin {
  String _kind = 'recommend';
  int _year = 2025;
  late final TabController _tabs;
  final _scroll = ScrollController();
  bool _showTop = false;

  @override
  void initState() {
    super.initState();
    _tabs = TabController(length: _boards.length, vsync: this);
    _tabs.addListener(() {
      final i = _tabs.index;
      if (i >= 0 && _boards[i].$1 != _kind) setState(() => _kind = _boards[i].$1);
    });
    _scroll.addListener(() {
      final show = _scroll.offset > 500;
      if (show != _showTop) setState(() => _showTop = show);
    });
  }

  @override
  void dispose() {
    _tabs.dispose();
    _scroll.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final meta = ref.watch(metaProvider);
    final genMax = meta.value?.manifest.genMax ?? 2025;
    final genMin = meta.value?.manifest.genMin ?? 2007;
    // meta 加载后校准默认年份
    if (meta.value != null && _year > genMax) {
      _year = genMax;
    }

    return Scaffold(
      appBar: AppBar(
        toolbarHeight: 44,
        title: TabBar(
          controller: _tabs,
          isScrollable: true,
          tabAlignment: TabAlignment.start,
          labelColor: scheme.primary,
          unselectedLabelColor: scheme.onSurfaceVariant,
          indicatorColor: scheme.primary,
          dividerColor: Colors.transparent,
          labelStyle:
              const TextStyle(fontSize: 14, fontWeight: FontWeight.w600),
          unselectedLabelStyle: const TextStyle(fontSize: 14),
          tabs: [
            for (final (_, label) in _boards) Tab(text: label),
          ],
        ),
      ),
      body: Column(
        children: [
          // 年份快速切换（demo 原下拉风格）；新书榜不显示
          if (_kind != 'new')
            Padding(
              padding: const EdgeInsets.fromLTRB(16, 6, 16, 0),
              child: Row(
                children: [
                  DropdownButton<int>(
                    value: _year.clamp(genMin, genMax),
                    underline: const SizedBox.shrink(),
                    items: [
                      for (int y = genMax; y >= genMin; y--)
                        DropdownMenuItem(
                            value: y,
                            child: Text('$y',
                                style: const TextStyle(fontSize: 13))),
                    ],
                    onChanged: (v) {
                      if (v == null) return;
                      setState(() => _year = v);
                      if (_scroll.hasClients) _scroll.jumpTo(0);
                    },
                  ),
                  const Spacer(),
                  Text('按 $_year 定年（$genMin–$genMax）',
                      style: TextStyle(
                          fontSize: 11,
                          color: scheme.onSurfaceVariant.withValues(alpha: .7))),
                ],
              ),
            ),
          // 官方榜单入口（docs/sfacg-live-ranks.md）：本页是站内口径（累计值
          // 分位），官方榜单是平台当期口径，两个来源分开导航。
          Padding(
            padding: const EdgeInsets.fromLTRB(16, 6, 16, 10),
            child: Card(
              clipBehavior: Clip.antiAlias,
              child: InkWell(
                onTap: () => context.push('/official-ranks'),
                child: Padding(
                  padding: const EdgeInsets.symmetric(
                      horizontal: 14, vertical: 10),
                  child: Row(
                    children: [
                      Icon(Icons.leaderboard_outlined,
                          size: 18, color: scheme.primary),
                      const SizedBox(width: 10),
                      Expanded(
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Text('官方榜单',
                                style: const TextStyle(
                                    fontSize: 13,
                                    fontWeight: FontWeight.w600)),
                            const SizedBox(height: 1),
                            Text('SFACG 官方三来源：月榜库（2013-03 起任意月）/ PC 当期四榜 / 移动热销榜',
                                style: TextStyle(
                                    fontSize: 11,
                                    color: scheme.onSurfaceVariant)),
                          ],
                        ),
                      ),
                      Icon(Icons.chevron_right,
                          size: 18, color: scheme.onSurfaceVariant),
                    ],
                  ),
                ),
              ),
            ),
          ),
          Expanded(
            child: Stack(
              children: [
                _BoardList(
                    key: ValueKey('$_kind-$_year'),
                    kind: _kind,
                    year: _year,
                    scroll: _scroll),
                if (_showTop)
                  Positioned(
                    right: 10,
                    bottom: 10,
                    child: _BackToTop(onTap: () => _scroll.animateTo(0,
                        duration: const Duration(milliseconds: 400),
                        curve: Curves.easeOut)),
                  ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class _BoardList extends ConsumerWidget {
  final String kind;
  final int year;
  final ScrollController scroll;

  const _BoardList(
      {super.key, required this.kind, required this.year, required this.scroll});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final items = ref.watch(_boardProvider((kind, year, 0)));
    final scheme = Theme.of(context).colorScheme;
    return items.when(
      loading: () => const Center(child: CircularProgressIndicator()),
      error: (e, _) => Padding(
          padding: const EdgeInsets.all(16), child: Text('加载失败：$e')),
      data: (list) => list.isEmpty
          ? const Center(child: Text('该年份下无种子书目'))
          : ListView.builder(
              controller: scroll,
              padding: const EdgeInsets.fromLTRB(14, 14, 14, 60),
              itemCount: list.length + 1,
              itemBuilder: (context, i) {
                if (i == list.length) {
                  return Padding(
                    padding: const EdgeInsets.only(top: 6),
                    child: Text('上滑加载更多 · 平台累计值，老书占优',
                        textAlign: TextAlign.center,
                        style: TextStyle(
                            fontSize: 11, color: scheme.onSurfaceVariant)),
                  );
                }
                return BookRowCard(item: list[i]);
              },
            ),
    );
  }
}

class _BackToTop extends StatelessWidget {
  final VoidCallback onTap;

  const _BackToTop({required this.onTap});

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return Material(
      color: scheme.surface,
      borderRadius: BorderRadius.circular(20),
      elevation: 3,
      child: InkWell(
        onTap: onTap,
        customBorder: const CircleBorder(),
        child: SizedBox(
          width: 40,
          height: 40,
          child: Icon(Icons.arrow_upward, size: 20, color: scheme.primary),
        ),
      ),
    );
  }
}
