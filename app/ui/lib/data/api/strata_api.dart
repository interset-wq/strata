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
      {required String kind, int limit = 50, int offset = 0}) async {
    final body = await _get('/rankings/board', {
      'kind': kind,
      'limit': '$limit',
      if (offset > 0) 'offset': '$offset',
    });
    return (body['items'] as List)
        .map((e) => RankItem.fromJson(e as Map<String, dynamic>))
        .toList();
  }

  Future<DiscoverPage> discover({String? cursor, int limit = 20}) async {
    final body = await _get('/discover', {
      'limit': '$limit',
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

  Future<void> watchAdd(int nid) async {
    await _post('/watchlist/$nid');
  }

  Future<void> watchRemove(int nid) async {
    await _delete('/watchlist/$nid');
  }

  Future<List<RankItem>> randomBooks({int limit = 8}) async {
    final body = await _get('/random', {'limit': '$limit'});
    return (body['items'] as List)
        .map((e) => RankItem.fromJson(e as Map<String, dynamic>))
        .toList();
  }

  Future<List<ShelfItem>> shelfList() async {
    final body = await _get('/shelf');
    return (body['items'] as List)
        .map((e) => ShelfItem.fromJson(e as Map<String, dynamic>))
        .toList();
  }

  /// 编辑精选（seed featured=1，构建期人工选定，非"热门"）。
  Future<List<FeaturedItem>> featured({int limit = 6}) async {
    final body = await _get('/featured', {'limit': '$limit'});
    return (body['items'] as List)
        .map((e) => FeaturedItem.fromJson(e as Map<String, dynamic>))
        .toList();
  }

  Future<void> shelfAdd(int nid) async {
    await _postBody('/shelf', {'nid': nid});
  }

  Future<void> shelfRemove(int nid) async {
    await _delete('/shelf/$nid');
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
        clicks = m['clicks'] as int?;
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

  WatchItem.fromJson(Map<String, dynamic> m)
      : nid = m['nid'] as int,
        title = m['title'] as String,
        author = m['author'] as String,
        genre = m['genre'] as String?,
        coverUrl = m['cover_url'] as String?,
        addedAt = m['added_at'] as int,
        role = m['role'] as String? ?? 'self',
        note = m['note'] as String?;
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

class ShelfItem {
  final int nid;
  final String title;
  final String author;
  final String? genre;
  final int addedAt;

  ShelfItem.fromJson(Map<String, dynamic> m)
      : nid = m['nid'] as int,
        title = m['title'] as String,
        author = m['author'] as String,
        genre = m['genre'] as String?,
        addedAt = m['added_at'] as int;
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
