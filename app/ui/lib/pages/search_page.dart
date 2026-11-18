import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../core/providers.dart';
import '../widgets/metric_badge.dart';

/// 本地搜索页（mockups 05 屏定稿）：L1 种子库内 title/author LIKE 匹配
/// （授权书也可搜到），命中数说明行 + 卡片式结果。
class SearchPage extends ConsumerStatefulWidget {
  const SearchPage({super.key});

  @override
  ConsumerState<SearchPage> createState() => _SearchPageState();
}

class _SearchPageState extends ConsumerState<SearchPage> {
  final _controller = TextEditingController();
  String? _query;

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  void _submit(String v) =>
      setState(() => _query = v.trim().isEmpty ? null : v.trim());

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final results = _query == null ? null : ref.watch(searchProvider(_query!));
    return Scaffold(
      appBar: AppBar(
        title: TextField(
          controller: _controller,
          decoration: InputDecoration(
            hintText: '搜索书名 / 作者（本地种子库）',
            border: InputBorder.none,
            suffixIcon: _query == null
                ? null
                : IconButton(
                    icon: const Icon(Icons.close, size: 18),
                    onPressed: () {
                      _controller.clear();
                      setState(() => _query = null);
                    },
                  ),
          ),
          textInputAction: TextInputAction.search,
          onSubmitted: _submit,
        ),
      ),
      body: results == null
          ? Center(
              child: Column(
                mainAxisAlignment: MainAxisAlignment.center,
                children: [
                  Icon(Icons.search,
                      size: 56, color: scheme.onSurfaceVariant.withValues(alpha: .5)),
                  const SizedBox(height: 12),
                  Text('输入关键词搜索 30,878 本种子',
                      style: TextStyle(fontSize: 12, color: scheme.onSurfaceVariant)),
                ],
              ),
            )
          : results.when(
              loading: () => const Center(child: CircularProgressIndicator()),
              error: (e, _) => Center(child: Text('搜索失败：$e')),
              data: (list) => Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Padding(
                    padding: const EdgeInsets.fromLTRB(16, 8, 16, 4),
                    child: Text(
                        '本地搜索 · 命中 ${list.length} 本 · 按收藏排序',
                        style: TextStyle(
                            fontSize: 11, color: scheme.onSurfaceVariant)),
                  ),
                  Expanded(
                    child: list.isEmpty
                        ? Center(
                            child: Text('无匹配结果',
                                style: TextStyle(color: scheme.onSurfaceVariant)))
                        : ListView.builder(
                            padding:
                                const EdgeInsets.fromLTRB(16, 4, 16, 16),
                            itemCount: list.length,
                            itemBuilder: (_, i) {
                              final it = list[i];
                              return Card(
                                margin: const EdgeInsets.only(bottom: 10),
                                child: InkWell(
                                  onTap: () => context.push('/book/${it.nid}'),
                                  borderRadius: BorderRadius.circular(16),
                                  child: Padding(
                                    padding: const EdgeInsets.all(12),
                                    child: Row(
                                      children: [
                                        Container(
                                          width: 52,
                                          height: 72,
                                          decoration: BoxDecoration(
                                            color: scheme.surface,
                                            border: Border.all(
                                                color: scheme.outline
                                                    .withValues(alpha: .4)),
                                            borderRadius:
                                                BorderRadius.circular(6),
                                          ),
                                          alignment: Alignment.center,
                                          child: Text(
                                              it.title.isEmpty
                                                  ? '书'
                                                  : it.title.characters.first,
                                              style: TextStyle(
                                                  fontFamily: 'serif',
                                                  fontSize: 24,
                                                  color: scheme
                                                      .onSurfaceVariant)),
                                        ),
                                        const SizedBox(width: 12),
                                        Expanded(
                                          child: Column(
                                            crossAxisAlignment:
                                                CrossAxisAlignment.start,
                                            children: [
                                              Text(it.title,
                                                  maxLines: 1,
                                                  overflow:
                                                      TextOverflow.ellipsis,
                                                  style: Theme.of(context)
                                                      .textTheme
                                                      .titleLarge
                                                      ?.copyWith(
                                                          fontSize: 13.5)),
                                              const SizedBox(height: 3),
                                              Text(
                                                  '${it.author} · ${it.estYear}'
                                                  '${it.genre != null ? ' · ${it.genre}' : ''}',
                                                  style: TextStyle(
                                                      fontSize: 11,
                                                      color: scheme
                                                          .onSurfaceVariant)),
                                              const SizedBox(height: 5),
                                              Container(
                                                padding: const EdgeInsets
                                                    .symmetric(
                                                    horizontal: 8,
                                                    vertical: 1),
                                                decoration: BoxDecoration(
                                                    border: Border.all(
                                                        color: scheme.outline
                                                            .withValues(
                                                                alpha: .5)),
                                                    borderRadius:
                                                        BorderRadius.circular(
                                                            999)),
                                                child: Row(
                                                    mainAxisSize:
                                                        MainAxisSize.min,
                                                    children: [
                                                      Icon(MetricIcons.favs,
                                                          size: 11,
                                                          color: scheme
                                                              .onSurfaceVariant),
                                                      const SizedBox(width: 2),
                                                      Text(
                                                          '收藏 ${_wan(it.favs ?? 0)}',
                                                          style: TextStyle(
                                                              fontSize: 10,
                                                              color: scheme
                                                                  .onSurfaceVariant)),
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
                            },
                          ),
                  ),
                ],
              ),
            ),
    );
  }
}

String _wan(int n) {
  if (n >= 10000) return '${(n / 10000).toStringAsFixed(0)}万';
  return '$n';
}
