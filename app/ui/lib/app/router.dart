import 'package:go_router/go_router.dart';

import '../pages/boot_page.dart';
import '../pages/home_page.dart';

final router = GoRouter(
  initialLocation: '/boot',
  routes: [
    GoRoute(path: '/boot', builder: (_, _) => const BootPage()),
    GoRoute(path: '/home', builder: (_, _) => const HomePage()),
  ],
);
