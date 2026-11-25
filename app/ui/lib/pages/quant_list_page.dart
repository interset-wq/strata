import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../core/providers.dart';
import '../data/api/strata_api.dart';
import '../widgets/back_to_top.dart';
import '../widgets/book_row_tile.dart';

/// 量化榜单页（用户 2026-11-25 裁定）：自定义指标独立出榜，**经典榜单禁止
/// 修改**。两榜：口碑（cqs DESC，行内无精确名次——红线 4）/ 位置（cps
/// DESC，替代旧「不发榜」裁定）。form 硬前置（红线 1）：目前仅长篇。
/// 无 clx 发现（篇幅偏好不属于榜单，红线 5）。
class QuantListPage extends ConsumerStatefulWidget {
  const QuantListPage({super.key});

  @override
  ConsumerState<QuantListPage> createState() => _QuantListPageState();
}

class _QuantListPageState extends ConsumerState<QuantListPage> {
  static const int _batch = 20;

  String _board = 'cqs'; // 'cqs' 口碑榜 | 'cps' 位置榜
  final _scroll = ScrollController();
  List<RankItem> _items = [];
  bool _loading = false;
  bool _done = false;
  bool _showTop = false;
  String? _error;

  @override
  void initState() {
    super.initState();
    _loadMore();
    _scroll.addListener(() {
      // 距底 400px 预取下一页（同经典榜）。
      if (_scroll.position.pixels >=
          _scroll.position.maxScrollExtent - 400) {
        _loadMore();
      }
      final show = _scroll.offset > 500;
      if (show != _showTop) setState(() => _showTop = show);
    });
  }

  @override
  void dispose() {
    _scroll.dispose();
    super.dispose();
  }

  Future<void> _loadMore() async {
    if (_loading || _done) return;
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final handle = await ref.read(bootProvider.future);
      final r = await handle.api.quantList(
        board: _board,
        form: 'long',
        limit: _batch,
        offset: _items.length,
      );
      if (!mounted) return;
      setState(() {
        _items = [..._items, ...r.items];
        _done = r.items.length < _batch;
        _loading = false;
      });
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _error = '$e';
        _loading = false;
      });
    }
  }

  Future<void> _switchBoard(String board) async {
    if (board == _board) return;
    setState(() {
      _board = board;
      _items = [];
      _done = false;
    });
    _scroll.jumpTo(0);
    await _loadMore();
  }

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return Scaffold(
      appBar: AppBar(title: const Text('量化榜单')),
      body: Column(
        children: [
          const SizedBox(height: 8),
          // 两榜切换：口碑（cqs）/ 位置（cps）
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: 16),
            child: SegmentedButton<String>(
              segments: const [
                ButtonSegment(
                    value: 'cqs',
                    label: Text('口碑'),
                    icon: Icon(Icons.thumb_up_alt_outlined)),
                ButtonSegment(
                    value: 'cps',
                    label: Text('位置'),
                    icon: Icon(Icons.place_outlined)),
              ],
              selected: {_board},
              onSelectionChanged: (s) => _switchBoard(s.first),
            ),
          ),
          // 口径说明（红线 4：不展示精确名次；红线 1：仅长篇）
          Padding(
            padding: const EdgeInsets.fromLTRB(20, 8, 20, 0),
            child: Text(
              _board == 'cqs'
                  ? '长篇 · 按同代口碑分排序（不显示精确名次）'
                  : '长篇 · 按同格收藏位置排序',
              style: TextStyle(fontSize: 11, color: scheme.onSurfaceVariant),
            ),
          ),
          Expanded(
            child: RefreshIndicator(
              onRefresh: () async {
                setState(() {
                  _items = [];
                  _done = false;
                });
                await _loadMore();
              },
              child: Stack(
                children: [
                  ListView.builder(
                    controller: _scroll,
                    padding: const EdgeInsets.fromLTRB(16, 8, 16, 80),
                    itemCount: _items.length + (_loading ? 1 : 0),
                    itemBuilder: (context, i) {
                      if (_error != null && _items.isEmpty && i == 0) {
                        return Padding(
                          padding: const EdgeInsets.all(24),
                          child: Center(
                            child: Text('加载失败：$_error',
                                style: TextStyle(
                                    color: scheme.error, fontSize: 13)),
                          ),
                        );
                      }
                      if (i == _items.length) {
                        return const Padding(
                          padding: EdgeInsets.all(24),
                          child:
                              Center(child: CircularProgressIndicator()),
                        );
                      }
                      return BookRowTile(item: _items[i]);
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
        ],
      ),
    );
  }
}
