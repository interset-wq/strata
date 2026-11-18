import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';

import '../pages/book_data_page.dart';
import '../pages/book_detail_page.dart';
import '../pages/boot_page.dart';
import '../pages/browse_page.dart';
import '../pages/discover_page.dart';
import '../pages/history_page.dart';
import '../pages/home_page.dart';
import '../pages/rankings_page.dart';
import '../pages/search_page.dart';
import '../pages/random_pool_page.dart';
import '../pages/watchlist_page.dart';
import '../pages/settings_page.dart';
import '../pages/shelf_page.dart';

/// 底部 Tab 承载 4 个一级页；详情页是二级页，在 Shell 之外全屏推入。
final router = GoRouter(
  initialLocation: '/boot',
  routes: [
    GoRoute(path: '/boot', builder: (_, _) => const BootPage()),
    StatefulShellRoute.indexedStack(
      builder: (context, state, shell) => Scaffold(
        body: shell,
        bottomNavigationBar: NavigationBar(
          selectedIndex: shell.currentIndex,
          onDestinationSelected: (i) => shell.goBranch(
            i,
            initialLocation: i == shell.currentIndex,
          ),
          destinations: const [
            NavigationDestination(
              icon: Icon(Icons.home_outlined),
              selectedIcon: Icon(Icons.home),
              label: '首页',
            ),
            NavigationDestination(
              icon: Icon(Icons.leaderboard_outlined),
              selectedIcon: Icon(Icons.leaderboard),
              label: '榜单',
            ),
            NavigationDestination(
              icon: Icon(Icons.search_outlined),
              selectedIcon: Icon(Icons.search),
              label: '搜索',
            ),
            NavigationDestination(
              icon: Icon(Icons.collections_bookmark_outlined),
              selectedIcon: Icon(Icons.collections_bookmark),
              label: '书架',
            ),
            NavigationDestination(
              icon: Icon(Icons.settings_outlined),
              selectedIcon: Icon(Icons.settings),
              label: '设置',
            ),
          ],
        ),
      ),
      branches: [
        StatefulShellBranch(routes: [
          GoRoute(path: '/home', builder: (_, _) => const HomePage()),
        ]),
        StatefulShellBranch(routes: [
          GoRoute(path: '/rankings', builder: (_, _) => const RankingsPage()),
        ]),
        StatefulShellBranch(routes: [
          GoRoute(path: '/search', builder: (_, _) => const SearchPage()),
        ]),
        StatefulShellBranch(routes: [
          GoRoute(path: '/shelf', builder: (_, _) => const ShelfPage()),
        ]),
        StatefulShellBranch(routes: [
          GoRoute(path: '/settings', builder: (_, _) => const SettingsPage()),
        ]),
      ],
    ),
    GoRoute(
      path: '/book/:nid',
      builder: (_, state) => BookDetailPage(
        nid: int.parse(state.pathParameters['nid']!),
      ),
    ),
    GoRoute(
      path: '/browse',
      builder: (_, state) => BrowsePage(
        mode: BrowseMode.values.firstWhere(
          (m) => m.name == (state.uri.queryParameters['mode'] ?? ''),
          orElse: () => BrowseMode.category,
        ),
      ),
    ),
    GoRoute(path: '/discover', builder: (_, _) => const DiscoverPage()),
    GoRoute(path: '/watchlist', builder: (_, _) => const WatchlistPage()),
    GoRoute(path: '/history', builder: (_, _) => const HistoryPage()),
    GoRoute(path: '/serial-random',
        builder: (_, _) => const RandomPoolPage(
            status: 'serial', title: '随机连载 · 100 本')),
    GoRoute(path: '/finished-random',
        builder: (_, _) => const RandomPoolPage(
            status: 'finished', title: '随机完结 · 100 本')),
    GoRoute(path: '/browse-random',
        builder: (_, _) => const RandomPoolPage(
            status: 'browse', title: '随便看看 · 100 本')),
    GoRoute(
      path: '/book/:nid/data',
      builder: (_, state) => BookDataPage(
        nid: int.parse(state.pathParameters['nid']!),
      ),
    ),
  ],
);
