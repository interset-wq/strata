import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../core/providers.dart';
import '../data/api/strata_api.dart';
import '../widgets/back_to_top.dart';
import '../widgets/book_row_tile.dart';

/// 一个 IP 入口的完整列表：收藏降序，一次性取全（最大 IP 组 36 本）。
final ipBooksProvider =
    FutureProvider.autoDispose.family<List<RankItem>, String>((ref, group)
        async {
  final api = (await ref.watch(bootProvider.future)).api;
  return api.ipBooks(form: 'ip_collab', group: group);
});

/// IP 入口二级页：某联动 IP（或“其他”长尾）的全部作品。
class IpBooksPage extends ConsumerStatefulWidget {
  final String group; // contest 名或 'other'
  final String label; // 展示名（崩坏3 / 少女前线 / 其他）

  const IpBooksPage({super.key, required this.group, required this.label});

  @override
  ConsumerState<IpBooksPage> createState() => _IpBooksPageState();
}

class _IpBooksPageState extends ConsumerState<IpBooksPage> {
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
    final items = ref.watch(ipBooksProvider(widget.group));
    final scheme = Theme.of(context).colorScheme;
    return Scaffold(
      appBar: AppBar(
        title: items.when(
          data: (list) => Text('${widget.label} · ${list.length} 本'),
          loading: () => Text(widget.label),
          error: (_, _) => Text(widget.label),
        ),
      ),
      body: items.when(
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (e, _) => Center(
            child: Text('加载失败：$e',
                style: TextStyle(fontSize: 12, color: scheme.error))),
        data: (list) => list.isEmpty
            ? const Center(
                child: Text('这个 IP 下暂无作品',
                    style: TextStyle(fontSize: 12)))
            : Stack(
                children: [
                  ListView.builder(
                    controller: _scroll,
                    padding: const EdgeInsets.fromLTRB(16, 8, 16, 80),
                    itemCount: list.length,
                    itemBuilder: (context, i) => BookRowTile(
                      item: list[i],
                      // “其他”长尾混排多个 IP，需要徽标；单一 IP 页全页同 IP，
                      // 与页面标题重复，不显示。
                      ipLabel: widget.group == 'other'
                          ? contestIpLabel(list[i].contest)
                          : null,
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
      ),
    );
  }
}
