import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../core/providers.dart';
import '../widgets/banner_carousel.dart';
import 'browse_page.dart';

/// 首页：编辑精选轮播 → 入口宫格 → 分类找书 → 继续浏览。
/// 不暴露种子统计——定位是找书 App（用户反馈 2026-11-17）。
class HomePage extends ConsumerWidget {
  const HomePage({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final featured = ref.watch(featuredProvider);
    return Scaffold(
      appBar: AppBar(
        title: _brandTitle(context),
        actions: [
          IconButton(
            icon: const Icon(Icons.refresh),
            tooltip: '刷新',
            onPressed: () => ref.invalidate(featuredProvider),
          ),
        ],
      ),
      body: featured.when(
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (e, _) => Center(child: Text('精选加载失败：$e')),
        data: (items) => ListView(
          padding: const EdgeInsets.symmetric(vertical: 8),
          children: [
            BannerCarousel(
              items: items,
              onTap: (it) => context.push('/book/${it.nid}'),
            ),
            const SizedBox(height: 8),
            _sectionTitle(context, '找书入口'),
            _entryGrid(context),
            _sectionTitle(context, '分类找书'),
            _genreChips(context),
            _sectionTitle(context, '继续浏览'),
            const _ContinueBrowsing(),
          ],
        ),
      ),
    );
  }

  Widget _brandTitle(BuildContext context) {
    final primary = Theme.of(context).colorScheme.primary;
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        Text('书层',
            style: Theme.of(context)
                .appBarTheme
                .titleTextStyle
                ?.copyWith(color: Theme.of(context).colorScheme.onSurface)),
        Text(' · ', style: TextStyle(color: primary)),
        Text('Strata',
            style: TextStyle(
              fontFamily: 'serif',
              fontSize: 18,
              fontWeight: FontWeight.w700,
              color: primary,
            )),
      ],
    );
  }

  Widget _sectionTitle(BuildContext context, String text) => Padding(
        padding: const EdgeInsets.fromLTRB(16, 14, 16, 8),
        child: Text(text, style: Theme.of(context).textTheme.titleLarge),
      );

  // 二级页面分流宫格：底部 Tab 之外的目的地都从这里进。
  Widget _entryGrid(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final entries = [
      ('类', '分类', BrowseMode.category),
      ('态', '状态', BrowseMode.status),
      ('赛', '比赛', BrowseMode.contest),
      ('篇', '短篇', BrowseMode.short),
    ];
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 16),
      child: Card(
        child: Padding(
          padding: const EdgeInsets.symmetric(vertical: 12),
          child: Row(
            children: [
              for (final (glyph, label, mode) in entries)
                Expanded(
                  child: InkWell(
                    onTap: () => context.push('/browse?mode=${mode.name}'),
                    borderRadius: BorderRadius.circular(12),
                    child: Column(
                      children: [
                        Container(
                          width: 40,
                          height: 40,
                          decoration: BoxDecoration(
                            color: scheme.primary.withValues(alpha: .12),
                            borderRadius: BorderRadius.circular(12),
                          ),
                          alignment: Alignment.center,
                          child: Text(
                            glyph,
                            style: TextStyle(
                              fontFamily: 'serif',
                              fontSize: 16,
                              color: scheme.primary,
                            ),
                          ),
                        ),
                        const SizedBox(height: 5),
                        Text(label, style: const TextStyle(fontSize: 11)),
                      ],
                    ),
                  ),
                ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _genreChips(BuildContext context) {
    const genres = ['魔幻', '玄幻', '古风', '科幻', '校园', '都市', '悬疑'];
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 16),
      child: Wrap(
        spacing: 8,
        runSpacing: 8,
        children: [
          for (final g in genres)
            ActionChip(
              label: Text(g),
              onPressed: () => context.go('/rankings'),
            ),
        ],
      ),
    );
  }
}

/// 继续浏览：书架里的书（本地足迹随使用增长）。
class _ContinueBrowsing extends ConsumerWidget {
  const _ContinueBrowsing();

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final shelf = ref.watch(shelfProvider);
    return shelf.when(
      loading: () => const Center(child: CircularProgressIndicator()),
      error: (e, _) => Padding(
        padding: const EdgeInsets.all(16),
        child: Text('加载失败：$e'),
      ),
      data: (items) {
        if (items.isEmpty) {
          return const Padding(
            padding: EdgeInsets.symmetric(horizontal: 16, vertical: 8),
            child: Text(
              '书架还是空的——逛逛榜单，把感兴趣的书收进来',
              style: TextStyle(color: Colors.grey),
            ),
          );
        }
        return SizedBox(
          height: 176,
          child: ListView.builder(
            scrollDirection: Axis.horizontal,
            padding: const EdgeInsets.symmetric(horizontal: 16),
            itemCount: items.length,
            itemBuilder: (context, i) {
              final it = items[i];
              return Padding(
                padding: const EdgeInsets.only(right: 12),
                child: InkWell(
                  onTap: () => context.push('/book/${it.nid}'),
                  borderRadius: BorderRadius.circular(10),
                  child: SizedBox(
                    width: 96,
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Container(
                          width: 96,
                          height: 132,
                          decoration: BoxDecoration(
                            borderRadius: BorderRadius.circular(10),
                            color: Theme.of(context)
                                .colorScheme
                                .primary
                                .withValues(alpha: .15),
                          ),
                          child: const Icon(Icons.menu_book, size: 28),
                        ),
                        const SizedBox(height: 6),
                        Text(
                          it.title,
                          maxLines: 2,
                          overflow: TextOverflow.ellipsis,
                          style: const TextStyle(
                            fontSize: 12,
                            fontWeight: FontWeight.w600,
                            height: 1.3,
                          ),
                        ),
                      ],
                    ),
                  ),
                ),
              );
            },
          ),
        );
      },
    );
  }
}
