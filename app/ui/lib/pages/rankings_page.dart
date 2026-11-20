import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../widgets/default_cover.dart';

import '../core/providers.dart';
import '../data/api/strata_api.dart';
import '../widgets/metric_badge.dart';

/// Classic 六榜（docs/12 展示列）：顶部横滑 tab 导航，平台累计值排序。
const _boards = [
  ('recommend', '推荐榜'),
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
        title: Text('榜单'),
        actions: [
          IconButton(
              icon: const Icon(Icons.swap_vert),
              onPressed: () => context.push('/discover')),
        ],
      ),
      body: Column(
        children: [
          // header tab：Classic 主线
          Container(
            height: 42,
            decoration: BoxDecoration(
                border: Border(
                    bottom: BorderSide(color: scheme.outline.withValues(alpha: .3)))),
            child: Row(
              children: [
                const SizedBox(width: 16),
                _modeTab(context, 'Classic', true, null),
              ],
            ),
          ),
          // 顶部六榜 tab（横滑）
          SizedBox(
            height: 44,
            child: TabBar(
              controller: _tabs,
              isScrollable: true,
              labelColor: scheme.primary,
              unselectedLabelColor: scheme.onSurfaceVariant,
              indicatorColor: scheme.primary,
              dividerColor: scheme.outline.withValues(alpha: .3),
              labelStyle:
                  const TextStyle(fontSize: 14, fontWeight: FontWeight.w600),
              unselectedLabelStyle: const TextStyle(fontSize: 14),
              tabs: [
                for (final (_, label) in _boards) Tab(text: label),
              ],
            ),
          ),
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

  Widget _modeTab(BuildContext context, String label, bool active, String? note) {
    final scheme = Theme.of(context).colorScheme;
    return GestureDetector(
      onTap: active ? null : null,
      child: Container(
        padding: const EdgeInsets.symmetric(vertical: 8, horizontal: 2),
        decoration: BoxDecoration(
            border: Border(
                bottom: BorderSide(
                    width: 2,
                    color: active
                        ? scheme.primary
                        : Colors.transparent))),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            Text(label,
                style: TextStyle(
                    fontSize: 14,
                    fontWeight: active ? FontWeight.w700 : FontWeight.w400,
                    color: active ? scheme.primary : scheme.onSurfaceVariant)),
            if (note != null) ...[
              const SizedBox(width: 4),
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 1),
                decoration: BoxDecoration(
                    border: Border.all(color: scheme.outline.withValues(alpha: .4)),
                    borderRadius: BorderRadius.circular(999)),
                child: Text(note,
                    style: TextStyle(
                        fontSize: 9, color: scheme.onSurfaceVariant)),
              ),
            ],
          ],
        ),
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
                            fontSize: 11, color: schemeOf(context).onSurfaceVariant)),
                  );
                }
                return _BoardCard(item: list[i]);
              },
            ),
    );
  }
}

ColorScheme schemeOf(BuildContext context) => Theme.of(context).colorScheme;

class _BoardCard extends StatelessWidget {
  final RankItem item;

  const _BoardCard({required this.item});

  @override
  Widget build(BuildContext context) {
    final scheme = schemeOf(context);
    final coverUrl = item.coverUrl;
    final hasCover = coverUrl != null && coverUrl.isNotEmpty;
    return Padding(
      padding: const EdgeInsets.only(bottom: 16),
      child: InkWell(
        onTap: () => context.push('/book/${item.nid}'),
        borderRadius: BorderRadius.circular(10),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            // 大封面：有封面拼 CDN 前缀；无封面书脊字占位（官方式降级）
            SizedBox(
              width: 104,
              height: 140,
              child: hasCover
                  ? ClipRRect(
                      borderRadius: BorderRadius.circular(10),
                      child: coverImage(coverUrl, item.nid),
                    )
                  : defaultCover(item.nid, radius: 10),
            ),
            const SizedBox(width: 12),
            Expanded(
              child: SizedBox(
                height: 140,
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(item.title,
                        maxLines: 2,
                        overflow: TextOverflow.ellipsis,
                        style: const TextStyle(
                            fontSize: 14, fontWeight: FontWeight.w600, height: 1.4)),
                    const SizedBox(height: 6),
                    Text(item.author,
                        style: TextStyle(
                            fontSize: 11.5, color: scheme.onSurfaceVariant)),
                    const SizedBox(height: 6),
                    Row(
                      children: [
                        if (item.genre != null)
                          _solidBadge(context, item.genre!, scheme.primary),
                        if (item.status != null) ...[
                          const SizedBox(width: 4),
                          _solidBadge(
                              context,
                              item.status!,
                              item.status == '已完结'
                                  ? scheme.secondary
                                  : scheme.tertiary),
                        ],
                      ],
                    ),
                    const Spacer(),
                    if (item.words != null)
                      MetricBadge(
                          icon: MetricIcons.words,
                          text: '${_wan(item.words!)}+字',
                          color: scheme.primary),
                  ],
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

Widget _solidBadge(BuildContext context, String text, Color bg) {
  return Container(
    padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 1),
    decoration: BoxDecoration(
        color: bg, borderRadius: BorderRadius.circular(4)),
    child: Text(text,
        style: TextStyle(
            fontSize: 10, color: Theme.of(context).colorScheme.onPrimary)),
  );
}

class _BackToTop extends StatelessWidget {
  final VoidCallback onTap;

  const _BackToTop({required this.onTap});

  @override
  Widget build(BuildContext context) {
    final scheme = schemeOf(context);
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

String _wan(int n) {
  if (n >= 10000) return '${(n / 10000).toStringAsFixed(0)}万';
  return '$n';
}
