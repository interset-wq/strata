import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../widgets/default_cover.dart';

import '../core/providers.dart';
import '../data/api/strata_api.dart';

/// 书架页（mockups 04 屏定稿）：官方式筛选 chips 行、封面卡条目、
/// 空态引导。数据 = 本地收藏（user.db.shelf JOIN seed.books）。
class ShelfPage extends ConsumerStatefulWidget {
  const ShelfPage({super.key});

  @override
  ConsumerState<ShelfPage> createState() => _ShelfPageState();
}

class _ShelfPageState extends ConsumerState<ShelfPage> {
  late Future<List<ShelfItem>> _shelf;
  String? _genreFilter; // null = 全部

  @override
  void initState() {
    super.initState();
    _load();
  }

  void _load() {
    _shelf = ref.read(bootProvider.future).then((h) => h.api.shelfList());
  }

  Future<void> _remove(ShelfItem item) async {
    final handle = await ref.read(bootProvider.future);
    await handle.api.shelfRemove(item.nid);
    _load();
    setState(() {});
  }

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return Scaffold(
      appBar: AppBar(
        title: const Text('书架'),
        actions: [
          IconButton(
              icon: const Icon(Icons.visibility_outlined),
              tooltip: '追踪管理',
              onPressed: () => context.push('/watchlist')),
        ],
      ),
      body: FutureBuilder<List<ShelfItem>>(
        future: _shelf,
        builder: (context, snap) {
          if (snap.connectionState != ConnectionState.done) {
            return const Center(child: CircularProgressIndicator());
          }
          if (snap.hasError) {
            return Center(child: Text('加载失败：${snap.error}'));
          }
          final items = snap.data ?? [];
          if (items.isEmpty) {
            return _EmptyState(onBrowse: () => context.go('/'));
          }
          // 官方式筛选 chips：全部 + 题材聚合（数据驱动，无假筛选）
          final genres =
              items.map((e) => e.genre).whereType<String>().toSet().toList()..sort();
          final filtered = _genreFilter == null
              ? items
              : items.where((e) => e.genre == _genreFilter).toList();
          return Column(
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
                          label: Text(g == '全部' ? g : g),
                          selected:
                              _genreFilter == (g == '全部' ? null : g),
                          onSelected: (_) =>
                              setState(() => _genreFilter = g == '全部' ? null : g),
                          labelStyle: TextStyle(
                              fontSize: 12,
                              color: _genreFilter == (g == '全部' ? null : g)
                                  ? scheme.onPrimary
                                  : scheme.onSurfaceVariant),
                          selectedColor: scheme.primary,
                        ),
                      ),
                  ],
                ),
              ),
              Expanded(
                child: filtered.isEmpty
                    ? Center(
                        child: Text('该筛选下暂无藏书',
                            style: TextStyle(color: scheme.onSurfaceVariant)))
                    : RefreshIndicator(
                        onRefresh: () async => _load(),
                        child: ListView.builder(
                          padding: const EdgeInsets.fromLTRB(16, 8, 16, 16),
                          itemCount: filtered.length,
                          itemBuilder: (context, i) =>
                              _ShelfCard(
                                item: filtered[i],
                                onRemove: () => _remove(filtered[i]),
                              ),
                        ),
                      ),
              ),
            ],
          );
        },
      ),
    );
  }
}

class _ShelfCard extends StatelessWidget {
  final ShelfItem item;
  final VoidCallback onRemove;

  const _ShelfCard({required this.item, required this.onRemove});

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final added = DateTime.fromMillisecondsSinceEpoch(item.addedAt * 1000);
    final days = DateTime.now().difference(added).inDays;
    final when = days <= 0 ? '今天' : days == 1 ? '昨天' : '收藏于 $days 天前';
    return Card(
      margin: const EdgeInsets.only(bottom: 10),
      child: InkWell(
        onTap: () => context.push('/book/${item.nid}'),
        borderRadius: BorderRadius.circular(16),
        child: Padding(
          padding: const EdgeInsets.all(12),
          child: Row(
            children: [
              // 无封面数据：书脊字占位（与发现流一致）
              Container(
                width: 52,
                height: 72,
                decoration: BoxDecoration(
                  color: scheme.surface,
                  border:
                      Border.all(color: scheme.outline.withValues(alpha: .4)),
                  borderRadius: BorderRadius.circular(6),
                ),
                alignment: Alignment.center,
                child: defaultCover(item.nid, radius: 6),
              ),
              const SizedBox(width: 12),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(item.title,
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        style: Theme.of(context)
                            .textTheme
                            .titleLarge
                            ?.copyWith(fontSize: 14)),
                    const SizedBox(height: 3),
                    Text(
                      item.genre != null ? '${item.author} · ${item.genre}' : item.author,
                      style: TextStyle(
                          fontSize: 11, color: scheme.onSurfaceVariant),
                    ),
                    const SizedBox(height: 5),
                    Container(
                      padding:
                          const EdgeInsets.symmetric(horizontal: 8, vertical: 1),
                      decoration: BoxDecoration(
                          border: Border.all(
                              color: scheme.outline.withValues(alpha: .5)),
                          borderRadius: BorderRadius.circular(999)),
                      child: Text(when,
                          style: TextStyle(
                              fontSize: 10, color: scheme.onSurfaceVariant)),
                    ),
                  ],
                ),
              ),
              IconButton(
                icon: Icon(Icons.favorite, color: scheme.primary),
                tooltip: '移出书架',
                onPressed: onRemove,
              ),
            ],
          ),
        ),
      ),
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
          Icon(Icons.collections_bookmark_outlined,
              size: 56, color: scheme.onSurfaceVariant.withValues(alpha: .5)),
          const SizedBox(height: 12),
          Text('书架还是空的',
              style: TextStyle(
                  fontFamily: 'serif',
                  fontSize: 17,
                  fontWeight: FontWeight.w700)),
          const SizedBox(height: 6),
          Text('去首页找到下一本想读的书，点「收藏」加入',
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
