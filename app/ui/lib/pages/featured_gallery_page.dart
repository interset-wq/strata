import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../core/providers.dart';
import '../data/api/strata_api.dart';
import '../widgets/back_to_top.dart';
import '../widgets/banner_large_card.dart';

/// 大图精选"更多"gallery：featured=1 全池，分页 10 本、上滑加载，
/// 默认按收藏降序（编辑精选池，热门在前），AppBar 按钮切换升/降序。
class FeaturedGalleryPage extends ConsumerStatefulWidget {
  const FeaturedGalleryPage({super.key});

  @override
  ConsumerState<FeaturedGalleryPage> createState() =>
      _FeaturedGalleryPageState();
}

class _FeaturedGalleryPageState extends ConsumerState<FeaturedGalleryPage> {
  static const _pageSize = 10;

  final _scroll = ScrollController();
  bool _showTop = false;

  String _order = 'desc';
  List<FeaturedItem> _items = const [];
  int _nextOffset = 0;
  bool _loading = false;
  bool _done = false;
  String? _error;

  @override
  void initState() {
    super.initState();
    _scroll.addListener(_onScroll);
    _load(reset: true);
  }

  void _onScroll() {
    // 距底部 400px 内预取下一页，spinner 先于触底出现。
    if (_scroll.position.pixels >=
        _scroll.position.maxScrollExtent - 400) {
      _load();
    }
    final show = _scroll.offset > 500;
    if (show != _showTop) setState(() => _showTop = show);
  }

  Future<void> _load({bool reset = false}) async {
    if (_loading || (!reset && _done)) return;
    setState(() {
      _loading = true;
      if (reset) {
        _items = const [];
        _nextOffset = 0;
        _done = false;
        _error = null;
      }
    });
    final api = (await ref.read(bootProvider.future)).api;
    try {
      final page = await api.featuredAll(
          limit: _pageSize, offset: _nextOffset, order: _order);
      if (!mounted) return;
      setState(() {
        _items = reset ? page : [..._items, ...page];
        _nextOffset += page.length;
        _done = page.length < _pageSize;
        _loading = false;
      });
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _loading = false;
        if (reset) _error = '$e';
      });
    }
  }

  void _toggleOrder() {
    _order = _order == 'desc' ? 'asc' : 'desc';
    _scroll.jumpTo(0);
    _load(reset: true);
  }

  @override
  void dispose() {
    _scroll.removeListener(_onScroll);
    _scroll.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return Scaffold(
      appBar: AppBar(
        title: const Text('大图精选 · 全部'),
        actions: [
          IconButton(
            icon: const Icon(Icons.swap_vert),
            tooltip: _order == 'desc' ? '切换为按收藏升序' : '切换为按收藏降序',
            onPressed: _toggleOrder,
          ),
          const SizedBox(width: 4),
        ],
      ),
      body: Stack(
        children: [
          if (_error != null && _items.isEmpty)
            Center(
                child: Text('加载失败：$_error',
                    style: TextStyle(fontSize: 12, color: scheme.error)))
          else if (_items.isEmpty && !_loading)
            const Center(child: Text('暂无内容'))
          else
            ListView.builder(
              controller: _scroll,
              padding: const EdgeInsets.only(top: 4, bottom: 80),
              itemCount: _items.length + (_loading ? 1 : 0),
              itemBuilder: (context, i) {
                if (i >= _items.length) {
                  return const Padding(
                    padding: EdgeInsets.all(16),
                    child: Center(
                        child: CircularProgressIndicator(strokeWidth: 2)),
                  );
                }
                return BannerLargeCard(
                    item: _items[i], index: i, items: _items);
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
    );
  }
}
