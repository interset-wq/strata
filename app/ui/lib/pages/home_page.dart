import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../app/theme.dart';
import '../core/providers.dart';
import '../data/api/strata_api.dart';
import '../widgets/banner_carousel.dart';
import '../widgets/banner_large_card.dart';
import '../widgets/back_to_top.dart';
import '../widgets/cover_banner.dart';
import '../widgets/default_cover.dart';
import 'browse_page.dart';

/// Classic 排行行卡数据（board 端点），kind: finish / popular。
final boardProvider = FutureProvider.autoDispose.family<List<RankItem>, String>(
  (ref, kind) async {
    final handle = await ref.watch(bootProvider.future);
    return handle.api.rankingBoard(kind: kind, limit: 8);
  },
);

/// 连载发现：从全库连载书中均匀抽样（ORDER BY RANDOM，等概率），
/// 每次下拉刷新重掷一批。
final serialShowcaseProvider = FutureProvider.autoDispose
    .family<List<RankItem>, String>((ref, form) async {
  final handle = await ref.watch(bootProvider.future);
  return handle.api.randomBooks(limit: 8, status: 'serial', form: form);
});

/// 完结精选：形态照搬连载发现——从完结长篇中均匀抽样 8 本，
/// 下拉刷新换一批，更多入口进 100 本二级页。
final finishedShowcaseProvider = FutureProvider.autoDispose
    .family<List<RankItem>, String>((ref, form) async {
  final handle = await ref.watch(bootProvider.future);
  return handle.api.randomBooks(limit: 8, status: 'finished', form: form);
});

/// 随便看看：形态照搬连载发现——从 60 万字以上的大书中均匀抽样 8 本
///（不限连载/完结），下拉刷新换一批，更多入口进 100 本二级页。
final browseShowcaseProvider = FutureProvider.autoDispose
    .family<List<RankItem>, String>((ref, form) async {
  final handle = await ref.watch(bootProvider.future);
  return handle.api.randomBooks(limit: 8, status: 'browse', form: form);
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
  static const _formValues = ['long', 'medium', 'short', 'dialogue', 'ip_collab'];
  String _form = 'long';

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
    final banners = ref.watch(bannerProvider(_form));
    return Scaffold(
      body: RefreshIndicator(
        onRefresh: () async {
          ref.invalidate(bannerProvider(_form));
          ref.invalidate(boardProvider);
          ref.invalidate(serialShowcaseProvider(_form));
          ref.invalidate(finishedShowcaseProvider(_form));
          ref.invalidate(browseShowcaseProvider(_form));
          await ref.read(bannerProvider(_form).future);
        },
        child: SafeArea(
          bottom: false,
          child: banners.when(
            loading: () => const Center(child: CircularProgressIndicator()),
            error: (e, _) => Center(child: Text('加载失败：$e')),
            data: (items) => Stack(
              children: [
                ListView(
                  controller: _scroll,
                  padding: const EdgeInsets.symmetric(vertical: 8),
              children: [
                _formTabs(
                  context,
                  onSelect: (i) {
                    final next = _formValues[i];
                    if (next == _form) return;
                    setState(() => _form = next);
                  },
                  onRefresh: () {
                    ref.invalidate(serialShowcaseProvider(_form));
                    ref.invalidate(finishedShowcaseProvider(_form));
                    ref.invalidate(browseShowcaseProvider(_form));
                  },
                ),
                _searchRow(context),
                // 对话 tab 无 featured 定制图：封面实时合成纸墨 banner。
                _form == 'dialogue'
                    ? _dialogueCarousel()
                    : BannerCarousel(
                        items: items,
                        onTap: (it) => context.push('/book/${it.nid}'),
                      ),
                const SizedBox(height: 8),
                // IP tab：入口行换成联动 IP（征文聚合）；其余 form 用通用宫格。
                _form == 'ip_collab' ? _ipEntryRow() : _entryGrid(context),
                _sectionTitle(context, '连载发现',
                    onMore: () => context.push('/serial-random')),
                _ShowcaseSection(provider: serialShowcaseProvider(_form)),
                _sectionTitle(context, '完结精选',
                    onMore: () => context.push('/finished-random')),
                _ShowcaseSection(provider: finishedShowcaseProvider(_form)),
                // 宽卡与大图精选是长篇池（授权作品/萌神/featured），
                // IP 池没有对应内容，隐藏避免空卡。
                if (_form != 'ip_collab') _entryCards(context),
                _sectionTitle(context, '随便看看',
                    onMore: () => context.push('/browse-random')),
                _ShowcaseSection(provider: browseShowcaseProvider(_form)),
                if (_form != 'ip_collab') ...[
                  _sectionTitle(context, '大图精选',
                      onMore: () => context.push('/featured-gallery')),
                  const _LargeImageSection(),
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
  Widget _formTabs(
    BuildContext context, {
    required ValueChanged<int> onSelect,
    required VoidCallback onRefresh,
  }) {
    final scheme = Theme.of(context).colorScheme;
    const forms = ['长篇', '中篇', '短篇', '对话', 'IP'];
    return SizedBox(
      height: 42,
      child: Row(
        children: [
          const SizedBox(width: 16),
          for (var i = 0; i < forms.length; i++) ...[
            if (i > 0) const SizedBox(width: 20),
            InkWell(
              onTap: () => onSelect(i),
              child: Container(
                padding: const EdgeInsets.symmetric(vertical: 8, horizontal: 2),
                decoration: BoxDecoration(
                  border: Border(
                    bottom: BorderSide(
                      width: 2,
                      color: _formValues[i] == _form
                          ? scheme.primary
                          : Colors.transparent,
                    ),
                  ),
                ),
                child: Text(
                  forms[i],
                  style: TextStyle(
                    fontSize: 14,
                    fontWeight: _formValues[i] == _form
                        ? FontWeight.w700
                        : FontWeight.w400,
                    color: _formValues[i] == _form
                        ? scheme.primary
                        : scheme.onSurfaceVariant,
                  ),
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

  // 宽卡入口：授权作品 / 萌神获奖——打断连续 4×2 网格的节奏，
  // 同时给两个 curated 池补上首页入口（icon 语义见 app/docs/15）。
  Widget _entryCards(BuildContext context) {
    return Column(
      children: [
        _wideEntryCard(context,
            icon: Icons.lock,
            title: '授权作品',
            subtitle: '官方授权日本轻小说',
            route: '/licensed'),
        const SizedBox(height: 10),
        _wideEntryCard(context,
            icon: Icons.emoji_events,
            title: '萌神获奖',
            subtitle: '官方萌神奖 2018–2024',
            route: '/moe-goddess'),
      ],
    );
  }

  Widget _wideEntryCard(BuildContext context,
      {required IconData icon,
      required String title,
      required String subtitle,
      required String route}) {
    final scheme = Theme.of(context).colorScheme;
    return InkWell(
      onTap: () => context.push(route),
      borderRadius: BorderRadius.circular(12),
      child: Container(
        margin: const EdgeInsets.symmetric(horizontal: 16, vertical: 6),
        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 12),
        decoration: BoxDecoration(
          color: scheme.surface,
          borderRadius: BorderRadius.circular(12),
          border: Border.all(color: scheme.outline.withValues(alpha: .25)),
        ),
        child: Row(
          children: [
            Container(
              width: 36,
              height: 36,
              decoration: BoxDecoration(
                color: scheme.primary.withValues(alpha: .08),
                borderRadius: BorderRadius.circular(10),
              ),
              child: Icon(icon, size: 20, color: scheme.primary),
            ),
            const SizedBox(width: 12),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(title,
                      style: TextStyle(
                          fontSize: 14,
                          fontWeight: FontWeight.w700,
                          color: scheme.onSurface)),
                  const SizedBox(height: 2),
                  Text(subtitle,
                      style: TextStyle(
                          fontSize: 11, color: scheme.onSurfaceVariant)),
                ],
              ),
            ),
            Icon(Icons.chevron_right, size: 20, color: scheme.outline),
          ],
        ),
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

  // 对话 tab 轮播：静态收藏序（不随日期变），封面合成纸墨 banner。
  Widget _dialogueCarousel() {
    final list = ref.watch(dialogueCarouselProvider);
    return list.when(
      loading: () => const Padding(
        padding: EdgeInsets.symmetric(horizontal: 16),
        child: AspectRatio(
          aspectRatio: 2.2,
          child: Center(
              child: CircularProgressIndicator(strokeWidth: 2)),
        ),
      ),
      error: (e, _) => Padding(
        padding: const EdgeInsets.symmetric(horizontal: 16),
        child: Text('加载失败：$e',
            style: const TextStyle(fontSize: 12)),
      ),
      data: (items) => CoverBannerCarousel(
        items: items,
        onTap: (it) => context.push('/book/${it.nid}'),
      ),
    );
  }

  // IP tab 入口行：命名 IP（收藏数前 2 的征文）+ 其他（长尾）。
  // contest 即联动 IP 轴（崩坏3征文 → 崩坏3）；文字卡无 icon（docs/15）。
  Widget _ipEntryRow() {
    final scheme = Theme.of(context).colorScheme;
    return ref.watch(ipGroupsProvider).when(
          loading: () => const Padding(
            padding: EdgeInsets.symmetric(horizontal: 16),
            child: SizedBox(
              height: 56,
              child:
                  Center(child: CircularProgressIndicator(strokeWidth: 2)),
            ),
          ),
          error: (e, _) => Padding(
            padding: const EdgeInsets.symmetric(horizontal: 16),
            child: Center(
                child: Text('加载失败：$e',
                    style: const TextStyle(fontSize: 12))),
          ),
          data: (r) {
            final named = r.groups.take(2).toList();
            final otherCount = r.total - named.fold(0, (s, g) => s + g.count);
            final entries = [
              for (final g in named) (g.label, g.contest, g.count),
              if (otherCount > 0) ('其他', 'other', otherCount),
            ];
            return Padding(
              padding: const EdgeInsets.symmetric(horizontal: 16),
              child: SizedBox(
                height: 56,
                child: Row(
                  children: [
                    for (final (label, group, count) in entries)
                      Expanded(
                        child: Padding(
                          padding: EdgeInsets.only(
                              right: label == entries.last.$1 ? 0 : 8),
                          child: InkWell(
                            onTap: () => context.push(
                                '/ip-books?group=${Uri.encodeComponent(group)}'
                                '&label=${Uri.encodeComponent(label)}'),
                            borderRadius: BorderRadius.circular(12),
                            child: Container(
                              decoration: BoxDecoration(
                                color: scheme.primary.withValues(alpha: .12),
                                borderRadius: BorderRadius.circular(12),
                              ),
                              alignment: Alignment.center,
                              child: Column(
                                mainAxisSize: MainAxisSize.min,
                                children: [
                                  Text(label,
                                      maxLines: 1,
                                      overflow: TextOverflow.ellipsis,
                                      style: TextStyle(
                                        fontFamily: StrataTokens.serif,
                                        fontWeight: FontWeight.w700,
                                        fontSize: 13,
                                      )),
                                  const SizedBox(height: 2),
                                  Text('$count 本',
                                      style: TextStyle(
                                          fontSize: 10,
                                          color: scheme.onSurfaceVariant)),
                                ],
                              ),
                            ),
                          ),
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

/// 随机抽样展示区：4×2 封面网格，无角标——内容即随机抽取的池子
/// （连载发现=连载长篇，完结精选=完结长篇），等概率、下拉刷新换一批。
// 大图精选：每日 banner 池的后段（与轮播同种子、offset 跳段不重复）。
// 与轮播不同：文字在图下方，点图进全屏查看器，点文字进详情页。
class _LargeImageSection extends ConsumerWidget {
  const _LargeImageSection();

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final items = ref.watch(largeImageProvider);
    return items.when(
      loading: () => const SizedBox(
          height: 120,
          child: Center(child: CircularProgressIndicator(strokeWidth: 2))),
      error: (e, _) => Padding(
          padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
          child:
              Text('加载失败：$e', style: const TextStyle(fontSize: 12))),
      data: (list) => Padding(
        padding: const EdgeInsets.only(bottom: 8),
        child: Column(
          children: [
            for (var i = 0; i < list.length; i++)
              BannerLargeCard(item: list[i], index: i, items: list),
          ],
        ),
      ),
    );
  }
}

class _ShowcaseSection extends ConsumerWidget {
  final FutureProvider<List<RankItem>> provider;

  const _ShowcaseSection({required this.provider});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final items = ref.watch(provider);
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

/// 默认封面兜底（用户拍板）：cover_url 为空用官方 default/defaultNew
/// 两张图按 nid 取余绑定，不用书脊占位。
Widget _spine(BuildContext context, int nid) {
  return defaultCover(nid, radius: 10);
}
