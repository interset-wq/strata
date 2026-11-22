/// 作者工作台图表矩阵（docs/07 §5）：更新热力图、全勤达标看板、六指标
/// 趋势折线、当前值仪表盘、同期对照空态。全部由观测序列 + book 端点在
/// 端上现算绘制——引擎零新端点。红线（docs/07 §5 / docs/12）：热力图锚
/// 绝对阈值；缺口不染色（空白 ≠ 断更）；估算值标注「非官方判定」；样本
/// 不足显示「观测不足」不画假趋势；所有值标注来源与时点。
library;

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../core/providers.dart';
import '../data/api/strata_api.dart';

/// 全勤线（官方口径 i.sfacg.com/fuli.shtml，2026-11 查证）：日更 ≥3,000
/// 字。docs/07 §2 要求阈值可配置不硬编码（存 prefs）；v1 取 const，
/// prefs 化留待后续。
const int kAttendanceThreshold = 3000;

/// 单日格种类（docs/07 §2 回退归因）：
/// gap = 数据缺口（不染色——空白 ≠ 断更）；baseline = 首个观测日（无前
/// 值可差分）；observed = 可归因（delta，可含 N 天累计）。
enum DayKind { gap, baseline, observed }

/// 更新热力图的一个自然日。
class DayCell {
  final DateTime day;
  final DayKind kind;

  /// observed 专有：当日新增字数。
  final int delta;

  /// observed 专有：相邻有观测日相差 N 天 = 含 N 天累计；1 = 单日高置信。
  final int cumDays;

  const DayCell(this.day, this.kind, {this.delta = 0, this.cumDays = 1});
}

/// 端上自然日差分（docs/07 §2 回退规则）：按本地自然日分组取每日最后一
/// 次 words（items 新→旧，当日首个命中 = 当日最后观测）；相邻有观测日相
/// 差 1 天 → 归后一日；相差 N 天 → 「含 N 天累计」；>7 天 → 中间格标数据
/// 缺口不染色（回退方案最致命的误导点）。返回连续格数组（窗口 26 周，
/// 右端 = [end] 所在日历日）。
List<DayCell> buildDayCells(List<ObservationRow> items, {DateTime? end}) {
  if (items.isEmpty) return const [];
  final endIn = end ?? DateTime.now();
  final endD = DateTime(endIn.year, endIn.month, endIn.day);

  final dayWords = <DateTime, int>{};
  for (final o in items) {
    final w = o.words;
    if (w == null) continue;
    final t = DateTime.fromMillisecondsSinceEpoch(o.observedAt * 1000);
    final d = DateTime(t.year, t.month, t.day);
    dayWords.putIfAbsent(d, () => w);
  }
  if (dayWords.isEmpty) return const [];

  final days = dayWords.keys.toList()..sort((a, b) => a.compareTo(b));
  const maxSpan = 26 * 7;
  final firstD = days.first;
  final startD = endD.difference(firstD).inDays > maxSpan - 1
      ? endD.subtract(const Duration(days: maxSpan - 1))
      : firstD;
  final n = endD.difference(startD).inDays + 1;
  final cells = List<DayCell>.generate(
      n, (i) => DayCell(startD.add(Duration(days: i)), DayKind.gap));

  for (var i = 0; i < days.length; i++) {
    final d = days[i];
    if (d.isBefore(startD) || d.isAfter(endD)) continue;
    final idx = d.difference(startD).inDays;
    if (i == 0) {
      cells[idx] = DayCell(d, DayKind.baseline);
      continue;
    }
    final gap = d.difference(days[i - 1]).inDays;
    var delta = dayWords[d]! - dayWords[days[i - 1]]!;
    if (delta < 0) delta = 0; // 累计值应单调不减；负值 = 上游异常，
    // 诚实取 0 不染负
    cells[idx] = DayCell(d, DayKind.observed, delta: delta, cumDays: gap);
  }
  return cells;
}

/// 万/亿记数（端上统一口径）。
String wan(int n) {
  if (n >= 100000000) return '${(n / 100000000).toStringAsFixed(1)}亿';
  if (n >= 10000) return '${(n / 10000).toStringAsFixed(1)}万';
  return '$n';
}

/// 更新热力图（docs/07 §5 首屏）：某日新增字数，色阶**锚全勤阈值**（不做
/// 书内归一化——归一化会把 2,900 字染成高产色）；默认 12 周，可切
/// 4/12/26；区分「无更新」与「数据缺口」（缺口不染色）。
class UpdateHeatmap extends StatefulWidget {
  final List<DayCell> cells;

  const UpdateHeatmap({super.key, required this.cells});

  @override
  State<UpdateHeatmap> createState() => _UpdateHeatmapState();
}

class _UpdateHeatmapState extends State<UpdateHeatmap> {
  int _weeks = 12;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final need = _weeks * 7;
    late final List<DayCell> tail;
    if (widget.cells.length >= need) {
      tail = widget.cells.sublist(widget.cells.length - need);
    } else {
      // 左端以 gap 补齐对齐（网格右端锚定最后一天）。
      final endD = widget.cells.isEmpty
          ? DateTime.now()
          : widget.cells.last.day;
      final pad = need - widget.cells.length;
      final startD = DateTime(endD.year, endD.month, endD.day)
          .subtract(Duration(days: pad));
      tail = [
        for (var i = 0; i < pad; i++)
          DayCell(startD.add(Duration(days: i)), DayKind.gap),
        ...widget.cells,
      ];
    }

    // 自适应格子：4 周 → 24px 大方格，12 周 → 铺满卡片，26 周 → ~11px
    // 恰好铺满——三档都不需要横向滚动（inner 宽 = 屏宽 - 页边距 32 - 卡边距 28）
    const g = 2.0;
    final cols = _weeks;
    final innerW = MediaQuery.sizeOf(context).width - 60;
    final s = ((innerW - (cols - 1) * g) / cols).clamp(9.0, 24.0);
    // 月份刻度：可见范围内每个 1 号
    final labels = <_MonthLabel>[];
    for (var i = 0; i < tail.length; i++) {
      if (tail[i].day.day == 1) {
        labels.add(_MonthLabel(x: i * (s + g), text: '${tail[i].day.month}月'));
      }
    }
    final grid = SizedBox(
      height: 7 * (s + g) + 16,
      width: cols * (s + g) - g,
      child: CustomPaint(
          painter: _HeatmapPainter(
              cells: tail, scheme: scheme, cell: s, labels: labels)),
    );

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
            children: [
              Expanded(
                child: Text('更新热力图',
                    style: TextStyle(
                        fontFamily: 'serif',
                        fontSize: 13,
                        fontWeight: FontWeight.w700)),
              ),
              const SizedBox(width: 8),
              SegmentedButton<int>(
                segments: const [
                  ButtonSegment(value: 4, label: Text('4周')),
                  ButtonSegment(value: 12, label: Text('12周')),
                  ButtonSegment(value: 26, label: Text('26周')),
                ],
                selected: {_weeks},
                onSelectionChanged: (sel) => setState(() => _weeks = sel.first),
                showSelectedIcon: false,
                style: ButtonStyle(
                  backgroundColor: WidgetStateProperty.resolveWith(
                      (states) => states.contains(WidgetState.selected)
                          ? scheme.primary
                          : Colors.transparent),
                  foregroundColor: WidgetStateProperty.resolveWith(
                      (states) => states.contains(WidgetState.selected)
                          ? scheme.onPrimary
                          : scheme.onSurface),
                ),
              ),
            ],
          ),
          const SizedBox(height: 10),
          grid,
          const SizedBox(height: 10),
          Wrap(
            spacing: 10,
            runSpacing: 4,
            children: [
              _swatch(context, scheme.onSurface.withValues(alpha: .12),
                  '无更新'),
              _swatch(context, scheme.primary.withValues(alpha: .25),
                  '<${wan(kAttendanceThreshold)}'),
              _swatch(context, scheme.primary.withValues(alpha: .6),
                  '${wan(kAttendanceThreshold)}–'
                  '${wan(kAttendanceThreshold * 2)}'),
              _swatch(context, scheme.primary,
                  '≥${wan(kAttendanceThreshold * 2)}'),
              _swatch(context, null, '缺口/基线（不染色）'),
            ],
          ),
          const SizedBox(height: 4),
          Text('格内点 = 含多日累计；空白 = 数据缺口（不是无更新日）',
              style: TextStyle(fontSize: 10, color: scheme.onSurfaceVariant)),
          Text('估算值，非官方判定  全勤线 ${wan(kAttendanceThreshold)} 字/日'
              '（官方口径）',
              style: TextStyle(
                  fontSize: 10,
                  color: scheme.onSurfaceVariant,
                  fontWeight: FontWeight.w700)),
        ],
      ),
    );
  }

  Widget _swatch(BuildContext context, Color? fill, String label) {
    final scheme = Theme.of(context).colorScheme;
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        Container(
          width: 11,
          height: 11,
          decoration: BoxDecoration(
            color: fill,
            borderRadius: BorderRadius.circular(2),
            border: fill == null
                ? Border.all(
                    color: scheme.outline.withValues(alpha: .25), width: 1)
                : null,
          ),
        ),
        const SizedBox(width: 4),
        Text(label,
            style: TextStyle(fontSize: 10, color: scheme.onSurfaceVariant)),
      ],
    );
  }
}

class _HeatmapPainter extends CustomPainter {
  final List<DayCell> cells; // 长度 = 周数 × 7，列 = 周，行 = 一(0)..日(6)
  final ColorScheme scheme;
  final double cell;
  final List<_MonthLabel> labels;

  _HeatmapPainter(
      {required this.cells,
      required this.scheme,
      required this.cell,
      required this.labels});

  @override
  void paint(Canvas canvas, Size size) {
    const g = 2.0;
    final s = cell;
    for (var i = 0; i < cells.length; i++) {
      final col = i ~/ 7, row = i % 7;
      final rect = Rect.fromLTWH(col * (s + g), row * (s + g), s, s);
      final c = cells[i];
      final fill = _fill(c);
      final rrect = RRect.fromRectAndRadius(rect, const Radius.circular(2));
      if (fill == null) {
        // 缺口 / 基线：不染色，仅极淡描边
        canvas.drawRRect(
            rrect,
            Paint()
              ..style = PaintingStyle.stroke
              ..strokeWidth = 1
              ..color = scheme.outline.withValues(alpha: .25));
      } else {
        canvas.drawRRect(rrect, Paint()..color = fill);
        if (c.kind == DayKind.observed && c.cumDays > 1) {
          // 含多日累计的小点标记（半径随格子缩放）
          final r = (s * 0.16).clamp(1.2, 2.2);
          canvas.drawCircle(Offset(rect.right - r - 1.5, rect.top + r + 1.5),
              r, Paint()..color = scheme.onSurface.withValues(alpha: .65));
        }
      }
    }
    // 月份刻度标签（底部 16px 区）
    for (final l in labels) {
      final tp = TextPainter(
        text: TextSpan(
            text: l.text,
            style:
                TextStyle(fontSize: 10, color: scheme.onSurfaceVariant)),
        textDirection: TextDirection.ltr,
      )..layout();
      tp.paint(canvas, Offset(l.x + 1, 7 * (s + g) + 4));
    }
  }

  Color? _fill(DayCell c) => switch (c.kind) {
        DayKind.gap || DayKind.baseline => null,
        DayKind.observed => switch (c.delta) {
              0 => scheme.onSurface.withValues(alpha: .12),
              < kAttendanceThreshold => scheme.primary.withValues(alpha: .25),
              < kAttendanceThreshold * 2 =>
                scheme.primary.withValues(alpha: .6),
              _ => scheme.primary,
            },
      };

  @override
  bool shouldRepaint(_HeatmapPainter old) =>
      old.cells.length != cells.length || old.cell != cell;
}

/// 月份刻度标签（x = 该月 1 号所在列的列首）。
class _MonthLabel {
  final double x;
  final String text;

  const _MonthLabel({required this.x, required this.text});
}

/// 全勤达标看板（docs/07 §5）：月累计/目标、断更次数（已用/允许 1）、
/// 预计达标。回退口径：仅「有观测且 Δ=0」可判断更；未观测日是缺口，
/// 不计断更。
class AttendanceBoard extends StatelessWidget {
  final List<DayCell> cells;

  /// 最新观测 status（已完结书不再适用全勤口径）。
  final String? status;

  const AttendanceBoard({super.key, required this.cells, this.status});

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final now = DateTime.now();
    final month = cells
        .where((c) =>
            c.kind == DayKind.observed &&
            c.day.year == now.year &&
            c.day.month == now.month)
        .toList();

    Widget body;
    if (status == '已完结') {
      body = Text('本书已完结——全勤指标不再适用',
          style: TextStyle(fontSize: 11.5, color: scheme.onSurfaceVariant));
    } else if (month.isEmpty) {
      body = Text('本月无观测数据（数据缺口，不判「无更新」）',
          style: TextStyle(fontSize: 11.5, color: scheme.onSurfaceVariant));
    } else {
      final delta = month.fold(0, (a, c) => a + c.delta);
      final target = now.day * kAttendanceThreshold;
      final halts = month.where((c) => c.delta == 0).length;
      body = Column(
        children: [
          _row(context, '本月累计更新',
              '${wan(delta)} 字 / 目标 ${wan(target)} 字'),
          const SizedBox(height: 6),
          ClipRect(
            child: Container(
              height: 4,
              decoration: BoxDecoration(
                color: scheme.outline.withValues(alpha: .25),
                borderRadius: BorderRadius.circular(2),
              ),
              child: FractionallySizedBox(
                alignment: Alignment.centerLeft,
                widthFactor: (delta / target).clamp(0.0, 1.0),
                child: Container(color: scheme.primary),
              ),
            ),
          ),
          const SizedBox(height: 10),
          Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              Text('断更已用',
                  style: TextStyle(
                      fontSize: 12, color: scheme.onSurfaceVariant)),
              Column(
                crossAxisAlignment: CrossAxisAlignment.end,
                children: [
                  Text(halts == 0 ? '0 / 1' : halts == 1 ? '1 / 1' : '$halts / 1',
                      style: TextStyle(
                          fontSize: 12,
                          fontWeight: FontWeight.w700,
                          color: halts == 0
                              ? null
                              : halts == 1
                                  ? scheme.tertiary
                                  : scheme.error)),
                  Text(halts == 0
                      ? '全勤保持中'
                      : halts == 1
                          ? '再断更一次即失全勤'
                          : '全勤已破（估算）',
                      style: TextStyle(
                          fontSize: 10,
                          color: halts == 0
                              ? scheme.onSurfaceVariant
                              : halts == 1
                                  ? scheme.tertiary
                                  : scheme.error)),
                ],
              ),
            ],
          ),
          const SizedBox(height: 6),
          _row(context, '预计达标', delta >= target ? '跟得上' : '落后 ${wan(target - delta)} 字',
              color: delta >= target ? scheme.primary : null),
        ],
      );
    }

    return Container(
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        border: Border.all(color: scheme.outline.withValues(alpha: .4)),
        borderRadius: BorderRadius.circular(12),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text('全勤达标看板',
              style: TextStyle(
                  fontFamily: 'serif',
                  fontSize: 13,
                  fontWeight: FontWeight.w700)),
          const SizedBox(height: 8),
          body,
          const SizedBox(height: 8),
          Text('估算值，非官方判定；全勤线 ${wan(kAttendanceThreshold)} 字/日'
              '（官方口径 i.sfacg.com/fuli.shtml）',
              style: TextStyle(fontSize: 10, color: scheme.onSurfaceVariant)),
        ],
      ),
    );
  }

  Widget _row(BuildContext context, String label, String value, {Color? color}) {
    final scheme = Theme.of(context).colorScheme;
    return Row(
      mainAxisAlignment: MainAxisAlignment.spaceBetween,
      children: [
        Text(label, style: TextStyle(fontSize: 12, color: scheme.onSurfaceVariant)),
        Text(value,
            style: TextStyle(
                fontSize: 12,
                fontWeight: FontWeight.w700,
                color: color ?? scheme.onSurface)),
      ],
    );
  }
}

/// 六指标（docs/07 §3）。
enum TrendMetric { words, clicks, favs, praises, shortC, longC }

extension TrendMetricX on TrendMetric {
  String get label => switch (this) {
        TrendMetric.words => '字数',
        TrendMetric.clicks => '点击',
        TrendMetric.favs => '收藏',
        TrendMetric.praises => '点赞',
        TrendMetric.shortC => '短评',
        TrendMetric.longC => '长评',
      };

  int? valueOf(ObservationRow o) => switch (this) {
        TrendMetric.words => o.words,
        TrendMetric.clicks => o.clicks,
        TrendMetric.favs => o.favs,
        TrendMetric.praises => o.praises,
        TrendMetric.shortC => o.shortComments,
        TrendMetric.longC => o.longComments,
      };
}

/// 六指标趋势折线（累计值）：chips 切换指标；非空点 ≥3 才画（docs/07 §5
/// 红线——样本不足显示「观测不足」，不画单点假趋势）。
class MetricTrend extends StatefulWidget {
  /// 观测行（新 → 旧，端点原始顺序）。
  final List<ObservationRow> items;

  const MetricTrend({super.key, required this.items});

  @override
  State<MetricTrend> createState() => _MetricTrendState();
}

class _MetricTrendState extends State<MetricTrend> {
  TrendMetric _metric = TrendMetric.favs;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final pts = widget.items
        .reversed
        .map((o) => _metric.valueOf(o))
        .whereType<int>()
        .map((v) => v.toDouble())
        .toList();
    final rising = pts.length >= 2 && pts.last >= pts.first;
    final color = rising ? scheme.primary : scheme.tertiary;
    final minV = pts.isEmpty ? 0.0 : pts.reduce((a, b) => a < b ? a : b);
    final maxV = pts.isEmpty ? 0.0 : pts.reduce((a, b) => a > b ? a : b);
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
          Text('六指标趋势（累计）',
              style: TextStyle(
                  fontFamily: 'serif',
                  fontSize: 13,
                  fontWeight: FontWeight.w700)),
          const SizedBox(height: 8),
          Wrap(
            spacing: 6,
            runSpacing: 6,
            children: [
              for (final m in TrendMetric.values)
                ChoiceChip(
                  label: Text(m.label,
                      style: const TextStyle(fontSize: 11)),
                  selected: m == _metric,
                  showCheckmark: false,
                  padding: const EdgeInsets.symmetric(
                      horizontal: 8, vertical: 2),
                  visualDensity: VisualDensity.compact,
                  onSelected: (_) => setState(() => _metric = m)),
            ],
          ),
          const SizedBox(height: 10),
          if (pts.length < 3)
            Text('观测不足（${pts.length} 点）——至少 3 个观测点才画趋势',
                style: TextStyle(
                    fontSize: 11.5, color: scheme.onSurfaceVariant))
          else ...[
            Row(
              children: [
                Text('${_metric.label}时序',
                    style: TextStyle(
                        fontSize: 11, color: scheme.onSurfaceVariant)),
                const Spacer(),
                Text('${wan(pts.first.toInt())} → ${wan(pts.last.toInt())}',
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
                painter: _LinePainter(
                    points: pts, minV: minV, span: span, color: color),
              ),
            ),
            if (_metric == TrendMetric.clicks) ...[
              const SizedBox(height: 6),
              Text('累计量，非独立日增（点击口径按通路分档，docs/07 §3）',
                  style: TextStyle(
                      fontSize: 10, color: scheme.onSurfaceVariant)),
            ],
          ],
        ],
      ),
    );
  }
}

class _LinePainter extends CustomPainter {
  final List<double> points;
  final double minV;
  final double span;
  final Color color;

  _LinePainter({
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
    canvas.drawCircle(
        Offset(size.width,
            size.height - (points.last - minV) / span * size.height),
        2.5,
        Paint()..color = color);
  }

  @override
  bool shouldRepaint(_LinePainter old) => old.points.length != points.length;
}

/// 当前值仪表盘（docs/07 §5）：最新观测 vs 种子基线。非种子书标注
/// 「本机收录，无基线」（docs/07 §6）。
class CurrentValuesGrid extends StatelessWidget {
  final BookDetail detail;

  /// 最新观测（items.first，可为 null）。
  final ObservationRow? latest;

  const CurrentValuesGrid({super.key, required this.detail, this.latest});

  /// 基线判别（docs/07 §6）：非种子书 local 恒 null 且 meta 非空；
  /// 种子书无观测时两者皆空，有观测时 local 非空。
  bool get _inSeed => detail.local != null || detail.meta == null;

  static int? _num(dynamic v) => v is int ? v : (v is num ? v.toInt() : null);

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final eff = detail.effective ?? const <String, dynamic>{};
    final base = detail.book;
    final t = latest == null
        ? null
        : DateTime.fromMillisecondsSinceEpoch(latest!.observedAt * 1000);
    final cells = <List<dynamic>>[
      ['字数', _num(eff['words']), _inSeed ? _num(base['words']) : null],
      ['点击', _num(eff['clicks']), _inSeed ? _num(base['clicks']) : null],
      ['收藏', _num(eff['favs']), _inSeed ? _num(base['favs']) : null],
      ['点赞', _num(eff['praises']), _inSeed ? _num(base['praises']) : null],
      ['短评', latest?.shortComments, null],
      ['长评', latest?.longComments, null],
    ];

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
            children: [
              Expanded(
                child: Text('当前值',
                    style: TextStyle(
                        fontFamily: 'serif',
                        fontSize: 13,
                        fontWeight: FontWeight.w700)),
              ),
              if (!_inSeed)
                Text('本机收录，无种子基线',
                    style: TextStyle(
                        fontSize: 10,
                        color: scheme.tertiary,
                        fontWeight: FontWeight.w700)),
            ],
          ),
          Padding(
            padding: const EdgeInsets.only(top: 4),
            child: Text(
              latest == null
                  ? '尚无本机观测——当前值 = 种子快照（${detail.dataEnd}）'
                  : '最新观测 ${t!.month}/${t.day} ${t.hour}:'
                      '${t.minute.toString().padLeft(2, '0')}（本机观测）',
              style: TextStyle(fontSize: 10, color: scheme.onSurfaceVariant),
            ),
          ),
          const SizedBox(height: 10),
          Wrap(
            spacing: 12,
            runSpacing: 10,
            children: [
              for (final c in cells)
                _ValueCell(
                  label: c[0] as String,
                  latest: c[1] as int?,
                  baseline: c[2] as int?,
                ),
            ],
          ),
        ],
      ),
    );
  }
}

class _ValueCell extends StatelessWidget {
  final String label;
  final int? latest;
  final int? baseline;

  const _ValueCell(
      {required this.label, required this.latest, required this.baseline});

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return Container(
      width: 100,
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 8),
      decoration: BoxDecoration(
        color: scheme.surface,
        border: Border.all(color: scheme.outline.withValues(alpha: .3)),
        borderRadius: BorderRadius.circular(10),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(label,
              style: TextStyle(
                  fontSize: 10, color: scheme.onSurfaceVariant)),
          const SizedBox(height: 2),
          Text(latest == null ? '—' : wan(latest!),
              style: TextStyle(
                  fontSize: 14,
                  fontWeight: FontWeight.w700,
                  color: scheme.onSurface)),
          const SizedBox(height: 1),
          Text(baseline == null ? '' : '种子 ${wan(baseline!)}',
              style: TextStyle(
                  fontSize: 9.5, color: scheme.onSurfaceVariant)),
        ],
      ),
    );
  }
}

/// 对照图一个原始点（时间戳秒 + 指标值）。
class _RawPt {
  final int ts;
  final double v;

  const _RawPt(this.ts, this.v);
}

/// 对照图归一化点（x/y 均 0..1，由时间轴与值域归一）。
class _Pt {
  final double x;
  final double y;

  const _Pt(this.x, this.y);
}

/// 多序列折线绘制器：各序列按**时间**归一（x = (ts - t0)/(t1 - t0)），
/// 不用序号对齐——各书观测频率不同，序号对齐会把时间轴扭曲。
class _MultiLinePainter extends CustomPainter {
  final List<List<_Pt>> series;
  final List<Color> colors;

  const _MultiLinePainter(this.series, this.colors);

  @override
  void paint(Canvas canvas, Size size) {
    for (var s = 0; s < series.length; s++) {
      final pts = series[s];
      if (pts.length < 2) continue;
      final path = Path();
      for (var i = 0; i < pts.length; i++) {
        final x = pts[i].x * size.width;
        final y = size.height - pts[i].y * size.height;
        if (i == 0) {
          path.moveTo(x, y);
        } else {
          path.lineTo(x, y);
        }
      }
      canvas.drawPath(
          path,
          Paint()
            ..color = colors[s]
            ..style = PaintingStyle.stroke
            ..strokeWidth = 1.6
            ..strokeJoin = StrokeJoin.round);
      canvas.drawCircle(Offset(pts.last.x * size.width,
          size.height - pts.last.y * size.height),
          2.5, Paint()..color = colors[s]);
    }
  }

  @override
  bool shouldRepaint(_MultiLinePainter old) =>
      old.series.length != series.length;
}

/// 取观测序列中选中指标的非空点（最旧 → 最新）。
List<_RawPt> _metricPts(TrendMetric metric, List<ObservationRow> obs) {
  final out = <_RawPt>[];
  for (final o in obs.reversed) {
    final v = metric.valueOf(o);
    if (v == null) continue;
    out.add(_RawPt(o.observedAt, v.toDouble()));
  }
  return out;
}

/// 对照图一条序列（锚点书或 peer）。
class _PeerSeries {
  final String label;

  /// est_year（0 = 未知 → 不进图，docs/07 §1）。
  final int estYear;

  /// 观测行（新 → 旧）。
  final List<ObservationRow> obs;

  /// 非空 = 指定颜色（锚点用 primary）。
  final Color? color;

  _PeerSeries(this.label, this.estYear, this.obs, {this.color});
}

/// 同期对照折线（docs/07 §5）：锚点书 + watchlist 全部 role=peer 书，同
/// 指标同轴（v1 扁平一组，docs/07 §8）。红线：est_year 差 >2 年软警告（不
/// 硬拦）；est_year 未知不进图；<2 点序列不画（不画单点假趋势）；时间轴按
/// observed_at 对齐。入口 = 本区块「加入对照作品」（本地搜索 → watchAdd
/// active=true role=peer，docs/07 §1：加入需选 role，v1 入口在数据页）。
class PeerCompare extends ConsumerStatefulWidget {
  /// 锚点书 nid（本页的书）。
  final int nid;

  /// 锚点书标题（详情不可达时的兜底显示）。
  final String anchorTitle;

  /// 锚点书 est_year（0 = 未知）。
  final int anchorEstYear;

  /// 锚点书观测行（新 → 旧，端点原始顺序）。
  final List<ObservationRow> items;

  const PeerCompare({
    super.key,
    required this.nid,
    required this.anchorTitle,
    required this.anchorEstYear,
    required this.items,
  });

  @override
  ConsumerState<PeerCompare> createState() => _PeerCompareState();
}

class _PeerCompareState extends ConsumerState<PeerCompare> {
  TrendMetric _metric = TrendMetric.favs;
  Future<List<_PeerSeries>>? _peers;

  void _reload() {
    setState(() => _peers = _loadPeers());
  }

  /// 加载全部 role=peer 书（排除锚点书本身）：观测序列 + est_year。失败
  /// 降级——缺序列显示「观测不足」、缺 est_year 不进图，不画假对照。
  Future<List<_PeerSeries>> _loadPeers() async {
    final h = await ref.read(bootProvider.future);
    final wl = await h.api.watchList();
    final out = <_PeerSeries>[];
    for (final w in wl) {
      if (w.role != 'peer' || w.nid == widget.nid) continue;
      List<ObservationRow> obs = const [];
      try {
        obs = await h.api.observations(w.nid);
      } catch (_) {}
      var estYear = 0;
      try {
        final bd = await h.api.book(w.nid);
        estYear = (bd.book['est_year'] as num?)?.toInt() ?? 0;
      } catch (_) {}
      out.add(_PeerSeries(
          w.title.isEmpty ? 'nid ${w.nid}' : w.title, estYear, obs));
    }
    return out;
  }

  Future<void> _addPeer(BuildContext context) {
    return showDialog<void>(
      context: context,
      builder: (dialogContext) =>
          _PeerPickDialog(anchorNid: widget.nid, onAdded: _reload),
    );
  }

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
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
            children: [
              Expanded(
                child: Text('同期对照',
                    style: TextStyle(
                        fontFamily: 'serif',
                        fontSize: 13,
                        fontWeight: FontWeight.w700)),
              ),
              IconButton(
                visualDensity: VisualDensity.compact,
                icon: Icon(Icons.person_add_alt_1,
                    size: 18, color: scheme.onSurfaceVariant),
                tooltip: '加入对照作品',
                onPressed: () => _addPeer(context),
              ),
            ],
          ),
          if (_peers == null)
            Padding(
              padding: const EdgeInsets.only(left: 2),
              child: Text('加载对照作品…',
                  style: TextStyle(
                      fontSize: 11.5, color: scheme.onSurfaceVariant)),
            )
          else
            FutureBuilder<List<_PeerSeries>>(
              future: _peers!,
              builder: (context, snap) {
                if (snap.hasError) {
                  return Padding(
                    padding: const EdgeInsets.only(left: 2),
                    child: Text('对照作品加载失败',
                        style: TextStyle(
                            fontSize: 11.5, color: scheme.tertiary)),
                  );
                }
                final peers = snap.data ?? const <_PeerSeries>[];
                if (peers.isEmpty) {
                  return Padding(
                    padding: const EdgeInsets.only(left: 2),
                    child: Text(
                        '还没有对照作品——点右上按钮加入同期作品（role=同期对照），此处显示同指标同轴对照折线（标注 est_year 差）。',
                        style: TextStyle(
                            fontSize: 11.5,
                            color: scheme.onSurfaceVariant,
                            height: 1.4)),
                  );
                }
                final anchor = _PeerSeries(widget.anchorTitle,
                    widget.anchorEstYear, widget.items,
                    color: scheme.primary);
                return Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Wrap(
                      spacing: 6,
                      runSpacing: 6,
                      children: [
                        for (final m in TrendMetric.values)
                          ChoiceChip(
                            label: Text(m.label,
                                style: const TextStyle(fontSize: 11)),
                            selected: m == _metric,
                            showCheckmark: false,
                            padding: const EdgeInsets.symmetric(
                                horizontal: 8, vertical: 2),
                            visualDensity: VisualDensity.compact,
                            onSelected: (_) => setState(() => _metric = m),
                          ),
                      ],
                    ),
                    const SizedBox(height: 10),
                    _peerChartBlock(context, scheme, _metric, anchor, peers),
                  ],
                );
              },
            ),
        ],
      ),
    );
  }
}

/// 对照图一条线（序列 + 选中指标的点）。
class _PeerLine {
  final _PeerSeries s;
  final List<_RawPt> pts;

  const _PeerLine(this.s, this.pts);
}

/// 对照折线主体：锚点 + peers，同指标同轴。时间轴 = 并集 observed_at
/// 最小/最大（各书观测频率不同，序号对齐会扭曲）；est_year 未知不进图；
/// <2 点序列不画，改列诚实标注（docs/07 §5）。
Widget _peerChartBlock(BuildContext context, ColorScheme scheme,
    TrendMetric metric, _PeerSeries anchor, List<_PeerSeries> peers) {
  final lines = [
    for (final s in <_PeerSeries>[anchor, ...peers])
      _PeerLine(s, _metricPts(metric, s.obs)),
  ];
  final drawLines =
      lines.where((l) => l.s.estYear != 0 && l.pts.length >= 2).toList();
  var t0 = 0;
  var t1 = 0;
  for (final l in drawLines) {
    for (final p in l.pts) {
      if (t0 == 0 || p.ts < t0) t0 = p.ts;
      if (p.ts > t1) t1 = p.ts;
    }
  }
  final notes = <Widget>[
    for (final l in lines.where((l) => l.s.estYear == 0))
      Padding(
        padding: const EdgeInsets.only(bottom: 3),
        child: Text('${l.s.label}：est_year 未知，不进图',
            style: TextStyle(
                fontSize: 11, color: scheme.onSurfaceVariant)),
      ),
    for (final l
        in lines.where((l) => l.s.estYear != 0 && l.pts.length < 2))
      Padding(
        padding: const EdgeInsets.only(bottom: 3),
        child: Text('${l.s.label}：观测不足（${l.pts.length} 点），不画',
            style: TextStyle(
                fontSize: 11, color: scheme.onSurfaceVariant)),
      ),
  ];
  if (drawLines.isEmpty || t1 <= t0) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        ...notes,
        Text('观测不足——可画的对照线至少需要 2 个非空观测点',
            style: TextStyle(
                fontSize: 11.5, color: scheme.onSurfaceVariant)),
      ],
    );
  }
  var minV = double.infinity;
  var maxV = -double.infinity;
  for (final l in drawLines) {
    for (final p in l.pts) {
      if (p.v < minV) minV = p.v;
      if (p.v > maxV) maxV = p.v;
    }
  }
  final span = (maxV - minV).abs().clamp(1.0, double.infinity);
  final palette = [scheme.tertiary, scheme.secondary, scheme.error, scheme.outline];
  final ptLists = <List<_Pt>>[];
  final colors = <Color>[];
  for (var i = 0; i < drawLines.length; i++) {
    final l = drawLines[i];
    ptLists.add([
      for (final p in l.pts)
        _Pt((p.ts - t0) / (t1 - t0), (p.v - minV) / span),
    ]);
    colors.add(l.s.color ?? palette[i % palette.length]);
  }
  final legend = <Widget>[];
  for (var i = 0; i < drawLines.length; i++) {
    final l = drawLines[i];
    final warn = anchor.estYear != 0 &&
        l.s.estYear != 0 &&
        (l.s.estYear - anchor.estYear).abs() > 2;
    legend.add(Padding(
      padding: const EdgeInsets.only(bottom: 3),
      child: Row(
        children: [
          Container(
            width: 10,
            height: 10,
            decoration: BoxDecoration(
                color: colors[i], shape: BoxShape.circle),
          ),
          const SizedBox(width: 6),
          Expanded(
            child: Text(l.s.label,
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
                style:
                    TextStyle(fontSize: 11, color: scheme.onSurfaceVariant)),
          ),
          if (l.s.estYear != 0)
            Text('${l.s.estYear}',
                style: TextStyle(
                    fontSize: 11, color: scheme.onSurfaceVariant)),
          if (warn) ...[
            const SizedBox(width: 6),
            Text('定年差 ${(l.s.estYear - anchor.estYear).abs()} 年',
                style: TextStyle(
                    fontSize: 10,
                    color: scheme.tertiary,
                    fontWeight: FontWeight.w600)),
          ],
        ],
      ),
    ));
  }
  return Column(
    crossAxisAlignment: CrossAxisAlignment.start,
    children: [
      ...notes,
      ...legend,
      const SizedBox(height: 8),
      SizedBox(
        height: 72,
        width: double.infinity,
        child: CustomPaint(painter: _MultiLinePainter(ptLists, colors)),
      ),
      if (metric == TrendMetric.clicks) ...[
        const SizedBox(height: 6),
        Text('累计量，非独立日增（点击口径按通路分档，docs/07 §3）',
            style: TextStyle(
                fontSize: 10, color: scheme.onSurfaceVariant)),
      ],
    ],
  );
}

/// 对照书挑选器（docs/07 §1：加入需选 role——v1 入口在数据页对照区块，
/// 一律加入为 role=peer、active=true（对照需要观测时序））。本地搜索
/// 命中后点选即加入。
class _PeerPickDialog extends ConsumerStatefulWidget {
  final int anchorNid;
  final VoidCallback onAdded;

  const _PeerPickDialog({required this.anchorNid, required this.onAdded});

  @override
  ConsumerState<_PeerPickDialog> createState() => _PeerPickDialogState();
}

class _PeerPickDialogState extends ConsumerState<_PeerPickDialog> {
  final _ctrl = TextEditingController();
  Future<List<SearchItem>>? _results;
  bool _adding = false;

  @override
  void dispose() {
    _ctrl.dispose();
    super.dispose();
  }

  void _search(String v) {
    final q = v.trim();
    if (q.isEmpty) return;
    setState(() {
      _results = ref
          .read(bootProvider.future)
          .then((h) => h.api.search(q));
    });
  }

  Future<void> _pick(SearchItem it) async {
    if (_adding) return;
    setState(() => _adding = true);
    try {
      final h = await ref.read(bootProvider.future);
      await h.api.watchAdd(it.nid, active: true, role: 'peer');
      if (!mounted) return;
      widget.onAdded();
      if (mounted) Navigator.of(context).pop();
    } catch (e) {
      if (!mounted) return;
      setState(() => _adding = false);
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(
          content: Text('加入失败：${StrataApiException.userMessage(e)}')));
    }
  }

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return AlertDialog(
      title: Text('加入对照作品', style: const TextStyle(fontSize: 14)),
      content: SizedBox(
        width: double.maxFinite,
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            TextField(
              controller: _ctrl,
              autofocus: true,
              decoration: InputDecoration(
                hintText: '搜索书名 / 作者 / nid（内置库）',
                border: OutlineInputBorder(
                    borderRadius: BorderRadius.circular(8)),
                isDense: true,
              ),
              textInputAction: TextInputAction.search,
              onSubmitted: _search,
            ),
            const SizedBox(height: 10),
            if (_results == null)
              Text('搜索内置库，点选加入为同期对照',
                  style: TextStyle(
                      fontSize: 11, color: scheme.onSurfaceVariant))
            else
              FutureBuilder<List<SearchItem>>(
                future: _results!,
                builder: (context, snap) {
                  if (snap.hasError) {
                    return Text('搜索失败',
                        style: TextStyle(
                            fontSize: 11, color: scheme.tertiary));
                  }
                  final items = snap.data ?? const <SearchItem>[];
                  if (items.isEmpty) {
                    return Text('内置库无命中',
                        style: TextStyle(
                            fontSize: 11,
                            color: scheme.onSurfaceVariant));
                  }
                  return SizedBox(
                    height: 240,
                    child: ListView.builder(
                      itemCount: items.length,
                      itemBuilder: (context, i) {
                        final it = items[i];
                        if (it.nid == widget.anchorNid) {
                          return const SizedBox.shrink();
                        }
                        return ListTile(
                          dense: true,
                          title: Text(it.title,
                              maxLines: 1,
                              overflow: TextOverflow.ellipsis,
                              style: const TextStyle(fontSize: 12.5)),
                          subtitle: Text(
                              it.author.isEmpty ? '—' : it.author,
                              maxLines: 1,
                              style: TextStyle(
                                  fontSize: 10.5,
                                  color: scheme.onSurfaceVariant)),
                          onTap: () => _pick(it),
                        );
                      },
                    ),
                  );
                },
              ),
          ],
        ),
      ),
      actions: [
        TextButton(
          onPressed: () => Navigator.of(context).pop(),
          child: const Text('关闭'),
        ),
      ],
    );
  }
}

