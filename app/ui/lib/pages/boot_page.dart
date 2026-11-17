import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../core/providers.dart';

/// Shows the engine boot progress. On failure displays diagnostics and a
/// retry button — never an infinite reload loop.
class BootPage extends ConsumerWidget {
  const BootPage({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    ref.listen(bootProvider, (prev, next) {
      if (next is AsyncData) {
        context.go('/home');
      }
    });

    return Scaffold(
      appBar: AppBar(title: const Text('Strata')),
      body: Center(
        child: switch (ref.watch(bootProvider)) {
          AsyncValue(:final isLoading) when isLoading => const Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                CircularProgressIndicator(),
                SizedBox(height: 16),
                Text('正在启动内嵌引擎…'),
              ],
            ),
          AsyncValue(:final error) => _FailureView(
              error: '$error',
              onRetry: () => ref.invalidate(bootProvider),
            ),
        },
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
    return Padding(
      padding: const EdgeInsets.all(24),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          const Icon(Icons.error_outline, size: 48, color: Colors.red),
          const SizedBox(height: 12),
          Text('引擎启动失败',
              style: Theme.of(context).textTheme.titleMedium),
          const SizedBox(height: 8),
          Text(error, textAlign: TextAlign.center),
          const SizedBox(height: 16),
          FilledButton.icon(
            onPressed: onRetry,
            icon: const Icon(Icons.refresh),
            label: const Text('重试'),
          ),
        ],
      ),
    );
  }
}
