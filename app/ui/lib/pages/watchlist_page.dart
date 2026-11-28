import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../widgets/book_row_tile.dart';

import '../core/providers.dart';
import '../data/api/strata_api.dart';
import '../widgets/back_to_top.dart';

/// 关注页（watchlist，v6 统一列表，2026-11-28 重版）：
/// 概览统计 + 双模式分段（全部/仅关注/追踪中）+ 分组/题材筛选 + 搜索 +
/// 排序 + 批量管理（长按多选）+ 备注/移组/间隔。数据 = 本地 watchlist
/// （user.db.watchlist JOIN seed.books），观测时序在详情页看（docs/07）。
class WatchlistPage extends ConsumerStatefulWidget {
  const WatchlistPage({super.key});

  @override
  ConsumerState<WatchlistPage> createState() => _WatchlistPageState();
}

class _WatchlistPageState extends ConsumerState<WatchlistPage> {
  String? _genreFilter; // null = 全部
  int _mode = 0; // 0 全部 / 1 仅关注 / 2 追踪中
  int? _groupFilter; // null = 全部（不做分组过滤）
  final int _sort = 0; // 0 最近添加 / 1 上次抓取 / 2 收藏最多
  String _query = '';
  bool _searchMode = false; // AppBar 搜索态：点击搜索 icon 后展开搜索框
  final _scroll = ScrollController();
  bool _showTop = false;

  // 批量管理（长按进入）：选中 nid 集合。
  bool get _batch => _selection.isNotEmpty;
  final Set<int> _selection = {};

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

  Future<void> _reload() async {
    ref.invalidate(watchlistProvider);
    ref.invalidate(watchGroupsProvider);
  }

  Future<void> _remove(WatchItem item) async {
    final handle = await ref.read(bootProvider.future);
    await handle.api.watchRemove(item.nid);
    _reload();
  }

  Future<void> _toggle(WatchItem item) async {
    final handle = await ref.read(bootProvider.future);
    await handle.api.watchSetActive(item.nid, !item.active);
    _reload();
  }

  void _exitBatch() => setState(_selection.clear);

  void _enterBatch(int nid) => setState(() => _selection.add(nid));

  Future<void> _batchRemove() async {
    final handle = await ref.read(bootProvider.future);
    for (final nid in _selection) {
      await handle.api.watchRemove(nid);
    }
    _exitBatch();
    _reload();
  }

  Future<void> _batchMove(int listId) async {
    final handle = await ref.read(bootProvider.future);
    for (final nid in _selection) {
      await handle.api.watchSetList(nid, listId);
    }
    _exitBatch();
    _reload();
  }

  void _showItemSheet(WatchItem item) {
    showModalBottomSheet<void>(
      context: context,
      builder: (_) => _ItemSheet(
        item: item,
        onChanged: _reload,
        onEditNote: () => _editNote(item),
        onMoveGroup: () => _moveToGroup(item),
      ),
    );
  }

  Future<void> _editNote(WatchItem item) async {
    final controller = TextEditingController(text: item.note ?? '');
    final note = await showDialog<String>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('备注'),
        content: TextField(
          controller: controller,
          autofocus: true,
          maxLines: 3,
          decoration: const InputDecoration(
              hintText: '记录为什么关注、读到哪一卷…', border: OutlineInputBorder()),
        ),
        actions: [
          TextButton(onPressed: () => Navigator.pop(context), child: const Text('取消')),
          TextButton(
            onPressed: () => Navigator.pop(context, controller.text),
            child: const Text('保存'),
          ),
        ],
      ),
    );
    if (note == null) return;
    final handle = await ref.read(bootProvider.future);
    await handle.api.watchSetNote(item.nid, note);
    _reload();
  }

  Future<void> _moveToGroup(WatchItem item) async {
    await showModalBottomSheet<void>(
      context: context,
      builder: (_) => _GroupPickerSheet(
        current: item.listId,
        onPick: (listId) async {
          final handle = await ref.read(bootProvider.future);
          await handle.api.watchSetList(item.nid, listId);
          _reload();
        },
      ),
    );
  }

  Future<void> _manageGroups() async {
    await showModalBottomSheet<void>(
      context: context,
      builder: (_) => const _GroupManageSheet(),
    );
    _reload();
  }

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return PopScope(
      canPop: !_batch,
      onPopInvokedWithResult: (didPop, _) {
        if (didPop) return;
        _exitBatch();
      },
      child: Scaffold(
        appBar: _batch ? _batchAppBar(scheme) : _normalAppBar(),
        body: ref.watch(watchlistProvider).when(
              loading: () => const _SkeletonList(),
              error: (e, _) => _ErrorState(
                message: '加载失败：$e',
                onRetry: _reload,
              ),
              data: (items) => _body(context, scheme, items),
            ),
      ),
    );
  }

  PreferredSizeWidget _normalAppBar() {
    final unread =
        ref.watch(notificationsProvider).value?['unread'] as int? ?? 0;
    if (_searchMode) {
      // 搜索态：AppBar 整体变搜索框，返回即退出搜索并清词。
      return AppBar(
        leading: IconButton(
          icon: const Icon(Icons.arrow_back),
          onPressed: () => setState(() {
            _searchMode = false;
            _query = '';
          }),
        ),
        title: TextField(
          autofocus: true,
          onChanged: (v) => setState(() => _query = v.trim()),
          decoration: const InputDecoration(
            isDense: true,
            hintText: '搜索标题 / 作者 / 备注',
            border: InputBorder.none,
          ),
        ),
      );
    }
    return AppBar(
        title: const Text('我的关注'),
        actions: [
          IconButton(
            icon: const Icon(Icons.search),
            tooltip: '搜索',
            onPressed: () => setState(() => _searchMode = true),
          ),
          IconButton(
            // 关注通知入口（2026-11-26）+ 未读角标（2026-11-28）：有未读
            // 关注更新时角标提示。
            tooltip: '关注通知',
            onPressed: () async {
              await context.push('/notifications');
              ref.invalidate(notificationsProvider);
            },
            icon: Badge(
              isLabelVisible: unread > 0,
              label: Text('$unread'),
              child: const Icon(Icons.notifications_outlined),
            ),
          ),
          IconButton(
            icon: const Icon(Icons.folder_outlined),
            tooltip: '管理分组',
            onPressed: _manageGroups,
          ),
        ],
      );
  }

  PreferredSizeWidget _batchAppBar(ColorScheme scheme) => AppBar(
        leading: IconButton(
          icon: const Icon(Icons.close),
          onPressed: _exitBatch,
        ),
        title: Text('已选 ${_selection.length} 项'),
        actions: [
          IconButton(
            icon: const Icon(Icons.drive_file_move_outlined),
            tooltip: '移动到分组',
            onPressed: _selection.isEmpty
                ? null
                : () => showModalBottomSheet<void>(
                      context: context,
                      builder: (_) => _GroupPickerSheet(
                        current: -1,
                        onPick: (listId) => _batchMove(listId),
                      ),
                    ),
          ),
          IconButton(
            icon: Icon(Icons.delete_outline, color: scheme.error),
            tooltip: '取消关注',
            onPressed: _selection.isEmpty ? null : _batchRemove,
          ),
        ],
      );

  Widget _body(BuildContext context, ColorScheme scheme, List<WatchItem> items) {
    if (items.isEmpty) {
      return _EmptyState(onBrowse: () => context.go('/home'));
    }
    final filtered = _applyFilters(items);
    return Stack(
      children: [
        Column(
          children: [
            _Overview(items: items),
            _SearchAndMode(
              query: _query,
              onQuery: (v) => setState(() => _query = v.trim()),
              mode: _mode,
              onMode: (v) => setState(() => _mode = v),
            ),
            _FilterChips(
              items: items,
              groupFilter: _groupFilter,
              onGroup: (v) => setState(() => _groupFilter = v),
              genreFilter: _genreFilter,
              onGenre: (v) => setState(() => _genreFilter = v),
              onManage: _manageGroups,
            ),
            Expanded(
              child: filtered.isEmpty
                  ? Center(
                      child: Text('该筛选下暂无条目',
                          style: TextStyle(color: scheme.onSurfaceVariant)))
                  : RefreshIndicator(
                      onRefresh: () async {
                        ref.invalidate(watchlistProvider);
                        try {
                          await ref.read(watchlistProvider.future);
                        } catch (_) {
                          // 错误态由 provider 的 AsyncValue 渲染。
                        }
                      },
                      child: ListView.builder(
                        controller: _scroll,
                        padding: const EdgeInsets.fromLTRB(16, 8, 16, 16),
                        itemCount: filtered.length,
                        itemBuilder: (context, i) => _WatchCard(
                          item: filtered[i],
                          selected: _selection.contains(filtered[i].nid),
                          batchMode: _batch,
                          onLongPress: () => _enterBatch(filtered[i].nid),
                          onTap: _batch
                              ? () => setState(() {
                                    _selection.contains(filtered[i].nid)
                                        ? _selection.remove(filtered[i].nid)
                                        : _selection.add(filtered[i].nid);
                                  })
                              : () => context.push('/book/${filtered[i].nid}'),
                          onToggle: () => _toggle(filtered[i]),
                          onRemove: () => _remove(filtered[i]),
                          onEditNote: () => _editNote(filtered[i]),
                          onMoveGroup: () => _moveToGroup(filtered[i]),
                          onSheet: () => _showItemSheet(filtered[i]),
                        ),
                      ),
                    ),
            ),
          ],
        ),
        if (_showTop)
          Positioned(
            right: 16,
            bottom: 24,
            child: BackToTop(
              onTap: () => _scroll.animateTo(0,
                  duration: const Duration(milliseconds: 400),
                  curve: Curves.easeOut),
            ),
          ),
      ],
    );
  }

  List<WatchItem> _applyFilters(List<WatchItem> items) {
    var out = items;
    if (_mode == 1) out = out.where((e) => !e.active).toList();
    if (_mode == 2) out = out.where((e) => e.active).toList();
    if (_genreFilter != null) {
      out = out.where((e) => e.genre == _genreFilter).toList();
    }
    if (_groupFilter != null) {
      out = out.where((e) => e.listId == _groupFilter).toList();
    }
    if (_query.isNotEmpty) {
      final q = _query.toLowerCase();
      out = out
          .where((e) =>
              e.title.toLowerCase().contains(q) ||
              e.author.toLowerCase().contains(q) ||
              (e.note ?? '').toLowerCase().contains(q))
          .toList();
    }
    switch (_sort) {
      case 1: // 上次抓取（无记录的排后面）
        out = [...out]..sort((a, b) =>
            (b.lastPollAt ?? 0).compareTo(a.lastPollAt ?? 0));
      case 2: // 收藏最多
        out = [...out]..sort((a, b) =>
            (b.favs ?? -1).compareTo(a.favs ?? -1));
      default: // 最近添加（引擎已按 added_at DESC）
        break;
    }
    return out;
  }
}

/// 概览卡：总数 / 追踪中 / 24h 内有更新——纯本地计数，不伪造时序。
class _Overview extends StatelessWidget {
  final List<WatchItem> items;
  const _Overview({required this.items});

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    Widget stat(String label, String value) {
      return Expanded(
        child: Container(
          padding: const EdgeInsets.symmetric(vertical: 8),
          decoration: BoxDecoration(
            color: scheme.surfaceContainerHighest.withValues(alpha: .4),
            borderRadius: BorderRadius.circular(10),
          ),
          child: Column(
            children: [
              Text(value,
                  style: TextStyle(
                      fontSize: 17,
                      fontWeight: FontWeight.w700,
                      color: scheme.primary)),
              Text(label,
                  style: TextStyle(
                      fontSize: 11, color: scheme.onSurfaceVariant)),
            ],
          ),
        ),
      );
    }

    final tracking = items.where((e) => e.active).length;
    final updated = items
        .where((e) =>
            e.lastPollAt != null &&
            DateTime.now()
                    .difference(DateTime.fromMillisecondsSinceEpoch(
                        e.lastPollAt! * 1000))
                    .inDays <=
                1)
        .length;
    return Padding(
      padding: const EdgeInsets.fromLTRB(16, 8, 16, 0),
      child: Row(
        children: [
          stat('全部', '${items.length}'),
          const SizedBox(width: 8),
          stat('追踪中', '$tracking'),
          const SizedBox(width: 8),
          stat('24h 内有更新', '$updated'),
        ],
      ),
    );
  }
}

/// 双模式分段（全部 / 仅关注 / 追踪中）；搜索已收进 AppBar。
class _SearchAndMode extends StatelessWidget {
  final String query;
  final ValueChanged<String> onQuery;
  final int mode;
  final ValueChanged<int> onMode;

  const _SearchAndMode(
      {required this.query,
      required this.onQuery,
      required this.mode,
      required this.onMode});

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.fromLTRB(16, 4, 16, 0),
      child: SizedBox(
        height: 40,
        child: SegmentedButton<int>(
          segments: const [
            ButtonSegment(value: 0, label: Text('全部')),
            ButtonSegment(value: 1, label: Text('仅关注')),
            ButtonSegment(value: 2, label: Text('追踪中')),
          ],
          selected: {mode},
          showSelectedIcon: false,
          style: const ButtonStyle(
            visualDensity: VisualDensity.compact,
            textStyle: WidgetStatePropertyAll(TextStyle(fontSize: 12)),
          ),
          onSelectionChanged: (s) => onMode(s.first),
        ),
      ),
    );
  }
}

/// 分组 + 题材筛选 chips 行。
class _FilterChips extends ConsumerWidget {
  final List<WatchItem> items;
  final int? groupFilter;
  final ValueChanged<int?> onGroup;
  final String? genreFilter;
  final ValueChanged<String?> onGenre;
  final VoidCallback onManage;

  const _FilterChips(
      {required this.items,
      required this.groupFilter,
      required this.onGroup,
      required this.genreFilter,
      required this.onGenre,
      required this.onManage});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final scheme = Theme.of(context).colorScheme;
    final genres =
        items.map((e) => e.genre).whereType<String>().toSet().toList()..sort();
    return ref.watch(watchGroupsProvider).when(
      loading: () =>
          const Center(child: SizedBox(width: 16, height: 16)),
      error: (e, _) => Center(
          child: Text('分组加载失败', style: TextStyle(fontSize: 12, color: scheme.error))),
      data: (groups) {
        Widget chip(String label, bool selected, VoidCallback onTap) {
          return Padding(
            padding: const EdgeInsets.only(right: 8),
            child: ChoiceChip(
              label: Text(label),
              selected: selected,
              showCheckmark: false,
              onSelected: (_) => onTap(),
              labelStyle: TextStyle(
                  fontSize: 12,
                  color: selected ? scheme.onPrimary : scheme.onSurfaceVariant),
              selectedColor: scheme.primary,
            ),
          );
        }

        return SizedBox(
          height: 44,
          child: ListView(
            scrollDirection: Axis.horizontal,
            padding: const EdgeInsets.symmetric(horizontal: 16),
            children: [
              chip('分组：全部', groupFilter == null, () => onGroup(null)),
              chip('未分组', groupFilter == 0, () => onGroup(0)),
              for (final g in groups)
                chip('${g.name} (${g.count})', groupFilter == g.id,
                    () => onGroup(g.id)),
              chip('管理分组', false, onManage),
              const VerticalDivider(),
              for (final g in ['全部', ...genres])
                chip(g, genreFilter == (g == '全部' ? null : g),
                    () => onGenre(g == '全部' ? null : g)),
            ],
          ),
        );
      },
    );
  }
}

/// 统一行（2026-11-26 书籍列表统一）：与经典榜单同款行（BookRowTile），
/// 长按进入批量多选；trailing 收观测/追踪/更多（备注/移组）操作。
class _WatchCard extends StatelessWidget {
  final WatchItem item;
  final bool selected;
  final bool batchMode;
  final VoidCallback onTap;
  final VoidCallback onLongPress;
  final VoidCallback onToggle;
  final VoidCallback onRemove;
  final VoidCallback onEditNote;
  final VoidCallback onMoveGroup;
  final VoidCallback onSheet;

  const _WatchCard(
      {required this.item,
      required this.selected,
      required this.batchMode,
      required this.onTap,
      required this.onLongPress,
      required this.onToggle,
      required this.onRemove,
      required this.onEditNote,
      required this.onMoveGroup,
      required this.onSheet});

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final added = DateTime.fromMillisecondsSinceEpoch(item.addedAt * 1000);
    final days = DateTime.now().difference(added).inDays;
    final when = days <= 0 ? '今天' : days == 1 ? '昨天' : '$days 天前';
    return InkWell(
      onTap: onTap,
      onLongPress: onLongPress,
      child: BookRowTile(
        item: RankItem.fromJson({
          'rank': 0,
          'nid': item.nid,
          'title': item.title,
          'author': item.genre != null
              ? '${item.author} · ${item.genre}'
              : item.author,
          'cover_url': item.coverUrl,
        }),
        extraTags: [
          if (item.role == 'peer') '对照',
          if (item.note != null && item.note!.isNotEmpty) '备注',
        ],
        trailing: batchMode
            ? Icon(
                selected ? Icons.check_circle : Icons.circle_outlined,
                color: selected ? scheme.primary : scheme.onSurfaceVariant)
            : Column(
                crossAxisAlignment: CrossAxisAlignment.end,
                children: [
                  Text(
                    item.active ? '追踪于 $when' : '保存于 $when',
                    style: TextStyle(
                        fontSize: 10,
                        color: item.active
                            ? scheme.primary
                            : scheme.onSurfaceVariant),
                  ),
                  const SizedBox(height: 4),
                  Row(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      IconButton(
                        icon: Icon(Icons.timeline,
                            size: 18, color: scheme.onSurfaceVariant),
                        tooltip: '观测数据',
                        onPressed: () => context.push('/book/${item.nid}/data'),
                      ),
                      IconButton(
                        icon: Icon(
                            item.active
                                ? Icons.visibility
                                : Icons.visibility_outlined,
                            color: item.active
                                ? scheme.primary
                                : scheme.onSurfaceVariant),
                        tooltip: item.active ? '停止追踪' : '追踪更新',
                        onPressed: onToggle,
                      ),
                      IconButton(
                        icon: Icon(Icons.more_vert,
                            size: 18, color: scheme.onSurfaceVariant),
                        tooltip: '更多',
                        onPressed: onSheet,
                      ),
                    ],
                  ),
                ],
              ),
      ),
    );
  }
}

/// 条目操作面板：备注 / 移动分组 / 取消关注。
class _ItemSheet extends ConsumerWidget {
  final WatchItem item;
  final VoidCallback onChanged;
  final VoidCallback onEditNote;
  final VoidCallback onMoveGroup;

  const _ItemSheet(
      {required this.item,
      required this.onChanged,
      required this.onEditNote,
      required this.onMoveGroup});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    Future<void> act(Future<void> Function(EngineHandle h) f) async {
      final handle = await ref.read(bootProvider.future);
      await f(handle);
      if (context.mounted) Navigator.pop(context);
      onChanged();
    }

    return SafeArea(
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          ListTile(
            leading: const Icon(Icons.notes),
            title: const Text('编辑备注'),
            onTap: () {
              Navigator.pop(context);
              onEditNote();
            },
          ),
          ListTile(
            leading: const Icon(Icons.drive_file_move_outlined),
            title: const Text('移动到分组'),
            onTap: () {
              Navigator.pop(context);
              onMoveGroup();
            },
          ),
          ListTile(
            leading: const Icon(Icons.delete_outline),
            title: const Text('取消关注'),
            onTap: () => act((h) => h.api.watchRemove(item.nid)),
          ),
        ],
      ),
    );
  }
}

/// 分组选择面板：把条目移入某个分组（或未分组）。
class _GroupPickerSheet extends ConsumerWidget {
  final int current;
  final ValueChanged<int> onPick;

  const _GroupPickerSheet({required this.current, required this.onPick});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    return SafeArea(
      child: ref.watch(watchGroupsProvider).when(
            loading: () => const Center(child: CircularProgressIndicator()),
            error: (e, _) => Center(child: Text('加载失败：$e')),
            data: (groups) => Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                ListTile(
                  leading: const Icon(Icons.clear_all),
                  title: const Text('未分组'),
                  onTap: () => _pick(context, 0),
                ),
                for (final g in groups)
                  ListTile(
                    leading: const Icon(Icons.folder_outlined),
                    title: Text(g.name),
                    trailing: Text('${g.count}',
                        style: TextStyle(
                            fontSize: 12, color: Colors.grey.shade600)),
                    onTap: () => _pick(context, g.id),
                  ),
              ],
            ),
          ),
    );
  }

  void _pick(BuildContext context, int id) {
    Navigator.pop(context);
    onPick(id);
  }
}

/// 分组管理面板：建组 / 重命名 / 删除。
class _GroupManageSheet extends ConsumerWidget {
  const _GroupManageSheet();

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    return SafeArea(
      child: ref.watch(watchGroupsProvider).when(
            loading: () => const Center(child: CircularProgressIndicator()),
            error: (e, _) => Center(child: Text('加载失败：$e')),
            data: (groups) => Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                ListTile(
                  leading: const Icon(Icons.add),
                  title: const Text('新建分组'),
                  onTap: () async {
                    final name = await _askName(context, null);
                    if (name == null || name.isEmpty) return;
                    final handle = await ref.read(bootProvider.future);
                    await handle.api.watchGroupCreate(name);
                    ref.invalidate(watchGroupsProvider);
                  },
                ),
                for (final g in groups)
                  ListTile(
                    leading: const Icon(Icons.folder_outlined),
                    title: Text(g.name),
                    trailing: Row(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        IconButton(
                          icon: const Icon(Icons.edit_outlined, size: 18),
                          tooltip: '重命名',
                          onPressed: () async {
                            final name = await _askName(context, g.name);
                            if (name == null || name.isEmpty) return;
                            final handle = await ref.read(bootProvider.future);
                            await handle.api.watchGroupRename(g.id, name);
                            ref.invalidate(watchGroupsProvider);
                          },
                        ),
                        IconButton(
                          icon: const Icon(Icons.delete_outline, size: 18),
                          tooltip: '删除分组',
                          onPressed: () async {
                            final handle = await ref.read(bootProvider.future);
                            await handle.api.watchGroupDelete(g.id);
                            ref.invalidate(watchGroupsProvider);
                          },
                        ),
                      ],
                    ),
                  ),
              ],
            ),
          ),
    );
  }

  Future<String?> _askName(BuildContext context, String? initial) {
    final controller = TextEditingController(text: initial ?? '');
    return showDialog<String>(
      context: context,
      builder: (context) => AlertDialog(
        title: Text(initial == null ? '新建分组' : '重命名分组'),
        content: TextField(
          controller: controller,
          autofocus: true,
          decoration: const InputDecoration(hintText: '分组名称'),
        ),
        actions: [
          TextButton(onPressed: () => Navigator.pop(context), child: const Text('取消')),
          TextButton(
            onPressed: () => Navigator.pop(context, controller.text.trim()),
            child: const Text('保存'),
          ),
        ],
      ),
    );
  }
}

/// 加载骨架：三行占位（列表骨架屏）。
class _SkeletonList extends StatelessWidget {
  const _SkeletonList();

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return ListView(
      padding: const EdgeInsets.fromLTRB(16, 8, 16, 16),
      children: [
        for (int i = 0; i < 6; i++)
          Padding(
            padding: const EdgeInsets.only(bottom: 12),
            child: Row(
              children: [
                Container(
                  width: 44,
                  height: 60,
                  decoration: BoxDecoration(
                    color: scheme.surfaceContainerHighest,
                    borderRadius: BorderRadius.circular(6),
                  ),
                ),
                const SizedBox(width: 12),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Container(
                          height: 14,
                          width: 180,
                          color: scheme.surfaceContainerHighest),
                      const SizedBox(height: 8),
                      Container(
                          height: 10,
                          width: 120,
                          color: scheme.surfaceContainerHighest),
                    ],
                  ),
                ),
              ],
            ),
          ),
      ],
    );
  }
}

/// 错误态 + 重试。
class _ErrorState extends StatelessWidget {
  final String message;
  final VoidCallback onRetry;

  const _ErrorState({required this.message, required this.onRetry});

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return Center(
      child: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          Icon(Icons.cloud_off_outlined,
              size: 48, color: scheme.onSurfaceVariant.withValues(alpha: .6)),
          const SizedBox(height: 10),
          Text(message, style: TextStyle(fontSize: 12, color: scheme.error)),
          const SizedBox(height: 12),
          OutlinedButton(onPressed: onRetry, child: const Text('重试')),
        ],
      ),
    );
  }
}

class _EmptyState extends StatelessWidget {
  final VoidCallback onBrowse;

  const _EmptyState({required this.onBrowse});

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return Center(
      child: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          Icon(Icons.bookmark_outline,
              size: 56, color: scheme.onSurfaceVariant.withValues(alpha: .5)),
          const SizedBox(height: 12),
          Text('还没有关注的书',
              style: TextStyle(
                  fontFamily: 'serif',
                  fontSize: 17,
                  fontWeight: FontWeight.w700)),
          const SizedBox(height: 6),
          Text('去首页找到下一本想读的书，点「关注此书」保存',
              style: TextStyle(fontSize: 12, color: scheme.onSurfaceVariant)),
          const SizedBox(height: 16),
          OutlinedButton(
            onPressed: onBrowse,
            style: OutlinedButton.styleFrom(
                foregroundColor: scheme.primary,
                side: BorderSide(color: scheme.primary)),
            child: const Text('去逛逛'),
          ),
        ],
      ),
    );
  }
}

