import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../core/providers.dart';
import '../data/api/strata_api.dart';
import '../widgets/back_to_top.dart';
import '../widgets/default_cover.dart';
import '../widgets/metric_badge.dart';

/// 随机连载：从全库连载书中等概率抽取 100 本，供重度依赖随机性找书的读者。
/// 每次"换一批"或下拉刷新都重掷一次（ORDER BY RANDOM，等概率）。
final randomSerialProvider =
    FutureProvider.autoDispose<List<RankItem>>((ref) async {
  final handle = await ref.watch(bootProvider.future);
  return handle.api.randomBooks(limit: 100, status: 'serial');
});

class SerialRandomPage extends ConsumerStatefulWidget {
  const SerialRandomPage({super.key});

  @override
  ConsumerState<SerialRandomPage> createState() => _SerialRandomPageState();
}

class _SerialRandomPageState extends ConsumerState<SerialRandomPage> {
  final _scroll = ScrollController();
  bool _showTop = false;

  @override
  void initState() {
    super.initState();
    _scroll.addListener(() {
      final show = _scroll.offset > 500;
      if (show != _showTop) setState(() => _showTop = show);
    });
  }

  @override
  void dispose() {
    _scroll.removeListener(() {});
    _scroll.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
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
          child: Stack(
            children: [
              ListView.builder(
                controller: _scroll,
                padding: const EdgeInsets.fromLTRB(16, 8, 16, 80),
                itemCount: list.length + 1,
                itemBuilder: (context, i) {
                  if (i == list.length) {
                    return _rerollButton();
                  }
                  return _SerialTile(item: list[i]);
                },
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
        ),
      ),
    );
  }

  Widget _rerollButton() {
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

  static String _wan(int? n) {
    if (n == null) return '';
    if (n >= 10000) return '${(n / 10000).toStringAsFixed(1)}万';
    return '$n';
  }

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final coverUrl = item.coverUrl;
    final hasCover = coverUrl != null && coverUrl.isNotEmpty;

    // 标签：题材 + book_tags（最多 3 个）
    final tags = <String>[
      if (item.genre != null && item.genre!.isNotEmpty) item.genre!,
      ...item.tags,
    ];
    if (tags.toSet().length != tags.length) {
      // 去重且保持顺序
      final seen = <String>{};
      tags.removeWhere((t) => !seen.add(t));
    }

    // 指标行：字数 · 收藏 · 点击 · 点赞（非空才显示；icon 语义见 app/docs/15）
    final metrics = <(IconData, String)>[
      if (item.words != null) (MetricIcons.words, '${_wan(item.words)}字'),
      if (item.favs > 0) (MetricIcons.favs, _wan(item.favs)),
      if (item.clicks != null) (MetricIcons.clicks, '${_wan(item.clicks)}阅'),
      if (item.praises != null && item.praises! > 0)
        (MetricIcons.praises, _wan(item.praises)),
    ];

    return InkWell(
      onTap: () => context.push('/book/${item.nid}'),
      borderRadius: BorderRadius.circular(12),
      child: Container(
        margin: const EdgeInsets.symmetric(vertical: 5),
        padding: const EdgeInsets.all(10),
        decoration: BoxDecoration(
          color: scheme.surface,
          borderRadius: BorderRadius.circular(12),
          border: Border.all(
              color: scheme.outline.withValues(alpha: .25)),
        ),
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
                          fontSize: 13, fontWeight: FontWeight.w600)),
                  const SizedBox(height: 3),
                  Text(item.author,
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style:
                          TextStyle(fontSize: 11, color: scheme.secondary)),
                  if (tags.isNotEmpty) ...[
                    const SizedBox(height: 6),
                    Wrap(
                      spacing: 4,
                      runSpacing: 4,
                      children: [
                        for (final t in tags.take(3))
                          Container(
                            padding: const EdgeInsets.symmetric(
                                horizontal: 6, vertical: 2),
                            decoration: BoxDecoration(
                              color: scheme.primary.withValues(alpha: .08),
                              borderRadius: BorderRadius.circular(4),
                            ),
                            child: Text(t,
                                style: TextStyle(
                                    fontSize: 10,
                                    color: scheme.primary)),
                          ),
                      ],
                    ),
                  ],
                  if (metrics.isNotEmpty) ...[
                    const SizedBox(height: 6),
                    Row(
                      children: [
                        for (var i = 0; i < metrics.length; i++) ...[
                          if (i > 0) const SizedBox(width: 10),
                          MetricBadge(
                              icon: metrics[i].$1, text: metrics[i].$2),
                        ],
                      ],
                    ),
                  ],
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}
