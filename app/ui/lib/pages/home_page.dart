import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../core/providers.dart';
import '../data/api/strata_api.dart';
import '../widgets/banner_carousel.dart';
import '../widgets/back_to_top.dart';
import '../widgets/default_cover.dart';
import 'browse_page.dart';

/// Classic 排行行卡数据（board 端点），kind: finish / popular。
final boardProvider = FutureProvider.autoDispose.family<List<RankItem>, String>(
  (ref, kind) async {
    final handle = await ref.watch(bootProvider.future);
    return handle.api.rankingBoard(kind: kind, limit: 8);
  },
);

/// 随机书架数据源：/random 均匀抽样，换一换即 invalidate。
final randomProvider = FutureProvider.autoDispose<List<RankItem>>((ref) async {
  final handle = await ref.watch(bootProvider.future);
  return handle.api.randomBooks(limit: 4);
});

/// 连载发现：从全库连载书中均匀抽样（ORDER BY RANDOM，等概率），
/// 每次下拉刷新重掷一批。
final serialShowcaseProvider = FutureProvider.autoDispose<List<RankItem>>((
  ref,
) async {
  final handle = await ref.watch(bootProvider.future);
  return handle.api.randomBooks(limit: 8, status: 'serial');
});

/// 首页：编辑精选轮播 → 入口宫格 → 分类找书 → 继续浏览。
/// 不暴露种子统计——定位是找书 App（用户反馈 2026-11-17）。
class HomePage extends ConsumerStatefulWidget {
  const HomePage({super.key});

  @override
  ConsumerState<HomePage> createState() => _HomePageState();
}

class _HomePageState extends ConsumerState<HomePage> {
  final _scroll = ScrollController();
  bool _showTop = false;

  @override
  void initState() {
    super.initState();
    _scroll.addListener(() {
      final show = _scroll.hasClients && _scroll.offset > 500;
      if (show != _showTop) setState(() => _showTop = show);
    });
  }

  @override
  void dispose() {
    _scroll.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final featured = ref.watch(featuredProvider);
    final banners = ref.watch(bannerProvider);
    return Scaffold(
      body: RefreshIndicator(
        onRefresh: () async {
          ref.invalidate(featuredProvider);
          ref.invalidate(bannerProvider);
          ref.invalidate(boardProvider);
          ref.invalidate(randomProvider);
          ref.invalidate(serialShowcaseProvider);
          await Future.wait([
            ref.read(featuredProvider.future),
            ref.read(bannerProvider.future),
          ]);
        },
        child: SafeArea(
          bottom: false,
          child: featured.when(
            loading: () => const Center(child: CircularProgressIndicator()),
            error: (e, _) => Center(child: Text('精选加载失败：$e')),
            data: (items) => Stack(
              children: [
                ListView(
                  controller: _scroll,
                  padding: const EdgeInsets.symmetric(vertical: 8),
              children: [
                _formTabs(context, () => ref.invalidate(featuredProvider)),
                _searchRow(context),
                BannerCarousel(
                  items: banners.asData?.value ?? items,
                  onTap: (it) => context.push('/book/${it.nid}'),
                ),
                const SizedBox(height: 8),
                _entryGrid(context),
                _sectionTitle(context, '连载发现',
                    onMore: () => context.push('/serial-random')),
                const _ShowcaseSection(),
                _sectionTitle(context, '完结精选'),
                const _BoardGrid(kind: 'finish'),
                _sectionTitle(context, '今日精品更新'),
                const _Spotlight(),
                _sectionTitle(context, '随机书架'),
                const _ShuffleGrid(),
                _sectionTitle(context, '继续浏览'),
                const _ContinueBrowsing(),
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
                          curve: Curves.easeOut),
                    ),
                  ),
              ],
            ),
          ),
        ),
      ),
    );
  }

  // header form tab（docs/13 form 字段）：长篇（=小说，15万字以上）/中篇/短篇/对话/IP。
  // 无品牌行——移动端惯例，顶部即内容导航。刷新挂在行末。
  Widget _formTabs(BuildContext context, VoidCallback onRefresh) {
    final scheme = Theme.of(context).colorScheme;
    const forms = ['长篇', '中篇', '短篇', '对话', 'IP'];
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
                    color: i == 0 ? scheme.primary : Colors.transparent,
                  ),
                ),
              ),
              child: Text(
                forms[i],
                style: TextStyle(
                  fontSize: 14,
                  fontWeight: i == 0 ? FontWeight.w700 : FontWeight.w400,
                  color: i == 0 ? scheme.primary : scheme.onSurfaceVariant,
                ),
              ),
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
                padding: const EdgeInsets.symmetric(
                  horizontal: 14,
                  vertical: 9,
                ),
                decoration: BoxDecoration(
                  color: scheme.surface,
                  border: Border.all(
                    color: scheme.outline.withValues(alpha: .4),
                  ),
                  borderRadius: BorderRadius.circular(999),
                ),
                child: Row(
                  children: [
                    Icon(
                      Icons.search,
                      size: 16,
                      color: scheme.onSurfaceVariant,
                    ),
                    const SizedBox(width: 8),
                    Text(
                      '搜索书名 / 作者',
                      style: TextStyle(
                        fontSize: 12,
                        color: scheme.onSurfaceVariant,
                      ),
                    ),
                  ],
                ),
              ),
            ),
          ),
          const SizedBox(width: 10),
          InkWell(
            onTap: () => context.push('/history'),
            borderRadius: BorderRadius.circular(999),
            child: Container(
              padding: const EdgeInsets.symmetric(horizontal: 13, vertical: 9),
              decoration: BoxDecoration(
                border: Border.all(color: scheme.outline.withValues(alpha: .4)),
                borderRadius: BorderRadius.circular(999),
              ),
              child: Row(
                children: [
                  Icon(Icons.history, size: 14, color: scheme.primary),
                  const SizedBox(width: 5),
                  Text(
                    '阅读记录',
                    style: TextStyle(
                      fontSize: 12,
                      fontWeight: FontWeight.w600,
                      color: scheme.primary,
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

  Widget _sectionTitle(BuildContext context, String text,
      {void Function()? onMore}) =>
      Padding(
        padding: const EdgeInsets.fromLTRB(16, 14, 16, 8),
        child: Row(
          children: [
            Expanded(
              child: Text(text,
                  style: Theme.of(context).textTheme.titleLarge,
                  overflow: TextOverflow.ellipsis),
            ),
            if (onMore != null)
              InkWell(
                onTap: onMore,
                borderRadius: BorderRadius.circular(8),
                child: Padding(
                  padding: const EdgeInsets.symmetric(
                      horizontal: 8, vertical: 4),
                  child: Row(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      Text('更多',
                          style: TextStyle(
                              fontSize: 12,
                              color: Theme.of(context).colorScheme.primary)),
                      Icon(Icons.chevron_right,
                          size: 16,
                          color: Theme.of(context).colorScheme.primary),
                    ],
                  ),
                ),
              ),
          ],
        ),
      );

  // 二级页面分流宫格：底部 Tab 之外的目的地都从这里进。
  Widget _entryGrid(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final entries = [
      (Icons.category, '分类', BrowseMode.category),
      (Icons.update, '状态', BrowseMode.status),
      (Icons.emoji_events, '比赛', BrowseMode.contest),
      (Icons.article, '短篇', BrowseMode.short),
    ];
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 16),
      child: Row(
        children: [
          for (final (icon, label, mode) in entries)
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
                      child: Icon(icon, size: 22, color: scheme.primary),
                    ),
                    const SizedBox(height: 5),
                    Text(label, style: const TextStyle(fontSize: 11)),
                  ],
                ),
              ),
            ),
        ],
      ),
    );
  }
}

/// 连载发现：随机连载书 4×2 封面网格，无角标——内容即随机抽取的
/// 全库连载书，等概率、每次下拉刷新换一批。
class _ShowcaseSection extends ConsumerWidget {
  const _ShowcaseSection();

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final items = ref.watch(serialShowcaseProvider);
    return items.when(
      loading: () => const Padding(
        padding: EdgeInsets.all(16),
        child: Center(child: CircularProgressIndicator()),
      ),
      error: (e, _) => Padding(
        padding: const EdgeInsets.symmetric(horizontal: 16),
        child: Text(
          '加载失败：$e',
          style: TextStyle(fontSize: 12, color: Colors.grey),
        ),
      ),
      data: (list) => Padding(
        padding: const EdgeInsets.symmetric(horizontal: 16),
        child: Column(
          children: [
            for (var row = 0; row < 2; row++) ...[
              if (row > 0) const SizedBox(height: 12),
              Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  for (var c = 0; c < 4; c++) ...[
                    if (c > 0) const SizedBox(width: 10),
                    Expanded(
                      child: (row * 4 + c) < list.length
                          ? _CoverCard(item: list[row * 4 + c], rank: null)
                          : const SizedBox(),
                    ),
                  ],
                ],
              ),
            ],
          ],
        ),
      ),
    );
  }
}

/// 完结精选：4 列封面网格（board finish 前 4）。
class _BoardGrid extends ConsumerWidget {
  final String kind;

  const _BoardGrid({required this.kind});

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
        child: Text(
          '加载失败：$e',
          style: TextStyle(fontSize: 12, color: Colors.grey),
        ),
      ),
      data: (list) => Padding(
        padding: const EdgeInsets.symmetric(horizontal: 16),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            for (var i = 0; i < list.take(4).length; i++) ...[
              if (i > 0) const SizedBox(width: 10),
              Expanded(child: _CoverCard(item: list[i], rank: null)),
            ],
          ],
        ),
      ),
    );
  }
}

/// 封面卡：CDN 实图/书脊字占位 + 可选榜单角标。
class _CoverCard extends StatelessWidget {
  final RankItem item;
  final int? rank;

  const _CoverCard({required this.item, this.rank});

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final coverUrl = item.coverUrl;
    final hasCover = coverUrl != null && coverUrl.isNotEmpty;
    return InkWell(
      onTap: () => context.push('/book/${item.nid}'),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          AspectRatio(
            aspectRatio: 3 / 4,
            child: Stack(
              children: [
                Positioned.fill(
                  child: hasCover
                      ? ClipRRect(
                          borderRadius: BorderRadius.circular(10),
                          child: Image.network(
                            coverImageUrl(coverUrl)!,
                            fit: BoxFit.cover,
                            loadingBuilder: coverLoadingBuilder,
                            errorBuilder: (_, _, _) =>
                                _spine(context, item.nid),
                          ),
                        )
                      : _spine(context, item.nid),
                ),
                if (rank != null)
                  Positioned(
                    top: 6,
                    left: 6,
                    child: Container(
                      padding: const EdgeInsets.symmetric(
                        horizontal: 6,
                        vertical: 1,
                      ),
                      decoration: BoxDecoration(
                        color: scheme.primary,
                        borderRadius: BorderRadius.circular(4),
                      ),
                      child: Text(
                        '人气 No.$rank',
                        style: TextStyle(fontSize: 9, color: scheme.onPrimary),
                      ),
                    ),
                  ),
              ],
            ),
          ),
          const SizedBox(height: 6),
          Text(
            item.title,
            maxLines: 2,
            overflow: TextOverflow.ellipsis,
            style: const TextStyle(fontSize: 12, fontWeight: FontWeight.w600),
          ),
          Text(
            '${item.genre ?? ''}${item.status != null ? ' · ${item.status}' : ''}',
            style: TextStyle(fontSize: 10, color: scheme.onSurfaceVariant),
          ),
        ],
      ),
    );
  }
}

/// 今日精品更新：编辑精选第一本，单本大图沉浸式（官方式）。
class _Spotlight extends ConsumerWidget {
  const _Spotlight();

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final featured = ref.watch(featuredProvider);
    return featured.when(
      loading: () => const SizedBox.shrink(),
      error: (e, _) => const SizedBox.shrink(),
      data: (items) {
        if (items.isEmpty) return const SizedBox.shrink();
        final it = items.first;
        final scheme = Theme.of(context).colorScheme;
        return Padding(
          padding: const EdgeInsets.symmetric(horizontal: 16),
          child: InkWell(
            onTap: () => context.push('/book/${it.nid}'),
            borderRadius: BorderRadius.circular(16),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                AspectRatio(
                  aspectRatio: 2,
                  child: ClipRRect(
                    borderRadius: const BorderRadius.vertical(
                      top: Radius.circular(16),
                    ),
                    child: Image.network(
                      'https://rs.sfacg.com/web/novel/images/images/beitouNew/${it.nid}.jpg',
                      fit: BoxFit.cover,
                      loadingBuilder: coverLoadingBuilder,
                      errorBuilder: (_, _, _) => ColoredBox(
                        color: scheme.primary.withValues(alpha: .15),
                      ),
                    ),
                  ),
                ),
                Container(
                  width: double.infinity,
                  padding: const EdgeInsets.all(12),
                  decoration: BoxDecoration(
                    color: scheme.surface,
                    borderRadius: const BorderRadius.vertical(
                      bottom: Radius.circular(16),
                    ),
                    border: Border.all(
                      color: scheme.outline.withValues(alpha: .4),
                    ),
                  ),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        it.title,
                        maxLines: 2,
                        overflow: TextOverflow.ellipsis,
                        style: const TextStyle(
                          fontSize: 14,
                          fontWeight: FontWeight.w700,
                        ),
                      ),
                      const SizedBox(height: 3),
                      Text(
                        it.author,
                        style: TextStyle(
                          fontSize: 11,
                          color: scheme.onSurfaceVariant,
                        ),
                      ),
                    ],
                  ),
                ),
              ],
            ),
          ),
        );
      },
    );
  }
}

/// 随机书架：/random 均匀抽样 + 换一换（官方"次元新书"同款）。
class _ShuffleGrid extends ConsumerStatefulWidget {
  const _ShuffleGrid();

  @override
  ConsumerState<_ShuffleGrid> createState() => _ShuffleGridState();
}

class _ShuffleGridState extends ConsumerState<_ShuffleGrid> {
  @override
  Widget build(BuildContext context) {
    final items = ref.watch(randomProvider);
    return items.when(
      loading: () => const Padding(
        padding: EdgeInsets.all(16),
        child: Center(child: CircularProgressIndicator()),
      ),
      error: (e, _) => Padding(
        padding: const EdgeInsets.symmetric(horizontal: 16),
        child: Text(
          '加载失败：$e',
          style: TextStyle(fontSize: 12, color: Colors.grey),
        ),
      ),
      data: (list) => Padding(
        padding: const EdgeInsets.symmetric(horizontal: 16),
        child: Column(
          children: [
            Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                for (var i = 0; i < list.take(4).length; i++) ...[
                  if (i > 0) const SizedBox(width: 10),
                  Expanded(child: _CoverCard(item: list[i], rank: null)),
                ],
              ],
            ),
            const SizedBox(height: 10),
            SizedBox(
              width: double.infinity,
              child: OutlinedButton(
                onPressed: () => ref.invalidate(randomProvider),
                style: OutlinedButton.styleFrom(
                  foregroundColor: Theme.of(context).colorScheme.primary,
                  side: BorderSide(
                    color: Theme.of(context).colorScheme.primary,
                  ),
                ),
                child: const Text('换一换 ↻'),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

/// 默认封面兜底（用户拍板）：cover_url 为空用官方 default/defaultNew
/// 两张图按 nid 取余绑定，不用书脊占位。
Widget _spine(BuildContext context, int nid) {
  return defaultCover(nid, radius: 10);
}

/// 继续浏览：书架里的书（本地足迹随使用增长）。
class _ContinueBrowsing extends ConsumerWidget {
  const _ContinueBrowsing();

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final shelf = ref.watch(shelfProvider);
    return shelf.when(
      loading: () => const Center(child: CircularProgressIndicator()),
      error: (e, _) =>
          Padding(padding: const EdgeInsets.all(16), child: Text('加载失败：$e')),
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
                            color: Theme.of(context).colorScheme.primary
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
