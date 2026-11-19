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

/// 首页轮播：中篇/IP 的 featured 池很小（含授权书也常不足 6 本），固定按
/// 收藏展示、不做每日随机；短篇自身没有 featured，沿用 IP 的固定轮播。
/// 长篇/对话仍用日期种子在各自形态内洗牌。
final bannerProvider = FutureProvider.autoDispose
    .family<List<FeaturedItem>, String>((ref, form) async {
  final handle = await ref.watch(bootProvider.future);
  final carouselForm = form == 'short' ? 'ip_collab' : form;
  if (carouselForm == 'medium' || carouselForm == 'ip_collab') {
    return handle.api
        .featured(limit: bannerCarouselCount, form: carouselForm);
  }
  final now = DateTime.now();
  final seed = now.year * 10000 + now.month * 100 + now.day;
  return handle.api.banners(
      seed: seed, limit: bannerCarouselCount, form: carouselForm);
});

const bannerCarouselCount = 6;
const largeImageCount = 6;

/// 对话 tab 轮播：dialogue 池中有封面的书（收藏降序固定序，不随日期变）。
/// dialogue 形态没有 featured 定制图，端上用封面实时合成纸墨 banner
/// （重纸纱 + 衬线书名 + 指标行），见 widgets/cover_banner.dart。
final dialogueCarouselProvider = FutureProvider<List<RankItem>>((ref) async {
  final handle = await ref.watch(bootProvider.future);
  return handle.api.coverCarousel(limit: bannerCarouselCount);
});

/// 大图精选：全形态 featured 池的每日后段（文字在图下方，点图全屏查看）。
/// 不受首页形态 tab 影响，也不与形态轮播共用池子。
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
