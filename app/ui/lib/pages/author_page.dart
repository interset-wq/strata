import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../core/providers.dart';
import '../data/api/strata_api.dart';
import '../widgets/back_to_top.dart';
import '../widgets/default_cover.dart';

/// 形式中文名与固定序（赛事档案页同款口径，docs/17 §7）。
const _formLabels = {
  'long': '长篇',
  'medium': '中篇',
  'short': '短篇',
  'dialogue': '对话',
  'ip_collab': 'IP 联动',
};
const _formOrder = ['long', 'medium', 'short', 'dialogue', 'ip_collab'];

/// 作者页（docs/17 作者维度改版，2026-11-22 定案；2026-11-24 E.30 分位退役）：
/// 头部资料（按需抓取 +
/// user.db 7 天缓存，docs/author-profile-on-demand）+ 作者概览卡（在库/
/// 库外/出道（估）/跨度 + 形式分布）+ 代表作（各 form favs Top-1，
/// E.30）+ 作品时间轴（年份分组、est_date 序、未知年份置末）+
/// 库外作品区块（§6）。全部统计由 /strata/author-books 全量行端上现算
/// （E.30：分位列已退役，代表作按 favs）。红线：est_year 标注估算；
/// 不新增抓取、不写用户数据。
class AuthorPage extends ConsumerStatefulWidget {
  final String author;
  final int bookNid;

  const AuthorPage({super.key, required this.author, this.bookNid = 0});

  @override
  ConsumerState<AuthorPage> createState() => _AuthorPageState();
}

class _AuthorPageState extends ConsumerState<AuthorPage> {
  AuthorProfile? _profile;
  bool _profileLoading = true;

  /// 全量书目（单次拉取，docs/17 §4.5）。
  List<RankItem> _books = const [];
  bool _booksLoading = false;
  bool _booksFailed = false;
  bool _newestFirst = true;

  final ScrollController _scroll = ScrollController();
  bool _showTop = false;

  @override
  void initState() {
    super.initState();
    _scroll.addListener(_onScroll);
    _loadProfile();
    _loadBooks();
  }

  @override
  void dispose() {
    _scroll.dispose();
    super.dispose();
  }

  void _onScroll() {
    final show = _scroll.offset > 500;
    if (show != _showTop) setState(() => _showTop = show);
  }

  Future<void> _loadProfile() async {
    try {
      final h = await ref.read(bootProvider.future);
      final p = await h.api.authorProfile(
        author: widget.author,
        nid: widget.bookNid,
        withIntro: true,
      );
      if (mounted) setState(() { _profile = p; _profileLoading = false; });
    } catch (_) {
      // 降级不阻塞：资料拿不到时头部回退到本地名，书目照常。
      if (mounted) setState(() => _profileLoading = false);
    }
  }

  /// 下拉刷新（用户 2026-11-25）：重新触发一次数据库查询。书单与库外
  /// 差集都是引擎现查，收录状态即时更新；档案走 TTL 缓存不抓网。
  Future<void> _refresh() async {
    await Future.wait([_loadProfile(), _loadBooks(silent: true)]);
  }

  /// 全量书目单次拉取（docs/17 §4.5：limit=200 = 统一契约上限；20260503.26
  /// 种子实测单作者最多 36 本，一页必够）。概览/代表作需全量，单次取回后
  /// 即时计算，无「部分数据」中间态。silent=true 用于下拉刷新：不切全屏
  /// loading，由刷新指示器表达进度。
  Future<void> _loadBooks({bool silent = false}) async {
    if (!silent) setState(() => _booksLoading = true);
    try {
      final h = await ref.read(bootProvider.future);
      final page = await h.api.authorBooks(
        author: widget.author,
        limit: 200,
        offset: 0,
        order: _newestFirst ? 'newest' : 'oldest',
      );
      if (!mounted) return;
      setState(() {
        _books = page;
        _booksLoading = false;
      });
    } catch (_) {
      if (mounted) setState(() { _booksLoading = false; _booksFailed = true; });
    }
  }

  /// 年份未知判定（docs/17 §4.4 统一判定式；20260503.26 种子实测 0 本此类
  /// 书——防御性，分组非空才渲染）。
  static bool _unknownYear(RankItem b) =>
      b.estYear == 0 ||
      b.estDate == null ||
      b.estDate!.isEmpty ||
      b.estDate!.startsWith('0001');

  /// 年份分组键（未知年份自成一组，置于末尾）。
  String _yearKey(RankItem b) => _unknownYear(b) ? '?' : '${b.estYear}';

  /// 时间轴重排（端上，不发网络——数据已全量取回，docs/17 §4.6）：
  /// est_date 字符串比较，年份未知书两个方向都沉底（与引擎 ORDER BY 口径
  /// 一致）。
  void _sortBooks() {
    final list = List<RankItem>.from(_books);
    list.sort((a, b) {
      final ua = _unknownYear(a), ub = _unknownYear(b);
      if (ua != ub) return ua ? 1 : -1;
      final da = a.estDate ?? '', db = b.estDate ?? '';
      final cmp = da.compareTo(db);
      final r = _newestFirst ? -cmp : cmp;
      return r != 0 ? r : a.nid.compareTo(b.nid);
    });
    _books = list;
  }

  /// 排序切换（docs/17 §4.6）：对已取回的全量列表端上重排（不触发网络），
  /// 年份未知书恒沉底。
  void _toggleOrder() {
    setState(() {
      _newestFirst = !_newestFirst;
      _sortBooks();
    });
  }

  /// 代表作：各 form favs Top-1（E.30：分位退役，展示层用经典累计；
  /// docs/17 §4.3）；固定形式序，无作品的 form（含全授权书作者）不出卡。
  List<RankItem> get _represents {
    final best = <String, RankItem>{};
    for (final b in _books) {
      if (b.favs <= 0 || b.form.isEmpty) continue;
      final cur = best[b.form];
      if (cur == null || b.favs > cur.favs) best[b.form] = b;
    }
    return _formOrder
        .where((f) => best.containsKey(f))
        .map((f) => best[f]!)
        .toList();
  }

  /// 库外作品（官方作品集 − seed，引擎差集，docs/author-profile-on-demand
  /// §6）：移动版作品集不截断（用户 2026-11-22 裁定），覆盖作者全部作品。
  List<AuthorWork> get _offLibrary => _profile?.offlibrary ?? const [];

  /// 头部区块数（概览卡 + 代表作 + 时间轴注，各自条件渲染，docs/17 §4）。
  int get _headCount {
    var n = 0;
    if (_books.isNotEmpty) n++;
    if (_represents.isNotEmpty) n++;
    if (_books.isNotEmpty) n++;
    return n;
  }

  int get _itemCount {
    var n = _headCount + _books.length;
    if (_offLibrary.isNotEmpty) n += _offLibrary.length + 1;
    if (_books.length >= 200) n++; // 防御性截断注（实测不会触发）
    return n;
  }

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return Scaffold(
      appBar: AppBar(
        title: Text(widget.author),
        actions: [
          IconButton(
            icon: Icon(_newestFirst ? Icons.south : Icons.north),
            tooltip: _newestFirst ? '当前最新在前，点按最早在前' : '当前最早在前，点按最新在前',
            onPressed: _toggleOrder,
          ),
        ],
      ),
      floatingActionButton: _showTop
          ? BackToTop(onTap: () => _scroll.animateTo(
                0,
                duration: const Duration(milliseconds: 400),
                curve: Curves.easeOut,
              ))
          : null,
      body: Column(
        children: [
          _header(context, scheme),
          Expanded(
            child: _body(context, scheme),
          ),
        ],
      ),
    );
  }

  Widget _body(BuildContext context, ColorScheme scheme) {
    final off = _offLibrary;
    if (_booksLoading) {
      return const Center(child: CircularProgressIndicator());
    }
    if (_books.isEmpty && off.isEmpty) {
      return Center(
        child: Text(
          _booksFailed ? '作品列表加载失败' : '该作者在内置库中暂无作品',
          style: TextStyle(color: scheme.onSurfaceVariant),
        ),
      );
    }
    return RefreshIndicator(
      onRefresh: _refresh,
      child: ListView.builder(
      controller: _scroll,
      padding: const EdgeInsets.fromLTRB(12, 4, 12, 96),
      itemCount: _itemCount,
      itemBuilder: (context, i) {
        if (i < _headCount) {
          return _headItem(context, scheme, i);
        }
        final k = i - _headCount;
        if (k < _books.length) {
          final b = _books[k];
          // est_year 分组头：年组变化时插入（未知年份自成一组置末，
          // docs/17 §4.4）。
          final showYear =
              k == 0 || _yearKey(_books[k - 1]) != _yearKey(b);
          return Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              if (showYear) _yearHeader(context, scheme, b),
              _bookRow(context, b, scheme),
            ],
          );
        }
        final j = k - _books.length;
        if (off.isNotEmpty) {
          if (j == 0) {
            return _offLibraryHeader(context, scheme, off.length);
          }
          if (j <= off.length) {
            return _OffWorkRow(work: off[j - 1], author: widget.author);
          }
        }
        if (_books.length >= 200) {
          return Padding(
            padding: const EdgeInsets.all(16),
            child: Center(
              child: Text('在库 >200，仅显示前 200',
                  style: TextStyle(color: scheme.onSurfaceVariant)),
            ),
          );
        }
        return const SizedBox.shrink();
      },
      ),
    );
  }

  /// 头部区块分发（概览卡 / 代表作 / 时间轴注，docs/17 §4 顺序）。
  Widget _headItem(BuildContext context, ColorScheme scheme, int i) {
    var n = 0;
    if (_books.isNotEmpty) {
      if (i == n) {
        return _OverviewCard(books: _books, offCount: _offLibrary.length);
      }
      n++;
    }
    if (_represents.isNotEmpty) {
      if (i == n) {
        return _RepresentsBlock(reps: _represents);
      }
      n++;
    }
    if (_books.isNotEmpty && i == n) {
      return Padding(
        padding: const EdgeInsets.fromLTRB(4, 10, 4, 0),
        child: Text('年份为估算（锚点插值）；未知年份置末',
            style: TextStyle(
                fontSize: 10.5, color: scheme.onSurfaceVariant)),
      );
    }
    return const SizedBox.shrink();
  }

  /// 年份分组头（点 + 标题 + 分隔线，与库外区块头同款样式，docs/16 不新造
  /// 控件）；未知年份组显示「年份未知」（docs/17 §4.4）。
  Widget _yearHeader(BuildContext context, ColorScheme scheme, RankItem b) {
    final label = _unknownYear(b) ? '年份未知' : '${b.estYear}';
    return Padding(
      padding: const EdgeInsets.fromLTRB(4, 12, 4, 6),
      child: Row(
        children: [
          Container(
            width: 8,
            height: 8,
            decoration:
                BoxDecoration(color: scheme.primary, shape: BoxShape.circle),
          ),
          const SizedBox(width: 8),
          Text(label,
              style: TextStyle(
                  fontSize: 13,
                  fontWeight: FontWeight.w600,
                  color: scheme.primary)),
          const SizedBox(width: 8),
          Expanded(
            child: Divider(
                height: 1, color: scheme.outline.withValues(alpha: .4)),
          ),
        ],
      ),
    );
  }

  Widget _offLibraryHeader(BuildContext context, ColorScheme scheme, int n) {
    return Padding(
      padding: const EdgeInsets.fromLTRB(4, 16, 4, 2),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Container(
                width: 8,
                height: 8,
                decoration: BoxDecoration(
                    color: scheme.secondary, shape: BoxShape.circle),
              ),
              const SizedBox(width: 8),
              Text(
                '其他作品（库外 $n）',
                style: TextStyle(
                    fontSize: 13,
                    fontWeight: FontWeight.w600,
                    color: scheme.secondary),
              ),
              const SizedBox(width: 8),
              Expanded(
                child: Divider(
                    height: 1,
                    color: scheme.outline.withValues(alpha: .4)),
              ),
            ],
          ),
          Padding(
            padding: const EdgeInsets.only(left: 16, top: 4),
            child: Text(
              '来自官方作品集（移动版不截断）；点开即收录，完整数据后台补全。',
              style: TextStyle(
                  fontSize: 11, color: scheme.onSurfaceVariant),
            ),
          ),
        ],
      ),
    );
  }

  Widget _header(BuildContext context, ColorScheme scheme) {
    final p = _profile;
    final name = (p != null && p.authorName.isNotEmpty)
        ? p.authorName
        : widget.author;
    return Padding(
      padding: const EdgeInsets.fromLTRB(16, 8, 16, 12),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          _profileLoading
              ? const SizedBox(
                  width: 56, height: 56,
                  child: CircularProgressIndicator(strokeWidth: 2))
              : CircleAvatar(
                  radius: 28,
                  backgroundImage:
                      (p != null && p.authorAvatar != null &&
                              p.authorAvatar!.isNotEmpty)
                          ? NetworkImage(p.authorAvatar!)
                          : null,
                  child: (p == null || p.authorAvatar == null ||
                          p.authorAvatar!.isEmpty)
                      ? Icon(Icons.person, size: 28, color: scheme.onSurfaceVariant)
                      : null,
                ),
          const SizedBox(width: 12),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(name,
                    style: Theme.of(context).textTheme.titleMedium),
                if (p != null && p.verdict == 'dead') ...[
                  const SizedBox(height: 4),
                  Text('源书已下架，资料暂不可刷新',
                      style: TextStyle(
                          fontSize: 12, color: scheme.onSurfaceVariant)),
                ],
                if (p != null &&
                    p.authorIntro != null &&
                    p.authorIntro!.isNotEmpty) ...[
                  const SizedBox(height: 6),
                  Text(p.authorIntro!,
                      style: TextStyle(
                          fontSize: 13, color: scheme.onSurfaceVariant),
                      maxLines: 4,
                      overflow: TextOverflow.ellipsis),
                ],
              ],
            ),
          ),
        ],
      ),
    );
  }

  Widget _bookRow(BuildContext context, RankItem b, ColorScheme scheme) {
    return Card(
      margin: const EdgeInsets.only(bottom: 8),
      child: InkWell(
        onTap: () => context.push('/book/${b.nid}'),
        child: Padding(
          padding: const EdgeInsets.all(10),
          child: Row(
            children: [
              ClipRRect(
                borderRadius: BorderRadius.circular(6),
                child: coverImage(b.coverUrl, b.nid,
                    width: 44, height: 62),
              ),
              const SizedBox(width: 10),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(b.title,
                        maxLines: 2,
                        overflow: TextOverflow.ellipsis,
                        style: Theme.of(context).textTheme.bodyLarge),
                    const SizedBox(height: 4),
                    Text(
                      [
                        if (b.estDate != null && b.estDate!.isNotEmpty)
                          b.estDate!,
                        if (b.status != null) b.status!,
                      ].join(' · '),
                      style: TextStyle(
                          fontSize: 12, color: scheme.onSurfaceVariant),
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

/// 作者概览卡（docs/17 §4.2）：四个 mini 统计 + 形式分布。
/// 全部由全量在库行端上现算；在库 0 本时整卡隐藏（调用方判定）。
class _OverviewCard extends StatelessWidget {
  final List<RankItem> books;
  final int offCount;

  const _OverviewCard({required this.books, required this.offCount});

  /// 出道年 = 在库非 0 est_year 最小值（估算值，docs/17 §5）。
  int get _debut {
    var min = 0;
    for (final b in books) {
      if (b.estYear > 0 && (min == 0 || b.estYear < min)) min = b.estYear;
    }
    return min;
  }

  int get _span {
    final d = _debut;
    var max = 0;
    for (final b in books) {
      if (b.estYear > max) max = b.estYear;
    }
    return (d == 0 || max <= d) ? 0 : max - d;
  }

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final forms = <String, int>{};
    for (final b in books) {
      if (b.form.isNotEmpty) forms[b.form] = (forms[b.form] ?? 0) + 1;
    }
    return Card(
      margin: const EdgeInsets.only(bottom: 10),
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                _stat(context, '${books.length}', '在库'),
                _stat(context, '$offCount', '库外'),
                _stat(context, _debut == 0 ? '—' : '$_debut', '出道（估）'),
                _stat(context, _span == 0 ? '—' : '$_span 年', '跨度'),
              ],
            ),
            const SizedBox(height: 10),
            Wrap(
              spacing: 6,
              runSpacing: 4,
              children: [
                for (final f in _formOrder)
                  if (forms[f] != null)
                    Container(
                      padding: const EdgeInsets.symmetric(
                          horizontal: 8, vertical: 2),
                      decoration: BoxDecoration(
                        border: Border.all(
                            color: scheme.outline.withValues(alpha: .4)),
                        borderRadius: BorderRadius.circular(999),
                      ),
                      child: Text(
                          '${_formLabels[f] ?? f} ${forms[f]}',
                          style: TextStyle(
                              fontSize: 10.5,
                              color: scheme.onSurfaceVariant)),
                    ),
              ],
            ),
          ],
        ),
      ),
    );
  }

  Widget _stat(BuildContext context, String value, String label) {
    final scheme = Theme.of(context).colorScheme;
    return Expanded(
      child: Column(
        children: [
          Text(value,
              style: const TextStyle(
                  fontSize: 15, fontWeight: FontWeight.w700)),
          const SizedBox(height: 1),
          Text(label,
              style: TextStyle(
                  fontSize: 10, color: scheme.onSurfaceVariant)),
        ],
      ),
    );
  }
}

/// 代表作（docs/17 §4.3）：各 form 同世代收藏分位 Top-1（docs/12 红线：
/// 原始收藏数永不排序）；横向封面行，点击进详情。
class _RepresentsBlock extends StatelessWidget {
  final List<RankItem> reps;

  const _RepresentsBlock({required this.reps});

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Padding(
          padding: const EdgeInsets.fromLTRB(4, 4, 4, 6),
          child: Row(
            children: [
              Container(
                width: 8,
                height: 8,
                decoration: BoxDecoration(
                    color: scheme.tertiary, shape: BoxShape.circle),
              ),
              const SizedBox(width: 8),
              Text('代表作',
                  style: TextStyle(
                      fontSize: 13,
                      fontWeight: FontWeight.w600,
                      color: scheme.tertiary)),
              const SizedBox(width: 8),
              Expanded(
                child: Divider(
                    height: 1, color: scheme.outline.withValues(alpha: .4)),
              ),
            ],
          ),
        ),
        SizedBox(
          height: 128,
          child: ListView.separated(
            scrollDirection: Axis.horizontal,
            itemCount: reps.length,
            separatorBuilder: (_, _) => const SizedBox(width: 8),
            itemBuilder: (context, i) {
              final b = reps[i];
              return Material(
                color: scheme.surface,
                borderRadius: BorderRadius.circular(10),
                child: InkWell(
                  borderRadius: BorderRadius.circular(10),
                  onTap: () => context.push('/book/${b.nid}'),
                  child: Container(
                    width: 92,
                    padding: const EdgeInsets.all(6),
                    decoration: BoxDecoration(
                      borderRadius: BorderRadius.circular(10),
                      border: Border.all(
                          color: scheme.outline.withValues(alpha: .4)),
                    ),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Expanded(
                          child: ClipRRect(
                            borderRadius: BorderRadius.circular(6),
                            child: coverImage(b.coverUrl, b.nid,
                                width: 80, height: 106),
                          ),
                        ),
                        const SizedBox(height: 4),
                        Text(b.title,
                            maxLines: 1,
                            overflow: TextOverflow.ellipsis,
                            style: const TextStyle(
                                fontSize: 10.5,
                                fontWeight: FontWeight.w600)),
                        Text(_formLabels[b.form] ?? b.form,
                            maxLines: 1,
                            overflow: TextOverflow.ellipsis,
                            style: TextStyle(
                                fontSize: 9.5, color: scheme.tertiary)),
                      ],
                    ),
                  ),
                ),
              );
            },
          ),
        ),
        const SizedBox(height: 10),
      ],
    );
  }
}

/// 库外作品行（作者页「其他作品」区块，docs/author-profile-on-demand §6）：
/// 官方作品集只有 nid + 标题（无 form/分位），封面走确定性兜底；点击 =
/// rankSeed 预写 + 进详情页（与官方榜单/清单页同一条库外收录链路）。
class _OffWorkRow extends ConsumerWidget {
  final AuthorWork work;
  final String author;

  const _OffWorkRow({required this.work, required this.author});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final scheme = Theme.of(context).colorScheme;
    return Card(
      margin: const EdgeInsets.only(bottom: 8),
      child: InkWell(
        onTap: () async {
          try {
            final h = await ref.read(bootProvider.future);
            await h.api.rankSeed(
              nid: work.nid,
              title: work.title,
              author: author,
              coverUrl: '',
            );
          } catch (_) {}
          if (!context.mounted) return;
          context.push('/book/${work.nid}');
        },
        child: Padding(
          padding: const EdgeInsets.all(10),
          child: Row(
            children: [
              ClipRRect(
                borderRadius: BorderRadius.circular(6),
                child: coverImage(null, work.nid, width: 44, height: 62),
              ),
              const SizedBox(width: 10),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(work.title,
                        maxLines: 2,
                        overflow: TextOverflow.ellipsis,
                        style: Theme.of(context).textTheme.bodyLarge),
                    const SizedBox(height: 4),
                    Text('库外 · ${work.nid}',
                        style: TextStyle(
                            fontSize: 12, color: scheme.onSurfaceVariant)),
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
