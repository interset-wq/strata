import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../core/providers.dart';

/// Home page: proves the engine is serving by calling /strata/meta.
class HomePage extends ConsumerWidget {
  const HomePage({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final meta = ref.watch(metaProvider);
    return Scaffold(
      appBar: AppBar(
        title: const Text('Strata'),
        actions: [
          IconButton(
            icon: const Icon(Icons.leaderboard),
            tooltip: '榜单',
            onPressed: () => context.go('/rankings'),
          ),
          IconButton(
            icon: const Icon(Icons.search),
            tooltip: '搜索',
            onPressed: () => context.go('/search'),
          ),
          IconButton(
            icon: const Icon(Icons.collections_bookmark),
            tooltip: '书架',
            onPressed: () => context.go('/shelf'),
          ),
          IconButton(
            icon: const Icon(Icons.refresh),
            tooltip: '刷新 meta',
            onPressed: () => ref.invalidate(metaProvider),
          ),
        ],
      ),
      body: meta.when(
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (error, _) =>
            Center(child: Text('meta 加载失败：$error', textAlign: TextAlign.center)),
        data: (value) => ListView(
          padding: const EdgeInsets.all(16),
          children: [
            Text('种子信息（/strata/meta）',
                style: Theme.of(context).textTheme.titleLarge),
            const SizedBox(height: 12),
            _row('seed_version', value.manifest.seedVersion),
            _row('book_count', '${value.manifest.bookCount}'),
            _row('licensed_count', '${value.manifest.licensedCount}'),
            _row('content_end', value.manifest.contentEnd),
            _row('built_at', value.manifest.builtAt),
            _row('出生年份区间', '${value.manifest.genMin}..${value.manifest.genMax}'),
            _row('tags', '${value.manifest.tagCount} 类 / ${value.manifest.tagRows} 行'),
            const SizedBox(height: 12),
            Text('seed_meta 条目数：${value.seedMeta.length}',
                style: Theme.of(context).textTheme.bodySmall),
          ],
        ),
      ),
    );
  }

  Widget _row(String label, String value) => Padding(
        padding: const EdgeInsets.symmetric(vertical: 4),
        child: Row(
          mainAxisAlignment: MainAxisAlignment.spaceBetween,
          children: [
            Text(label),
            Text(value, style: const TextStyle(fontWeight: FontWeight.w600)),
          ],
        ),
      );
}
