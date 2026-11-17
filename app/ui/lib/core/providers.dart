import 'dart:io';

import 'package:flutter/services.dart' show rootBundle;
import 'package:flutter_riverpod/flutter_riverpod.dart';
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
