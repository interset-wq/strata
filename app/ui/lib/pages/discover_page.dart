import 'package:cached_network_image/cached_network_image.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../core/providers.dart';
import '../widgets/default_cover.dart';
import '../widgets/metric_badge.dart';
import '../data/api/strata_api.dart';

/// 发现流 = 推荐层落点（docs/12 §2/§3、app/docs/18-runtime-metrics.md）：
/// 量化推荐流 /recommend（form 内 cqs 排序、cps 中层带筛选；k 为篇幅偏好
/// 权重，>0 时运行时 clx 重排），游标分页每批 20 本，上滑自动加载，
/// back-to-top。展示层
/// 与推荐层解耦——本流恒走量化信号，平台累计值只作展示锚点、不参与
/// 排序（docs/12 §3.2 红线）。文案按「你可能错过的书」口径
/// （docs/12 §7.2）；mockup 期的 "Classic" tab 行与 swap 占位按钮已
/// 移除（模式切换属榜单页正式 UI 的待拍板项，发现流不挂模式）。
class DiscoverPage extends ConsumerStatefulWidget {
  const DiscoverPage({super.key});

  @override
  ConsumerState<DiscoverPage> createState() => _DiscoverPageState();
}

class _DiscoverPageState extends ConsumerState<DiscoverPage> {
  final List<RankItem> _items = [];
  String? _cursor;
  bool _loading = false;
  bool _done = false;
  bool _showTop = false;
  double _k = 0; // 篇幅偏好权重（报告 24 §2.5）：0=纯 cqs
  bool _kLoaded = false; // 落盘 pref 只在首屏解析一次，切档后以 UI 为准
  final _scroll = ScrollController();

  @override
  void initState() {
    super.initState();
    _load();
    _scroll.addListener(_onScroll);
  }

  void _onScroll() {
    final show = _scroll.offset > 500;
    if (show != _showTop) setState(() => _showTop = show);
    if (_scroll.position.extentAfter < 400) _load();
  }

  Future<void> _load() async {
    if (_loading || _done) return;
    _loading = true;
    try {
      final handle = await ref.read(bootProvider.future);
      if (!_kLoaded && _cursor == null) {
        // 落盘的篇幅偏好（discover_k pref）：首屏解析一次，重启保持。
        _kLoaded = true;
        try {
          final s = await handle.api.settings();
          _k = double.tryParse(s.discoverK) ?? 0;
        } catch (_) {}
      }
      final page = await handle.api.recommend(cursor: _cursor, k: _k);
      setState(() {
        _items.addAll(page.items);
        _cursor = page.nextCursor;
        _done = !page.hasMore;
      });
    } catch (_) {
      // 静默：下一屏再试
    } finally {
      _loading = false;
    }
  }

  // 篇幅偏好切档（报告 24 §2.5，clx）：重置流并按新 k 重载；落盘保持。
  void _setK(double k) {
    if (k == _k) return;
    setState(() {
      _k = k;
      _kLoaded = true;
      _items.clear();
      _cursor = null;
      _done = false;
    });
    _persistK(k);
    _load();
  }

  // K 档位落盘（user.db prefs discover_k）：切换即写，重启保持。
  Future<void> _persistK(double k) async {
    try {
      final handle = await ref.read(bootProvider.future);
      await handle.api.setDiscoverK(k == 0 ? '0' : '$k');
    } catch (_) {}
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
      appBar: AppBar(title: Text('发现')),
      body: Column(
        children: [
          Padding(
            padding: const EdgeInsets.only(left: 16),
            child: Text('你可能错过的书 · 上滑不断翻',
                style: TextStyle(
                    fontSize: 11, color: scheme.onSurfaceVariant)),
          ),
          // 篇幅偏好（app/docs/18-runtime-metrics.md §5）：clx 运行时
          // 重排，文案不叫「排名」；三档预设 K=0/0.25/0.60，会话内记忆。
          Padding(
            padding: const EdgeInsets.fromLTRB(16, 6, 16, 0),
            child: Wrap(
              spacing: 8,
              crossAxisAlignment: WrapCrossAlignment.center,
              children: [
                Text('篇幅偏好',
                    style: TextStyle(
                        fontSize: 11, color: scheme.onSurfaceVariant)),
                for (final (k, label) in const [
                  (0.0, '不加权'),
                  (0.25, '偏厚'),
                  (0.60, '厚书优先'),
                ])
                  ChoiceChip(
                    label: Text(label, style: const TextStyle(fontSize: 11)),
                    selected: _k == k,
                    showCheckmark: false,
                    visualDensity: VisualDensity.compact,
                    onSelected: (_) => _setK(k),
                  ),
              ],
            ),
          ),
          Expanded(
            child: Stack(
              children: [
                ListView.builder(
                  controller: _scroll,
                  padding: const EdgeInsets.fromLTRB(16, 12, 16, 60),
                  itemCount: _items.length + (_done ? 0 : 1),
                  itemBuilder: (context, i) {
                    if (i >= _items.length) {
                      return const Padding(
                        padding: EdgeInsets.all(16),
                        child: Center(child: CircularProgressIndicator()),
                      );
                    }
                    return _DiscoverCard(item: _items[i]);
                  },
                ),
                if (_showTop)
                  Positioned(
                    right: 16,
                    bottom: 16,
                    child: Material(
                      color: scheme.surface,
                      borderRadius: BorderRadius.circular(20),
                      elevation: 3,
                      child: InkWell(
                        onTap: () => _scroll.animateTo(0,
                            duration: const Duration(milliseconds: 400),
                            curve: Curves.easeOut),
                        customBorder: const CircleBorder(),
                        child: SizedBox(
                          width: 40,
                          height: 40,
                          child: Icon(Icons.arrow_upward,
                              size: 20, color: scheme.primary),
                        ),
                      ),
                    ),
                  ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class _DiscoverCard extends StatelessWidget {
  final RankItem item;

  const _DiscoverCard({required this.item});

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final coverUrl = item.coverUrl;
    final hasCover = coverUrl != null && coverUrl.isNotEmpty;
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
                width: 64,
                height: 88,
                child: hasCover
                    ? ClipRRect(
                        borderRadius: BorderRadius.circular(6),
                        child: CachedNetworkImage(
                          imageUrl:
                              'https://rs.sfacg.com/web/novel/images/images/beitouNew/${item.nid}.jpg',
                          fit: BoxFit.cover,
                          placeholder: (_, _) =>
                              const ColoredBox(color: Color(0x59B8AE9E)),
                          errorWidget: (_, _, _) =>
                              defaultCover(item.nid, title: item.title, radius: 10),
                        ),
                      )
                    : defaultCover(item.nid, title: item.title, radius: 10),
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
                    // E.30：分位列退役，徽标只显收藏（端上可刷新累计值）。
                    _badge(context, '收藏 ${_wan(item.favs)}',
                        fg: scheme.primary,
                        icon: MetricIcons.favs),
                    if (item.cqsState == 'low') ...[
                      const SizedBox(height: 3),
                      _badge(context, '低置信',
                          fg: scheme.onSurfaceVariant),
                    ],
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

Widget _badge(BuildContext context, String text, {Color? fg, IconData? icon}) {
  final scheme = Theme.of(context).colorScheme;
  return Container(
    padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 1),
    decoration: BoxDecoration(
      border: Border.all(color: scheme.outline.withValues(alpha: .5)),
      borderRadius: BorderRadius.circular(999),
    ),
    child: Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        if (icon != null) ...[
          Icon(icon, size: 11, color: fg ?? scheme.onSurfaceVariant),
          const SizedBox(width: 2),
        ],
        Text(text,
            style: TextStyle(fontSize: 10, color: fg ?? scheme.onSurfaceVariant)),
      ],
    ),
  );
}

String _wan(int n) {
  if (n >= 10000) return '${(n / 10000).toStringAsFixed(0)}万';
  return '$n';
}
