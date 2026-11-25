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
import '../widgets/contest_row_card.dart';

/// Classic 排行行卡数据（board 端点），kind: finish / popular。
final boardProvider = FutureProvider.autoDispose.family<List<RankItem>, String>(
  (ref, kind) async {
    final handle = await ref.watch(bootProvider.future);
    return handle.api.rankingBoard(kind: kind, limit: 8);
  },
);

/// 连载发现：从全库连载书中均匀抽样（ORDER BY RANDOM，等概率），
/// 每次下拉刷新重掷一批。
/// 三个 showcase 均不 autoDispose：ListView 懒构建下分区滚出视口缓存区
/// 即卸载子树，autoDispose 会在滚回时重抽随机批（2026-11-24 用户报告
/// 的滑动换批回归）；常驻后重掷只走下拉刷新的 invalidate。
final serialShowcaseProvider = FutureProvider.family<List<RankItem>, String>((
  ref,
  form,
) async {
  final handle = await ref.watch(bootProvider.future);
  return handle.api.randomBooks(limit: 8, status: 'serial', form: form);
});

/// 完结精选：形态照搬连载发现——从完结长篇中均匀抽样 8 本，
/// 下拉刷新换一批，更多入口进 100 本二级页。
final finishedShowcaseProvider = FutureProvider.family<List<RankItem>, String>((
  ref,
  form,
) async {
  final handle = await ref.watch(bootProvider.future);
  return handle.api.randomBooks(limit: 8, status: 'finished', form: form);
});

/// 随便看看：形态照搬连载发现——从 60 万字以上的大书中均匀抽样 8 本
///（不限连载/完结），下拉刷新换一批，更多入口进 100 本二级页。
final browseShowcaseProvider = FutureProvider.family<List<RankItem>, String>((
  ref,
  form,
) async {
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
  static const _formValues = [
    'long',
    'medium',
    'short',
    'dialogue',
    'ip_collab',
  ];
  String _form = 'long';

  // IP tab：小池（seed 只有 62 本/6 个征文），首页只做分组卡片，
  // 不再把全池 62 行倒进“随便看看”；二级页看单 IP 全部作品。

  // 中篇 tab（小池，words 5万–15万，池规模随种子版本变化）：入口网格
  // 门户（总榜/年份/比赛/题材/优质/随机）。原页内单列表信息量低
  // （用户 2026-11-19 反馈），榜单落点复用 ClassicListPage，随机走
  // /medium-random。与长篇=分区首页、短篇=入口列表、对话=篇幅+榜单
  // 3×3、IP=分组封面卡片刻意区分（docs/16）。

  // 对话 tab（大类，无完结条款，E.22 口径）：字数从 3 万到上百万，
  // 单一收藏榜会被长篇占满。入口网格按短/中/长篇幅 + 榜单分流；
  // 轮播用封面合成纸墨 banner（无 featured 定制图池）。

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
    final banners = ref.watch(bannerProvider(carouselProviderKey(_form)));
    return Scaffold(
      body: RefreshIndicator(
        onRefresh: () async {
          ref.invalidate(bannerProvider(carouselProviderKey(_form)));
          ref.invalidate(boardProvider);
          ref.invalidate(serialShowcaseProvider(_form));
          ref.invalidate(finishedShowcaseProvider(_form));
          ref.invalidate(browseShowcaseProvider(_form));
          ref.invalidate(ipGroupsProvider);
          ref.invalidate(contestGroupsProvider);
          ref.invalidate(yearGroupsProvider);
          ref.invalidate(genreGroupsProvider);
          await ref.read(bannerProvider(carouselProviderKey(_form)).future);
        },
        child: SafeArea(bottom: false, child: _buildBody(context, banners)),
      ),
    );
  }

  // 页面骨架不等待轮播：banner 只在自己的槽位里 loading，切 form 标签
  // 不会把整页替换成全屏 spinner（用户 2026-11-20 反馈）。
  Widget _buildBody(
    BuildContext context,
    AsyncValue<List<FeaturedItem>> banners,
  ) {
    void selectForm(int i) {
      final next = _formValues[i];
      if (next == _form) return;
      setState(() => _form = next);
    }

    // 短篇 tab（docs/form-definitions §4）：收录资格（完结条款 +
    // 质量豁免 + 征文保底）由种子层实施，池本身已干净。布局对齐
    // 其他页面：纸墨合成轮播（无 featured）+ 短篇专属五格入口
    // （年份/比赛/题材/优质/随机——长篇的 showcase 与随机池对
    // ≤5万字池无数据）。单列表已取消（用户 2026-11-19 定）。
    if (_form == 'short') {
      return Stack(
        children: [
          ListView(
            controller: _scroll,
            padding: const EdgeInsets.symmetric(vertical: 8),
            children: [
              _formTabs(context, onSelect: selectForm),
              _searchRow(context),
              // 纸墨合成轮播（无 featured 定制图，封面合成）+
              // 短篇专属五格入口。
              _coverBannerCarousel('short'),
              const SizedBox(height: 8),
              _shortEntryGrid(context),
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
                  curve: Curves.easeOut,
                ),
              ),
            ),
        ],
      );
    }
    // IP tab 书少（seed 只有 62 本/6 个征文），不做全池列表：
    // 轮播保持一致 + 6 张 IP 分组封面卡片；单 IP 的全部作品进二级页。
    if (_form == 'ip_collab') {
      return Stack(
        children: [
          ListView(
            controller: _scroll,
            padding: const EdgeInsets.symmetric(vertical: 8),
            children: [
              _formTabs(context, onSelect: selectForm),
              _searchRow(context),
              _featuredCarousel(context, banners),
              const SizedBox(height: 8),
              const IpGroupGrid(),
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
                  curve: Curves.easeOut,
                ),
              ),
            ),
        ],
      );
    }
    // 对话 tab（大类）：纸墨轮播 + 3×3 入口网格。篇幅轴放在
    // 网格首位，避免单一收藏榜被长篇占满（用户 2026-11-20）。
    if (_form == 'dialogue') {
      return Stack(
        children: [
          ListView(
            controller: _scroll,
            padding: const EdgeInsets.symmetric(vertical: 8),
            children: [
              _formTabs(context, onSelect: selectForm),
              _searchRow(context),
              _coverBannerCarousel('dialogue'),
              const SizedBox(height: 8),
              _portalGrid(
                context,
                _dialogueEntryGridEntries(),
                crossAxisCount: 3,
              ),
              _wideEntryCard(
                context,
                icon: Icons.leaderboard_outlined,
                title: '官方对话月票榜',
                subtitle: '2017-07 起 · 按月可查',
                route: '/official-ranks/m4',
              ),
              _contestArchiveSection(context, 'dialogue'),
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
                  curve: Curves.easeOut,
                ),
              ),
            ),
        ],
      );
    }
    // 中篇 tab（小池）：固定轮播 + 2×3 入口网格（总榜/年份/
    // 比赛/题材/优质/随机）。原页内单列表信息量低（用户
    // 2026-11-19 反馈）；与长篇=分区首页、短篇=入口列表、
    // IP=分组封面卡片刻意区分（docs/16）。
    if (_form == 'medium') {
      return Stack(
        children: [
          ListView(
            controller: _scroll,
            padding: const EdgeInsets.symmetric(vertical: 8),
            children: [
              _formTabs(context, onSelect: selectForm),
              _searchRow(context),
              // 中篇 featured 池很小：固定收藏序轮播，不做每日随机。
              _featuredCarousel(context, banners),
              const SizedBox(height: 8),
              _mediumEntryGrid(context),
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
                  curve: Curves.easeOut,
                ),
              ),
            ),
        ],
      );
    }
    return Stack(
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
            ),
            _searchRow(context),
            // 通用布局只服务长篇 tab（对话/中篇/短篇/IP 各有
            // 独立分支）：featured 池有定制 banner 图。
            _featuredCarousel(context, banners),
            const SizedBox(height: 8),
            _entryGrid(context),
            _wideEntryCard(
              context,
              icon: Icons.leaderboard_outlined,
              title: '官方榜单',
              subtitle: '月票 / 新书 / 热销 / 打赏 · 在线',
              route: '/official-ranks',
            ),
            _sectionTitle(
              context,
              '连载发现',
              onMore: () => context.push('/serial-random'),
            ),
            _ShowcaseSection(provider: serialShowcaseProvider(_form)),
            _sectionTitle(
              context,
              '完结精选',
              onMore: () => context.push('/finished-random'),
            ),
            _ShowcaseSection(provider: finishedShowcaseProvider(_form)),
            _booklistRecommendSection(context),
            _sectionTitle(
              context,
              '随便看看',
              onMore: () => context.push('/browse-random'),
            ),
            _ShowcaseSection(provider: browseShowcaseProvider(_form)),
            _sectionTitle(
              context,
              '大图精选',
              onMore: () => context.push('/featured-gallery'),
            ),
            const _LargeImageSection(),
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
                curve: Curves.easeOut,
              ),
            ),
          ),
      ],
    );
  }

  Widget _featuredCarousel(
    BuildContext context,
    AsyncValue<List<FeaturedItem>> banners,
  ) {
    final scheme = Theme.of(context).colorScheme;
    return banners.when(
      data: (items) => BannerCarousel(
        items: items,
        onTap: (it) => context.push('/book/${it.nid}'),
      ),
      loading: () => Padding(
        padding: const EdgeInsets.symmetric(horizontal: 16),
        child: AspectRatio(
          aspectRatio: 2.2,
          child: DecoratedBox(
            decoration: BoxDecoration(
              color: scheme.primary.withValues(alpha: .08),
              borderRadius: BorderRadius.circular(16),
            ),
            child: const Center(
              child: CircularProgressIndicator(strokeWidth: 2),
            ),
          ),
        ),
      ),
      error: (e, _) => Padding(
        padding: const EdgeInsets.symmetric(horizontal: 16),
        child: SizedBox(
          height: 150,
          child: Center(
            child: TextButton(
              onPressed: () =>
                  ref.invalidate(bannerProvider(carouselProviderKey(_form))),
              child: const Text('轮播加载失败，点按重试'),
            ),
          ),
        ),
      ),
    );
  }

  // header form tab（docs/13 form 字段）：长篇（=小说，15万字以上）/中篇/短篇/对话/IP。
  // 无品牌行——移动端惯例，顶部即内容导航。行末是提示按钮（info，弹出
  // 形式推断说明模态框，见 _showFormInfoDialog）；刷新走下拉手势。
  Widget _formTabs(
    BuildContext context, {
    required ValueChanged<int> onSelect,
  }) {
    final scheme = Theme.of(context).colorScheme;
    const forms = ['长篇', '中篇', '短篇', '对话', 'IP'];
    return Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        SizedBox(
          height: 42,
          child: Row(
            children: [
              const SizedBox(width: 16),
              for (var i = 0; i < forms.length; i++) ...[
                if (i > 0) const SizedBox(width: 20),
                InkWell(
                  onTap: () => onSelect(i),
                  child: Container(
                    padding: const EdgeInsets.symmetric(
                      vertical: 8,
                      horizontal: 2,
                    ),
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
                icon: const Icon(Icons.info, size: 20),
                tooltip: '形式推断说明',
                onPressed: () => _showFormInfoDialog(context),
              ),
            ],
          ),
        ),
      ],
    );
  }

  // form 推断说明模态框（docs/form-definitions §1/§7：form 是估计值，
  // UI 须标注「形式为推断，非官方分类」——行内标注改为此模态框，
  // 用户 2026-11-19 定，不占页面）。
  void _showFormInfoDialog(BuildContext context) {
    showDialog(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('关于小说形式'),
        content: const SizedBox(
          width: double.maxFinite,
          child: Text(
            '小说形式（长篇/中篇/短篇/对话/IP）由本地数据推断，'
            '非官方分类：\n\n'
            '• 长篇 >15万字、中篇 5–15万字、短篇 ≤5万字（字数切档）\n'
            '• 对话/互动：征文标记 + 章节形态判据\n'
            '• IP：联动征文封闭名单（崩坏3/少女前线等）\n'
            '• 短篇/中篇池仅含已完结作品，少量高口碑连载经质量豁免\n'
            '• 征文名是投稿赛道，不定字数档位',
            style: TextStyle(fontSize: 13, height: 1.7),
          ),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(ctx),
            child: const Text('知道了'),
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

  Widget _wideEntryCard(
    BuildContext context, {
    required IconData icon,
    required String title,
    required String subtitle,
    required String route,
  }) {
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
                  Text(
                    title,
                    style: TextStyle(
                      fontSize: 14,
                      fontWeight: FontWeight.w700,
                      color: scheme.onSurface,
                    ),
                  ),
                  const SizedBox(height: 2),
                  Text(
                    subtitle,
                    style: TextStyle(
                      fontSize: 11,
                      color: scheme.onSurfaceVariant,
                    ),
                  ),
                ],
              ),
            ),
            Icon(Icons.chevron_right, size: 20, color: scheme.outline),
          ],
        ),
      ),
    );
  }

  // 对话区 / IP 区赛事归档（用户裁定 2026-11-22：对话的归档放对话区、
  // IP 的归档放 IP 区；列表页「其他」tab 只留主题类）：按引擎侧 lane
  // 分类过滤，零请求，空则整区隐藏。
  Widget _contestArchiveSection(BuildContext context, String lane) {
    final groups = ref.watch(contestArchiveProvider);
    final items = groups.value?.where((g) => g.lane == lane).toList() ?? [];
    if (items.isEmpty) return const SizedBox.shrink();
    return Column(
      children: [
        _sectionTitle(context, '赛事归档'),
        for (final g in items) ContestRowCard(group: g),
      ],
    );
  }

  Widget _sectionTitle(
    BuildContext context,
    String text, {
    void Function()? onMore,
  }) => Padding(
    padding: const EdgeInsets.fromLTRB(16, 14, 16, 8),
    child: Row(
      children: [
        Expanded(
          child: Text(
            text,
            style: Theme.of(context).textTheme.titleLarge,
            overflow: TextOverflow.ellipsis,
          ),
        ),
        if (onMore != null)
          InkWell(
            onTap: onMore,
            borderRadius: BorderRadius.circular(8),
            child: Padding(
              padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
              child: Row(
                mainAxisSize: MainAxisSize.min,
                children: [
                  Text(
                    '更多',
                    style: TextStyle(
                      fontSize: 12,
                      color: Theme.of(context).colorScheme.primary,
                    ),
                  ),
                  Icon(
                    Icons.chevron_right,
                    size: 16,
                    color: Theme.of(context).colorScheme.primary,
                  ),
                ],
              ),
            ),
          ),
      ],
    ),
  );

  // 二级页面分流宫格：底部 Tab 之外的目的地都从这里进。
  // 第四格是经典榜单（与短篇/中篇/对话 tab 首位同构：四段切换 +
  // 逆序，总榜=其中收藏段；用户 2026-11-21：原短篇入口让位）。
  Widget _entryGrid(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final entries = [
      (Icons.local_library, '日轻', '/licensed'),
      (Icons.person_search, '作者榜', '/author-ranks?form=long'),
      (Icons.insights, '量化榜单', '/quant-list'),
      (
        Icons.leaderboard,
        '经典榜单',
        '/classic-list?title=经典榜单&form=long&metric-switchable=1',
      ),
    ];
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 16),
      child: Row(
        children: [
          for (final (icon, label, path) in entries)
            Expanded(
              child: InkWell(
                onTap: () => context.push(path),
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

  // 书单推荐（docs/booklist-in-app.md §深化）：引擎按 UTC 日期种子随机
  // 抽 3 个官方书单，横排文本卡（#id + 标题 + 作品数 + 作者），点击进
  // 书单详情。增益区块：加载失败/空结果整行隐藏，不阻塞首页。
  Widget _booklistRecommendSection(BuildContext context) {
    final items = ref.watch(booklistRecommendProvider).value;
    if (items == null || items.isEmpty) return const SizedBox.shrink();
    return Column(
      children: [
        _sectionTitle(
          context,
          '书单推荐',
          onMore: () => context.push('/booklists'),
        ),
        SizedBox(
          height: 88,
          child: ListView(
            scrollDirection: Axis.horizontal,
            padding: const EdgeInsets.symmetric(horizontal: 16),
            children: [for (final b in items) _booklistCard(context, b)],
          ),
        ),
      ],
    );
  }

  Widget _booklistCard(BuildContext context, Booklist b) {
    final scheme = Theme.of(context).colorScheme;
    return InkWell(
      onTap: () => context.push('/booklists/${b.id}'),
      borderRadius: BorderRadius.circular(12),
      child: Container(
        width: 150,
        height: 74,
        margin: const EdgeInsets.only(right: 8),
        padding: const EdgeInsets.all(10),
        decoration: BoxDecoration(
          color: scheme.surfaceContainerLow,
          borderRadius: BorderRadius.circular(12),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          mainAxisAlignment: MainAxisAlignment.spaceBetween,
          children: [
            Row(
              children: [
                Text(
                  '#${b.id}',
                  style: TextStyle(
                    fontSize: 11,
                    fontWeight: FontWeight.w700,
                    color: scheme.primary,
                  ),
                ),
                const Spacer(),
                Text(
                  '${b.novelNum} 部作品',
                  style: TextStyle(
                    fontSize: 10,
                    color: scheme.onSurfaceVariant,
                  ),
                ),
              ],
            ),
            Text(
              b.title,
              style: const TextStyle(
                fontSize: 11.5,
                fontWeight: FontWeight.w600,
              ),
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
            ),
            Text(
              b.author,
              style: TextStyle(fontSize: 10, color: scheme.onSurfaceVariant),
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
            ),
          ],
        ),
      ),
    );
  }

  // 中篇 tab 入口网格（2×3）：经典榜单/年份/比赛/题材/优质/随机。
  // 首位经典榜单与短篇 tab 同构（点击/收藏/点赞/字数四段切换 + 逆序，
  // 总榜=其中收藏段，故不再单列总榜入口）；入口只做导航，轴切换留在
  // ClassicListPage 页内（docs/16）。
  Widget _mediumEntryGrid(BuildContext context) {
    final entries = <(IconData, String, String, String)>[
      (
        Icons.leaderboard,
        '经典榜单',
        '点击/收藏/点赞/字数',
        '/classic-list?title=经典榜单&form=medium&metric-switchable=1',
      ),
      (
        Icons.calendar_month,
        '年份榜',
        '筛选面板里选年份',
        '/classic-list?title=${Uri.encodeComponent('年份榜')}'
            '&form=medium',
      ),
      (
        Icons.emoji_events,
        '比赛榜',
        '按征文赛道筛选',
        '/classic-list?title=${Uri.encodeComponent('比赛榜')}'
            '&form=medium&contest-switchable=1',
      ),
      (
        Icons.category,
        '题材榜',
        '筛选面板里选题材',
        '/classic-list?title=${Uri.encodeComponent('题材榜')}'
            '&form=medium',
      ),
      (
        Icons.star,
        '优质中篇',
        '同代分位头部',
        '/classic-list?title=${Uri.encodeComponent('优质中篇')}'
            '&form=medium&order=pct',
      ),
      (Icons.shuffle, '随机中篇', '随机 100 本', '/medium-random'),
    ];
    return _portalGrid(context, entries, crossAxisCount: 2);
  }

  // 对话 tab 入口网格（3×3）：篇幅优先，再是榜单轴。首位经典榜单与
  // 短篇/中篇同构（四段切换 + 逆序，总榜=其中收藏段）。
  List<(IconData, String, String, String)> _dialogueEntryGridEntries() {
    String listPath(String title, String extra) =>
        '/classic-list?title=${Uri.encodeComponent(title)}&form=dialogue$extra';
    return [
      (
        Icons.leaderboard,
        '经典榜单',
        '点击/收藏/点赞/字数',
        listPath('经典榜单', '&metric-switchable=1'),
      ),
      (
        Icons.insights,
        '量化榜单',
        '口碑/位置两榜',
        '/quant-list?form=dialogue',
      ),
      (Icons.short_text, '短对话', '≤5 万字', listPath('短对话', '&words-band=short')),
      (
        Icons.menu_book,
        '中对话',
        '5–15 万字',
        listPath('中对话', '&words-band=medium'),
      ),
      (
        Icons.auto_stories,
        '长对话',
        '>15 万字',
        listPath('长对话', '&words-band=long'),
      ),
      (Icons.calendar_month, '年份榜', '顶部年份条切换', listPath('年份榜', '')),
      (
        Icons.emoji_events,
        '比赛榜',
        '按征文赛道筛选',
        listPath('比赛榜', '&contest-switchable=1'),
      ),
      (Icons.category, '题材榜', '筛选面板里选题材', listPath('题材榜', '')),
      (Icons.star, '优质对话', '同代分位头部', listPath('优质对话', '&order=pct')),
      (Icons.shuffle, '随机对话', '随机 100 本', '/dialogue-random'),
    ];
  }

  Widget _portalGrid(
    BuildContext context,
    List<(IconData, String, String, String)> entries, {
    required int crossAxisCount,
  }) {
    final scheme = Theme.of(context).colorScheme;
    return Padding(
      padding: const EdgeInsets.fromLTRB(16, 0, 16, 16),
      child: GridView.builder(
        shrinkWrap: true,
        physics: const NeverScrollableScrollPhysics(),
        itemCount: entries.length,
        gridDelegate: SliverGridDelegateWithFixedCrossAxisCount(
          crossAxisCount: crossAxisCount,
          mainAxisSpacing: 10,
          crossAxisSpacing: 10,
          childAspectRatio: crossAxisCount >= 3 ? 0.82 : 1.2,
        ),
        itemBuilder: (context, i) {
          final (icon, title, desc, path) = entries[i];
          return InkWell(
            borderRadius: BorderRadius.circular(14),
            onTap: () => context.push(path),
            child: Container(
              padding: const EdgeInsets.all(12),
              decoration: BoxDecoration(
                color: scheme.surface,
                borderRadius: BorderRadius.circular(14),
                border: Border.all(color: scheme.outline.withValues(alpha: .3)),
              ),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Container(
                    width: 34,
                    height: 34,
                    decoration: BoxDecoration(
                      color: scheme.primary.withValues(alpha: .12),
                      borderRadius: BorderRadius.circular(10),
                    ),
                    alignment: Alignment.center,
                    child: Icon(icon, size: 19, color: scheme.primary),
                  ),
                  const Spacer(),
                  Text(
                    title,
                    style: const TextStyle(
                      fontSize: 14,
                      fontWeight: FontWeight.w600,
                    ),
                  ),
                  const SizedBox(height: 2),
                  Text(
                    desc,
                    maxLines: 2,
                    overflow: TextOverflow.ellipsis,
                    style: TextStyle(
                      fontSize: 11,
                      color: scheme.onSurfaceVariant,
                    ),
                  ),
                ],
              ),
            ),
          );
        },
      ),
    );
  }

  Widget _shortEntryGrid(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final entries = [
      (
        Icons.leaderboard,
        '经典榜单',
        '点击/收藏/点赞/字数',
        '/classic-list?title=经典榜单&form=short&metric-switchable=1',
      ),
      (
        Icons.calendar_month,
        '年份榜',
        '筛选面板里选年份',
        '/classic-list?title=年份榜&form=short',
      ),
      (
        Icons.emoji_events,
        '比赛榜',
        '侧滑面板切换赛道',
        '/classic-list?title=比赛榜&form=short&contest-switchable=1',
      ),
      (Icons.category, '题材榜', '筛选面板里选题材', '/classic-list?title=题材榜&form=short'),
      (
        Icons.star,
        '优质短篇',
        '同代分位头部',
        '/classic-list?title=${Uri.encodeComponent('优质短篇')}&form=short&order=pct',
      ),
      (Icons.shuffle, '随机短篇', '随机 100 本', '/short-random'),
    ];
    return Padding(
      padding: const EdgeInsets.fromLTRB(16, 4, 16, 8),
      child: Column(
        children: [
          for (final (icon, title, desc, path) in entries)
            Padding(
              padding: const EdgeInsets.only(bottom: 10),
              child: InkWell(
                borderRadius: BorderRadius.circular(12),
                onTap: () => context.push(path),
                child: Container(
                  padding: const EdgeInsets.symmetric(
                    horizontal: 14,
                    vertical: 12,
                  ),
                  decoration: BoxDecoration(
                    color: scheme.surface,
                    borderRadius: BorderRadius.circular(12),
                    border: Border.all(
                      color: scheme.outline.withValues(alpha: .3),
                    ),
                  ),
                  child: Row(
                    children: [
                      Container(
                        width: 38,
                        height: 38,
                        decoration: BoxDecoration(
                          color: scheme.primary.withValues(alpha: .12),
                          borderRadius: BorderRadius.circular(10),
                        ),
                        alignment: Alignment.center,
                        child: Icon(icon, size: 20, color: scheme.primary),
                      ),
                      const SizedBox(width: 12),
                      Expanded(
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Text(
                              title,
                              style: const TextStyle(
                                fontSize: 14,
                                fontWeight: FontWeight.w600,
                              ),
                            ),
                            const SizedBox(height: 2),
                            Text(
                              desc,
                              style: TextStyle(
                                fontSize: 11,
                                color: scheme.onSurfaceVariant,
                              ),
                            ),
                          ],
                        ),
                      ),
                      Icon(
                        Icons.chevron_right,
                        size: 18,
                        color: scheme.onSurfaceVariant,
                      ),
                    ],
                  ),
                ),
              ),
            ),
        ],
      ),
    );
  }

  // 对话/短篇 tab 轮播：无 featured 定制图，封面实时合成纸墨 banner
  // （见 widgets/cover_banner.dart）。静态收藏序（不随日期变），按 form 分池。
  Widget _coverBannerCarousel(String form) {
    final list = ref.watch(coverCarouselProvider(carouselProviderKey(form)));
    return list.when(
      loading: () => const Padding(
        padding: EdgeInsets.symmetric(horizontal: 16),
        child: AspectRatio(
          aspectRatio: 2.2,
          child: Center(child: CircularProgressIndicator(strokeWidth: 2)),
        ),
      ),
      error: (e, _) => Padding(
        padding: const EdgeInsets.symmetric(horizontal: 16),
        child: Text('加载失败：$e', style: const TextStyle(fontSize: 12)),
      ),
      data: (items) => CoverBannerCarousel(
        items: items,
        onTap: (it) => context.push('/book/${it.nid}'),
      ),
    );
  }
}

/// IP tab 分组网格：全部征文分组都露出（seed 当前 6 组），每组用
/// 纯文字卡片（IP 名 + 本数 + 收藏最高一本），点进该 IP 的二级列表。
/// contest 即联动 IP 轴（崩坏3征文 → 崩坏3）；不再把长尾折进“其他”。
class IpGroupGrid extends ConsumerWidget {
  const IpGroupGrid({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final scheme = Theme.of(context).colorScheme;
    return ref
        .watch(ipGroupsProvider)
        .when(
          loading: () => const Padding(
            padding: EdgeInsets.symmetric(vertical: 32),
            child: Center(child: CircularProgressIndicator(strokeWidth: 2)),
          ),
          error: (e, _) => Padding(
            padding: const EdgeInsets.symmetric(horizontal: 16),
            child: Center(
              child: Text('加载失败：$e', style: const TextStyle(fontSize: 12)),
            ),
          ),
          data: (r) {
            if (r.groups.isEmpty) {
              return const Padding(
                padding: EdgeInsets.symmetric(vertical: 32),
                child: Center(
                  child: Text('暂无 IP 合作作品', style: TextStyle(fontSize: 12)),
                ),
              );
            }
            return Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Padding(
                  padding: const EdgeInsets.symmetric(horizontal: 16),
                  child: Row(
                    children: [
                      Text(
                        'IP 合集',
                        style: TextStyle(
                          fontFamily: StrataTokens.serif,
                          fontSize: 16,
                          fontWeight: FontWeight.w700,
                          color: scheme.onSurface,
                        ),
                      ),
                      const Spacer(),
                      Text(
                        '${r.groups.length} 个征文 · ${r.total} 本',
                        style: TextStyle(
                          fontSize: 11,
                          color: scheme.onSurfaceVariant,
                        ),
                      ),
                    ],
                  ),
                ),
                const SizedBox(height: 10),
                Padding(
                  padding: const EdgeInsets.symmetric(horizontal: 16),
                  child: LayoutBuilder(
                    builder: (context, constraints) {
                      final width = (constraints.maxWidth - 12) / 2;
                      return Wrap(
                        spacing: 12,
                        runSpacing: 16,
                        children: [
                          for (final g in r.groups)
                            SizedBox(
                              width: width,
                              child: _IpGroupCard(group: g),
                            ),
                        ],
                      );
                    },
                  ),
                ),
              ],
            );
          },
        );
  }
}

class _IpGroupCard extends StatelessWidget {
  final IpGroup group;

  const _IpGroupCard({required this.group});

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return InkWell(
      onTap: () => context.push(
        '/ip-books?group=${Uri.encodeComponent(group.contest)}'
        '&label=${Uri.encodeComponent(group.label)}',
      ),
      borderRadius: BorderRadius.circular(12),
      child: Container(
        height: 148,
        padding: const EdgeInsets.fromLTRB(14, 12, 14, 12),
        decoration: BoxDecoration(
          color: scheme.surface,
          borderRadius: BorderRadius.circular(12),
          border: Border.all(color: scheme.outline.withValues(alpha: .55)),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Container(
                  width: 3,
                  height: 12,
                  decoration: BoxDecoration(
                    color: scheme.primary,
                    borderRadius: BorderRadius.circular(2),
                  ),
                ),
                const SizedBox(width: 6),
                Text(
                  'IP 合作',
                  style: TextStyle(
                    fontSize: 9,
                    fontWeight: FontWeight.w600,
                    letterSpacing: 1.2,
                    color: scheme.primary,
                  ),
                ),
                const Spacer(),
                Text(
                  '${group.count} 本',
                  style: TextStyle(
                    fontSize: 10,
                    color: scheme.onSurfaceVariant,
                  ),
                ),
              ],
            ),
            const SizedBox(height: 10),
            Text(
              group.label,
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              style: TextStyle(
                fontFamily: StrataTokens.serif,
                fontSize: 17,
                fontWeight: FontWeight.w700,
                color: scheme.onSurface,
              ),
            ),
            const SizedBox(height: 4),
            Expanded(
              child: Text(
                group.topTitle.isEmpty ? '暂无作品' : group.topTitle,
                maxLines: 2,
                overflow: TextOverflow.ellipsis,
                style: TextStyle(
                  fontSize: 11,
                  height: 1.35,
                  color: scheme.onSurfaceVariant,
                ),
              ),
            ),
            Row(
              children: [
                Text(
                  '查看作品',
                  style: TextStyle(
                    fontSize: 10,
                    fontWeight: FontWeight.w600,
                    color: scheme.primary,
                  ),
                ),
                const SizedBox(width: 3),
                Icon(Icons.arrow_forward, size: 12, color: scheme.primary),
              ],
            ),
          ],
        ),
      ),
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
        child: Center(child: CircularProgressIndicator(strokeWidth: 2)),
      ),
      error: (e, _) => Padding(
        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
        child: Text('加载失败：$e', style: const TextStyle(fontSize: 12)),
      ),
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
                          child: coverImage(coverUrl, item.nid),
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
