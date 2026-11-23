import 'dart:convert';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:path_provider/path_provider.dart';
import 'package:share_plus/share_plus.dart';

import '../core/providers.dart';
import '../data/api/strata_api.dart';

/// 导出用户本地数据：引擎 /export 全量 dump → 临时 JSON → 系统分享面板。
Future<void> _exportData(BuildContext context, WidgetRef ref) async {
  final messenger = ScaffoldMessenger.of(context);
  try {
    final h = await ref.read(bootProvider.future);
    final data = await h.api.exportData();
    final dir = await getTemporaryDirectory();
    final file = File(
        '${dir.path}/strata-export-${DateTime.now().millisecondsSinceEpoch}.json');
    await file
        .writeAsString(const JsonEncoder.withIndent('  ').convert(data));
    await SharePlus.instance.share(
      ShareParams(files: [XFile(file.path)], subject: 'Strata 数据备份'),
    );
  } catch (e) {
    messenger.showSnackBar(SnackBar(content: Text('导出失败：$e')));
  }
}

/// 详情刷新限流开关的数据源：引擎 /settings。
final detailRateLimitProvider =
    FutureProvider.autoDispose<EngineSettings>((ref) async {
  final handle = await ref.watch(bootProvider.future);
  return handle.api.settings();
});

/// 工作台测试书开关的数据源：引擎 /dev/test-book（docs/07 开发辅助）。
final testBookProvider =
    FutureProvider.autoDispose<TestBook>((ref) async {
  final handle = await ref.watch(bootProvider.future);
  return handle.api.testBook();
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
                  data: (st) => Column(
                    children: [
                      SwitchListTile(
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
                      // App API 增强通路（docs/05 §3.5）：开关持久化为引擎
                      // 设置项；认证是 App 内置凭据自签（sfacg-app-api.md §1），
                      // 无需用户输入任何凭据。
                      SwitchListTile(
                        title: const Text('App API 增强抓取'),
                        subtitle: Text(
                          st.appApiEnabled
                              ? '刷新优先走 App API（精确字数/评分等），失败自动回落'
                              : '关闭——刷新只走移动版页面（默认）',
                          style: const TextStyle(fontSize: 12),
                        ),
                        value: st.appApiEnabled,
                        onChanged: (v) async {
                          await ref
                              .read(bootProvider.future)
                              .then((h) => h.api.setAppAPIEnabled(v));
                          ref.invalidate(detailRateLimitProvider);
                        },
                      ),
                    ],
                  ),
                ),
          ),
          const SizedBox(height: 16),
          Text('数据', style: Theme.of(context).textTheme.titleLarge),
          const SizedBox(height: 8),
          Card(
            child: ListTile(
              leading: const Icon(Icons.ios_share),
              title: const Text('导出数据'),
              subtitle: const Text(
                  '观察 / 关注 / 浏览足迹 → JSON 文件分享出去备份（无云同步）',
                  style: TextStyle(fontSize: 12)),
              onTap: () => _exportData(context, ref),
            ),
          ),
          const SizedBox(height: 16),
          Text('测试工具', style: Theme.of(context).textTheme.titleLarge),
          const SizedBox(height: 8),
          Card(
            child: ref.watch(testBookProvider).when(
              loading: () => const Padding(
                padding: EdgeInsets.all(16),
                child: Center(child: CircularProgressIndicator()),
              ),
              error: (e, _) => Padding(
                padding: const EdgeInsets.all(16),
                child: Text('引擎未就绪：$e',
                    style: TextStyle(color: scheme.error, fontSize: 12)),
              ),
              data: (tb) => SwitchListTile(
                title: const Text('工作台测试书'),
                subtitle: Text(
                  tb.present
                      ? '已注入「${tb.title}」：${tb.rows ?? 0} 条模拟观测，关注 tab 可见'
                      : '注入一本带 60 天模拟观测数据的虚构书，用于开发作者工作台',
                  style: const TextStyle(fontSize: 12),
                ),
                value: tb.present,
                onChanged: (v) async {
                  final h = await ref.read(bootProvider.future);
                  try {
                    if (v) {
                      await h.api.injectTestBook();
                    } else {
                      await h.api.removeTestBook();
                    }
                  } finally {
                    // 成败都重新同步开关状态
                    ref.invalidate(testBookProvider);
                  }
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
