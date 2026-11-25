import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../core/providers.dart';
import '../data/api/strata_api.dart';
import '../widgets/back_to_top.dart';
import '../widgets/book_row_tile.dart';

/// 通用榜单列表页（各 tab 入口的落点）：classic 端点 + 任意维度 +
/// order（favs=收藏降序，pct=同代分位降序，docs/form-definitions §6
/// 优质口径）。20 本/页上滑加载。
/// 页内控件：年份 = 顶部固定横向 chip 条（高频榜单轴，常驻）；
/// 比赛赛道 = Drawer（侧滑面板，大池要搜索）；四维筛选（状态/价格/
/// 题材/标签）= 统一筛选 BottomSheet（AppBar filter_list 按钮 + 激活
/// 计数角标）。年份不再进筛选面板（2026-11-25，docs/16）。
class ClassicListPage extends ConsumerStatefulWidget {
  final String title;
  final String form;
  final String? contest;
  final String? wordsBand; // 'short' | 'medium' | 'long'（对话 tab 篇幅轴）
  final String order; // 'favs' | 'pct' | 'clicks' | 'praises' | 'words'
  final bool contestSwitchable;
  final bool metricSwitchable;

  const ClassicListPage({
    super.key,
    required this.title,
    this.form = 'short',
    this.contest,
    this.wordsBand,
    this.order = 'favs',
    this.contestSwitchable = false,
    this.metricSwitchable = false,
  });

  @override
  ConsumerState<ClassicListPage> createState() => _ClassicListPageState();
}

class _ClassicListPageState extends ConsumerState<ClassicListPage> {
  final _scroll = ScrollController();
  final _drawerSearch = TextEditingController();
  bool _showTop = false;
  int? _currentYear; // 年份轴（顶部年份条切换；null=全部年份）
  String? _currentContest; // 比赛轴（drawer 切换）
  String? _currentGenre; // 筛选维度：题材（筛选面板切换）
  String? _fStatus; // 筛选维度：状态（已完结/连载中）
  String? _fPtype; // 筛选维度：价格（免费/VIP/签约，数据驱动）
  List<String> _fTags = const []; // 筛选维度：标签（多选 OR，用户 2026-11-21）
  String _drawerQuery = ''; // drawer 搜索词（本地过滤赛道组）
  String _currentOrder = 'favs'; // 指标轴（经典榜单四榜切换）
  bool _ascending = false; // 逆序（升序）态
  List<RankItem> _items = [];
  bool _loading = false;
  bool _done = false;
  String? _error;

  @override
  void initState() {
    super.initState();
    _currentContest = widget.contest;
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
        status: _fStatus,
        ptype: _fPtype,
        tag: _fTags.isEmpty ? null : _fTags.join(','),
        wordsBand: widget.wordsBand,
        order: _currentOrder == 'favs' ? null : _currentOrder,
        dir: _ascending ? 'asc' : null,
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
      appBar: AppBar(title: Text(_appBarTitle()), actions: [_filterButton()]),
      body: Column(
        children: [
          _yearStrip(),
          if (widget.metricSwitchable) _metricSwitcher(),
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

  // 年份轴独立于筛选：常驻在列表上方，横向滚动；切换后保留其他筛选。
  // 年份使用 /year-groups（form 池口径），不拉 /facets 全量值。
  Widget _yearStrip() {
    final scheme = Theme.of(context).colorScheme;
    final res = ref.watch(yearGroupsProvider(widget.form));
    return SizedBox(
      height: 44,
      child: res.when(
        loading: () => const Center(
          child: SizedBox(
            width: 16,
            height: 16,
            child: CircularProgressIndicator(strokeWidth: 2),
          ),
        ),
        error: (e, _) => Center(
          child: TextButton(
            onPressed: () => ref.invalidate(yearGroupsProvider(widget.form)),
            child: Text(
              '年份加载失败，点按重试',
              style: TextStyle(fontSize: 12, color: scheme.error),
            ),
          ),
        ),
        data: (r) => ListView.separated(
          scrollDirection: Axis.horizontal,
          padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 4),
          itemCount: r.groups.length + 1,
          separatorBuilder: (context, index) => const SizedBox(width: 8),
          itemBuilder: (context, i) {
            if (i == 0) return _yearChip('全部', _currentYear == null, null);
            final g = r.groups[i - 1];
            return _yearChip('${g.year}', _currentYear == g.year, g);
          },
        ),
      ),
    );
  }

  Widget _yearChip(String label, bool selected, YearGroup? g) {
    final chip = ChoiceChip(
      showCheckmark: false,
      visualDensity: VisualDensity.compact,
      materialTapTargetSize: MaterialTapTargetSize.shrinkWrap,
      label: Text(label, style: const TextStyle(fontSize: 12)),
      selected: selected,
      onSelected: (_) => _selectYear(g?.year),
    );
    if (g == null) return chip;
    return Tooltip(message: '${g.year} 代 · ${g.count} 本', child: chip);
  }

  void _selectYear(int? year) {
    if (year == _currentYear) return;
    setState(() {
      _currentYear = year;
      _resetList();
    });
    _scroll.jumpTo(0);
    _loadMore();
  }

  // 筛选面板入口（AppBar 右侧，docs/15：Icons.filter_list = 筛选）：
  // 状态/价格/题材/标签四维 BottomSheet（用户 2026-11-25：年份移出）；
  // 有激活维度时图标带计数角标。
  Widget _filterButton() {
    final n = _activeFilterCount;
    return IconButton(
      tooltip: '筛选',
      icon: Badge(
        isLabelVisible: n > 0,
        label: Text('$n', style: const TextStyle(fontSize: 10)),
        child: const Icon(Icons.filter_list),
      ),
      onPressed: _openFilterSheet,
    );
  }

  int get _activeFilterCount {
    var n = 0;
    if (_fStatus != null) n++;
    if (_fPtype != null) n++;
    if (_currentGenre != null) n++;
    n += _fTags.length;
    return n;
  }

  void _openFilterSheet() {
    showModalBottomSheet<void>(
      context: context,
      isScrollControlled: true,
      useSafeArea: true,
      builder: (ctx) => _FilterSheet(
        form: widget.form,
        genre: _currentGenre,
        status: _fStatus,
        ptype: _fPtype,
        tags: List.of(_fTags),
        onChanged: (genre, status, ptype, tags) =>
            _onFilterChanged(genre, status, ptype, tags),
      ),
    );
  }

  // 筛选面板 live-apply：值未变不重载；变化则重置列表、回顶、重载
  // （面板保持打开，可连续多选维度）。
  void _onFilterChanged(
    String? genre,
    String? status,
    String? ptype,
    List<String> tags,
  ) {
    final changed =
        genre != _currentGenre ||
        status != _fStatus ||
        ptype != _fPtype ||
        tags.join(',') != _fTags.join(',');
    setState(() {
      _currentGenre = genre;
      _fStatus = status;
      _fPtype = ptype;
      _fTags = tags;
      _resetList();
    });
    if (!changed) return;
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
  // SegmentedButton（Material 分段控件，横向平铺四选）+ 尾部逆序按钮。
  Widget _metricSwitcher() {
    const metrics = [
      ('clicks', '点击'),
      ('favs', '收藏'),
      ('praises', '点赞'),
      ('words', '字数'),
    ];
    final scheme = Theme.of(context).colorScheme;
    return Padding(
      padding: const EdgeInsets.fromLTRB(16, 6, 16, 2),
      child: Row(
        children: [
          Expanded(
            child: SegmentedButton<String>(
              segments: [
                for (final (key, label) in metrics)
                  ButtonSegment(value: key, label: Text(label)),
              ],
              // 用户 2026-11-21：去掉激活段右侧的 ✔（默认 showSelectedIcon）。
              showSelectedIcon: false,
              selected: {_currentOrder},
              onSelectionChanged: (sel) => _selectOrder(sel.first),
            ),
          ),
          const SizedBox(width: 8),
          IconButton(
            // 逆序切换（docs/15：Icons.compare_arrows = 逆序）：升序态
            // 图标着色；对四个累计值榜均生效（pct 榜无逆序）。
            tooltip: _ascending ? '切换为降序' : '切换为升序',
            icon: Icon(
              Icons.compare_arrows,
              color: _ascending ? scheme.primary : null,
            ),
            onPressed: _toggleAscending,
          ),
        ],
      ),
    );
  }

  void _toggleAscending() {
    setState(() {
      _ascending = !_ascending;
      _resetList();
    });
    _scroll.jumpTo(0);
    _loadMore();
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

  // 比赛 drawer：各赛道组（contest 归一化聚合 count DESC，N征系篇幅赛项
  // 已并入母赛事）+ 本地搜索过滤 +
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

/// 筛选面板 BottomSheet（用户 2026-11-21 定，2026-11-25 年份移出）：
/// 状态/价格/题材/标签四维，单选 + 「全部」复位；标签维度多选 OR。
/// 年份是高频榜单轴，已改为列表顶部独立横向条（docs/16）。
/// chip 不显示计数、选中不显示 ✔（showCheckmark:false，组件默认是 true，
/// 与 SegmentedButton 口径一致）；点选 live-apply（背后列表实时刷新），
/// 面板保持打开直到「完成」。值列表 = /facets（form 池口径）；状态是
/// 固定枚举，价格值数据驱动（免费/VIP/签约）。
class _FilterSheet extends ConsumerStatefulWidget {
  final String form;
  final String? genre;
  final String? status;
  final String? ptype;
  final List<String> tags;
  final void Function(
    String? genre,
    String? status,
    String? ptype,
    List<String> tags,
  )
  onChanged;

  const _FilterSheet({
    required this.form,
    required this.genre,
    required this.status,
    required this.ptype,
    required this.tags,
    required this.onChanged,
  });

  @override
  ConsumerState<_FilterSheet> createState() => _FilterSheetState();
}

class _FilterSheetState extends ConsumerState<_FilterSheet> {
  static const _tagPreviewLimit = 12;

  final _tagSearch = TextEditingController();
  String? _genre;
  String? _status;
  String? _ptype;
  List<String> _tags = const [];
  bool _tagsExpanded = false;

  @override
  void initState() {
    super.initState();
    _genre = widget.genre;
    _status = widget.status;
    _ptype = widget.ptype;
    _tags = List.of(widget.tags);
  }

  @override
  void dispose() {
    _tagSearch.dispose();
    super.dispose();
  }

  bool get _hasActiveFilters =>
      _genre != null || _status != null || _ptype != null || _tags.isNotEmpty;

  int get _selectedCount {
    var n = 0;
    if (_status != null) n++;
    if (_ptype != null) n++;
    if (_genre != null) n++;
    n += _tags.length;
    return n;
  }

  void _resetAll() {
    if (!_hasActiveFilters) return;
    setState(() {
      _genre = null;
      _status = null;
      _ptype = null;
      _tags = const [];
      _tagsExpanded = false;
      _tagSearch.clear();
    });
    widget.onChanged(_genre, _status, _ptype, _tags);
  }

  void _toggleTag(String name) {
    _pickTags(
      _tags.contains(name)
          ? _tags.where((x) => x != name).toList()
          : [..._tags, name],
    );
  }

  // live-apply：更新本地选中态并通知父页（父页对比后决定是否重载）。
  void _pick(void Function() apply, {required bool changed}) {
    if (!changed) return;
    apply();
    setState(() {});
    widget.onChanged(_genre, _status, _ptype, _tags);
  }

  // 标签多选（OR，用户 2026-11-21）：toggle 单个标签；「全部」= 清空。
  void _pickTags(List<String> next) {
    if (next.join(',') == _tags.join(',')) return;
    _tags = next;
    setState(() {});
    widget.onChanged(_genre, _status, _ptype, _tags);
  }

  Widget _section(String title, Widget chips) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Padding(
          padding: const EdgeInsets.fromLTRB(16, 14, 16, 0),
          child: Text(
            title,
            style: const TextStyle(fontSize: 13, fontWeight: FontWeight.w600),
          ),
        ),
        Padding(padding: const EdgeInsets.fromLTRB(16, 8, 16, 0), child: chips),
      ],
    );
  }

  Widget get _divider => const Divider(height: 20, indent: 16, endIndent: 16);

  Widget _tagSection(FacetsResult f) {
    final scheme = Theme.of(context).colorScheme;
    final query = _tagSearch.text.trim().toLowerCase();
    final selected = _tags.toSet();
    final matched = query.isEmpty
        ? f.tags
        : f.tags.where((t) => t.name.toLowerCase().contains(query)).toList();
    final selectedTags = f.tags
        .where((t) => selected.contains(t.name))
        .toList();
    final unselected = matched
        .where((t) => !selected.contains(t.name))
        .toList();
    final preview = query.isEmpty && !_tagsExpanded
        ? unselected.take(_tagPreviewLimit).toList()
        : unselected;
    final canExpand = query.isEmpty && unselected.length > _tagPreviewLimit;

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Padding(
          padding: const EdgeInsets.fromLTRB(16, 14, 16, 0),
          child: Row(
            children: [
              const Text(
                '标签（多选，OR）',
                style: TextStyle(fontSize: 13, fontWeight: FontWeight.w600),
              ),
              if (_tags.isNotEmpty) ...[
                const SizedBox(width: 8),
                Text(
                  '已选 ${_tags.length}',
                  style: TextStyle(
                    fontSize: 12,
                    color: scheme.onSurfaceVariant,
                  ),
                ),
              ],
            ],
          ),
        ),
        if (f.tags.length > _tagPreviewLimit)
          Padding(
            padding: const EdgeInsets.fromLTRB(16, 8, 16, 0),
            child: TextField(
              controller: _tagSearch,
              onChanged: (_) => setState(() {}),
              decoration: InputDecoration(
                hintText: '搜索标签',
                prefixIcon: const Icon(Icons.search, size: 18),
                suffixIcon: _tagSearch.text.isEmpty
                    ? null
                    : IconButton(
                        tooltip: '清除标签搜索',
                        icon: const Icon(Icons.close, size: 18),
                        onPressed: () {
                          _tagSearch.clear();
                          setState(() {});
                        },
                      ),
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
        Padding(
          padding: const EdgeInsets.fromLTRB(16, 8, 16, 0),
          child: Wrap(
            spacing: 8,
            runSpacing: 4,
            children: [
              _tagChip('全部', _tags.isEmpty, null),
              for (final t in selectedTags) _tagChip(t.name, true, t.name),
              for (final t in preview) _tagChip(t.name, false, t.name),
            ],
          ),
        ),
        if (canExpand)
          Padding(
            padding: const EdgeInsets.only(left: 16, top: 4),
            child: TextButton(
              onPressed: () => setState(() => _tagsExpanded = !_tagsExpanded),
              child: Text(_tagsExpanded ? '收起' : '展开全部（${unselected.length}）'),
            ),
          ),
        if (query.isNotEmpty && matched.isEmpty)
          Padding(
            padding: const EdgeInsets.fromLTRB(16, 4, 16, 0),
            child: Text(
              '没有匹配的标签',
              style: TextStyle(fontSize: 12, color: scheme.onSurfaceVariant),
            ),
          ),
      ],
    );
  }

  // 统一 chip 视觉（用户 2026-11-25）：选中实心填充白字、未选细描边灰字；
  // 单选（状态/价格/题材）与多选（标签）共用同一套配色，不再混用
  // ChoiceChip/FilterChip 的默认皮肤。
  Widget _chipBase(String label, bool selected, VoidCallback onTap) {
    final scheme = Theme.of(context).colorScheme;
    return InkWell(
      borderRadius: BorderRadius.circular(14),
      onTap: onTap,
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
        decoration: BoxDecoration(
          color: selected ? scheme.primary : null,
          border: selected
              ? null
              : Border.all(color: scheme.outline.withValues(alpha: .45)),
          borderRadius: BorderRadius.circular(14),
        ),
        child: Text(
          label,
          style: TextStyle(
            fontSize: 12,
            color: selected ? Colors.white : scheme.onSurfaceVariant,
          ),
        ),
      ),
    );
  }

  Widget _tagChip(String label, bool selected, String? name) {
    return _chipBase(label, selected,
        () => name == null ? _pickTags(const []) : _toggleTag(name));
  }

  Widget _chip(String label, bool selected, void Function() onTap) {
    return _chipBase(label, selected, onTap);
  }

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final res = ref.watch(facetsProvider(widget.form));
    return res.when(
      loading: () => const SizedBox(
        height: 160,
        child: Center(child: CircularProgressIndicator(strokeWidth: 2)),
      ),
      error: (e, _) => Padding(
        padding: const EdgeInsets.all(24),
        child: Text(
          '加载筛选值失败：$e',
          style: TextStyle(fontSize: 12, color: scheme.error),
        ),
      ),
      data: (f) {
        return ConstrainedBox(
          constraints: BoxConstraints(
            maxHeight: MediaQuery.of(context).size.height * 0.85,
          ),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
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
              Padding(
                padding: const EdgeInsets.fromLTRB(16, 12, 16, 0),
                child: Row(
                  children: [
                    Text(
                      '筛选',
                      style: TextStyle(
                        fontSize: 15,
                        fontWeight: FontWeight.w700,
                      ),
                    ),
                    if (_selectedCount > 0) ...[
                      const SizedBox(width: 8),
                      Text(
                        '已选 $_selectedCount 项',
                        style: TextStyle(
                          fontSize: 12,
                          color: scheme.onSurfaceVariant,
                        ),
                      ),
                    ],
                  ],
                ),
              ),
              Flexible(
                child: SingleChildScrollView(
                  padding: const EdgeInsets.only(top: 2, bottom: 8),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      _section(
                        '状态',
                        Wrap(
                          spacing: 8,
                          runSpacing: 4,
                          children: [
                            _chip(
                              '全部',
                              _status == null,
                              () => _pick(
                                () => _status = null,
                                changed: _status != null,
                              ),
                            ),
                            for (final s in ['已完结', '连载中'])
                              _chip(
                                s,
                                _status == s,
                                () => _pick(
                                  () => _status = s,
                                  changed: _status != s,
                                ),
                              ),
                          ],
                        ),
                      ),
                      _divider,
                      _section(
                        '价格',
                        Wrap(
                          spacing: 8,
                          runSpacing: 4,
                          children: [
                            _chip(
                              '全部',
                              _ptype == null,
                              () => _pick(
                                () => _ptype = null,
                                changed: _ptype != null,
                              ),
                            ),
                            for (final p in f.ptypes)
                              _chip(
                                p.name,
                                _ptype == p.name,
                                () => _pick(
                                  () => _ptype = p.name,
                                  changed: _ptype != p.name,
                                ),
                              ),
                          ],
                        ),
                      ),
                      _divider,
                      _section(
                        '题材',
                        Wrap(
                          spacing: 8,
                          runSpacing: 4,
                          children: [
                            _chip(
                              '全部',
                              _genre == null,
                              () => _pick(
                                () => _genre = null,
                                changed: _genre != null,
                              ),
                            ),
                            for (final g in f.genres)
                              _chip(
                                g.name,
                                _genre == g.name,
                                () => _pick(
                                  () => _genre = g.name,
                                  changed: _genre != g.name,
                                ),
                              ),
                          ],
                        ),
                      ),
                      _divider,
                      _tagSection(f),
                    ],
                  ),
                ),
              ),
              SafeArea(
                top: false,
                child: Padding(
                  padding: const EdgeInsets.fromLTRB(16, 8, 16, 12),
                  child: Row(
                    children: [
                      Expanded(
                        child: OutlinedButton(
                          onPressed: _hasActiveFilters ? _resetAll : null,
                          child: const Text('重置'),
                        ),
                      ),
                      const SizedBox(width: 12),
                      Expanded(
                        flex: 2,
                        child: FilledButton(
                          onPressed: () => Navigator.pop(context),
                          child: const Text('完成'),
                        ),
                      ),
                    ],
                  ),
                ),
              ),
            ],
          ),
        );
      },
    );
  }
}
