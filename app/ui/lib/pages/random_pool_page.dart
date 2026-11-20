import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../core/providers.dart';
import '../data/api/strata_api.dart';
import '../widgets/back_to_top.dart';
import '../widgets/book_row_tile.dart';

/// 随机池：从指定池中等概率抽取 100 本（serial=连载长篇，
/// finished=完结长篇，browse=60万字大书，short=短篇/中篇/对话池，
/// 与首页随机区/短篇/中篇/对话 tab 一一对应）。
/// 每次"换一批"或下拉刷新都重掷一次（ORDER BY RANDOM，等概率）。
final randomPoolProvider = FutureProvider.autoDispose
    .family<List<RankItem>, ({String status, String form})>((ref, key) async {
      final handle = await ref.watch(bootProvider.future);
      return handle.api.randomBooks(
        limit: 100,
        status: key.status,
        form: key.form,
      );
    });

/// 随机池 100 本二级页（连载/完结/随便看看/短篇/中篇/对话共用，由 status/form/title 区分）。
class RandomPoolPage extends ConsumerStatefulWidget {
  final String status; // 'serial' | 'finished' | 'browse' | 'short'
  final String title;
  final String? form; // 覆盖默认 form；中篇随机池 = short + medium

  const RandomPoolPage({
    super.key,
    required this.status,
    required this.title,
    this.form,
  });

  @override
  ConsumerState<RandomPoolPage> createState() => _RandomPoolPageState();
}

class _RandomPoolPageState extends ConsumerState<RandomPoolPage> {
  final _scroll = ScrollController();
  bool _showTop = false;

  ({String status, String form}) get _key => (
    status: widget.status,
    form: widget.form ?? (widget.status == 'short' ? 'short' : 'long'),
  );

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
    final items = ref.watch(randomPoolProvider(_key));
    final scheme = Theme.of(context).colorScheme;
    return Scaffold(
      appBar: AppBar(title: Text(widget.title)),
      body: items.when(
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (e, _) => Center(
          child: Text(
            '加载失败：$e',
            style: TextStyle(fontSize: 12, color: scheme.error),
          ),
        ),
        data: (list) => RefreshIndicator(
          onRefresh: () async {
            ref.invalidate(randomPoolProvider(_key));
            await ref.read(randomPoolProvider(_key).future);
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
                  return BookRowTile(item: list[i]);
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
                      curve: Curves.easeOut,
                    ),
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
        onPressed: () => ref.invalidate(randomPoolProvider(_key)),
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
