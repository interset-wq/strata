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

  // 官方 App 分享出的书籍链接形态（PC /Novel/{nid}/、移动版 /b/{nid}/）。
  static final RegExp _nidLink =
      RegExp(r'sfacg\.com/(?:Novel|b)/(\d+)', caseSensitive: false);

  /// 查询规范化：粘贴进来的 SFACG 书籍链接自动提取 nid 转成 #id；
  /// #id 是唯一的 nid 精确搜索入口，其余输入（含纯数字）原样走关键词。
  String _normalizeQuery(String raw) {
    if (raw.startsWith('#')) return raw;
    final m = _nidLink.firstMatch(raw);
    if (m != null) return '#${m.group(1)}';
    return raw;
  }

  void _submit(String v) {
    final q = _normalizeQuery(v.trim());
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
        _remoteError = StrataApiException.userMessage(e);
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
            hintText: '搜索书名、作者或 #id（内置库）',
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
              error: (e, _) =>
                  Center(child: Text('搜索失败：${StrataApiException.userMessage(e)}')),
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
          Text('搜索书名、作者或 #id（内置库）',
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
    final nidMiss = list.isEmpty && _isNIDQuery(_query);
    return ListView.builder(
      padding: const EdgeInsets.fromLTRB(16, 4, 16, 16),
      itemCount: list.length + (nidMiss ? 1 : 0) + _remoteExtraRows(),
      itemBuilder: (_, i) {
        if (i < list.length) return _localCard(context, scheme, list[i]);
        i -= list.length;
        if (nidMiss && i == 0) {
          return _nidMissCard(context, scheme, _query!.substring(1));
        }
        i -= 1;
        return _remoteRow(context, scheme, i, list.length);
      },
    );
  }

  /// nid 查询判定（与引擎侧同规则：仅 # 前缀 = 按 id 精确找书；
  /// 纯数字与其他输入一律走关键词）。
  bool _isNIDQuery(String? q) {
    if (q == null || !q.startsWith('#') || q.length < 2) return false;
    for (final r in q.substring(1).runes) {
      if (r < 0x30 || r > 0x39) return false;
    }
    return true;
  }

  /// 「未收录」行（nid 精确查找未命中）：内置库与已收录库都没有此书——
  /// 点开先 rank-seed 预写（纯本地写，毫秒级），详情页首帧即渲染、后台
  /// refresh 补全（与榜单/清单页库外书同路径；不预写会整页 404 等待
  /// 同步抓取，体感极慢）。
  Widget _nidMissCard(BuildContext context, ColorScheme scheme, String nid) {
    return Card(
      margin: const EdgeInsets.only(bottom: 10),
      child: InkWell(
        onTap: () async {
          final n = int.tryParse(nid) ?? 0;
          try {
            final h = await ref.read(bootProvider.future);
            await h.api.rankSeed(nid: n, title: 'nid $nid', coverUrl: '');
          } catch (_) {
            // 预写失败也进详情：详情页会自行报错可重试。
          }
          if (context.mounted) context.push('/book/$nid');
        },
        borderRadius: BorderRadius.circular(16),
        child: Padding(
          padding: const EdgeInsets.all(12),
          child: Row(
            children: [
              ClipRRect(
                borderRadius: BorderRadius.circular(6),
                child: coverImage(null, int.tryParse(nid) ?? 0,
                    width: 52, height: 72),
              ),
              const SizedBox(width: 12),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text('未收录的书',
                        style: Theme.of(context)
                            .textTheme
                            .titleLarge
                            ?.copyWith(fontSize: 13.5)),
                    const SizedBox(height: 5),
                    Text(
                        'nid $nid · 内置库与已收录库都没有，点开收录并查看',
                        style: TextStyle(
                            fontSize: 11, color: scheme.onSurfaceVariant)),
                  ],
                ),
              ),
            ],
          ),
        ),
      ),
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
                child: coverImage(it.coverUrl, it.nid,
                    width: 52, height: 72),
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
                        if (!it.inSeed) _badge(context, '新书'),
                      ],
                    ),
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
                  onPressed: _remoteLoading ? null : _searchRemote,
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
                child: coverImage(it.coverUrl, it.nid,
                    width: 52, height: 72),
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
