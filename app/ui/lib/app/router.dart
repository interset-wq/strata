import 'package:go_router/go_router.dart';

import '../pages/book_detail_page.dart';
import '../pages/boot_page.dart';
import '../pages/home_page.dart';
import '../pages/rankings_page.dart';
import '../pages/search_page.dart';
import '../pages/shelf_page.dart';

final router = GoRouter(
  initialLocation: '/boot',
  routes: [
    GoRoute(path: '/boot', builder: (_, _) => const BootPage()),
    GoRoute(path: '/home', builder: (_, _) => const HomePage()),
    GoRoute(path: '/rankings', builder: (_, _) => const RankingsPage()),
    GoRoute(path: '/search', builder: (_, _) => const SearchPage()),
    GoRoute(path: '/shelf', builder: (_, _) => const ShelfPage()),
    GoRoute(
      path: '/book/:nid',
      builder: (_, state) => BookDetailPage(
        nid: int.parse(state.pathParameters['nid']!),
      ),
    ),
  ],
);
