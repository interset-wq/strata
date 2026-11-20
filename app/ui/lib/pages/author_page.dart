import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../core/providers.dart';
import '../data/api/strata_api.dart';
import '../widgets/back_to_top.dart';
import '../widgets/default_cover.dart';

/// 作者页（数据就绪版；时间轴 UI 待作者规划后改版，
/// docs/author-profile-on-demand §1：作品列表 = 本地 db 时间轴，
/// 头部资料 = 按需抓取 + user.db 7 天缓存）。
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

  final List<RankItem> _books = [];
  bool _booksLoading = false;
  bool _booksDone = false;
  bool _booksFailed = false;
  bool _newestFirst = true;

  static const int _pageSize = 20;
  final ScrollController _scroll = ScrollController();
  bool _showTop = false;

  @override
  void initState() {
    super.initState();
    _scroll.addListener(_onScroll);
    _loadProfile();
    _loadMore();
  }

  @override
  void dispose() {
    _scroll.dispose();
    super.dispose();
  }

  void _onScroll() {
    final show = _scroll.offset > 500;
    if (show != _showTop) setState(() => _showTop = show);
    _loadMoreAtBottom();
  }

  void _loadMoreAtBottom() {
    if (_scroll.hasClients &&
        _scroll.position.pixels >= _scroll.position.maxScrollExtent - 400) {
      _loadMore();
    }
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

  Future<void> _loadMore() async {
    if (_booksLoading || _booksDone || _booksFailed) return;
    setState(() => _booksLoading = true);
    try {
      final h = await ref.read(bootProvider.future);
      final page = await h.api.authorBooks(
        author: widget.author,
        limit: _pageSize,
        offset: _books.length,
        order: _newestFirst ? 'newest' : 'oldest',
      );
      if (!mounted) return;
      setState(() {
        _books.addAll(page);
        _booksDone = page.length < _pageSize;
        _booksLoading = false;
      });
    } catch (_) {
      if (mounted) setState(() { _booksLoading = false; _booksFailed = true; });
    }
  }

  /// 排序切换（docs/08 §author-books order 参数）：清空重新分页加载。
  void _toggleOrder() {
    setState(() {
      _newestFirst = !_newestFirst;
      _books.clear();
      _booksDone = false;
      _booksFailed = false;
    });
    _loadMore();
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
    if (_books.isEmpty && !_booksLoading) {
      return Center(
        child: Text(
          _booksFailed ? '作品列表加载失败' : '该作者在内置库中暂无作品',
          style: TextStyle(color: scheme.onSurfaceVariant),
        ),
      );
    }
    return ListView.builder(
      controller: _scroll,
      padding: const EdgeInsets.fromLTRB(12, 4, 12, 96),
      itemCount: _books.length + (_booksLoading && !_booksDone ? 1 : 0),
      itemBuilder: (context, i) {
        if (i >= _books.length) {
          return const Padding(
            padding: EdgeInsets.all(16),
            child: Center(child: CircularProgressIndicator(strokeWidth: 2)),
          );
        }
        final b = _books[i];
        // est_year 分组头：同年首行前插入（0 年 = 回填沉底书，不分组）。
        final showYear = b.estYear != 0 &&
            (i == 0 || _books[i - 1].estYear != b.estYear);
        return Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            if (showYear) _yearHeader(context, scheme, b.estYear),
            _bookRow(context, b, scheme),
          ],
        );
      },
    );
  }

  Widget _yearHeader(BuildContext context, ColorScheme scheme, int year) {
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
          Text('$year',
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
                child: Image.network(
                  coverImageUrl(b.coverUrl) ?? defaultCoverUrl(b.nid),
                  width: 44,
                  height: 62,
                  fit: BoxFit.cover,
                  loadingBuilder: coverLoadingBuilder,
                  errorBuilder: (_, _, _) => Image.network(
                    defaultCoverUrl(b.nid),
                    width: 44,
                    height: 62,
                    fit: BoxFit.cover,
                    errorBuilder: (_, _, _) => ColoredBox(
                      color: scheme.primary.withValues(alpha: .15),
                      child: Icon(Icons.book_outlined,
                          color: scheme.onSurfaceVariant),
                    ),
                  ),
                ),
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
