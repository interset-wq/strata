import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../core/providers.dart';
import '../data/api/strata_api.dart';
import '../widgets/default_cover.dart';

/// 收录管理页（docs/08 §discovered）：自动收录的库外书集中展示，
/// 滑动移除（只删 user.db discovered 行，种子库不可变）；关注入口
/// 在详情页（与内置书同一按钮）。
class CollectedPage extends ConsumerStatefulWidget {
  const CollectedPage({super.key});

  @override
  ConsumerState<CollectedPage> createState() => _CollectedPageState();
}

class _CollectedPageState extends ConsumerState<CollectedPage> {
  List<DiscoveredItem>? _items;
  bool _failed = false;
  // nid -> tracking on（关注状态映射，docs/12：watchlist 单一列表）。
  Map<int, bool> _watching = {};

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    try {
      final h = await ref.read(bootProvider.future);
      final list = await h.api.discovered();
      final wl = await h.api.watchList();
      if (mounted) {
        setState(() {
          _items = list;
          _failed = false;
          _watching = {for (final w in wl) w.nid: w.active};
        });
      }
    } catch (_) {
      if (mounted) setState(() => _failed = true);
    }
  }

  /// 一键追踪切换：active = 订阅式后台抓取开（每 tick 由 watchlist
  /// worker 轮询，docs/06）；inactive = 仅保存。
  Future<void> _toggleWatch(DiscoveredItem it) async {
    final h = await ref.read(bootProvider.future);
    final active = !(_watching[it.nid] ?? false);
    try {
      if (_watching.containsKey(it.nid)) {
        await h.api.watchSetActive(it.nid, active);
      } else {
        await h.api.watchAdd(it.nid, active: active);
      }
      if (!mounted) return;
      setState(() => _watching[it.nid] = active);
    } catch (_) {
      // 切换失败保持原状（网络/引擎忙），不打断列表。
    }
  }

  Future<void> _remove(DiscoveredItem it) async {
    try {
      final h = await ref.read(bootProvider.future);
      await h.api.deleteDiscovered(it.nid);
      if (!mounted) return;
      setState(() {
        (_items ?? []).removeWhere((e) => e.nid == it.nid);
      });
    } catch (_) {
      // 删除失败保持原样（下轮 load 恢复），不打断列表。
    }
  }

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final items = _items;
    return Scaffold(
      appBar: AppBar(title: const Text('收录的书')),
      body: items == null
          ? (_failed
              ? Center(
                  child: Text('加载失败',
                      style: TextStyle(color: scheme.onSurfaceVariant)))
              : const Center(child: CircularProgressIndicator()))
          : items.isEmpty
              ? Center(
                  child: Text('还没有收录的书\n在搜索页「搜全站」后点开新书即可自动收录',
                      textAlign: TextAlign.center,
                      style: TextStyle(
                          fontSize: 13, color: scheme.onSurfaceVariant)),
                )
              : ListView.builder(
                  padding: const EdgeInsets.fromLTRB(12, 8, 12, 16),
                  itemCount: items.length,
                  itemBuilder: (_, i) {
                    final it = items[i];
                    return Dismissible(
                      key: ValueKey(it.nid),
                      direction: DismissDirection.endToStart,
                      onDismissed: (_) => _remove(it),
                      background: Container(
                        alignment: Alignment.centerRight,
                        padding: const EdgeInsets.only(right: 20),
                        decoration: BoxDecoration(
                          color: scheme.errorContainer,
                          borderRadius: BorderRadius.circular(12),
                        ),
                        child: Icon(Icons.delete_outline,
                            color: scheme.onErrorContainer),
                      ),
                      child: _card(context, scheme, it),
                    );
                  },
                ),
    );
  }

  Widget _card(BuildContext context, ColorScheme scheme, DiscoveredItem it) {
    return Card(
      margin: const EdgeInsets.only(bottom: 8),
      child: InkWell(
        onTap: () => context.push('/book/${it.nid}'),
        borderRadius: BorderRadius.circular(12),
        child: Padding(
          padding: const EdgeInsets.all(10),
          child: Row(
            children: [
              ClipRRect(
                borderRadius: BorderRadius.circular(6),
                child: Image.network(
                  coverImageUrl(it.coverUrl) ?? defaultCoverUrl(it.nid),
                  width: 44,
                  height: 62,
                  fit: BoxFit.cover,
                  loadingBuilder: coverLoadingBuilder,
                  errorBuilder: (_, _, _) => Image.network(
                    defaultCoverUrl(it.nid),
                    width: 44,
                    height: 62,
                    fit: BoxFit.cover,
                    errorBuilder: (_, _, _) => ColoredBox(
                        color: scheme.primary.withValues(alpha: .15)),
                  ),
                ),
              ),
              const SizedBox(width: 10),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(it.title,
                        maxLines: 2,
                        overflow: TextOverflow.ellipsis,
                        style: Theme.of(context).textTheme.bodyLarge),
                    const SizedBox(height: 4),
                    Text(
                      [
                        if (it.author != null && it.author!.isNotEmpty)
                          it.author!,
                        '收录于 ${_date(it.observedAt)}',
                      ].join(' · '),
                      style: TextStyle(
                          fontSize: 12, color: scheme.onSurfaceVariant),
                    ),
                  ],
                ),
              ),
              IconButton(
                icon: Icon(_watching[it.nid] ?? false
                    ? Icons.visibility
                    : Icons.visibility_outlined),
                tooltip: (_watching[it.nid] ?? false) ? '停止追踪' : '追踪更新',
                onPressed: () => _toggleWatch(it),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

String _date(int ts) {
  final d = DateTime.fromMillisecondsSinceEpoch(ts * 1000);
  final mm = d.month.toString().padLeft(2, '0');
  final dd = d.day.toString().padLeft(2, '0');
  return '${d.year}-$mm-$dd';
}
