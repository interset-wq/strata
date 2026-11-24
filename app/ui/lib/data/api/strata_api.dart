import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:connectivity_plus/connectivity_plus.dart';

/// HTTP client for the embedded Go engine.
/// Contract: app/docs/08-engine-api.md.
class StrataApi {
  final HttpClient _client = HttpClient();
  final String base; // e.g. http://127.0.0.1:45851

  // Offline pre-check for endpoints that proxy upstream fetches
  // (search/remote, official-ranks/*, refresh, author-*): without it a
  // device-side fetch hangs with no route, and the UI spinner never ends.
  Connectivity? _connectivity;
  DateTime _lastOnlineCheck = DateTime.fromMillisecondsSinceEpoch(0);
  bool _cachedOnline = true;

  StrataApi(this.base);

  /// Currently online (5s-cached local check; engine's localhost is always
  /// reachable, so this only guards upstream-proxying endpoints).
  Future<bool> isOnline() async {
    final now = DateTime.now();
    if (now.difference(_lastOnlineCheck) < const Duration(seconds: 5) &&
        _connectivity != null) {
      return _cachedOnline;
    }
    _connectivity ??= Connectivity();
    final results = await _connectivity!.checkConnectivity();
    _cachedOnline = results.any((r) => r != ConnectivityResult.none);
    _lastOnlineCheck = now;
    return _cachedOnline;
  }

  Uri _uri(String path, [Map<String, String>? query]) =>
      Uri.parse('$base/strata$path').replace(queryParameters: query);

  Future<void> _ensureOnline({required bool internet}) async {
    if (!internet) return;
    if (!await isOnline()) {
      throw StrataApiException(
          status: 0, code: 'offline', message: '当前离线，请检查网络连接');
    }
  }

  Future<dynamic> _get(
    String path, [
    Map<String, String>? query,
    bool internet = false,
  ]) async {
    await _ensureOnline(internet: internet);
    final req = await _client.getUrl(_uri(path, query));
    final resp = await req.close();
    final body = await resp.transform(utf8.decoder).join();
    if (resp.statusCode != 200) {
      String code = 'internal';
      String message = body;
      try {
        final err = (jsonDecode(body) as Map<String, dynamic>)['error'];
        code = err['code'] as String? ?? code;
        message = err['message'] as String? ?? message;
      } catch (_) {
        // non-JSON error body; keep raw text
      }
      throw StrataApiException(
        status: resp.statusCode,
        code: code,
        message: message,
      );
    }
    return jsonDecode(body);
  }

  /// 官方在线数据 UI 侧最后兜底（2026-11-23 真机转圈报告）：引擎已有
  /// 逐请求 15s / 窗口 30s deadline，这里保证用户可见的"转圈"必然有
  /// 尽头；超时转友好文案，页面进错误态 + 重试。
  Future<dynamic> _getOnline(String path, [Map<String, String>? query]) async {
    try {
      return await _get(path, query).timeout(const Duration(seconds: 45));
    } on TimeoutException {
      throw StrataApiException(
          status: 0,
          code: 'timeout',
          message: '官方数据加载超时，请检查网络后重试');
    }
  }

  Future<Healthz> healthz() async =>
      Healthz.fromJson(await _get('/healthz') as Map<String, dynamic>);

  Future<Meta> meta() async =>
      Meta.fromJson(await _get('/meta') as Map<String, dynamic>);

  Future<EngineSettings> settings() async =>
      EngineSettings.fromJson(await _get('/settings') as Map<String, dynamic>);

  Future<EngineSettings> setDetailRateLimitEnabled(bool enabled) async =>
      EngineSettings.fromJson(
        await _putBody('/settings', {'detail_rate_limit_enabled': enabled})
            as Map<String, dynamic>,
      );

  Future<EngineSettings> setAppAPIEnabled(bool enabled) async =>
      EngineSettings.fromJson(
        await _putBody('/settings', {'app_api_enabled': enabled})
            as Map<String, dynamic>,
      );

  /// 篇幅偏好 K 档位落盘（user.db prefs）：切换即写，重启保持。
  Future<EngineSettings> setDiscoverK(String k) async =>
      EngineSettings.fromJson(
        await _putBody('/settings', {'discover_k': k}) as Map<String, dynamic>,
      );

  /// 本地数据导出（observations/watchlist/browsing_history 全量 dump）：
  /// v1 无云同步，设置页「导出数据」用它生成交付 JSON。
  Future<Map<String, dynamic>> exportData() async =>
      (await _get('/export') as Map<String, dynamic>);

  /// 工作台虚构测试书（docs/07 开发辅助，设置页测试开关）：状态读取。
  Future<TestBook> testBook() async =>
      TestBook.fromJson(await _get('/dev/test-book') as Map<String, dynamic>);

  /// 注入虚构测试书：60 天模拟观测 + 详情 overlay + 关注条目（不追踪）。
  Future<TestBook> injectTestBook({int days = 60}) async =>
      TestBook.fromJson(
          await _post('/dev/test-book?days=$days') as Map<String, dynamic>);

  /// 移除虚构测试书（overlay / 收录 / 关注 / 观测一并清理）。
  Future<void> removeTestBook() => _delete('/dev/test-book');

  Future<BookDetail> book(int nid) async =>
      BookDetail.fromJson(await _get('/books/$nid') as Map<String, dynamic>);

  Future<List<RankItem>> rankingFavs({
    required int year,
    String? genre,
    String? status,
    String? contest,
    int limit = 50,
  }) async {
    final body = await _get('/rankings/favs', {
      'year': '$year',
      'limit': '$limit',
      'genre': ?genre,
      'status': ?status,
      'contest': ?contest,
    });
    return (body['items'] as List)
        .map((e) => RankItem.fromJson(e as Map<String, dynamic>))
        .toList();
  }

  Future<List<RankItem>> rankingBoard({
    required String kind,
    String? form,
    int year = 0,
    int limit = 50,
    int offset = 0,
  }) async {
    final body = await _get('/rankings/board', {
      'kind': kind,
      'limit': '$limit',
      'form': ?form,
      if (year > 0) 'year': '$year',
      if (offset > 0) 'offset': '$offset',
    });
    return (body['items'] as List)
        .map((e) => RankItem.fromJson(e as Map<String, dynamic>))
        .toList();
  }

  // --- 官方榜单（demo 页；docs/sfacg-live-ranks.md 三来源） ---

  /// 历史月榜库（MonthlyBoy.ashx，2013-03 起任意月份）；rank: 0 月票/2 新书/3 热销/4 对话月票。
  Future<List<OfficialRankEntry>> officialRanksMonthly({
    required String month,
    int rank = 0,
  }) async {
    final body = await _get('/official-ranks/monthly',
        {'date': month, 'rank': '$rank'}, true);
    return (body['items'] as List)
        .map((e) => OfficialRankEntry.fromJson(e as Map<String, dynamic>))
        .toList();
  }

  /// PC 当期四榜（book.sfacg.com/Rank/）：月票带票数、打赏/热销无数值、粉丝榜读者侧。
  Future<List<OfficialPcBoard>> officialRanksPc() async {
    final body = await _get('/official-ranks/pc', null, true);
    return (body['boards'] as List)
        .map((e) => OfficialPcBoard.fromJson(e as Map<String, dynamic>))
        .toList();
  }

  /// 移动五榜之一（m.sfacg.com/rank/{slug}.html）；slug: original/bm/new/jp/sale。
  Future<List<OfficialRankEntry>> officialRanksMobile({
    required String slug,
  }) async {
    final body = await _get('/official-ranks/mobile', {'board': slug}, true);
    return (body['items'] as List)
        .map((e) => OfficialRankEntry.fromJson(e as Map<String, dynamic>))
        .toList();
  }

  /// 官方热销信号（docs/sfacg-live-ranks.md）：当前在已缓存官方热销榜上
  /// （月榜库当期 rank=3 ∪ PC 月度热销 ∪ 移动热销）的 nid 集合。
  /// 引擎侧从不为它发起抓取——未缓存/离线时返回空集，静默降级。
  Future<Set<int>> officialSaleSet() async {
    final body = await _get('/official-ranks/sale-set') as Map<String, dynamic>;
    final nids = (body['nids'] as List? ?? const []);
    return nids.map((e) => (e as num).toInt()).toSet();
  }

  /// Classic category/status/contest list: absolute favs order by default,
  /// or same-generation favorite percentile (order='pct', 优质短篇口径).
  Future<List<RankItem>> rankingClassic({
    String? genre,
    String? status,
    String? contest,
    String? form,
    String? wordsBand,
    int? year,
    String? tag,
    String? ptype,
    String? order,
    String? dir,
    int limit = 50,
    int offset = 0,
  }) async {
    final body = await _get('/rankings/classic', {
      'limit': '$limit',
      'genre': ?genre,
      'status': ?status,
      'contest': ?contest,
      'form': ?form,
      'words-band': ?wordsBand,
      if (year != null) 'year': '$year',
      'tag': ?tag,
      'ptype': ?ptype,
      'order': ?order,
      'dir': ?dir,
      if (offset > 0) 'offset': '$offset',
    });
    return (body['items'] as List)
        .map((e) => RankItem.fromJson(e as Map<String, dynamic>))
        .toList();
  }

  Future<DiscoverPage> discover({
    String? cursor,
    String? form,
    int limit = 20,
  }) async {
    final body = await _get('/discover', {
      'limit': '$limit',
      'form': ?form,
      if (cursor != null && cursor.isNotEmpty) 'cursor': cursor,
    });
    return DiscoverPage.fromJson(body as Map<String, dynamic>);
  }

  /// 量化推荐流（docs/12 §3、app/docs/18-runtime-metrics.md）：form 内 cqs
  /// 排序（长篇/对话/中篇；cps 中层带筛选），k 为篇幅偏好权重（0=纯 cqs，
  /// >0 运行时 clx 重排），游标分页。响应形状与 discover 同构，复用同一模型。
  Future<DiscoverPage> recommend({
    String? cursor,
    String? form,
    int limit = 20,
    double k = 0,
  }) async {
    final body = await _get('/recommend', {
      'limit': '$limit',
      'form': ?form,
      if (cursor != null && cursor.isNotEmpty) 'cursor': cursor,
      if (k > 0) 'k': '$k',
    });
    return DiscoverPage.fromJson(body as Map<String, dynamic>);
  }

  Future<HistoryData> history({int limit = 50}) async {
    final body = await _get('/history', {'limit': '$limit'});
    return HistoryData.fromJson(body as Map<String, dynamic>);
  }

  Future<void> recordHistory(int nid) async {
    await _post('/history/$nid');
  }

  /// 关注书观测的按日聚合（docs/07 §4 热力图）：day = epoch 天。
  Future<List<HeatmapDay>> watchHeatmap({int days = 90}) async {
    final body =
        await _get('/watchlist/heatmap', {'days': '$days'}) as Map<String, dynamic>;
    return (body['cells'] as List)
        .map((c) => HeatmapDay.fromJson(c as Map<String, dynamic>))
        .toList();
  }

  /// 世代探索（est_year × genre 离线聚合，纯种子数据）。
  Future<List<ErasExploreRow>> erasExplorer() async {
    final body = await _get('/eras-explorer') as Map<String, dynamic>;
    return (body['rows'] as List)
        .map((r) => ErasExploreRow.fromJson(r as Map<String, dynamic>))
        .toList();
  }

  Future<List<ShortItem>> rankingShort({int limit = 50}) async {
    final body = await _get('/rankings/short', {'limit': '$limit'});
    return (body['items'] as List)
        .map((e) => ShortItem.fromJson(e as Map<String, dynamic>))
        .toList();
  }

  Future<List<RankItem>> rankingNew({int limit = 50}) async {
    final body = await _get('/rankings/new', {'limit': '$limit'});
    return (body['items'] as List)
        .map((e) => RankItem.fromJson(e as Map<String, dynamic>))
        .toList();
  }

  Future<List<SearchItem>> search(String q, {int limit = 50}) async {
    final body = await _get('/search', {'q': q, 'limit': '$limit'});
    return (body['items'] as List)
        .map((e) => SearchItem.fromJson(e as Map<String, dynamic>))
        .toList();
  }

  /// Triggers a mobile-page detail fetch (sync; global limiter serializes).
  /// state: alive | dead | zombie; written: observation appended.
  /// 榜单预写（docs/08 §rank-seed）：点榜单行时先把该行 title/author/
  /// 封面/题材写入 user.db book_meta（source=rank，只填空字段），
  /// 库外书详情页首帧即可渲染，完整数据由后台 refresh 补全。纯本地写。
  Future<void> rankSeed({
    required int nid,
    required String title,
    String author = '',
    String coverUrl = '',
    String genre = '',
  }) async {
    await _postBody('/books/$nid/rank-seed', {
      'title': title,
      'author': author,
      'cover_url': coverUrl,
      'genre': genre,
    });
  }

  Future<RefreshResult> refresh(int nid) async {
    final body = await _post('/books/$nid/refresh', internet: true);
    return RefreshResult.fromJson(body);
  }

  Future<List<ObservationRow>> observations(int nid) async {
    final body = await _get('/books/$nid/observations');
    return (body['items'] as List)
        .map((e) => ObservationRow.fromJson(e as Map<String, dynamic>))
        .toList();
  }

  Future<List<WatchItem>> watchList() async {
    final body = await _get('/watchlist');
    return (body['items'] as List)
        .map((e) => WatchItem.fromJson(e as Map<String, dynamic>))
        .toList();
  }

  /// 加入 watchlist（v6 统一列表）：[active]=false 只存（原「加入书架」），
  /// true = 追踪（后台抓取 + 观测时序）；[role]=self 本人作品 | peer 同期
  /// 对照（docs/07 §1）；满 100 本上限时 409 watchlist_full。
  Future<void> watchAdd(int nid,
      {bool active = false, String role = 'self'}) async {
    await _postBody('/watchlist/$nid', {'active': active, 'role': role});
  }

  /// 切换追踪状态（v6）：PUT /watchlist/:nid {active}。
  Future<void> watchSetActive(int nid, bool active) async {
    await _putBody('/watchlist/$nid', {'active': active});
  }

  /// 切换 role（docs/07 §1）：self 本人作品 / peer 同期对照（PUT 一列，
  /// 历史曲线连续）。
  Future<void> watchSetRole(int nid, String role) async {
    await _putBody('/watchlist/$nid', {'role': role});
  }

  Future<void> watchRemove(int nid) async {
    await _delete('/watchlist/$nid');
  }

  Future<List<RankItem>> randomBooks({
    int limit = 8,
    String? status,
    String? form,
  }) async {
    final body = await _get('/random', {
      'limit': '$limit',
      'status': ?status,
      'form': ?form,
    });
    return (body['items'] as List)
        .map((e) => RankItem.fromJson(e as Map<String, dynamic>))
        .toList();
  }

  /// 授权作品：licensed 日本轻小说全量列表（收藏排序，无随机）。
  Future<List<RankItem>> licensedBooks({int limit = 100}) async {
    final body = await _get('/licensed', {'limit': '$limit'});
    return (body['items'] as List)
        .map((e) => RankItem.fromJson(e as Map<String, dynamic>))
        .toList();
  }

  /// 萌神获奖：2018–2024 各年度萌神 tag 书籍全量列表（收藏排序）。
  Future<List<RankItem>> moeGoddessBooks({int limit = 100}) async {
    final body = await _get('/moe-goddess', {'limit': '$limit'});
    return (body['items'] as List)
        .map((e) => RankItem.fromJson(e as Map<String, dynamic>))
        .toList();
  }

  /// 赛事档案列表（docs/contest-display-in-app.md 形态一）：seed 内置库按
  /// 赛事聚合（N征系列并入母赛事），零请求。官方日期来自引擎内嵌的
  /// 用户核实静态表（analysis/references/contest-editions.md）。
  Future<List<ContestGroup>> contestArchive() async {
    final body = await _get('/contests');
    return (body['groups'] as List)
        .map((e) => ContestGroup.fromJson(e as Map<String, dynamic>))
        .toList();
  }

  /// 一届赛事的代表作 + 该届库内获奖作品（schema v5）：各 form 头部按
  /// favs（经典累计，NULL 殿后，E.30），per 限每形态条数；奖项字段
  /// 同样不参与排序。
  Future<ContestBooks> contestArchiveBooks({
    required String contest,
    int per = 10,
  }) async {
    final body = await _get('/contests/books', {
      'contest': contest,
      'per': '$per',
    });
    return ContestBooks.fromJson(body as Map<String, dynamic>);
  }

  /// 一届赛事的官方清单一页（形态二，按需）：引擎按 (tag, page) 缓存
  /// （活跃 24h / 已结束 10 年——数据不变）并 join 本地 seed；接口失效回落库内子集
  /// （source=degraded，见 note）。多轨赛事传 division（档案页
  /// rosterTracks），单轨留空。
  Future<RosterPage> roster({
    required String contest,
    String division = '',
    int page = 1,
  }) async {
    final body = await _get('/roster', {
      'contest': contest,
      'division': division,
      'page': '$page',
    });
    return RosterPage.fromJson(body);
  }

  /// 官方书单列表一窗（顺序 id 探测：引擎每窗 10 个、逐个走限速器——
  /// 首窗 ≈10 秒，当日再访 24h 缓存秒回；docs/booklist-in-app.md）。
  Future<BooklistPage> booklists({int page = 1}) async {
    final body = await _getOnline('/booklists', {'page': '$page'});
    return BooklistPage.fromJson(body);
  }

  /// 书单详情（元数据 + 作品列表，引擎 24h 缓存 + 本地 join）。
  Future<BooklistDetail> booklistNovels(int id) async {
    final body = await _getOnline('/booklists/$id/novels');
    return BooklistDetail.fromJson(body);
  }

  /// 首页书单推荐行：引擎按 UTC 日期种子随机抽 count 个书单号（当日稳定、
  /// 24h 缓存；失效号自动补抽——docs/booklist-in-app.md §深化）。
  Future<List<Booklist>> booklistRecommend({int count = 3}) async {
    final body = await _getOnline('/booklists/recommend', {'count': '$count'});
    return (body['items'] as List)
        .map((e) => Booklist.fromJson(e as Map<String, dynamic>))
        .toList();
  }

  /// 编辑精选（seed featured=1，构建期人工选定，非"热门"）。
  /// 传 form 时只取该形态的 featured 池，池子不足 limit 时原样返回。
  Future<List<FeaturedItem>> featured({int limit = 6, String? form}) async {
    final params = {'limit': '$limit'};
    if (form != null) params['form'] = form;
    final body = await _get('/featured', params);
    return (body['items'] as List)
        .map((e) => FeaturedItem.fromJson(e as Map<String, dynamic>))
        .toList();
  }

  /// 每日 banner：日期种子对整个 banner 池（含 is_licensed）等概率抽取。
  /// form 非空时只在该形态的 featured 池内洗牌。
  Future<List<FeaturedItem>> banners({
    required int seed,
    int limit = 6,
    int offset = 0,
    String? form,
  }) async {
    final params = {'seed': '$seed', 'limit': '$limit', 'offset': '$offset'};
    if (form != null) params['form'] = form;
    final body = await _get('/banner', params);
    return (body['items'] as List)
        .map((e) => FeaturedItem.fromJson(e as Map<String, dynamic>))
        .toList();
  }

  /// 大图精选 gallery：featured=1 全池分页，默认按收藏降序，
  /// order='asc' 倒序；nid 作 tie-breaker，分页稳定。
  Future<List<FeaturedItem>> featuredAll({
    int limit = 10,
    int offset = 0,
    String order = 'desc',
  }) async {
    final body = await _get('/featured-all', {
      'limit': '$limit',
      'offset': '$offset',
      'order': order,
    });
    return (body['items'] as List)
        .map((e) => FeaturedItem.fromJson(e as Map<String, dynamic>))
        .toList();
  }

  /// 对话/短篇轮播：form 池中有封面书的收藏 Top-100 头部池，按日期
  /// 种子每日轮换（与 banner 同款哈希）。
  Future<List<RankItem>> coverCarousel({
    required int seed,
    int limit = 6,
    String form = 'dialogue',
  }) async {
    final body = await _get('/cover-carousel', {
      'limit': '$limit',
      'form': form,
      'seed': '$seed',
    });
    return (body['items'] as List)
        .map((e) => RankItem.fromJson(e as Map<String, dynamic>))
        .toList();
  }

  /// 发书日历（docs/14 P1）：seed 书按 est_date 聚合成日期格。
  /// granularity=day|week|month（周一起算周）；anchor=YYYY-MM-DD。
  /// month 视图只有 total（格太小不放卡片）；day/week 另带 per_cell 条
  /// 收藏序条目。est_conf=low 的书只进 month 视图（引擎侧过滤）。
  /// 作者作品列表（作者页时间轴，docs/author-profile-on-demand §1）：
  /// 该作者的内置库书目，est_date DESC（定年 0001 回填书沉底）。纯本地。
  Future<List<RankItem>> authorBooks({
    required String author,
    int limit = 20,
    int offset = 0,
    String order = 'newest',
  }) async {
    final body = await _get('/author-books', {
      'author': author,
      'limit': '$limit',
      'offset': '$offset',
      'order': order,
    });
    return (body['items'] as List)
        .map((e) => RankItem.fromJson(e as Map<String, dynamic>))
        .toList();
  }

  /// 作者资料（按需抓取 + user.db 缓存，docs/author-profile-on-demand §1-3）：
  /// 头像/名/作品集来自移动版详情页（[nid] 是该作者任意一本书），
  /// 简介仅 [withIntro] 时追加 PC 请求；[fresh] 绕过 7 天缓存。
  /// 网络/引擎错误抛异常；源书下架不抛——返回 verdict='dead' 的资料对象。
  Future<AuthorProfile> authorProfile({
    required String author,
    required int nid,
    bool withIntro = true,
    bool fresh = false,
  }) async {
    final body = await _get('/author-profile', {
      'author': author,
      'nid': '$nid',
      if (withIntro) 'with_intro': '1',
      if (fresh) 'fresh': '1',
    }, true) as Map<String, dynamic>;
    return AuthorProfile.fromJson(body);
  }

  /// 最近本地搜索关键词（搜索页空态，docs/08 §search-history）。
  Future<List<String>> searchHistory({int limit = 10}) async {
    final body = await _get('/search-history', {'limit': '$limit'});
    return (body['items'] as List).map((e) => e.toString()).toList();
  }

  /// 官方 HTML 搜索（docs/08 §search-remote）：30 条硬上限 + 静默限流识别。
  /// 6 秒内重复触发返回 429（抛异常）；限流不抛——rateLimited=true。
  Future<RemoteSearchResult> searchRemote(String q) async {
    final body = await _post(
      '/search/remote?q=${Uri.encodeComponent(q)}',
      internet: true,
    ) as Map<String, dynamic>;
    return RemoteSearchResult.fromJson(body);
  }

  /// 移除一条自动收录（用户手动删除，仅 user.db）。
  Future<void> deleteDiscovered(int nid) async {
    await _delete('/discovered/$nid');
  }

  /// 自动收录的库外书列表（收录管理页，docs/08 §discovered）。
  Future<List<DiscoveredItem>> discovered({int limit = 200}) async {
    final body = await _get('/discovered', {'limit': '$limit'});
    return (body['items'] as List)
        .map((e) => DiscoveredItem.fromJson(e as Map<String, dynamic>))
        .toList();
  }

  Future<CalendarResponse> calendar({
    required String granularity,
    required String anchor,
    int perCell = 3,
  }) async {
    final body = await _get('/calendar', {
      'granularity': granularity,
      'anchor': anchor,
      'per_cell': '$perCell',
    });
    return CalendarResponse.fromJson(body as Map<String, dynamic>);
  }

  /// IP tab 入口行：一个 form 的书按征文（contest）聚合，
  /// count DESC（引擎侧稳定排序）；total 用于端上折出“其他”入口。
  Future<IpGroupsResult> ipGroups({
    String form = 'ip_collab',
    String? status,
  }) async {
    final body = await _get('/ip-groups', {'form': form, 'status': ?status});
    return IpGroupsResult(
      total: (body['total'] as num).toInt(),
      groups: (body['groups'] as List)
          .map((e) => IpGroup.fromJson(e as Map<String, dynamic>))
          .toList(),
    );
  }

  /// 筛选 facet（经典榜单筛选面板）：form 池的题材/价格/年份/标签值列表。
  Future<FacetsResult> facets({String? form}) async {
    final body = await _get('/facets', {'form': ?form});
    return FacetsResult.fromJson(body);
  }

  /// 短篇 tab 年份入口：form 池按 est_year 聚合（年份降序）。
  Future<YearGroupsResult> yearGroups({String form = 'short'}) async {
    final body = await _get('/year-groups', {'form': form});
    return YearGroupsResult(
      total: (body['total'] as num).toInt(),
      groups: (body['groups'] as List)
          .map((e) => YearGroup.fromJson(e as Map<String, dynamic>))
          .toList(),
    );
  }

  /// 短篇 tab 题材浏览：form 池按 genre 聚合（本数降序）。
  Future<GenreGroupsResult> genreGroups({String form = 'short'}) async {
    final body = await _get('/genre-groups', {'form': form});
    return GenreGroupsResult(
      total: (body['total'] as num).toInt(),
      groups: (body['groups'] as List)
          .map((e) => GenreGroup.fromJson(e as Map<String, dynamic>))
          .toList(),
    );
  }

  /// 一个 IP 入口的列表：group 是征文名（精确匹配）或 'other'
  /// （收藏数前 2 名征文之外的长尾）；组内收藏降序。
  Future<List<RankItem>> ipBooks({
    String form = 'ip_collab',
    required String group,
    int limit = 100,
  }) async {
    final body = await _get('/ip-books', {
      'limit': '$limit',
      'form': form,
      'group': group,
    });
    return (body['items'] as List)
        .map((e) => RankItem.fromJson(e as Map<String, dynamic>))
        .toList();
  }

  Future<dynamic> _post(String path, {bool internet = false}) async {
    await _ensureOnline(internet: internet);
    final req = await _client.openUrl('POST', _uri(path));
    final resp = await req.close();
    final text = await resp.transform(utf8.decoder).join();
    if (resp.statusCode != 200) {
      throw StrataApiException(
        status: resp.statusCode,
        code: 'internal',
        message: text,
      );
    }
    return jsonDecode(text);
  }

  Future<dynamic> _postBody(String path, Map<String, dynamic> body) async {
    final req = await _client.openUrl('POST', _uri(path));
    req.headers.contentType = ContentType.json;
    req.write(jsonEncode(body));
    final resp = await req.close();
    final text = await resp.transform(utf8.decoder).join();
    if (resp.statusCode != 200) {
      throw StrataApiException(
        status: resp.statusCode,
        code: 'internal',
        message: text,
      );
    }
    return jsonDecode(text);
  }

  Future<dynamic> _putBody(String path, Map<String, dynamic> body) async {
    final req = await _client.openUrl('PUT', _uri(path));
    req.headers.contentType = ContentType.json;
    req.write(jsonEncode(body));
    final resp = await req.close();
    final text = await resp.transform(utf8.decoder).join();
    if (resp.statusCode != 200) {
      throw StrataApiException(
        status: resp.statusCode,
        code: 'internal',
        message: text,
      );
    }
    return jsonDecode(text);
  }

  Future<void> _delete(String path) async {
    final req = await _client.openUrl('DELETE', _uri(path));
    final resp = await req.close();
    await resp.transform(utf8.decoder).drain();
    if (resp.statusCode != 200) {
      throw StrataApiException(
        status: resp.statusCode,
        code: 'internal',
        message: 'delete failed',
      );
    }
  }

  Future<void> close() async => _client.close();
}

/// 引擎侧用户可调的抓取限制（详情刷新 24h 冷却开关、App API 增强开关）。
class EngineSettings {
  final bool detailRateLimitEnabled;
  final int windowSeconds;
  final bool appApiEnabled;
  final String discoverK;

  EngineSettings({
    required this.detailRateLimitEnabled,
    required this.windowSeconds,
    this.appApiEnabled = false,
    this.discoverK = '0',
  });

  factory EngineSettings.fromJson(Map<String, dynamic> j) => EngineSettings(
    detailRateLimitEnabled: j['detail_rate_limit_enabled'] as bool? ?? true,
    windowSeconds: j['detail_refresh_window_seconds'] as int? ?? 86400,
    appApiEnabled: j['app_api_enabled'] as bool? ?? false,
    discoverK: j['discover_k'] as String? ?? '0',
  );
}

/// 关注书观测的按日聚合（docs/07 §4 热力图）：day = epoch 天。
class HeatmapDay {
  final int day;
  final int books;
  final int rows;
  HeatmapDay({required this.day, required this.books, required this.rows});

  factory HeatmapDay.fromJson(Map<String, dynamic> j) => HeatmapDay(
    day: (j['day'] as num).toInt(),
    books: (j['books'] as num).toInt(),
    rows: (j['rows'] as num).toInt(),
  );
}

/// 世代探索的一格（est_year × genre 聚合，纯种子数据）。
class ErasExploreRow {
  final int estYear;
  final String genre;
  final int books;
  final double? medianFavs;
  ErasExploreRow({
    required this.estYear,
    required this.genre,
    required this.books,
    this.medianFavs,
  });

  factory ErasExploreRow.fromJson(Map<String, dynamic> j) => ErasExploreRow(
    estYear: (j['est_year'] as num).toInt(),
    genre: j['genre'] as String,
    books: (j['books'] as num).toInt(),
    medianFavs: (j['median_favs'] as num?)?.toDouble(),
  );
}

/// 工作台虚构测试书状态（设置页测试开关，docs/07 开发辅助）。
class TestBook {
  final int nid;
  final bool present;
  final String? title;
  final int? days;
  final int? rows;

  const TestBook({
    required this.nid,
    required this.present,
    this.title,
    this.days,
    this.rows,
  });

  factory TestBook.fromJson(Map<String, dynamic> j) => TestBook(
        nid: j['nid'] as int? ?? 0,
        present: j['present'] as bool? ?? false,
        title: j['title'] as String?,
        days: j['days'] as int?,
        rows: j['rows'] as int?,
      );
}

/// 浏览足迹：纯本地 user.db 数据。
class HistoryData {
  final List<HistoryEntry> items;

  HistoryData({required this.items});

  factory HistoryData.fromJson(Map<String, dynamic> j) => HistoryData(
    items: (j['items'] as List)
        .map((e) => HistoryEntry.fromJson(e as Map<String, dynamic>))
        .toList(),
  );
}

class HistoryEntry {
  final int nid;
  final String title;
  final String author;
  final String? genre;
  final int viewedAt;

  HistoryEntry({
    required this.nid,
    required this.title,
    required this.author,
    this.genre,
    required this.viewedAt,
  });

  factory HistoryEntry.fromJson(Map<String, dynamic> j) => HistoryEntry(
    nid: j['nid'] as int,
    title: j['title'] as String? ?? '',
    author: j['author'] as String? ?? '',
    genre: j['genre'] as String?,
    viewedAt: j['viewed_at'] as int? ?? 0,
  );
}

class StrataApiException implements Exception {
  final int status;
  final String code; // invalid_argument | not_found | internal
  final String message;

  StrataApiException({
    required this.status,
    required this.code,
    required this.message,
  });

  @override
  String toString() => 'StrataApiException($status, $code): $message';

  /// User-facing error text: offline shows the plain message (the global
  /// banner already explains the state); anything else keeps full detail.
  static String userMessage(Object e) =>
      e is StrataApiException && e.code == 'offline' ? e.message : e.toString();
}

class Healthz {
  final int schemaVersion;
  final String seedVersion;
  final int bookCount;
  final int licensedCount;
  final String contentEnd;
  final int genMin;
  final int genMax;

  Healthz.fromJson(Map<String, dynamic> m)
    : schemaVersion = m['schema_version'] as int,
      seedVersion = m['seed_version'] as String,
      bookCount = m['book_count'] as int,
      licensedCount = m['licensed_count'] as int,
      contentEnd = m['content_end'] as String,
      genMin = m['gen_min'] as int,
      genMax = m['gen_max'] as int;
}

class Meta {
  final Manifest manifest;
  final Map<String, String> seedMeta;

  Meta.fromJson(Map<String, dynamic> m)
    : manifest = Manifest.fromJson(m['manifest'] as Map<String, dynamic>),
      seedMeta = (m['seed_meta'] as Map<String, dynamic>).map(
        (k, v) => MapEntry(k, '$v'),
      );
}

class Manifest {
  final int schemaVersion;
  final String seedVersion;
  final String contentEnd;
  final String builtAt;
  final int bookCount;
  final int licensedCount;
  final int tagCount;
  final int tagRows;
  final int genMin;
  final int genMax;

  Manifest.fromJson(Map<String, dynamic> m)
    : schemaVersion = m['schema_version'] as int,
      seedVersion = m['seed_version'] as String,
      contentEnd = m['content_end'] as String,
      builtAt = m['built_at'] as String,
      bookCount = m['book_count'] as int,
      licensedCount = m['licensed_count'] as int,
      tagCount = m['tag_count'] as int,
      tagRows = m['tag_rows'] as int,
      genMin = m['gen_min'] as int,
      genMax = m['gen_max'] as int;
}

class CalendarItem {
  final int nid;
  final String title;
  final String author;
  final String? genre;
  final int favs;
  final String? coverUrl;
  final String estDate; // YYYY-MM-DD
  final String estConf; // exact|high|mid|low（docs/14 §1.3 精度分档）

  CalendarItem.fromJson(Map<String, dynamic> m)
    : nid = m['nid'] as int,
      title = m['title'] as String,
      author = m['author'] as String,
      genre = m['genre'] as String?,
      favs = m['favs'] as int,
      coverUrl = m['cover_url'] as String?,
      estDate = m['est_date'] as String,
      estConf = m['est_conf'] as String? ?? 'mid';
}

class CalendarDay {
  final String date; // YYYY-MM-DD
  final int total; // 内置库（可点击子集）
  final int universe; // 全平台估计（calendar_universe，seed v4）；0 = 无记录
  final List<CalendarItem> items; // 仅 day/week；month 视图为空

  CalendarDay.fromJson(Map<String, dynamic> m)
    : date = m['date'] as String,
      total = m['total'] as int,
      universe = (m['universe'] as num?)?.toInt() ?? 0,
      items = ((m['items'] as List?) ?? const [])
          .map((e) => CalendarItem.fromJson(e as Map<String, dynamic>))
          .toList();
}

class CalendarResponse {
  final String granularity; // day|week|month
  final String anchor; // day/week → YYYY-MM-DD（周一）；month → YYYY-MM
  final List<CalendarDay> cells;

  CalendarResponse.fromJson(Map<String, dynamic> m)
    : granularity = m['granularity'] as String,
      anchor = m['anchor'] as String,
      cells = (m['cells'] as List)
          .map((e) => CalendarDay.fromJson(e as Map<String, dynamic>))
          .toList();
}

/// 赛事档案条目（/strata/contests）：赛事级聚合 + 官方日期（用户核实）。
/// count/forms 只覆盖内置库（seed 收录）作品；库外参赛规模属 P1 清单 API。
class ContestGroup {
  final String name;
  final String series; // x|winter|spring|autumn|other
  final int count;
  final Map<String, int> forms;
  final List<String> tracks; // 原始赛项名，count DESC
  final int yearMin;
  final int yearMax;
  final int? year; // 官方启动年份（静态表）
  final String? start; // 官方启动日（无则 null，UI 只显年份）
  final String? end;
  final String? note; // 公布等后续节点
  /// 官方活动页 URL（引擎内嵌已验证静态表，源 docs/contest-roster-harvest
  /// §2）；null = 未验证（页面下线/未取到），档案页隐藏跳转入口、不编造。
  final String? official;
  /// other 系列事件的首页 tab 归属（用户裁定 2026-11-22）：'dialogue' /
  /// 'ip'；'' = 主题类（列表页「其他」tab）。四季系列永无 lane。
  final String lane;
  /// 可拉取官方清单（引擎有已验证 tagId 静态台账）；
  /// rosterTracks = 已验证赛道（空 = 单轨，roster 请求 division 传空）。
  final bool roster;
  final List<String> rosterTracks;

  ContestGroup({
    required this.name,
    required this.series,
    required this.count,
    required this.forms,
    required this.tracks,
    required this.yearMin,
    required this.yearMax,
    this.year,
    this.start,
    this.end,
    this.note,
    this.official,
    this.lane = '',
    this.roster = false,
    this.rosterTracks = const [],
  });

  ContestGroup.fromJson(Map<String, dynamic> m)
      : name = m['name'] as String,
        series = m['series'] as String,
        count = (m['count'] as num).toInt(),
        forms = (m['forms'] as Map<String, dynamic>)
            .map((k, v) => MapEntry(k, (v as num).toInt())),
        tracks = (m['tracks'] as List).map((e) => e as String).toList(),
        yearMin = (m['year_min'] as num).toInt(),
        yearMax = (m['year_max'] as num).toInt(),
        year = (m['year'] as num?)?.toInt(),
        start = m['start'] as String?,
        end = m['end'] as String?,
        note = m['note'] as String?,
        official = m['official'] as String?,
        lane = m['lane'] as String? ?? '',
        roster = m['roster'] as bool? ?? false,
        rosterTracks = (m['roster_tracks'] as List? ?? const [])
            .map((e) => e as String)
            .toList();
}

/// 官方清单条目（/strata/roster）：清单 6 字段（nid/标题/作者/简介/封面/
/// categoryID）+ 本地 join。库内作品带 form/累计展示字段；库外作品只有
/// 清单字段——不伪造徽标（docs/12 红线）。categoryID 是赛道提示
/// （0 常规/1 对话/3 短篇/4 沉浸式），不是 form 真值（E.28）。
class RosterItem {
  final int nid;
  final String title;
  final String author;
  final String intro;
  final String? coverUrl;
  final int categoryId;
  final bool inLibrary;
  final String? form;
  final int? favs;
  final String? status;
  final int? estYear;
  final int? words;

  RosterItem.fromJson(Map<String, dynamic> m)
      : nid = m['nid'] as int,
        title = m['title'] as String,
        author = m['author'] as String? ?? '',
        intro = m['intro'] as String? ?? '',
        coverUrl = m['cover'] as String?,
        categoryId = (m['category_id'] as num?)?.toInt() ?? 0,
        inLibrary = m['in_library'] as bool? ?? false,
        form = m['form'] as String?,
        favs = (m['favs'] as num?)?.toInt(),
        status = m['status'] as String?,
        estYear = (m['est_year'] as num?)?.toInt(),
        words = (m['words'] as num?)?.toInt();
}

/// 官方清单页：source=official（上游清单）| degraded（引擎回落库内子集，
/// 见 note）。库外条目点击复用搜索页链路（/book/{nid} → 详情 + 自动收录）。
class RosterPage {
  final String contest;
  final String division;
  final int page;
  final int pages;
  final String source;
  final String? note;
  final List<RosterItem> items;
  /// 官方全量参赛规模估算（总页数×实际页大小，误差 ≤ 一页；降级响应无此
  /// 键）——UI 显示「约 N 篇」（用户 2026-11-22 裁定：近似即可，不多发请求）。
  final int? totalEstimate;

  RosterPage.fromJson(Map<String, dynamic> m)
      : contest = m['contest'] as String,
        division = m['division'] as String? ?? '',
        page = (m['page'] as num?)?.toInt() ?? 1,
        pages = (m['pages'] as num?)?.toInt() ?? 1,
        totalEstimate = (m['total_estimate'] as num?)?.toInt(),
        source = m['source'] as String? ?? 'official',
        note = m['note'] as String?,
        items = (m['items'] as List)
            .map((e) => RosterItem.fromJson(e as Map<String, dynamic>))
            .toList();
}

/// 官方书单（/strata/booklists 窗口项 / 详情头；官方 API 无枚举动作，
/// 引擎顺序 id 探测 10 个/窗、24h 缓存——docs/booklist-in-app.md）。
class Booklist {
  final int id;
  final String title;
  final String summary;
  final String author;
  final String avatar;
  final bool vip;
  final int markNum;
  final int recommends;
  final int novelNum;
  final String updated;

  Booklist.fromJson(Map<String, dynamic> m)
      : id = (m['id'] as num?)?.toInt() ?? 0,
        title = m['title'] as String,
        summary = m['summary'] as String? ?? '',
        author = m['author'] as String? ?? '',
        avatar = m['avatar'] as String? ?? '',
        vip = m['vip'] as bool? ?? false,
        markNum = (m['mark_num'] as num?)?.toInt() ?? 0,
        recommends = (m['recommend_num'] as num?)?.toInt() ?? 0,
        novelNum = (m['novel_num'] as num?)?.toInt() ?? 0,
        updated = m['updated'] as String? ?? '';
}

/// 书单内一部作品：官方累计值（字数/点击/收藏）纯展示，永不进推荐
/// 打分（docs/12 红线）；inLibrary/form 为引擎本地 join，库外不伪造。
class BooklistNovel {
  final int nid;
  final String title;
  final String author;
  final String cover;
  final String type;
  final int words;
  final int clicks;
  final int favs;
  final bool finish;
  final String note;
  final bool inLibrary;
  final String form;

  BooklistNovel.fromJson(Map<String, dynamic> m)
      : nid = (m['nid'] as num?)?.toInt() ?? 0,
        title = m['title'] as String,
        author = m['author'] as String? ?? '',
        cover = m['cover'] as String? ?? '',
        type = m['type'] as String? ?? '',
        words = (m['words'] as num?)?.toInt() ?? 0,
        clicks = (m['clicks'] as num?)?.toInt() ?? 0,
        favs = (m['favs'] as num?)?.toInt() ?? 0,
        finish = m['finish'] as bool? ?? false,
        note = m['note'] as String? ?? '',
        inLibrary = m['in_library'] as bool? ?? false,
        form = m['form'] as String? ?? '';
}

/// 书单列表一窗（done=true 表示页不满、已到底）。
class BooklistPage {
  final int page;
  final List<Booklist> items;
  final bool done;

  BooklistPage.fromJson(Map<String, dynamic> m)
      : page = (m['page'] as num?)?.toInt() ?? 1,
        items = (m['items'] as List)
            .map((e) => Booklist.fromJson(e as Map<String, dynamic>))
            .toList(),
        done = m['done'] as bool? ?? true;
}

/// 书单详情：头部元数据 + 作品列表（官方顺序，本地 join 后）。
class BooklistDetail {
  final Booklist booklist;
  final List<BooklistNovel> items;

  BooklistDetail.fromJson(Map<String, dynamic> m)
      : booklist =
            Booklist.fromJson((m['booklist'] as Map).cast<String, dynamic>()),
        items = (m['items'] as List)
            .map((e) => BooklistNovel.fromJson(e as Map<String, dynamic>))
            .toList();
}

class RankItem {
  final int rank;
  final int nid;
  final String title;
  final String author;
  final String? genre;
  final int estYear;
  final int favs;
  final String? contest;
  final String? coverUrl;
  final String? status;
  final int? words;
  final int? clicks;
  final int? praises;
  final String form;
  final List<String> tags;

  /// 定年日期（YYYY-MM-DD）：作者页时间轴用（est_date）；旧端点不返回此字段。
  final String? estDate;

  /// 证据强度（app/docs/18-runtime-metrics.md）：'stable'/'low'，仅 cqs 流
  /// 返回；其余端点为空串。
  final String cqsState;

  RankItem.fromJson(Map<String, dynamic> m)
    : rank = m['rank'] as int,
      nid = m['nid'] as int,
      title = m['title'] as String,
      author = m['author'] as String,
      genre = m['genre'] as String?,
      estYear = m['est_year'] as int,
      favs = m['favs'] as int,
      contest = m['contest'] as String?,
      coverUrl = m['cover_url'] as String?,
      status = m['status'] as String?,
      words = m['words'] as int?,
      clicks = m['clicks'] as int?,
      praises = (m['praises'] as num?)?.toInt(),
      form = m['form'] as String? ?? '',
      estDate = m['est_date'] as String?,
      cqsState = m['cqs_state'] as String? ?? '',
      tags = ((m['tags'] as List?) ?? const [])
          .map((e) => e.toString())
          .toList();
}

/// 移动版详情页作者区（book_Author）的作品集条目。
class AuthorWork {
  final int nid;
  final String title;

  AuthorWork.fromJson(Map<String, dynamic> m)
    : nid = m['nid'] as int,
      title = m['title'] as String;
}

/// 作者资料（按需抓取 + user.db 缓存，docs/author-profile-on-demand §3）。
/// 快照数据：[authorIntro] 可为空（作者没写——正常值，勿伪造）；
/// [verdict] = 'ok' | 'dead'（源书已下架）| 'error'（抓取失败），供 UI 降级。
class AuthorProfile {
  final int nid;
  final String authorName;
  final String? authorIntro;
  final String? authorAvatar;
  final List<AuthorWork> works;
  // 库外作品 = works − seed（引擎差集，保持页面序）：作者页「其他作品」
  // 区块（docs/author-profile-on-demand §6）；works 本身仍是官方全量。
  final List<AuthorWork> offlibrary;
  final String verdict;
  final int observedAt;
  final String source; // 'cache' | 'live'

  AuthorProfile.fromJson(Map<String, dynamic> m)
    : nid = m['nid'] as int,
      authorName = m['author_name'] as String? ?? '',
      authorIntro = m['author_intro'] as String?,
      authorAvatar = m['author_avatar'] as String?,
      works = ((m['works'] as List?) ?? const [])
          .map((e) => AuthorWork.fromJson(e as Map<String, dynamic>))
          .toList(),
      offlibrary = ((m['offlibrary'] as List?) ?? const [])
          .map((e) => AuthorWork.fromJson(e as Map<String, dynamic>))
          .toList(),
      verdict = m['verdict'] as String? ?? 'error',
      observedAt = m['observed_at'] as int? ?? 0,
      source = m['source'] as String? ?? 'live';
}

class WatchItem {
  final int nid;
  final String title;
  final String author;
  final String? genre;
  final String? coverUrl;
  final int addedAt;
  final String role;
  final String? note;

  /// v6 统一列表：true = 追踪中（后台抓取），false = 只存（原书架条目）。
  final bool active;

  WatchItem.fromJson(Map<String, dynamic> m)
    : nid = m['nid'] as int,
      title = m['title'] as String,
      author = m['author'] as String,
      genre = m['genre'] as String?,
      coverUrl = m['cover_url'] as String?,
      addedAt = m['added_at'] as int,
      role = m['role'] as String? ?? 'self',
      note = m['note'] as String?,
      active = m['active'] as bool? ?? false;
}

class DiscoverPage {
  final List<RankItem> items;
  final String? nextCursor;

  DiscoverPage.fromJson(Map<String, dynamic> m)
    : items = (m['items'] as List)
          .map((e) => RankItem.fromJson(e as Map<String, dynamic>))
          .toList(),
      nextCursor = m['next_cursor'] as String?;

  bool get hasMore => nextCursor != null && nextCursor!.isNotEmpty;
}

class ShortItem {
  final int rank;
  final int nid;
  final String title;
  final String author;
  final String? genre;
  final int estYear;
  final int favs;
  final int? words;
  final String? coverUrl;

  ShortItem.fromJson(Map<String, dynamic> m)
    : rank = m['rank'] as int,
      nid = m['nid'] as int,
      title = m['title'] as String,
      author = m['author'] as String,
      genre = m['genre'] as String?,
      estYear = m['est_year'] as int,
      favs = m['favs'] as int,
      words = m['words'] as int?,
      coverUrl = m['cover_url'] as String?;
}

class SearchItem {
  final int nid;
  final String title;
  final String author;
  final String? genre;
  final int estYear;
  final int? favs;
  final String? coverUrl;

  /// false = 自动收录的库外书（discovered 覆盖层），est_year/favs 为空。
  final bool inSeed;

  SearchItem.fromJson(Map<String, dynamic> m)
    : nid = m['nid'] as int,
      title = m['title'] as String,
      author = m['author'] as String,
      genre = m['genre'] as String?,
      estYear = m['est_year'] as int,
      favs = m['favs'] as int?,
      coverUrl = m['cover_url'] as String?,
      inSeed = m['in_seed'] as bool? ?? true;
}

/// 官方搜索结果行（docs/08 §search-remote）：[inSeed] = 内置库命中；
/// 库外为站内新书（详情按需抓取视图）。
class RemoteSearchItem {
  final int nid;
  final String title;
  final String author;
  final String? updatedAt;
  final String? coverUrl;
  final String? summary;
  final bool inSeed;

  RemoteSearchItem.fromJson(Map<String, dynamic> m)
    : nid = m['nid'] as int,
      title = m['title'] as String,
      author = m['author'] as String? ?? '',
      updatedAt = m['updated_at'] as String?,
      coverUrl = m['cover_url'] as String?,
      summary = m['summary'] as String?,
      inSeed = m['in_seed'] as bool? ?? false;
}

/// 官方搜索响应：[rateLimited] = 静默限流（HTTP 200 但指纹翻转，
/// docs/sfacg-endpoints §2.1）——UI 明确提示，绝不伪造空结果。
class RemoteSearchResult {
  final bool rateLimited;
  final int declared;
  final List<RemoteSearchItem> items;

  RemoteSearchResult.fromJson(Map<String, dynamic> m)
    : rateLimited = m['meta']?['rate_limited'] as bool? ?? false,
      declared = m['meta']?['declared'] as int? ?? 0,
      items = ((m['items'] as List?) ?? const [])
          .map((e) => RemoteSearchItem.fromJson(e as Map<String, dynamic>))
          .toList();
}

/// contest（征文）→ 联动 IP 展示名（崩坏3征文 → 崩坏3，
/// 失业魔王同人征文 → 失业魔王）。contest 为空返回 null（无征文标）。
String? contestIpLabel(String? contest) {
  if (contest == null || contest.isEmpty) return null;
  var s = contest;
  if (s.endsWith('同人征文')) {
    s = s.substring(0, s.length - 4);
  } else if (s.endsWith('征文')) {
    s = s.substring(0, s.length - 2);
  }
  return s.isEmpty ? contest : s;
}

/// contest（征文）→ 短篇 tab 比赛 chip 的紧凑标签：
/// 去「征文」/「同人征文」后缀（2025春季征文 → 2025春季），「超新星杯」
/// 特殊处理（“超新星杯”短篇大赛 → 超新星杯）。入参已是引擎归一化后的
/// 赛事名（六征长篇/中篇/短篇 → 六征，仅 N征 系列，用户 2026-11-21）。
String contestChipLabel(String contest) {
  if (contest.contains('超新星杯')) return '超新星杯';
  var s = contest;
  if (s.endsWith('同人征文')) {
    s = s.substring(0, s.length - 4);
  } else if (s.endsWith('征文')) {
    s = s.substring(0, s.length - 2);
  }
  return s.isEmpty ? contest : s;
}

/// IP 入口行的一个分组：contest（征文）→ 联动 IP，count 本数。
class IpGroup {
  final String contest;
  final int count;

  const IpGroup({required this.contest, required this.count});

  factory IpGroup.fromJson(Map<String, dynamic> j) => IpGroup(
    contest: j['contest'] as String,
    count: (j['count'] as num).toInt(),
  );

  /// 展示名：由 contest 推导（崩坏3征文 → 崩坏3）。
  String get label => contestIpLabel(contest) ?? contest;
}

/// IP 入口行结果：total = 池总量（用于端上折出“其他”），
/// groups = 按征文（contest）聚合、count DESC 的分组。
class IpGroupsResult {
  final int total;
  final List<IpGroup> groups;

  const IpGroupsResult({required this.total, required this.groups});
}

/// 筛选 facet 的一个可选项 + 池内本数（GET /facets）。
class FacetValue {
  final String name;
  final int count;

  const FacetValue({required this.name, required this.count});

  factory FacetValue.fromJson(Map<String, dynamic> j) => FacetValue(
    name: j['name'] as String,
    count: (j['count'] as num).toInt(),
  );
}

/// 年份 facet：est_year → 本数（年份降序）。
class FacetYear {
  final int year;
  final int count;

  const FacetYear({required this.year, required this.count});

  factory FacetYear.fromJson(Map<String, dynamic> j) => FacetYear(
    year: (j['year'] as num).toInt(),
    count: (j['count'] as num).toInt(),
  );
}

/// 筛选 facet（经典榜单筛选面板，用户 2026-11-21）：某 form 池的
/// genres/ptypes/tags（top 60，count DESC）/years（year DESC）。
/// 状态是固定枚举（已完结/连载中），不在 facet 里。
class FacetsResult {
  final List<FacetValue> genres;
  final List<FacetValue> ptypes;
  final List<FacetValue> tags;
  final List<FacetYear> years;

  const FacetsResult({
    required this.genres,
    required this.ptypes,
    required this.tags,
    required this.years,
  });

  factory FacetsResult.fromJson(Map<String, dynamic> j) => FacetsResult(
    genres: (j['genres'] as List)
        .map((e) => FacetValue.fromJson(e as Map<String, dynamic>))
        .toList(),
    ptypes: (j['ptypes'] as List)
        .map((e) => FacetValue.fromJson(e as Map<String, dynamic>))
        .toList(),
    tags: (j['tags'] as List)
        .map((e) => FacetValue.fromJson(e as Map<String, dynamic>))
        .toList(),
    years: (j['years'] as List)
        .map((e) => FacetYear.fromJson(e as Map<String, dynamic>))
        .toList(),
  );
}

/// 年份分组：est_year → 本数（年份降序）。
class YearGroup {
  final int year;
  final int count;

  const YearGroup({required this.year, required this.count});

  factory YearGroup.fromJson(Map<String, dynamic> j) => YearGroup(
    year: (j['year'] as num).toInt(),
    count: (j['count'] as num).toInt(),
  );
}

class YearGroupsResult {
  final int total;
  final List<YearGroup> groups;

  const YearGroupsResult({required this.total, required this.groups});
}

/// 题材分组：genre → 本数（本数降序）。
class GenreGroup {
  final String genre;
  final int count;

  const GenreGroup({required this.genre, required this.count});

  factory GenreGroup.fromJson(Map<String, dynamic> j) => GenreGroup(
    genre: j['genre'] as String,
    count: (j['count'] as num).toInt(),
  );
}

class GenreGroupsResult {
  final int total;
  final List<GenreGroup> groups;

  const GenreGroupsResult({required this.total, required this.groups});
}

class FeaturedItem {
  final int nid;
  final String title;
  final String author;
  final String? coverUrl;
  final int? favs;

  FeaturedItem.fromJson(Map<String, dynamic> m)
    : nid = m['nid'] as int,
      title = m['title'] as String,
      author = m['author'] as String,
      coverUrl = m['cover_url'] as String?,
      favs = m['favs'] as int?;
}

class RefreshResult {
  final String state; // alive | dead | zombie
  final bool written;
  final Map<String, dynamic>? detail;

  RefreshResult.fromJson(Map<String, dynamic> m)
      : state = m['state'] as String,
        written = m['written'] as bool,
        detail = m['detail'] as Map<String, dynamic>?;
}

/// 自动收录的库外书一行（user.db discovered，docs/08 §discovered）。
class DiscoveredItem {
  final int nid;
  final String title;
  final String? author;
  final String? coverUrl;
  final String? summary;
  final String source;
  final int observedAt;

  DiscoveredItem.fromJson(Map<String, dynamic> m)
      : nid = m['nid'] as int,
        title = m['title'] as String,
        author = m['author'] as String?,
        coverUrl = m['cover_url'] as String?,
        summary = m['summary'] as String?,
        source = m['source'] as String? ?? 'search',
        observedAt = m['observed_at'] as int? ?? 0;
}

class ObservationRow {
  final int observedAt;
  final int? clicks;
  final int? favs;
  final int? praises;
  final int? words;
  final int? shortComments;
  final int? longComments;
  final String? status;
  final String? updatedAt;
  final String? source;

  ObservationRow.fromJson(Map<String, dynamic> m)
    : observedAt = m['observed_at'] as int,
      clicks = m['clicks'] as int?,
      favs = m['favs'] as int?,
      praises = m['praises'] as int?,
      words = m['words'] as int?,
      shortComments = m['short_comments'] as int?,
      longComments = m['long_comments'] as int?,
      status = m['status'] as String?,
      updatedAt = m['updated_at'] as String?,
      source = m['source'] as String?;
}

/// 一条获奖记录（schema v5，docs/contest-display-in-app.md §6）。
/// award 为表内原值：44 本已标定届次是具体奖项名，其余 867 本为
/// 「待逐档标定」占位——展示层统一映射为「征文获奖」，不显示占位原文。
class Award {
  final int nid;
  final String edition;
  final String award;
  final String? category;

  Award.fromJson(Map<String, dynamic> m)
      : nid = m['nid'] as int,
        edition = m['edition'] as String,
        award = m['award'] as String,
        category = m['category'] as String?;

  /// 徽标文案（占位 → 征文获奖，docs §6）。
  String get displayAward => award == '待逐档标定' ? '征文获奖' : award;
}

/// /contests/books 响应：代表作（items）。获奖清单已从档案页移除（用户
/// 裁定 2026-11-22：参赛者的 top10 大概就是获奖者；获奖徽标保留在书籍
/// 详情页）；引擎仍返回 awards 键，端上不再解析。
class ContestBooks {
  final List<RankItem> items;

  ContestBooks.fromJson(Map<String, dynamic> m)
      : items = (m['items'] as List)
            .map((e) => RankItem.fromJson(e as Map<String, dynamic>))
            .toList();
}

class BookDetail {
  final String source; // seed | local
  final String dataEnd;
  final Map<String, dynamic> book;
  final List<String> tags;
  final Map<String, dynamic>? effective;
  // local/meta 仅用于基线判别（docs/07 §6）：非种子书 local 恒 null 且
  // meta 非空；种子书无观测时两者皆空，有观测时 local 非空。
  final Map<String, dynamic>? local;
  final Map<String, dynamic>? meta;
  // 种子侧获奖记录（schema v5）：仅徽标素材，永不参与排序/打分。
  // 种子书详情恒有该字段（空列表 = 无获奖）；库外 overlay 无此字段。
  final List<Award> awards;

  BookDetail.fromJson(Map<String, dynamic> m)
    : source = m['source'] as String,
      dataEnd = m['data_end'] as String,
      book = m['book'] as Map<String, dynamic>,
      tags = (m['tags'] as List).cast<String>(),
      effective = m['effective'] as Map<String, dynamic>?,
      local = m['local'] as Map<String, dynamic>?,
      meta = m['meta'] as Map<String, dynamic>?,
      awards = (m['awards'] as List?)
              ?.map((e) => Award.fromJson(e as Map<String, dynamic>))
              .toList() ??
          const [];
}

/// 官方榜单一行（三来源共用，docs/sfacg-live-ranks.md）。
/// nid 为 0 = 读者侧行（PC 粉丝榜，只有用户名）；
/// value 承载月票/火券（来源公布数值时）。
class OfficialRankEntry {
  final int nid;
  final int rank;
  final String title;
  final String author;
  final String? genre;
  final String? coverUrl;
  final int value;

  OfficialRankEntry.fromJson(Map<String, dynamic> m)
    : nid = m['nid'] as int? ?? 0,
      rank = m['rank'] as int? ?? 0,
      title = m['title'] as String? ?? '',
      author = m['author'] as String? ?? '',
      genre = m['genre'] as String?,
      coverUrl = m['cover_url'] as String?,
      value = m['value'] as int? ?? 0;
}

/// PC Rank 页的一个榜单（book.sfacg.com/Rank/ 共四榜）。
class OfficialPcBoard {
  final String name;
  final List<OfficialRankEntry> entries;

  OfficialPcBoard.fromJson(Map<String, dynamic> m)
    : name = m['name'] as String,
      entries = (m['entries'] as List)
          .map((e) => OfficialRankEntry.fromJson(e as Map<String, dynamic>))
          .toList();
}
