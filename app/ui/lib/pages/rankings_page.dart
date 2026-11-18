import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../widgets/default_cover.dart';

import '../core/providers.dart';
import '../data/api/strata_api.dart';

/// Classic 六榜侧栏（官方式）：映射到平台累计值排序（docs/12 展示列）。
const _boards = [
  ('recommend', '推荐榜'),
  ('popular', '人气榜'),
  ('favs', '收藏榜'),
  ('new', '新书榜'),
  ('finish', '完结榜'),
  ('words', '字数榜'),
];

final _boardProvider = FutureProvider.autoDispose
    .family<List<RankItem>, (String, int)>((ref, arg) async {
  final handle = await ref.watch(bootProvider.future);
  return handle.api.rankingBoard(kind: arg.$1, limit: 50, offset: arg.$2);
});

/// 榜单页（mockups 10 屏定稿）：header tab（Classic 主线 + 量化预留）、
/// 官方式左侧榜单侧栏、右侧大封面卡列表、back-to-top。
class RankingsPage extends ConsumerStatefulWidget {
  const RankingsPage({super.key});

  @override
  ConsumerState<RankingsPage> createState() => _RankingsPageState();
}

class _RankingsPageState extends ConsumerState<RankingsPage> {
  String _kind = 'recommend';
  final _scroll = ScrollController();
  bool _showTop = false;

  @override
  void initState() {
    super.initState();
    _scroll.addListener(() {
      final show = _scroll.offset > 500;
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
    final scheme = Theme.of(context).colorScheme;
    return Scaffold(
      appBar: AppBar(
        title: Text('榜单'),
        actions: [
          IconButton(
              icon: const Icon(Icons.swap_vert),
              onPressed: () => context.push('/discover')),
        ],
      ),
      body: Column(
        children: [
          // header tab：Classic 主线，量化模式预留（数据分析中）
          Container(
            height: 42,
            decoration: BoxDecoration(
                border: Border(
                    bottom: BorderSide(color: scheme.outline.withValues(alpha: .3)))),
            child: Row(
              children: [
                const SizedBox(width: 16),
                _modeTab(context, 'Classic', true, null),
                const SizedBox(width: 22),
                _modeTab(context, '量化', false, '数据分析中'),
              ],
            ),
          ),
          Expanded(
            child: Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                // 左侧榜单侧栏：朱砂胶囊选中
                SizedBox(
                  width: 92,
                  child: ListView(
                    padding: const EdgeInsets.symmetric(vertical: 14),
                    children: [
                      for (final (kind, label) in _boards)
                        Padding(
                          padding: const EdgeInsets.fromLTRB(8, 0, 8, 4),
                          child: GestureDetector(
                            onTap: () => setState(() => _kind = kind),
                            child: Container(
                              padding: const EdgeInsets.symmetric(vertical: 9),
                              alignment: Alignment.center,
                              decoration: BoxDecoration(
                                color: _kind == kind
                                    ? scheme.primary
                                    : Colors.transparent,
                                borderRadius: BorderRadius.circular(999),
                              ),
                              child: Text(label,
                                  style: TextStyle(
                                    fontSize: 13,
                                    fontWeight: _kind == kind
                                        ? FontWeight.w700
                                        : FontWeight.w400,
                                    color: _kind == kind
                                        ? scheme.onPrimary
                                        : scheme.onSurfaceVariant,
                                  )),
                            ),
                          ),
                        ),
                    ],
                  ),
                ),
                Expanded(
                  child: Stack(
                    children: [
                      _BoardList(key: ValueKey(_kind), kind: _kind, scroll: _scroll),
                      if (_showTop)
                        Positioned(
                          right: 10,
                          bottom: 10,
                          child: _BackToTop(onTap: () => _scroll.animateTo(0,
                              duration: const Duration(milliseconds: 400),
                              curve: Curves.easeOut)),
                        ),
                    ],
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }

  Widget _modeTab(BuildContext context, String label, bool active, String? note) {
    final scheme = Theme.of(context).colorScheme;
    return GestureDetector(
      onTap: active ? null : null,
      child: Container(
        padding: const EdgeInsets.symmetric(vertical: 8, horizontal: 2),
        decoration: BoxDecoration(
            border: Border(
                bottom: BorderSide(
                    width: 2,
                    color: active
                        ? scheme.primary
                        : Colors.transparent))),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            Text(label,
                style: TextStyle(
                    fontSize: 14,
                    fontWeight: active ? FontWeight.w700 : FontWeight.w400,
                    color: active ? scheme.primary : scheme.onSurfaceVariant)),
            if (note != null) ...[
              const SizedBox(width: 4),
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 1),
                decoration: BoxDecoration(
                    border: Border.all(color: scheme.outline.withValues(alpha: .4)),
                    borderRadius: BorderRadius.circular(999)),
                child: Text(note,
                    style: TextStyle(
                        fontSize: 9, color: scheme.onSurfaceVariant)),
              ),
            ],
          ],
        ),
      ),
    );
  }
}

class _BoardList extends ConsumerWidget {
  final String kind;
  final ScrollController scroll;

  const _BoardList({super.key, required this.kind, required this.scroll});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final items = ref.watch(_boardProvider((kind, 0)));
    return items.when(
      loading: () => const Center(child: CircularProgressIndicator()),
      error: (e, _) => Padding(
          padding: const EdgeInsets.all(16), child: Text('加载失败：$e')),
      data: (list) => ListView.builder(
        controller: scroll,
        padding: const EdgeInsets.fromLTRB(14, 14, 14, 60),
        itemCount: list.length + 1,
        itemBuilder: (context, i) {
          if (i == list.length) {
            return Padding(
              padding: const EdgeInsets.only(top: 6),
              child: Text('上滑加载更多 · 平台累计值，老书占优',
                  textAlign: TextAlign.center,
                  style: TextStyle(
                      fontSize: 11, color: schemeOf(context).onSurfaceVariant)),
            );
          }
          return _BoardCard(item: list[i]);
        },
      ),
    );
  }
}

ColorScheme schemeOf(BuildContext context) => Theme.of(context).colorScheme;

class _BoardCard extends StatelessWidget {
  final RankItem item;

  const _BoardCard({required this.item});

  @override
  Widget build(BuildContext context) {
    final scheme = schemeOf(context);
    final coverUrl = item.coverUrl;
    final hasCover = coverUrl != null && coverUrl.isNotEmpty;
    return Padding(
      padding: const EdgeInsets.only(bottom: 16),
      child: InkWell(
        onTap: () => context.push('/book/${item.nid}'),
        borderRadius: BorderRadius.circular(10),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            // 大封面：有封面拼 CDN 前缀；无封面书脊字占位（官方式降级）
            SizedBox(
              width: 104,
              height: 140,
              child: hasCover
                  ? ClipRRect(
                      borderRadius: BorderRadius.circular(10),
                      child: Image.network(
                        coverImageUrl(coverUrl)!,
                        fit: BoxFit.cover,
                        loadingBuilder: coverLoadingBuilder,
                        errorBuilder: (_, _, _) => defaultCover(item.nid, radius: 10),
                      ),
                    )
                  : defaultCover(item.nid, radius: 10),
            ),
            const SizedBox(width: 12),
            Expanded(
              child: SizedBox(
                height: 140,
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(item.title,
                        maxLines: 2,
                        overflow: TextOverflow.ellipsis,
                        style: const TextStyle(
                            fontSize: 14, fontWeight: FontWeight.w600, height: 1.4)),
                    const SizedBox(height: 6),
                    Text(item.author,
                        style: TextStyle(
                            fontSize: 11.5, color: scheme.onSurfaceVariant)),
                    const SizedBox(height: 6),
                    Row(
                      children: [
                        if (item.genre != null)
                          _solidBadge(context, item.genre!, scheme.primary),
                        if (item.status != null) ...[
                          const SizedBox(width: 4),
                          _solidBadge(
                              context,
                              item.status!,
                              item.status == '已完结'
                                  ? scheme.secondary
                                  : scheme.tertiary),
                        ],
                      ],
                    ),
                    const Spacer(),
                    if (item.words != null)
                      Text('${_wan(item.words!)}+字',
                          style: TextStyle(
                              fontSize: 12,
                              color: scheme.primary,
                              fontWeight: FontWeight.w600)),
                  ],
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

Widget _solidBadge(BuildContext context, String text, Color bg) {
  return Container(
    padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 1),
    decoration: BoxDecoration(
        color: bg, borderRadius: BorderRadius.circular(4)),
    child: Text(text,
        style: TextStyle(
            fontSize: 10, color: Theme.of(context).colorScheme.onPrimary)),
  );
}

class _BackToTop extends StatelessWidget {
  final VoidCallback onTap;

  const _BackToTop({required this.onTap});

  @override
  Widget build(BuildContext context) {
    final scheme = schemeOf(context);
    return Material(
      color: scheme.surface,
      borderRadius: BorderRadius.circular(20),
      elevation: 3,
      child: InkWell(
        onTap: onTap,
        customBorder: const CircleBorder(),
        child: SizedBox(
          width: 40,
          height: 40,
          child: Icon(Icons.arrow_upward, size: 20, color: scheme.primary),
        ),
      ),
    );
  }
}

String _wan(int n) {
  if (n >= 10000) return '${(n / 10000).toStringAsFixed(0)}万';
  return '$n';
}
