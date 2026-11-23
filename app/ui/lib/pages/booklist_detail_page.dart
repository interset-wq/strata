import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../core/providers.dart';
import '../data/api/strata_api.dart';
import '../widgets/back_to_top.dart';
import '../widgets/book_row_card.dart';
import '../widgets/default_cover.dart';
import '../widgets/metric_badge.dart';

/// 书单详情页（docs/booklist-in-app.md）：头部卡片（#id 标题 + 简介 +
/// 作者 + N 部作品 + 更新日期）+ 作品列表（官方顺序，无排序控制）；
/// 行卡 = 封面 + 标题 + 作者/题材 + 字数/点击/收藏（官方累计值，纯
/// 展示——docs/12 红线）+ 完结状态 + 逐本推荐语。库内叠加 form 徽标
/// 直接进详情页，库外点击先 rankSeed 预写再进详情页（收录链路同
/// roster 行）。
class BooklistDetailPage extends ConsumerStatefulWidget {
  const BooklistDetailPage({super.key, required this.id});

  final int id;

  @override
  ConsumerState<BooklistDetailPage> createState() => _BooklistDetailPageState();
}

class _BooklistDetailPageState extends ConsumerState<BooklistDetailPage> {
  final _scroll = ScrollController();

  bool _showTop = false;
  BooklistDetail? _detail;
  bool _loading = true;
  String? _error;

  static const _formLabels = {
    'short': '短篇',
    'medium': '中篇',
    'long': '长篇',
    'dialogue': '对话',
    'ip_collab': 'IP',
  };

  @override
  void initState() {
    super.initState();
    _scroll.addListener(_onScroll);
    _load();
  }

  @override
  void dispose() {
    _scroll.dispose();
    super.dispose();
  }

  void _onScroll() {
    final show = _scroll.hasClients && _scroll.offset > 500;
    if (show != _showTop) setState(() => _showTop = show);
  }

  Future<void> _load() async {
    final handle = await ref.read(bootProvider.future);
    if (!mounted) return;
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final d = await handle.api.booklistNovels(widget.id);
      if (!mounted) return;
      setState(() {
        _detail = d;
        _loading = false;
      });
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _loading = false;
        _error = '书单加载失败：$e';
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final d = _detail;
    return Scaffold(
      appBar: AppBar(title: Text('书单 #${widget.id}')),
      body: Stack(
        children: [
          if (_loading)
            const Center(child: CircularProgressIndicator(strokeWidth: 2))
          else if (_error != null || d == null)
            Center(
              child: Column(
                mainAxisAlignment: MainAxisAlignment.center,
                children: [
                  Text(
                    _error ?? '书单不存在',
                    style: TextStyle(
                        fontSize: 12, color: scheme.onSurfaceVariant),
                  ),
                  const SizedBox(height: 12),
                  FilledButton(
                    onPressed: _load,
                    child: const Text('重试', style: TextStyle(fontSize: 12.5)),
                  ),
                ],
              ),
            )
          else
            ListView(
              controller: _scroll,
              padding: const EdgeInsets.symmetric(vertical: 8),
              children: [
                _header(
                  context,
                  d.booklist,
                  inLibrary: d.items.where((n) => n.inLibrary).length,
                ),
                for (final n in d.items) _novelRow(context, n),
                Padding(
                  padding: const EdgeInsets.fromLTRB(0, 16, 0, 24),
                  child: Center(
                    child: Text(
                      '— 共 ${d.items.length} 部 —',
                      style: TextStyle(
                          fontSize: 11, color: scheme.onSurfaceVariant),
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

  Widget _header(BuildContext context, Booklist b, {required int inLibrary}) {
    final scheme = Theme.of(context).colorScheme;
    return Container(
      margin: const EdgeInsets.all(16),
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: scheme.surfaceContainerLow,
        borderRadius: BorderRadius.circular(12),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text.rich(
            TextSpan(
              children: [
                TextSpan(
                  text: '#${b.id} ',
                  style: TextStyle(
                    fontSize: 14,
                    fontWeight: FontWeight.w700,
                    color: scheme.primary,
                  ),
                ),
                TextSpan(
                  text: b.title,
                  style:
                      const TextStyle(fontSize: 14, fontWeight: FontWeight.w700),
                ),
              ],
            ),
          ),
          if (b.summary.isNotEmpty) ...[
            const SizedBox(height: 6),
            Text(
              b.summary,
              style: TextStyle(fontSize: 12, color: scheme.onSurfaceVariant),
              maxLines: 4,
              overflow: TextOverflow.ellipsis,
            ),
          ],
          const SizedBox(height: 8),
          Row(
            children: [
              Flexible(
                child: Text(
                  [b.author, if (b.vip) 'VIP']
                      .where((s) => s.isNotEmpty)
                      .join(' '),
                  style:
                      TextStyle(fontSize: 11, color: scheme.onSurfaceVariant),
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                ),
              ),
              const Spacer(),
              Text(
                '${b.novelNum} 部作品${b.updated.isEmpty ? '' : '  ${b.updated}'}',
                style:
                    TextStyle(fontSize: 11, color: scheme.onSurfaceVariant),
              ),
            ],
          ),
          const SizedBox(height: 4),
          // 书单自身统计（recommendNum/markNum 为官方累计值，纯展示，
          // docs/12 红线）+ 本地 join 的库内占比。
          Row(
            children: [
              Text(
                '库内 $inLibrary/${b.novelNum}',
                style:
                    TextStyle(fontSize: 10.5, color: scheme.onSurfaceVariant),
              ),
              const SizedBox(width: 10),
              Text(
                '推荐 ${b.recommends}',
                style:
                    TextStyle(fontSize: 10.5, color: scheme.onSurfaceVariant),
              ),
              const SizedBox(width: 10),
              Text(
                '收藏 ${b.markNum}',
                style:
                    TextStyle(fontSize: 10.5, color: scheme.onSurfaceVariant),
              ),
            ],
          ),
        ],
      ),
    );
  }

  Widget _novelRow(BuildContext context, BooklistNovel n) {
    final scheme = Theme.of(context).colorScheme;
    final metaParts = [
      if (n.type.isNotEmpty) n.type,
      n.finish ? '已完结' : '连载中',
      if (n.inLibrary && n.form.isNotEmpty) _formLabels[n.form] ?? n.form,
    ];
    return InkWell(
      onTap: () async {
        if (!n.inLibrary) {
          try {
            final h = await ref.read(bootProvider.future);
            await h.api.rankSeed(
              nid: n.nid,
              title: n.title,
              author: n.author,
              coverUrl: n.cover,
              genre: n.type,
            );
          } catch (_) {}
        }
        if (!context.mounted) return;
        context.push('/book/${n.nid}');
      },
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 10),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            coverImage(n.cover, n.nid, width: 44, height: 60),
            const SizedBox(width: 10),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    n.title,
                    style: const TextStyle(
                        fontSize: 13.5, fontWeight: FontWeight.w600),
                    maxLines: 2,
                    overflow: TextOverflow.ellipsis,
                  ),
                  const SizedBox(height: 3),
                  Text(
                    [n.author, ...metaParts]
                        .where((s) => s.isNotEmpty)
                        .join('  '),
                    style:
                        TextStyle(fontSize: 11.5, color: scheme.onSurfaceVariant),
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                  ),
                  const SizedBox(height: 5),
                  Row(
                    children: [
                      MetricBadge(
                          icon: MetricIcons.words, text: wanText(n.words)),
                      const SizedBox(width: 10),
                      MetricBadge(
                          icon: MetricIcons.clicks, text: wanText(n.clicks)),
                      const SizedBox(width: 10),
                      MetricBadge(
                          icon: MetricIcons.favs, text: wanText(n.favs)),
                    ],
                  ),
                  if (n.note.isNotEmpty) ...[
                    const SizedBox(height: 4),
                    Text(
                      n.note,
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
