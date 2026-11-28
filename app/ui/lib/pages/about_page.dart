import 'package:flutter/material.dart';
import 'package:package_info_plus/package_info_plus.dart';

import '../app/theme.dart';

/// App 信息页（设置 › 关于）：开源 app 常用风格——intro、技术栈、许可、
/// 数据来源。版本号从包配置读取（pubspec version/build），不再硬编码；
/// 不依赖引擎；链接入口（GitHub / Issues / QQ 群）留在设置页。
class AboutPage extends StatelessWidget {
  const AboutPage({super.key});

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return Scaffold(
      appBar: AppBar(title: const Text('App 信息')),
      body: FutureBuilder<PackageInfo>(
        future: PackageInfo.fromPlatform(),
        builder: (context, snap) {
          final info = snap.data;
          return ListView(
            padding: const EdgeInsets.fromLTRB(16, 32, 16, 24),
            children: [
              // App logo：用 fullbleed 完整图（foreground 是自适应图标的
              // 遮罩前景层，透明底，渲染出来与桌面图标完全不同——bug 修复
              // 2026-11-28），圆角对齐桌面图标的遮罩形状。
              ClipRRect(
                borderRadius: BorderRadius.circular(16),
                child: Image.asset(
                  'assets/icon/app-icon-fullbleed.png',
                  width: 72,
                  height: 72,
                ),
              ),
              const SizedBox(height: 10),
              Text(
                '书层 Strata',
                textAlign: TextAlign.center,
                style: const TextStyle(
                  fontFamily: StrataTokens.serif,
                  fontSize: 26,
                  fontWeight: FontWeight.w600,
                ),
              ),
              const SizedBox(height: 6),
              Text(
                info == null
                    ? '读取版本号…'
                    : '版本 ${info.version}（build ${info.buildNumber}）',
                textAlign: TextAlign.center,
                style: TextStyle(fontSize: 12, color: scheme.onSurfaceVariant),
              ),
              const SizedBox(height: 24),
              _section(
                context,
                '简介',
                // 与 GitHub 仓库 intro 保持一致（用户裁定 2026-11-27）。
                'Offline-first light-novel discovery app for SFACG: '
                'Flutter UI + embedded Go engine (FFI), a 248k-book local '
                'bibliography, and on-demand official lists & author '
                'tracking. AGPL-3.0.',
                icon: Icons.auto_stories,
              ),
              _section(
                context,
                '技术栈',
                null,
                icon: Icons.code,
                children: [
                  _row(context, '界面', 'Flutter（Material 3）',
                      icon: Icons.widgets),
                  _divider(context),
                  _row(context, '引擎', 'Go · dart:ffi · localhost HTTP',
                      icon: Icons.terminal),
                  _divider(context),
                  _row(context, '存储', 'SQLite（纯 Go 驱动，无 cgo）',
                      icon: Icons.storage),
                  _divider(context),
                  _row(context, '状态与路由', 'Riverpod · go_router',
                      icon: Icons.account_tree),
                ],
              ),
              _section(
                context,
                '许可',
                null,
                icon: Icons.gavel,
                children: [
                  _row(context, '本应用', 'AGPL-3.0', icon: Icons.copyright),
                  _divider(context),
                  InkWell(
                    onTap: () => showLicensePage(
                      context: context,
                      applicationName: '书层 Strata',
                      applicationVersion: info?.version ?? '',
                    ),
                    child: _row(context, '开源许可', '查看全部 ›',
                        icon: Icons.article),
                  ),
                ],
              ),
              _section(
                context,
                '数据来源',
                null,
                icon: Icons.public,
                children: [
                  _row(context, '书目', 'SFACG 菠萝包轻小说公开页面',
                      icon: Icons.menu_book),
                  _divider(context),
                  _row(context, '数据形态', '一次性内置种子 + 本机观测，不取正文',
                      icon: Icons.shield),
                ],
              ),
            ],
          );
        },
      ),
    );
  }

  Widget _section(BuildContext context, String title, String? body,
      {List<Widget>? children, IconData? icon}) {
    final scheme = Theme.of(context).colorScheme;
    return Padding(
      padding: const EdgeInsets.only(bottom: 16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              if (icon != null) ...[
                Icon(icon, size: 14, color: scheme.onSurfaceVariant),
                const SizedBox(width: 4),
              ],
              Text(title,
                  style: TextStyle(
                      fontSize: 11.5,
                      fontWeight: FontWeight.w600,
                      color: scheme.onSurfaceVariant)),
            ],
          ),
          const SizedBox(height: 6),
          Card(
            margin: EdgeInsets.zero,
            child: Column(
              children: [
                if (body != null)
                  Padding(
                    padding: const EdgeInsets.all(14),
                    child: Text(
                      body,
                      style: TextStyle(
                          fontSize: 12.5,
                          color: scheme.onSurface,
                          height: 1.6),
                    ),
                  )
                else ...?children,
              ],
            ),
          ),
        ],
      ),
    );
  }

  Widget _row(BuildContext context, String label, String value,
      {IconData? icon}) {
    final scheme = Theme.of(context).colorScheme;
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 11),
      child: Row(
        children: [
          if (icon != null) ...[
            Icon(icon, size: 15, color: scheme.onSurfaceVariant),
            const SizedBox(width: 8),
          ],
          Expanded(
            child: Text(
              label,
              style: TextStyle(fontSize: 13, color: scheme.onSurfaceVariant),
            ),
          ),
          Flexible(
            child: Text(
              value,
              textAlign: TextAlign.right,
              style: const TextStyle(fontSize: 13),
            ),
          ),
        ],
      ),
    );
  }

  Widget _divider(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return Container(
      height: 1,
      margin: const EdgeInsets.only(left: 14),
      color: scheme.outline.withValues(alpha: .5),
    );
  }
}
