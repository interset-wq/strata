import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../core/providers.dart';

/// 关注通知列表页（关注 tab 升级，用户裁定 2026-11-26）：watch_events
/// 新→旧全量，AppBar「全部已读」；行点击进详情（库外触发自动收录）。
/// 系统通知（cron worker 抓到更新时）也落到这个入口。
class NotificationsPage extends ConsumerStatefulWidget {
  const NotificationsPage({super.key});

  @override
  ConsumerState<NotificationsPage> createState() => _NotificationsPageState();
}

class _NotificationsPageState extends ConsumerState<NotificationsPage> {
  late Future<Map<String, dynamic>> _data;

  @override
  void initState() {
    super.initState();
    _load();
  }

  void _load() {
    _data = ref.read(bootProvider.future).then((h) => h.api.notifications());
  }

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    const kindLabels = {'words': '字数', 'favs': '收藏', 'status': '状态'};
    return Scaffold(
      appBar: AppBar(
        title: const Text('关注通知'),
        actions: [
          TextButton(
            onPressed: () async {
              final h = await ref.read(bootProvider.future);
              await h.api.notificationsRead();
              _load();
            },
            child: const Text('全部已读'),
          ),
        ],
      ),
      body: FutureBuilder<Map<String, dynamic>>(
        future: _data,
        builder: (context, snap) {
          if (snap.connectionState != ConnectionState.done) {
            return const Center(child: CircularProgressIndicator());
          }
          if (snap.hasError) {
            return Center(child: Text('加载失败：${snap.error}'));
          }
          final items = (snap.data!['items'] as List?) ?? const [];
          if (items.isEmpty) {
            return Center(
              child: Text(
                '暂无通知——关注的书有更新时会在这里提示',
                textAlign: TextAlign.center,
                style: TextStyle(fontSize: 12, color: scheme.onSurfaceVariant),
              ),
            );
          }
          return ListView.builder(
            padding: const EdgeInsets.all(16),
            itemCount: items.length,
            itemBuilder: (context, i) {
              final e = items[i] as Map<String, dynamic>;
              final nid = (e['nid'] as num).toInt();
              final kind =
                  kindLabels[e['kind'] as String? ?? ''] ?? '更新';
              final t = DateTime.fromMillisecondsSinceEpoch(
                  ((e['created_at'] as num?)?.toInt() ?? 0) * 1000);
              return Card(
                margin: const EdgeInsets.only(bottom: 8),
                child: ListTile(
                  onTap: () => context.push('/book/$nid'),
                  title: Text(e['title'] as String? ?? '',
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: const TextStyle(fontSize: 13)),
                  subtitle: Text(
                      '$kind  ${e['old_value'] ?? '—'} → ${e['new_value'] ?? '—'}'
                      '${e['read'] == true ? '' : '  · 未读'}',
                      style: TextStyle(
                          fontSize: 11, color: scheme.onSurfaceVariant)),
                  trailing: Text(
                      '${t.month}/${t.day} '
                      '${t.hour}:${t.minute.toString().padLeft(2, '0')}',
                      style: TextStyle(
                          fontSize: 10, color: scheme.onSurfaceVariant)),
                ),
              );
            },
          );
        },
      ),
    );
  }
}
