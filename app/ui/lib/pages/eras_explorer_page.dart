import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../core/providers.dart';
import '../data/api/strata_api.dart';

/// 世代探索（docs/18 同源的离线聚合）：est_year × genre 的书数与同代
/// P50 收藏（0.45–0.55 分位带均值）。纯种子数据，零网络请求。
final erasExplorerProvider =
    FutureProvider.autoDispose<List<ErasExploreRow>>((ref) async {
  final handle = await ref.watch(bootProvider.future);
  return handle.api.erasExplorer();
});

/// 世代对比探索器：选题材 → 2007–2026 每年的书数条 + 同代 P50 收藏。
/// 帮助用户回答「这个题材哪几年繁荣、收藏水位如何变化」。
class ErasExplorerPage extends ConsumerWidget {
  const ErasExplorerPage({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    return Scaffold(
      appBar: AppBar(title: const Text('世代探索')),
      body: ref.watch(erasExplorerProvider).when(
            loading: () => const Center(child: CircularProgressIndicator()),
            error: (e, _) => Center(child: Text('加载失败：$e')),
            data: (rows) {
              final genres = rows.map((r) => r.genre).toSet().toList()..sort();
              return _ErasBody(genres: genres, rows: rows);
            },
          ),
    );
  }
}

class _ErasBody extends ConsumerStatefulWidget {
  final List<String> genres;
  final List<ErasExploreRow> rows;

  const _ErasBody({required this.genres, required this.rows});

  @override
  ConsumerState<_ErasBody> createState() => _ErasBodyState();
}

class _ErasBodyState extends ConsumerState<_ErasBody> {
  String? _selected; // null = 第一个题材

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final selected = _selected ?? widget.genres.first;
    final visible = widget.rows.where((r) => r.genre == selected).toList()
      ..sort((a, b) => a.estYear.compareTo(b.estYear));
    final maxBooks =
        visible.fold<int>(0, (m, r) => r.books > m ? r.books : m);

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Padding(
          padding: const EdgeInsets.fromLTRB(16, 12, 16, 4),
          child: DropdownButton<String>(
            value: selected,
            isExpanded: true,
            items: [
              for (final g in widget.genres)
                DropdownMenuItem(value: g, child: Text(g)),
            ],
            onChanged: (g) => setState(() => _selected = g ?? selected),
          ),
        ),
        Padding(
          padding: const EdgeInsets.symmetric(horizontal: 16),
          child: Text('每年在库书数 · 同代 P50 收藏',
              style: TextStyle(fontSize: 11, color: scheme.onSurfaceVariant)),
        ),
        Expanded(
          child: ListView(
            padding: const EdgeInsets.fromLTRB(16, 8, 16, 16),
            children: [
              for (final r in visible)
                Padding(
                  padding: const EdgeInsets.symmetric(vertical: 4),
                  child: Row(
                    children: [
                      SizedBox(
                        width: 44,
                        child: Text('${r.estYear}',
                            style: TextStyle(
                                fontSize: 11,
                                color: scheme.onSurfaceVariant)),
                      ),
                      Expanded(
                        child: Align(
                          alignment: Alignment.centerLeft,
                          child: FractionallySizedBox(
                            widthFactor:
                                maxBooks == 0 ? 0 : r.books / maxBooks,
                            child: Container(
                              height: 14,
                              decoration: BoxDecoration(
                                color: scheme.primary.withAlpha(180),
                                borderRadius: BorderRadius.circular(3),
                              ),
                            ),
                          ),
                        ),
                      ),
                      SizedBox(
                        width: 64,
                        child: Text('${r.books} 本',
                            textAlign: TextAlign.right,
                            style: const TextStyle(fontSize: 11)),
                      ),
                      SizedBox(
                        width: 88,
                        child: Text(
                          r.medianFavs == null
                              ? ''
                              : 'P50 ${r.medianFavs!.round()}',
                          textAlign: TextAlign.right,
                          style: TextStyle(
                              fontSize: 11, color: scheme.onSurfaceVariant),
                        ),
                      ),
                    ],
                  ),
                ),
            ],
          ),
        ),
      ],
    );
  }
}
