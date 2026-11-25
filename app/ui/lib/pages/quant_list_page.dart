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
  /// 形式（用户 2026-11-25：app 一切按 form 隔离，无页内切换）：
  /// 长篇 tab 入口默认 'long'；对话 tab 入口传 'dialogue'。
  final String form;

  const QuantListPage({super.key, this.form = 'long'});

  @override
  ConsumerState<QuantListPage> createState() => _QuantListPageState();
}

class _QuantListPageState extends ConsumerState<QuantListPage> {
  static const int _batch = 20;

  String _board = 'cqs'; // 'cqs' 口碑榜 | 'cps' 位置榜
  int _session = 0; // 加载会话号：切榜/刷新自增，陈旧响应作废
  int _baseOffset = 0; // 手动翻页锚点（用户 2026-11-25：便于手动传 offset）
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
        form: widget.form,
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

  /// 手动翻页：跳到指定 offset（用户 2026-11-25）；跳转后列表替换为
  /// 该页数据，继续上滑从该锚点自然延续。
  Future<void> _jumpToOffsetValue(int v) async {
    if (v < 0) v = 0;
    if (v == _baseOffset && _items.isNotEmpty) return;
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

  /// 手动翻页 dialog（2026-11-25：offset 输入藏进 AppBar icon，
  /// 页面无直接入口）。
  void _showPagerDialog() {
    final controller =
        TextEditingController(text: _baseOffset > 0 ? '$_baseOffset' : '');
    showDialog<void>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('手动翻页'),
        content: SizedBox(
          width: 320,
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              const Text('跳到指定 offset（条目序号，从 0 起）',
                  style: TextStyle(fontSize: 11)),
              const SizedBox(height: 8),
              TextField(
                controller: controller,
                autofocus: true,
                keyboardType: TextInputType.number,
                decoration: const InputDecoration(
                  hintText: '0',
                  isDense: true,
                  border: OutlineInputBorder(),
                ),
              ),
            ],
          ),
        ),
        actions: [
          TextButton(
            onPressed: () {
              Navigator.pop(ctx);
              _jumpToOffsetValue(0);
            },
            child: const Text('重置'),
          ),
          TextButton(
            onPressed: () => Navigator.pop(ctx),
            child: const Text('取消'),
          ),
          FilledButton(
            onPressed: () {
              final v = int.tryParse(controller.text.trim()) ?? 0;
              Navigator.pop(ctx);
              _jumpToOffsetValue(v);
            },
            child: const Text('跳转'),
          ),
        ],
      ),
    );
  }

  /// 榜单依据 modal（2026-11-25：替代页面说明行，内容随当前榜切换）。
  void _showAboutDialog() {
    final scope = widget.form == 'dialogue' ? '对话' : '长篇';
    showDialog<void>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('榜单依据'),
        content: SizedBox(
          width: 320,
          child: Text(
            _board == 'cqs'
                ? '当前榜：口碑（cqs）\n\n按「同代口碑分」降序：\n· 同代 = 同形式 × 同年 × 同题材 × 同收藏档\n· 分数越高 = 口碑在同代同类中越好\n· 不显示精确名次\n\n「位置」榜按「同格收藏位置」（cps）：\n同形式 × 年 × 篇幅档 × 题材里的收藏位置\n\n当前形式：$scope；种子快照 + 库外书现算'
                : '当前榜：位置（cps）\n\n按「同格收藏位置」降序：\n同形式 × 年 × 篇幅档 × 题材里的收藏位置\n\n「口碑」榜按「同代口碑分」（cqs）：\n· 同代 = 同形式 × 同年 × 同题材 × 同收藏档\n· 不显示精确名次\n\n当前形式：$scope；种子快照 + 库外书现算',
            style: const TextStyle(fontSize: 12, height: 1.6),
          ),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(ctx),
            child: const Text('知道了'),
          ),
        ],
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return Scaffold(
      appBar: AppBar(
        title: Text(widget.form == 'dialogue' ? '对话量化榜单' : '量化榜单'),
        actions: [
          IconButton(
            tooltip: '手动翻页',
            // 自绘角标（不用 material Badge：isLabelShown 在本 Flutter
            // 版本不可用）：offset>0 时红点显示当前值。
            icon: Stack(
              clipBehavior: Clip.none,
              alignment: Alignment.center,
              children: [
                const Icon(Icons.keyboard),
                if (_baseOffset > 0)
                  Positioned(
                    right: -4,
                    top: -2,
                    child: Container(
                      padding: const EdgeInsets.symmetric(
                          horizontal: 4, vertical: 1),
                      decoration: BoxDecoration(
                        color: scheme.error,
                        borderRadius: BorderRadius.circular(8),
                      ),
                      child: Text('$_baseOffset',
                          style: const TextStyle(
                              color: Colors.white, fontSize: 9)),
                    ),
                  ),
              ],
            ),
            onPressed: _showPagerDialog,
          ),
          IconButton(
            tooltip: '榜单依据',
            icon: const Icon(Icons.info_outline),
            onPressed: _showAboutDialog,
          ),
          const SizedBox(width: 4),
        ],
      ),
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
          Expanded(
            child: RefreshIndicator(
              onRefresh: () async {
                _session++;
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
