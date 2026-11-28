import 'package:flutter_test/flutter_test.dart';
import 'package:strata/core/providers.dart';
import 'package:strata/data/api/strata_api.dart';
import 'package:strata/widgets/book_row_tile.dart';
import 'package:strata/widgets/default_cover.dart';

void main() {
  group('coverImageUrl（封面 URL 归一化）', () {
    test('null/空 → null（调用方回退默认封面）', () {
      expect(coverImageUrl(null), isNull);
      expect(coverImageUrl(''), isNull);
    });

    test('完整 http(s) URL 原样保留（观测封面）', () {
      const url =
          'https://rss.sfacg.com/web/novel/images/NovelCover/Big/2025/12/x.jpg';
      expect(coverImageUrl(url), url);
    });

    test('// 协议相对 → 补 https:（官方 app 观测值形态）', () {
      expect(
        coverImageUrl('//rss.sfacg.com/a.jpg'),
        'https://rss.sfacg.com/a.jpg',
      );
    });

    test('seed 相对路径 → 拼 CDN 前缀', () {
      expect(
        coverImageUrl('2025/12/xx.jpg'),
        'https://rss.sfacg.com/web/novel/images/NovelCover/Big/2025/12/xx.jpg',
      );
    });
  });

  group('coverImageUrl（封面 URL 归一化）', () {
    // 默认封面兜底 2026-11-26 改为纯本地占位（logo 水印 + 首字符），
    // 远程 default/defaultNew 兜底图退役；URL 归一化口径不变。
    test('空值归一化为 null（调用方回退本地占位）', () {
      expect(coverImageUrl(null), isNull);
      expect(coverImageUrl(''), isNull);
    });
  });

  group('contestIpLabel / contestChipLabel（征文 → IP 展示名）', () {
    test('2026-11-27 起完整显示我方统一命名，不再去后缀', () {
      expect(contestIpLabel('崩坏3同人'), '崩坏3同人');
      expect(contestIpLabel('失业魔王同人'), '失业魔王同人');
      expect(contestIpLabel('点鸭星穹'), '点鸭星穹');
      expect(contestIpLabel(null), isNull);
      expect(contestIpLabel(''), isNull);
    });

    test('chip 标签完整显示赛事名', () {
      expect(contestChipLabel('超新星杯短篇'), '超新星杯短篇');
      expect(contestChipLabel('四征长篇'), '四征长篇');
      expect(contestChipLabel('2025春征'), '2025春征');
    });
  });

  group('BookRowTile.wan（指标数格式化）', () {
    test('万字换算与整数直通', () {
      expect(BookRowTile.wan(null), '');
      expect(BookRowTile.wan(9999), '9999');
      expect(BookRowTile.wan(10000), '1.0万');
      expect(BookRowTile.wan(26917), '2.7万');
      expect(BookRowTile.wan(123456), '12.3万');
    });
  });

  group('RankItem.fromJson（引擎 JSON 契约）', () {
    test('全字段解析', () {
      final it = RankItem.fromJson({
        'rank': 1,
        'nid': 1001,
        'title': '甲',
        'author': 'A',
        'genre': '魔幻',
        'est_year': 2020,
        'favs': 123,
        'contest': '崩坏3征文',
        'cover_url': '2020/1/x.jpg',
        'status': '连载中',
        'words': 120000,
        'clicks': 9000,
        'praises': 55,
        'form': 'long',
        'tags': ['标签A', '标签B'],
      });
      expect(it.nid, 1001);
      expect(it.coverUrl, '2020/1/x.jpg');
      expect(it.tags, ['标签A', '标签B']);
      expect(it.contest, '崩坏3征文');
    });

    test('可选字段缺失时兜底', () {
      final it = RankItem.fromJson({
        'rank': 2,
        'nid': 1002,
        'title': '乙',
        'author': 'B',
        'est_year': 2019,
        'favs': 1,
        'form': 'short',
      });
      expect(it.genre, isNull);
      expect(it.words, isNull);
      expect(it.praises, isNull);
      expect(it.tags, isEmpty);
    });
  });

  group('carousel form（首页轮播形态映射）', () {
    test('短篇沿用 IP 的固定 featured 池', () {
      expect(carouselFormFor('short'), 'ip_collab');
      expect(carouselIsFixed('short'), isTrue);
    });

    test('中篇/IP 固定，长篇/对话仍按日洗牌', () {
      expect(carouselIsFixed('medium'), isTrue);
      expect(carouselIsFixed('ip_collab'), isTrue);
      expect(carouselIsFixed('long'), isFalse);
      expect(carouselIsFixed('dialogue'), isFalse);
    });
  });
}
