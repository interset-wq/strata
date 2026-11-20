import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../core/providers.dart';
import '../data/api/strata_api.dart';
import '../widgets/default_cover.dart';
import '../widgets/metric_badge.dart';

/// 搜索页（docs/08 §search + §search-remote）：L1 段为内置库 LIKE 搜索
/// （真封面 + 作者名入口），官方全站搜索手动触发（30 条硬上限、静默限流
/// 明确提示、库外命中标「新书」并写 discovered），空态为最近搜索 chips。
class SearchPage extends ConsumerStatefulWidget {
  const SearchPage({super.key});

  @override
  ConsumerState<SearchPage> createState() => _SearchPageState();
}

class _SearchPageState extends ConsumerState<SearchPage> {
  final _controller = TextEditingController();
  String? _query;

  // 全站搜索状态（手动触发；官方搜索有静默限流——docs/sfacg-endpoints
  // §2.1，引擎侧另有 6 秒自冷却）。
  bool _remoteLoading = false;
  bool _rateLimited = false;
  int? _declared;
  String? _remoteError;
  List<RemoteSearchItem> _remoteItems = const [];

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  void _submit(String v) {
    final q = v.trim();
    setState(() {
      _query = q.isEmpty ? null : q;
      // 新词使全站搜索旧结果失效。
      _remoteItems = const [];
      _rateLimited = false;
      _declared = null;
      _remoteError = null;
      _remoteLoading = false;
    });
    if (_query != null) ref.invalidate(searchHistoryProvider);
  }

  Future<void> _searchRemote() async {
    final q = _query;
    if (q == null || _remoteLoading) return;
    setState(() {
      _remoteLoading = true;
      _rateLimited = false;
      _remoteError = null;
      _remoteItems = const [];
    });
    try {
      final h = await ref.read(bootProvider.future);
      final r = await h.api.searchRemote(q);
      if (!mounted) return;
      setState(() {
        _remoteLoading = false;
        _rateLimited = r.rateLimited;
        _declared = r.declared;
        _remoteItems = r.items;
      });
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _remoteLoading = false;
        _remoteError = e.toString();
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final results = _query == null ? null : ref.watch(searchProvider(_query!));
    return Scaffold(
      appBar: AppBar(
        title: TextField(
          controller: _controller,
          decoration: InputDecoration(
            hintText: '搜索书名 / 作者（内置库）',
            border: InputBorder.none,
            suffixIcon: _query == null
                ? null
                : IconButton(
                    icon: const Icon(Icons.close, size: 18),
                    onPressed: () {
                      _controller.clear();
                      _submit('');
                    },
                  ),
          ),
          textInputAction: TextInputAction.search,
          onSubmitted: _submit,
        ),
      ),
      body: results == null
          ? _emptyState(context, scheme)
          : results.when(
              loading: () => const Center(child: CircularProgressIndicator()),
              error: (e, _) => Center(child: Text('搜索失败：$e')),
              data: (list) => _resultList(context, scheme, list),
            ),
    );
  }

  Widget _emptyState(BuildContext context, ColorScheme scheme) {
    final history = ref.watch(searchHistoryProvider);
    return Center(
      child: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          Icon(Icons.search,
              size: 56, color: scheme.onSurfaceVariant.withValues(alpha: .5)),
          const SizedBox(height: 12),
          Text('搜索书名 / 作者（内置库）',
              style: TextStyle(fontSize: 12, color: scheme.onSurfaceVariant)),
          const SizedBox(height: 20),
          history.when(
            data: (words) => words.isEmpty
                ? const SizedBox.shrink()
                : Column(
                    children: [
                      Text('最近搜索',
                          style: TextStyle(
                              fontSize: 11,
                              color: scheme.onSurfaceVariant)),
                      const SizedBox(height: 8),
                      Padding(
                        padding: const EdgeInsets.symmetric(horizontal: 24),
                        child: Wrap(
                          spacing: 8,
                          runSpacing: 8,
                          alignment: WrapAlignment.center,
                          children: [
                            for (final w in words)
                              ActionChip(
                                label: Text(w, style: const TextStyle(fontSize: 12)),
                                onPressed: () {
                                  _controller.text = w;
                                  _submit(w);
                                },
                              ),
                          ],
                        ),
                      ),
                    ],
                  ),
            loading: () => const SizedBox.shrink(),
            error: (_, _) => const SizedBox.shrink(),
          ),
        ],
      ),
    );
  }

  Widget _resultList(
      BuildContext context, ColorScheme scheme, List<SearchItem> list) {
    return ListView.builder(
      padding: const EdgeInsets.fromLTRB(16, 4, 16, 16),
      itemCount: list.length + _remoteExtraRows(),
      itemBuilder: (_, i) {
        if (i < list.length) return _localCard(context, scheme, list[i]);
        return _remoteRow(context, scheme, i - list.length, list.length);
      },
    );
  }

  int _remoteExtraRows() {
    if (_remoteLoading || _remoteError != null || _rateLimited) return 1;
    if (_remoteItems.isNotEmpty) return _remoteItems.length + 1;
    return 1; // 「搜全站」按钮行
  }

  Widget _localCard(BuildContext context, ColorScheme scheme, SearchItem it) {
    return Card(
      margin: const EdgeInsets.only(bottom: 10),
      child: InkWell(
        onTap: () => context.push('/book/${it.nid}'),
        borderRadius: BorderRadius.circular(16),
        child: Padding(
          padding: const EdgeInsets.all(12),
          child: Row(
            children: [
              ClipRRect(
                borderRadius: BorderRadius.circular(6),
                child: Image.network(
                  coverImageUrl(it.coverUrl) ?? defaultCoverUrl(it.nid),
                  width: 52,
                  height: 72,
                  fit: BoxFit.cover,
                  loadingBuilder: coverLoadingBuilder,
                  errorBuilder: (_, _, _) => Image.network(
                    defaultCoverUrl(it.nid),
                    width: 52,
                    height: 72,
                    fit: BoxFit.cover,
                    errorBuilder: (_, _, _) => ColoredBox(
                        color: scheme.primary.withValues(alpha: .15)),
                  ),
                ),
              ),
              const SizedBox(width: 12),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(it.title,
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        style: Theme.of(context)
                            .textTheme
                            .titleLarge
                            ?.copyWith(fontSize: 13.5)),
                    const SizedBox(height: 3),
                    InkWell(
                      // 作者入口：点作者名重搜（与作者页同语义入口）。
                      onTap: () {
                        _controller.text = it.author;
                        _submit(it.author);
                      },
                      child: Text(it.author,
                          style: TextStyle(
                              fontSize: 11,
                              color: scheme.primary,
                              decoration: TextDecoration.underline,
                              decorationColor:
                                  scheme.primary.withValues(alpha: .4))),
                    ),
                    const SizedBox(height: 5),
                    Container(
                      padding: const EdgeInsets.symmetric(
                          horizontal: 8, vertical: 1),
                      decoration: BoxDecoration(
                          border: Border.all(
                              color:
                                  scheme.outline.withValues(alpha: .5)),
                          borderRadius: BorderRadius.circular(999)),
                      child: Row(
                          mainAxisSize: MainAxisSize.min,
                          children: [
                            Icon(MetricIcons.favs,
                                size: 11,
                                color: scheme.onSurfaceVariant),
                            const SizedBox(width: 2),
                            Text('收藏 ${_wan(it.favs ?? 0)}',
                                style: TextStyle(
                                    fontSize: 10,
                                    color: scheme.onSurfaceVariant)),
                          ]),
                    ),
                  ],
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _remoteRow(BuildContext context, ColorScheme scheme, int row,
      int localCount) {
    // 逐段渲染：按钮 / loading / 错误 / 限流提示 / 结果（口径行 + 卡片）。
    if (row == 0) {
      Widget child;
      if (_remoteLoading) {
        child = const Row(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            SizedBox(
                width: 14,
                height: 14,
                child: CircularProgressIndicator(strokeWidth: 2)),
            SizedBox(width: 10),
            Text('正在搜全站…', style: TextStyle(fontSize: 12)),
          ],
        );
      } else if (_remoteError != null) {
        child = const Text('搜全站失败，稍后重试', style: TextStyle(fontSize: 12));
      } else if (_rateLimited) {
        child = const Text('官方搜索已被限流，请几分钟后再试',
            style: TextStyle(fontSize: 12));
      } else if (_remoteItems.isNotEmpty) {
        child = Text(
          '全站 · 显示 ${_remoteItems.length} 条（官方声明 $_declared 条，上限 30）'
          ' · 内置库命中标「库内」',
          style: TextStyle(fontSize: 11, color: scheme.onSurfaceVariant),
        );
      } else {
        child = const Text('搜全站（官方，最多 30 条）',
            style: TextStyle(fontSize: 12));
      }
      return Padding(
        padding: const EdgeInsets.symmetric(vertical: 10),
        child: Center(
          child: _remoteLoading
              ? child
              : ActionChip(
                  label: child,
                  onPressed: _remoteError != null ? _searchRemote : null,
                  avatar: _remoteError != null
                      ? null
                      : Icon(Icons.travel_explore,
                          size: 16, color: scheme.primary),
                ),
        ),
      );
    }
    final it = _remoteItems[row - 1];
    return _remoteCard(context, scheme, it);
  }

  Widget _remoteCard(
      BuildContext context, ColorScheme scheme, RemoteSearchItem it) {
    return Card(
      margin: const EdgeInsets.only(bottom: 10),
      child: InkWell(
        onTap: () => context.push('/book/${it.nid}'),
        borderRadius: BorderRadius.circular(16),
        child: Padding(
          padding: const EdgeInsets.all(12),
          child: Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              ClipRRect(
                borderRadius: BorderRadius.circular(6),
                child: Image.network(
                  coverImageUrl(it.coverUrl) ?? defaultCoverUrl(it.nid),
                  width: 52,
                  height: 72,
                  fit: BoxFit.cover,
                  loadingBuilder: coverLoadingBuilder,
                  errorBuilder: (_, _, _) => Image.network(
                    defaultCoverUrl(it.nid),
                    width: 52,
                    height: 72,
                    fit: BoxFit.cover,
                    errorBuilder: (_, _, _) => ColoredBox(
                        color: scheme.primary.withValues(alpha: .15)),
                  ),
                ),
              ),
              const SizedBox(width: 12),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(
                      children: [
                        Expanded(
                          child: Text(it.title,
                              maxLines: 1,
                              overflow: TextOverflow.ellipsis,
                              style: Theme.of(context)
                                  .textTheme
                                  .titleLarge
                                  ?.copyWith(fontSize: 13.5)),
                        ),
                        _badge(context, it.inSeed ? '库内' : '新书',
                            filled: it.inSeed),
                      ],
                    ),
                    if (it.author.isNotEmpty) ...[
                      const SizedBox(height: 3),
                      Text(it.author,
                          style: TextStyle(
                              fontSize: 11,
                              color: scheme.onSurfaceVariant)),
                    ],
                    if (it.summary != null && it.summary!.isNotEmpty) ...[
                      const SizedBox(height: 5),
                      Text(it.summary!,
                          style: TextStyle(
                              fontSize: 11,
                              color: scheme.onSurfaceVariant),
                          maxLines: 2,
                          overflow: TextOverflow.ellipsis),
                    ],
                  ],
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _badge(BuildContext context, String text, {bool filled = false}) {
    final scheme = Theme.of(context).colorScheme;
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 1),
      decoration: BoxDecoration(
        color: filled ? scheme.primary : null,
        border: Border.all(color: scheme.primary),
        borderRadius: BorderRadius.circular(999),
      ),
      child: Text(text,
          style: TextStyle(
              fontSize: 10,
              color: filled ? scheme.onPrimary : scheme.primary)),
    );
  }
}

String _wan(int n) {
  if (n >= 10000) return '${(n / 10000).toStringAsFixed(0)}万';
  return '$n';
}
