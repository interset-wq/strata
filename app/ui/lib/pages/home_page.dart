import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../core/providers.dart';
import '../data/api/strata_api.dart';
import '../widgets/banner_carousel.dart';
import 'browse_page.dart';

/// Classic 排行行卡数据（board 端点），kind: finish / popular。
final boardProvider =
    FutureProvider.autoDispose.family<List<RankItem>, String>((ref, kind) async {
  final handle = await ref.watch(bootProvider.future);
  return handle.api.rankingBoard(kind: kind, limit: 3);
});

/// 首页：编辑精选轮播 → 入口宫格 → 分类找书 → 继续浏览。
/// 不暴露种子统计——定位是找书 App（用户反馈 2026-11-17）。
class HomePage extends ConsumerWidget {
  const HomePage({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final featured = ref.watch(featuredProvider);
    return Scaffold(
      body: SafeArea(
        bottom: false,
        child: featured.when(
          loading: () => const Center(child: CircularProgressIndicator()),
          error: (e, _) => Center(child: Text('精选加载失败：$e')),
          data: (items) => ListView(
            padding: const EdgeInsets.symmetric(vertical: 8),
            children: [
              _formTabs(context, () => ref.invalidate(featuredProvider)),
              _searchRow(context),
              BannerCarousel(
                items: items,
                onTap: (it) => context.push('/book/${it.nid}'),
              ),
              const SizedBox(height: 8),
              _sectionTitle(context, '找书入口'),
              _entryGrid(context),
              _sectionTitle(context, '完本推荐'),
              const _RecommendSection(kind: 'finish'),
              _sectionTitle(context, '热门书'),
              const _RecommendSection(kind: 'popular'),
              _sectionTitle(context, '继续浏览'),
              const _ContinueBrowsing(),
            ],
          ),
        ),
      ),
    );
  }

  // header form tab（docs/13 form 字段，已定稿）：小说/中篇/短篇/对话/IP。
  // 无品牌行——移动端惯例，顶部即内容导航。刷新挂在行末。
  Widget _formTabs(BuildContext context, VoidCallback onRefresh) {
    final scheme = Theme.of(context).colorScheme;
    const forms = ['小说', '中篇', '短篇', '对话', 'IP'];
    return SizedBox(
      height: 42,
      child: Row(
        children: [
          const SizedBox(width: 16),
          for (var i = 0; i < forms.length; i++) ...[
            if (i > 0) const SizedBox(width: 20),
            Container(
              padding: const EdgeInsets.symmetric(vertical: 8, horizontal: 2),
              decoration: BoxDecoration(
                  border: Border(
                      bottom: BorderSide(
                          width: 2,
                          color: i == 0
                              ? scheme.primary
                              : Colors.transparent))),
              child: Text(forms[i],
                  style: TextStyle(
                      fontSize: 14,
                      fontWeight:
                          i == 0 ? FontWeight.w700 : FontWeight.w400,
                      color: i == 0
                          ? scheme.primary
                          : scheme.onSurfaceVariant)),
            ),
          ],
          const Spacer(),
          IconButton(
            icon: const Icon(Icons.refresh, size: 20),
            tooltip: '刷新',
            onPressed: onRefresh,
          ),
        ],
      ),
    );
  }

  // 搜索框 + 阅读记录行（官方式）：搜索胶囊进本地搜索，阅读记录暂占位。
  Widget _searchRow(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return Padding(
      padding: const EdgeInsets.fromLTRB(16, 10, 16, 6),
      child: Row(
        children: [
          Expanded(
            child: InkWell(
              onTap: () => context.push('/search'),
              borderRadius: BorderRadius.circular(999),
              child: Container(
                padding:
                    const EdgeInsets.symmetric(horizontal: 14, vertical: 9),
                decoration: BoxDecoration(
                  color: scheme.surface,
                  border:
                      Border.all(color: scheme.outline.withValues(alpha: .4)),
                  borderRadius: BorderRadius.circular(999),
                ),
                child: Row(
                  children: [
                    Icon(Icons.search,
                        size: 16, color: scheme.onSurfaceVariant),
                    const SizedBox(width: 8),
                    Text('搜索书名 / 作者',
                        style: TextStyle(
                            fontSize: 12, color: scheme.onSurfaceVariant)),
                  ],
                ),
              ),
            ),
          ),
          const SizedBox(width: 10),
          InkWell(
            onTap: () => ScaffoldMessenger.of(context).showSnackBar(
                const SnackBar(content: Text('阅读记录整理中'))),
            borderRadius: BorderRadius.circular(999),
            child: Container(
              padding:
                  const EdgeInsets.symmetric(horizontal: 13, vertical: 9),
              decoration: BoxDecoration(
                border:
                    Border.all(color: scheme.outline.withValues(alpha: .4)),
                borderRadius: BorderRadius.circular(999),
              ),
              child: Row(
                children: [
                  Icon(Icons.history, size: 14, color: scheme.primary),
                  const SizedBox(width: 5),
                  Text('阅读记录',
                      style: TextStyle(
                          fontSize: 12,
                          fontWeight: FontWeight.w600,
                          color: scheme.primary)),
                ],
              ),
            ),
          ),
        ],
      ),
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

}

/// 推荐流分区（novly 模式）：完结库/全库按平台累计值的行卡列表，
/// 取前 3 本。锚点是平台点击数——展示层口径（docs/12 §1），不进推荐打分。
class _RecommendSection extends ConsumerWidget {
  final String kind;

  const _RecommendSection({required this.kind});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final items = ref.watch(boardProvider(kind));
    return items.when(
      loading: () => const Padding(
        padding: EdgeInsets.all(16),
        child: Center(child: CircularProgressIndicator()),
      ),
      error: (e, _) => Padding(
        padding: const EdgeInsets.symmetric(horizontal: 16),
        child: Text('加载失败：$e',
            style: TextStyle(fontSize: 12, color: Colors.grey)),
      ),
      data: (list) => Column(
        children: [
          for (final it in list.take(3))
            Padding(
              padding: const EdgeInsets.fromLTRB(16, 0, 16, 10),
              child: _RecommendCard(item: it),
            ),
        ],
      ),
    );
  }
}

/// 行卡：封面/书脊 + 标题 + 作者·题材 + 点击数徽章（mockup 01 定稿）。
class _RecommendCard extends StatelessWidget {
  final RankItem item;

  const _RecommendCard({required this.item});

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final coverUrl = item.coverUrl;
    final hasCover = coverUrl != null && coverUrl.isNotEmpty;
    return Card(
      margin: EdgeInsets.zero,
      child: InkWell(
        onTap: () => context.push('/book/${item.nid}'),
        borderRadius: BorderRadius.circular(16),
        child: Padding(
          padding: const EdgeInsets.all(10),
          child: Row(
            children: [
              SizedBox(
                width: 44,
                height: 60,
                child: hasCover
                    ? ClipRRect(
                        borderRadius: BorderRadius.circular(6),
                        child: Image.network(
                          'https://rss.sfacg.com/web/novel/images/NovelCover/Big/$coverUrl',
                          fit: BoxFit.cover,
                          errorBuilder: (_, _, _) =>
                              _spine(context, item.title),
                        ),
                      )
                    : _spine(context, item.title),
              ),
              const SizedBox(width: 12),
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
                            ?.copyWith(fontSize: 13)),
                    const SizedBox(height: 2),
                    Text(
                      item.genre != null
                          ? '${item.author} · ${item.genre}'
                          : item.author,
                      style: TextStyle(
                          fontSize: 11, color: scheme.onSurfaceVariant),
                    ),
                  ],
                ),
              ),
              const SizedBox(width: 8),
              Container(
                padding:
                    const EdgeInsets.symmetric(horizontal: 8, vertical: 1),
                decoration: BoxDecoration(
                    border: Border.all(
                        color: scheme.outline.withValues(alpha: .5)),
                    borderRadius: BorderRadius.circular(999)),
                child: Text('点击 ${_wan(item.clicks ?? 0)}',
                    style: TextStyle(
                        fontSize: 10, color: scheme.onSurfaceVariant)),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

Widget _spine(BuildContext context, String title) {
  final scheme = Theme.of(context).colorScheme;
  return Container(
    decoration: BoxDecoration(
      color: scheme.surface,
      border: Border.all(color: scheme.outline.withValues(alpha: .4)),
      borderRadius: BorderRadius.circular(6),
    ),
    alignment: Alignment.center,
    child: Text(title.isEmpty ? '书' : title.characters.first,
        style: TextStyle(
            fontFamily: 'serif', fontSize: 18, color: scheme.onSurfaceVariant)),
  );
}

String _wan(int n) {
  if (n >= 10000) return '${(n / 10000).toStringAsFixed(0)}万';
  return '$n';
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
