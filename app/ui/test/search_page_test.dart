import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:strata/core/providers.dart';
import 'package:strata/data/api/strata_api.dart';
import 'package:strata/pages/search_page.dart';

/// 只提供搜索页依赖的两个端点；其他端点误用会真连 127.0.0.1:1 抛错。
class _FakeSearchApi extends StrataApi {
  _FakeSearchApi() : super('http://127.0.0.1:1');

  @override
  Future<List<SearchItem>> search(String q, {int limit = 50}) async => [
        SearchItem.fromJson({
          'nid': 1001,
          'title': '秋米测试作品',
          'author': '秋米',
          'est_year': 2020,
          'favs': 247,
        }),
      ];

  @override
  Future<List<String>> searchHistory({int limit = 10}) async => const [];
}

void main() {
  testWidgets('搜索结果：普通词命中本地结果时，全站行索引不越界', (tester) async {
    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          bootProvider.overrideWith((ref) async => EngineHandle(
                api: _FakeSearchApi(),
                seedVersion: 'test',
                bookCount: 1,
              )),
        ],
        child: const MaterialApp(home: SearchPage()),
      ),
    );
    await tester.pumpAndSettle();
    await tester.enterText(find.byType(TextField), '秋米');
    await tester.testTextInput.receiveAction(TextInputAction.search);
    await tester.pumpAndSettle();

    expect(tester.takeException(), isNull);
    expect(find.text('秋米测试作品'), findsOneWidget);
    expect(find.text('搜全站（官方，最多 30 条）'), findsOneWidget);
  });
}
