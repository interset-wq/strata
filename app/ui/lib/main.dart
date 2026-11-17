import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'app/router.dart';
import 'app/theme.dart';

void main() {
  runApp(const ProviderScope(child: StrataApp()));
}

class StrataApp extends ConsumerWidget {
  const StrataApp({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    return MaterialApp.router(
      title: 'Strata',
      theme: StrataTheme.light(),
      darkTheme: StrataTheme.dark(),
      routerConfig: router,
    );
  }
}
