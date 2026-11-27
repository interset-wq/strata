import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../widgets/book_row_tile.dart';

import '../core/providers.dart';
import '../data/api/strata_api.dart';
import '../widgets/back_to_top.dart';

/// 关注页（watchlist，v6 统一列表，原「书架」条目 = 未激活）：官方式筛选
/// chips 行、统一卡（激活/未激活徽标 + 追踪切换 + 移除）、空态引导。
/// 数据 = 本地 watchlist（user.db.watchlist JOIN seed.books）。
/// 观测时序在详情页看（docs/07）。
class WatchlistPage extends ConsumerStatefulWidget {
  const WatchlistPage({super.key});

  @override
  ConsumerState<WatchlistPage> createState() => _WatchlistPageState();
}

class _WatchlistPageState extends ConsumerState<WatchlistPage> {
  late Future<List<WatchItem>> _items;
  String? _genreFilter; // null = 全部
  final _scroll = ScrollController();
  bool _showTop = false;

  @override
  void initState() {
    super.initState();
    _load();
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

  void _load() {
    _items = ref.read(bootProvider.future).then((h) => h.api.watchList());
  }

  Future<void> _remove(WatchItem item) async {
    final handle = await ref.read(bootProvider.future);
    await handle.api.watchRemove(item.nid);
    _load();
  }

  Future<void> _toggle(WatchItem item) async {
    final handle = await ref.read(bootProvider.future);
    await handle.api.watchSetActive(item.nid, !item.active);
    _load();
  }

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return Scaffold(
      appBar: AppBar(
        title: const Text('我的关注'),
        // 关注通知入口（2026-11-26）：系统通知/cron 抓到的更新事件列表。
        actions: [
          IconButton(
            icon: const Icon(Icons.notifications_outlined),
            tooltip: '关注通知',
            onPressed: () => context.push('/notifications'),
          ),
        ],
      ),
      body: FutureBuilder<List<WatchItem>>(
        future: _items,
        builder: (context, snap) {
          if (snap.connectionState != ConnectionState.done) {
            return const Center(child: CircularProgressIndicator());
          }
          if (snap.hasError) {
            return Center(child: Text('加载失败：${snap.error}'));
          }
          final items = snap.data ?? [];
          if (items.isEmpty) {
            return _EmptyState(onBrowse: () => context.go('/home'));
          }
          // 官方式筛选 chips：全部 + 题材聚合（数据驱动，无假筛选）
          final genres =
              items.map((e) => e.genre).whereType<String>().toSet().toList()
                ..sort();
          final filtered = _genreFilter == null
              ? items
              : items.where((e) => e.genre == _genreFilter).toList();
          return Stack(
            children: [
              Column(
                children: [
                  SizedBox(
                    height: 44,
                    child: ListView(
                      scrollDirection: Axis.horizontal,
                      padding: const EdgeInsets.symmetric(horizontal: 16),
                      children: [
                        for (final g in ['全部', ...genres])
                          Padding(
                            padding: const EdgeInsets.only(right: 8),
                            child: ChoiceChip(
                              label: Text(g),
                              selected:
                                  _genreFilter == (g == '全部' ? null : g),
                              onSelected: (_) => setState(
                                  () => _genreFilter = g == '全部' ? null : g),
                              labelStyle: TextStyle(
                                  fontSize: 12,
                                  color: _genreFilter ==
                                          (g == '全部' ? null : g)
                                      ? scheme.onPrimary
                                      : scheme.onSurfaceVariant),
                              selectedColor: scheme.primary,
                            ),
                          ),
                      ],
                    ),
                  ),
                  const _HeatmapCard(),
                  Expanded(
                    child: filtered.isEmpty
                        ? Center(
                            child: Text(
                                '该筛选下暂无条目',
                                style: TextStyle(
                                    color: scheme.onSurfaceVariant)))
                        : RefreshIndicator(
                            onRefresh: () async => _load(),
                            child: ListView.builder(
                              controller: _scroll,
                              padding: const EdgeInsets.fromLTRB(16, 8, 16, 16),
                              itemCount: filtered.length,
                              itemBuilder: (context, i) => _WatchCard(
                                item: filtered[i],
                                onToggle: () => _toggle(filtered[i]),
                                onRemove: () => _remove(filtered[i]),
                              ),
                            ),
                          ),
                  ),
                ],
              ),
              if (_showTop)
                Positioned(
                  right: 16,
                  bottom: 24,
                  child: BackToTop(
                    onTap: () => _scroll.animateTo(
                        0,
                        duration: const Duration(milliseconds: 400),
                        curve: Curves.easeOut),
                  ),
                ),
            ],
          );
        },
      ),
    );
  }
}

/// 统一行（2026-11-26 书籍列表统一）：与经典榜单同款行（BookRowTile），
/// 「追踪于/保存于 N 天前」与观测/追踪/移除操作收进右侧 trailing 槽，
/// 「对照」徽标走 extraTags。点卡进详情（观测时序在详情页看）。
class _WatchCard extends StatelessWidget {
  final WatchItem item;
  final VoidCallback onToggle;
  final VoidCallback onRemove;

  const _WatchCard(
      {required this.item, required this.onToggle, required this.onRemove});

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final added = DateTime.fromMillisecondsSinceEpoch(item.addedAt * 1000);
    final days = DateTime.now().difference(added).inDays;
    final when = days <= 0 ? '今天' : days == 1 ? '昨天' : '$days 天前';
    return BookRowTile(
      item: RankItem.fromJson({
        'rank': 0,
        'nid': item.nid,
        'title': item.title,
        'author': item.genre != null
            ? '${item.author} · ${item.genre}'
            : item.author,
        'cover_url': item.coverUrl,
      }),
      extraTags: item.role == 'peer' ? const ['对照'] : const [],
      trailing: Column(
        crossAxisAlignment: CrossAxisAlignment.end,
        children: [
          Text(
            item.active ? '追踪于 $when' : '保存于 $when',
            style: TextStyle(
                fontSize: 10,
                color: item.active ? scheme.primary : scheme.onSurfaceVariant),
          ),
          const SizedBox(height: 4),
          // 观测数据快捷入口（docs/07 工作台直达路径）+ 追踪切换（v6）+ 移除
          Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              IconButton(
                icon: Icon(Icons.timeline,
                    size: 18, color: scheme.onSurfaceVariant),
                tooltip: '观测数据',
                onPressed: () => context.push('/book/${item.nid}/data'),
              ),
              IconButton(
                icon: Icon(
                    item.active
                        ? Icons.visibility
                        : Icons.visibility_outlined,
                    color: item.active
                        ? scheme.primary
                        : scheme.onSurfaceVariant),
                tooltip: item.active ? '停止追踪' : '追踪更新',
                onPressed: onToggle,
              ),
              IconButton(
                icon: Icon(Icons.delete_outline,
                    size: 18, color: scheme.onSurfaceVariant),
                tooltip: '取消关注',
                onPressed: onRemove,
              ),
            ],
          ),
        ],
      ),
    );
  }
}

/// 更新热力图（docs/07 §4）：关注书观测的按日聚合，90 天格子，
/// 强度 = 当日有观测的书数。纯聚合视图，不伪造全库时序。
class _HeatmapCard extends ConsumerWidget {
  const _HeatmapCard();

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final scheme = Theme.of(context).colorScheme;
    final future =
        ref.read(bootProvider.future).then((h) => h.api.watchHeatmap());
    return FutureBuilder<List<HeatmapDay>>(
      future: future,
      builder: (context, snap) {
        Widget body;
        if (snap.hasError) {
          body = Text('加载失败：${snap.error}',
              style: TextStyle(color: scheme.error, fontSize: 12));
        } else if (snap.connectionState != ConnectionState.done) {
          body = const Center(
              child: SizedBox(
                  width: 16,
                  height: 16,
                  child: CircularProgressIndicator(strokeWidth: 2)));
        } else {
          final byDay = {
            for (final c in snap.data ?? <HeatmapDay>[]) c.day: c,
          };
          final today = DateTime.now().millisecondsSinceEpoch ~/ 86400000;
          final maxBooks = byDay.values
              .fold<int>(0, (m, c) => c.books > m ? c.books : m);
          body = Wrap(
            spacing: 2,
            runSpacing: 2,
            children: [
              for (int d = today - 89; d <= today; d++)
                Builder(builder: (_) {
                  final c = byDay[d];
                  final f =
                      (c == null || maxBooks == 0) ? 0.0 : c.books / maxBooks;
                  return Container(
                    width: 11,
                    height: 11,
                    decoration: BoxDecoration(
                      color: f == 0
                          ? scheme.surfaceContainerHighest
                          : scheme.primary.withAlpha((80 + 175 * f).round()),
                      borderRadius: BorderRadius.circular(2),
                    ),
                  );
                }),
            ],
          );
        }
        return Card(
          margin: const EdgeInsets.fromLTRB(16, 4, 16, 4),
          child: Padding(
            padding: const EdgeInsets.all(12),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text('更新动态 · 90 天',
                    style: TextStyle(
                        fontSize: 12, color: scheme.onSurfaceVariant)),
                const SizedBox(height: 8),
                body,
              ],
            ),
          ),
        );
      },
    );
  }
}

class _EmptyState extends StatelessWidget {
  final VoidCallback onBrowse;

  const _EmptyState({required this.onBrowse});

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return Center(
      child: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          Icon(Icons.bookmark_outline,
              size: 56, color: scheme.onSurfaceVariant.withValues(alpha: .5)),
          const SizedBox(height: 12),
          Text('还没有关注的书',
              style: TextStyle(
                  fontFamily: 'serif',
                  fontSize: 17,
                  fontWeight: FontWeight.w700)),
          const SizedBox(height: 6),
          Text('去首页找到下一本想读的书，点「关注此书」保存',
              style: TextStyle(fontSize: 12, color: scheme.onSurfaceVariant)),
          const SizedBox(height: 16),
          OutlinedButton(
            onPressed: onBrowse,
            style: OutlinedButton.styleFrom(
                foregroundColor: scheme.primary,
                side: BorderSide(color: scheme.primary)),
            child: const Text('去逛逛'),
          ),
        ],
      ),
    );
  }
}
