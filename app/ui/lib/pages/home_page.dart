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
import '../widgets/book_row_tile.dart';
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
  static const _formValues = [
    'long',
    'medium',
    'short',
    'dialogue',
    'ip_collab',
  ];
  String _form = 'long';

  // IP tab“随便看看”：ip_collab 全池（收藏降序），20 本/页，接近底部
  // 上滑加载下一页。确定性列表，只有它能做 load-more。
  List<RankItem> _ipItems = const [];
  bool _ipLoading = false;
  bool _ipDone = false;
  String? _ipError;

  // 中篇 tab（944 本，words 5万–15万）：页内浏览体验——单行题材 chips +
  // 页内无限列表（照搬 IP tab "随便看看"分区模式）。双轴双行 chips
  // 可用性差（用户 2026-11-19 定），简化为题材单轴；年份/优质轴砍掉。
  // 与三个已有 tab 的体验刻意区分：长篇=分区首页、短篇=入口门户、
  // IP=入口行+列表、中篇=页内浏览器（docs/16）。
  String? _mediumGenre;
  List<RankItem> _mediumItems = const [];
  bool _mediumLoading = false;
  bool _mediumDone = false;
  String? _mediumError;

  // 对话 tab（6,189 本，无完结条款：2,574 完结 + 3,615 连载，E.22 口径）：
  // 页内浏览体验与中篇同构（单行题材 chips + 页内无限列表，docs/16）；
  // 轮播用封面合成纸墨 banner（无 featured 定制图池）。
  String? _dialogueGenre;
  List<RankItem> _dialogueItems = const [];
  bool _dialogueLoading = false;
  bool _dialogueDone = false;
  String? _dialogueError;

  @override
  void initState() {
    super.initState();
    _scroll.addListener(() {
      final show = _scroll.hasClients && _scroll.offset > 500;
      if (show != _showTop) setState(() => _showTop = show);
      if (_scroll.hasClients &&
          _scroll.offset >= _scroll.position.maxScrollExtent - 300) {
        if (_form == 'ip_collab') {
          _loadIpMore();
        } else if (_form == 'medium') {
          _loadMediumMore();
        } else if (_form == 'dialogue') {
          _loadDialogueMore();
        }
      }
    });
  }

  @override
  void dispose() {
    _scroll.dispose();
    super.dispose();
  }

  // IP tab“随便看看”下一页：classic 端点 form=ip_collab（收藏降序 +
  // offset 分页），失败显示重试而不是静默吞掉。
  Future<void> _loadIpMore() async {
    if (_ipLoading || _ipDone) return;
    setState(() {
      _ipLoading = true;
      _ipError = null;
    });
    try {
      final handle = await ref.read(bootProvider.future);
      final page = await handle.api.rankingClassic(
        form: 'ip_collab',
        limit: 20,
        offset: _ipItems.length,
      );
      if (!mounted) return;
      setState(() {
        _ipItems = [..._ipItems, ...page];
        _ipDone = page.length < 20;
        _ipLoading = false;
      });
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _ipError = '$e';
        _ipLoading = false;
      });
    }
  }

  // 中篇 tab 页内列表下一页：classic 端点 form=medium + 题材轴
  // （收藏降序；年份/优质轴随双行 chips 砍掉）。
  Future<void> _loadMediumMore() async {
    if (_mediumLoading || _mediumDone) return;
    setState(() {
      _mediumLoading = true;
      _mediumError = null;
    });
    try {
      final handle = await ref.read(bootProvider.future);
      final page = await handle.api.rankingClassic(
        form: 'medium',
        genre: _mediumGenre,
        limit: 20,
        offset: _mediumItems.length,
      );
      if (!mounted) return;
      setState(() {
        _mediumItems = [..._mediumItems, ...page];
        _mediumDone = page.length < 20;
        _mediumLoading = false;
      });
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _mediumError = '$e';
        _mediumLoading = false;
      });
    }
  }

  // 中篇题材切换：重置列表原地重载（不回顶——列表就在 chip 行下方，
  // 重置后滚动位置自然回到列表头部附近，用户仍看得见新列表）。
  void _setMediumGenre(String? g) {
    if (g == _mediumGenre) return;
    setState(() {
      _mediumGenre = g;
      _mediumItems = const [];
      _mediumDone = false;
      _mediumError = null;
      _mediumLoading = false;
    });
    _loadMediumMore();
  }

  // 对话 tab 页内列表下一页：classic 端点 form=dialogue + 题材轴
  // （收藏降序；对话池无完结条款，不按 status 过滤，E.22）。
  Future<void> _loadDialogueMore() async {
    if (_dialogueLoading || _dialogueDone) return;
    setState(() {
      _dialogueLoading = true;
      _dialogueError = null;
    });
    try {
      final handle = await ref.read(bootProvider.future);
      final page = await handle.api.rankingClassic(
        form: 'dialogue',
        genre: _dialogueGenre,
        limit: 20,
        offset: _dialogueItems.length,
      );
      if (!mounted) return;
      setState(() {
        _dialogueItems = [..._dialogueItems, ...page];
        _dialogueDone = page.length < 20;
        _dialogueLoading = false;
      });
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _dialogueError = '$e';
        _dialogueLoading = false;
      });
    }
  }

  // 对话题材切换：重置列表原地重载（同中篇，不回顶）。
  void _setDialogueGenre(String? g) {
    if (g == _dialogueGenre) return;
    setState(() {
      _dialogueGenre = g;
      _dialogueItems = const [];
      _dialogueDone = false;
      _dialogueError = null;
      _dialogueLoading = false;
    });
    _loadDialogueMore();
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
          ref.invalidate(contestGroupsProvider);
          ref.invalidate(yearGroupsProvider);
          ref.invalidate(genreGroupsProvider);
          await ref.read(bannerProvider(_form).future);
        },
        child: SafeArea(
          bottom: false,
          child: banners.when(
            loading: () => const Center(child: CircularProgressIndicator()),
            error: (e, _) => Center(child: Text('加载失败：$e')),
            data: (items) {
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
              // IP tab 书少（54 本），不需要多个分区：轮播 + IP 入口行 +
              // “随便看看”（全池列表，上滑加载更多），无 showcase 分区。
              if (_form == 'ip_collab') {
                if (_ipItems.isEmpty && !_ipLoading) {
                  WidgetsBinding.instance.addPostFrameCallback(
                    (_) => _loadIpMore(),
                  );
                }
                return Stack(
                  children: [
                    ListView(
                      controller: _scroll,
                      padding: const EdgeInsets.symmetric(vertical: 8),
                      children: [
                        _formTabs(context, onSelect: selectForm),
                        _searchRow(context),
                        BannerCarousel(
                          items: items,
                          onTap: (it) => context.push('/book/${it.nid}'),
                        ),
                        const SizedBox(height: 8),
                        const IpEntryRow(),
                        _sectionTitle(context, '随便看看'),
                        Padding(
                          padding: const EdgeInsets.symmetric(horizontal: 16),
                          child: Column(
                            children: [
                              for (final it in _ipItems)
                                BookRowTile(
                                  item: it,
                                  ipLabel: contestIpLabel(it.contest),
                                ),
                              if (_ipError != null)
                                Padding(
                                  padding: const EdgeInsets.symmetric(
                                    vertical: 24,
                                  ),
                                  child: Center(
                                    child: TextButton(
                                      onPressed: _loadIpMore,
                                      child: const Text('加载失败，点按重试'),
                                    ),
                                  ),
                                )
                              else if (_ipLoading)
                                const Padding(
                                  padding: EdgeInsets.symmetric(vertical: 24),
                                  child: Center(
                                    child: CircularProgressIndicator(
                                      strokeWidth: 2,
                                    ),
                                  ),
                                )
                              else if (_ipDone && _ipItems.isNotEmpty)
                                Padding(
                                  padding: const EdgeInsets.fromLTRB(
                                    0,
                                    8,
                                    0,
                                    24,
                                  ),
                                  child: Center(
                                    child: Text(
                                      '— 共 ${_ipItems.length} 本 —',
                                      style: TextStyle(
                                        fontSize: 11,
                                        color: Theme.of(context)
                                            .colorScheme
                                            .onSurfaceVariant,
                                      ),
                                    ),
                                  ),
                                ),
                            ],
                          ),
                        ),
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
              // 对话 tab（6,189 本）：页内浏览体验（纸墨轮播 + 单行题材
              // chips + 页内无限列表），与中篇同构（docs/16）。
              if (_form == 'dialogue') {
                if (_dialogueItems.isEmpty && !_dialogueLoading) {
                  WidgetsBinding.instance.addPostFrameCallback(
                    (_) => _loadDialogueMore(),
                  );
                }
                return Stack(
                  children: [
                    ListView(
                      controller: _scroll,
                      padding: const EdgeInsets.symmetric(vertical: 8),
                      children: [
                        _formTabs(context, onSelect: selectForm),
                        _searchRow(context),
                        _coverBannerCarousel('dialogue'),
                        const SizedBox(height: 4),
                        _dialogueGenreChips(context),
                        const SizedBox(height: 4),
                        _dialogueListSection(context),
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
              // 中篇 tab（944 本）：页内浏览体验（单行题材 chips + 页内
              // 无限列表），与长篇（分区首页）/短篇（入口门户）/IP
              // （入口行+列表）刻意区分，见 docs/16。年份/赛道轴砍掉
              // （双轴双行 chips 可用性差，用户 2026-11-19 定）。
              if (_form == 'medium') {
                if (_mediumItems.isEmpty && !_mediumLoading) {
                  WidgetsBinding.instance.addPostFrameCallback(
                    (_) => _loadMediumMore(),
                  );
                }
                return Stack(
                  children: [
                    ListView(
                      controller: _scroll,
                      padding: const EdgeInsets.symmetric(vertical: 8),
                      children: [
                        _formTabs(context, onSelect: selectForm),
                        _searchRow(context),
                        // 中篇 featured 池 3 本：固定序收藏降序轮播
                        // （bannerProvider('medium')，不做每日随机）。
                        BannerCarousel(
                          items: items,
                          onTap: (it) => context.push('/book/${it.nid}'),
                        ),
                        const SizedBox(height: 4),
                        _mediumGenreChips(context),
                        const SizedBox(height: 4),
                        _mediumListSection(context),
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
                      BannerCarousel(
                        items: items,
                        onTap: (it) => context.push('/book/${it.nid}'),
                      ),
                      const SizedBox(height: 8),
                      _entryGrid(context),
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
                      _ShowcaseSection(
                        provider: finishedShowcaseProvider(_form),
                      ),
                      _entryCards(context),
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
            },
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

  // 宽卡入口：授权作品 / 萌神获奖——打断连续 4×2 网格的节奏，
  // 同时给两个 curated 池补上首页入口（icon 语义见 app/docs/15）。
  Widget _entryCards(BuildContext context) {
    return Column(
      children: [
        _wideEntryCard(
          context,
          icon: Icons.lock,
          title: '授权作品',
          subtitle: '官方授权日本轻小说',
          route: '/licensed',
        ),
        const SizedBox(height: 10),
        _wideEntryCard(
          context,
          icon: Icons.emoji_events,
          title: '萌神获奖',
          subtitle: '官方萌神奖 2018–2024',
          route: '/moe-goddess',
        ),
      ],
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

  // 短篇 tab 入口列表：5 个目的地专属入口（年份/比赛/题材/优质/随机）。
  // 原五格宫格只有一行高、页面只占半屏，改纵向列表（用户 2026-11-19 定）：
  // 每行图标 + 标题 + 描述 + 箭头，撑满页面。icon 登记见 docs/15
  // （比赛/题材复用全局宫格语义）。
  // 中篇 tab 单行题材 chips（横向滚动，FilterChip 单选）：全部题材 +
  // 9 题材。原双轴双行 chips（题材行×年份行+优质互斥）可用性差
  // （用户 2026-11-19 定），简化为题材单轴。
  // 对话 tab 单行题材 chips（横向滚动，FilterChip 单选）：全部题材 +
  // 9 题材（同人占 75%，小题材最少 21 本仍可浏览）。
  Widget _dialogueGenreChips(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final genres = ref.watch(genreGroupsProvider('dialogue'));
    return genres.when(
      loading: () => const SizedBox(height: 46),
      error: (e, _) => const SizedBox(height: 46),
      data: (r) => SizedBox(
        height: 46,
        child: ListView.separated(
          scrollDirection: Axis.horizontal,
          padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 4),
          itemCount: r.groups.length + 1,
          separatorBuilder: (_, _) => const SizedBox(width: 8),
          itemBuilder: (_, i) {
            final name = i == 0 ? null : r.groups[i - 1].genre;
            return FilterChip(
              label: Text(name ?? '全部题材',
                  style: const TextStyle(fontSize: 12)),
              selected: _dialogueGenre == name,
              onSelected: (_) => _setDialogueGenre(name),
              showCheckmark: false,
              selectedColor: scheme.primary.withValues(alpha: .15),
            );
          },
        ),
      ),
    );
  }

  // 对话 tab 页内列表（与中篇同构）：BookRowTile + 失败重试 / 加载
  // spinner / 空态 / "共 N 本"收尾。
  Widget _dialogueListSection(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 16),
      child: Column(
        children: [
          for (final it in _dialogueItems) BookRowTile(item: it),
          if (_dialogueError != null)
            Padding(
              padding: const EdgeInsets.symmetric(vertical: 24),
              child: Center(
                child: TextButton(
                  onPressed: _loadDialogueMore,
                  child: const Text('加载失败，点按重试'),
                ),
              ),
            )
          else if (_dialogueLoading)
            const Padding(
              padding: EdgeInsets.symmetric(vertical: 24),
              child: Center(
                child: CircularProgressIndicator(strokeWidth: 2),
              ),
            )
          else if (_dialogueDone && _dialogueItems.isEmpty)
            Padding(
              padding: const EdgeInsets.symmetric(vertical: 24),
              child: Center(
                child: Text(
                  '该题材下暂无对话作品',
                  style: TextStyle(
                      fontSize: 12, color: scheme.onSurfaceVariant),
                ),
              ),
            )
          else if (_dialogueDone && _dialogueItems.isNotEmpty)
            Padding(
              padding: const EdgeInsets.fromLTRB(0, 8, 0, 24),
              child: Center(
                child: Text(
                  '— 共 ${_dialogueItems.length} 本 —',
                  style: TextStyle(
                      fontSize: 11, color: scheme.onSurfaceVariant),
                ),
              ),
            ),
        ],
      ),
    );
  }

  Widget _mediumGenreChips(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final genres = ref.watch(genreGroupsProvider('medium'));
    return genres.when(
      loading: () => const SizedBox(height: 46),
      error: (e, _) => const SizedBox(height: 46),
      data: (r) => SizedBox(
        height: 46,
        child: ListView.separated(
          scrollDirection: Axis.horizontal,
          padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 4),
          itemCount: r.groups.length + 1,
          separatorBuilder: (_, _) => const SizedBox(width: 8),
          itemBuilder: (_, i) {
            final name = i == 0 ? null : r.groups[i - 1].genre;
            return FilterChip(
              label: Text(name ?? '全部题材',
                  style: const TextStyle(fontSize: 12)),
              selected: _mediumGenre == name,
              onSelected: (_) => _setMediumGenre(name),
              showCheckmark: false,
              selectedColor: scheme.primary.withValues(alpha: .15),
            );
          },
        ),
      ),
    );
  }

  // 中篇 tab 页内列表（照搬 IP tab "随便看看"分区模式）：BookRowTile +
  // 失败重试 / 加载 spinner / 空态（双轴组合可能为空）/ "共 N 本"收尾。
  Widget _mediumListSection(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 16),
      child: Column(
        children: [
          for (final it in _mediumItems) BookRowTile(item: it),
          if (_mediumError != null)
            Padding(
              padding: const EdgeInsets.symmetric(vertical: 24),
              child: Center(
                child: TextButton(
                  onPressed: _loadMediumMore,
                  child: const Text('加载失败，点按重试'),
                ),
              ),
            )
          else if (_mediumLoading)
            const Padding(
              padding: EdgeInsets.symmetric(vertical: 24),
              child: Center(
                child: CircularProgressIndicator(strokeWidth: 2),
              ),
            )
          else if (_mediumDone && _mediumItems.isEmpty)
            Padding(
              padding: const EdgeInsets.symmetric(vertical: 24),
              child: Center(
                child: Text(
                  '该组合下暂无中篇作品',
                  style: TextStyle(
                      fontSize: 12, color: scheme.onSurfaceVariant),
                ),
              ),
            )
          else if (_mediumDone && _mediumItems.isNotEmpty)
            Padding(
              padding: const EdgeInsets.fromLTRB(0, 8, 0, 24),
              child: Center(
                child: Text(
                  '— 共 ${_mediumItems.length} 本 —',
                  style: TextStyle(
                      fontSize: 11, color: scheme.onSurfaceVariant),
                ),
              ),
            ),
        ],
      ),
    );
  }

  Widget _shortEntryGrid(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final entries = [
      (
        Icons.calendar_month,
        '年份榜',
        '榜内面板切换年份',
        '/classic-list?title=年份榜&form=short&year-switchable=1',
      ),
      (
        Icons.emoji_events,
        '比赛榜',
        '侧滑面板切换赛道',
        '/classic-list?title=比赛榜&form=short&contest-switchable=1',
      ),
      (
        Icons.category,
        '题材榜',
        '标签行切换题材',
        '/classic-list?title=题材榜&form=short&genre-switchable=1',
      ),
      (
        Icons.star,
        '优质短篇',
        '同代分位头部',
        '/classic-list?title=${Uri.encodeComponent('优质短篇')}&form=short&order=pct'
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
                  padding:
                      const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
                  decoration: BoxDecoration(
                    color: scheme.surface,
                    borderRadius: BorderRadius.circular(12),
                    border: Border.all(
                        color: scheme.outline.withValues(alpha: .3)),
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
                                  fontSize: 14, fontWeight: FontWeight.w600),
                            ),
                            const SizedBox(height: 2),
                            Text(
                              desc,
                              style: TextStyle(
                                  fontSize: 11,
                                  color: scheme.onSurfaceVariant),
                            ),
                          ],
                        ),
                      ),
                      Icon(Icons.chevron_right,
                          size: 18, color: scheme.onSurfaceVariant),
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
    final list = ref.watch(coverCarouselProvider(form));
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

/// IP tab 入口行：命名 IP（收藏数前 2 的征文）+ 其他（长尾）。
/// contest 即联动 IP 轴（崩坏3征文 → 崩坏3）；文字卡无 icon（docs/15）。
class IpEntryRow extends ConsumerWidget {
  const IpEntryRow({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final scheme = Theme.of(context).colorScheme;
    return ref
        .watch(ipGroupsProvider)
        .when(
          loading: () => const Padding(
            padding: EdgeInsets.symmetric(horizontal: 16),
            child: SizedBox(
              height: 56,
              child: Center(child: CircularProgressIndicator(strokeWidth: 2)),
            ),
          ),
          error: (e, _) => Padding(
            padding: const EdgeInsets.symmetric(horizontal: 16),
            child: Center(
              child: Text('加载失败：$e', style: const TextStyle(fontSize: 12)),
            ),
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
                            right: label == entries.last.$1 ? 0 : 8,
                          ),
                          child: InkWell(
                            onTap: () => context.push(
                              '/ip-books?group=${Uri.encodeComponent(group)}'
                              '&label=${Uri.encodeComponent(label)}',
                            ),
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
                                  Text(
                                    label,
                                    maxLines: 1,
                                    overflow: TextOverflow.ellipsis,
                                    style: TextStyle(
                                      fontFamily: StrataTokens.serif,
                                      fontWeight: FontWeight.w700,
                                      fontSize: 13,
                                    ),
                                  ),
                                  const SizedBox(height: 2),
                                  Text(
                                    '$count 本',
                                    style: TextStyle(
                                      fontSize: 10,
                                      color: scheme.onSurfaceVariant,
                                    ),
                                  ),
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
