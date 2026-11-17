import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../core/providers.dart';

/// 本地搜索页：L1 种子库内 title/author LIKE 匹配（授权书也可搜到）。
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

  @override
  Widget build(BuildContext context) {
    final results =
        _query == null ? null : ref.watch(searchProvider(_query!));
    return Scaffold(
      appBar: AppBar(
        title: TextField(
          controller: _controller,
          decoration: const InputDecoration(
            hintText: '搜索书名 / 作者（本地种子库）',
            border: InputBorder.none,
          ),
          textInputAction: TextInputAction.search,
          onSubmitted: (v) =>
              setState(() => _query = v.trim().isEmpty ? null : v.trim()),
        ),
      ),
      body: results == null
          ? const Center(child: Text('输入关键词搜索 30,878 本种子'))
          : results.when(
              loading: () => const Center(child: CircularProgressIndicator()),
              error: (e, _) => Center(child: Text('搜索失败：$e')),
              data: (list) => list.isEmpty
                  ? const Center(child: Text('无匹配结果'))
                  : ListView.builder(
                      itemCount: list.length,
                      itemBuilder: (_, i) {
                        final it = list[i];
                        return ListTile(
                          title: Text(it.title),
                          subtitle: Text(
                              '${it.author} · ${it.estYear}'
                              '${it.genre != null ? ' · ${it.genre}' : ''}'),
                          trailing: Text('${it.favs ?? 0} 收藏'),
                          onTap: () => context.go('/book/${it.nid}'),
                        );
                      },
                    ),
            ),
    );
  }
}
