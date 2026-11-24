import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:go_router/go_router.dart';
import 'package:url_launcher/url_launcher.dart';

import '../widgets/default_cover.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../core/providers.dart';
import '../data/api/strata_api.dart';
import '../widgets/metric_badge.dart';

/// 官方热销信号（docs/sfacg-live-ranks.md）：当前在已缓存官方热销榜上的
/// nid 集合。被动信号——引擎从不为它抓取，未缓存/离线时为空集（不显示徽标）。
final _saleSetProvider = FutureProvider.autoDispose<Set<int>>((ref) async {
  final h = await ref.read(bootProvider.future);
  return h.api.officialSaleSet();
});

/// 书籍详情页：种子数据 + 最新观测的 effective 展示，
/// 附三态刷新（docs/05）与观测历史。
class BookDetailPage extends ConsumerStatefulWidget {
  final int nid;
  const BookDetailPage({super.key, required this.nid});

  @override
  ConsumerState<BookDetailPage> createState() => _BookDetailPageState();
}

class _BookDetailPageState extends ConsumerState<BookDetailPage> {
  /// 官方兜底封面：部分作品在 CDN 无封面图（Big/{nid}.jpg 404）
  static const _defaultCover =
      'https://rs.sfacg.com/web/novel/images/NovelCover/Big/default.jpg';

  bool refreshing = false;
  bool _footprintLogged = false;
  // 榜单库外书自动补全（docs/08 §rank-seed）：每次进页至多一次。
  bool _autoCompleted = false;
  // 库外书（官方搜索「新书」）自动收录状态，docs/08 §search-remote。
  bool _collectTried = false;
  bool _collecting = false;
  String? _collectError;
  String? refreshMessage;
  Color? refreshColor;
  // v6 统一 watchlist：onWatch = 在列表里，tracking = 激活（后台抓取）。
  bool onWatch = false;
  bool tracking = false;
  Future<List<ObservationRow>>? observations;

  @override
  void initState() {
    super.initState();
    // 以当前书的 watchlist 状态初始化（v6 统一列表，本地查询）。
    ref.read(bootProvider.future).then((h) async {
      final items = await h.api.watchList();
      for (final it in items) {
        if (it.nid == widget.nid) {
          if (mounted) {
            setState(() {
              onWatch = true;
              tracking = it.active;
            });
          }
          break;
        }
      }
    }).onError((Object _, StackTrace _) {});
  }

  /// 库外书（官方搜索「新书」）自动收录：seed 无此行时自动触发一次
  /// 按需抓取并重载；失败显示明确文案，不无限重试（docs/08 §search-remote）。
  Widget _bookError(BuildContext context, Object e) {
    final scheme = Theme.of(context).colorScheme;
    if (!(e is StrataApiException && e.status == 404)) {
      return Center(child: Text('加载失败：${StrataApiException.userMessage(e)}'));
    }
    if (_collectError != null) {
      return Center(
        child: Text('收录失败：$_collectError',
            style: TextStyle(color: scheme.onSurfaceVariant)),
      );
    }
    if (_collecting) {
      return const Center(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            CircularProgressIndicator(),
            SizedBox(height: 12),
            Text('正在收录这本书…'),
          ],
        ),
      );
    }
    if (_collectTried) {
      // 抓取跑过但 user.db 仍无数据（站上不可读/已下架）。
      return const Center(child: Text('收录未返回数据，该书可能已下架'));
    }
    _collectTried = true;
    _collecting = true;
    WidgetsBinding.instance.addPostFrameCallback((_) => _collect());
    return const Center(child: CircularProgressIndicator());
  }

  Future<void> _collect() async {
    String? err;
    try {
      final h = await ref.read(bootProvider.future);
      final r = await h.api.refresh(widget.nid);
      // rate_limited = 24h 冷却窗（含失败占用）——明确提示，不误报。
      if (r.state == 'rate_limited') {
        err = '已进入刷新冷却（24 小时），稍后再试';
      } else if (r.state != 'alive') {
        err = '该书在站上不可读（${r.state}）';
      }
    } catch (ex) {
      err = StrataApiException.userMessage(ex);
    }
    if (!mounted) return;
    setState(() {
      _collecting = false;
      _collectError = err;
    });
    if (err == null) ref.invalidate(bookProvider(widget.nid));
  }

  /// 官方页面直达（docs/15：Icons.open_in_new = 官方页面）：移动版详情页，
  /// 用系统浏览器打开——App 自身不加载官方页面内容。
  Future<void> _openOfficial() async {
    final url = Uri.parse('https://m.sfacg.com/b/${widget.nid}/');
    var ok = false;
    try {
      ok = await launchUrl(url, mode: LaunchMode.externalApplication);
    } catch (_) {}
    if (!mounted || ok) return;
    ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('无法打开浏览器')));
  }

  /// 复制反馈（标题 / 书籍 ID）。
  void _copied(String what) {
    if (!mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('$what已复制'),
            duration: const Duration(seconds: 1)));
  }

  @override
  Widget build(BuildContext context) {
    final detail = ref.watch(bookProvider(widget.nid));
    return Scaffold(
      appBar: AppBar(
        // 设计稿 03：‹ 返回 + 居中"书籍详情" + 收藏心形
        title: const Text('书籍详情'),
        centerTitle: true,
        actions: [
          IconButton(
            // 官方页面直达（docs/15）：系统浏览器打开移动版详情页。
            icon: const Icon(Icons.open_in_new),
            tooltip: '打开官方页面',
            onPressed: _openOfficial,
          ),
          IconButton(
            icon: Icon(tracking ? Icons.visibility : Icons.visibility_outlined),
            tooltip: !onWatch
                ? '加入追踪'
                : (tracking ? '停止追踪' : '追踪更新'),
            onPressed: _toggleTracking,
          ),
          IconButton(
            icon:
                Icon(onWatch ? Icons.bookmark : Icons.bookmark_add_outlined),
            tooltip: onWatch ? '取消关注' : '关注此书',
            onPressed: onWatch ? _removeWatch : _addWatch,
          ),
        ],
      ),
      body: detail.when(
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (e, _) => _bookError(context, e),
        data: (d) {
          // 打开即记一次浏览足迹（fire-and-forget，纯本地 user.db）。
          if (!_footprintLogged) {
            _footprintLogged = true;
            ref.read(bootProvider.future).then((h) => h.api.recordHistory(widget.nid),
                onError: (_) {});
          }
          final b = d.book;
          // 榜单库外书自动补全（docs/08 §rank-seed）：rank-seed 预写只
          // 有标题/作者/封面（无字数）——首帧立即渲染，完整数据走后台
          // refresh 静默补全，不再全屏转圈等收录。
          if (!_autoCompleted && b['words'] == null) {
            _autoCompleted = true;
            WidgetsBinding.instance.addPostFrameCallback((_) {
              if (mounted) _refresh(context);
            });
          }
          // effective = 种子值被最新本地观测覆盖后的展示值（契约 08）。
          final eff = (d.effective ?? const {}).cast<String, dynamic>();

          String? s(Object? v) => v?.toString();
          final licensed = b['is_licensed'] == true;
          final scheme = Theme.of(context).colorScheme;
          // 官方热销徽标（被动信号：缓存未命中/离线 → false，静默不显示）。
          final onSale = ref.watch(_saleSetProvider).maybeWhen(
                data: (set) => set.contains(widget.nid),
                orElse: () => false,
              );
          // 种子 cover_url 存相对路径（无前缀，上游爬虫缺前缀为已知问题）：
          // 有值拼 CDN 前缀；空值用官方默认封面兜底（用户拍板 2026-11-17）。
          final raw = s(eff['cover_url'] ?? b['cover_url']);
          final cover = (raw == null || raw.isEmpty)
              ? _defaultCover
              : raw.startsWith('http')
                  ? raw
                  : raw.startsWith('//')
                      ? 'https:$raw'
                      : 'https://rss.sfacg.com/web/novel/images/NovelCover/Big/$raw';
          return ListView(
            padding: const EdgeInsets.all(16),
            children: [
              // 书头：封面（朱砂错位投影）+ 标题/作者/徽章（设计稿 03）
              Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Container(
                    decoration: BoxDecoration(
                      borderRadius: BorderRadius.circular(8),
                      boxShadow: [
                        BoxShadow(
                          color: scheme.primary.withValues(alpha: .25),
                          offset: const Offset(5, 5),
                        ),
                      ],
                    ),
                    child: ClipRRect(
                      borderRadius: BorderRadius.circular(8),
                      child: SizedBox(
                        width: 92,
                        height: 128,
                        child: coverImage(cover, widget.nid),
                      ),
                    ),
                  ),
                  const SizedBox(width: 16),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        // 标题快速复制：长按（用户 2026-11-21 要求）。
                        Tooltip(
                          message: '长按复制标题',
                          child: GestureDetector(
                            onLongPress: () {
                              final t = s(eff['title'] ?? b['title']) ?? '';
                              Clipboard.setData(ClipboardData(text: t));
                              _copied('标题');
                            },
                            child: Text(
                                s(eff['title'] ?? b['title']) ?? '',
                                style:
                                    Theme.of(context).textTheme.headlineSmall),
                          ),
                        ),
                        const SizedBox(height: 6),
                        InkWell(
                          // 作者入口（docs/author-profile-on-demand）：
                          // 时间轴列表页由作者规划 UI，数据已就绪。
                          onTap: () {
                            final a = s(eff['author'] ?? b['author']);
                            if (a != null && a.isNotEmpty) {
                              context.push(
                                  '/author?author=${Uri.encodeComponent(a)}&nid=${widget.nid}');
                            }
                          },
                          child: Text(s(eff['author'] ?? b['author']) ?? '',
                              style: TextStyle(
                                  fontSize: 12,
                                  color: scheme.onSurfaceVariant,
                                  decoration: TextDecoration.underline,
                                  decorationColor:
                                      scheme.onSurfaceVariant.withValues(alpha: .4))),
                        ),
                        const SizedBox(height: 8),
                        Wrap(
                          spacing: 6,
                          children: [
                            if (s(eff['status'] ?? b['status']) != null)
                              _badge(context,
                                  s(eff['status'] ?? b['status'])!,
                                  filled: true),
                            if (onSale)
                              _badge(context, '官方热销', filled: true),
                            if (s(eff['genre'] ?? b['genre']) != null)
                              _badge(context,
                                  s(eff['genre'] ?? b['genre'])!),
                            if (s(b['est_year']) != null)
                              _badge(context, '${s(b['est_year'])} 代'),
                            // 获奖徽标（schema v5，docs §6）：{edition} · {award|征文获奖}，
                            // edition 原样显示不走映射表，多届并列；永不参与排序/打分。
                            for (final aw in d.awards)
                              _badge(context,
                                  '${aw.edition} · ${aw.displayAward}'),
                          ],
                        ),
                      ],
                    ),
                  ),
                ],
              ),
              const SizedBox(height: 12),
              Wrap(
                spacing: 8,
                children: [
                  for (final tag in d.tags) Chip(label: Text(tag)),
                ],
              ),
              if (s(eff['summary']) != null) ...[
                const SizedBox(height: 12),
                Text('\u4f5c\u54c1\u7b80\u4ecb',
                    style: Theme.of(context).textTheme.titleSmall),
                const SizedBox(height: 4),
                Text(s(eff['summary'])!,
                    style: TextStyle(
                        fontSize: 12, color: scheme.onSurfaceVariant)),
              ],
              const SizedBox(height: 12),
              if (licensed)
                const Padding(
                  padding: EdgeInsets.only(bottom: 12),
                  child: Text(
                    '授权作品（is_licensed=1）：可搜索、可看详情，不参与榜单与统计',
                    style: TextStyle(color: Colors.deepOrange),
                  ),
                ),
              // 六指标格：点击/收藏/点赞/字数（短评/长评来自观测，种子无）
              _metricGrid(context, eff, b),
              _pctlCard(context, b),
              _metaCard(context, d, eff, b),
              const SizedBox(height: 12),
              Row(
                children: [
                  FilledButton.icon(
                    onPressed: refreshing ? null : () => _refresh(context),
                    icon: refreshing
                        ? const SizedBox(
                            width: 16,
                            height: 16,
                            child: CircularProgressIndicator(strokeWidth: 2))
                        : const Icon(Icons.refresh),
                    label: const Text('刷新观测'),
                  ),
                  const SizedBox(width: 12),
                  onWatch
                      ? OutlinedButton.icon(
                          onPressed: _removeWatch,
                          icon: const Icon(Icons.bookmark),
                          label: const Text('已关注'),
                        )
                      : OutlinedButton.icon(
                          onPressed: _addWatch,
                          icon: const Icon(Icons.bookmark_add_outlined),
                          label: const Text('关注此书'),
                        ),
                ],
              ),
              if (refreshMessage != null) ...[
                const SizedBox(height: 8),
                Text(refreshMessage!,
                    style: TextStyle(color: refreshColor)),
              ],
              const Divider(height: 32),
              Row(
                children: [
                  Expanded(
                    child: Text('观测历史',
                        style: Theme.of(context).textTheme.titleMedium),
                  ),
                  TextButton.icon(
                    onPressed: () =>
                        context.push('/book/${widget.nid}/data'),
                    icon: const Icon(Icons.timeline, size: 18),
                    label: const Text('图表'),
                  ),
                ],
              ),
              const SizedBox(height: 8),
              _observationsList(),
            ],
          );
        },
      ),
    );
  }

  Future<void> _refresh(BuildContext context) async {
    setState(() => refreshing = true);
    try {
      final handle = await ref.read(bootProvider.future);
      final r = await handle.api.refresh(widget.nid);
      final rd = r.detail ?? const <String, dynamic>{};
      setState(() {
        switch (r.state) {
          case 'alive':
            refreshMessage = '观测已写入（favs=${rd['favs'] ?? rd['markCount']}）';
            refreshColor = Colors.green;
          case 'dead':
            refreshMessage = '官方页面不存在（未写观测）';
            refreshColor = Colors.deepOrange;
          case 'zombie':
            refreshMessage = '该书当前不可阅读（未写观测）';
            refreshColor = Colors.deepOrange;
          case 'rate_limited':
            final retry = rd['retry_after_seconds'] as int? ?? 0;
            final hours = (retry / 3600).ceil();
            refreshMessage =
                '24 小时内已刷新过（约 $hours 小时后可再试，设置中可关闭限流）';
            refreshColor = Colors.deepOrange;
          default:
            refreshMessage = '未知状态：${r.state}';
            refreshColor = Colors.red;
        }
      });
      ref.invalidate(bookProvider(widget.nid));
      setState(() {
        observations = handle.api.observations(widget.nid);
      });
    } catch (e) {
      setState(() {
        refreshMessage = '刷新失败：$e';
        refreshColor = Colors.red;
      });
    } finally {
      setState(() => refreshing = false);
    }
  }

  /// 加入 watchlist（v6：只存，原「收藏/加入书架」）。
  Future<void> _addWatch() async {
    final handle = await ref.read(bootProvider.future);
    await handle.api.watchAdd(widget.nid);
    setState(() => onWatch = true);
  }

  Future<void> _removeWatch() async {
    final handle = await ref.read(bootProvider.future);
    await handle.api.watchRemove(widget.nid);
    setState(() {
      onWatch = false;
      tracking = false;
    });
  }

  /// 追踪切换（v6）：不在列表 = 加入并激活；在列表 = 翻转 poll_enabled。
  Future<void> _toggleTracking() async {
    final handle = await ref.read(bootProvider.future);
    final next = !tracking;
    if (onWatch) {
      await handle.api.watchSetActive(widget.nid, next);
    } else {
      await handle.api.watchAdd(widget.nid, active: true);
    }
    setState(() {
      onWatch = true;
      tracking = next;
    });
  }

  Widget _observationsList() {
    observations ??=
        ref.read(bootProvider.future).then((h) => h.api.observations(widget.nid));
    return FutureBuilder<List<ObservationRow>>(
      future: observations,
      builder: (context, snap) {
        if (snap.connectionState != ConnectionState.done) {
          return const Center(child: CircularProgressIndicator());
        }
        if (snap.hasError) {
          return Text('观测加载失败：${snap.error}');
        }
        final items = snap.data ?? [];
        if (items.isEmpty) {
          return const Text('暂无本地观测，点上方「刷新观测」开始累积',
              style: TextStyle(color: Colors.grey));
        }
        return Column(
          children: [
            for (final o in items)
              ListTile(
                dense: true,
                title: Text(
                    '${DateTime.fromMillisecondsSinceEpoch(o.observedAt * 1000)}'
                    .replaceAll('.000', '')),
                subtitle: Row(
                  children: [
                    MetricBadge(icon: MetricIcons.favs, text: '收藏 ${o.favs ?? '-'}'),
                    const SizedBox(width: 10),
                    MetricBadge(icon: MetricIcons.praises, text: '赞 ${o.praises ?? '-'}'),
                    const SizedBox(width: 10),
                    MetricBadge(icon: MetricIcons.words, text: '字数 ${o.words ?? '-'}'),
                  ],
                ),
              ),
          ],
        );
      },
    );
  }

  String? _num(Object? v) {
    if (v == null) return null;
    final s = v.toString();
    if (s.isEmpty || s == 'null') return null;
    final n = int.tryParse(s);
    if (n == null) return s;
    // 大数字缩写：≥1亿用亿、≥1万用万，避免溢出换行
    final abs = n.abs();
    if (abs >= 100000000) {
      return '${(n / 100000000).toStringAsFixed(2)}亿';
    }
    if (abs >= 10000) {
      return '${(n / 10000).toStringAsFixed(1)}万';
    }
    return n.toString();
  }

  /// 设计稿徽章：filled=朱砂底，否则描边。
  Widget _badge(BuildContext context, String text, {bool filled = false}) {
    final scheme = Theme.of(context).colorScheme;
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 9, vertical: 3),
      decoration: BoxDecoration(
        color: filled ? scheme.primary.withValues(alpha: .12) : null,
        border: filled ? null : Border.all(color: scheme.outline),
        borderRadius: BorderRadius.circular(999),
      ),
      child: Text(
        text,
        style: TextStyle(
          fontSize: 10,
          color: filled ? scheme.primary : scheme.onSurfaceVariant,
        ),
      ),
    );
  }

  /// 六指标格（设计稿：尽可能多展示数据；短评/长评由观测通路提供，待接入）。
  Widget _metricGrid(BuildContext context, Map<String, dynamic> eff,
      Map<String, dynamic> b) {
    String v(String key) => _num(eff[key] ?? b[key]) ?? '—';
    final scheme = Theme.of(context).colorScheme;
    final labels = [('点击', 'clicks'), ('收藏', 'favs'), ('点赞', 'praises'), ('字数', 'words')];
    return Row(
      children: [
        for (final (label, key) in labels)
          Expanded(
            child: Card(
              margin: const EdgeInsets.symmetric(horizontal: 4),
              child: Padding(
                padding: const EdgeInsets.symmetric(vertical: 10),
                child: Column(
                  children: [
                    Text(label,
                        style: TextStyle(
                            fontSize: 10, color: scheme.onSurfaceVariant)),
                    const SizedBox(height: 3),
                    Text(v(key),
                        style: Theme.of(context)
                            .textTheme
                            .titleLarge
                            ?.copyWith(fontSize: 15)),
                  ],
                ),
              ),
            ),
          ),
      ],
    );
  }

  /// PR 指标卡（E.30：同代分位列已退役；PR = 赞/藏，端上可重算的比值
  /// 信号）。favs < 10 时 PR 为 NULL，整卡隐藏。
  Widget _pctlCard(BuildContext context, Map<String, dynamic> b) {
    final scheme = Theme.of(context).colorScheme;
    final pr = double.tryParse(b['pr']?.toString() ?? '');
    if (pr == null) return const SizedBox.shrink();
    return Card(
      margin: const EdgeInsets.only(top: 12),
      child: Padding(
        padding: const EdgeInsets.all(14),
        child: Row(
          mainAxisAlignment: MainAxisAlignment.spaceBetween,
          children: [
            Text('PR（赞/藏）',
                style:
                    TextStyle(fontSize: 12, color: scheme.onSurfaceVariant)),
            Text(pr.toStringAsFixed(3),
                style: TextStyle(
                    fontSize: 11,
                    fontWeight: FontWeight.w700,
                    color: scheme.secondary)),
          ],
        ),
      ),
    );
  }

  /// 完整元数据卡（数据全展示原则）。
  Widget _metaCard(BuildContext context, BookDetail d, Map<String, dynamic> eff,
      Map<String, dynamic> b) {
    String? s(Object? v) => v?.toString();
    Widget row(String label, String? value) {
      if (value == null || value.isEmpty || value == 'null') {
        return const SizedBox.shrink();
      }
      return Padding(
        padding: const EdgeInsets.symmetric(vertical: 3),
        child: Row(
          mainAxisAlignment: MainAxisAlignment.spaceBetween,
          children: [
            Text(label,
                style: TextStyle(
                    fontSize: 12,
                    color: Theme.of(context).colorScheme.onSurfaceVariant)),
            Flexible(
              child: Text(value,
                  textAlign: TextAlign.right,
                  style: const TextStyle(fontSize: 12)),
            ),
          ],
        ),
      );
    }

    return Card(
      margin: const EdgeInsets.only(top: 12),
      child: Padding(
        padding: const EdgeInsets.all(14),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text('元数据',
                style: TextStyle(
                    fontSize: 12,
                    color: Theme.of(context).colorScheme.onSurfaceVariant)),
            const SizedBox(height: 6),
            InkWell(
              // 书籍 ID（可复制，用户 2026-11-21 要求）：复制 nid 便于跨端检索。
              onTap: () {
                Clipboard.setData(ClipboardData(text: '${widget.nid}'));
                _copied('书籍 ID');
              },
              child: Padding(
                padding: const EdgeInsets.symmetric(vertical: 3),
                child: Row(
                  mainAxisAlignment: MainAxisAlignment.spaceBetween,
                  children: [
                    Text('书籍 ID',
                        style: TextStyle(
                            fontSize: 12,
                            color: Theme.of(context)
                                .colorScheme
                                .onSurfaceVariant)),
                    Row(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        Text('${widget.nid}',
                            style: const TextStyle(fontSize: 12)),
                        const SizedBox(width: 4),
                        Icon(Icons.copy_rounded,
                            size: 12,
                            color: Theme.of(context)
                                .colorScheme
                                .onSurfaceVariant),
                      ],
                    ),
                  ],
                ),
              ),
            ),
            row('状态', eff['status']?.toString() ?? s(b['status'])),
            row('上架日期', s(b['est_date'])),
            row('收录置信度', s(b['est_conf'])),
            row('价格类型', s(eff['price_type'] ?? b['price_type'])),
            row('比赛', s(b['contest'])),
            row('featured', b['featured'] == true ? '是（编辑精选）' : null),
            row('官方更新时间', s(eff['updated_at'] ?? b['updated_at'])),
            row('官方上架时间', s(eff['add_time'])),
            row('官方评分', s(eff['point'])),
            row('同人', eff['category_id'] == 1 ? '是' : null),
            row('敏感标记', eff['is_sensitive'] == true ? '是' : null),
            row('数据来源', d.source == 'local' ? '本地观测' : '种子'),
            row('数据截止', d.dataEnd),
          ],
        ),
      ),
    );
  }
}
