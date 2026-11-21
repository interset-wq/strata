import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';

import '../pages/author_page.dart';
import '../pages/book_data_page.dart';
import '../pages/book_detail_page.dart';
import '../pages/boot_page.dart';
import '../pages/browse_page.dart';
import '../pages/classic_list_page.dart';
import '../pages/discover_page.dart';
import '../pages/featured_gallery_page.dart';
import '../pages/history_page.dart';
import '../pages/home_page.dart';
import '../pages/ip_books_page.dart';
import '../pages/rankings_page.dart';
import '../pages/calendar_page.dart';
import '../pages/search_page.dart';
import '../pages/image_viewer_page.dart';
import '../pages/random_pool_page.dart';
import '../pages/pool_list_page.dart';
import '../pages/settings_page.dart';
import '../pages/collected_page.dart';
import '../pages/official_ranks_page.dart';
import '../pages/watchlist_page.dart';

/// 底部 Tab 承载 5 个一级页（搜索已让位给发书日历，docs/14 P1）；
/// 搜索是二级页（各页搜索框入口推入），详情页在 Shell 之外全屏推入。
final router = GoRouter(
  initialLocation: '/boot',
  routes: [
    GoRoute(path: '/boot', builder: (_, _) => const BootPage()),
    StatefulShellRoute.indexedStack(
      builder: (context, state, shell) => Scaffold(
        body: shell,
        bottomNavigationBar: NavigationBar(
          selectedIndex: shell.currentIndex,
          onDestinationSelected: (i) =>
              shell.goBranch(i, initialLocation: i == shell.currentIndex),
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
              icon: Icon(Icons.event_available_outlined),
              selectedIcon: Icon(Icons.event_available),
              label: '日历',
            ),
            NavigationDestination(
              icon: Icon(Icons.bookmark_outline),
              selectedIcon: Icon(Icons.bookmark),
              label: '关注',
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
        StatefulShellBranch(
          routes: [GoRoute(path: '/home', builder: (_, _) => const HomePage())],
        ),
        StatefulShellBranch(
          routes: [
            GoRoute(path: '/rankings', builder: (_, _) => const RankingsPage()),
          ],
        ),
        StatefulShellBranch(
          routes: [
            GoRoute(path: '/calendar', builder: (_, _) => const CalendarPage()),
          ],
        ),
        StatefulShellBranch(
          routes: [
            GoRoute(
              path: '/watchlist',
              builder: (_, _) => const WatchlistPage(),
            ),
          ],
        ),
        StatefulShellBranch(
          routes: [
            GoRoute(path: '/settings', builder: (_, _) => const SettingsPage()),
            GoRoute(
              path: '/collected',
              builder: (_, _) => const CollectedPage(),
            ),
            GoRoute(
              path: '/official-ranks',
              builder: (_, _) => const OfficialRanksPage(),
            ),
            GoRoute(
              path: '/official-ranks/:board',
              builder: (_, st) =>
                  OfficialRankDetailPage(board: st.pathParameters['board']!),
            ),
          ],
        ),
      ],
    ),
    GoRoute(
      path: '/book/:nid',
      builder: (_, state) =>
          BookDetailPage(nid: int.parse(state.pathParameters['nid']!)),
    ),
    // 搜索是二级页：入口在首页搜索胶囊与各 form tab 搜索框，不再占底部导航位。
    // 作者页（docs/author-profile-on-demand）：二级全屏，从详情页作者名推入。
    // 当前为数据就绪版（资料头部 + 书目列表），时间轴 UI 待作者规划后改版。
    GoRoute(
      path: '/author',
      builder: (_, state) => AuthorPage(
        author: state.uri.queryParameters['author'] ?? '',
        bookNid: int.tryParse(state.uri.queryParameters['nid'] ?? '') ?? 0,
      ),
    ),
    GoRoute(path: '/search', builder: (_, _) => const SearchPage()),
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
    GoRoute(
      path: '/ip-books',
      builder: (_, state) {
        final group = state.uri.queryParameters['group'] ?? '';
        final label = state.uri.queryParameters['label'] ?? group;
        return IpBooksPage(group: group, label: label);
      },
    ),
    GoRoute(path: '/history', builder: (_, _) => const HistoryPage()),
    GoRoute(
      path: '/serial-random',
      builder: (_, _) =>
          const RandomPoolPage(status: 'serial', title: '随机连载 · 100 本'),
    ),
    GoRoute(
      path: '/finished-random',
      builder: (_, _) =>
          const RandomPoolPage(status: 'finished', title: '随机完结 · 100 本'),
    ),
    GoRoute(
      path: '/browse-random',
      builder: (_, _) =>
          const RandomPoolPage(status: 'browse', title: '随便看看 · 100 本'),
    ),
    // 短篇/中篇 tab：通用榜单列表页（年份/比赛/题材轴在页内切换，
    // 无中间页）+ 随机池。
    GoRoute(
      path: '/short-random',
      builder: (_, _) =>
          const RandomPoolPage(status: 'short', title: '随机短篇 · 100 本'),
    ),
    GoRoute(
      path: '/medium-random',
      builder: (_, _) => const RandomPoolPage(
        status: 'short',
        title: '随机中篇 · 100 本',
        form: 'medium',
      ),
    ),
    GoRoute(
      path: '/dialogue-random',
      builder: (_, _) => const RandomPoolPage(
        status: 'short',
        title: '随机对话 · 100 本',
        form: 'dialogue',
      ),
    ),
    GoRoute(
      path: '/classic-list',
      builder: (_, state) {
        final q = state.uri.queryParameters;
        return ClassicListPage(
          title: q['title'] ?? '短篇',
          form: q['form'] ?? 'short',
          year: int.tryParse(q['year'] ?? ''),
          contest: q['contest'],
          genre: q['genre'],
          wordsBand: q['words-band'],
          order: q['order'] ?? 'favs',
          yearSwitchable: (q['year-switchable'] ?? '') == '1',
          contestSwitchable: (q['contest-switchable'] ?? '') == '1',
          genreSwitchable: (q['genre-switchable'] ?? '') == '1',
          metricSwitchable: (q['metric-switchable'] ?? '') == '1',
        );
      },
    ),
    GoRoute(
      path: '/licensed',
      builder: (_, _) => const PoolListPage(kind: 'licensed', title: '授权作品'),
    ),
    GoRoute(
      path: '/moe-goddess',
      builder: (_, _) => const PoolListPage(kind: 'moe-goddess', title: '萌神获奖'),
    ),
    GoRoute(
      path: '/featured-gallery',
      builder: (_, _) => const FeaturedGalleryPage(),
    ),
    GoRoute(
      path: '/image-viewer/:index',
      builder: (_, state) => ImageViewerPage(
        initialIndex: int.tryParse(state.pathParameters['index'] ?? '0') ?? 0,
      ),
    ),
    GoRoute(
      path: '/book/:nid/data',
      builder: (_, state) =>
          BookDataPage(nid: int.parse(state.pathParameters['nid']!)),
    ),
  ],
);
