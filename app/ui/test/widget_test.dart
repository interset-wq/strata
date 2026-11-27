import 'dart:async';
import 'dart:io';
import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:strata/core/providers.dart';
import 'package:strata/data/api/strata_api.dart';
import 'package:strata/pages/about_page.dart';
import 'package:strata/pages/book_detail_page.dart';
import 'package:strata/pages/contest_archive_page.dart';
import 'package:strata/pages/contest_list_page.dart';
import 'package:strata/pages/roster_page.dart' as roster_page;
import 'package:strata/pages/settings_page.dart';
import 'package:strata/widgets/book_row_tile.dart';

/// 测试环境里所有 Image.network 都走这个 mock：返回一张 1×1 PNG，
/// 避免真实网络请求。
class _MockHttpOverrides extends HttpOverrides {
  @override
  HttpClient createHttpClient(SecurityContext? _) => _MockHttpClient();
}

class _MockHttpClient implements HttpClient {
  bool _autoUncompress = true;

  @override
  bool get autoUncompress => _autoUncompress;

  @override
  set autoUncompress(bool value) => _autoUncompress = value;

  @override
  Future<HttpClientRequest> getUrl(Uri url) async => _MockRequest();

  @override
  dynamic noSuchMethod(Invocation invocation) =>
      throw UnimplementedError('$invocation');
}

class _MockRequest implements HttpClientRequest {
  @override
  Future<HttpClientResponse> close() async => _MockResponse();

  @override
  dynamic noSuchMethod(Invocation invocation) =>
      throw UnimplementedError('$invocation');
}

// 1×1 红色 PNG（合法可解码）。
const _pixelPng = [
  0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A, //
  0x00, 0x00, 0x00, 0x0D, 0x49, 0x48, 0x44, 0x52,
  0x00, 0x00, 0x00, 0x01, 0x00, 0x00, 0x00, 0x01,
  0x08, 0x06, 0x00, 0x00, 0x00, 0x1F, 0x15, 0xC4,
  0x89, 0x00, 0x00, 0x00, 0x0D, 0x49, 0x44, 0x41,
  0x54, 0x78, 0x9C, 0x62, 0x00, 0x01, 0x00, 0x00,
  0x05, 0x00, 0x01, 0x0D, 0x0A, 0x2D, 0xB4, 0x00,
  0x00, 0x00, 0x00, 0x49, 0x45, 0x4E, 0x44, 0xAE,
  0x42, 0x60, 0x82,
];

// Flutter 的 NetworkImage 只读 headers.value('content-type')，所以 mock
// 只需实现这一个查询。
class _MockHeaders implements HttpHeaders {
  @override
  String? value(String name) =>
      name.toLowerCase() == 'content-type' ? 'image/png' : null;

  @override
  dynamic noSuchMethod(Invocation invocation) =>
      throw UnimplementedError('$invocation');
}

class _MockResponse implements HttpClientResponse {
  @override
  int get statusCode => 200;

  @override
  int get contentLength => _pixelPng.length;

  @override
  HttpClientResponseCompressionState get compressionState =>
      HttpClientResponseCompressionState.notCompressed;

  @override
  HttpHeaders get headers => _MockHeaders();

  @override
  StreamSubscription<Uint8List> listen(
    void Function(Uint8List event)? onData, {
    Function? onError,
    void Function()? onDone,
    bool? cancelOnError,
  }) {
    return Stream<Uint8List>.fromIterable([Uint8List.fromList(_pixelPng)])
        .listen(
          onData,
          onError: onError,
          onDone: onDone,
          cancelOnError: cancelOnError,
        );
  }

  @override
  dynamic noSuchMethod(Invocation invocation) =>
      throw UnimplementedError('$invocation');
}

void main() {
  testWidgets('BookRowTile 渲染标题/作者/IP 徽标/标签/指标行', (tester) async {
    HttpOverrides.global = _MockHttpOverrides();
    addTearDown(() => HttpOverrides.global = null);

    final item = RankItem.fromJson({
      'rank': 1,
      'nid': 1001,
      'title': '测试之书',
      'author': '测试作者',
      'genre': '魔幻',
      'est_year': 2020,
      'favs': 123,
      'fav_pctl': 0.8,
      'cover_url': '2020/1/x.jpg',
      'status': '连载中',
      'words': 120000,
      'clicks': 9000,
      'praises': 55,
      'form': 'long',
      'tags': ['标签A', '标签B'],
    });

    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: ListView(
            children: [BookRowTile(item: item, ipLabel: '崩坏3')],
          ),
        ),
      ),
    );
    // 让 mock 图片走完解码帧
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 100));

    expect(find.text('测试之书'), findsOneWidget);
    expect(find.text('测试作者'), findsOneWidget);
    expect(find.text('崩坏3'), findsOneWidget); // IP 徽标
    expect(find.text('魔幻'), findsOneWidget); // 题材 tag
    expect(find.text('标签A'), findsOneWidget);
    // 指标行：12.0万字 · 9000 · 123 · 55（顺序 字数→点击→收藏→赞）
    expect(find.text('12.0万字'), findsOneWidget);
    expect(find.text('9000'), findsOneWidget);
    expect(find.text('123'), findsOneWidget);
    expect(find.text('55'), findsOneWidget);
  });

  testWidgets('BookRowTile 无封面时兜底渲染且指标空值不显示', (tester) async {
    HttpOverrides.global = _MockHttpOverrides();
    addTearDown(() => HttpOverrides.global = null);

    final item = RankItem.fromJson({
      'rank': 2,
      'nid': 1002,
      'title': '无封面之书',
      'author': 'B',
      'genre': null,
      'est_year': 2019,
      'favs': 0,
      'form': 'short',
      'words': 3000,
    });

    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: ListView(children: [BookRowTile(item: item)]),
        ),
      ),
    );
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 100));

    expect(find.text('无封面之书'), findsOneWidget);
    expect(find.text('3000字'), findsOneWidget);
    // clicks/praises 为 null、favs=0 → 指标行只有字数
    expect(find.text('9000'), findsNothing);
    expect(find.text('123'), findsNothing);
  });

  group('书籍详情页分区（2026-11-26 IA 重排）', () {
    // 种子书：连载中 + 最后更新远早于快照日 + 参赛且获奖 + 同作者另有两本
    BookDetail seedDetail() => BookDetail.fromJson({
      'source': 'seed',
      'data_end': '2026-11-24',
      'book': {
        'nid': 1001,
        'title': '测试之书',
        'author': '测试作者',
        'genre': '魔幻',
        'price_type': 'VIP',
        'status': '连载中',
        'contest': '第十二届征文',
        'words': 1560000,
        'clicks': 123000,
        'favs': 45000,
        'praises': 82000,
        'featured': false,
        'cover_url': null,
        'updated_at': '2026-01-28T22:35:15',
        'est_year': 2019,
        'est_date': '2019-03-06',
        'est_conf': '中',
        'form': 'long',
        'cqs_state': '不参与评分',
        'is_licensed': false,
      },
      'tags': <String>['复仇', '悬疑'],
      'effective': {
        'title': '测试之书',
        'author': '测试作者',
        'status': '连载中',
        'words': 1560000,
        'summary': '甲' * 120,
        'add_time': '2019-03-04',
      },
      'awards': [
        {'nid': 1001, 'edition': '第 12 届征文', 'award': '银奖', 'category': '长篇'},
      ],
      'refresh': {
        'rate_limit_enabled': true,
        'window_seconds': 86400,
        'last_attempt_at': 1700000000,
      },
    });

    List<RankItem> twoWorks() => [
      RankItem.fromJson({
        'rank': 1,
        'nid': 1001,
        'title': '测试之书',
        'author': '测试作者',
        'est_year': 2019,
        'favs': 1,
        'form': 'long',
      }),
      RankItem.fromJson({
        'rank': 2,
        'nid': 2002,
        'title': '银盐时代',
        'author': '测试作者',
        'est_year': 2021,
        'favs': 2,
        'form': 'long',
      }),
      RankItem.fromJson({
        'rank': 3,
        'nid': 2003,
        'title': '第七种沉默',
        'author': '测试作者',
        'est_year': 2022,
        'favs': 3,
        'form': 'long',
      }),
    ];

    // 相关推荐：同 form、别的作者（后端已排除锚点作者）。
    List<RankItem> twoSimilar() => [
      RankItem.fromJson({
        'rank': 1,
        'nid': 3001,
        'title': '雾中列车',
        'author': '他人甲',
        'est_year': 2020,
        'favs': 900,
        'form': 'long',
      }),
      RankItem.fromJson({
        'rank': 2,
        'nid': 3002,
        'title': '北城以北',
        'author': '他人乙',
        'est_year': 2021,
        'favs': 700,
        'form': 'long',
      }),
    ];

    Future<void> pumpDetail(
      WidgetTester tester, {
      BookDetail? detail,
      List<RankItem>? related,
    }) async {
      HttpOverrides.global = _MockHttpOverrides();
      addTearDown(() => HttpOverrides.global = null);
      tester.view.physicalSize = const Size(1080, 4800);
      tester.view.devicePixelRatio = 3;
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);

      final api = _FakeApi(detail ?? seedDetail(), twoWorks(), [
        ObservationRow.fromJson({
          'observed_at': 1764000000,
          'favs': 45000,
          'praises': 82000,
          'words': 1560000,
        }),
        ObservationRow.fromJson({
          'observed_at': 1763913600,
          'favs': 44800,
          'praises': 81700,
          'words': 1550000,
        }),
      ], similar: related ?? const []);
      await tester.pumpWidget(
        ProviderScope(
          overrides: [
            bootProvider.overrideWith(
              (ref) async =>
                  EngineHandle(api: api, seedVersion: 'test', bookCount: 3),
            ),
          ],
          child: const MaterialApp(home: BookDetailPage(nid: 1001)),
        ),
      );
      await tester.pumpAndSettle();
    }

    double y(WidgetTester tester, Finder f) => tester.getTopLeft(f).dy;

    testWidgets('分区顺序：简介 → 热度 → 赛事 → 口径 → 关联（观测已收二级页）', (tester) async {
      await pumpDetail(tester);

      expect(find.text('作品简介'), findsOneWidget);
      expect(find.text('点击'), findsOneWidget);
      expect(find.text('第十二届征文'), findsOneWidget);
      expect(find.text('其他作品'), findsOneWidget);
      expect(find.text('数据口径与来源'), findsOneWidget);

      final heatY = y(tester, find.text('点击'));
      expect(y(tester, find.text('作品简介')), lessThan(heatY));
      expect(y(tester, find.text('第十二届征文')), greaterThan(heatY));
      // 口径卡排在发现区块之前（用户 2026-11-26）
      expect(
        y(tester, find.text('数据口径与来源')),
        greaterThan(y(tester, find.text('第十二届征文'))),
      );
      expect(
        y(tester, find.text('其他作品')),
        greaterThan(y(tester, find.text('数据口径与来源'))),
      );
      // 横滑标题不带本数、不再挂「作者页」按钮（入口只有作者名一处）
      expect(find.text('作者页'), findsNothing);
      expect(find.byIcon(Icons.arrow_forward), findsNothing);
      // 观测历史不占详情页区块；体量与更新卡已删
      expect(find.text('观测历史'), findsNothing);
      expect(find.text('体量与更新'), findsNothing);
    });

    testWidgets('热度卡只有四个计数，无任何分位/派生指标', (tester) async {
      await pumpDetail(tester);
      for (final k in ['点击', '收藏', '点赞', '字数']) {
        expect(find.text(k), findsOneWidget);
      }
      expect(find.textContaining('前 '), findsNothing);
      expect(find.textContaining('分位'), findsNothing);
      expect(find.text('PR'), findsNothing);
      expect(find.textContaining('CQS'), findsNothing);
    });

    testWidgets('赛事卡只报届次：不写「参赛」、不加区块标题、获奖一律不显示', (tester) async {
      await pumpDetail(tester);
      // 一张卡只装一件事：区块标题是噪音（用户 2026-11-26）
      expect(find.text('赛事'), findsNothing);
      expect(find.text('第十二届征文'), findsOneWidget);
      expect(find.text('参赛'), findsNothing);
      // contest_awards 里 867/911 是占位「待逐档标定」→ 端上不再出现任何获奖文案
      expect(find.text('征文获奖'), findsNothing);
      expect(find.text('银奖'), findsNothing);
      expect(find.byIcon(Icons.emoji_events), findsNothing);
      // 旗标必须带色且看得见：朱砂实心旗（金色描线在纸面近乎灰）
      final flag = tester.widget<Icon>(find.byIcon(Icons.flag));
      final flagCtx = tester.element(find.byIcon(Icons.flag));
      expect(flag.color, Theme.of(flagCtx).colorScheme.primary);
    });

    testWidgets('最后更新折进口径卡且 ISO 时间戳格式化；不再有停更徽标', (tester) async {
      await pumpDetail(tester);
      expect(find.text('体量与更新'), findsNothing);
      expect(find.textContaining('停更'), findsNothing);
      await tester.tap(find.text('数据口径与来源'));
      await tester.pumpAndSettle();
      expect(find.text('最后更新'), findsOneWidget);
      expect(find.text('2026-01-28 22:35'), findsOneWidget);
      expect(find.textContaining('2026-01-28T22:35:15'), findsNothing);
      expect(find.text('官方建档'), findsOneWidget);
    });

    testWidgets('主动作收口到底部栏：AppBar 只有官方页与观测两个入口', (tester) async {
      await pumpDetail(tester);
      expect(find.byIcon(Icons.open_in_new), findsOneWidget);
      expect(find.byIcon(Icons.timeline), findsOneWidget);
      // 观测入口与官方页入口同在 AppBar 动作区（不塞在标题里，用户 2026-11-26）
      final data = tester.getCenter(find.byIcon(Icons.timeline));
      final official = tester.getCenter(find.byIcon(Icons.open_in_new));
      expect(data.dy, official.dy);
      expect(data.dx, lessThan(official.dx));
      expect(find.text('书籍详情'), findsOneWidget);
      // 关注/追踪图标不再出现在 AppBar（同一动作全站只此一处）
      expect(find.byIcon(Icons.bookmark_add_outlined), findsOneWidget);
      expect(find.byIcon(Icons.visibility_outlined), findsOneWidget);
      expect(find.text('关注'), findsOneWidget);
      expect(find.text('追踪'), findsOneWidget);
      expect(find.text('刷新'), findsOneWidget);
      // 旧的页内重复按钮不再存在
      expect(find.text('刷新观测'), findsNothing);
      expect(find.text('关注此书'), findsNothing);
    });

    testWidgets('简介全文渲染，不截断（用户 2026-11-26）', (tester) async {
      await pumpDetail(tester);
      expect(find.text('甲' * 120), findsOneWidget);
      expect(find.text('展开全文'), findsNothing);
      expect(find.text('收起'), findsNothing);
    });

    testWidgets('数据口径默认折叠，展开后才出现字段', (tester) async {
      await pumpDetail(tester);
      expect(find.text('数据来源'), findsNothing);
      await tester.tap(find.text('数据口径与来源'));
      await tester.pumpAndSettle();
      expect(find.text('数据来源'), findsOneWidget);
      expect(find.text('内置'), findsOneWidget);
      expect(find.text('入库日期（估计）'), findsOneWidget);
      // 官方信息这个旧名字不再出现
      expect(find.text('官方信息'), findsNothing);
    });

    testWidgets('观测历史只在二级页：详情页正文无区块，入口在 AppBar 动作区', (tester) async {
      await pumpDetail(tester);
      expect(find.byIcon(Icons.timeline), findsOneWidget);
      expect(find.text('观测历史'), findsNothing);
      expect(find.text('图表'), findsNothing);
      expect(find.textContaining('上次刷新'), findsNothing);
      expect(find.textContaining('查看全部'), findsNothing);
    });

    testWidgets('库外书（无 form/est/awards）对应行整行不渲染', (tester) async {
      await pumpDetail(
        tester,
        detail: BookDetail.fromJson({
          'source': 'local',
          'data_end': '2026-11-24',
          'book': {
            'nid': 1001,
            'title': '库外之书',
            'author': '某作者',
            'status': '连载中',
            'words': 420000,
            'clicks': 31000,
            'favs': 8420,
            'praises': 12000,
            'updated_at': '2026-11-20T10:00:00',
          },
          'tags': <String>[],
          'effective': {'title': '库外之书', 'words': 420000},
        }),
      );
      // 内置专有字段不存在 → 对应行整行不渲染（口径卡只剩真有的一侧）
      expect(find.text('入库日期（估计）'), findsNothing);
      expect(find.text('收录置信度'), findsNothing);
      expect(find.text('形式'), findsNothing);
      expect(find.text('其他作品'), findsNothing);
      // 本数不进文案，作者页入口只在作者名（用户 2026-11-26）
      expect(find.text('作者页'), findsNothing);
      expect(find.text('第十二届征文'), findsNothing);
      expect(find.text('数据来源'), findsNothing); // 折叠态，展开才有
    });

    testWidgets('相关推荐独立成轨：排在其他作品之后，不含锚点与诊断字段', (tester) async {
      await pumpDetail(tester, related: twoSimilar());
      expect(find.text('相关推荐'), findsOneWidget);
      expect(find.text('雾中列车'), findsOneWidget);
      expect(find.text('北城以北'), findsOneWidget);
      expect(
        y(tester, find.text('相关推荐')),
        greaterThan(y(tester, find.text('其他作品'))),
      );
      // 条卡第二行报作者与年代：推荐的作者是陌生人，只给书名无从判断（用户 2026-11-26）
      expect(find.text('他人甲 · 2020'), findsOneWidget);
      expect(find.text('他人乙 · 2021'), findsOneWidget);
      // 卡片尺寸：62dp/11px×2 行时书名普遍被截成「转生异世界不吸…」，
      // 其他作品放大到 12px×3 行，相关推荐走 13px×3 行的横式条卡。
      final coverTitle = tester.widget<Text>(find.text('银盐时代'));
      expect(coverTitle.style?.fontSize, 12);
      expect(coverTitle.maxLines, 3);
      final infoTitle = tester.widget<Text>(find.text('雾中列车'));
      expect(infoTitle.style?.fontSize, 13);
      expect(infoTitle.maxLines, 3);
      // 轨上只说人话：召回档/排序键等内部指标名不外泄
      expect(find.textContaining('cqs'), findsNothing);
      expect(find.textContaining('强标签'), findsNothing);
      expect(find.textContaining('A′'), findsNothing);
    });

    testWidgets('相关推荐不足两本整行隐藏（增益区块不占位）', (tester) async {
      await pumpDetail(tester, related: [twoSimilar().first]);
      expect(find.text('相关推荐'), findsNothing);
      await pumpDetail(tester, related: const []);
      expect(find.text('相关推荐'), findsNothing);
      // 其他作品轨不受影响
      expect(find.text('其他作品'), findsOneWidget);
    });
  });

  group('设置页分组（2026-11-26 改版）', () {
    Future<void> pumpSettings(WidgetTester tester) async {
      // ListView 只构建可见项：把测试视口拉高，四组才都在树上
      tester.view.physicalSize = const Size(600, 2400);
      tester.view.devicePixelRatio = 1.0;
      addTearDown(tester.view.reset);
      await tester.pumpWidget(
        ProviderScope(
          overrides: [
            metaProvider.overrideWith(
              (ref) async => Meta.fromJson({
                'manifest': {
                  'schema_version': 9,
                  'seed_version': 'v9',
                  'content_end': '2026-11-24',
                  'built_at': '2026-11-25',
                  'book_count': 246000,
                  'licensed_count': 47,
                  'tag_count': 30,
                  'tag_rows': 100,
                  'gen_min': 2007,
                  'gen_max': 2026,
                },
                'seed_meta': <String, dynamic>{},
              }),
            ),
            detailRateLimitProvider.overrideWith(
              (ref) async => EngineSettings(
                detailRateLimitEnabled: true,
                windowSeconds: 86400,
              ),
            ),
            testBookProvider.overrideWith(
              (ref) async => const TestBook(nid: 900001, present: false),
            ),
          ],
          child: const MaterialApp(home: SettingsPage()),
        ),
      );
      await tester.pumpAndSettle();
    }

    testWidgets('五组小标题，「数据」不再出现两次；主题收成一行', (tester) async {
      await pumpSettings(tester);
      for (final g in ['阅读', '数据', '抓取', '开发者', '关于']) {
        expect(find.text(g), findsOneWidget);
      }
      expect(find.text('外观'), findsNothing);
      expect(
        find.text('书层 Strata · AGPL-3.0\n数据来自 SFACG 菠萝包轻小说公开页面'),
        findsOneWidget,
      );
      // 主题不再占三行 RadioListTile
      expect(find.byType(RadioListTile<ThemeMode>), findsNothing);
      expect(find.text('主题'), findsOneWidget);
      expect(find.text('跟随系统'), findsOneWidget);
      expect(find.text('浅色（纸面）'), findsNothing);
    });

    testWidgets('关于组：App 信息页入口 + GitHub 仓库 / Issues + QQ 群号', (tester) async {
      await pumpSettings(tester);
      expect(find.text('App 信息'), findsOneWidget);
      expect(find.text('GitHub 仓库'), findsOneWidget);
      expect(find.text('github.com/interset-wq/strata'), findsOneWidget);
      expect(find.text('问题反馈'), findsOneWidget);
      expect(find.text('QQ 群'), findsOneWidget);
      expect(find.text('881041631'), findsOneWidget);
    });

    testWidgets('App 信息页：版本 / 许可 / 数据来源 / 离线声明', (tester) async {
      await tester.pumpWidget(const MaterialApp(home: AboutPage()));
      expect(find.text('书层 Strata'), findsOneWidget);
      expect(find.text('版本 1.0.0（build 1）'), findsOneWidget);
      expect(find.text('AGPL-3.0（开源）'), findsOneWidget);
      expect(find.text('SFACG 菠萝包轻小说公开页面'), findsOneWidget);
      expect(find.textContaining('完全离线运行'), findsOneWidget);
    });

    testWidgets('测试工具默认折叠：种子日期展开才可见', (tester) async {
      await pumpSettings(tester);
      expect(find.text('测试种子日期'), findsNothing);
      await tester.tap(find.text('测试工具'));
      await tester.pumpAndSettle();
      expect(find.text('测试种子日期'), findsOneWidget);
      expect(find.text('工作台测试书'), findsOneWidget);
    });

    testWidgets('口径说明默认折叠，说明文字不占正文', (tester) async {
      await pumpSettings(tester);
      expect(find.textContaining('观测数据只保存在本机'), findsNothing);
      await tester.tap(find.text('口径说明'));
      await tester.pumpAndSettle();
      expect(find.textContaining('观测数据只保存在本机'), findsOneWidget);
    });
  });

  group('赛事档案两个页面（2026-11-26 接官方规模）', () {
    ContestGroup thirteen() => ContestGroup.fromJson({
      'name': '十三征',
      'series': 'x',
      'count': 335,
      'forms': {'long': 246, 'short': 80, 'medium': 7, 'dialogue': 2},
      'tracks': ['十三征长篇', '十三征短篇', '十三征中篇'],
      'year_min': 2025,
      'year_max': 2025,
      'year': 2025,
      'start': '2025-05-04',
      'end': '2025-10-07',
      'result': '2026-01-16',
      'official': 'https://pages.sfacg.com/h5/act/zw20250504/',
      'roster': true,
      'divisions': [
        {'name': '长篇', 'tag': 701, 'roster': 3407},
        {'name': '中篇', 'tag': 702, 'roster': 767},
        {'name': '短篇', 'tag': 703, 'roster': 623},
      ],
      'roster_total': 4797,
      'award_total': 25,
    });

    ContestGroup seven() => ContestGroup.fromJson({
      'name': '七征',
      'series': 'x',
      'count': 452,
      'forms': {'long': 217, 'dialogue': 144, 'short': 81},
      'tracks': ['七征长篇', '七征对话类征文长篇'],
      'year_min': 2019,
      'year_max': 2019,
      'year': 2019,
      'start': '2019-05-25',
      'end': '2019-09-24',
      'result': '2019-12-24',
      'roster': true,
      'divisions': [
        {'name': '长篇', 'tag': 408, 'roster': 4272},
        {'name': '对话长篇', 'tag': 411, 'roster': 583},
      ],
      'roster_total': 7350,
    });

    ContestGroup spring2025() => ContestGroup.fromJson({
      'name': '2025春季征文',
      'series': 'spring',
      'count': 115,
      'forms': {'long': 114, 'dialogue': 1},
      'tracks': ['2025春季征文'],
      'year_min': 2025,
      'year_max': 2025,
      'year': 2025,
      'start': '2025-03-01',
      'end': '2025-05-03',
      'roster': true,
      'divisions': [
        {'name': '全部', 'tag': 555, 'roster': 1708},
      ],
      'roster_total': 1708,
    });

    ContestGroup noRoster() => ContestGroup.fromJson({
      'name': '玄幻征文',
      'series': 'other',
      'count': 125,
      'forms': {'long': 96, 'dialogue': 29},
      'tracks': ['玄幻征文'],
      'year_min': 2019,
      'year_max': 2019,
    });

    // 一/二/三征：上游只有获奖作品标签（635–649，contest-achieve 采集
    // 2026-11-24），引擎以 list_kind=award 接进同一条名单链路——
    // 参赛清单口径不存在，页面只能说「获奖名额 / 获奖名单」。
    ContestGroup oneZheng() => ContestGroup.fromJson({
      'name': '一征',
      'series': 'x',
      'count': 2,
      'forms': {'long': 2},
      'tracks': ['一征'],
      'year_min': 2014,
      'year_max': 2014,
      'roster': false,
      'list_kind': 'award',
      'divisions': [
        {'name': '金奖', 'tag': 635, 'kind': 'award', 'roster': 1, 'awards': 1},
        {'name': '银奖', 'tag': 636, 'kind': 'award', 'roster': 1, 'awards': 1},
        {'name': '铜奖', 'tag': 637, 'kind': 'award', 'roster': 3, 'awards': 3},
      ],
      'award_total': 5,
    });

    List<Map<String, dynamic>> twoBooks() => [
      {
        'rank': 1,
        'nid': 1001,
        'title': '魔王小姐请再忍耐一下',
        'author': '香草和布丁',
        'est_year': 2011,
        'favs': 33521,
        'form': 'long',
      },
      {
        'rank': 2,
        'nid': 1002,
        'title': '夺舍失败后',
        'author': '太阳花田里的树',
        'est_year': 2012,
        'favs': 29266,
        'form': 'short',
      },
    ];

    Future<void> pumpList(
      WidgetTester tester,
      List<ContestGroup> gs, {
      String? lane,
    }) async {
      HttpOverrides.global = _MockHttpOverrides();
      addTearDown(() => HttpOverrides.global = null);
      tester.view.physicalSize = const Size(600, 2400);
      tester.view.devicePixelRatio = 1.0;
      addTearDown(tester.view.reset);
      await tester.pumpWidget(
        ProviderScope(
          overrides: [
            bootProvider.overrideWith(
              (ref) async => EngineHandle(
                api: _FakeContestApi(gs),
                seedVersion: 'test',
                bookCount: 3,
              ),
            ),
          ],
          child: MaterialApp(home: ContestListPage(initialLane: lane)),
        ),
      );
      await tester.pumpAndSettle();
    }

    Future<void> pumpArchive(
      WidgetTester tester,
      ContestGroup g, {
      List<Map<String, dynamic>>? books,
      List<Map<String, dynamic>>? awards,
    }) async {
      HttpOverrides.global = _MockHttpOverrides();
      addTearDown(() => HttpOverrides.global = null);
      tester.view.physicalSize = const Size(600, 3000);
      tester.view.devicePixelRatio = 1.0;
      addTearDown(tester.view.reset);
      await tester.pumpWidget(
        // 同一 test 里连着 pump 两个 ProviderScope：State 会被复用，容器连
        // overrides 一起留着（第二次还在读第一份数据）。key 换掉才真重建。
        ProviderScope(
          key: ValueKey('archive-${g.name}'),
          overrides: [
            bootProvider.overrideWith(
              (ref) async => EngineHandle(
                api: _FakeContestApi(
                  [g],
                  books: books ?? const [],
                  awards: awards ?? const [],
                ),
                seedVersion: 'test',
                bookCount: 3,
              ),
            ),
          ],
          child: MaterialApp(home: ContestArchivePage(name: g.name)),
        ),
      );
      await tester.pumpAndSettle();
    }

    Future<void> pumpRoster(WidgetTester tester, ContestGroup g) async {
      HttpOverrides.global = _MockHttpOverrides();
      addTearDown(() => HttpOverrides.global = null);
      tester.view.physicalSize = const Size(600, 1400);
      tester.view.devicePixelRatio = 1.0;
      addTearDown(tester.view.reset);
      await tester.pumpWidget(
        ProviderScope(
          overrides: [
            bootProvider.overrideWith(
              (ref) async => EngineHandle(
                api: _FakeContestApi(
                  [g],
                  rosterKind: g.listKind,
                  rosterItems: [
                    {
                      'nid': 9990101,
                      'title': '金奖作品',
                      'author': '作者甲',
                      'in_library': false,
                    },
                  ],
                ),
                seedVersion: 'test',
                bookCount: 3,
              ),
            ),
          ],
          child: MaterialApp(home: roster_page.RosterPage(contest: g.name)),
        ),
      );
      await tester.pumpAndSettle();
    }

    double top(WidgetTester tester, Finder f) => tester.getTopLeft(f).dy;

    testWidgets('列表：主数=官方清单，年份轨只在 X征，最近一届在前', (tester) async {
      await pumpList(tester, [spring2025(), thirteen(), seven(), noRoster()]);

      // 默认春季 tab：单轨赛事的官方数当主数，年份不占独立列（左轨只属于
      // 同系列年表）。
      expect(find.text('1,708'), findsOneWidget);
      expect(find.text('2025'), findsNothing);
      expect(find.text('官方清单'), findsOneWidget);
      expect(find.text('在库'), findsOneWidget);

      await tester.tap(find.text('X征'));
      await tester.pumpAndSettle();
      expect(find.text('4,797'), findsOneWidget);
      expect(find.text('7,350'), findsOneWidget);
      expect(find.text('2025'), findsOneWidget); // 十三征的年代轨
      expect(find.text('2019'), findsOneWidget);
      expect(
        top(tester, find.text('十三征')) < top(tester, find.text('七征')),
        isTrue,
      );
      // 副题走官方赛程（压到月），不是旧的「N 本」在库口径句。
      expect(find.textContaining('开赛 2025.05 · 截止 2025.10'), findsOneWidget);
    });

    testWidgets('列表：旧口径说明行删除，合计移到尾部', (tester) async {
      await pumpList(tester, [spring2025(), thirteen(), seven(), noRoster()]);
      expect(find.textContaining('计数 = 本地内置库'), findsNothing);

      await tester.tap(find.text('X征'));
      await tester.pumpAndSettle();
      expect(
        find.textContaining('本分类共 2 届 · 官方清单合计 12,147 条 · 本地在库 787 本'),
        findsOneWidget,
      );
    });

    testWidgets('列表：获奖事件官方列显未知，合计只点名不计入', (tester) async {
      await pumpList(tester, [oneZheng()]);
      await tester.tap(find.text('X征'));
      await tester.pumpAndSettle();
      // 获奖名额不是参赛总数（用户 2026-11-27 裁定）：官方列写「未知」，
      // 不把 5 个奖名额冒充 5 条清单。
      expect(find.text('未知'), findsOneWidget);
      expect(find.text('5'), findsNothing);
      expect(find.text('5 名'), findsNothing);
      expect(find.textContaining('1 届只有获奖名单，未计入'), findsOneWidget);
    });

    testWidgets('lane=short：短篇征文归档只显短篇线，标题正确', (tester) async {
      final shortContest = ContestGroup.fromJson({
        'name': '超新星杯短篇',
        'series': 'other',
        'lane': 'short',
        'count': 87,
        'forms': {'short': 87},
        'tracks': ['超新星杯短篇'],
        'year': 2024,
        'year_min': 2024,
        'year_max': 2024,
      });
      await pumpList(tester, [spring2025(), shortContest], lane: 'short');

      expect(find.text('短篇征文归档'), findsOneWidget);
      expect(find.text('超新星杯短篇'), findsOneWidget);
      // lane 视图忽略 series 过滤，且不混入非 short lane 的赛事。
      expect(find.text('2025春季征文'), findsNothing);
      expect(find.text('赛事档案'), findsNothing);
      // 跨系列筛选不显示系列 tab：否则从短篇入口进来顶部却选中「主题」
      // （用户 2026-11-27 报的 bug），对话/IP 入口同理。
      expect(find.text('春季'), findsNothing);
      expect(find.text('主题'), findsNothing);
    });

    testWidgets('档案：头部压成元信息 + 覆盖，赛程不再进详情', (tester) async {
      await pumpArchive(tester, thirteen(), books: twoBooks());

      // 年份 / 系列 / 在库形态压成一行，不再逐形态报数。
      expect(find.textContaining('2025 年 · X征'), findsOneWidget);
      expect(find.textContaining('长篇 / 中篇 / 短篇 / 对话'), findsOneWidget);
      expect(find.text('在库 335 · 覆盖 7.0%'), findsOneWidget);
      expect(find.text('参赛清单 4,797 →'), findsOneWidget);

      // 代表作按 form 分组；两本不同 form 时各有小标题。
      expect(find.text('代表作'), findsOneWidget);
      expect(find.text('长篇'), findsOneWidget);
      expect(find.text('短篇'), findsOneWidget);
      expect(find.text('魔王小姐请再忍耐一下'), findsOneWidget);
      expect(find.text('夺舍失败后'), findsOneWidget);

      // 赛程、官方清单条数、赛项行、覆盖率条、旧动作区全部退出详情页。
      expect(find.text('投稿开始'), findsNothing);
      expect(find.text('投稿截止'), findsNothing);
      expect(find.text('结果公布'), findsNothing);
      expect(find.textContaining('预计'), findsNothing);
      expect(find.text('官方清单'), findsNothing);
      expect(find.text('赛项'), findsNothing);
      expect(find.text('3,407'), findsNothing);
      expect(find.byType(LinearProgressIndicator), findsNothing);
      expect(find.text('浏览在库作品'), findsNothing);
      expect(find.text('浏览全部作品'), findsNothing);
    });

    testWidgets('档案：AppBar 只留奖杯/外链 icon，参赛清单入口不随代表作消失', (tester) async {
      await pumpArchive(tester, thirteen(), books: twoBooks());
      expect(find.byTooltip('获奖记录'), findsOneWidget);
      expect(find.byTooltip('官方活动页'), findsOneWidget);
      expect(find.byIcon(Icons.emoji_events), findsOneWidget);
      expect(find.byIcon(Icons.open_in_new), findsOneWidget);
      expect(find.text('参赛清单 4,797 →'), findsOneWidget);
      // 官方活动页 / 获奖作品不再占正文。
      expect(find.text('官方活动页'), findsNothing);
      expect(find.text('获奖作品'), findsNothing);

      final running = ContestGroup.fromJson({
        'name': '十四征',
        'series': 'x',
        'count': 0,
        'forms': <String, dynamic>{},
        'tracks': ['十四征-长篇'],
        'year_min': 2026,
        'year_max': 2026,
        'year': 2026,
        'start': '2026-05-01',
        'end': '2026-10-07',
        'result': '2030-01-15',
        'roster': true,
        'divisions': [
          {'name': '长篇', 'tag': 801, 'roster': 3583},
          {'name': '短篇', 'tag': 802, 'roster': 481},
        ],
        'roster_total': 4064,
      });
      await pumpArchive(tester, running);
      // 在库 0 本：不摆代表作，但参赛清单仍是唯一书目来源，入口保留。
      expect(find.text('在库 0 · 覆盖 0.0%'), findsOneWidget);
      expect(find.text('参赛清单 4,064 →'), findsOneWidget);
      expect(find.text('代表作'), findsNothing);

      await pumpArchive(tester, noRoster());
      expect(find.text('在库 125 · 无参赛清单接口'), findsOneWidget);
      expect(find.text('参赛清单 →'), findsNothing);
      expect(find.text('参赛清单 4,064 →'), findsNothing);
      expect(find.text('代表作'), findsNothing);
      expect(find.byTooltip('官方活动页'), findsNothing);
    });

    testWidgets('档案：award-only 只留奖杯 icon，不再铺获奖名额/名单', (tester) async {
      await pumpArchive(tester, oneZheng());
      expect(find.text('在库 2 · 官方只公布获奖名单'), findsOneWidget);
      expect(find.byTooltip('获奖记录'), findsOneWidget);
      expect(find.byIcon(Icons.emoji_events), findsOneWidget);
      expect(find.byTooltip('官方活动页'), findsNothing);

      // 获奖名单走 AppBar；正文不再有统计格、奖项行、获奖名单入口。
      expect(find.text('获奖名额'), findsNothing);
      expect(find.text('获奖名单'), findsNothing);
      expect(find.text('奖项'), findsNothing);
      expect(find.text('5'), findsNothing);
      expect(find.text('参赛清单'), findsNothing);
      expect(find.text('代表作'), findsNothing);
    });

    testWidgets('档案：获奖作品不进正文，只留 AppBar 奖杯入口', (tester) async {
      await pumpArchive(
        tester,
        thirteen(),
        books: twoBooks(),
        awards: [
          {
            'nid': 999001,
            'title': '已核实的金奖作品',
            'awards': ['金奖'],
            'contest': '十三征-长篇',
            'series': 'X征',
            'in_seed': true,
            'author': '测试作者',
            'favs': 1200,
            'est_year': 2025,
            'form': 'long',
          },
          {
            'nid': 999002,
            'title': '库外获奖作品',
            'awards': ['铜奖', '推荐奖'],
            'contest': '十三征-短篇',
            'series': 'X征',
            'in_seed': false,
          },
        ],
      );
      expect(find.byTooltip('获奖记录'), findsOneWidget);
      expect(find.byTooltip('官方活动页'), findsOneWidget);
      expect(find.text('获奖作品'), findsNothing);
      expect(find.text('已核实的金奖作品'), findsNothing);
      expect(find.text('库外获奖作品'), findsNothing);
      expect(find.text('铜奖·推荐奖'), findsNothing);
      expect(find.text('金奖'), findsNothing);
      expect(find.textContaining('contest-achieve'), findsNothing);
      expect(find.text('参赛清单 4,797 →'), findsOneWidget);
    });

    testWidgets('名单页：获奖事件标题与条数按获奖名单口径', (tester) async {
      await pumpRoster(tester, oneZheng());
      expect(find.text('获奖名单 · 一征'), findsOneWidget);
      // 金奖台账 1 条：写「获奖名单 1 条」，不写参赛清单。
      expect(find.text('获奖名单 1 条'), findsOneWidget);
      expect(find.textContaining('官方清单'), findsNothing);
    });
  });
}

/// 详情页用到的端点全部本地伪造：不碰引擎、不碰网络。
class _FakeApi extends StrataApi {
  final BookDetail _detail;
  final List<RankItem> _works;
  final List<ObservationRow> _obs;
  final List<RankItem> _related;

  _FakeApi(
    this._detail,
    this._works,
    this._obs, {
    List<RankItem> similar = const [],
  }) : _related = similar,
       super('http://127.0.0.1:1');

  @override
  Future<BookDetail> book(int nid) async => _detail;

  @override
  Future<List<ObservationRow>> observations(int nid) async => _obs;

  @override
  Future<List<WatchItem>> watchList() async => const [];

  @override
  Future<Set<int>> officialSaleSet() async => const {1001};

  @override
  Future<void> recordHistory(int nid) async {}

  @override
  Future<List<RankItem>> authorBooks({
    required String author,
    int limit = 20,
    int offset = 0,
    String order = 'newest',
  }) async => // 真端点按作者名精确匹配 seed：库外作者查不到任何行。
      author == '测试作者' ? _works : const [];

  @override
  Future<List<RankItem>> relatedBooks({
    required int nid,
    int limit = 8,
  }) async => // 真端点已排除锚点/同作者/跨 form。
      _related;
}

/// 赛事档案两端点伪造（列表 + 单届代表作）：页面其余继承 StrataApi，
/// 未覆写的端点一旦被误用会真去连 127.0.0.1:1 并抛错，测试即红。
class _FakeContestApi extends StrataApi {
  final List<ContestGroup> _groups;
  final List<Map<String, dynamic>> _books;
  final List<Map<String, dynamic>> _awards;
  final String rosterKind;
  final List<Map<String, dynamic>> rosterItems;

  _FakeContestApi(
    this._groups, {
    this._books = const [],
    this._awards = const [],
    this.rosterKind = '',
    this.rosterItems = const [],
  }) : super('http://127.0.0.1:1');

  @override
  Future<List<ContestGroup>> contestArchive() async => _groups;

  @override
  Future<ContestBooks> contestArchiveBooks({
    required String contest,
    int per = 10,
  }) async => ContestBooks.fromJson({'items': _books, 'awards': _awards});

  @override
  Future<RosterPage> roster({
    required String contest,
    String division = '',
    int page = 1,
    String scope = '',
  }) async => RosterPage.fromJson({
    'contest': contest,
    'division': division,
    'page': 1,
    'pages': 1,
    'source': 'official',
    'list_kind': rosterKind,
    'items': rosterItems,
  });
}
