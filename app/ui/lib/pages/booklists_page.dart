import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../core/providers.dart';
import '../data/api/strata_api.dart';
import '../widgets/back_to_top.dart';

/// 官方书单浏览页（docs/booklist-in-app.md）：官方 API 无枚举动作，引擎
/// 顺序 id 探测（每窗 10 个、逐个走限速器——首窗 ≈10 秒，当日再访 24h
/// 缓存秒回）。顶部 #id 跳转框直跳某号所在窗口；行卡：#id + 标题 +
/// 简介 2 行 + 作者 + N 部作品 + 更新日期。
class BooklistsPage extends ConsumerStatefulWidget {
  const BooklistsPage({super.key});

  @override
  ConsumerState<BooklistsPage> createState() => _BooklistsPageState();
}

class _BooklistsPageState extends ConsumerState<BooklistsPage> {
  final _scroll = ScrollController();
  final _idCtrl = TextEditingController();

  bool _showTop = false;
  int _page = 0;
  List<Booklist> _items = const [];
  bool _loading = true;
  bool _loadingMore = false;
  bool _moreFailed = false;
  bool _done = false;
  String? _error;

  @override
  void initState() {
    super.initState();
    _scroll.addListener(_onScroll);
    _loadPage(1, reset: true);
  }

  @override
  void dispose() {
    _scroll.dispose();
    _idCtrl.dispose();
    super.dispose();
  }

  void _onScroll() {
    final show = _scroll.hasClients && _scroll.offset > 500;
    if (show != _showTop) setState(() => _showTop = show);
    if (_loading || _loadingMore || _done || _moreFailed) return;
    if (_scroll.position.pixels >=
        _scroll.position.maxScrollExtent - 400) {
      _loadPage(_page + 1, reset: false);
    }
  }

  Future<void> _loadPage(int page, {required bool reset}) async {
    final handle = await ref.read(bootProvider.future);
    if (!mounted) return;
    if (reset) {
      if (_loading) return;
      setState(() {
        _loading = true;
        _error = null;
        _items = const [];
        _page = 0;
        _done = false;
        _moreFailed = false;
      });
    } else {
      if (_loadingMore) return;
      setState(() => _loadingMore = true);
    }
    try {
      final r = await handle.api.booklists(page: page);
      if (!mounted) return;
      setState(() {
        if (reset) {
          _items = r.items;
        } else {
          _items = [..._items, ...r.items];
        }
        _page = r.page;
        _done = r.done;
        _loading = false;
        _loadingMore = false;
      });
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _loading = false;
        _loadingMore = false;
        if (reset) {
          _error = '书单加载失败：$e';
        } else {
          _moreFailed = true;
        }
      });
    }
  }

  /// #id 跳转：直跳该号所在窗口（引擎页窗 = 10 个连续号）。
  void _jumpTo(int id) {
    _idCtrl.clear();
    _loadPage((id - 1) ~/ 10 + 1, reset: true);
  }

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return Scaffold(
      appBar: AppBar(title: const Text('书单')),
      body: Stack(
        children: [
          ListView(
            controller: _scroll,
            padding: const EdgeInsets.symmetric(vertical: 8),
            children: [
              _jumpRow(context),
              if (_loading && _page == 0)
                Padding(
                  padding: const EdgeInsets.symmetric(vertical: 48),
                  child: Center(
                    child: Column(
                      children: [
                        const CircularProgressIndicator(strokeWidth: 2),
                        const SizedBox(height: 12),
                        Text(
                          '正在探测书单（首窗约 10 秒）…',
                          style:
                              TextStyle(fontSize: 11, color: scheme.onSurfaceVariant),
                        ),
                      ],
                    ),
                  ),
                )
              else if (_error != null && _items.isEmpty)
                Padding(
                  padding: const EdgeInsets.symmetric(vertical: 48),
                  child: Center(
                    child: Column(
                      children: [
                        Text(
                          _error!,
                          style: TextStyle(
                              fontSize: 12, color: scheme.onSurfaceVariant),
                        ),
                        const SizedBox(height: 12),
                        FilledButton(
                          onPressed: () => _loadPage(1, reset: true),
                          child:
                              const Text('重试', style: TextStyle(fontSize: 12.5)),
                        ),
                      ],
                    ),
                  ),
                )
              else ...[
                for (final b in _items) _row(context, b),
                if (_loadingMore)
                  const Padding(
                    padding: EdgeInsets.symmetric(vertical: 16),
                    child: Center(
                      child: CircularProgressIndicator(strokeWidth: 2),
                    ),
                  )
                else if (_moreFailed)
                  Padding(
                    padding: const EdgeInsets.symmetric(vertical: 16),
                    child: Center(
                      child: TextButton(
                        onPressed: () => _loadPage(_page + 1, reset: false),
                        child: const Text('加载失败，点按重试'),
                      ),
                    ),
                  )
                else if (_done && _items.isNotEmpty)
                  Padding(
                    padding: const EdgeInsets.fromLTRB(0, 16, 0, 24),
                    child: Center(
                      child: Text(
                        '— 已探到末尾 —',
                        style: TextStyle(
                            fontSize: 11, color: scheme.onSurfaceVariant),
                      ),
                    ),
                  )
              ],
            ],
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
    );
  }

  Widget _jumpRow(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.fromLTRB(16, 4, 16, 8),
      child: Row(
        children: [
          Expanded(
            child: TextField(
              controller: _idCtrl,
              keyboardType: TextInputType.number,
              maxLength: 4,
              style: const TextStyle(fontSize: 13),
              decoration: InputDecoration(
                isDense: true,
                hintText: '跳转书单号（如 523）',
                contentPadding:
                    const EdgeInsets.symmetric(vertical: 8),
              ),
              onSubmitted: (v) {
                final n = int.tryParse(v);
                if (n != null && n > 0) _jumpTo(n);
              },
            ),
          ),
          const SizedBox(width: 8),
          FilledButton(
            onPressed: () {
              final n = int.tryParse(_idCtrl.text);
              if (n != null && n > 0) _jumpTo(n);
            },
            child: const Text('跳转', style: TextStyle(fontSize: 12.5)),
          ),
        ],
      ),
    );
  }

  Widget _row(BuildContext context, Booklist b) {
    final scheme = Theme.of(context).colorScheme;
    final meta = [
      '${b.novelNum} 部作品',
      if (b.updated.isNotEmpty) b.updated,
    ].join('  ');
    return InkWell(
      onTap: () => context.push('/booklists/${b.id}'),
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 10),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text.rich(
              TextSpan(
                children: [
                  TextSpan(
                    text: '#${b.id} ',
                    style: TextStyle(
                      fontSize: 12.5,
                      fontWeight: FontWeight.w700,
                      color: scheme.primary,
                    ),
                  ),
                  TextSpan(
                    text: b.title,
                    style: const TextStyle(
                        fontSize: 13.5, fontWeight: FontWeight.w600),
                  ),
                ],
              ),
            ),
            if (b.summary.isNotEmpty) ...[
              const SizedBox(height: 3),
              Text(
                b.summary,
                style:
                    TextStyle(fontSize: 11.5, color: scheme.onSurfaceVariant),
                maxLines: 2,
                overflow: TextOverflow.ellipsis,
              ),
            ],
            const SizedBox(height: 3),
            Row(
              children: [
                if (b.author.isNotEmpty)
                  Flexible(
                    child: Text(
                      b.author + (b.vip ? '  VIP' : ''),
                      style: TextStyle(
                          fontSize: 10.5, color: scheme.onSurfaceVariant),
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                    ),
                  ),
                const Spacer(),
                Text(
                  meta,
                  style: TextStyle(
                      fontSize: 10.5, color: scheme.onSurfaceVariant),
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }
}
