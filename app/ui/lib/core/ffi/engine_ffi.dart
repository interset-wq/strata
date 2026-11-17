import 'dart:async';
import 'dart:convert';
import 'dart:ffi';
import 'dart:io';

import 'package:ffi/ffi.dart';

/// Dart binding for the c-shared Go engine (cmd/ffi).
///
/// Contract (app/docs/08-engine-api.md): strata_start returns a JSON string
/// {ok, addr?, seed_version?, book_count?, licensed_count?, error?}.
class EngineStartResult {
  final bool ok;
  final String? addr;
  final String? seedVersion;
  final int? bookCount;
  final String? error;

  EngineStartResult({
    required this.ok,
    this.addr,
    this.seedVersion,
    this.bookCount,
    this.error,
  });

  factory EngineStartResult.fromJson(String raw) {
    final m = jsonDecode(raw) as Map<String, dynamic>;
    return EngineStartResult(
      ok: m['ok'] as bool? ?? false,
      addr: m['addr'] as String?,
      seedVersion: m['seed_version'] as String?,
      bookCount: m['book_count'] as int?,
      error: m['error'] as String?,
    );
  }
}

typedef _StartNative = Pointer<Utf8> Function(Pointer<Utf8>, Pointer<Utf8>);
typedef _StartDart = Pointer<Utf8> Function(Pointer<Utf8>, Pointer<Utf8>);
typedef _StopNative = Pointer<Utf8> Function();
typedef _StopDart = Pointer<Utf8> Function();
typedef _FreeNative = Void Function(Pointer<Utf8>);
typedef _FreeDart = void Function(Pointer<Utf8>);

class EngineFfi {
  late DynamicLibrary _lib;
  late _StartDart _start;
  late _StopDart _stop;
  late _FreeDart _free;

  EngineFfi() {
    _lib = DynamicLibrary.open('libstrata.so');
    _start = _lib.lookupFunction<_StartNative, _StartDart>('strata_start');
    _stop = _lib.lookupFunction<_StopNative, _StopDart>('strata_stop');
    _free = _lib.lookupFunction<_FreeNative, _FreeDart>('strata_free');
  }

  EngineStartResult start(String assetsDir, String dataDir) {
    final a = assetsDir.toNativeUtf8();
    final d = dataDir.toNativeUtf8();
    try {
      final p = _start(a, d);
      try {
        return EngineStartResult.fromJson(p.toDartString());
      } finally {
        _free(p);
      }
    } finally {
      calloc.free(a);
      calloc.free(d);
    }
  }

  EngineStartResult stop() {
    final p = _stop();
    try {
      return EngineStartResult.fromJson(p.toDartString());
    } finally {
      _free(p);
    }
  }
}

/// Starts the engine and polls /healthz until it answers, per contract:
/// 200ms interval, 15s total timeout.
Future<EngineStartResult> startAndWaitHealthy(
    EngineFfi ffi, String assetsDir, String dataDir) async {
  final result = ffi.start(assetsDir, dataDir);
  if (!result.ok) return result;

  final deadline = DateTime.now().add(const Duration(seconds: 15));
  final client = HttpClient();
  try {
    while (DateTime.now().isBefore(deadline)) {
      try {
        final req =
            await client.getUrl(Uri.parse('${result.addr}/strata/healthz'));
        final resp = await req.close().timeout(const Duration(seconds: 2));
        if (resp.statusCode == 200) {
          await resp.drain();
          return result;
        }
        await resp.drain();
      } on TimeoutException {
        // fall through and retry
      } on SocketException {
        // engine not accepting yet
      }
      await Future<void>.delayed(const Duration(milliseconds: 200));
    }
    return EngineStartResult(ok: false, error: 'healthz timeout after 15s');
  } finally {
    client.close();
  }
}
