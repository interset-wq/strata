import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../core/providers.dart';
import '../data/api/strata_api.dart';

/// 题材枚举与引擎 api.go 保持一致（契约 08）。
const genres = [
  '魔幻', '玄幻', '古风', '科幻', '校园', '都市', '游戏', '同人', '悬疑',
];

/// 榜单页：分位榜 / 题材榜 / 短篇榜 / 新书榜。
class RankingsPage extends ConsumerWidget {
  const RankingsPage({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final meta = ref.watch(metaProvider);
    final genMax = meta.value?.manifest.genMax ?? 2025;
    final genMin = meta.value?.manifest.genMin ?? 2007;

    return DefaultTabController(
      length: 4,
      child: Scaffold(
        appBar: AppBar(
          title: const Text('榜单'),
          actions: [
            IconButton(
              icon: const Icon(Icons.search),
              tooltip: '搜索',
              onPressed: () => context.go('/search'),
            ),
          ],
          bottom: const TabBar(
            isScrollable: true,
            tabs: [
              Tab(text: '分位榜'),
              Tab(text: '题材榜'),
              Tab(text: '短篇榜'),
              Tab(text: '新书榜'),
            ],
          ),
        ),
        body: TabBarView(
          children: [
            _FavsTab(genMin: genMin, genMax: genMax, genre: null),
            _FavsTab(genMin: genMin, genMax: genMax, genre: '魔幻'),
            _ShortTab(),
            _NewTab(),
          ],
        ),
      ),
    );
  }
}

class _FavsTab extends ConsumerStatefulWidget {
  final int genMin, genMax;
  final String? genre;
  const _FavsTab({required this.genMin, required this.genMax, this.genre});

  @override
  ConsumerState<_FavsTab> createState() => _FavsTabState();
}

class _FavsTabState extends ConsumerState<_FavsTab> {
  late int year = widget.genMax;
  late String? genre = widget.genre;

  @override
  void didUpdateWidget(_FavsTab old) {
    super.didUpdateWidget(old);
    if (old.genre != widget.genre) genre = widget.genre;
  }

  @override
  Widget build(BuildContext context) {
    final arg = (year: year, genre: genre);
    final items = ref.watch(favsRankingProvider(arg));
    final selectors = <Widget>[
      DropdownButton<int>(
        value: year,
        items: [
          for (int y = widget.genMax; y >= widget.genMin; y--)
            DropdownMenuItem(value: y, child: Text('$y')),
        ],
        onChanged: (v) => setState(() => year = v!),
      ),
    ];
    if (widget.genre != null) {
      selectors.add(
        DropdownButton<String>(
          value: genre,
          items: [
            const DropdownMenuItem(value: null, child: Text('全部')),
            for (final g in genres)
              DropdownMenuItem(value: g, child: Text(g)),
          ],
          onChanged: (v) => setState(() => genre = v),
        ),
      );
    }
    return Column(
      children: [
        Padding(
          padding: const EdgeInsets.symmetric(horizontal: 16),
          child: Row(children: [...selectors, const Spacer()]),
        ),
        Expanded(child: items.when(
          loading: () => const Center(child: CircularProgressIndicator()),
          error: (e, _) => Center(child: Text('加载失败：$e')),
          data: (list) => list.isEmpty
              ? const Center(child: Text('该年份/题材下无种子书目'))
              : ListView.builder(
                  itemCount: list.length,
                  itemBuilder: (_, i) => _RankTile(item: list[i]),
                ),
        )),
      ],
    );
  }
}

class _ShortTab extends ConsumerWidget {
  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final items = ref.watch(shortRankingProvider);
    return items.when(
      loading: () => const Center(child: CircularProgressIndicator()),
      error: (e, _) => Center(child: Text('加载失败：$e')),
      data: (list) => list.isEmpty
          ? const Center(child: Text('无数据'))
          : ListView.builder(
              itemCount: list.length,
              itemBuilder: (_, i) {
                final it = list[i];
                return ListTile(
                  leading: Text('${it.rank}'),
                  title: Text(it.title),
                  subtitle: Text('${it.author} · ${it.estYear}'),
                  trailing: Text('${it.favs} 收藏'),
                  onTap: () => context.go('/book/${it.nid}'),
                );
              },
            ),
    );
  }
}

class _NewTab extends ConsumerWidget {
  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final items = ref.watch(newRankingProvider);
    return items.when(
      loading: () => const Center(child: CircularProgressIndicator()),
      error: (e, _) => Center(child: Text('加载失败：$e')),
      data: (list) => list.isEmpty
          ? const Center(child: Text('无数据'))
          : ListView.builder(
              itemCount: list.length,
              itemBuilder: (_, i) => _RankTile(item: list[i]),
            ),
    );
  }
}

class _RankTile extends StatelessWidget {
  final RankItem item;
  const _RankTile({required this.item});

  @override
  Widget build(BuildContext context) {
    return ListTile(
      leading: Text('${item.rank}'),
      title: Text(item.title),
      subtitle: Text('${item.author} · ${item.estYear}'
          '${item.genre != null ? ' · ${item.genre}' : ''}'),
      trailing: Text(
        'pctl ${item.favPctl.toStringAsFixed(1)}',
        style: Theme.of(context).textTheme.bodySmall,
      ),
      onTap: () => context.go('/book/${item.nid}'),
    );
  }
}
