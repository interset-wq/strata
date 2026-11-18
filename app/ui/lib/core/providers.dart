import 'dart:io';

import 'package:flutter/material.dart' show ThemeMode;
import 'package:flutter/services.dart' show rootBundle;
import 'package:flutter_riverpod/flutter_riverpod.dart';
// Riverpod 3 moved StateProvider to the legacy namespace.
import 'package:flutter_riverpod/legacy.dart';
import 'package:path_provider/path_provider.dart';

import '../data/api/strata_api.dart';
import 'ffi/engine_ffi.dart';

/// Thrown when the embedded engine cannot be started. The message is shown
/// verbatim on the failure page (contract: no infinite retries).
class EngineBootException implements Exception {
  final String message;
  EngineBootException(this.message);

  @override
  String toString() => message;
}

class EngineHandle {
  final StrataApi api;
  final String seedVersion;
  final int bookCount;

  EngineHandle({
    required this.api,
    required this.seedVersion,
    required this.bookCount,
  });
}

/// Boots the Go engine and returns a ready-to-use API client.
/// Invalidate to retry; this future either completes with a healthy
/// engine or throws a diagnostic message.
final bootProvider = FutureProvider<EngineHandle>((ref) async {
  final docs = await getApplicationDocumentsDirectory();
  final assetsDir = await _extractAssets('${docs.path}/assets');
  final dataDir = Directory('${docs.path}/data');
  await dataDir.create(recursive: true);

  final result =
      await startAndWaitHealthy(EngineFfi(), assetsDir, dataDir.path);
  if (!result.ok) {
    throw EngineBootException(result.error ?? 'engine failed to start');
  }
  return EngineHandle(
    api: StrataApi(result.addr!),
    seedVersion: result.seedVersion ?? '?',
    bookCount: result.bookCount ?? 0,
  );
});

/// /strata/meta, used by the home page.
final metaProvider = FutureProvider<Meta>((ref) async {
  final handle = await ref.watch(bootProvider.future);
  return handle.api.meta();
});

/// 每日 banner：以当天日期为随机种子，对整个 banner 池（含 is_licensed）
/// 等概率抽取——同一天稳定、隔天必变、池内每个 banner 都可能被抽中。
final bannerProvider = FutureProvider<List<FeaturedItem>>((ref) async {
  final handle = await ref.watch(bootProvider.future);
  final now = DateTime.now();
  final seed = now.year * 10000 + now.month * 100 + now.day;
  return handle.api.banners(seed: seed, limit: bannerCarouselCount);
});

/// 轮播与大图精选共用的每日种子：同一天对 featured 全池做一次
/// 确定性洗牌，轮播取前 [bannerCarouselCount] 张（offset 0），
/// 大图精选紧随其后取 6 张（offset = bannerCarouselCount），
/// 两段天然不重复，同日稳定、隔天都变。
const bannerCarouselCount = 6;
const largeImageCount = 6;

/// 大图精选：与每日轮播同种子的后段（文字在图下方，点图全屏查看）。
final largeImageProvider = FutureProvider<List<FeaturedItem>>((ref) async {
  final handle = await ref.watch(bootProvider.future);
  final now = DateTime.now();
  final seed = now.year * 10000 + now.month * 100 + now.day;
  return handle.api.banners(
      seed: seed, limit: largeImageCount, offset: bannerCarouselCount);
});

/// 图片全屏查看器的当前图集（首页大图精选打开查看器前写入）。
final imageViewerProvider = StateProvider<List<FeaturedItem>>((ref) => const []);

/// 书架（“想读”，首页“继续浏览”数据源）。
final shelfProvider = FutureProvider<List<ShelfItem>>((ref) async {
  final handle = await ref.watch(bootProvider.future);
  return handle.api.shelfList();
});

/// 外观主题：默认跟随系统（设置页可切浅色/深色）。
final themeModeProvider = StateProvider<ThemeMode>((ref) => ThemeMode.system);

typedef YearGenre = ({int year, String? genre});

/// 分位榜（可选题材过滤）。
final favsRankingProvider =
    FutureProvider.family<List<RankItem>, YearGenre>((ref, arg) async {
  final handle = await ref.watch(bootProvider.future);
  return handle.api.rankingFavs(year: arg.year, genre: arg.genre);
});

/// 题材榜：分位榜 + genre 必选，二者共用同一端点。
final shortRankingProvider =
    FutureProvider<List<ShortItem>>((ref) async {
  final handle = await ref.watch(bootProvider.future);
  return handle.api.rankingShort();
});

final newRankingProvider = FutureProvider<List<RankItem>>((ref) async {
  final handle = await ref.watch(bootProvider.future);
  return handle.api.rankingNew();
});

final searchProvider =
    FutureProvider.family<List<SearchItem>, String>((ref, q) async {
  final handle = await ref.watch(bootProvider.future);
  return handle.api.search(q);
});

final bookProvider = FutureProvider.family<BookDetail, int>((ref, nid) async {
  final handle = await ref.watch(bootProvider.future);
  return handle.api.book(nid);
});

Future<String> _extractAssets(String dirPath) async {
  final dir = Directory(dirPath);
  await dir.create(recursive: true);
  for (final name in ['manifest.json', 'seed.db.gz']) {
    final f = File('${dir.path}/$name');
    final data = await rootBundle.load('assets/$name');
    await f.writeAsBytes(data.buffer.asUint8List(), flush: true);
  }
  return dirPath;
}
