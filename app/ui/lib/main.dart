import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'app/router.dart';
import 'app/theme.dart';
import 'core/providers.dart';

void main() {
  runApp(const ProviderScope(child: StrataApp()));
}

class StrataApp extends ConsumerWidget {
  const StrataApp({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final themeMode = ref.watch(themeModeProvider);
    final online = ref.watch(connectivityProvider).maybeWhen(
          data: isOnline,
          // Don't flash a false offline state while the first check is
          // still in flight.
          orElse: () => true,
        );

    return MaterialApp.router(
      title: 'Strata',
      theme: StrataTheme.light(),
      darkTheme: StrataTheme.dark(),
      themeMode: themeMode,
      routerConfig: router,
      builder: (context, child) {
        final content = child ?? const SizedBox.shrink();
        if (online) return content;
        final scheme = Theme.of(context).colorScheme;
        return Column(
          children: [
            Material(
              color: scheme.errorContainer,
              child: SafeArea(
                bottom: false,
                child: Center(
                  child: Padding(
                    padding:
                        const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
                    child: Row(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        Icon(Icons.cloud_off,
                            size: 14, color: scheme.onErrorContainer),
                        const SizedBox(width: 6),
                        // Keep it short: long text overflows next to the
                        // debug ribbon on narrow screens.
                        Flexible(
                          child: Text(
                            '离线——本地数据可用，联网功能暂不可用',
                            maxLines: 1,
                            overflow: TextOverflow.ellipsis,
                            style: TextStyle(
                                fontSize: 12,
                                color: scheme.onErrorContainer),
                          ),
                        ),
                      ],
                    ),
                  ),
                ),
              ),
            ),
            Expanded(child: content),
          ],
        );
      },
    );
  }
}
