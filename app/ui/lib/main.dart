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
    return MaterialApp.router(
      title: 'Strata',
      theme: StrataTheme.light(),
      darkTheme: StrataTheme.dark(),
      themeMode: themeMode,
      routerConfig: router,
    );
  }
}
