import 'package:flutter/gestures.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:go_router/go_router.dart';
import 'package:url_launcher/url_launcher.dart';

import '../widgets/back_to_top.dart';
import '../widgets/default_cover.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../core/providers.dart';
import '../data/api/strata_api.dart';

/// 官方热销信号（docs/sfacg-live-ranks.md）：当前在已缓存官方热销榜上的
/// nid 集合。被动信号——引擎从不为它抓取，未缓存/离线时为空集（不显示徽标）。
final _saleSetProvider = FutureProvider.autoDispose<Set<int>>((ref) async {
  final h = await ref.read(bootProvider.future);
  return h.api.officialSaleSet();
});

/// 同作者作品（关联发现横滑）：`/author-books` 是纯 seed 查询（pool=seed，
/// 无上游请求），离线可用。增益区块——加载中/失败/条数不足整行隐藏。
final _authorWorksProvider = FutureProvider.autoDispose
    .family<List<RankItem>, String>((ref, author) async {
      final h = await ref.read(bootProvider.future);
      return h.api.authorBooks(author: author, limit: 12);
    });

/// 相关推荐（docs/related-books.md §4）：`/related` 是纯 seed 分级召回，
/// 离线可用。后端已排除锚点作者，与「其他作品」天然不相交，无需前端去重。
final _relatedWorksProvider = FutureProvider.autoDispose
    .family<List<RankItem>, int>((ref, nid) async {
      final h = await ref.read(bootProvider.future);
      return h.api.relatedBooks(nid: nid);
    });

/// 书籍详情页：种子数据 + 最新观测的 effective 展示，附三态刷新（docs/05）。
/// 观测历史不在此页（AppBar 动作区入口进 `/book/:nid/data` 二级页）。
class BookDetailPage extends ConsumerStatefulWidget {
  final int nid;
  const BookDetailPage({super.key, required this.nid});

  @override
  ConsumerState<BookDetailPage> createState() => _BookDetailPageState();
}

class _BookDetailPageState extends ConsumerState<BookDetailPage> {
  bool refreshing = false;
  bool _footprintLogged = false;
  // 榜单库外书自动补全（docs/08 §rank-seed）：每次进页至多一次。
  bool _autoCompleted = false;
  // 库外书（官方搜索「新书」）自动收录状态，docs/08 §search-remote。
  bool _collectTried = false;
  bool _collecting = false;
  String? _collectError;
  // v6 统一 watchlist：onWatch = 在列表里，tracking = 激活（后台抓取）。
  bool onWatch = false;
  bool tracking = false;

  // 标题区点击复制：title 与 #id 各自可点（用户 2026-11-25）。
  final TapGestureRecognizer _titleTap = TapGestureRecognizer();
  final TapGestureRecognizer _idTap = TapGestureRecognizer();

  // 详情页两屏以上，按 docs/16 长页约定提供回到顶部。
  final ScrollController _scroll = ScrollController();
  bool _showTop = false;

  void _onScroll() {
    final show = _scroll.offset > 500;
    if (show != _showTop) setState(() => _showTop = show);
  }

  @override
  void dispose() {
    _titleTap.dispose();
    _idTap.dispose();
    _scroll.dispose();
    super.dispose();
  }

  @override
  void initState() {
    super.initState();
    _scroll.addListener(_onScroll);
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
        // 设计稿 03：‹ 返回 + 居中"书籍详情"。关注/追踪已移到常驻底部
        // 动作栏（同一动作不在 AppBar 与页内各出现一次）。
        title: const Text('书籍详情'),
        centerTitle: true,
        actions: [
          IconButton(
            // 观测历史已从本页正文收进二级页（用户 2026-11-26）：入口
            // 与其他出口动作同列，不再挤在标题里。
            icon: const Icon(Icons.timeline),
            tooltip: '观测数据',
            onPressed: () => context.push('/book/${widget.nid}/data'),
          ),
          IconButton(
            // 官方页面直达（docs/15）：系统浏览器打开移动版详情页。
            icon: const Icon(Icons.open_in_new),
            tooltip: '打开官方页面',
            onPressed: _openOfficial,
          ),
        ],
      ),
      bottomNavigationBar: _actionBar(),
      floatingActionButton: _showTop
          ? BackToTop(onTap: () => _scroll.animateTo(
                0,
                duration: const Duration(milliseconds: 400),
                curve: Curves.easeOut))
          : null,
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
              if (mounted) _refresh();
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
          // 封面：URL 归一化与本地占位兜底统一交给 coverImage（种子
          // cover_url 存相对路径是上游爬虫已知问题，空值走本地占位）。
          final cover = s(eff['cover_url'] ?? b['cover_url']);
          return ListView(
            controller: _scroll,
            padding: const EdgeInsets.all(16),
            children: [
              // 授权作品提示上移到首屏：它改变这本书的全部统计语义，
              // 不该读到简介以后才看到。
              if (licensed)
                Padding(
                  padding: const EdgeInsets.only(bottom: 12),
                  child: Text(
                    '授权作品：可搜索、可看详情，不参与榜单与统计',
                    // 对比度修正（2026-11-26）：原 Colors.deepOrange #FF5722
                    // 在卡面仅 3.11:1；#C2410F 5.09:1 过 AA。
                    style: const TextStyle(color: Color(0xFFC2410F)),
                  ),
                ),
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
                        // 标题区点击复制（用户 2026-11-25）：点 title 复制
                        // 标题，点 #id 复制 id；#id 小号浅色作次级信息。
                        Text.rich(
                          TextSpan(
                            style: Theme.of(context).textTheme.headlineSmall,
                            children: [
                              TextSpan(
                                text: s(eff['title'] ?? b['title']) ?? '',
                                recognizer: _titleTap..onTap = () {
                                  final t =
                                      s(eff['title'] ?? b['title']) ?? '';
                                  Clipboard.setData(ClipboardData(text: t));
                                  _copied('标题');
                                },
                              ),
                              TextSpan(
                                text: ' #${widget.nid}',
                                style: TextStyle(
                                  fontSize: 13,
                                  color: Theme.of(context)
                                      .colorScheme
                                      .onSurfaceVariant,
                                ),
                                recognizer: _idTap..onTap = () {
                                  Clipboard.setData(
                                      ClipboardData(text: '${widget.nid}'));
                                  _copied('书籍 ID');
                                },
                              ),
                            ],
                          ),
                          maxLines: 3,
                          overflow: TextOverflow.ellipsis,
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
                            // 价格类型与状态同款徽标，紧随其后（用户 2026-11-25）。
                            if (s(eff['price_type'] ?? b['price_type']) != null)
                              _badge(context,
                                  s(eff['price_type'] ?? b['price_type'])!,
                                  filled: true),
                            if (onSale)
                              _badge(context, '官方热销', filled: true),
                            if (s(eff['genre'] ?? b['genre']) != null)
                              _badge(context,
                                  s(eff['genre'] ?? b['genre'])!),
                            if (s(b['est_year']) != null)
                              _badge(context, '${s(b['est_year'])}'),
                          ],
                        ),
                      ],
                    ),
                  ),
                ],
              ),
              if (d.tags.isNotEmpty) ...[
                const SizedBox(height: 12),
                Wrap(
                  spacing: 8,
                  children: [
                    for (final tag in d.tags) Chip(label: Text(tag)),
                  ],
                ),
              ],
              if (s(eff['summary']) != null) ...[
                const SizedBox(height: 12),
                Text('作品简介',
                    style: Theme.of(context).textTheme.titleSmall),
                const SizedBox(height: 4),
                Text(
                  s(eff['summary'])!,
                  style: TextStyle(
                      fontSize: 12, color: scheme.onSurfaceVariant),
                ),
              ],
              // 热度：只有平台四计数——自定义派生指标与同代分位一律不展示
              // （用户裁定 2026-11-26）。
              _coreDataCard(context, eff, b),
              _contestCard(context, s(b['contest'])),
              // 数据口径与来源：低频字段，默认折叠，排在发现区块之前
              // （用户 2026-11-26）。
              _provenanceCard(context, d, eff, b),
              _relatedRail(context, s(eff['author'] ?? b['author'])),
              // 相关推荐排在同作者之后：先「这个人还写了什么」，再「这类书还有什么」。
              _similarRail(context),
              const SizedBox(height: 8),
            ],
          );
        },
      ),
    );
  }

  Future<void> _refresh() async {
    setState(() => refreshing = true);
    String msg;
    Color color;
    try {
      final handle = await ref.read(bootProvider.future);
      final r = await handle.api.refresh(widget.nid);
      final rd = r.detail ?? const <String, dynamic>{};
      switch (r.state) {
        case 'alive':
          msg = '观测已写入（favs=${rd['favs'] ?? rd['markCount']}）';
          // 对比度修正（2026-11-26）：SnackBar 为彩色底 + 白字，
          // 原 Colors.green #4CAF50 白字仅 2.78:1 → #2E7D32 5.13:1。
          color = const Color(0xFF2E7D32);
        case 'dead':
          msg = '官方页面不存在（未写观测）';
          // 原 Colors.deepOrange #FF5722 白字 3.16:1 → #C2410F 5.18:1。
          color = const Color(0xFFC2410F);
        case 'zombie':
          msg = '该书当前不可阅读（未写观测）';
          color = const Color(0xFFC2410F);
        case 'rate_limited':
          final retry = rd['retry_after_seconds'] as int? ?? 0;
          final hours = (retry / 3600).ceil();
          msg = '24 小时内已刷新过（约 $hours 小时后可再试，设置中可关闭限流）';
          color = const Color(0xFFC2410F);
        default:
          msg = '未知状态：${r.state}';
          // 原 Colors.red #F44336 白字 3.68:1 → #B3261E 6.54:1。
          color = const Color(0xFFB3261E);
      }
      ref.invalidate(bookProvider(widget.nid));
    } catch (e) {
      msg = '刷新失败：$e';
      color = const Color(0xFFB3261E);
    } finally {
      if (mounted) setState(() => refreshing = false);
    }
    // 反馈走 SnackBar（docs/16 待办）：底部动作栏常驻后，页内文字提示
    // 会随内容滚走。
    if (!mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(SnackBar(
      content: Text(msg),
      backgroundColor: color,
      duration: const Duration(seconds: 3),
    ));
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

  /// 核心数据卡（2026-11-26 重设计：六指标格 + PR 卡 + 元数据卡的数字
  /// 部分三卡合一）：主行 = 平台累计指标（点击/收藏/点赞/字数）。
  /// 自定义派生指标（PR/CQS/CPS/长度归一）不展示——用户看不懂
  /// （用户裁定 2026-11-26）。
  Widget _coreDataCard(BuildContext context, Map<String, dynamic> eff,
      Map<String, dynamic> b) {
    String v(String key) => _num(eff[key] ?? b[key]) ?? '—';
    final scheme = Theme.of(context).colorScheme;
    return Card(
      margin: const EdgeInsets.only(top: 12),
      child: Padding(
        padding: const EdgeInsets.symmetric(vertical: 10, horizontal: 8),
        child: Row(
          children: [
            for (final (label, key) in const [
              ('点击', 'clicks'),
              ('收藏', 'favs'),
              ('点赞', 'praises'),
              ('字数', 'words'),
            ])
              Expanded(
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
          ],
        ),
      ),
    );
  }

  /// 上游时间戳是 ISO（`2024-07-04T20:33:36`）：更新留到分钟，建档只到日期。
  static String? _fmtTs(String? iso, {bool withTime = false}) {
    if (iso == null || iso.length < 10) return iso;
    final date = iso.substring(0, 10);
    if (withTime && iso.length >= 16) return '$date ${iso.substring(11, 16)}';
    return date;
  }

  /// 赛事卡：一行一届次（`books.contest`，引擎已归一为届名），点击进该届
  /// 档案页。不写「参赛」二字（这行存在即已参赛），也不加区块标题（一张卡
  /// 只装一件事，标题是噪音）；获奖一律不显示：`contest_awards` 911 行里
  /// 867 行是占位值「待逐档标定」，真获奖名全库只有 42 本，说不出信息量
  /// （用户裁定 2026-11-26）。
  Widget _contestCard(BuildContext context, String? contest) {
    if (contest == null || contest.isEmpty) return const SizedBox.shrink();
    return Card(
      margin: const EdgeInsets.only(top: 12),
      child: Padding(
        padding: const EdgeInsets.symmetric(vertical: 2),
        child: _contestRow(context, contest),
      ),
    );
  }

  Widget _contestRow(BuildContext context, String edition) {
    final scheme = Theme.of(context).colorScheme;
    return ListTile(
      dense: true,
      contentPadding: const EdgeInsets.symmetric(horizontal: 14, vertical: 2),
      // 朱砂实心旗：金色 token（#A8834F）描线旗在纸面上只有 ~3:1 对比，
      // 18px 下肉眼看就是灰的（真机截图 2026-11-26），换主色 + 实心才立得住。
      leading: Icon(Icons.flag, size: 20, color: scheme.primary),
      title: Text(edition, style: const TextStyle(fontSize: 13)),
      trailing:
          Icon(Icons.chevron_right, size: 18, color: scheme.onSurfaceVariant),
      // 旧版跳分类 tab（tab 猜测器还把 X征 猜成「其他」）：这行说的是
      // 某一届，就该落在那一届的档案页上。
      onTap: () => context.push('/contests/${Uri.encodeComponent(edition)}'),
    );
  }

  /// 关联发现（其他作品横滑）：详情页此前除作者名外没有出口。
  /// 增益区块——加载中 / 失败 / 不足两本就整行隐藏，绝不阻塞主内容。
  Widget _relatedRail(BuildContext context, String? author) {
    if (author == null || author.isEmpty) return const SizedBox.shrink();
    return ref.watch(_authorWorksProvider(author)).maybeWhen(
          data: (items) {
            final others =
                items.where((e) => e.nid != widget.nid).take(8).toList();
            if (others.length < 2) return const SizedBox.shrink();
            // 不带本数、不挂「作者页」按钮（作者页入口在上方作者名，
            // 同一去处不在页内开两个口，用户 2026-11-26）。
            return _coverRail(context, '其他作品', others);
          },
          orElse: () => const SizedBox.shrink(),
        );
  }

  /// 相关推荐（同 form × 同世代 × 强标签重叠的分级召回，docs/related-books.md）：
  /// 与「其他作品」分开成轨——一条讲作者的其它书，一条讲同类作品，
  /// 混排会让人误以为推荐也是同一作者。增益区块，同样不足两本即隐藏。
  /// 形态用横式条卡而非纯封面行：推荐的作者全是陌生人，只给封面+书名
  /// 看不出"推的是谁"，多一行作者·年代才有判断依据（用户 2026-11-26）。
  Widget _similarRail(BuildContext context) {
    return ref.watch(_relatedWorksProvider(widget.nid)).maybeWhen(
          data: (items) {
            if (items.length < 2) return const SizedBox.shrink();
            return _infoRail(context, '相关推荐', items);
          },
          orElse: () => const SizedBox.shrink(),
        );
  }

  /// 封面横滑行（其他作品）：86dp 宽、书名 12px 三行——62dp 时 11px 两行
  /// 装不下多数书名，一屏截成「转生异世界不吸…」（用户 2026-11-26 裁定放大）。
  Widget _coverRail(
      BuildContext context, String title, List<RankItem> items) {
    return Padding(
      padding: const EdgeInsets.only(top: 16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(title, style: Theme.of(context).textTheme.titleSmall),
          const SizedBox(height: 8),
          SizedBox(
            height: 178,
            child: ListView.separated(
              scrollDirection: Axis.horizontal,
              itemCount: items.length,
              separatorBuilder: (_, _) => const SizedBox(width: 10),
              itemBuilder: (_, i) {
                final it = items[i];
                return GestureDetector(
                  onTap: () => context.push('/book/${it.nid}'),
                  child: SizedBox(
                    width: 86,
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        ClipRRect(
                          borderRadius: BorderRadius.circular(6),
                          child: SizedBox(
                            width: 86,
                            height: 121,
                            child: coverImage(it.coverUrl, it.nid),
                          ),
                        ),
                        const SizedBox(height: 4),
                        Text(it.title,
                            maxLines: 3,
                            overflow: TextOverflow.ellipsis,
                            style: const TextStyle(fontSize: 12)),
                      ],
                    ),
                  ),
                );
              },
            ),
          ),
        ],
      ),
    );
  }

  /// 横式条卡轨（相关推荐）：200dp 宽卡 = 56×78 封面 + 书名最多三行 +
  /// 一行作者·年代。封面与文字并排，书名才放得下长标题。
  Widget _infoRail(
      BuildContext context, String title, List<RankItem> items) {
    final scheme = Theme.of(context).colorScheme;
    return Padding(
      padding: const EdgeInsets.only(top: 16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(title, style: Theme.of(context).textTheme.titleSmall),
          const SizedBox(height: 8),
          SizedBox(
            height: 94,
            child: ListView.separated(
              scrollDirection: Axis.horizontal,
              itemCount: items.length,
              separatorBuilder: (_, _) => const SizedBox(width: 10),
              itemBuilder: (_, i) {
                final it = items[i];
                final sub = it.estYear >= 2000
                    ? '${it.author} · ${it.estYear}'
                    : it.author;
                return GestureDetector(
                  onTap: () => context.push('/book/${it.nid}'),
                  child: Container(
                    width: 200,
                    padding: const EdgeInsets.all(8),
                    decoration: BoxDecoration(
                      color: scheme.surface,
                      borderRadius: BorderRadius.circular(8),
                      border: Border.all(color: scheme.outline),
                    ),
                    child: Row(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        ClipRRect(
                          borderRadius: BorderRadius.circular(6),
                          child: SizedBox(
                            width: 56,
                            height: 78,
                            child: coverImage(it.coverUrl, it.nid),
                          ),
                        ),
                        const SizedBox(width: 10),
                        Expanded(
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              Text(it.title,
                                  maxLines: 3,
                                  overflow: TextOverflow.ellipsis,
                                  style: const TextStyle(fontSize: 13)),
                              const SizedBox(height: 4),
                              Text(sub,
                                  maxLines: 1,
                                  overflow: TextOverflow.ellipsis,
                                  style: TextStyle(
                                      fontSize: 11,
                                      color: scheme.onSurfaceVariant)),
                            ],
                          ),
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
    );
  }

  /// 数据口径与来源（原「官方信息」卡）：口径与官方时间戳，默认折叠，
  /// 只在核对时展开；官方评分（point）已废弃不显示。
  Widget _provenanceCard(BuildContext context, BookDetail d,
      Map<String, dynamic> eff, Map<String, dynamic> b) {
    String? s(Object? v) => v?.toString();
    final formRaw = s(b['form']);
    return Card(
      margin: const EdgeInsets.only(top: 12),
      child: Theme(
        data: Theme.of(context)
            .copyWith(dividerColor: Colors.transparent),
        child: ExpansionTile(
          tilePadding: const EdgeInsets.symmetric(horizontal: 14),
          childrenPadding: const EdgeInsets.fromLTRB(14, 0, 14, 10),
          initiallyExpanded: false,
          title: Text('数据口径与来源',
              style: Theme.of(context).textTheme.titleSmall),
          children: [
            _metaRow(context, '数据来源',
                d.source == 'local' ? '本地观测' : '内置'),
            _metaRow(context, '快照', d.dataEnd),
            _metaRow(context, '最后更新',
                _fmtTs(s(eff['updated_at'] ?? b['updated_at']), withTime: true)),
            _metaRow(context, '官方建档', _fmtTs(s(eff['add_time']))),
            _metaRow(context, '形式',
                formRaw == null ? null : (_formLabels[formRaw] ?? formRaw)),
            _metaRow(context, '入库日期（估计）', s(b['est_date'])),
            _metaRow(context, '收录置信度', s(b['est_conf'])),
            _metaRow(context, 'cqs 状态', s(b['cqs_state'])),
            _metaRow(context, '官方分类 ID',
                s(d.meta?['type_id'] ?? eff['type_id'])),
            _metaRow(context, '同人',
                eff['category_id'] == 1 ? '是' : null),
            _metaRow(context, '敏感标记',
                eff['is_sensitive'] == true ? '是' : null),
            _metaRow(context, '允许下载',
                eff['allow_down'] == true ? '是' : null),
            _metaRow(context, '编辑精选',
                b['featured'] == true ? '是' : null),
          ],
        ),
      ),
    );
  }

  /// 标签 + 值一行；值为空整行不渲染（缺失字段不留空槽）。
  Widget _metaRow(BuildContext context, String label, String? value,
      {Widget? tail}) {
    if ((value == null || value.isEmpty || value == 'null') && tail == null) {
      return const SizedBox.shrink();
    }
    final scheme = Theme.of(context).colorScheme;
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 3),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: [
          Text(label, style: TextStyle(fontSize: 12, color: scheme.onSurfaceVariant)),
          Flexible(
            child: Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                if (value != null && value.isNotEmpty && value != 'null')
                  Flexible(
                      child: Text(value,
                          textAlign: TextAlign.right,
                          style: const TextStyle(fontSize: 12))),
                if (tail != null) ...[const SizedBox(width: 6), tail],
              ],
            ),
          ),
        ],
      ),
    );
  }

  /// 形式枚举 → 中文展示名（docs/13）；数据库枚举不直接露出。
  static const _formLabels = {
    'long': '长篇',
    'medium': '中篇',
    'short': '短篇',
    'dialogue': '对话',
    'ip_collab': 'IP 联动',
    'invalid': '无效',
  };

  /// 常驻底部动作栏：关注 / 追踪 / 刷新观测。此前同一动作在 AppBar 图标
  /// 和页内按钮行各出现一次，滚动即沉底；收口后主操作始终一键可达。
  Widget _actionBar() {
    return SafeArea(
      minimum: const EdgeInsets.fromLTRB(12, 6, 12, 10),
      child: Row(
        children: [
          Expanded(
            child: OutlinedButton.icon(
              onPressed: onWatch ? _removeWatch : _addWatch,
              icon: Icon(onWatch ? Icons.bookmark : Icons.bookmark_add_outlined,
                  size: 18),
              label: Text(onWatch ? '已关注' : '关注'),
            ),
          ),
          const SizedBox(width: 8),
          Expanded(
            child: OutlinedButton.icon(
              onPressed: _toggleTracking,
              icon:
                  Icon(tracking ? Icons.visibility : Icons.visibility_outlined,
                      size: 18),
              label: Text(tracking ? '停止追踪' : '追踪'),
            ),
          ),
          const SizedBox(width: 8),
          Expanded(
            child: FilledButton.icon(
              onPressed: refreshing ? null : _refresh,
              icon: refreshing
                  ? const SizedBox(
                      width: 15,
                      height: 15,
                      child: CircularProgressIndicator(strokeWidth: 2))
                  : const Icon(Icons.refresh, size: 18),
              label: const Text('刷新'),
            ),
          ),
        ],
      ),
    );
  }
}
