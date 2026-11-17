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

  Future<BookDetail> book(int nid) async =>
      BookDetail.fromJson(await _get('/books/$nid') as Map<String, dynamic>);

  Future<List<RankItem>> rankingFavs({
    required int year,
    String? genre,
    int limit = 50,
  }) async {
    final body = await _get('/rankings/favs', {
      'year': '$year',
      'limit': '$limit',
      'genre': ?genre,
    });
    return (body['items'] as List)
        .map((e) => RankItem.fromJson(e as Map<String, dynamic>))
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
    final body = await _get('/search', {
      'q': q,
      'limit': '$limit',
    });
    return (body['items'] as List)
        .map((e) => SearchItem.fromJson(e as Map<String, dynamic>))
        .toList();
  }

  Future<void> close() async => _client.close();
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

  RankItem.fromJson(Map<String, dynamic> m)
      : rank = m['rank'] as int,
        nid = m['nid'] as int,
        title = m['title'] as String,
        author = m['author'] as String,
        genre = m['genre'] as String?,
        estYear = m['est_year'] as int,
        favs = m['favs'] as int,
        favPctl = (m['fav_pctl'] as num?)?.toDouble() ?? 0;
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

  ShortItem.fromJson(Map<String, dynamic> m)
      : rank = m['rank'] as int,
        nid = m['nid'] as int,
        title = m['title'] as String,
        author = m['author'] as String,
        genre = m['genre'] as String?,
        estYear = m['est_year'] as int,
        favs = m['favs'] as int,
        words = m['words'] as int?;
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

class BookDetail {
  final String source; // seed | local
  final String dataEnd;
  final Map<String, dynamic> book;
  final List<String> tags;

  BookDetail.fromJson(Map<String, dynamic> m)
      : source = m['source'] as String,
        dataEnd = m['data_end'] as String,
        book = m['book'] as Map<String, dynamic>,
        tags = (m['tags'] as List).cast<String>();
}
