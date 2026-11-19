import 'dart:async';
import 'dart:io';
import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:strata/data/api/strata_api.dart';
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
        .listen(onData,
            onError: onError, onDone: onDone, cancelOnError: cancelOnError);
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
}
