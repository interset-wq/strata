import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../widgets/default_cover.dart';
import '../widgets/back_to_top.dart';

import '../core/providers.dart';
import '../data/api/strata_api.dart';

/// 作者工作台 · 追踪列表（Phase 5，mockups 12 屏）：watchlist 管理。
/// 观测数据只存本机 user.db（docs/12 §3.4 隔离红线）。
class WatchlistPage extends ConsumerStatefulWidget {
  const WatchlistPage({super.key});

  @override
  ConsumerState<WatchlistPage> createState() => _WatchlistPageState();
}

class _WatchlistPageState extends ConsumerState<WatchlistPage> {
  late Future<List<WatchItem>> _watch;
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
    _watch = ref.read(bootProvider.future).then((h) => h.api.watchList());
  }

  Future<void> _remove(WatchItem item) async {
    final handle = await ref.read(bootProvider.future);
    await handle.api.watchRemove(item.nid);
    _load();
    setState(() {});
  }

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return Scaffold(
      appBar: AppBar(title: const Text('追踪管理')),
      body: FutureBuilder<List<WatchItem>>(
        future: _watch,
        builder: (context, snap) {
          if (snap.connectionState != ConnectionState.done) {
            return const Center(child: CircularProgressIndicator());
          }
          if (snap.hasError) {
            return Center(child: Text('加载失败：${snap.error}'));
          }
          final items = snap.data ?? [];
          if (items.isEmpty) {
            return Center(
              child: Column(
                mainAxisAlignment: MainAxisAlignment.center,
                children: [
                  Icon(Icons.visibility_outlined,
                      size: 56,
                      color: scheme.onSurfaceVariant.withValues(alpha: .5)),
                  const SizedBox(height: 12),
                  Text('还没有追踪的书',
                      style: TextStyle(
                          fontFamily: 'serif',
                          fontSize: 17,
                          fontWeight: FontWeight.w700)),
                  const SizedBox(height: 6),
                  Text('在书籍详情页点「追踪」，这里记录观测时序',
                      style: TextStyle(
                          fontSize: 12, color: scheme.onSurfaceVariant)),
                ],
              ),
            );
          }
          return RefreshIndicator(
            onRefresh: () async => _load(),
            child: Stack(
              children: [
                ListView.builder(
                  controller: _scroll,
                  padding: const EdgeInsets.fromLTRB(16, 8, 16, 16),
                  itemCount: items.length,
                  itemBuilder: (context, i) => _WatchCard(
                    item: items[i],
                    onRemove: () => _remove(items[i]),
                  ),
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
            ),
          );
        },
      ),
    );
  }
}

class _WatchCard extends StatelessWidget {
  final WatchItem item;
  final VoidCallback onRemove;

  const _WatchCard({required this.item, required this.onRemove});

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final added = DateTime.fromMillisecondsSinceEpoch(item.addedAt * 1000);
    final days = DateTime.now().difference(added).inDays;
    final when = days <= 0 ? '今天' : days == 1 ? '昨天' : '$days 天前';
    return Card(
      margin: const EdgeInsets.only(bottom: 10),
      child: InkWell(
        onTap: () => context.push('/book/${item.nid}'),
        borderRadius: BorderRadius.circular(16),
        child: Padding(
          padding: const EdgeInsets.all(12),
          child: Row(
            children: [
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
                      item.genre != null
                          ? '${item.author} · ${item.genre}'
                          : item.author,
                      style: TextStyle(
                          fontSize: 11, color: scheme.onSurfaceVariant),
                    ),
                    const SizedBox(height: 5),
                    Row(
                      children: [
                        _badge(context, '追踪 $when', fg: scheme.primary),
                        if (item.note != null && item.note!.isNotEmpty) ...[
                          const SizedBox(width: 4),
                          Expanded(
                            child: Text(item.note!,
                                maxLines: 1,
                                overflow: TextOverflow.ellipsis,
                                style: TextStyle(
                                    fontSize: 10,
                                    color: scheme.onSurfaceVariant)),
                          ),
                        ],
                      ],
                    ),
                  ],
                ),
              ),
              IconButton(
                icon: Icon(Icons.timeline, color: scheme.primary),
                tooltip: '观测数据',
                onPressed: () => context.push('/book/${item.nid}/data'),
              ),
              IconButton(
                icon: Icon(Icons.visibility_off_outlined,
                    color: scheme.onSurfaceVariant),
                tooltip: '取消追踪',
                onPressed: onRemove,
              ),
            ],
          ),
        ),
      ),
    );
  }
}

Widget _badge(BuildContext context, String text, {Color? fg}) {
  final scheme = Theme.of(context).colorScheme;
  return Container(
    padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 1),
    decoration: BoxDecoration(
      border: Border.all(color: scheme.outline.withValues(alpha: .5)),
      borderRadius: BorderRadius.circular(999),
    ),
    child: Text(text,
        style: TextStyle(fontSize: 10, color: fg ?? scheme.onSurfaceVariant)),
  );
}
