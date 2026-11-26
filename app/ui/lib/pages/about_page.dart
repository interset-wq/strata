import 'package:flutter/material.dart';

import '../app/theme.dart';

/// App 信息页（设置 › 关于）：版本、许可与数据来源。纯静态信息，
/// 不依赖引擎；链接入口（GitHub / Issues / QQ 群）留在设置页。
class AboutPage extends StatelessWidget {
  const AboutPage({super.key});

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return Scaffold(
      appBar: AppBar(title: const Text('App 信息')),
      body: ListView(
        padding: const EdgeInsets.fromLTRB(16, 32, 16, 24),
        children: [
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
            '版本 1.0.0（build 1）',
            textAlign: TextAlign.center,
            style: TextStyle(fontSize: 12, color: scheme.onSurfaceVariant),
          ),
          const SizedBox(height: 24),
          Card(
            child: Column(
              children: [
                _row(context, '许可', 'AGPL-3.0（开源）'),
                _divider(context),
                _row(context, '数据来源', 'SFACG 菠萝包轻小说公开页面'),
                _divider(context),
                _row(context, '数据形态', '一次性内置种子 + 本机观测'),
              ],
            ),
          ),
          const SizedBox(height: 16),
          Text(
            '完全离线运行：内置只读种子库是收录书目的快照，关注、观察与'
            '浏览足迹只保存在本机。无账号、无云同步，不上传任何用户数据。',
            style: TextStyle(
              fontSize: 11,
              color: scheme.onSurfaceVariant,
              height: 1.6,
            ),
          ),
        ],
      ),
    );
  }

  Widget _row(BuildContext context, String label, String value) {
    final scheme = Theme.of(context).colorScheme;
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 11),
      child: Row(
        children: [
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
      color: scheme.outline,
    );
  }
}