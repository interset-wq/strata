import 'dart:convert';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:path_provider/path_provider.dart';
import 'package:share_plus/share_plus.dart';
import 'package:url_launcher/url_launcher.dart';

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

/// 详情刷新限流开关的数据源：引擎 /settings（定义移至 core/providers.dart，
/// 详情页也在监听它——settings 改开关后解除刷新按钮禁用）。

/// 工作台测试书开关的数据源：引擎 /dev/test-book（docs/07 开发辅助）。
final testBookProvider =
    FutureProvider.autoDispose<TestBook>((ref) async {
  final handle = await ref.watch(bootProvider.future);
  return handle.api.testBook();
});

/// 设置页：阅读 / 数据 / 抓取 / 开发者 / 关于五组，一组一张卡、卡内行同构
/// （2026-11-26 改版：旧页 8 张卡 8 个衬线大标题、两种「数据」同名分组、
/// 主题独占三行高度，节奏乱；现按分组小标题 + 一行一事收口。
/// 关于组 = App 信息页 + GitHub 仓库 / Issues + QQ 群号复制）。
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
        padding: const EdgeInsets.fromLTRB(16, 8, 16, 24),
        children: [
          _label(context, '阅读'),
          _card(context, [
            _navRow(context,
                icon: Icons.palette_outlined,
                title: '主题',
                value: _modeLabel(mode),
                onTap: () => _pickTheme(context, ref, mode)),
          ]),
          _label(context, '数据'),
          _card(context, [
            _valueRow(context, '种子版本', meta, (m) => m.manifest.seedVersion),
            _valueRow(context, '收录书目', meta,
                (m) => '${m.manifest.bookCount} 本'),
            _valueRow(context, '数据截止', meta, (m) => m.manifest.contentEnd),
          ]),
          _card(context, [
            _navRow(context,
                icon: Icons.bookmark_added_outlined,
                iconColor: scheme.secondary,
                title: '收录的书',
                subtitle: '搜索全站自动收录的新书',
                onTap: () => context.push('/collected')),
            _navRow(context,
                icon: Icons.ios_share,
                title: '导出数据',
                subtitle: '观察 / 关注 / 浏览足迹 → JSON 文件备份（无云同步）',
                onTap: () => _exportData(context, ref)),
          ]),
          _label(context, '抓取'),
          _card(context, [
            _switchRow(context, ref,
                title: '每日刷新限额',
                subtitleOf: (st) => st.detailRateLimitEnabled
                    ? '开启：每本书每天最多 1 次刷新请求（0 点重置）'
                    : '关闭：每本书每天最多 5 次刷新请求（0 点重置）',
                watch: detailRateLimitProvider,
                read: (st) => st.detailRateLimitEnabled,
                write: (h, v) => h.api.setDetailRateLimitEnabled(v)),
            _switchRow(context, ref,
                title: 'App API 增强抓取',
                subtitleOf: (st) => st.appApiEnabled
                    ? '刷新优先走 App API（精确字数/评分等），失败自动回落'
                    : '关闭——刷新只走移动版页面（默认）',
                watch: detailRateLimitProvider,
                read: (st) => st.appApiEnabled,
                // App API 是内置凭据自签（sfacg-app-api.md §1），无需用户输入。
                write: (h, v) => h.api.setAppAPIEnabled(v)),
            _switchRow(context, ref,
                title: '关注时同时开启定时刷新',
                subtitleOf: (st) => st.watchDefaultActive
                    ? '开启——关注即加入关注列表并由引擎定时抓取更新'
                    : '关闭——关注仅加入关注列表，不发起定时抓取',
                watch: detailRateLimitProvider,
                read: (st) => st.watchDefaultActive,
                write: (h, v) => h.api.setWatchDefaultActive(v)),
            _scheduleRow(context, ref),
          ]),
          _card(context, [
            _fold(context,
                icon: Icons.info_outline,
                title: '口径说明',
                children: [
                  _note(context, '种子数据随 App 一次性分发，长期不更新——'
                      '榜单与统计反映的是数据截止时点的快照'),
                  _note(context, '观测数据只保存在本机 user.db，'
                      '保留 180 天，不上传任何服务器'),
                  _note(context, '详情刷新走全局限速（1 秒间隔），'
                      '前台操作优先，失败不重试'),
                ]),
          ]),
          _label(context, '开发者'),
          _card(context, [
            _fold(context,
                icon: Icons.developer_mode_outlined,
                title: '测试工具',
                // 里面是整行控件，行自带 14 缩进，不再叠加 childrenPadding
                childrenPadding: const EdgeInsets.only(bottom: 6),
                children: [
                  _switchRow(context, ref,
                      title: '工作台测试书',
                      subtitleOf: (tb) => tb.present
                          ? '已注入「${tb.title}」：${tb.rows ?? 0} 条模拟观测，关注 tab 可见'
                          : '注入一本带 60 天模拟观测数据的虚构书，用于开发作者工作台',
                      watch: testBookProvider,
                      read: (tb) => tb.present,
                      write: (h, v) async {
                        if (v) {
                          await h.api.injectTestBook();
                        } else {
                          await h.api.removeTestBook();
                        }
                      }),
                  _seedDateRow(context, ref),
                ]),
          ]),
          _label(context, '关于'),
          _card(context, [
            _navRow(context,
                icon: Icons.info_outline,
                title: 'App 信息',
                subtitle: '版本、许可与数据来源',
                onTap: () => context.push('/about')),
            _navRow(context,
                icon: Icons.code,
                title: 'GitHub 仓库',
                subtitle: 'github.com/interset-wq/strata',
                onTap: () => _openUrl(context,
                    'https://github.com/interset-wq/strata')),
            _navRow(context,
                icon: Icons.bug_report_outlined,
                title: '问题反馈',
                subtitle: 'GitHub Issues：报告问题与功能建议',
                onTap: () => _openUrl(context,
                    'https://github.com/interset-wq/strata/issues')),
            _navRow(context,
                icon: Icons.forum_outlined,
                title: 'QQ 群',
                subtitle: '点击复制群号',
                value: '881041631',
                showChevron: false,
                onTap: () => _copyQq(context)),
          ]),
          Padding(
            padding: const EdgeInsets.only(top: 18),
            child: Center(
              child: Text(
                '书层 Strata · AGPL-3.0\n数据来自 SFACG 菠萝包轻小说公开页面',
                textAlign: TextAlign.center,
                style: TextStyle(fontSize: 11, color: scheme.onSurfaceVariant, height: 1.6),
              ),
            ),
          ),
        ],
      ),
    );
  }

  static String _modeLabel(ThemeMode m) => switch (m) {
        ThemeMode.system => '跟随系统',
        ThemeMode.light => '浅色（纸面）',
        ThemeMode.dark => '深色（夜读）',
      };

  Future<void> _openUrl(BuildContext context, String url) async {
    var ok = false;
    try {
      ok = await launchUrl(Uri.parse(url),
          mode: LaunchMode.externalApplication);
    } catch (_) {}
    if (!context.mounted || ok) return;
    ScaffoldMessenger.of(context)
        .showSnackBar(const SnackBar(content: Text('无法打开浏览器')));
  }

  Future<void> _copyQq(BuildContext context) async {
    await Clipboard.setData(const ClipboardData(text: '881041631'));
    if (!context.mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(const SnackBar(
        content: Text('群号已复制'), duration: Duration(seconds: 1)));
  }

  /// 主题选择：一行收口，进底部面板选（旧页用整张 RadioListTile 卡占三行）。
  void _pickTheme(BuildContext context, WidgetRef ref, ThemeMode current) {
    showModalBottomSheet<void>(
      context: context,
      showDragHandle: true,
      builder: (ctx) => Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          for (final m in ThemeMode.values)
            ListTile(
              title: Text(_modeLabel(m)),
              trailing: m == current
                  ? Icon(Icons.check, color: Theme.of(ctx).colorScheme.primary)
                  : null,
              onTap: () {
                ref.read(themeModeProvider.notifier).state = m;
                Navigator.of(ctx).pop();
              },
            ),
        ],
      ),
    );
  }

  Widget _label(BuildContext context, String text) {
    final scheme = Theme.of(context).colorScheme;
    return Padding(
      padding: const EdgeInsets.fromLTRB(4, 14, 4, 6),
      child: Text(text,
          style: TextStyle(
              fontSize: 11,
              letterSpacing: 1,
              color: scheme.onSurfaceVariant)),
    );
  }

  /// 一组一张卡：卡内只放行，行间一根分隔线（左侧留 14 缩进，不顶到圆角）。
  Widget _card(BuildContext context, List<Widget> rows) {
    final scheme = Theme.of(context).colorScheme;
    return Card(
      margin: const EdgeInsets.only(bottom: 10),
      child: Column(
        children: [
          for (var i = 0; i < rows.length; i++) ...[
            if (i > 0)
              Container(
                height: 1,
                margin: const EdgeInsets.only(left: 14),
                color: scheme.outline,
              ),
            rows[i],
          ],
        ],
      ),
    );
  }

  /// 只读键值行（无图标：三行同图标是噪音，值右对齐即可扫）。
  /// 引擎未就绪时值位显示状态，不整卡报错（旧页三张卡各转各的圈）。
  Widget _valueRow(BuildContext context, String label, AsyncValue<Meta> meta,
      String Function(Meta m) pick) {
    final scheme = Theme.of(context).colorScheme;
    final value = meta.maybeWhen(
        data: pick, orElse: () => meta.isLoading ? '…' : '引擎未就绪');
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 11),
      child: Row(
        children: [
          Expanded(
              child: Text(label,
                  style: TextStyle(
                      fontSize: 13, color: scheme.onSurfaceVariant))),
          Flexible(
            child: Text(value,
                textAlign: TextAlign.right,
                style: const TextStyle(fontSize: 13)),
          ),
        ],
      ),
    );
  }

  Widget _navRow(BuildContext context,
      {required IconData icon,
      required String title,
      String? subtitle,
      String? value,
      bool showChevron = true,
      Color? iconColor,
      required VoidCallback onTap}) {
    final scheme = Theme.of(context).colorScheme;
    return ListTile(
      contentPadding: const EdgeInsets.symmetric(horizontal: 14, vertical: 2),
      leading: Icon(icon, size: 20, color: iconColor ?? scheme.onSurfaceVariant),
      title: Text(title, style: const TextStyle(fontSize: 13)),
      subtitle: subtitle == null
          ? null
          : Text(subtitle, style: const TextStyle(fontSize: 11, height: 1.4)),
      trailing: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          if (value != null)
            Text(value, style: TextStyle(fontSize: 12, color: scheme.onSurfaceVariant)),
          if (showChevron)
            Icon(Icons.chevron_right, size: 20, color: scheme.onSurfaceVariant),
        ],
      ),
      onTap: onTap,
    );
  }

  /// 开关行：状态说明由数据本身给（开/关各说一句，含注入书名等实况），
  /// 引擎未就绪时整行禁用。
  Widget _switchRow<T>(BuildContext context, WidgetRef ref,
      {required String title,
      required String Function(T data) subtitleOf,
      required FutureProvider<T> watch,
      required bool Function(T data) read,
      required Future<void> Function(EngineHandle h, bool v) write}) {
    final async = ref.watch(watch);
    final on = async.maybeWhen(data: read, orElse: () => false);
    return SwitchListTile(
      contentPadding: const EdgeInsets.symmetric(horizontal: 14, vertical: 2),
      title: Text(title, style: const TextStyle(fontSize: 13)),
      subtitle: Text(
          async.maybeWhen(
              data: subtitleOf,
              orElse: () => async.isLoading ? '读取中…' : '引擎未就绪'),
          style: const TextStyle(fontSize: 11, height: 1.4)),
      value: on,
      onChanged: async is AsyncData<T>
          ? (v) async {
              final h = await ref.read(bootProvider.future);
              await write(h, v);
              ref.invalidate(watch);
            }
          : null,
    );
  }

  /// 定时抓取节奏（watch_schedule）：全局覆盖条目级间隔。每分钟档仅供
  /// 测试（每个 tick 都会发起真实请求，风控与耗电风险自负）。
  static const _scheduleOptions = <String, String>{
    '': '按条目间隔（默认）',
    '30s': '每 30 秒（测试用）',
    '1min': '每分钟（测试用）',
    'hourly': '每小时',
    '6h': '每 6 小时',
    '12h': '每 12 小时',
    'daily': '每天整点（0 点后一次）',
  };

  Widget _scheduleRow(BuildContext context, WidgetRef ref) {
    final async = ref.watch(detailRateLimitProvider);
    final current =
        async.maybeWhen(data: (st) => st.watchSchedule, orElse: () => '');
    return ListTile(
      contentPadding: const EdgeInsets.symmetric(horizontal: 14, vertical: 2),
      title: const Text('定时抓取节奏', style: TextStyle(fontSize: 13)),
      subtitle: Text(
        async.maybeWhen(
          data: (st) =>
              '当前：${_scheduleOptions[st.watchSchedule] ?? '按条目间隔（默认）'}',
          orElse: () => async.isLoading ? '读取中…' : '引擎未就绪',
        ),
        style: const TextStyle(fontSize: 11, height: 1.4),
      ),
      trailing: const Icon(Icons.chevron_right, size: 20),
      onTap: async is AsyncData<EngineSettings>
          ? () async {
              final picked = await showDialog<String>(
                context: context,
                builder: (context) => SimpleDialog(
                  title: const Text('定时抓取节奏',
                      style: TextStyle(fontSize: 16)),
                  children: [
                    RadioGroup<String>(
                      groupValue: current,
                      onChanged: (v) => Navigator.pop(context, v),
                      child: Column(
                        children: [
                          for (final e in _scheduleOptions.entries)
                            RadioListTile<String>(
                              value: e.key,
                              title: Text(e.value,
                                  style: const TextStyle(fontSize: 13)),
                            ),
                        ],
                      ),
                    ),
                  ],
                ),
              );
              if (picked == null || picked == current) return;
              final h = await ref.read(bootProvider.future);
              await h.api.setWatchSchedule(picked);
              ref.invalidate(detailRateLimitProvider);
            }
          : null,
    );
  }

  Widget _fold(BuildContext context,
      {required IconData icon,
      required String title,
      required List<Widget> children,
      EdgeInsets childrenPadding =
          const EdgeInsets.fromLTRB(14, 0, 14, 12)}) {    final scheme = Theme.of(context).colorScheme;
    return Theme(
      data: Theme.of(context).copyWith(dividerColor: Colors.transparent),
      child: ExpansionTile(
        initiallyExpanded: false,
        tilePadding: const EdgeInsets.symmetric(horizontal: 14),
        childrenPadding: childrenPadding,
        leading: Icon(icon, size: 20, color: scheme.onSurfaceVariant),
        title: Text(title, style: const TextStyle(fontSize: 13)),
        children: children,
      ),
    );
  }

  Widget _note(BuildContext context, String text) {
    final scheme = Theme.of(context).colorScheme;
    return Padding(
      padding: const EdgeInsets.only(bottom: 8),
      child: Text(text,
          style: TextStyle(
              fontSize: 11, color: scheme.onSurfaceVariant, height: 1.6)),
    );
  }

  // 测试种子日期（用户裁定 2026-11-26）：覆盖轮播/大图精选的日期种子键
  // （null = 跟随今天），用于人工验证按日轮换逻辑是否生效。
  Widget _seedDateRow(BuildContext context, WidgetRef ref) {
    final override = ref.watch(seedDateOverrideProvider);
    final now = DateTime.now();
    final set = override != null && override.isNotEmpty;
    return ListTile(
      contentPadding: const EdgeInsets.symmetric(horizontal: 14, vertical: 2),
      leading: const Icon(Icons.date_range, size: 20),
      title: Text('测试种子日期', style: const TextStyle(fontSize: 13)),
      subtitle: Text(
        set ? '覆盖为 $override（轮播/大图精选按此日期抽签）'
            : '跟随今天（${now.year * 10000 + now.month * 100 + now.day}）',
        style: const TextStyle(fontSize: 11, height: 1.4),
      ),
      trailing: set
          ? TextButton(
              onPressed: () =>
                  ref.read(seedDateOverrideProvider.notifier).state = null,
              child: const Text('恢复今天'),
            )
          : null,
      onTap: () async {
        final picked = await showDatePicker(
          context: context,
          initialDate: now,
          firstDate: DateTime(2020),
          lastDate: DateTime(now.year + 1),
        );
        if (picked == null) return;
        ref.read(seedDateOverrideProvider.notifier).state =
            '${picked.year * 10000 + picked.month * 100 + picked.day}';
      },
    );
  }
}
