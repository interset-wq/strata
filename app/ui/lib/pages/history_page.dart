import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../core/providers.dart';
import '../data/api/strata_api.dart';
import '../widgets/default_cover.dart';

/// 阅读记录：本地 user.db 的浏览足迹，按最近打开排序。
final historyProvider = FutureProvider.autoDispose<HistoryData>((ref) async {
  final handle = await ref.watch(bootProvider.future);
  return handle.api.history(limit: 50);
});

class HistoryPage extends ConsumerWidget {
  const HistoryPage({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final items = ref.watch(historyProvider);
    final scheme = Theme.of(context).colorScheme;
    return Scaffold(
      appBar: AppBar(title: const Text('阅读记录')),
      body: items.when(
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (e, _) => Center(
            child: Text('加载失败：$e',
                style: TextStyle(fontSize: 12, color: scheme.error))),
        data: (page) {
          final list = page.items;
          if (list.isEmpty) {
            return const Center(
              child: Text('还没有浏览足迹\n打开任意一本书后会出现在这里',
                  textAlign: TextAlign.center,
                  style: TextStyle(fontSize: 13)),
            );
          }
          return ListView.builder(
            padding: const EdgeInsets.all(16),
            itemCount: list.length,
            itemBuilder: (context, i) {
              final it = list[i];
              return _HistoryTile(entry: it);
            },
          );
        },
      ),
    );
  }
}

class _HistoryTile extends StatelessWidget {
  final HistoryEntry entry;

  const _HistoryTile({required this.entry});

  String _time(int ts) {
    final d = DateTime.fromMillisecondsSinceEpoch(ts * 1000);
    final now = DateTime.now();
    final diff = now.difference(d);
    if (diff.inMinutes < 1) return '刚刚';
    if (diff.inHours < 1) return '${diff.inMinutes} 分钟前';
    if (diff.inDays < 1) return '${diff.inHours} 小时前';
    return '${d.month}/${d.day}';
  }

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return InkWell(
      onTap: () => context.push('/book/${entry.nid}'),
      child: Padding(
        padding: const EdgeInsets.symmetric(vertical: 8),
        child: Row(
          children: [
            SizedBox(
              width: 40,
              height: 56,
              child: defaultCover(entry.nid, radius: 6),
            ),
            const SizedBox(width: 12),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(entry.title,
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: const TextStyle(
                          fontSize: 14, fontWeight: FontWeight.w600)),
                  const SizedBox(height: 2),
                  Text(
                    '${entry.author}${entry.genre != null ? ' · ${entry.genre}' : ''}',
                    style: TextStyle(
                        fontSize: 11, color: scheme.onSurfaceVariant),
                  ),
                ],
              ),
            ),
            Text(_time(entry.viewedAt),
                style: TextStyle(
                    fontSize: 11, color: scheme.onSurfaceVariant)),
          ],
        ),
      ),
    );
  }
}
