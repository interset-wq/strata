import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:path_provider/path_provider.dart';

import 'core/ffi/engine_ffi.dart';

void main() {
  runApp(const StrataApp());
}

class StrataApp extends StatelessWidget {
  const StrataApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Strata',
      theme: ThemeData(useMaterial3: true, colorSchemeSeed: Colors.indigo),
      home: const BootPage(),
    );
  }
}

/// Boots the embedded Go engine and reports the acceptance facts.
class BootPage extends StatefulWidget {
  const BootPage({super.key});

  @override
  State<BootPage> createState() => _BootPageState();
}

enum BootState { running, ok, failure }

class _BootPageState extends State<BootPage> {
  BootState state = BootState.running;
  EngineStartResult? result;

  @override
  void initState() {
    super.initState();
    _boot();
  }

  Future<void> _boot() async {
    setState(() {
      state = BootState.running;
      result = null;
    });
    try {
      final docs = await getApplicationDocumentsDirectory();
      final assetsDir = await _extractAssets(docs.path);
      final dataDir = Directory('${docs.path}/data');
      await dataDir.create(recursive: true);

      final r = await startAndWaitHealthy(
          EngineFfi(), assetsDir, dataDir.path);
      setState(() {
        result = r;
        state = r.ok ? BootState.ok : BootState.failure;
      });
    } catch (e) {
      setState(() {
        result = EngineStartResult(ok: false, error: '$e');
        state = BootState.failure;
      });
    }
  }

  /// Copies the bundled seed assets from the APK to the filesystem so the
  /// Go engine can read them (it cannot read Flutter asset streams).
  Future<String> _extractAssets(String base) async {
    final dir = Directory('$base/assets');
    await dir.create(recursive: true);
    for (final name in ['manifest.json', 'seed.db.gz']) {
      final f = File('${dir.path}/$name');
      final data = await rootBundle.load('assets/$name');
      await f.writeAsBytes(data.buffer.asUint8List(), flush: true);
    }
    return dir.path;
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Strata — FFI spike')),
      body: switch (state) {
        BootState.running => const Center(child: CircularProgressIndicator()),
        BootState.ok => _OkView(result: result!),
        BootState.failure => _FailureView(
            error: result?.error ?? 'unknown',
            onRetry: _boot,
          ),
      },
    );
  }
}

class _OkView extends StatelessWidget {
  final EngineStartResult result;
  const _OkView({required this.result});

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Text('engine ok @ ${result.addr}'),
          Text('seed_version=${result.seedVersion}'),
          // Phase 1 acceptance: engine reports the seed's book_count=30878.
          Text(
            'book_count=${result.bookCount}',
            style: Theme.of(context).textTheme.headlineMedium,
          ),
        ],
      ),
    );
  }
}

class _FailureView extends StatelessWidget {
  final String error;
  final VoidCallback onRetry;
  const _FailureView({required this.error, required this.onRetry});

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(24),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            const Icon(Icons.error_outline, size: 48, color: Colors.red),
            const SizedBox(height: 12),
            Text(error, textAlign: TextAlign.center),
            const SizedBox(height: 12),
            FilledButton.icon(
              onPressed: onRetry,
              icon: const Icon(Icons.refresh),
              label: const Text('重试'),
            ),
          ],
        ),
      ),
    );
  }
}
