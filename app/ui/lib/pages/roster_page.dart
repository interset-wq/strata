import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../core/providers.dart';
import '../data/api/strata_api.dart';
import '../widgets/back_to_top.dart';
import '../widgets/default_cover.dart';

/// 官方清单浏览页（docs/contest-display-in-app.md 形态二）：按需拉官方
/// 参赛清单（引擎按 (tag, page) 缓存 24h/10 年 + 本地 join），无限滚动；
/// 保持官方返回顺序，无排序控件（v1 定案）。
///
/// 2026-11-26：一/二/三征的上游 tagId 是获奖作品标签（635-649），同一
/// 链路改挂「获奖名单 · X」标题——口径永远是获奖名单，不是参赛清单。
///
/// 库外作品点击复用搜索页链路（/book/{nid} → 详情覆盖层 + 自动收录）。
/// 降级（无 tagId / 接口失效）：引擎回落库内子集（source=degraded），
/// 页面顶部提示条——不空白、不清空已显示值。
class RosterPage extends ConsumerStatefulWidget {
  const RosterPage({super.key, required this.contest, this.division});

  final String contest;

  /// 档案页赛项行带进来的赛道；null = 由本页取台账首轨。
  final String? division;

  @override
  ConsumerState<RosterPage> createState() => _RosterPageState();
}

class _RosterPageState extends ConsumerState<RosterPage> {
  final _scroll = ScrollController();
  bool _showTop = false;

  // 赛道（division）在档案组加载后解析：取台账首轨名（单轨事件 = 「全部」，
  // 引擎把它认回空赛道），多轨默认第一轨。
  String _division = '';
  bool _divisionReady = false;

  int _filter = 0; // 0 全部 / 1 仅库内 / 2 仅库外
  List<RosterItem> _items = const [];
  int _page = 0;
  int _pages = 1;
  int? _totalEstimate; // 当前 division 的官方全量规模估算（约 N 篇）
  String _source = '';
  String _sourceKind = ''; // 响应里的 list_kind（roster | award）
  String? _note;
  bool _loading = true;
  bool _loadingMore = false;
  String? _error;
  String? _loadedDivision; // 当前 _items 所属 division（换轨竞态保护）

  @override
  void initState() {
    super.initState();
    _division = widget.division ?? '';
    _scroll.addListener(_onScroll);
  }

  @override
  void dispose() {
    _scroll.dispose();
    super.dispose();
  }

  void _onScroll() {
    final show = _scroll.hasClients && _scroll.offset > 500;
    if (show != _showTop) setState(() => _showTop = show);
    if (!_divisionReady || _loading || _loadingMore) return;
    if (_page >= _pages) return;
    if (_scroll.position.pixels >=
        _scroll.position.maxScrollExtent - 400) {
      _loadPage(_page + 1, reset: false);
    }
  }

  Future<void> _loadPage(int page, {required bool reset}) async {
    _loadedDivision = _division;
    if (reset) {
      // 首载由 build 内的 Consumer builder 触发：此刻 _loading 已为
      // true、_error 已为 null，跳过冗余 setState（build 中同步
      // setState 在 debug 断言崩溃）；事件路径（换轨/重试）照常。
      if (!_loading || _error != null) {
        setState(() {
          _loading = true;
          _error = null;
        });
      }
    } else {
      if (_loadingMore) return;
      setState(() => _loadingMore = true);
    }
    try {
      final handle = await ref.read(bootProvider.future);
      final r = await handle.api.roster(
        contest: widget.contest,
        division: _division,
        page: page,
      );
      if (!mounted || _division != _loadedDivision) return; // 换轨后的旧响应
      setState(() {
        // 显式 if/else：级联 `..addAll` 直接跟在条件表达式后会绑定整个
        // 表达式，reset 时变成 r.items.addAll(r.items) 自加 →
        // Concurrent modification during iteration（真机 2026-11-21 实证）。
        if (reset) {
          _items = r.items;
        } else {
          _items.addAll(r.items);
        }
        _page = r.page;
        _pages = r.pages;
        _totalEstimate = r.totalEstimate;
        _source = r.source;
        _sourceKind = r.listKind;
        _note = r.note;
        _loading = false;
        _loadingMore = false;
      });
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _loading = false;
        _loadingMore = false;
        _error = '清单加载失败：$e';
      });
    }
  }

  void _switchDivision(String d) {
    if (d == _division) return;
    setState(() {
      _division = d;
      _filter = 0;
      _items = const [];
      _totalEstimate = null;
      _loading = true;
      _error = null;
    });
    _loadPage(1, reset: true);
  }

  List<RosterItem> get _visible {
    switch (_filter) {
      case 1:
        return _items.where((it) => it.inLibrary).toList();
      case 2:
        return _items.where((it) => !it.inLibrary).toList();
      default:
        return _items;
    }
  }

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    // 档案组提供 divisions（赛道 chip + 官方条数）和 list_kind（参赛清单
    // 还是获奖名单）；首次解析默认赛道。标题要在 Scaffold 层就定口径，
    // 所以这里 watch，而不是缩在 body 的 Consumer 里。
    ContestGroup? group;
    for (final g
        in ref.watch(contestArchiveProvider).value ?? const <ContestGroup>[]) {
      if (g.name == widget.contest) {
        group = g;
        break;
      }
    }
    if (group != null && !_divisionReady) {
      _divisionReady = true;
      // 档案页赛项行已经指定赛道时不覆盖，只有裸入口才落回首轨。
      if (_division.isEmpty && group.divisions.isNotEmpty) {
        _division = group.divisions.first.name;
      }
      _loadPage(1, reset: true);
    }
    final award = (group?.listKind ?? _sourceKind) == 'award';
    // 档案组未就绪时先叫「清单」，不抢先说错口径。
    final title = group == null
        ? '清单 · ${widget.contest}'
        : '${award ? '获奖名单' : '官方清单'} · ${widget.contest}';
    return Scaffold(
      appBar: AppBar(title: Text(title)),
      body: Stack(
        children: [
          _content(scheme, group, award),
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
    );
  }

  Widget _content(ColorScheme scheme, ContestGroup? group, bool award) {
    final tracks = group?.divisions ?? const <ContestDivision>[];
    // 当前赛道的台账条数（2026-11-24 官方清单快照，零请求）。
    int? ledgerCount;
    for (final d in tracks) {
      if (d.name == _division) ledgerCount = d.roster;
    }
    return Column(
      children: [
        if (tracks.length > 1)
          SizedBox(
            height: 44,
            child: ListView(
              scrollDirection: Axis.horizontal,
              padding: const EdgeInsets.symmetric(horizontal: 16),
              children: [
                for (final d in tracks)
                  Padding(
                    padding: const EdgeInsets.only(right: 8),
                    child: ChoiceChip(
                      label: Text(d.name, style: const TextStyle(fontSize: 12)),
                      selected: _division == d.name,
                      showCheckmark: false,
                      onSelected: (_) => _switchDivision(d.name),
                    ),
                  ),
              ],
            ),
          ),
        if (_source == 'official' &&
            (ledgerCount != null || _totalEstimate != null))
          Padding(
            padding: const EdgeInsets.only(left: 16, top: 2),
            // 口径：这是官方清单条目数，不是参赛总量（v1 只接得到清单），
            // 所以写「清单 N 条」不写「N 篇参赛」；台账缺数时才退回本次
            // 响应 pages×size 的上界（约）。获奖名单同一口径。
            child: Text(
              ledgerCount != null
                  ? '${award ? '获奖名单' : '官方清单'} $ledgerCount 条'
                  : '${award ? '获奖名单' : '官方清单'}约 $_totalEstimate 条',
              style: TextStyle(fontSize: 11, color: scheme.onSurfaceVariant),
            ),
          ),
        Padding(
          padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 6),
          child: SegmentedButton<int>(
            segments: const [
              ButtonSegment(value: 0, label: Text('全部')),
              ButtonSegment(value: 1, label: Text('仅库内')),
              ButtonSegment(value: 2, label: Text('仅库外')),
            ],
            selected: {_filter},
            showSelectedIcon: false,
            onSelectionChanged: (sel) => setState(() => _filter = sel.first),
          ),
        ),
        if (_source == 'degraded') _noteBar(scheme, award),
        Expanded(child: _body(scheme)),
      ],
    );
  }

  /// 降级提示条（引擎回落库内子集时显示 note）。
  Widget _noteBar(ColorScheme scheme, bool award) {
    return Container(
      width: double.infinity,
      color: scheme.tertiaryContainer,
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
      child: Text(
        _note ?? (award ? '仅库内作品，获奖名单不完整' : '仅库内作品，清单不完整'),
        style:
            TextStyle(fontSize: 11.5, color: scheme.onTertiaryContainer),
      ),
    );
  }

  Widget _body(ColorScheme scheme) {
    if (_loading) {
      return const Center(child: CircularProgressIndicator());
    }
    if (_error != null) {
      return Center(
        child: Padding(
          padding: const EdgeInsets.all(24),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Text(
                _error!,
                style: TextStyle(
                    fontSize: 13, color: scheme.onSurfaceVariant),
              ),
              const SizedBox(height: 12),
              OutlinedButton(
                onPressed: () => _loadPage(1, reset: true),
                child: const Text('重试'),
              ),
            ],
          ),
        ),
      );
    }
    final items = _visible;
    if (items.isEmpty) {
      return Center(
        child: Text(
          '暂无作品',
          style: TextStyle(fontSize: 13, color: scheme.onSurfaceVariant),
        ),
      );
    }
    return ListView.separated(
      controller: _scroll,
      padding: const EdgeInsets.only(bottom: 32),
      itemCount: items.length + 1,
      separatorBuilder: (_, _) => const Divider(height: 1),
      itemBuilder: (context, i) {
        if (i == items.length) {
          return _loadingMore
              ? const Padding(
                  padding: EdgeInsets.all(16),
                  child: Center(
                      child: CircularProgressIndicator(strokeWidth: 2)))
              : Padding(
                  padding: const EdgeInsets.all(16),
                  child: Center(
                    child: Text(
                      _page < _pages ? '' : '没有更多了',
                      style: TextStyle(
                          fontSize: 11, color: scheme.onSurfaceVariant),
                    ),
                  ),
                );
        }
        return _RosterRow(item: items[i]);
      },
    );
  }
}

/// 清单行卡（与 BookRowCard 不同构：多一行官方简介 + 库内/库外态）：
/// 封面 + 标题 + 作者·form·状态（库内）/ 库外徽标（库外）。
class _RosterRow extends ConsumerWidget {
  final RosterItem item;

  const _RosterRow({required this.item});

  static const _formLabels = {
    'long': '长篇',
    'medium': '中篇',
    'short': '短篇',
    'dialogue': '对话',
    'ip_collab': 'IP联动',
  };

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final scheme = Theme.of(context).colorScheme;
    final meta = <String>[];
    if (item.inLibrary) {
      if (item.form != null && item.form!.isNotEmpty) {
        meta.add(_formLabels[item.form!] ?? item.form!);
      }
      if (item.status != null && item.status!.isNotEmpty) {
        meta.add(item.status!);
      }
    } else {
      meta.add('库外');
    }
    return InkWell(
      // 库外书先预写清单的 标题/作者/封面 到 book_meta（rank-seed，纯本地
      // 写——同官方榜单页，docs/08 §rank-seed）：详情页首帧渲染 overlay、
      // 完整数据由后台 refresh 静默补全；裸 404 会落全屏「正在收录」兜底
      // 路径，要等上游抓取超时才结束（真机 2026-11-21 实证）。库内书直接
      // 进详情页（种子数据完整）。
      onTap: () async {
        if (!item.inLibrary) {
          try {
            final h = await ref.read(bootProvider.future);
            await h.api.rankSeed(
              nid: item.nid,
              title: item.title,
              author: item.author,
              coverUrl: item.coverUrl ?? '',
            );
          } catch (_) {}
        }
        if (!context.mounted) return;
        context.push('/book/${item.nid}');
      },
      child: Padding(
        padding:
            const EdgeInsets.symmetric(horizontal: 16, vertical: 10),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            coverImage(item.coverUrl, item.nid, width: 44, height: 60),
            const SizedBox(width: 10),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    item.title,
                    style: const TextStyle(
                        fontSize: 13.5, fontWeight: FontWeight.w600),
                    maxLines: 2,
                    overflow: TextOverflow.ellipsis,
                  ),
                  const SizedBox(height: 3),
                  Text(
                    [item.author, ...meta]
                        .where((s) => s.isNotEmpty)
                        .join('  '),
                    style: TextStyle(
                        fontSize: 11.5, color: scheme.onSurfaceVariant),
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                  ),
                  if (item.intro.isNotEmpty) ...[
                    const SizedBox(height: 3),
                    Text(
                      item.intro,
                      style: TextStyle(
                          fontSize: 11.5, color: scheme.onSurfaceVariant),
                      maxLines: 2,
                      overflow: TextOverflow.ellipsis,
                    ),
                  ],
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}
