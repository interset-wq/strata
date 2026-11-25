import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';

import '../pages/author_page.dart';
import '../pages/book_data_page.dart';
import '../pages/book_detail_page.dart';
import '../pages/booklist_detail_page.dart';
import '../pages/booklists_page.dart';
import '../pages/boot_page.dart';
import '../pages/browse_page.dart';
import '../pages/contest_archive_page.dart';
import '../pages/contest_list_page.dart';
import '../pages/roster_page.dart';
import '../pages/classic_list_page.dart';
import '../pages/discover_page.dart';
import '../pages/featured_gallery_page.dart';
import '../pages/history_page.dart';
import '../pages/eras_explorer_page.dart';
import '../pages/home_page.dart';
import '../pages/ip_books_page.dart';
import '../pages/author_rank_page.dart';
import '../pages/quant_list_page.dart';
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
              label: '比赛',
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
            GoRoute(
              path: '/contests',
              builder: (context, state) => ContestListPage(
                  initialTab: state.uri.queryParameters['tab']),
            ),
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
        initialContest: state.uri.queryParameters['c'],
      ),
    ),
    // 赛事档案（docs/contest-display-in-app.md 形态一）：本地零请求视图，
    // 库外参赛规模/获奖属 P1 清单 API。
    // 赛事档案全屏页（从详情页等根级页面进入）。不能复用 /contests——
    // 那是底部导航 shell 分支内的路径，从 shell 外 push 会报错。
    GoRoute(
      path: '/contest-archive',
      builder: (context, state) => ContestListPage(
          initialTab: state.uri.queryParameters['tab']),
    ),
    // 官方清单（形态二，按需 + 引擎按页缓存）；静态段必须在
    // /contests/:name 之前注册，否则 'roster' 会被当赛事名吃掉。
    GoRoute(
      path: '/contests/roster',
      builder: (_, state) => RosterPage(
        contest: state.uri.queryParameters['c'] ?? '',
      ),
    ),
    GoRoute(
      path: '/contests/:name',
      builder: (_, state) =>
          ContestArchivePage(name: state.pathParameters['name']!),
    ),
    // 官方书单（docs/booklist-in-app.md）：顺序 id 探测浏览，引擎 24h 缓存；
    // 静态段在参数段之前注册（与 /contests/roster 同款）。
    GoRoute(path: '/booklists', builder: (_, _) => const BooklistsPage()),
    GoRoute(
      path: '/booklists/:id',
      builder: (_, state) => BooklistDetailPage(
        id: int.tryParse(state.pathParameters['id'] ?? '') ?? 0,
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
        path: '/eras-explorer',
        builder: (_, _) => const ErasExplorerPage()),
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
      path: '/quant-list',
      builder: (_, loc) => QuantListPage(
        // 按 form 隔离出页（用户 2026-11-25：app 一切按 form 隔离，
        // 无页内切换）：长篇 tab 默认 / 对话 tab 传 form=dialogue。
        form: loc.uri.queryParameters['form'] ?? 'long',
      ),
    ),
    GoRoute(
      path: '/author-ranks',
      builder: (_, loc) => AuthorRankPage(
        // 同隔离原则（docs/author-rank.md §9）：form 缺省 long。
        form: loc.uri.queryParameters['form'] ?? 'long',
      ),
    ),
    GoRoute(
      path: '/classic-list',
      builder: (_, state) {
        final q = state.uri.queryParameters;
        return ClassicListPage(
          title: q['title'] ?? '短篇',
          form: q['form'] ?? 'short',
          contest: q['contest'],
          wordsBand: q['words-band'],
          order: q['order'] ?? 'favs',
          contestSwitchable: (q['contest-switchable'] ?? '') == '1',
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
