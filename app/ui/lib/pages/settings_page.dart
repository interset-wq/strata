import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../core/providers.dart';
import '../data/api/strata_api.dart';

/// 详情刷新限流开关的数据源：引擎 /settings。
final detailRateLimitProvider =
    FutureProvider.autoDispose<EngineSettings>((ref) async {
  final handle = await ref.watch(bootProvider.future);
  return handle.api.settings();
});

/// 设置页：外观、数据状态、口径说明、关于。
class SettingsPage extends ConsumerWidget {
  const SettingsPage({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final meta = ref.watch(metaProvider);
    final mode = ref.watch(themeModeProvider);
    final scheme = Theme.of(context).colorScheme;

    return Scaffold(
      appBar: AppBar(title: const Text('设置')),
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          Card(
            child: ListTile(
              leading: const Icon(Icons.bookmark_added_outlined),
              title: const Text('收录的书'),
              subtitle: const Text('搜索全站自动收录的新书'),
              onTap: () => context.push('/collected'),
            ),
          ),
          const SizedBox(height: 8),
          Card(
            child: ListTile(
              leading: const Icon(Icons.leaderboard_outlined),
              title: const Text('官方榜单（demo）'),
              subtitle: const Text(
                  'SFACG 官方三来源榜单：历史月榜库 / PC 四榜 / 移动五榜'),
              onTap: () => context.push('/official-ranks'),
            ),
          ),
          const SizedBox(height: 16),
          Text('外观', style: Theme.of(context).textTheme.titleLarge),
          const SizedBox(height: 8),
          Card(
            child: RadioGroup<ThemeMode>(
              groupValue: mode,
              onChanged: (m) =>
                  ref.read(themeModeProvider.notifier).state = m!,
              child: Column(
                children: [
                  RadioListTile<ThemeMode>(
                    value: ThemeMode.system,
                    title: const Text('跟随系统'),
                  ),
                  RadioListTile<ThemeMode>(
                    value: ThemeMode.light,
                    title: const Text('浅色（纸面）'),
                  ),
                  RadioListTile<ThemeMode>(
                    value: ThemeMode.dark,
                    title: const Text('深色（夜读）'),
                  ),
                ],
              ),
            ),
          ),
          const SizedBox(height: 16),
          Text('数据', style: Theme.of(context).textTheme.titleLarge),
          const SizedBox(height: 8),
          Card(
            child: meta.when(
              loading: () => const Padding(
                padding: EdgeInsets.all(16),
                child: Center(child: CircularProgressIndicator()),
              ),
              error: (e, _) => Padding(
                padding: const EdgeInsets.all(16),
                child: Text('引擎未就绪：$e',
                    style: TextStyle(color: scheme.error, fontSize: 12)),
              ),
              data: (m) => Padding(
                padding: const EdgeInsets.all(14),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    _row(context, '种子版本', m.manifest.seedVersion),
                    _row(context, '收录书目', '${m.manifest.bookCount} 本'),
                    _row(context, '数据截止', m.manifest.contentEnd),
                  ],
                ),
              ),
            ),
          ),
          const SizedBox(height: 16),
          Text('抓取', style: Theme.of(context).textTheme.titleLarge),
          const SizedBox(height: 8),
          Card(
            child: ref.watch(detailRateLimitProvider).when(
                  loading: () => const Padding(
                    padding: EdgeInsets.all(16),
                    child: Center(child: CircularProgressIndicator()),
                  ),
                  error: (e, _) => Padding(
                    padding: const EdgeInsets.all(16),
                    child: Text('引擎未就绪：$e',
                        style: TextStyle(color: scheme.error, fontSize: 12)),
                  ),
                  data: (st) => SwitchListTile(
                    title: const Text('详情刷新限流（24 小时一次）'),
                    subtitle: Text(
                      st.detailRateLimitEnabled
                          ? '同一本书每天最多向官方发起一次刷新请求'
                          : '已关闭——可随时手动刷新（请节制）',
                      style: const TextStyle(fontSize: 12),
                    ),
                    value: st.detailRateLimitEnabled,
                    onChanged: (v) async {
                      await ref
                          .read(bootProvider.future)
                          .then((h) => h.api.setDetailRateLimitEnabled(v));
                      ref.invalidate(detailRateLimitProvider);
                    },
                  ),
                ),
          ),
          const SizedBox(height: 16),
          Text('口径说明', style: Theme.of(context).textTheme.titleLarge),
          const SizedBox(height: 8),
          Card(
            child: Padding(
              padding: const EdgeInsets.all(14),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  _note(context, '种子数据随 App 一次性分发，长期不更新——'
                      '榜单与统计反映的是数据截止时点的快照'),
                  _note(context, '观测数据只保存在本机 user.db，'
                      '保留 180 天，不上传任何服务器'),
                  _note(context, '详情刷新走全局限速（1 秒间隔），'
                      '前台操作优先，失败不重试'),
                ],
              ),
            ),
          ),
          const SizedBox(height: 16),
          Text('关于', style: Theme.of(context).textTheme.titleLarge),
          const SizedBox(height: 8),
          Card(
            child: Padding(
              padding: const EdgeInsets.all(14),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  _row(context, '名称', '书层 Strata'),
                  _row(context, '许可', 'AGPL-3.0'),
                  _row(context, '数据来源', 'SFACG 菠萝包轻小说公开页面'),
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }

  Widget _row(BuildContext context, String label, String value) {
    final scheme = Theme.of(context).colorScheme;
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 4),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: [
          Text(label,
              style:
                  TextStyle(fontSize: 13, color: scheme.onSurfaceVariant)),
          Flexible(
            child: Text(value,
                textAlign: TextAlign.right,
                style: const TextStyle(fontSize: 13)),
          ),
        ],
      ),
    );
  }

  Widget _note(BuildContext context, String text) {
    final scheme = Theme.of(context).colorScheme;
    return Padding(
      padding: const EdgeInsets.only(bottom: 8),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Padding(
            padding: const EdgeInsets.only(top: 2, right: 8),
            child: Icon(Icons.info_outline, size: 13, color: scheme.secondary),
          ),
          Expanded(
            child: Text(text,
                style: TextStyle(
                    fontSize: 12, color: scheme.onSurfaceVariant, height: 1.5)),
          ),
        ],
      ),
    );
  }
}
