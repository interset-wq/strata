import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../core/providers.dart';
import '../data/api/strata_api.dart';
import '../widgets/default_cover.dart';

/// 随机连载：从全库连载书中等概率抽取 100 本，供重度依赖随机性找书的读者。
/// 每次"换一批"或下拉刷新都重掷一次（ORDER BY RANDOM，等概率）。
final randomSerialProvider =
    FutureProvider.autoDispose<List<RankItem>>((ref) async {
  final handle = await ref.watch(bootProvider.future);
  return handle.api.randomBooks(limit: 100, status: 'serial');
});

class SerialRandomPage extends ConsumerWidget {
  const SerialRandomPage({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final items = ref.watch(randomSerialProvider);
    final scheme = Theme.of(context).colorScheme;
    return Scaffold(
      appBar: AppBar(title: const Text('随机连载 · 100 本')),
      body: items.when(
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (e, _) => Center(
            child: Text('加载失败：$e',
                style: TextStyle(fontSize: 12, color: scheme.error))),
        data: (list) => RefreshIndicator(
          onRefresh: () async {
            ref.invalidate(randomSerialProvider);
            await ref.read(randomSerialProvider.future);
          },
          child: ListView.builder(
            padding: const EdgeInsets.fromLTRB(16, 8, 16, 80),
            itemCount: list.length + 1,
            itemBuilder: (context, i) {
              if (i == list.length) {
                return _rerollButton(context, ref);
              }
              return _SerialTile(item: list[i]);
            },
          ),
        ),
      ),
    );
  }

  Widget _rerollButton(BuildContext context, WidgetRef ref) {
    final scheme = Theme.of(context).colorScheme;
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 16),
      child: OutlinedButton.icon(
        onPressed: () => ref.invalidate(randomSerialProvider),
        icon: const Icon(Icons.refresh, size: 18),
        label: const Text('换一批（再抽 100 本）'),
        style: OutlinedButton.styleFrom(
          foregroundColor: scheme.primary,
          side: BorderSide(color: scheme.primary.withValues(alpha: .5)),
          padding: const EdgeInsets.symmetric(vertical: 14),
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(22),
          ),
        ),
      ),
    );
  }
}

class _SerialTile extends StatelessWidget {
  final RankItem item;

  const _SerialTile({required this.item});

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final coverUrl = item.coverUrl;
    final hasCover = coverUrl != null && coverUrl.isNotEmpty;
    return InkWell(
      onTap: () => context.push('/book/${item.nid}'),
      borderRadius: BorderRadius.circular(12),
      child: Padding(
        padding: const EdgeInsets.symmetric(vertical: 8),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            SizedBox(
              width: 48,
              height: 64,
              child: ClipRRect(
                borderRadius: BorderRadius.circular(6),
                child: hasCover
                    ? Image.network(
                        coverImageUrl(coverUrl)!,
                        fit: BoxFit.cover,
                        loadingBuilder: coverLoadingBuilder,
                        errorBuilder: (_, _, _) =>
                            defaultCover(item.nid),
                      )
                    : defaultCover(item.nid),
              ),
            ),
            const SizedBox(width: 12),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(item.title,
                      maxLines: 2,
                      overflow: TextOverflow.ellipsis,
                      style: const TextStyle(
                          fontSize: 14, fontWeight: FontWeight.w600)),
                  const SizedBox(height: 3),
                  Text(item.author,
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style:
                          TextStyle(fontSize: 11, color: scheme.secondary)),
                  const SizedBox(height: 3),
                  Text(
                    [
                      if (item.genre != null) item.genre!,
                      if (item.status != null) item.status!,
                    ].join(' · '),
                    style: TextStyle(
                        fontSize: 10, color: scheme.onSurfaceVariant),
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}
