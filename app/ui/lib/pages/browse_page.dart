import 'package:flutter/material.dart';

import '../widgets/default_cover.dart';
import '../widgets/metric_badge.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../core/providers.dart';
import '../data/api/strata_api.dart';
import '../widgets/back_to_top.dart';
import '../widgets/book_row_card.dart';

/// 二级浏览页模式：宫格四入口共用，数据维度不同。
enum BrowseMode { category, status, contest, short }

/// 二级浏览页：分类（题材榜）/ 状态（连载/完结）/ 比赛（征文作品）/
/// 短篇（短篇榜）。按 mockups.html 06–09 屏落地，口径与榜单页一致。
class BrowsePage extends ConsumerStatefulWidget {
  final BrowseMode mode;

  /// 初始赛事（赛事档案页"浏览全部作品"跳转携带，query c）。
  final String? initialContest;

  const BrowsePage({super.key, required this.mode, this.initialContest});

  @override
  ConsumerState<BrowsePage> createState() => _BrowsePageState();
}

class _BrowsePageState extends ConsumerState<BrowsePage> {
  String? _filter; // 分类页=题材名；状态页=状态文案
  String _contest = ''; // 比赛页：'' = 全部参赛作品；否则具体届次名
  final _scroll = ScrollController();
  bool _showTop = false;

  @override
  void initState() {
    super.initState();
    if (widget.initialContest != null && widget.initialContest!.isNotEmpty) {
      _contest = widget.initialContest!;
    }
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

  String get _title => switch (widget.mode) {
        BrowseMode.category => '分类找书',
        BrowseMode.status => '按状态浏览',
        BrowseMode.contest => '征文比赛',
        BrowseMode.short => '短篇榜',
      };

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        leading: IconButton(icon: const Icon(Icons.arrow_back), onPressed: () => context.pop()),
        title: Text(_title),
        actions: const [
          IconButton(icon: Icon(Icons.search), onPressed: null),
        ],
      ),
      body: _Body(
        mode: widget.mode,
        filter: _filter,
        contest: _contest,
        scroll: _scroll,
        showTop: _showTop,
        onFilter: (f) => setState(() => _filter = f),
        onContest: (c) => setState(() => _contest = c),
      ),
    );
  }
}

class _Body extends ConsumerWidget {
  final BrowseMode mode;
  final String? filter;
  final String contest;
  final ScrollController scroll;
  final bool showTop;
  final ValueChanged<String?> onFilter;
  final ValueChanged<String> onContest;

  const _Body({
    required this.mode,
    required this.filter,
    required this.contest,
    required this.scroll,
    required this.showTop,
    required this.onFilter,
    required this.onContest,
  });

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final scheme = Theme.of(context).colorScheme;
    final mode = this.mode;
    return Stack(
      children: [
        ListView(
          controller: scroll,
          padding: const EdgeInsets.all(16),
      children: [
        Text(_caliberNote(mode),
            style: TextStyle(fontSize: 11, color: scheme.onSurfaceVariant)),
        const SizedBox(height: 10),
        if (mode == BrowseMode.category) _chips(context, const ['魔幻', '玄幻', '古风', '科幻', '校园', '都市', '游戏', '悬疑'], filter, onFilter),
        if (mode == BrowseMode.status) _chips(context, const ['连载中', '已完结'], filter, onFilter),
        if (mode == BrowseMode.contest)
          Align(
            alignment: Alignment.centerLeft,
            child: ActionChip(
              label: Text(
                contest == '' ? '全部比赛 ▾' : contest,
                style: TextStyle(fontSize: 12, color: scheme.secondary),
              ),
              side: BorderSide(color: scheme.secondary),
              onPressed: () => _pickContest(context, ref),
            ),
          ),
        const SizedBox(height: 12),
        if (mode == BrowseMode.contest && contest == '')
          _contestBanner(context),
        if (mode == BrowseMode.short)
          ref.watch(shortRankingProvider).when(
                loading: () => const Center(
                    child: Padding(
                        padding: EdgeInsets.all(24),
                        child: CircularProgressIndicator())),
                error: (e, _) => Padding(
                    padding: const EdgeInsets.all(16),
                    child: Text('加载失败：$e')),
                data: (items) => Column(
                  children: [
                    for (final it in items) _ShortCard(item: it),
                  ],
                ),
              ),
        if (mode != BrowseMode.short)
          ..._rankItems(context, ref).map(
            (it) => BookRowCard(item: it),
          ),
        ],
        ),
        if (showTop)
          Positioned(
            right: 16,
            bottom: 24,
            child: BackToTop(
              onTap: () => scroll.animateTo(
                  0,
                  duration: const Duration(milliseconds: 400),
                  curve: Curves.easeOut),
            ),
          ),
      ],
    );
  }

  String _caliberNote(BrowseMode mode) => switch (mode) {
        BrowseMode.contest => '经典大赛累计收藏榜（排除授权作品）',
        BrowseMode.short => '短篇 · 按平台累计收藏排序',
        _ => '按平台累计收藏排序 · 排除授权作品',
      };

  Iterable<RankItem> _rankItems(BuildContext context, WidgetRef ref) {
    final items = ref.watch(
        _browseProvider((mode: mode, filter: filter ?? '', contest: contest)));
    return items.value ?? const [];
  }

  Future<void> _pickContest(BuildContext context, WidgetRef ref) async {
    // 赛事名来自赛事档案（归并后的事件名，含对话类分轨；零新增请求）。
    final groups = await ref.read(contestArchiveProvider.future);
    if (!context.mounted) return;
    await showModalBottomSheet<void>(
      context: context,
      builder: (context) => SafeArea(
        child: ListView(
          shrinkWrap: true,
          children: [
            Padding(
              padding: const EdgeInsets.all(16),
              child: Text('选择征文比赛（共 ${groups.length} 届）',
                  style: Theme.of(context).textTheme.titleLarge),
            ),
            for (final g in groups)
              ListTile(
                title: Text(g.name),
                trailing: Text('${g.count}',
                    style: TextStyle(
                        fontSize: 12,
                        color: Theme.of(context)
                            .colorScheme
                            .onSurfaceVariant)),
                onTap: () {
                  onContest(g.name);
                  Navigator.pop(context);
                },
              ),
          ],
        ),
      ),
    );
  }
}

// ---------------------------------------------------------------------------
// 数据

typedef _BrowseQuery = ({BrowseMode mode, String filter, String contest});

final _browseProvider = FutureProvider.autoDispose
    .family<List<RankItem>, _BrowseQuery>((ref, q) async {
  final handle = await ref.watch(bootProvider.future);
  return handle.api.rankingClassic(
    genre: q.mode == BrowseMode.category ? q.filter : null,
    status: q.mode == BrowseMode.status ? q.filter : null,
    contest: q.mode == BrowseMode.contest ? (q.contest == '' ? '1' : q.contest) : null,
  );
});

// ---------------------------------------------------------------------------
// 卡片

Widget _contestBanner(BuildContext context) {
  final scheme = Theme.of(context).colorScheme;
  return Container(
    width: double.infinity,
    margin: const EdgeInsets.only(bottom: 12),
    padding: const EdgeInsets.all(10),
    decoration: BoxDecoration(
      color: scheme.primary.withValues(alpha: .12),
      borderRadius: BorderRadius.circular(16),
    ),
    child: Text('❋ 征文比赛作品 · 选择一届查看',
        style: TextStyle(fontSize: 11.5, color: scheme.onSurfaceVariant)),
  );
}

Widget _chips(
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

class _ShortCard extends StatelessWidget {
  final ShortItem item;

  const _ShortCard({required this.item});

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final top = item.rank <= 3;
    final words = item.words;
    return Card(
      margin: const EdgeInsets.only(bottom: 10),
      child: InkWell(
        onTap: () => context.push('/book/${item.nid}'),
        borderRadius: BorderRadius.circular(16),
        child: Padding(
          padding: const EdgeInsets.all(12),
          child: Row(
            children: [
              SizedBox(
                width: 30,
                child: Text(
                  '${item.rank}',
                  textAlign: TextAlign.center,
                  style: TextStyle(
                    fontFamily: 'serif',
                    fontSize: top ? 20 : 18,
                    fontWeight: FontWeight.w700,
                    color: top ? scheme.primary : scheme.onSurfaceVariant,
                  ),
                ),
              ),
              const SizedBox(width: 12),
              Container(
                width: 40,
                height: 56,
                decoration: BoxDecoration(
                  borderRadius: BorderRadius.circular(6),
                  boxShadow: [
                    BoxShadow(
                        color: scheme.primary.withValues(alpha: .25),
                        offset: const Offset(-4, 4)),
                  ],
                ),
                child: ClipRRect(
                  borderRadius: BorderRadius.circular(6),
                  child: coverImage(item.coverUrl, item.nid,
                      title: item.title),
                ),
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
                            ?.copyWith(fontSize: 13.5)),
                    const SizedBox(height: 3),
                    Text(item.author,
                        style: TextStyle(
                            fontSize: 11, color: scheme.onSurfaceVariant)),
                    const SizedBox(height: 5),
                    Wrap(
                      spacing: 4,
                      children: [
                        if (words != null)
                          bookBadge(context, wanText(words),
                              fg: scheme.onSurfaceVariant),
                        bookBadge(context, '收藏 ${wanText(item.favs)}',
                            fg: scheme.secondary, icon: MetricIcons.favs),
                      ],
                    ),
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

