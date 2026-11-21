import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../core/providers.dart';
import '../data/api/strata_api.dart';
import '../widgets/back_to_top.dart';
import '../widgets/book_row_tile.dart';

/// 通用榜单列表页（短篇 tab 各入口的落点）：classic 端点 + 任意
/// year/contest/genre 轴 + order（favs=收藏降序，pct=同代分位降序，
/// docs/form-definitions §6 优质短篇口径）。20 本/页上滑加载。
/// 页内轴切换器（用户 2026-11-19 定：入口不做中间页，直达榜单 + 页内切轴），
/// 三种控件刻意不重复：年份 = ModalBottomSheet、比赛 = Drawer（侧滑面板）、
/// 题材 = FilterChip 行。
class ClassicListPage extends ConsumerStatefulWidget {
  final String title;
  final String form;
  final int? year;
  final String? contest;
  final String? genre;
  final String? wordsBand; // 'short' | 'medium' | 'long'（对话 tab 篇幅轴）
  final String order; // 'favs' | 'pct' | 'clicks' | 'praises' | 'words'
  final bool yearSwitchable;
  final bool contestSwitchable;
  final bool genreSwitchable;
  final bool metricSwitchable;

  const ClassicListPage({
    super.key,
    required this.title,
    this.form = 'short',
    this.year,
    this.contest,
    this.genre,
    this.wordsBand,
    this.order = 'favs',
    this.yearSwitchable = false,
    this.contestSwitchable = false,
    this.genreSwitchable = false,
    this.metricSwitchable = false,
  });

  @override
  ConsumerState<ClassicListPage> createState() => _ClassicListPageState();
}

class _ClassicListPageState extends ConsumerState<ClassicListPage> {
  final _scroll = ScrollController();
  final _drawerSearch = TextEditingController();
  bool _showTop = false;
  int? _currentYear; // 年份轴（bottom sheet 切换）
  String? _currentContest; // 比赛轴（drawer 切换）
  String? _currentGenre; // 题材轴（chip 行切换）
  String _drawerQuery = ''; // drawer 搜索词（本地过滤 38 组）
  String _currentOrder = 'favs'; // 指标轴（经典榜单四榜切换）
  List<RankItem> _items = [];
  bool _loading = false;
  bool _done = false;
  String? _error;

  @override
  void initState() {
    super.initState();
    _currentYear = widget.year;
    _currentContest = widget.contest;
    _currentGenre = widget.genre;
    const metrics = ['clicks', 'favs', 'praises', 'words'];
    _currentOrder = widget.metricSwitchable
        ? (metrics.contains(widget.order) ? widget.order : 'clicks')
        : widget.order;
    _loadMore();
    _scroll.addListener(() {
      // 距底 400px 预取下一页。
      if (_scroll.position.pixels >= _scroll.position.maxScrollExtent - 400) {
        _loadMore();
      }
      final show = _scroll.offset > 500;
      if (show != _showTop) setState(() => _showTop = show);
    });
  }

  @override
  void dispose() {
    _scroll.dispose();
    _drawerSearch.dispose();
    super.dispose();
  }

  Future<void> _loadMore() async {
    if (_loading || _done) return;
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final handle = await ref.read(bootProvider.future);
      final page = await handle.api.rankingClassic(
        form: widget.form,
        year: _currentYear,
        contest: _currentContest,
        genre: _currentGenre,
        wordsBand: widget.wordsBand,
        order: _currentOrder == 'favs' ? null : _currentOrder,
        limit: 20,
        offset: _items.length,
      );
      if (!mounted) return;
      setState(() {
        _items = [..._items, ...page];
        _done = page.length < 20;
        _loading = false;
      });
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _error = '$e';
        _loading = false;
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      // 比赛轴启用时提供侧滑面板（AppBar 自动出现汉堡按钮作为入口）。
      drawer: widget.contestSwitchable ? _buildContestDrawer() : null,
      appBar: AppBar(title: Text(_appBarTitle())),
      body: Column(
        children: [
          if (widget.metricSwitchable) _metricSwitcher(),
          if (widget.yearSwitchable) _yearSelector(),
          if (widget.genreSwitchable) _genreChips(),
          Expanded(
            child: RefreshIndicator(
              onRefresh: () async {
                setState(() {
                  _items = [];
                  _done = false;
                });
                await _loadMore();
              },
              child: Stack(
                children: [
                  ListView.builder(
                    controller: _scroll,
                    padding: const EdgeInsets.fromLTRB(16, 8, 16, 80),
                    itemCount: _items.length + 1,
                    itemBuilder: (context, i) {
                      if (i == _items.length) return _tail();
                      return BookRowTile(item: _items[i]);
                    },
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
              ),
            ),
          ),
        ],
      ),
    );
  }

  // 年份切换条（固定列表上方）：胶囊按钮显示当前轴，点开
  // ModalBottomSheet 选择面板（用户 2026-11-19 定：dropdown 是 web 表单
  // 风格，美观性一般，改 bottom sheet）。数据 = /year-groups。
  Widget _yearSelector() {
    final scheme = Theme.of(context).colorScheme;
    final res = ref.watch(yearGroupsProvider(widget.form));
    return res.when(
      loading: () => const SizedBox(height: 52),
      error: (e, _) => const SizedBox(height: 52),
      data: (r) {
        String label;
        if (_currentYear == null) {
          label = '全部年份 · ${r.total} 本';
        } else {
          int? cnt;
          for (final g in r.groups) {
            if (g.year == _currentYear) {
              cnt = g.count;
              break;
            }
          }
          label = cnt == null ? '$_currentYear' : '$_currentYear · $cnt 本';
        }
        return Padding(
          padding: const EdgeInsets.fromLTRB(16, 2, 16, 6),
          child: InkWell(
            borderRadius: BorderRadius.circular(12),
            onTap: () => _openYearSheet(context, r),
            child: Container(
              padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
              decoration: BoxDecoration(
                color: scheme.surface,
                borderRadius: BorderRadius.circular(12),
                border: Border.all(color: scheme.outline.withValues(alpha: .4)),
              ),
              child: Row(
                children: [
                  Icon(
                    Icons.calendar_month,
                    size: 18,
                    color: scheme.onSurfaceVariant,
                  ),
                  const SizedBox(width: 8),
                  Expanded(
                    child: Text(
                      label,
                      style: const TextStyle(
                        fontSize: 13,
                        fontWeight: FontWeight.w600,
                      ),
                    ),
                  ),
                  Icon(
                    Icons.expand_more,
                    size: 18,
                    color: scheme.onSurfaceVariant,
                  ),
                ],
              ),
            ),
          ),
        );
      },
    );
  }

  // 年份选择 bottom sheet：全部年份 + 各年（年份降序 + 本数 + 选中态），
  // 固定 62% 屏高、内部滚动，圆角纸面容器。
  void _openYearSheet(BuildContext context, YearGroupsResult r) {
    final scheme = Theme.of(context).colorScheme;
    showModalBottomSheet<void>(
      context: context,
      backgroundColor: Colors.transparent,
      builder: (ctx) => SizedBox(
        height: MediaQuery.of(ctx).size.height * 0.62,
        child: Container(
          decoration: BoxDecoration(
            color: scheme.surface,
            borderRadius: const BorderRadius.vertical(top: Radius.circular(20)),
          ),
          padding: EdgeInsets.only(
            bottom: MediaQuery.of(ctx).viewInsets.bottom,
          ),
          child: Column(
            children: [
              const SizedBox(height: 12),
              Container(
                width: 36,
                height: 4,
                decoration: BoxDecoration(
                  color: scheme.outline.withValues(alpha: .3),
                  borderRadius: BorderRadius.circular(2),
                ),
              ),
              const SizedBox(height: 14),
              Text(
                '选择年份',
                style: const TextStyle(
                  fontSize: 15,
                  fontWeight: FontWeight.w700,
                ),
              ),
              const SizedBox(height: 6),
              Expanded(
                child: ListView.builder(
                  padding: const EdgeInsets.symmetric(vertical: 8),
                  itemCount: r.groups.length + 1,
                  itemBuilder: (c, i) {
                    final year = i == 0 ? null : r.groups[i - 1].year;
                    final count = i == 0 ? r.total : r.groups[i - 1].count;
                    final selected = year == _currentYear;
                    return InkWell(
                      onTap: () {
                        Navigator.pop(ctx);
                        _selectYear(year);
                      },
                      child: Container(
                        padding: const EdgeInsets.symmetric(
                          horizontal: 20,
                          vertical: 13,
                        ),
                        color: selected
                            ? scheme.primary.withValues(alpha: .08)
                            : null,
                        child: Row(
                          children: [
                            Text(
                              year == null ? '全部年份' : '$year',
                              style: TextStyle(
                                fontSize: 14,
                                fontWeight: selected
                                    ? FontWeight.w700
                                    : FontWeight.w500,
                                color: selected ? scheme.primary : null,
                              ),
                            ),
                            const Spacer(),
                            Text(
                              '$count 本',
                              style: TextStyle(
                                fontSize: 12,
                                color: scheme.onSurfaceVariant,
                              ),
                            ),
                            if (selected)
                              Icon(
                                Icons.check,
                                size: 18,
                                color: scheme.primary,
                              ),
                          ],
                        ),
                      ),
                    );
                  },
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }

  void _selectYear(int? y) {
    if (y == _currentYear) return;
    setState(() {
      _currentYear = y;
      _items = const [];
      _done = false;
      _error = null;
      _loading = false;
    });
    _scroll.jumpTo(0);
    _loadMore();
  }

  // 已选比赛轴时标题追加赛道标签（drawer 入口 = AppBar 汉堡按钮）。
  String _appBarTitle() {
    if (widget.contestSwitchable && _currentContest != null) {
      return '${widget.title}  ${contestIpLabel(_currentContest)}';
    }
    if (widget.metricSwitchable) {
      const labels = {
        'clicks': '点击榜',
        'favs': '收藏榜',
        'praises': '点赞榜',
        'words': '字数榜',
      };
      return '${widget.title}  ${labels[_currentOrder] ?? ''}';
    }
    return widget.title;
  }

  // 指标切换条（第 4 种不重复控件形态，docs/16）：既有三种为
  // 胶囊+BottomSheet / 汉堡+Drawer / FilterChip 行，四指标经典榜用
  // SegmentedButton（Material 分段控件，横向平铺四选）。
  Widget _metricSwitcher() {
    const metrics = [
      ('clicks', '点击'),
      ('favs', '收藏'),
      ('praises', '点赞'),
      ('words', '字数'),
    ];
    return Padding(
      padding: const EdgeInsets.fromLTRB(16, 6, 16, 2),
      child: SegmentedButton<String>(
        segments: [
          for (final (key, label) in metrics)
            ButtonSegment(value: key, label: Text(label)),
        ],
        selected: {_currentOrder},
        onSelectionChanged: (sel) => _selectOrder(sel.first),
      ),
    );
  }

  void _selectOrder(String o) {
    if (o == _currentOrder) return;
    setState(() {
      _currentOrder = o;
      _resetList();
    });
    _scroll.jumpTo(0);
    _loadMore();
  }

  // 比赛 drawer：38 个赛道组（contest 聚合 count DESC）+ 本地搜索过滤 +
  // 选中态。material drawer 的标准触发 = AppBar 汉堡 / 屏幕左缘右滑。
  Widget _buildContestDrawer() {
    final scheme = Theme.of(context).colorScheme;
    final res = ref.watch(contestGroupsProvider(widget.form));
    return Drawer(
      backgroundColor: scheme.surface,
      child: SafeArea(
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Padding(
              padding: const EdgeInsets.fromLTRB(16, 16, 16, 8),
              child: Text(
                '征文赛道',
                style: const TextStyle(
                  fontSize: 16,
                  fontWeight: FontWeight.w700,
                ),
              ),
            ),
            Padding(
              padding: const EdgeInsets.symmetric(horizontal: 16),
              child: TextField(
                controller: _drawerSearch,
                onChanged: (v) => setState(() => _drawerQuery = v),
                decoration: InputDecoration(
                  hintText: '搜索赛道',
                  prefixIcon: Icon(Icons.search, size: 18),
                  isDense: true,
                  filled: true,
                  fillColor: scheme.surface,
                  border: OutlineInputBorder(
                    borderRadius: BorderRadius.circular(12),
                    borderSide: BorderSide(
                      color: scheme.outline.withValues(alpha: .4),
                    ),
                  ),
                ),
              ),
            ),
            const SizedBox(height: 8),
            Expanded(
              child: res.when(
                loading: () => const Center(
                  child: CircularProgressIndicator(strokeWidth: 2),
                ),
                error: (e, _) => Center(
                  child: Text(
                    '加载失败：$e',
                    style: TextStyle(fontSize: 12, color: scheme.error),
                  ),
                ),
                data: (r) {
                  final groups = _drawerQuery.isEmpty
                      ? r.groups
                      : r.groups
                            .where(
                              (g) =>
                                  g.contest.contains(_drawerQuery) ||
                                  g.label.contains(_drawerQuery),
                            )
                            .toList();
                  return ListView.builder(
                    itemCount: groups.length,
                    itemBuilder: (c, i) {
                      final g = groups[i];
                      final selected = g.contest == _currentContest;
                      return ListTile(
                        leading: Icon(
                          Icons.emoji_events,
                          size: 18,
                          color: selected
                              ? scheme.primary
                              : scheme.onSurfaceVariant,
                        ),
                        title: Text(
                          g.label,
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                          style: TextStyle(
                            fontSize: 14,
                            fontWeight: selected
                                ? FontWeight.w700
                                : FontWeight.w500,
                            color: selected ? scheme.primary : null,
                          ),
                        ),
                        trailing: Text(
                          '${g.count} 本',
                          style: TextStyle(
                            fontSize: 12,
                            color: scheme.onSurfaceVariant,
                          ),
                        ),
                        onTap: () {
                          Navigator.pop(context);
                          _selectContest(g.contest);
                        },
                      );
                    },
                  );
                },
              ),
            ),
          ],
        ),
      ),
    );
  }

  // 题材 chip 行：「全部题材」+ 各题材（本数），FilterChip 单选切换。
  Widget _genreChips() {
    final scheme = Theme.of(context).colorScheme;
    final res = ref.watch(genreGroupsProvider(widget.form));
    return res.when(
      loading: () => const SizedBox(height: 48),
      error: (e, _) => const SizedBox(height: 48),
      data: (r) => Padding(
        padding: const EdgeInsets.fromLTRB(16, 2, 16, 8),
        child: Wrap(
          spacing: 8,
          runSpacing: 8,
          children: [
            FilterChip(
              label: const Text('全部题材', style: TextStyle(fontSize: 12)),
              selected: _currentGenre == null,
              onSelected: (_) => _selectGenre(null),
              selectedColor: scheme.primary.withValues(alpha: .15),
            ),
            for (final g in r.groups)
              FilterChip(
                label: Text(
                  '${g.genre}  ${g.count} 本',
                  style: const TextStyle(fontSize: 12),
                ),
                selected: _currentGenre == g.genre,
                onSelected: (_) => _selectGenre(g.genre),
                selectedColor: scheme.primary.withValues(alpha: .15),
              ),
          ],
        ),
      ),
    );
  }

  // 切轴通用：重置列表并回顶重载。
  void _resetList() {
    _items = const [];
    _done = false;
    _error = null;
    _loading = false;
  }

  void _selectContest(String? c) {
    if (c == _currentContest) return;
    setState(() {
      _currentContest = c;
      _resetList();
    });
    _scroll.jumpTo(0);
    _loadMore();
  }

  void _selectGenre(String? g) {
    if (g == _currentGenre) return;
    setState(() {
      _currentGenre = g;
      _resetList();
    });
    _scroll.jumpTo(0);
    _loadMore();
  }

  // 列表尾部：加载中 spinner / 失败重试 / 空态 / 到底标记。
  Widget _tail() {
    if (_error != null) {
      return Padding(
        padding: const EdgeInsets.symmetric(vertical: 24),
        child: Center(
          child: TextButton(
            onPressed: _loadMore,
            child: const Text('加载失败，点按重试'),
          ),
        ),
      );
    }
    if (_loading) {
      return const Padding(
        padding: EdgeInsets.symmetric(vertical: 24),
        child: Center(child: CircularProgressIndicator(strokeWidth: 2)),
      );
    }
    if (_items.isEmpty) {
      return const Padding(
        padding: EdgeInsets.symmetric(vertical: 48),
        child: Center(child: Text('该口径下暂无作品', style: TextStyle(fontSize: 12))),
      );
    }
    if (_done) {
      return const Padding(
        padding: EdgeInsets.symmetric(vertical: 24),
        child: Center(child: Text('没有更多了', style: TextStyle(fontSize: 11))),
      );
    }
    return const SizedBox.shrink();
  }
}
