import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:strata/core/providers.dart';
import 'package:strata/data/api/strata_api.dart';
import 'package:strata/pages/calendar_page.dart';

/// /calendar + /meta 伪造：日历页最小补丁（bounds 边界/落点 + 幽灵日
/// 可见可点 + 内置数当格子主角 + 估计标注 + 尾部不完整月不估算）的回归锚。
/// 原版结构不动：粒度段为月/周/VIP（日视图只经点格子下钻），
/// 月视图恒为 7 列日历网格。
class _FakeCalendarApi extends StrataApi {
  final String first;
  final String last;
  final Map<String, List<Map<String, dynamic>>> months; // key = YYYY-MM-01
  final Map<String, List<Map<String, dynamic>>> days; // key = YYYY-MM-DD

  _FakeCalendarApi({
    required this.first,
    required this.last,
    this.months = const {},
    this.days = const {},
  }) : super('http://127.0.0.1:1');

  @override
  Future<Meta> meta() async => Meta.fromJson({
    'manifest': {
      'schema_version': 9,
      'seed_version': 'test',
      'content_end': last,
      'built_at': '2026-11-26',
      'book_count': 10,
      'licensed_count': 1,
      'tag_count': 2,
      'tag_rows': 3,
      'gen_min': 2007,
      'gen_max': 2026,
    },
    'seed_meta': <String, String>{},
  });

  @override
  Future<CalendarResponse> calendar({
    required String granularity,
    required String anchor,
    int perCell = 3,
  }) async {
    final cells = switch (granularity) {
      'month' => months[anchor] ?? const [],
      // 真引擎日视图永远返回一格（空日期补零），伪造层保持一致。
      'day' => days[anchor] ?? [_cell(anchor, 0, 0)],
      _ => const <Map<String, dynamic>>[],
    };
    return CalendarResponse.fromJson({
      'granularity': granularity,
      'anchor': anchor,
      'cells': cells,
      'bounds': {'first': first, 'last': last},
    });
  }
}

Map<String, dynamic> _cell(
  String date,
  int total,
  int universe, [
  List<Map<String, dynamic>> items = const [],
]) => {'date': date, 'total': total, 'universe': universe, 'items': items};

Future<void> _pumpCalendar(WidgetTester tester, _FakeCalendarApi api) async {
  tester.view.physicalSize = const Size(360, 2400);
  tester.view.devicePixelRatio = 1.0;
  addTearDown(tester.view.reset);
  await tester.pumpWidget(
    ProviderScope(
      overrides: [
        bootProvider.overrideWith(
          (ref) async => EngineHandle(
            api: api,
            seedVersion: 'test',
            bookCount: 3,
          ),
        ),
      ],
      child: const MaterialApp(home: CalendarPage()),
    ),
  );
  await tester.pumpAndSettle();
}

void main() {
  group('日历页最小补丁', () {
    testWidgets('落点 = bounds 最新月；可越过 bounds 继续翻页；原版结构保留', (
      tester,
    ) async {
      // 2026-10：各日内置 3 本；15 日 = 幽灵日（内置 0 / 估计 40）。
      final cells = [
        for (var d = 1; d <= 31; d++)
          _cell(
            '2026-10-${d.toString().padLeft(2, '0')}',
            d == 15 ? 0 : 3,
            d == 15 ? 40 : 100 + d,
          ),
      ];
      await _pumpCalendar(
        tester,
        _FakeCalendarApi(
          first: '2008-01-01',
          // 完整月（末日 = 月末）：估计照常展示；下一页仍被 bounds 收住
          last: '2026-10-31',
          months: {'2026-10-01': cells},
          days: {
            '2026-10-15': [_cell('2026-10-15', 0, 40)],
          },
        ),
      );

      // 默认落点：bounds.last 所在月（不是 2025-01，也不是 genMax 12-31）
      expect(find.text('2026年10月'), findsOneWidget);
      // 月视图恒为 7 列日历网格
      expect(find.byType(GridView), findsOneWidget);
      // 粒度段：月/周/VIP 三段（日视图只经点格子下钻，不设「日」段）
      for (final seg in ['月', '周', 'VIP']) {
        expect(find.text(seg), findsOneWidget);
      }
      expect(find.text('日'), findsNothing);
      // 估算数量必须带「估计」标注；内置数当格子主角
      expect(find.text('~40'), findsOneWidget);
      // 页底汇总保留
      expect(find.textContaining('本月：全平台估计 ~'), findsOneWidget);
      // 不设时间上限：越过 bounds.last(2026-10-31) 仍可继续翻页
      expect(
        tester
            .widget<IconButton>(
              find.widgetWithIcon(IconButton, Icons.chevron_right),
            )
            .onPressed,
        isNotNull,
      );
      expect(
        tester
            .widget<IconButton>(
              find.widgetWithIcon(IconButton, Icons.chevron_left),
            )
            .onPressed,
        isNotNull,
      );

      // 幽灵日（内置 0 / 有估计）可点 → 下钻日视图，估计标注保留
      await tester.tap(find.text('~40'));
      await tester.pumpAndSettle();
      expect(find.text('10月15日（周四）'), findsOneWidget);
      expect(
        find.text('内置库当日无可点击作品（全平台估计 ~40 本）'),
        findsOneWidget,
      );
      // 回月视图 = 点回「月」段（原版交互）
      await tester.tap(find.text('月'));
      await tester.pumpAndSettle();
      expect(find.text('2026年10月'), findsOneWidget);

      // 越过 bounds.last 后仍可进入下一月（即使该月无数据）
      await tester.tap(find.widgetWithIcon(IconButton, Icons.chevron_right));
      await tester.pumpAndSettle();
      expect(find.text('2026年11月'), findsOneWidget);
    });

    testWidgets('稀疏月同样走日历网格，幽灵格可见', (tester) async {
      final built = const {
        1: 2,
        2: 1,
        5: 1,
        7: 1,
        9: 1,
        14: 1,
        15: 1,
        20: 1,
        27: 1,
      };
      final cells = [
        for (var d = 1; d <= 30; d++)
          _cell(
            '2010-06-${d.toString().padLeft(2, '0')}',
            built[d] ?? 0,
            8 + d % 5,
          ),
      ];
      await _pumpCalendar(
        tester,
        _FakeCalendarApi(
          first: '2008-01-01',
          last: '2010-06-30',
          months: {'2010-06-01': cells},
          days: {
            '2010-06-03': [_cell('2010-06-03', 0, 11)],
          },
        ),
      );

      expect(find.text('2010年6月'), findsOneWidget);
      expect(find.byType(GridView), findsOneWidget); // 日历形式不打折
      // 幽灵格（内置 0 / 有估计）也摆出估计数（带「估计~」+「本」后缀）；
      // 6 个 d≡3 (mod 5) 的格子同为 ~11，取第一个
      await tester.tap(find.text('~11').first);
      await tester.pumpAndSettle();
      expect(
        find.text('内置库当日无可点击作品（全平台估计 ~11 本）'),
        findsOneWidget,
      );
    });

    testWidgets('不完整月不做全平台估计：只显示内置数，并注明估计上界', (tester) async {
      // bounds.last = 2026-10-07 不在月末 → 10 月数据不完整，App 层整月
      // 不展示估计（种子/引擎仍返回 10 月的 universe 数，这里故意带上）。
      final cells = [
        for (var d = 1; d <= 31; d++)
          _cell(
            '2026-10-${d.toString().padLeft(2, '0')}',
            d == 5 ? 40 : (d == 6 ? 41 : 0),
            d == 3 ? 16 : 0,
          ),
      ];
      await _pumpCalendar(
        tester,
        _FakeCalendarApi(
          first: '2008-01-01',
          last: '2026-10-07',
          months: {'2026-10-01': cells},
          days: {
            '2026-10-01': [_cell('2026-10-01', 0, 11)],
            '2026-10-06': [
              _cell('2026-10-06', 41, 0, [
                {
                  'nid': 1,
                  'title': '甲',
                  'author': 'A',
                  'favs': 10,
                  'est_date': '2026-10-06',
                  'est_conf': 'high',
                },
              ]),
            ],
          },
        ),
      );

      expect(find.text('2026年10月'), findsOneWidget);
      // 网格里没有任何 ~N 估计数字（页首图例的「~N」是口径说明，不算）
      expect(
        find.byWidgetPredicate(
          (w) =>
              w is Text && w.data != null && RegExp(r'^~\d+$').hasMatch(w.data!),
        ),
        findsNothing,
      );
      expect(
        find.text('本月：内置库 81 本（可点击）· 数据不完整，全平台估计只到 2026年9月'),
        findsOneWidget,
      );

      // 有内置书的日：下钻列表照常可看，页底注明估计上界
      await tester.tap(find.text('41'));
      await tester.pumpAndSettle();
      expect(find.text('10月6日（周二）'), findsOneWidget);
      expect(
        find.text('— 内置库 41 本，按收藏排序 —'),
        findsOneWidget,
      );

      // ◀ 逐日退回 10/1：引擎仍给 ~11，但 App 层压掉 → 说明「数据不完整」，
      // 不能回落成「当日没有估计发书作品」（那会被读成当天真的没人发书）
      for (var i = 0; i < 5; i++) {
        await tester.tap(find.widgetWithIcon(IconButton, Icons.chevron_left));
        await tester.pumpAndSettle();
      }
      expect(find.text('10月1日（周四）'), findsOneWidget);
      expect(
        find.text('内置库当日无作品；该日数据不完整，全平台估计只到 2026年9月'),
        findsOneWidget,
      );
      expect(find.textContaining('全平台估计 ~11 本'), findsNothing);
    });
  });
}
