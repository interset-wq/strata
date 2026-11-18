import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../core/providers.dart';
import '../data/api/strata_api.dart';

/// 单书数据页（Phase 5 作者工作台）：本机观测时序 + 更新历史。
/// 红线（docs/12）：诚实区分「暂无更新」与「数据缺口」，
/// 不在端上伪造全库时序——只展示本机已有的观测点。
class BookDataPage extends ConsumerStatefulWidget {
  final int nid;

  const BookDataPage({super.key, required this.nid});

  @override
  ConsumerState<BookDataPage> createState() => _BookDataPageState();
}

class _BookDataPageState extends ConsumerState<BookDataPage> {
  late Future<List<ObservationRow>> _obs;

  @override
  void initState() {
    super.initState();
    _load();
  }

  void _load() {
    _obs =
        ref.read(bootProvider.future).then((h) => h.api.observations(widget.nid));
  }

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return Scaffold(
      appBar: AppBar(title: const Text('观测数据')),
      body: FutureBuilder<List<ObservationRow>>(
        future: _obs,
        builder: (context, snap) {
          if (snap.connectionState != ConnectionState.done) {
            return const Center(child: CircularProgressIndicator());
          }
          if (snap.hasError) {
            return Center(child: Text('加载失败：${snap.error}'));
          }
          final items = snap.data ?? [];
          if (items.length < 2) {
            return _GapState(count: items.length);
          }
          // 区分「暂无更新」与「有变化」：对比最近两条观测的累计值
          final newest = items.first;
          final previous = items[1];
          final changed = (newest.favs != previous.favs) ||
              (newest.praises != previous.praises) ||
              (newest.words != previous.words);
          final first = items.last;
          final spanDays =
              ((newest.observedAt - first.observedAt) / 86400).floor();
          return ListView(
            padding: const EdgeInsets.all(16),
            children: [
              // 摘要卡：诚实结论
              Container(
                padding: const EdgeInsets.all(14),
                decoration: BoxDecoration(
                  color: scheme.primary.withValues(alpha: .08),
                  borderRadius: BorderRadius.circular(16),
                ),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      changed ? '检测到更新' : '暂无更新',
                      style: TextStyle(
                          fontFamily: 'serif',
                          fontSize: 15,
                          fontWeight: FontWeight.w700,
                          color: scheme.primary),
                    ),
                    const SizedBox(height: 4),
                    Text(
                      '本机已观测 ${items.length} 次，跨度 $spanDays 天。'
                      '${changed
                          ? '与上一次观测相比指标有变化。'
                          : '两次观测之间各项累计值没有变化——是暂时没有新数据，不是数据缺口。'}',
                      style: TextStyle(
                          fontSize: 11.5, color: scheme.onSurfaceVariant),
                    ),
                  ],
                ),
              ),
              const SizedBox(height: 14),
              // 观测折线：观测点 ≥3 才启用（docs/12 红线——不足不硬画）
              if (items.length >= 3)
                _TrendChart(
                  points: (items.reversed.toList())
                      .where((o) => o.favs != null)
                      .map((o) => o.favs!.toDouble())
                      .toList(),
                ),
              if (items.length >= 3) const SizedBox(height: 14),
              Text('观测时序（新 → 旧）',
                  style: TextStyle(
                      fontSize: 12, color: scheme.onSurfaceVariant)),
              const SizedBox(height: 8),
              for (final o in items) _ObsRow(o: o),
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
            ],
          ),
          const SizedBox(height: 6),
          Wrap(
            spacing: 4,
            runSpacing: 4,
            children: [
              if (o.favs != null) _chip(context, '收藏 ${_wan(o.favs!)}'),
              if (o.praises != null) _chip(context, '推荐 ${_wan(o.praises!)}'),
              if (o.words != null)
                _chip(context, '字数 ${_wan(o.words!)}',
                    fg: scheme.primary),
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

  Widget _chip(BuildContext context, String text, {Color? fg}) {
    final scheme = Theme.of(context).colorScheme;
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
      decoration: BoxDecoration(
          color: scheme.surface,
          border: Border.all(color: scheme.outline.withValues(alpha: .4)),
          borderRadius: BorderRadius.circular(999)),
      child: Text(text, style: TextStyle(fontSize: 10, color: fg ?? scheme.onSurfaceVariant)),
    );
  }
}

/// 观测折线（favs 时序）：朱砂细线 + 端点数值。观测点 ≥3 才画。
class _TrendChart extends StatelessWidget {
  final List<double> points;

  const _TrendChart({required this.points});

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final isRising = points.last >= points.first;
    final color = isRising ? scheme.primary : scheme.tertiary;
    final minV = points.reduce((a, b) => a < b ? a : b);
    final maxV = points.reduce((a, b) => a > b ? a : b);
    final span = (maxV - minV).abs().clamp(1.0, double.infinity);
    return Container(
      padding: const EdgeInsets.all(14),
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
              Text('收藏时序',
                  style: TextStyle(
                      fontSize: 11, color: scheme.onSurfaceVariant)),
              Text('${_wan(points.first.toInt())} → ${_wan(points.last.toInt())}',
                  style: TextStyle(
                      fontSize: 11,
                      fontWeight: FontWeight.w700,
                      color: color)),
            ],
          ),
          const SizedBox(height: 8),
          SizedBox(
            height: 72,
            width: double.infinity,
            child: CustomPaint(
              painter: _SparklinePainter(
                  points: points, minV: minV, span: span, color: color),
            ),
          ),
        ],
      ),
    );
  }
}

class _SparklinePainter extends CustomPainter {
  final List<double> points;
  final double minV;
  final double span;
  final Color color;

  _SparklinePainter({
    required this.points,
    required this.minV,
    required this.span,
    required this.color,
  });

  @override
  void paint(Canvas canvas, Size size) {
    if (points.length < 2) return;
    final step = size.width / (points.length - 1);
    final path = Path();
    for (var i = 0; i < points.length; i++) {
      final x = i * step;
      final y = size.height - (points[i] - minV) / span * size.height;
      if (i == 0) {
        path.moveTo(x, y);
      } else {
        path.lineTo(x, y);
      }
    }
    canvas.drawPath(
        path,
        Paint()
          ..color = color
          ..style = PaintingStyle.stroke
          ..strokeWidth = 1.6
          ..strokeJoin = StrokeJoin.round);
    // 端点小圆
    canvas.drawCircle(
        Offset(size.width, size.height - (points.last - minV) / span * size.height),
        2.5,
        Paint()..color = color);
  }

  @override
  bool shouldRepaint(covariant _SparklinePainter old) =>
      old.points.length != points.length;
}

String _wan(int n) {
  if (n >= 10000) return '${(n / 10000).toStringAsFixed(1)}万';
  return '$n';
}
