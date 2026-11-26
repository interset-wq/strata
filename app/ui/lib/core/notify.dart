import 'dart:async';

import 'package:flutter_local_notifications/flutter_local_notifications.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'providers.dart';

/// 关注通知服务（关注 tab 升级，用户裁定 2026-11-26）：引擎 cron worker
/// （watcher，docs/06 U5）把关注书的观测变化写进 watch_events，Flutter
/// 侧定期拉未读并发一条系统通知。app 被杀即无抓取也无通知——cron 与
/// 通知都是 app 存活期行为（docs/06 口径：前台活跃期检查，不叠加全库调度）。
final _plugin = FlutterLocalNotificationsPlugin();
bool _initialized = false;

Future<void> _init() async {
  if (_initialized) return;
  await _plugin.initialize(
    settings: const InitializationSettings(
      android: AndroidInitializationSettings('@mipmap/ic_launcher'),
    ),
  );
  await _plugin
      .resolvePlatformSpecificImplementation<
          AndroidFlutterLocalNotificationsPlugin>()
      ?.requestNotificationsPermission();
  _initialized = true;
}

/// 拉一次未读并发系统通知（>0 才发；同 id 覆盖，不刷屏）。
/// App 启动即挂载：boot 就绪后立即拉一次，之后每 5 分钟一次。
final notificationsPollerProvider = Provider((ref) {
  Future<void> tick() async {
    try {
      final handle = await ref.read(bootProvider.future);
      final body = await handle.api.notifications();
      final unread = (body['unread'] as num?)?.toInt() ?? 0;
      if (unread <= 0) return;
      await _init();
      await _plugin.show(
        id: 1001,
        title: '关注更新',
        body: '关注的书有 $unread 条未读更新',
        notificationDetails: const NotificationDetails(
          android: AndroidNotificationDetails(
            'watch',
            '关注更新',
            importance: Importance.defaultImportance,
            priority: Priority.defaultPriority,
          ),
        ),
      );
    } catch (_) {
      // 引擎未就绪/离线：静默，下个 tick 再试。
    }
  }

  unawaited(() async {
    await ref.read(bootProvider.future);
    await tick();
  }());
  final timer =
      Timer.periodic(const Duration(minutes: 5), (_) => unawaited(tick()));
  ref.onDispose(() => timer.cancel());
});
