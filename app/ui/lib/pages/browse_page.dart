import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../core/providers.dart';
import '../data/api/strata_api.dart';

/// 二级浏览页模式：宫格四入口共用，数据维度不同。
enum BrowseMode { category, status, contest, short }

/// 二级浏览页：分类（题材榜）/ 状态（连载/完结）/ 比赛（征文作品）/
/// 短篇（短篇榜）。榜单卡片按分位展示，口径与榜单页一致（排除授权书）。
class BrowsePage extends ConsumerStatefulWidget {
  final BrowseMode mode;

  const BrowsePage({super.key, required this.mode});

  @override
  ConsumerState<BrowsePage> createState() => _BrowsePageState();
}

class _BrowsePageState extends ConsumerState<BrowsePage> {
  String? _filter; // 分类页=题材名；状态页=状态文案；比赛页恒 "1"

  static const _genres = ['魔幻', '玄幻', '古风', '科幻', '校园', '都市', '游戏', '悬疑'];

  String get _title => switch (widget.mode) {
        BrowseMode.category => '分类找书',
        BrowseMode.status => '按状态浏览',
        BrowseMode.contest => '征文比赛作品',
        BrowseMode.short => '短篇榜',
      };

  @override
  Widget build(BuildContext context) {
    final meta = ref.watch(metaProvider);
    final year = meta.value?.manifest.genMax;
    return Scaffold(
      appBar: AppBar(title: Text(_title)),
      body: year == null
          ? const Center(child: CircularProgressIndicator())
          : ListView(
              padding: const EdgeInsets.all(16),
              children: [
                if (widget.mode == BrowseMode.category) _genreChips(context),
                if (widget.mode == BrowseMode.status) _statusChips(context),
                if (widget.mode != BrowseMode.short)
                  _BoardCards(
                    key: ValueKey('${widget.mode}-$_filter-$year'),
                    year: year,
                    mode: widget.mode,
                    filter: _filter,
                  ),
                if (widget.mode == BrowseMode.short)
                  _ShortCards(key: ValueKey('short-$year'), year: year),
              ],
            ),
    );
  }

  Widget _genreChips(BuildContext context) {
    return _filterChips(
      context,
      _genres,
      _filter,
      (g) => setState(() => _filter = g),
    );
  }

  Widget _statusChips(BuildContext context) {
    return _filterChips(
      context,
      const ['连载中', '已完结'],
      _filter,
      (s) => setState(() => _filter = s),
    );
  }
}

class _BoardCards extends ConsumerWidget {
  final int year;
  final BrowseMode mode;
  final String? filter;

  const _BoardCards({super.key, required this.year, required this.mode, this.filter});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final handleRef = ref.watch(bootProvider.future);
    return FutureBuilder(
      future: handleRef.then((h) => h.api.rankingFavs(
            year: year,
            genre: mode == BrowseMode.category ? filter : null,
            status: mode == BrowseMode.status ? filter : null,
            contest: mode == BrowseMode.contest ? '1' : null,
          )),
      builder: (context, snap) {
        if (snap.connectionState != ConnectionState.done) {
          return const Center(
              child: Padding(
            padding: EdgeInsets.all(24),
            child: CircularProgressIndicator(),
          ));
        }
        if (snap.hasError) {
          return Padding(
            padding: const EdgeInsets.all(16),
            child: Text('加载失败：${snap.error}'),
          );
        }
        final items = snap.data ?? const <RankItem>[];
        if (items.isEmpty) {
          return const Padding(
            padding: EdgeInsets.all(16),
            child: Text('该筛选下暂无作品', style: TextStyle(color: Colors.grey)),
          );
        }
        return Column(
          children: [
            for (final it in items) _BoardCard(item: it),
          ],
        );
      },
    );
  }
}

class _ShortCards extends ConsumerWidget {
  final int year;

  const _ShortCards({super.key, required this.year});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    return ref.watch(shortRankingProvider).when(
          loading: () => const Center(child: CircularProgressIndicator()),
          error: (e, _) => Padding(
            padding: const EdgeInsets.all(16),
            child: Text('加载失败：$e'),
          ),
          data: (items) => Column(
            children: [
              for (final it in items) _ShortCard(item: it),
            ],
          ),
        );
  }
}

class _BoardCard extends StatelessWidget {
  final RankItem item;

  const _BoardCard({required this.item});

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return Card(
      margin: const EdgeInsets.only(bottom: 10),
      child: InkWell(
        onTap: () => context.push('/book/${item.nid}'),
        borderRadius: BorderRadius.circular(16),
        child: Padding(
          padding: const EdgeInsets.all(14),
          child: Row(
            children: [
              SizedBox(
                width: 34,
                child: Text('#${item.rank}',
                    style: TextStyle(
                        fontFamily: 'serif',
                        fontSize: 14,
                        color: item.rank <= 3
                            ? scheme.primary
                            : scheme.onSurfaceVariant,
                        fontWeight: FontWeight.w700)),
              ),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(item.title,
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        style: Theme.of(context)
                            .textTheme
                            .titleLarge
                            ?.copyWith(fontSize: 15)),
                    const SizedBox(height: 4),
                    Text(
                      '${item.author} · ${item.genre ?? '未分类'} · ${item.estYear} 代',
                      style: TextStyle(
                          fontSize: 11, color: scheme.onSurfaceVariant),
                    ),
                  ],
                ),
              ),
              Column(
                crossAxisAlignment: CrossAxisAlignment.end,
                children: [
                  Text('${_wan(item.favs)} 收藏',
                      style: TextStyle(
                          fontSize: 12,
                          fontWeight: FontWeight.w700,
                          color: scheme.primary)),
                  const SizedBox(height: 4),
                  Text('分位 ${item.favPctl.toStringAsFixed(1)}%',
                      style: TextStyle(
                          fontSize: 10, color: scheme.onSurfaceVariant)),
                ],
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _ShortCard extends StatelessWidget {
  final ShortItem item;

  const _ShortCard({required this.item});

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return Card(
      margin: const EdgeInsets.only(bottom: 10),
      child: InkWell(
        onTap: () => context.push('/book/${item.nid}'),
        borderRadius: BorderRadius.circular(16),
        child: Padding(
          padding: const EdgeInsets.all(14),
          child: Row(
            children: [
              SizedBox(
                width: 34,
                child: Text('#${item.rank}',
                    style: TextStyle(
                        fontFamily: 'serif',
                        fontSize: 14,
                        color: item.rank <= 3
                            ? scheme.primary
                            : scheme.onSurfaceVariant,
                        fontWeight: FontWeight.w700)),
              ),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(item.title,
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        style: Theme.of(context)
                            .textTheme
                            .titleLarge
                            ?.copyWith(fontSize: 15)),
                    const SizedBox(height: 4),
                    Text(item.author,
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
}

Widget _filterChips(
    BuildContext context, List<String> labels, String? selected, void Function(String?) onTap) {
  return Wrap(
    spacing: 8,
    runSpacing: 8,
    children: [
      for (final label in labels)
        FilterChip(
          label: Text(label),
          selected: selected == label,
          onSelected: (sel) => onTap(sel ? label : null),
        ),
    ],
  );
}

String _wan(int n) {
  if (n >= 10000) return '${(n / 10000).toStringAsFixed(1)}万';
  return '$n';
}
