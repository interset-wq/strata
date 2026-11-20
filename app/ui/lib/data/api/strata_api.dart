import 'dart:async';
import 'dart:convert';
import 'dart:io';

/// HTTP client for the embedded Go engine.
/// Contract: app/docs/08-engine-api.md.
class StrataApi {
  final HttpClient _client = HttpClient();
  final String base; // e.g. http://127.0.0.1:45851

  StrataApi(this.base);

  Uri _uri(String path, [Map<String, String>? query]) =>
      Uri.parse('$base/strata$path').replace(queryParameters: query);

  Future<dynamic> _get(String path, [Map<String, String>? query]) async {
    final req = await _client.getUrl(_uri(path, query));
    final resp = await req.close();
    final body =
        await resp.transform(utf8.decoder).join();
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

  Future<Healthz> healthz() async =>
      Healthz.fromJson(await _get('/healthz') as Map<String, dynamic>);

  Future<Meta> meta() async => Meta.fromJson(await _get('/meta') as Map<String, dynamic>);

  Future<EngineSettings> settings() async =>
      EngineSettings.fromJson(await _get('/settings') as Map<String, dynamic>);

  Future<EngineSettings> setDetailRateLimitEnabled(bool enabled) async =>
      EngineSettings.fromJson(await _putBody(
          '/settings', {'detail_rate_limit_enabled': enabled}) as Map<String, dynamic>);

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

  Future<List<RankItem>> rankingBoard(
      {required String kind,
      String? form,
      int limit = 50,
      int offset = 0}) async {
    final body = await _get('/rankings/board', {
      'kind': kind,
      'limit': '$limit',
      'form': ?form,
      if (offset > 0) 'offset': '$offset',
    });
    return (body['items'] as List)
        .map((e) => RankItem.fromJson(e as Map<String, dynamic>))
        .toList();
  }

  /// Classic category/status/contest list: absolute favs order by default,
  /// or same-generation favorite percentile (order='pct', 优质短篇口径).
  Future<List<RankItem>> rankingClassic({
    String? genre,
    String? status,
    String? contest,
    String? form,
    int? year,
    String? order,
    int limit = 50,
    int offset = 0,
  }) async {
    final body = await _get('/rankings/classic', {
      'limit': '$limit',
      'genre': ?genre,
      'status': ?status,
      'contest': ?contest,
      'form': ?form,
      if (year != null) 'year': '$year',
      'order': ?order,
      if (offset > 0) 'offset': '$offset',
    });
    return (body['items'] as List)
        .map((e) => RankItem.fromJson(e as Map<String, dynamic>))
        .toList();
  }

  Future<DiscoverPage> discover(
      {String? cursor, String? form, int limit = 20}) async {
    final body = await _get('/discover', {
      'limit': '$limit',
      'form': ?form,
      if (cursor != null && cursor.isNotEmpty) 'cursor': cursor,
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
    final body = await _get('/search', {
      'q': q,
      'limit': '$limit',
    });
    return (body['items'] as List)
        .map((e) => SearchItem.fromJson(e as Map<String, dynamic>))
        .toList();
  }

  /// Triggers a mobile-page detail fetch (sync; global limiter serializes).
  /// state: alive | dead | zombie; written: observation appended.
  Future<RefreshResult> refresh(int nid) async {
    final body = await _post('/books/$nid/refresh');
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
  /// true = 追踪（后台抓取 + 观测时序）。
  Future<void> watchAdd(int nid, {bool active = false}) async {
    await _postBody('/watchlist/$nid', {'active': active});
  }

  /// 切换追踪状态（v6）：PUT /watchlist/:nid {active}。
  Future<void> watchSetActive(int nid, bool active) async {
    await _putBody('/watchlist/$nid', {'active': active});
  }

  Future<void> watchRemove(int nid) async {
    await _delete('/watchlist/$nid');
  }

  Future<List<RankItem>> randomBooks(
      {int limit = 8, String? status, String? form}) async {
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
  Future<List<FeaturedItem>> banners(
      {required int seed,
      int limit = 6,
      int offset = 0,
      String? form}) async {
    final params = {
      'seed': '$seed',
      'limit': '$limit',
      'offset': '$offset',
    };
    if (form != null) params['form'] = form;
    final body = await _get('/banner', params);
    return (body['items'] as List)
        .map((e) => FeaturedItem.fromJson(e as Map<String, dynamic>))
        .toList();
  }

  /// 大图精选 gallery：featured=1 全池分页，默认按收藏降序，
  /// order='asc' 倒序；nid 作 tie-breaker，分页稳定。
  Future<List<FeaturedItem>> featuredAll(
      {int limit = 10, int offset = 0, String order = 'desc'}) async {
    final body = await _get('/featured-all',
        {'limit': '$limit', 'offset': '$offset', 'order': order});
    return (body['items'] as List)
        .map((e) => FeaturedItem.fromJson(e as Map<String, dynamic>))
        .toList();
  }

  /// 对话/短篇轮播：form 池中有封面书的收藏 Top-100 头部池，按日期
  /// 种子每日轮换（与 banner 同款哈希）。
  Future<List<RankItem>> coverCarousel(
      {required int seed, int limit = 6, String form = 'dialogue'}) async {
    final body = await _get('/cover-carousel',
        {'limit': '$limit', 'form': form, 'seed': '$seed'});
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
  }) async {
    final body = await _get('/author-books',
        {'author': author, 'limit': '$limit', 'offset': '$offset'});
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
    }) as Map<String, dynamic>;
    return AuthorProfile.fromJson(body);
  }

  Future<CalendarResponse> calendar({
    required String granularity,
    required String anchor,
    int perCell = 3,
  }) async {
    final body = await _get(
        '/calendar', {'granularity': granularity, 'anchor': anchor, 'per_cell': '$perCell'});
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
  Future<List<RankItem>> ipBooks(
      {String form = 'ip_collab',
      required String group,
      int limit = 100}) async {
    final body = await _get(
        '/ip-books', {'limit': '$limit', 'form': form, 'group': group});
    return (body['items'] as List)
        .map((e) => RankItem.fromJson(e as Map<String, dynamic>))
        .toList();
  }

  Future<dynamic> _post(String path) async {
    final req = await _client.openUrl('POST', _uri(path));
    final resp = await req.close();
    final text = await resp.transform(utf8.decoder).join();
    if (resp.statusCode != 200) {
      throw StrataApiException(
          status: resp.statusCode, code: 'internal', message: text);
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
          status: resp.statusCode, code: 'internal', message: text);
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
          status: resp.statusCode, code: 'internal', message: text);
    }
    return jsonDecode(text);
  }

  Future<void> _delete(String path) async {
    final req = await _client.openUrl('DELETE', _uri(path));
    final resp = await req.close();
    await resp.transform(utf8.decoder).drain();
    if (resp.statusCode != 200) {
      throw StrataApiException(
          status: resp.statusCode, code: 'internal', message: 'delete failed');
    }
  }

  Future<void> close() async => _client.close();
}

/// 引擎侧用户可调的抓取限制（详情刷新 24h 冷却开关）。
class EngineSettings {
  final bool detailRateLimitEnabled;
  final int windowSeconds;

  EngineSettings({required this.detailRateLimitEnabled, required this.windowSeconds});

  factory EngineSettings.fromJson(Map<String, dynamic> j) => EngineSettings(
        detailRateLimitEnabled: j['detail_rate_limit_enabled'] as bool? ?? true,
        windowSeconds: j['detail_refresh_window_seconds'] as int? ?? 86400,
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
      : manifest = Manifest.fromJson(
            m['manifest'] as Map<String, dynamic>),
        seedMeta = (m['seed_meta'] as Map<String, dynamic>)
            .map((k, v) => MapEntry(k, '$v'));
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

class RankItem {
  final int rank;
  final int nid;
  final String title;
  final String author;
  final String? genre;
  final int estYear;
  final int favs;
  final double favPctl;
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

  RankItem.fromJson(Map<String, dynamic> m)
      : rank = m['rank'] as int,
        nid = m['nid'] as int,
        title = m['title'] as String,
        author = m['author'] as String,
        genre = m['genre'] as String?,
        estYear = m['est_year'] as int,
        favs = m['favs'] as int,
        favPctl = (m['fav_pctl'] as num?)?.toDouble() ?? 0,
        contest = m['contest'] as String?,
        coverUrl = m['cover_url'] as String?,
        status = m['status'] as String?,
        words = m['words'] as int?,
        clicks = m['clicks'] as int?,
        praises = (m['praises'] as num?)?.toInt(),
        form = m['form'] as String? ?? '',
        estDate = m['est_date'] as String?,
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

  SearchItem.fromJson(Map<String, dynamic> m)
      : nid = m['nid'] as int,
        title = m['title'] as String,
        author = m['author'] as String,
        genre = m['genre'] as String?,
        estYear = m['est_year'] as int,
        favs = m['favs'] as int?;
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
/// 去「征文」/「同人征文」后缀（四征短篇 → 四征短篇、2025春季征文 →
/// 2025春季），「超新星杯」特殊处理（“超新星杯”短篇大赛 → 超新星杯）。
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
      contest: j['contest'] as String, count: (j['count'] as num).toInt());

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

/// 年份分组：est_year → 本数（年份降序）。
class YearGroup {
  final int year;
  final int count;

  const YearGroup({required this.year, required this.count});

  factory YearGroup.fromJson(Map<String, dynamic> j) => YearGroup(
      year: (j['year'] as num).toInt(), count: (j['count'] as num).toInt());
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
      genre: j['genre'] as String, count: (j['count'] as num).toInt());
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

class ObservationRow {
  final int observedAt;
  final int? favs;
  final int? praises;
  final int? words;
  final String? status;
  final String? updatedAt;

  ObservationRow.fromJson(Map<String, dynamic> m)
      : observedAt = m['observed_at'] as int,
        favs = m['favs'] as int?,
        praises = m['praises'] as int?,
        words = m['words'] as int?,
        status = m['status'] as String?,
        updatedAt = m['updated_at'] as String?;
}

class BookDetail {
  final String source; // seed | local
  final String dataEnd;
  final Map<String, dynamic> book;
  final List<String> tags;
  final Map<String, dynamic>? effective;

  BookDetail.fromJson(Map<String, dynamic> m)
      : source = m['source'] as String,
        dataEnd = m['data_end'] as String,
        book = m['book'] as Map<String, dynamic>,
        tags = (m['tags'] as List).cast<String>(),
        effective = m['effective'] as Map<String, dynamic>?;
}
