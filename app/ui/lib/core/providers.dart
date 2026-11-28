import 'dart:io';

import 'package:connectivity_plus/connectivity_plus.dart';
import 'package:flutter/material.dart' show ThemeMode;
import 'package:flutter/services.dart' show rootBundle;
import 'package:flutter_riverpod/flutter_riverpod.dart';
// Riverpod 3 moved StateProvider to the legacy namespace.
import 'package:flutter_riverpod/legacy.dart';
import 'package:path_provider/path_provider.dart';

import '../data/api/strata_api.dart';
import 'ffi/engine_ffi.dart';

/// Live network paths (connectivity_plus). Empty list or all-`none` =
/// offline; seed browsing keeps working, upstream-proxying endpoints do not.
final connectivityProvider = StreamProvider<List<ConnectivityResult>>((
  ref,
) async* {
  final connectivity = Connectivity();
  yield await connectivity.checkConnectivity();
  yield* connectivity.onConnectivityChanged;
});

/// True when at least one network path is active.
bool isOnline(List<ConnectivityResult> results) =>
    results.any((r) => r != ConnectivityResult.none);

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

  final result = await startAndWaitHealthy(
    EngineFfi(),
    assetsDir,
    dataDir.path,
  );
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

/// 短篇没有自己的 featured 池，轮播沿用 IP 的固定池。
String carouselFormFor(String form) => form == 'short' ? 'ip_collab' : form;

/// 中篇/IP 的 featured 池很小（含授权书也常不足 6 本），固定收藏序、
/// 不做每日随机；长篇/对话仍用日期种子在各自形态内洗牌。
bool carouselIsFixed(String form) {
  final carouselForm = carouselFormFor(form);
  return carouselForm == 'medium' || carouselForm == 'ip_collab';
}

/// 测试种子日期覆盖（YYYYMMDD 字符串；null = 跟随今天）。设置页
/// 「测试种子日期」选择器写入——用于人工验证轮播/大图精选的按日
/// 轮换逻辑（用户裁定 2026-11-26）。
final seedDateOverrideProvider = StateProvider<String?>((ref) => null);

/// 本地日期键（YYYYMMDD）：轮播随机种子的来源。必须放进 family 键——
/// 常驻 family 的 `DateTime.now()` 只在进程首次求值时捕获一次，进程活过
/// 午夜就永远停在昨天的抽签上（2026-11-23 用户报告的回归）。
/// 设置页可用 seedDateOverrideProvider 覆盖（测试用）。
String carouselDayKey(WidgetRef ref) {
  final override = ref.watch(seedDateOverrideProvider);
  if (override != null && override.isNotEmpty) return override;
  final now = DateTime.now();
  return '${now.year * 10000 + now.month * 100 + now.day}';
}

/// 轮播 provider 的 family 键：form + 当日日期键，新的一天产生新键。
String carouselProviderKey(WidgetRef ref, String form) =>
    '$form@${carouselDayKey(ref)}';

final bannerProvider = FutureProvider.autoDispose
    .family<List<FeaturedItem>, String>((ref, formDay) async {
      final at = formDay.indexOf('@');
      final form = formDay.substring(0, at);
      final dayKey = formDay.substring(at + 1);
      final handle = await ref.watch(bootProvider.future);
      final carouselForm = carouselFormFor(form);
      if (carouselIsFixed(form)) {
        return handle.api.featured(
          limit: bannerCarouselCount,
          form: carouselForm,
        );
      }
      final seed = int.parse(dayKey);
      return handle.api.banners(
        seed: seed,
        limit: bannerCarouselCount,
        form: carouselForm,
      );
    });

const bannerCarouselCount = 6;
const largeImageCount = 6;

/// 对话/短篇 tab 轮播：该 form 有封面书的收藏 Top-100 头部池，按日期
/// 种子每日轮换（与长篇 banner 同款哈希）。没有 featured 定制图的形态
/// 端上用封面实时合成纸墨 banner（重纸纱 + 衬线书名 + 指标行），见
/// widgets/cover_banner.dart。按 form 分池。
final coverCarouselProvider = FutureProvider.autoDispose
    .family<List<RankItem>, String>((ref, formDay) async {
      final at = formDay.indexOf('@');
      final form = formDay.substring(0, at);
      final dayKey = formDay.substring(at + 1);
      final handle = await ref.watch(bootProvider.future);
      final seed = int.parse(dayKey);
      return handle.api.coverCarousel(
        seed: seed,
        form: form,
        limit: bannerCarouselCount,
      );
    });

/// 发书日历查询参数（family 键）：粒度 + 锚点日 + 每格条目上限。
class CalendarQuery {
  final String granularity; // day|week|month
  final String anchor; // YYYY-MM-DD
  final int perCell;

  const CalendarQuery({
    required this.granularity,
    required this.anchor,
    this.perCell = 3,
  });

  @override
  bool operator ==(Object other) =>
      other is CalendarQuery &&
      other.granularity == granularity &&
      other.anchor == anchor &&
      other.perCell == perCell;

  @override
  int get hashCode => Object.hash(granularity, anchor, perCell);
}

/// 发书日历（docs/14 P1）：seed 书按 est_date 聚合成日期格。
/// month 视图只有 total；day/week 另带 per_cell 条收藏序条目。
final calendarProvider = FutureProvider.family<CalendarResponse, CalendarQuery>(
  (ref, q) async {
    final handle = await ref.watch(bootProvider.future);
    return handle.api.calendar(
      granularity: q.granularity,
      anchor: q.anchor,
      perCell: q.perCell,
    );
  },
);

/// 每周签约升 VIP 推荐（官方活动名"每周上架推荐"）：key = 周六期数 YYYYMMDD。在线层，
/// 引擎侧 24h 期次缓存；失败可重试，不影响月/周/日的种子视图。
final preorderProvider = FutureProvider.family<PreorderResponse, String>((
  ref,
  date,
) async {
  final handle = await ref.watch(bootProvider.future);
  return handle.api.preorder(date: date);
});

/// VIP 上架专题（vipPush H5 直出页，docs/sfacg-endpoints.md §7.6）：与预约层
/// 同一周六期次、不同数据线；引擎 24h 期次缓存，失败可重试不影响月/周/日。
final vipPushProvider = FutureProvider.family<VipPushResponse, String>((
  ref,
  date,
) async {
  final handle = await ref.watch(bootProvider.future);
  return handle.api.vipPush(date: date);
});

/// IP tab 分组网格：ip_collab 池按征文（contest）聚合（count DESC），
/// 端上展示全部组，每组带收藏最高一本的 top_* 做封面卡片。
final ipGroupsProvider = FutureProvider<IpGroupsResult>((ref) async {
  final handle = await ref.watch(bootProvider.future);
  return handle.api.ipGroups(form: 'ip_collab');
});

/// 首页书单推荐行（docs/booklist-in-app.md §深化）：引擎按 UTC 日期种子
/// 随机抽 3 个官方书单（当日稳定、24h 缓存）。增益区块：加载失败/空
/// 结果整行隐藏，不阻塞首页（home 端 valueOrNull 为空不渲染）。
final booklistRecommendProvider = FutureProvider<List<Booklist>>((ref) async {
  final handle = await ref.watch(bootProvider.future);
  return handle.api.booklistRecommend();
});

/// 赛道聚合（contest，count DESC）by form：榜单页轴切换的数据源
/// （短篇比赛榜 Drawer，form 可复用于其他形态）。
/// 与列表同源（不按 status 过滤，见 docs/form-definitions §4）。
final contestGroupsProvider = FutureProvider.family<IpGroupsResult, String>((
  ref,
  form,
) async {
  final handle = await ref.watch(bootProvider.future);
  return handle.api.ipGroups(form: form);
});

/// 赛事档案列表（docs/contest-display-in-app.md 形态一）：seed 内置库按
/// 赛事聚合 + 引擎内嵌官方日期（用户核实）。零请求。
final contestArchiveProvider = FutureProvider<List<ContestGroup>>((ref) async {
  final handle = await ref.watch(bootProvider.future);
  return handle.api.contestArchive();
});

/// 一届赛事的代表作（per-form 窗口，同代收藏分位序）+ 该届库内获奖作品
/// （schema v5；奖项字段不参与排序，docs/contest-display-in-app.md §6）。
final contestArchiveBooksProvider = FutureProvider.family<ContestBooks, String>(
  (ref, contest) async {
    final handle = await ref.watch(bootProvider.future);
    return handle.api.contestArchiveBooks(contest: contest);
  },
);

/// 筛选 facet（经典榜单筛选面板）：form 池的状态外五维度值列表
/// （状态为固定枚举，不在 facet 里）。
final facetsProvider = FutureProvider.family<FacetsResult, String>((
  ref,
  form,
) async {
  final handle = await ref.watch(bootProvider.future);
  return handle.api.facets(form: form);
});

/// 年份聚合（est_year DESC）by form：经典榜单页顶部年份轴横向条。
final yearGroupsProvider = FutureProvider.family<YearGroupsResult, String>((
  ref,
  form,
) async {
  final handle = await ref.watch(bootProvider.future);
  return handle.api.yearGroups(form: form);
});

/// 题材聚合（count DESC）by form：榜单页题材 chip / 中篇 tab 题材行。
final genreGroupsProvider = FutureProvider.family<GenreGroupsResult, String>((
  ref,
  form,
) async {
  final handle = await ref.watch(bootProvider.future);
  return handle.api.genreGroups(form: form);
});

/// 大图精选：全形态 featured 池的每日后段（文字在图下方，点图全屏查看）。
/// 不受首页形态 tab 影响，也不与形态轮播共用池子。
/// 键必须含日期（与轮播 carouselProviderKey 同款）：常驻 provider 的
/// DateTime.now() 只在进程首次求值时捕获一次，进程活过午夜就永远停在
/// 旧种子上（2026-11-26 用户报告的多天不更新回归；2026-11-23 轮播同款）。
final largeImageProvider = FutureProvider.autoDispose
    .family<List<FeaturedItem>, String>((ref, dayKey) async {
      final handle = await ref.watch(bootProvider.future);
      final seed = int.parse(dayKey);
      return handle.api.banners(
        seed: seed,
        limit: largeImageCount,
        offset: bannerCarouselCount,
      );
    });

/// 图片全屏查看器的当前图集（首页大图精选打开查看器前写入）。
final imageViewerProvider = StateProvider<List<FeaturedItem>>(
  (ref) => const [],
);

/// 外观主题：默认跟随系统（设置页可切浅色/深色）。
final themeModeProvider = StateProvider<ThemeMode>((ref) => ThemeMode.system);

typedef YearGenre = ({int year, String? genre});

/// 分位榜（可选题材过滤）。
final favsRankingProvider = FutureProvider.family<List<RankItem>, YearGenre>((
  ref,
  arg,
) async {
  final handle = await ref.watch(bootProvider.future);
  return handle.api.rankingFavs(year: arg.year, genre: arg.genre);
});

/// 题材榜：分位榜 + genre 必选，二者共用同一端点。
final shortRankingProvider = FutureProvider<List<ShortItem>>((ref) async {
  final handle = await ref.watch(bootProvider.future);
  return handle.api.rankingShort();
});

final newRankingProvider = FutureProvider<List<RankItem>>((ref) async {
  final handle = await ref.watch(bootProvider.future);
  return handle.api.rankingNew();
});

final searchProvider = FutureProvider.family<List<SearchItem>, String>((
  ref,
  q,
) async {
  final handle = await ref.watch(bootProvider.future);
  return handle.api.search(q);
});

/// 最近本地搜索关键词（搜索页空态 chips；每次提交后 invalidate）。
final searchHistoryProvider = FutureProvider<List<String>>((ref) async {
  final handle = await ref.watch(bootProvider.future);
  return handle.api.searchHistory();
});

/// 关注列表（watchlist JOIN seed.books）。所有 watchAdd / watchRemove /
/// watchSetActive 成功后 invalidate，保证常驻 IndexedStack 的关注 tab 在
/// 从详情页返回时立即刷新（页面 initState 只跑一次，不能只靠 _load）。
final watchlistProvider = FutureProvider<List<WatchItem>>((ref) async {
  final handle = await ref.watch(bootProvider.future);
  return handle.api.watchList();
});

/// 关注通知未读数：关注页 AppBar 角标与系统本地通知都读它。
final notificationsProvider =
    FutureProvider.autoDispose<Map<String, dynamic>>((ref) async {
  final handle = await ref.watch(bootProvider.future);
  return handle.api.notifications();
});

final bookProvider = FutureProvider.family<BookDetail, int>((ref, nid) async {
  final handle = await ref.watch(bootProvider.future);
  return handle.api.book(nid);
});

/// 详情刷新限流开关的数据源：引擎 /settings。settings 页用它渲染开关，
/// 详情页监听它——限流开关变化后解除刷新按钮的限额禁用。
final detailRateLimitProvider =
    FutureProvider.autoDispose<EngineSettings>((ref) async {
  final handle = await ref.watch(bootProvider.future);
  return handle.api.settings();
});

/// v12 用户分组（watch_lists）：分组 chips 与移动/建组对话框共用。
final watchGroupsProvider =
    FutureProvider.autoDispose<List<WatchGroup>>((ref) async {
  final handle = await ref.watch(bootProvider.future);
  return handle.api.watchGroups();
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
