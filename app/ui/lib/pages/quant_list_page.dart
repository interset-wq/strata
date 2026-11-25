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
  int _session = 0; // 加载会话号：切榜/刷新自增，陈旧响应作废
  int _baseOffset = 0; // 手动翻页锚点（用户 2026-11-25：便于手动传 offset）
  final _offsetInput = TextEditingController();
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
    _offsetInput.dispose();
    super.dispose();
  }

  Future<void> _loadMore() async {
    if (_loading || _done) return;
    // 快照：board/offset 在调用时钉死，在途期间切榜不改请求参数；
    // 响应回来时 session 对不上即作废（修复位置榜空白/串榜竞态，
    // 用户 2026-11-25 报告位置榜空列表）。
    final session = _session;
    final board = _board;
    final offset = _baseOffset + _items.length;
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final handle = await ref.read(bootProvider.future);
      final r = await handle.api.quantList(
        board: board,
        form: 'long',
        limit: _batch,
        offset: offset,
      );
      if (!mounted || session != _session) return;
      setState(() {
        _items = [..._items, ...r.items];
        _done = r.items.length < _batch;
        _loading = false;
      });
    } catch (e) {
      if (!mounted || session != _session) return;
      setState(() {
        _error = '$e';
        _loading = false;
      });
    }
  }

  Future<void> _switchBoard(String board) async {
    if (board == _board) return;
    // 会话号自增作废在途请求；强制释放 _loading 保证新榜首屏
    // 请求一定发出（否则在途口碑请求期间切榜，位置榜永远不加载）。
    _session++;
    _offsetInput.clear();
    setState(() {
      _board = board;
      _baseOffset = 0;
      _items = [];
      _done = false;
      _loading = false;
    });
    _scroll.jumpTo(0);
    await _loadMore();
  }

  /// 手动翻页：直接传 offset 跳到该页（用户 2026-11-25）；跳转后列表
  /// 替换为该页数据，继续上滑从该锚点自然延续。
  Future<void> _jumpToOffset() async {
    final v = int.tryParse(_offsetInput.text.trim());
    if (v == null || v < 0) return;
    _session++;
    setState(() {
      _baseOffset = v;
      _items = [];
      _done = false;
      _loading = false;
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
              (_board == 'cqs'
                      ? '长篇 · 按同代口碑分排序（不显示精确名次）'
                      : '长篇 · 按同格收藏位置排序') +
                  (_baseOffset > 0 ? '  (offset $_baseOffset)' : ''),
              style: TextStyle(fontSize: 11, color: scheme.onSurfaceVariant),
            ),
          ),
          // 手动翻页器：直接传 offset 跳转（用户 2026-11-25）
          Padding(
            padding: const EdgeInsets.fromLTRB(16, 8, 16, 0),
            child: Row(
              children: [
                Expanded(
                  child: TextField(
                    controller: _offsetInput,
                    keyboardType: TextInputType.number,
                    decoration: const InputDecoration(
                      hintText: 'offset',
                      isDense: true,
                      border: OutlineInputBorder(),
                    ),
                    onSubmitted: (_) => _jumpToOffset(),
                  ),
                ),
                const SizedBox(width: 8),
                FilledButton.tonal(
                  onPressed: _jumpToOffset,
                  child: const Text('跳转'),
                ),
              ],
            ),
          ),
          Expanded(
            child: RefreshIndicator(
              onRefresh: () async {
                _session++;
                _offsetInput.clear();
                setState(() {
                  _baseOffset = 0;
                  _items = [];
                  _done = false;
                  _loading = false;
                });
                await _loadMore();
              },
              child: Stack(
                children: [
                  ListView.builder(
                    controller: _scroll,
                    padding: const EdgeInsets.fromLTRB(16, 8, 16, 80),
                    itemCount: _items.length +
                        (_loading || (_error != null && _items.isEmpty)
                            ? 1
                            : 0),
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
