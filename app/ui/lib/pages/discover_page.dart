import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../core/providers.dart';
import '../widgets/default_cover.dart';
import '../data/api/strata_api.dart';

/// Classic 发现流（mockups 11 屏定稿，docs/12 §5）：有封面书按平台热度
/// 两列封面墙，游标分页每批 20 本，上滑自动加载，back-to-top。
class DiscoverPage extends ConsumerStatefulWidget {
  const DiscoverPage({super.key});

  @override
  ConsumerState<DiscoverPage> createState() => _DiscoverPageState();
}

class _DiscoverPageState extends ConsumerState<DiscoverPage> {
  final List<RankItem> _items = [];
  String? _cursor;
  bool _loading = false;
  bool _done = false;
  bool _showTop = false;
  final _scroll = ScrollController();

  @override
  void initState() {
    super.initState();
    _load();
    _scroll.addListener(_onScroll);
  }

  void _onScroll() {
    final show = _scroll.offset > 500;
    if (show != _showTop) setState(() => _showTop = show);
    if (_scroll.position.extentAfter < 400) _load();
  }

  Future<void> _load() async {
    if (_loading || _done) return;
    _loading = true;
    try {
      final handle = await ref.read(bootProvider.future);
      final page = await handle.api.discover(cursor: _cursor);
      setState(() {
        _items.addAll(page.items);
        _cursor = page.nextCursor;
        _done = !page.hasMore;
      });
    } catch (_) {
      // 静默：下一屏再试
    } finally {
      _loading = false;
    }
  }

  @override
  void dispose() {
    _scroll.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return Scaffold(
      appBar: AppBar(
        title: Text('发现'),
        actions: const [IconButton(icon: Icon(Icons.swap_vert), onPressed: null)],
      ),
      body: Column(
        children: [
          Container(
            height: 42,
            decoration: BoxDecoration(
                border: Border(
                    bottom: BorderSide(
                        color: scheme.outline.withValues(alpha: .3)))),
            child: Row(
              children: [
                const SizedBox(width: 16),
                Container(
                  padding: const EdgeInsets.symmetric(vertical: 8, horizontal: 2),
                  decoration: BoxDecoration(
                      border: Border(
                          bottom: BorderSide(width: 2, color: scheme.primary))),
                  child: Text('Classic',
                      style: TextStyle(
                          fontSize: 14,
                          fontWeight: FontWeight.w700,
                          color: scheme.primary)),
                ),
                const SizedBox(width: 22),
                Container(
                  padding: const EdgeInsets.symmetric(vertical: 8, horizontal: 2),
                  child: Row(mainAxisSize: MainAxisSize.min, children: [
                    Text('量化',
                        style: TextStyle(
                            fontSize: 14, color: scheme.onSurfaceVariant)),
                    const SizedBox(width: 4),
                    Container(
                      padding: const EdgeInsets.symmetric(
                          horizontal: 6, vertical: 1),
                      decoration: BoxDecoration(
                          border: Border.all(
                              color: scheme.outline.withValues(alpha: .4)),
                          borderRadius: BorderRadius.circular(999)),
                      child: Text('数据分析中',
                          style: TextStyle(
                              fontSize: 9, color: scheme.onSurfaceVariant)),
                    ),
                  ]),
                ),
              ],
            ),
          ),
          Text('按平台热度发现 · 上滑不断翻 · 12,107 本有封面',
              style: TextStyle(
                  fontSize: 11, color: scheme.onSurfaceVariant)),
          Expanded(
            child: Stack(
              children: [
                ListView.builder(
                  controller: _scroll,
                  padding: const EdgeInsets.fromLTRB(16, 12, 16, 60),
                  itemCount: _items.length + (_done ? 0 : 1),
                  itemBuilder: (context, i) {
                    if (i >= _items.length) {
                      return const Padding(
                        padding: EdgeInsets.all(16),
                        child: Center(child: CircularProgressIndicator()),
                      );
                    }
                    return _DiscoverCard(item: _items[i]);
                  },
                ),
                if (_showTop)
                  Positioned(
                    right: 16,
                    bottom: 16,
                    child: Material(
                      color: scheme.surface,
                      borderRadius: BorderRadius.circular(20),
                      elevation: 3,
                      child: InkWell(
                        onTap: () => _scroll.animateTo(0,
                            duration: const Duration(milliseconds: 400),
                            curve: Curves.easeOut),
                        customBorder: const CircleBorder(),
                        child: SizedBox(
                          width: 40,
                          height: 40,
                          child: Icon(Icons.arrow_upward,
                              size: 20, color: scheme.primary),
                        ),
                      ),
                    ),
                  ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class _DiscoverCard extends StatelessWidget {
  final RankItem item;

  const _DiscoverCard({required this.item});

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final coverUrl = item.coverUrl;
    final hasCover = coverUrl != null && coverUrl.isNotEmpty;
    return Card(
      margin: const EdgeInsets.only(bottom: 10),
      child: InkWell(
        onTap: () => context.push('/book/${item.nid}'),
        borderRadius: BorderRadius.circular(16),
        child: Padding(
          padding: const EdgeInsets.all(12),
          child: Row(
            children: [
              SizedBox(
                width: 64,
                height: 88,
                child: hasCover
                    ? ClipRRect(
                        borderRadius: BorderRadius.circular(6),
                        child: Image.network(
                          'https://rss.sfacg.com/web/novel/images/NovelCover/Big/$coverUrl',
                          fit: BoxFit.cover,
                          errorBuilder: (_, _, _) => defaultCover(item.nid, radius: 10),
                        ),
                      )
                    : defaultCover(item.nid, radius: 10),
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
                            ?.copyWith(fontSize: 13.5)),
                    const SizedBox(height: 3),
                    Text(item.author,
                        style: TextStyle(
                            fontSize: 11, color: scheme.onSurfaceVariant)),
                    const SizedBox(height: 5),
                    _badge(context, '点击 ${_wan(item.clicks ?? 0)}',
                        fg: scheme.primary),
                  ],
                ),
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

String _wan(int n) {
  if (n >= 10000) return '${(n / 10000).toStringAsFixed(0)}万';
  return '$n';
}
