import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../core/providers.dart';
import '../data/api/strata_api.dart';
import '../widgets/back_to_top.dart';
import '../widgets/book_row_tile.dart';

/// curated 全量池：日轻（licensed，官方授权日本轻小说）/ 萌神获奖（moe-goddess）。
/// 与随机池不同：收藏排序的确定性列表，不换批、不重掷。
final poolListProvider =
    FutureProvider.autoDispose.family<List<RankItem>, String>((ref, kind)
        async {
  final api = (await ref.watch(bootProvider.future)).api;
  return kind == 'licensed'
      ? api.licensedBooks()
      : api.moeGoddessBooks();
});

/// curated 全量列表二级页（行卡 + back-to-top，无随机逻辑）。
class PoolListPage extends ConsumerStatefulWidget {
  final String kind; // 'licensed' | 'moe-goddess'
  final String title;

  const PoolListPage({
    super.key,
    required this.kind,
    required this.title,
  });

  @override
  ConsumerState<PoolListPage> createState() => _PoolListPageState();
}

class _PoolListPageState extends ConsumerState<PoolListPage> {
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
    final items = ref.watch(poolListProvider(widget.kind));
    final scheme = Theme.of(context).colorScheme;
    return Scaffold(
      appBar: AppBar(title: Text(widget.title)),
      body: items.when(
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (e, _) => Center(
            child: Text('加载失败：$e',
                style: TextStyle(fontSize: 12, color: scheme.error))),
        data: (list) => Stack(
          children: [
            ListView.builder(
              controller: _scroll,
              padding: const EdgeInsets.fromLTRB(16, 8, 16, 80),
              itemCount: list.length,
              itemBuilder: (context, i) => BookRowTile(item: list[i]),
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
    );
  }
}
