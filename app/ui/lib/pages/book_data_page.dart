import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../core/providers.dart';
import '../data/api/strata_api.dart';
import '../widgets/back_to_top.dart';
import '../widgets/metric_badge.dart';
import 'book_data_charts.dart';

/// 单书数据页（Phase 5 作者工作台，docs/07 §5 图表矩阵）：更新热力图
/// （首屏）+ 全勤达标看板 + 当前值仪表盘 + 六指标趋势 + 同期对照空态 +
/// 观测时序。全部端上现算（引擎零新端点）。红线（docs/12）：诚实区分
/// 「暂无更新」与「数据缺口」，不在端上伪造全库时序。
class BookDataPage extends ConsumerStatefulWidget {
  final int nid;

  const BookDataPage({super.key, required this.nid});

  @override
  ConsumerState<BookDataPage> createState() => _BookDataPageState();
}

class _BookDataPageState extends ConsumerState<BookDataPage> {
  late Future<List<Object?>> _data; // [List<ObservationRow>, BookDetail?]
  final ScrollController _scroll = ScrollController();
  bool _showTop = false;
  bool _showAllObs = false;

  @override
  void initState() {
    super.initState();
    // book 可 404（库外书未抓过详情）——吞掉置 null，当前值仪表盘降级
    _data = Future.wait<Object?>([
      ref
          .read(bootProvider.future)
          .then((h) => h.api.observations(widget.nid)),
      ref
          .read(bootProvider.future)
          .then<BookDetail?>((h) => h.api.book(widget.nid))
          .catchError((_) => null),
    ]);
    _scroll.addListener(_onScroll);
  }

  void _onScroll() {
    final show = _scroll.offset > 500;
    if (show != _showTop) setState(() => _showTop = show);
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
      appBar: AppBar(title: const Text('观测数据')),
      floatingActionButton: _showTop
          ? BackToTop(onTap: () => _scroll.animateTo(
                0,
                duration: const Duration(milliseconds: 400),
                curve: Curves.easeOut))
          : null,
      body: FutureBuilder<List<Object?>>(
        future: _data,
        builder: (context, snap) {
          if (snap.connectionState != ConnectionState.done) {
            return const Center(child: CircularProgressIndicator());
          }
          if (snap.hasError) {
            return Center(child: Text('加载失败：${snap.error}'));
          }
          final items = snap.data![0] as List<ObservationRow>;
          final book = snap.data![1] as BookDetail?;
          if (items.length < 2) {
            return _GapState(count: items.length);
          }
          final cells = buildDayCells(items);
          final hasWords = items.any((o) => o.words != null);
          final newest = items.first;
          final previous = items[1];
          final changed = (newest.words != previous.words) ||
              (newest.favs != previous.favs) ||
              (newest.praises != previous.praises) ||
              (newest.clicks != previous.clicks);
          final first = items.last;
          final spanDays =
              ((newest.observedAt - first.observedAt) / 86400).floor();
          return ListView(
            controller: _scroll,
            padding: const EdgeInsets.all(16),
            children: [
              // 1. 更新热力图（首屏）+ 全勤达标看板——需字数观测
              if (hasWords) ...[
                UpdateHeatmap(cells: cells),
                const SizedBox(height: 14),
                AttendanceBoard(cells: cells, status: newest.status),
                const SizedBox(height: 14),
              ],
              // 2. 当前值仪表盘（book 端点可达时）
              if (book != null) ...[
                CurrentValuesGrid(detail: book, latest: newest),
                const SizedBox(height: 14),
              ],
              // 3. 六指标趋势折线
              MetricTrend(items: items),
              const SizedBox(height: 14),
              // 4. 同期对照（role=peer 对照折线，docs/07 §5）
              PeerCompare(
                nid: widget.nid,
                anchorTitle:
                    (book?.book['title'] as String?) ?? 'nid ${widget.nid}',
                anchorEstYear:
                    (book?.book['est_year'] as num?)?.toInt() ?? 0,
                items: items,
              ),
              const SizedBox(height: 14),
              // 5. 观测时序
              Row(
                children: [
                  Text('观测时序（新 → 旧）',
                      style: TextStyle(
                          fontSize: 12,
                          fontWeight: FontWeight.w700,
                          color: scheme.onSurfaceVariant)),
                  const Spacer(),
                  Text('${changed ? '检测到更新' : '暂无更新'} · ${items.length} 次 / $spanDays 天',
                      style: TextStyle(
                          fontSize: 11,
                          color: changed
                              ? scheme.primary
                              : scheme.onSurfaceVariant)),
                ],
              ),
              const SizedBox(height: 8),
              // 默认只给最近 7 条——52 条全展开约 12 屏，把图表区埋掉；
              // 需要原始序列时手动展开
              for (final o in (_showAllObs ? items : items.take(7)))
                _ObsRow(o: o),
              if (items.length > 7) ...[
                const SizedBox(height: 2),
                Center(
                  child: TextButton(
                    onPressed: () =>
                        setState(() => _showAllObs = !_showAllObs),
                    child:
                        Text(_showAllObs ? '收起' : '展开全部 ${items.length} 条'),
                  ),
                ),
              ],
            ],
          );
        },
      ),
    );
  }
}

class _GapState extends StatelessWidget {
  final int count;

  const _GapState({required this.count});

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return Center(
      child: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          Icon(Icons.timeline,
              size: 56, color: scheme.onSurfaceVariant.withValues(alpha: .5)),
          const SizedBox(height: 12),
          Text('数据缺口',
              style: TextStyle(
                  fontFamily: 'serif',
                  fontSize: 17,
                  fontWeight: FontWeight.w700)),
          const SizedBox(height: 6),
          Text(
              count == 0
                  ? '还没有观测记录。详情页刷新成功后会自动累积观测点。'
                  : '只有 1 次观测，时序尚未形成。等待下次刷新后再看。',
              textAlign: TextAlign.center,
              style: TextStyle(fontSize: 12, color: scheme.onSurfaceVariant)),
        ],
      ),
    );
  }
}

class _ObsRow extends StatelessWidget {
  final ObservationRow o;

  const _ObsRow({required this.o});

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final t = DateTime.fromMillisecondsSinceEpoch(o.observedAt * 1000);

    return Container(
      margin: const EdgeInsets.only(bottom: 8),
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        border: Border.all(color: scheme.outline.withValues(alpha: .4)),
        borderRadius: BorderRadius.circular(12),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              Text('${t.month}/${t.day} ${t.hour}:${t.minute.toString().padLeft(2, '0')}',
                  style: TextStyle(
                      fontSize: 12, fontWeight: FontWeight.w700)),
              if (o.source != null && o.source != 'detail')
                Text(o.source == 'simulate' ? '模拟' : (o.source ?? ''),
                    style: TextStyle(
                        fontSize: 10,
                        color: scheme.onSurfaceVariant.withValues(alpha: .7))),
            ],
          ),
          const SizedBox(height: 6),
          Wrap(
            spacing: 4,
            runSpacing: 4,
            children: [
              if (o.words != null)
                _chip(context, '字数 ${wan(o.words!)}',
                    fg: scheme.primary, icon: MetricIcons.words),
              if (o.clicks != null)
                _chip(context, '点击 ${wan(o.clicks!)}'),
              if (o.favs != null)
                _chip(context, '收藏 ${wan(o.favs!)}', icon: MetricIcons.favs),
              if (o.praises != null)
                _chip(context, '点赞 ${wan(o.praises!)}',
                    icon: MetricIcons.praises),
              if (o.shortComments != null)
                _chip(context, '短评 ${o.shortComments}'),
              if (o.longComments != null)
                _chip(context, '长评 ${o.longComments}'),
            ],
          ),
          if (o.updatedAt != null)
            Padding(
              padding: const EdgeInsets.only(top: 4),
              child: Text('最新章节更新于 ${o.updatedAt}',
                  style: TextStyle(
                      fontSize: 10, color: scheme.onSurfaceVariant)),
            ),
        ],
      ),
    );
  }

  Widget _chip(BuildContext context, String text, {Color? fg, IconData? icon}) {
    final scheme = Theme.of(context).colorScheme;
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
      decoration: BoxDecoration(
          color: scheme.surface,
          border: Border.all(color: scheme.outline.withValues(alpha: .4)),
          borderRadius: BorderRadius.circular(999)),
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
}
